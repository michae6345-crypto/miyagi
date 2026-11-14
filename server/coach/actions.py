"""Latency + action helpers: cancel-on-user-action, "Do it for me" patches, "where is X" grounding.

- `inflight.start(key, coro)` runs a coach call as a task and cancels the previous one with the
  same key; `inflight.cancel()` aborts everything (call it on any real user action). Cancelling
  closes the streaming HTTP request.
- `do_it_for_me(step, file, file_text)` → a minimal patch that compiles, for E4 to preview/apply.
- `locate(query, screen)` → screen targets: exact text match first (no model), else Claude Haiku
  over the set-of-mark screenshot. Opus stays for coaching. (Screen/code reading is Claude only.)
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Coroutine
from typing import Any

from . import llm
from .common import clamp_words, get_lesson, number_lines, step_brief, system_blocks
from .diagnose import LAST, notebook_code
from .hints import apply_fix
from .screen import ScreenContext

log = logging.getLogger("coach.actions")


# ---------- cancel on user action -------------------------------------------------------------

class Inflight:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, key: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Run `coro` as the current `key` task, cancelling the one it replaces."""
        self.cancel(key)
        task = asyncio.create_task(coro)
        self._tasks[key] = task
        task.add_done_callback(lambda t, k=key: self._tasks.pop(k, None) if self._tasks.get(k) is t else None)
        return task

    def cancel(self, key: str | None = None) -> int:
        """Cancel one key (or all when None). Returns how many tasks were cancelled."""
        keys = [key] if key is not None else list(self._tasks)
        n = 0
        for k in keys:
            t = self._tasks.pop(k, None)
            if t is not None and not t.done():
                t.cancel()
                n += 1
        return n

    def running(self) -> list[str]:
        return [k for k, t in self._tasks.items() if not t.done()]


inflight = Inflight()


# ---------- "Do it for me" ------------------------------------------------------------------------

PATCH_SYSTEM = """You write the smallest change that fixes the learner's current tutorial step, for a "Do it for me" button. The learner previews it before it is applied.
- Make EVERY edit the diagnosis asks for (if it says to change two things, change both) in one contiguous block; keep the learner's names and style; no unrelated edits, no comments about the change.
- yours: the exact contiguous line(s) to replace, copied from the numbered file (without the line numbers).
- expected: the replacement line(s), with the same indentation as in the file.
- line: 1-based line number of the first line of `yours`.
- command: if the fix is a terminal action instead (install a package, `git rebase --abort`), that one shell command and yours/expected ""; else "". Never `git add` / `--continue` while conflict markers remain.
- summary: one line, at most 12 words, imperative ("Lower Adam's learning rate to 1e-3").
- The result must be valid code (Python must compile) and must actually change something."""

PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "yours": {"type": "string"},
        "expected": {"type": "string"},
        "line": {"type": "integer"},
        "command": {"type": "string"},
    },
    "required": ["summary", "yours", "expected", "line", "command"],
    "additionalProperties": False,
}


def _result(file: str, patch: dict, summary: str, line: int | None, via: str) -> dict:
    return {
        "file": file,
        "unified_diff": patch["unified_diff"],
        "summary": clamp_words(summary, 14).rstrip("."),
        "line": line,
        "new_text": patch["new_text"],
        "requires_confirmation": True,
        "_meta": {"via": via},
    }


def _command_result(command: str, summary: str, via: str) -> dict:
    """A terminal fix: nothing to write; the app copies `command` (it never runs it)."""
    return {"file": None, "unified_diff": "", "summary": clamp_words(summary, 14).rstrip("."), "line": None,
            "new_text": None, "command": command, "requires_confirmation": True, "_meta": {"via": via}}


def _action_sentence(card: dict) -> str:
    """The card body's last sentence is its action ("Lower the learning rate to 1e-3")."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", card.get("body", "")) if x.strip()]
    return sentences[-1] if sentences else card.get("title", "Apply the suggested fix")


def missing_edits(action: str, expected: str) -> list[str]:
    """Values the action sentence asks for ("…to 1e-3", "…to `squash`") that the patch doesn't contain.
    S9 G1: the card said two edits, the diff made one, and the rebase 'succeeded' with nothing squashed."""
    wanted = re.findall(r"`([^`]+)`", action) + re.findall(r"\bto\s+([\w.+\-=/]+[\w)])", action)
    exp = expected.lower()
    stop = {"the", "a", "an", "it", "be", "use", "your", "their", "make", "keep", "match"}
    return [w for w in dict.fromkeys(wanted) if w.lower() not in stop and w.lower() not in exp]


async def do_it_for_me(step: dict, file: str, file_text: str, last_offtrack: dict | None = None, *, lesson: dict | None = None) -> dict:
    """A minimal patch that compiles: {file, unified_diff, summary, line, new_text, requires_confirmation},
    or a terminal fix {command, summary, file: None, new_text: None} when that is the fix.

    Reuses the latest diagnosis's diff when it applies cleanly AND makes every edit its action
    sentence names; otherwise asks Opus (up to two tries, the second told why the first failed).
    Rejects no-op patches. Never writes files or runs commands. Raises `CoachUnavailable`.
    """
    last = last_offtrack or LAST.get(step.get("id", "")) or {}
    action = _action_sentence(last) if last else ""
    error = ""
    if diff := last.get("diff"):
        if diff.get("command") and not diff.get("expected"):
            return _command_result(diff["command"], action or "Run this command", "diagnosis")
        p = apply_fix({**diff, "file": file}, file_text)
        missing = missing_edits(action, diff.get("expected", "")) if p["error"] is None else []
        if p["error"] is None and not missing:
            return _result(file, p, action, diff.get("line"), "diagnosis")
        error = p["error"] or f"the diagnosis's diff misses part of the fix: {', '.join(missing)}"

    lesson = lesson if lesson is not None else get_lesson()
    for attempt in range(2):
        user = "\n\n".join(
            x
            for x in [
                f"CURRENT STEP:\n{step_brief(step)}",
                f"DIAGNOSIS: {last.get('title')} — {last.get('body')}" if last else "",
                f"PREVIOUS ATTEMPT FAILED: {error}" if error else "",
                f"FILE {file}, numbered:\n{number_lines(notebook_code(file_text), 400)}",
                "Write the patch.",
            ]
            if x
        )
        try:
            res = await llm.structured_call(
                purpose="do_it_for_me", model=llm.OPUS, system=system_blocks(PATCH_SYSTEM, lesson),
                user_text=user, schema=PATCH_SCHEMA, effort="low", max_tokens=8000, timeout=40.0,
            )
        except llm.CoachLLMError as e:
            raise llm.CoachUnavailable(f"could not write a patch: {e}") from e
        d = res.data
        if (d.get("command") or "").strip() and not (d.get("expected") or "").strip():
            return _command_result(d["command"].strip(), d["summary"], f"opus#{attempt + 1}")
        p = apply_fix({"yours": d["yours"], "expected": d["expected"], "line": d.get("line"), "file": file}, file_text)
        missing = missing_edits(action, d["expected"]) if p["error"] is None else []
        if p["error"] is None and not missing:
            return _result(file, p, d["summary"], d.get("line"), f"opus#{attempt + 1}")
        error = p["error"] or f"the patch misses part of the fix: {', '.join(missing)}"
        log.info("do_it_for_me attempt %d rejected: %s", attempt + 1, error)
    raise llm.CoachUnavailable(f"no safe patch: {error}")


# ---------- "where is X" -----------------------------------------------------------------------------

LOCATE_SYSTEM = """You ground a short request ("where is X") on a screenshot for a tutorial overlay. The images are the whole screen with numbered boxes and a full-resolution crop around the cursor (red ring); the BOXES list gives each box's text. Answer with the ids of the boxes that are X, best first (at most 3), or [] if X is not visible. Only ids from the list."""

LOCATE_SCHEMA = {
    "type": "object",
    "properties": {"box_ids": {"type": "array", "items": {"type": "integer"}}},
    "required": ["box_ids"],
    "additionalProperties": False,
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def text_matches(query: str, screen: ScreenContext) -> list[int]:
    """Boxes whose text contains the query (whitespace/case-insensitive), tightest first."""
    q = _norm(query)
    if not q:
        return []
    hits = [b for b in screen.boxes if q in _norm(b.text)]
    return [b.id for b in sorted(hits, key=lambda b: len(b.text))]


async def locate(query: str, screen: ScreenContext, *, use_model: bool = True) -> list[dict]:
    """Resolve "where is X" to targets [{boxId, label, text, rect}].

    Exact text on screen → no model. Otherwise Claude Haiku picks set-of-mark box ids (Opus stays
    for coaching). Raises CoachUnavailable when it cannot ask the model.
    """
    if ids := text_matches(query, screen):
        return screen.resolve_targets([{"box_id": i, "label": query[:24]} for i in ids[:3]])
    if not use_model:
        return []
    ask = f'Find: "{query}"'
    try:
        res = await llm.structured_call(
            purpose="locate", model=llm.HAIKU, system=[{"type": "text", "text": LOCATE_SYSTEM}],
            user_text=f"{ask}\n\n{screen.text()}", user_content=[{"type": "text", "text": ask}, *screen.claude_content()],
            schema=LOCATE_SCHEMA, effort="low", max_tokens=2000, timeout=10.0,
        )
    except llm.CoachLLMError as e:
        raise llm.CoachUnavailable(f"locate failed: {e}") from e
    return screen.resolve_targets([{"box_id": i, "label": query[:24]} for i in res.data.get("box_ids", [])[:3]])
