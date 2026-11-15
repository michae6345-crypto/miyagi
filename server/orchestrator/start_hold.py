"""Desktop test 6 (Nov 15, 03:33-03:41, T6-CP3 / CP15): after "Start the lesson" on the Before-you-start sheet the
engine stayed held (phase "ready") until the learner clicked into VS Code: no type box, no checks, both runs. And
VS Code opened scrolled to the very bottom of nn.py (only its empty line 14 on screen; step 1's line 5 off it).

- The hold (E4) gates checks / judge / coaching only. The step's type box goes up under it (session.emit no longer
  drops a box while held; start_step places it as for any step) and follows app switches (on_front_switch).
- Any learner action from the app releases it (session.START_ACTIONS: install, skip_setup, explain, diagram, ask, ...
  were missing, so T6's Install left step 1 held). So does `front_input`: a key / click after the lesson's VS Code
  window, showing the step's file, came to the front under the hold. "Start the lesson" is a click on the overlay,
  which never takes focus, so it lands with VS Code in front; E5 books it as Miyagi's (not lesson work), so
  _maybe_begin's "a key / click in the lesson's editor" missed it.
- `reveal_step_line`: once per step (and again on Continue) the step's line is scrolled into view in the lesson's
  own VS Code window through the companion extension (POST /open: file + line, preserveFocus), the cursor where the
  code goes. Never under the learner's typing, never when that line is on screen already or the step's box is up.

Hooks in LessonSession (kept tiny for merges): emit, start_step, resume, _maybe_begin, on_front_switch.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from . import where_row

log = logging.getLogger("orchestrator.session")

REVEAL_WAIT_S = 30.0  # VS Code may still be opening at step start (t6: ~2 s, its extension ~3 s more; longer while
REVEAL_POLL_S = 1.0  # the auto-open waits for the learner to leave Miyagi's launcher)
TYPING_WAIT_S = 10.0  # the learner keeps typing this long: no reveal on this step (never under a keystroke)


def _code_app(app: str) -> bool:
    from .session import CODE_APP_NAMES

    return app.strip().lower() in CODE_APP_NAMES


# ------------------------------------------------------------------ the hold's "VS Code in front" release

def note_front(s: Any, app: str) -> None:
    """on_front_switch while held: remember when the lesson's editor came to the front (another app: forget it).
    Miyagi's own overlay never counts (the sheet's buttons are clicked with VS Code still in front)."""
    a = (app or "").strip().lower()
    if not a or a in s.OVERLAY_APPS:
        return
    s._held_front = (s._hold_t, s.clock()) if _code_app(a) else None


async def front_input(s: Any) -> bool:
    """tick, while held: the lesson's VS Code window is the app in front (the window server's; the overlay never
    counts) on the step's file, and the learner pressed a key / clicked since it came to the front after lesson.ready
    (any key / click: "Start the lesson" on the overlay is one) -> True: start the step."""
    step = s.step
    front = s._live_front()
    if step is None or not front or not _code_app(front) or s._lesson_window_hidden():
        if front and front.strip().lower() not in s.OVERLAY_APPS:
            s._held_front = None
        return False
    now, seen = s.clock(), getattr(s, "_held_front", None)
    if seen is None or seen[0] != s._hold_t:  # first seen in front under this hold: only input after this counts
        s._held_front = (s._hold_t, now)
        return False
    since = getattr(s.inputs, "seconds_since_input", None) if s.inputs is not None else None
    v = since() if callable(since) else None
    if v is None or v >= now - seen[1]:
        return False
    want = Path(s._step_file(step) or "").name
    try:
        info = await asyncio.to_thread(where_row.lesson_active_file, s.workdir, getattr(s.last_obs, "windows", None))
    except Exception:  # noqa: BLE001 - unknown: VS Code in front on the lesson's window is enough
        info = None
    if want and info and info.get("file") and info["file"] != want:
        return False  # the lesson's window shows another file (README.md): not the lesson file yet
    return True


# ------------------------------------------------------------------ the step's line on screen

def _line_end(lines: list[str], line: int) -> int:
    return len(lines[line - 1].rstrip()) + 1 if 0 < line <= len(lines) else 1


def _target(s: Any, step: dict) -> tuple[str, int, int] | None:
    """(file, 1-based line, column) to show for the step: where its code goes (the row _insert_plan / the type box
    picks, or the end of the line above when that row already holds the next section), where typing goes on
    (_code_progress), else its target's anchor. None: a run step, all of its code typed, no file."""
    if s._run_command(step):
        return None
    plan = s._insert_plan(step)
    if plan is not None:
        lines, ins, above = plan["lines"], int(plan["ins"]), int(plan["above"])
        if ins > len(lines):  # after the file's last line: the end of that line (Enter opens the new one)
            return str(plan["path"]), max(1, len(lines)), _line_end(lines, len(lines))
        if above and lines[ins - 1].strip():  # that row holds the next section: the end of the line above it
            return str(plan["path"]), above, _line_end(lines, above)
        return str(plan["path"]), max(1, ins), 1  # an empty row: its start
    prog = s._code_progress(step)
    if prog is not None:
        if prog.get("kind") == "done":
            return None
        _p, lines = s._step_lines(step)
        return str(prog["path"]), int(prog["line"]), _line_end(lines, int(prog["line"]))
    from . import workspace as wsmod

    loc = wsmod.target_location(s.workdir, step, missing="end")
    if loc is None:
        return None
    try:
        lines = Path(loc[0]).read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    line = max(1, min(int(loc[1]), len(lines) or 1))
    return str(loc[0]), line, _line_end(lines, line)


def _visible(win: dict, path: str, line: int) -> bool:
    f = win.get("file")
    try:
        same = bool(f) and Path(str(f)).resolve() == Path(path).resolve()
    except OSError:
        same = False
    return same and any(int(r.get("startLine") or 0) <= line <= int(r.get("endLine") or 0)
                        for r in win.get("visibleRanges") or [])


def _reveal_once(s: Any, ext: Any, step: dict) -> str:
    """One try (blocking): "no_window" (the lesson's VS Code window isn't up yet), "revealed", or why not."""
    target = _target(s, step)
    if target is None:
        return "no_line"
    w, _ = where_row._lesson_ext_window(s.workdir)
    if w is None:
        return "no_window"
    path, line, col = target
    if _visible(w, path, line):
        return "visible"
    res = ext.open_file(path, line, column=col, folder=s.workdir, preserve_focus=True, port=int(w["port"]))
    if not (isinstance(res, dict) and res.get("ok")):
        return f"failed ({(res or {}).get('error') if isinstance(res, dict) else 'no answer'})"
    log.info("t6: revealed %s:%s in the lesson's VS Code window (was %s)", Path(path).name, line,
             ", ".join(f"{r.get('startLine')}-{r.get('endLine')}" for r in w.get("visibleRanges") or []) or "no editor")
    return "revealed"


def _box_up(s: Any, gen: int) -> bool:
    own = getattr(s, "_spot_owner", None)
    return s.spot_rect is not None and own is not None and own[0] == "step" and own[1] == gen


async def reveal_step_line(s: Any, step: dict, again: bool = False) -> bool:
    """Step start (once per step) / Continue (again=True): put the step's line on screen in the lesson's own VS Code
    window (companion extension), waiting for that window while VS Code opens. -> revealed."""
    gen = s.step_gen
    if not s.lesson_mode or (not again and getattr(s, "_revealed_gen", None) == gen):
        return False
    s._revealed_gen = gen
    if getattr(getattr(s, "screen", None), "reader", None) is None or not s.workdir:
        return False  # tests / no screen reader: never the real editor (as session._vscode_ext)
    try:  # not session._vscode_ext(): it is None until a window answers, and VS Code may still be opening
        from server.workspace import vscode_ext as ext
    except Exception:  # noqa: BLE001
        return False
    waited = typed = 0.0
    while True:
        if gen != s.step_gen or s.step is not step or s.passed or s.awaiting_resume or _box_up(s, gen):
            return False  # moved on / paused / the box is up (its line is on screen)
        if s.typing():
            if typed >= TYPING_WAIT_S:
                log.info("t6: no reveal of %s's line: the learner is typing", step.get("id"))
                return False
            typed += 0.5
            await asyncio.sleep(0.5)
            continue
        try:
            why = await asyncio.to_thread(_reveal_once, s, ext, step)
        except Exception:  # noqa: BLE001 - a convenience: the lesson runs without it
            log.exception("t6: revealing the step's line failed")
            return False
        if why != "no_window" or waited >= REVEAL_WAIT_S:
            if why not in ("revealed", "visible", "no_line"):
                log.info("t6: no reveal of %s's line: %s", step.get("id"), why)
            return why == "revealed"
        waited += REVEAL_POLL_S
        await asyncio.sleep(REVEAL_POLL_S)
