"""The session's link to the skill tree (server/skilltree): which steps were helped, and what a pass records.

    note_assist(s, kind)            an action on the step: Show me, Do it for me, or the HINT_ASSIST_LEVEL-th hint
    note_card(s, type_, payload)    a card / off-track going out: a level-3 one (the exact fix) makes its step assisted
    tags(s)                         stepId -> catalog skill ids for the running lesson (cached per graph)
    await on_pass(s, step, skipped) record the pass (or a skip of a due review), keep a proof; -> step.passed fields

Assisted (contract StepPassed.assisted): passed after Show me's snippet, a level-3 hint or Do it for me. An assisted pass
counts as practice, never toward mastery, and keeps no proof (it is not only the learner's own work). Kept per step id
for the lesson; a new lesson starts clean. The work runs in a thread and never raises into the lesson.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("orchestrator")

ASSIST_KINDS = frozenset({"show_me", "apply_fix", "run_command"})  # run_command: "Run it for me"
HINT_ASSIST_LEVEL = 3  # the third hint on a step gives the answer away
MAX_READ = 200_000


def _assist_state(s: Any) -> dict:
    got = getattr(s, "_skill_assisted", None)
    lesson = ((getattr(s, "graph", None) or {}).get("lesson") or {}).get("id")
    if not isinstance(got, dict) or got.get("lesson") != lesson:
        got = {"lesson": lesson, "steps": set(), "hints": {}}
        s._skill_assisted = got
    return got


def assisted(s: Any, step_id: str) -> bool:
    return step_id in _assist_state(s)["steps"]


def note_assist(s: Any, kind: str, step: dict | None = None) -> None:
    step = step if step is not None else getattr(s, "step", None)
    if not isinstance(step, dict) or not step.get("id"):
        return
    st = _assist_state(s)
    if kind == "hint":
        n = st["hints"][step["id"]] = st["hints"].get(step["id"], 0) + 1
        if n >= HINT_ASSIST_LEVEL:
            st["steps"].add(step["id"])
    elif kind in ASSIST_KINDS:
        st["steps"].add(step["id"])


FIX_LEVEL = 3  # hint ladder (server/coach/hints.LEVELS, contract Offtrack.level): 3 = the exact fix ("diff")


def note_card(s: Any, type_: str, payload: dict | None) -> None:
    """Session.emit, as a `card` / `offtrack` really goes out: a level-3 card gives the answer away, whether the
    learner asked for it (a Hint) or the engine sent it on its own (the off-track ladder's repeat / stuck card, the
    Demo's sign-bug card), so its step's pass is assisted. Like Show me, only once its content is shown: a
    withdrawal (dismissAfterMs / clear) or a card that never reaches the app marks nothing."""
    if type_ not in ("card", "offtrack") or not isinstance(payload, dict) or payload.get("clear"):
        return
    if payload.get("dismissAfterMs") is not None and not (payload.get("title") or payload.get("body")):
        return  # an empty off-track withdrawal (advice_clear)
    try:
        level = int(payload.get("level") or 0)
    except (TypeError, ValueError):
        level = 0
    if level < FIX_LEVEL and payload.get("levelName") != "diff":
        return
    sid = payload.get("stepId")
    cur = getattr(s, "step", None)
    step = cur if isinstance(cur, dict) and (not sid or cur.get("id") == sid) else ({"id": sid} if sid else None)
    try:
        note_assist(s, "show_me", step)
    except Exception as e:  # noqa: BLE001 - the skill tree must never cost the card itself
        log.warning("skill tree: could not mark %s assisted: %s", sid, e)


def tags(s: Any) -> dict[str, list[str]]:
    from server.skilltree import tagging

    g = getattr(s, "graph", None) if isinstance(getattr(s, "graph", None), dict) else {}
    steps = list(getattr(s, "steps", None) or g.get("steps") or [])
    # keyed on the lesson and its step ids, never id(graph): CPython reuses a freed dict's address
    sig = ((g.get("lesson") or {}).get("id"), tuple(st.get("id") if isinstance(st, dict) else None for st in steps))
    cached = getattr(s, "_skilltree_tags", None)
    if cached is not None and cached[0] == sig:
        return cached[1]
    out = tagging.tag_graph({"lesson": g.get("lesson") or {}, "steps": steps})
    s._skilltree_tags = (sig, out)
    return out


def _read_file(workdir: str | None, rel: str | None) -> tuple[str | None, str | None]:
    """The learner's file, inside the lesson folder only, never a secret file or a big one. (text, path relative)."""
    if not rel:
        return None, None
    try:
        from server.redact import is_secret_file

        root = Path(workdir or ".").resolve()
        p = (root / rel).resolve()
        if root not in p.parents:
            return None, None
        ref = os.path.relpath(p, root)
        if is_secret_file(p) or not p.is_file() or p.stat().st_size > MAX_READ:
            return None, ref
        return p.read_text(encoding="utf-8", errors="replace"), ref
    except (OSError, ValueError):
        return None, None


def _source_lesson(lesson: dict) -> dict:
    """A review lesson ("review-<skill>-<lesson>", lesson.review.lessonId) records its passes and proofs under the
    lesson it replays, so the same underlying step keeps one key in the skill record."""
    rv = lesson.get("review") if isinstance(lesson.get("review"), dict) else {}
    src = rv.get("lessonId")
    if not isinstance(src, str) or not src:
        return lesson
    title = rv.get("lessonTitle")
    return {**lesson, "id": src, **({"title": title} if isinstance(title, str) and title else {})}


def record(step: dict, skill_ids: list[str], *, assisted: bool, skipped: bool, lesson: dict | None,
           workdir: str | None, run: Any = None, now: float | None = None) -> dict:
    """Blocking part of on_pass (a worker thread): {"events": [...], "proofId"?}."""
    from server.skilltree import ledger, proofs

    lesson = _source_lesson(lesson or {})
    if not skill_ids:
        return {"events": []}
    if skipped:  # a skip is never a pass; it misses the reviews that were due
        due = [sid for sid in skill_ids if ((ledger.skill_row(sid, now=now) or {}).get("review") or {}).get("due")]
        return {"events": [ev for sid in due if (ev := ledger.record_review(sid, False, now=now))]}
    if step.get("kind") == "read":
        return {"events": []}
    pid = None
    if not assisted:
        try:
            text, ref = _read_file(workdir, step.get("file"))
            body = proofs.build(step, file_text=text, file_ref=ref, run=run)
            if body:
                pid = proofs.save(body, skill_ids=skill_ids, lesson=lesson, step=step, now=now)
        except Exception as e:  # noqa: BLE001 - a proof is optional
            log.warning("skill tree: no proof kept: %s", e)
    evs = ledger.record_pass(skill_ids, lesson_id=lesson.get("id"), step_id=step.get("id"), assisted=assisted, now=now,
                             proof_id=pid, lesson_title=lesson.get("title"), step_title=step.get("title"))
    return {"events": evs, **({"proofId": pid} if pid else {})}


async def on_pass(s: Any, step: dict | None, skipped: bool = False) -> dict:
    """The ui-v4 step.passed fields for this pass: {key, assisted, skillIds, proofId?} ({key} alone when the step
    practises no catalog skill). Never raises."""
    if not isinstance(step, dict) or not step.get("id"):
        return {}
    lesson = dict(((getattr(s, "graph", None) or {}).get("lesson") or {}))
    src = _source_lesson(lesson)  # a review pass keys on the lesson it replays (activity_feed.step_key agrees)
    out: dict[str, Any] = {"key": f"{src.get('id') or 'lesson'}:{step['id']}"}
    try:
        ids = tags(s).get(step["id"]) or []
        helped = assisted(s, step["id"])
        if not skipped:
            out["assisted"] = helped
        if not ids:
            return out
        out["skillIds"] = list(ids)
        runs = list(getattr(s, "step_runs", None) or [])
        run = next((r for r in reversed(runs) if getattr(r, "exit_code", None) == 0), None)
        got = await asyncio.to_thread(record, step, ids, assisted=helped, skipped=skipped, lesson=lesson,
                                      workdir=getattr(s, "workdir", None), run=run)
        if got.get("proofId"):
            out["proofId"] = got["proofId"]
        s.skill_events = got.get("events") or []
    except Exception as e:  # noqa: BLE001 - the skill tree must never break the lesson
        log.warning("skill tree: could not record %s: %s", step.get("id"), e)
    return out
