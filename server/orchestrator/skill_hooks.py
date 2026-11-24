"""The session's link to the skill tree (server/skilltree): which steps were helped, and what a pass adds.

    note_assist(s, kind)            the learner pressed hint / show me / Do it for me / Run it for me on the step
    await on_pass(s, step, skipped) a step passed (or was skipped): record it, keep a proof, return the update payload

Assisted = any ASSIST_KINDS action on that step (kept per step id for the lesson; a new lesson starts clean). The work
runs in a thread and never raises into the lesson: the skill tree is an extra.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("orchestrator")

ASSIST_KINDS = frozenset({"hint", "show_me", "apply_fix", "run_command"})
MAX_READ = 200_000


def _assisted(s: Any) -> set:
    got = getattr(s, "_skill_assisted", None)
    lesson = ((getattr(s, "graph", None) or {}).get("lesson") or {}).get("id")
    if got is None or got[0] != lesson:
        got = (lesson, set())
        s._skill_assisted = got
    return got[1]


def note_assist(s: Any, kind: str) -> None:
    step = getattr(s, "step", None)
    if kind in ASSIST_KINDS and isinstance(step, dict) and step.get("id"):
        _assisted(s).add(step["id"])


def tags(s: Any) -> dict[str, list[str]]:
    """stepId -> catalog skill ids for the running lesson (cached per graph)."""
    from server.skilltree import tagging

    g = getattr(s, "graph", None) if isinstance(getattr(s, "graph", None), dict) else {}
    steps = list(getattr(s, "steps", None) or g.get("steps") or [])
    sig = (id(g), len(steps))
    cached = getattr(s, "_skilltree_tags", None)
    if cached is not None and cached[0] == sig:
        return cached[1]
    out = tagging.tag_graph({"lesson": g.get("lesson") or {}, "steps": steps})
    s._skilltree_tags = (sig, out)
    return out


def _read_file(workdir: str | None, rel: str | None) -> tuple[str | None, str | None]:
    if not rel:
        return None, None
    try:
        from server.redact import is_secret_file

        root = Path(workdir or ".").resolve()
        p = (root / rel).resolve()
        if root not in p.parents and p != root:
            return None, None  # never outside the lesson folder
        if is_secret_file(p) or not p.is_file() or p.stat().st_size > MAX_READ:
            return None, os.path.relpath(p, root)
        return p.read_text(encoding="utf-8", errors="replace"), os.path.relpath(p, root)
    except (OSError, ValueError):
        return None, None


def record(step: dict, skill_ids: list[str], *, assisted: bool, skipped: bool, lesson_id: str | None,
           workdir: str | None, run: Any = None, now: float | None = None) -> dict | None:
    """Blocking part of on_pass (a worker thread). Returns the update payload, or None when nothing changed."""
    from server.skilltree import api, ledger, proofs

    if not skill_ids:
        return None
    if skipped:  # a skip is never a pass; it misses the reviews that were due
        due = [sid for sid in skill_ids if ((ledger.skill_row(sid, now=now) or {}).get("review") or {}).get("due")]
        evs = [ev for sid in due if (ev := ledger.record_review(sid, False, now=now))]
        return api.update(evs, now=now, skill_ids=skill_ids) if evs else None
    if step.get("kind") == "read":
        return None
    pid = None
    try:
        text, ref = _read_file(workdir, step.get("file"))
        body = proofs.build(step, file_text=text, file_ref=ref, run=run)
        if body and not assisted:
            pid = proofs.save(body, skill_ids=skill_ids, lesson_id=lesson_id, step_id=step.get("id"), now=now)
    except Exception as e:  # noqa: BLE001 - a proof is optional
        log.warning("skill tree: no proof kept: %s", e)
    evs = ledger.record_pass(skill_ids, lesson_id=lesson_id, step_id=step.get("id"), assisted=assisted, now=now,
                             proof_id=pid)
    return api.update(evs, now=now, skill_ids=skill_ids)


async def on_pass(s: Any, step: dict | None, skipped: bool = False) -> dict | None:
    if not isinstance(step, dict) or not step.get("id"):
        return None
    try:
        ids = tags(s).get(step["id"]) or []
        if not ids:
            return None
        lesson_id = ((getattr(s, "graph", None) or {}).get("lesson") or {}).get("id")
        runs = list(getattr(s, "step_runs", None) or [])
        run = next((r for r in reversed(runs) if getattr(r, "exit_code", None) == 0), None)
        return await asyncio.to_thread(record, step, ids, assisted=step["id"] in _assisted(s), skipped=skipped,
                                       lesson_id=lesson_id, workdir=getattr(s, "workdir", None), run=run)
    except Exception as e:  # noqa: BLE001 - the skill tree must never break the lesson
        log.warning("skill tree: could not record %s: %s", step.get("id"), e)
        return None
