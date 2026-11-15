"""No ⌘S chores, no flicker (Michael, Nov 15 after test 6: "do you need to make it do ctrl+s every time? ... it's not
updating quickly ... remember that humans are doing this").

Grading already reads VS Code's exact buffer (editor_text.EditorBuffers). This module removes the save chores around it:

    await intercept(s, card)     _emit_card: a card that asks for ⌘S -> the step's file is saved through the companion
                                 extension instead (POST /save, 0.0.3: an empty edit + save) and the card is dropped (or
                                 its ⌘S sentence is); only when the extension can't save does the learner see it
    on_vscode_event(s, ev)       the extension's dirty / save / editor events -> the step is re-graded within ~0.2 s
    await poll(s)                tick (1/s): the step file's buffer changed -> re-grade now (no 2-5 s scene look wait);
                                 a run step's unsaved fix is saved after ~1 s of quiet, so a terminal run runs it
    already_done(s, step)        a code step whose whole code and every check pattern are in the file already
    await advance(s, gen, idx)   after a pass: steps whose code is already in the file pass at once, then ONE step
                                 starts with ONE card "You already did steps 2–3" (never a cascade of starts / cards)
                                 (never in a Demo lesson: the presenter passes every step on cue, stage.py)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Any

from . import stage

log = logging.getLogger("orchestrator.quiet_save")

RETRY_S = 3.0  # a save the extension refused / couldn't reach: the card goes out, and no new try for this long
RUN_AUTOSAVE_QUIET_S = 1.0  # a run step's file: saved once the buffer has been still this long
_UNTITLED = re.compile(r"untitled|unsaved .{0,40}\btab\b|\(⌘S\) as\b", re.I)
_SAVE_ASK = re.compile(r"⌘S|\bsave\b.*\bso I can check\b", re.I)
_SAVE_TITLE = re.compile(r"^(save\b|save to finish)", re.I)


# "In nn.py, delete line 12 (…), then save with ⌘S." (stale_advice's Do it for me over unsaved edits): only the save
# clause goes, the instruction stays. Dropping the whole sentence dropped the whole card, so Do it for me showed nothing.
_SAVE_CLAUSE = re.compile(r",?\s+(?:and\s+)?then\s+save\b[^!?]*?(?:with\s+⌘S|\(⌘S\))(?=[.!?]?$)", re.I)


def _without_save(sentence: str) -> str:
    """A sentence that asks for something else first, then ⌘S: that something else, ending as it did."""
    m = _SAVE_CLAUSE.search(sentence)
    if m is None or not sentence[:m.start()].strip():
        return sentence
    return sentence[:m.start()].rstrip(" ,") + sentence[m.end():]


def is_save_prompt(card: dict) -> bool:
    text = f"{card.get('title') or ''}\n{card.get('body') or ''}"
    return "⌘S" in text and not _UNTITLED.search(text) and card.get("kind") not in ("where", "setup", "resume")


def _step_path(s: Any, step: dict) -> Path | None:
    from . import workspace as wsmod

    f = s._step_file(step) or step.get("file") or ""
    try:
        return wsmod.resolve_file(s.workdir, f) if f else None
    except Exception:  # noqa: BLE001
        return None


async def save_now(s: Any, step: dict, why: str) -> bool | None:
    """Save the step's file through the companion. -> True saved, False nothing unsaved, None couldn't (no extension)."""
    st = s.__dict__.setdefault("_quiet_save", {"failed_t": -1e9})
    if time.monotonic() - st["failed_t"] < RETRY_S:
        return None
    try:
        saved = await s._save_step_file(step)
    except Exception:  # noqa: BLE001
        log.exception("quiet save failed")
        saved = False
    if saved:
        log.info("saved %s quietly (%s)", (_step_path(s, step) or Path("?")).name, why)
        return True
    if s._dirty_step_file(step):  # still unsaved: the extension isn't there (or refused)
        st["failed_t"] = time.monotonic()
        return None
    return False


async def intercept(s: Any, card: dict) -> dict | None:
    """-> the card to send (as it was, or without its ⌘S sentence), or None: the save was done instead."""
    step = getattr(s, "step", None)
    if step is None or not is_save_prompt(card) or (card.get("stepId") not in (None, step.get("id"))):
        return card
    if not getattr(s, "lesson_mode", False) or getattr(s, "_untitled_editor", lambda: None)():
        return card
    res = await save_now(s, step, f"instead of {card.get('title')!r}")
    if res is None:
        return card  # the extension can't save it: the learner has to (the one case a ⌘S card is right)
    s._spawn(s.evaluate("file"))  # graded on the saved file now (the watcher would take up to 0.5 s)
    name = (_step_path(s, step) or Path(step.get("file") or "file")).name
    title, body = str(card.get("title") or ""), str(card.get("body") or "")
    rest = " ".join(x for x in map(_without_save, re.split(r"(?<=[.!?])\s+", body.strip()))
                    if x and not _SAVE_ASK.search(x)).strip()
    if "Do it for me" in body:  # "Save nn.py first / Press ⌘S, then Do it for me again."
        return {**card, "title": f"Saved {name}", "body": "Press Do it for me again."}
    if _SAVE_TITLE.match(title) and not rest:
        return None  # "Save to finish" / "Save nn.py" / "Save so I can check": done, the re-grade speaks
    if title == "You fixed it" and not rest:
        return {**card, "body": "Checking it now."}
    return {**card, "body": rest} if rest else None


# ------------------------------------------------------------------ freshness (~1 s, not the 2-5 s scene looks)
def _buffer_sig(s: Any, step: dict) -> str | None:
    p = _step_path(s, step)
    if p is None:
        return None
    text = s._buffers.text(p)
    if text is None:
        try:
            text = p.read_text(errors="replace")
        except OSError:
            return None
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def _live(s: Any) -> dict | None:
    step = getattr(s, "step", None)
    if (step is None or s.passed or s.phase != "active" or s.awaiting_resume or s.awaiting_start
            or not getattr(s, "lesson_mode", False)):
        return None
    return step


async def regrade(s: Any, why: str) -> None:
    step = _live(s)
    if step is None:
        return
    st = s.__dict__.setdefault("_quiet_save", {"failed_t": -1e9})
    p = _step_path(s, step)
    if p is not None:
        await s._buffers.refresh([p], s.workdir)
    sig = _buffer_sig(s, step)
    if sig is not None and sig == st.get("sig") and why == "poll":
        return
    changed = sig is not None and st.get("sig") not in (None, sig)
    st["sig"], st["sig_t"] = sig, time.monotonic()
    if changed or why != "poll":
        await s.evaluate("edit")
    if changed and s._run_command(step) and s._dirty_step_file(step):  # a run step: its fix is what runs next
        st["run_save_due"] = (s.step_gen, time.monotonic() + RUN_AUTOSAVE_QUIET_S)


async def poll(s: Any) -> None:
    """tick: re-grade when the buffer changed; save a run step's still buffer (a terminal run reads the disk)."""
    if _live(s) is None:
        return
    await regrade(s, "poll")
    st = s.__dict__.get("_quiet_save") or {}
    due = st.get("run_save_due")
    if due is not None and due[0] != s.step_gen:  # (audit) that run step is over: never a save of the next step's
        st["run_save_due"] = due = None  # half-typed code on its behalf
    if due is not None and time.monotonic() >= due[1] and (step := _live(s)) is not None:
        st["run_save_due"] = None
        if await save_now(s, step, "run step: the fix runs next") and _live(s) is step:
            await s.evaluate("file")


def on_vscode_event(s: Any, ev: dict) -> None:
    """POST /vscode/event: a dirty / save / editor change of the step's file -> re-grade now."""
    if ev.get("type") not in ("dirty", "save", "editor") or _live(s) is None:
        return
    s._spawn(regrade(s, ev.get("type") or "event"))


# ------------------------------------------------------------------ skipping ahead: one card, no cascade
def already_done(s: Any, step: dict) -> bool:
    """A code step whose code is already in its file (VS Code's buffer, else the disk): every non-blank line of the
    step's code AND every check pattern. Run / setup steps never count (they need their run)."""
    code = (step.get("code") or "").strip()
    if not code or step.get("setup") or s._run_command(step) or step.get("kind") not in (None, "code"):
        return False
    p = _step_path(s, step)
    if p is None:
        return False
    text = s._buffers.text(p)
    if text is None:
        try:
            text = p.read_text(errors="replace")
        except OSError:
            return False
    have = {ln.strip() for ln in text.splitlines() if ln.strip()}
    if any(ln.strip() not in have for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("#")):
        return False
    pats = [c.get("pattern") for c in step.get("checks") or [] if c.get("pattern")]
    try:
        return bool(pats) and all(re.search(pt, text, re.M) for pt in pats)
    except re.error:
        return False


async def advance(s: Any, gen: int, idx: int) -> None:
    """_pass_step's advance: code steps already done pass without starting (one step.passed each, no cards), then the
    first step not done starts, with one card when steps were jumped. Never moves backwards; the last step always
    starts (its pass ends the lesson)."""
    await asyncio.sleep(s.advance_delay_s)
    if gen != s.step_gen or idx <= s.idx:
        return  # Back / goto / a newer pass moved on meanwhile: never jump back over it
    jumped: list[int] = []
    try:
        p = _step_path(s, s.steps[idx])
        if p is not None:
            await s._buffers.refresh([p], s.workdir)
        while idx < len(s.steps) - 1 and not stage.on(s) and already_done(s, s.steps[idx]):  # a Demo: every step on cue
            jumped.append(idx)
            idx += 1
    except Exception:  # noqa: BLE001 - never blocks the advance
        log.exception("skip-ahead check failed")
    if gen != s.step_gen:
        return
    for j in jumped:
        payload = {"stepId": s.steps[j]["id"], "nextStepId": s.steps[j + 1]["id"], "already": True}
        await s.emit("step.passed", payload)
        s._record("step_passed", {"nextStepId": payload["nextStepId"], "already": True}, s.steps[j])
    await s.start_step(idx)
    if jumped and s.step is s.steps[idx]:
        a, b = jumped[0] + 1, jumped[-1] + 1
        which = f"step {a}" if a == b else f"steps {a}–{b}"
        log.info("skipped ahead past %s: their code is already in the file", which)
        await s._emit_card({"stepId": s.steps[idx]["id"], "kind": "step", "title": f"You already did {which}",
                            "body": f"Their code is already in your file. On to step {idx + 1}."}, window_s=5.0)
