"""Run-step pointing after desktop test 7 (Nov 15, Demo mode): the Run ▷ found on time, and Hint / Show me on a run whose
problem is in the code pointing at that code, not at ▷.

- (3) The ▷ race: VS Code's AX tree is switched on by the first lookup (ax.enable_electron_ax) and Chromium fills it in
  over the next seconds. t7 03:56:31.121 "enabled AX tree for pid 81248", 2 ms later "VS Code's Run ▷ isn't on screen
  (no Python extension?): the terminal box instead", and the box never became the ▷ (it did on Hint, 60 s later).
  place_run_box: the terminal box goes up as the fallback at once, the ▷ is looked up again after RETRY_S (then every
  SLOW_S for UPGRADE_FOR_S) and replaces it (+ zoom, ui_targets.run_spot) as soon as it is found, unless the learner
  typed in VS Code since the terminal box went up (they're typing the command there). "no Python extension?" is only
  logged once every quick retry missed. (server.screen.ax / reader: a lookup that missed while the tree was filling
  in is only cached for a moment, not the usual 6 s.)
- (4) The culprit: a run step's "Not yet" whose cause is in the code. t7: "Loss is stuck at 0.49" (W1, W2 and W3
  started at zeros), Hint 1 "Look at how W1, W2 and W3 start…", and the box was the ▷. culprit(): the lines to look
  at, from the files alone, no model call:
    - stuck at curated.STUCK_LOSS (identical hidden neurons): the W<k> = … lines that aren't random (W1..W3 as one box);
    - the off-track diagnosis names a line: its diff's line still in the file, else its `line` / "line N" (t6: "Wrong
      sign in tanh slope: change + to - on line 23 of nn.py");
    - the run stopped on a NameError (t6: forward called before its def): the traceback's line in the step's file.
  culprit_spot(): that span's rect (Accessibility / the gutter, wsmod.line_location); scrolled off, the companion
  reveals it first (vscode_ext.open_file with the line, preserveFocus), then it is measured. A cause the learner has
  since changed (the weights are random now, the diagnosed line is gone, the file changed after that run) is no
  culprit: a rerun is next, so the ▷ is the box again. follow(): once that happens after a culprit box this module put
  up (also when the save took that box down), the ▷ box comes back (a box of the press: owner "answer", so E17's
  _run_box_done doesn't take it down at once), and it goes once the rerun starts.
- (2) lives in session.start_step: a Demo lesson's run step always gets its Run it card (Run it for me) next to the box;
  a check's "Not yet" on any run step carries Run it for me from the first one.

Hooks in LessonSession (kept tiny for merges): _lesson_spot_once -> place_run_box; _show_where -> culprit_spot;
_run_box_done -> follow.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any

from . import spot_lines

log = logging.getLogger("orchestrator.session")

RETRY_S = (0.3, 0.8, 1.5, 3.0)  # the ▷ looked up again this long after each miss (VS Code filling its AX tree)
SLOW_S = 3.0  # then this often (the Python extension can activate late in a fresh window)
UPGRADE_FOR_S = 30.0  # how long a terminal fallback box may still become the ▷ box
OPEN_TRIES = 30  # "Open the terminal" / Save / ... boxes: looked at again every 2 s (~60 s), as before
REVEAL_WAIT_S = 0.4  # after the companion scrolled VS Code, before the lines are measured
SPAN_MAX = 8  # culprit lines further apart than this: only the first one is boxed (one box, one place)

_W_INIT = re.compile(r"^\s*(W\d+)\s*=(?!=)\s*(\S.*)$")
_RAND = re.compile(r"rand")
_LINE_N = re.compile(r"\bline (\d+)\b", re.I)
_NAME_ERR = re.compile(r"\b(?:NameError|UnboundLocalError)\b.*?'(\w+)'")
_TB = re.compile(r'^\s*File "([^"]+)", line (\d+)')


# ---------------------------------------------------------------------------------------------- (3) the Run ▷ race

def _typed_since(s: Any, t0: float) -> bool:
    """A key in the lesson's editor / terminal (inputs.py's work keys) after session clock t0. (A key before it, the
    ⌘S that passed the step before, never counts.)"""
    v = s._work_since("key")
    return v is not None and v < s.clock() - t0


async def place_run_box(s: Any, gen: int, step: dict, cmd: str, gone) -> None:
    """A run step's own box at step start (E17): the Run ▷ when VS Code shows it, else the terminal's prompt line,
    else where to open the terminal ("Open the terminal" / Save first boxes are looked at again every 2 s, ~60 s, as
    before). A terminal box that stands in for a ▷ not found yet becomes the ▷ box once it is found (module doc)."""
    button = s._run_button_file(step, cmd) is not None  # a command the ▷ runs on its own (`python3 nn.py`)
    waits = iter(RETRY_S if button else ())
    term: tuple[float, float] | None = None  # when the terminal box first went up: (session clock, monotonic)
    shown: str | None = None  # the caption of the last box this placed
    looks = opens = 0
    while True:
        if gone() or s._step_ran():  # E17: after a run the box has done its job (_run_box_done)
            return
        if term is not None and _typed_since(s, term[0]):
            log.info("run step %s: the learner typed in VS Code: the terminal box stays", step.get("id"))
            return
        spot = await s._run_spot(step, cmd)
        looks += 1
        if gone() or s._step_ran():
            return
        kind = spot.pop("kind", None)
        if kind == "run_button" and term is not None:
            if s.spot_rect is not None and shown is not None and s._spot_caption != shown:
                return  # another box took this one's place (an answer, a fix line): it stands
            if s.typing():  # never move a box under a keystroke: look again in a moment
                if time.monotonic() - term[1] >= UPGRADE_FOR_S:
                    return
                await asyncio.sleep(0.5)
                continue
            log.info("run step %s: VS Code's Run ▷ is on screen now (look %d): the terminal box becomes the ▷ box",
                     step.get("id"), looks)
        if spot:  # E17: the Run ▷ / terminal panel / menu item are where to act; the targeter never moves them
            await s._show_spot(spot, steady=True, verify=False)
            shown = spot.get("caption")
        if kind == "run_button" or (kind == "terminal" and not button):
            return
        if kind == "terminal" and term is None:
            term = (s.clock(), time.monotonic())
        wait = next(waits, None)  # the ▷ isn't there (yet): VS Code may still be filling its AX tree
        if wait is None:
            if button and looks == len(RETRY_S) + 1:
                s._run_note(f"VS Code's Run ▷ isn't on screen after {looks} looks (no Python extension?): "
                            f"the {'terminal' if kind == 'terminal' else kind or 'no'} box stays")
            if kind == "terminal":
                if time.monotonic() - term[1] >= UPGRADE_FOR_S:
                    return
                wait = SLOW_S
            else:
                opens += 1
                if opens > OPEN_TRIES:
                    return
                wait = 2.0  # "Open the terminal" / Save first: the next look upgrades it once that's done
        await asyncio.sleep(wait)


# ---------------------------------------------------------------------------------------------- (4) the culprit lines

def _failing(s: Any, run: Any) -> bool:
    """A check row fails (a Demo lesson only sets the rows), or the step's last run crashed."""
    return (bool(s.last_failed) or any((c or {}).get("status") == "fail" for c in (s.check_state or {}).values())
            or (run is not None and run.exit_code not in (0, None)))


def _last_run(s: Any) -> Any:
    return next((r for r in reversed(s.step_runs or []) if not r.running), None)


def _changed_since(s: Any, step: dict, path: Path, run: Any) -> bool:
    """The step's file changed after `run` began: unsaved edits now, or saved after it (VS Code's ▷ and Run it for me
    save before they run). No run: unknown, so unchanged."""
    if run is None:
        return False
    if s._dirty_step_file(step):
        return True
    try:
        return path.stat().st_mtime > float(run.started_t) + 0.5
    except OSError:
        return False


def _names(ws: list[str]) -> str:
    return ws[0] if len(ws) == 1 else ", ".join(ws[:-1]) + " and " + ws[-1]


def _span(first: int, last: int) -> tuple[int, int]:
    return (first, last) if last - first <= SPAN_MAX else (first, first)


def _stuck(s: Any, step: dict) -> bool:
    from . import curated

    try:
        return curated.active(s) and curated._stuck_here(s, step)
    except Exception:  # noqa: BLE001 - not a curated lesson's state: no stuck culprit
        return False


def _stuck_lines(lines: list[str]) -> dict | None:
    """The weights that start the same: every first `W<k> = …` line that isn't random (zeros, ones, a constant)."""
    first: dict[str, tuple[int, str]] = {}
    for i, ln in enumerate(lines, start=1):
        m = _W_INIT.match(ln)
        if m and m.group(1) not in first:
            first[m.group(1)] = (i, m.group(2))
    bad = sorted((n, name) for name, (n, rhs) in first.items() if not _RAND.search(rhs))
    if not bad:
        return None  # they start random now: the run that got stuck is old, a rerun is next
    a, b = _span(bad[0][0], bad[-1][0])
    names = [name for n, name in bad if a <= n <= b]
    return {"first": a, "last": b, "caption": f"Look at how {_names(names)} start", "why": "stuck"}


def _named_line(s: Any, step: dict, path: Path, lines: list[str], run: Any) -> dict | None:
    """The line this step's off-track diagnosis is about: its diff's line while it is still in the file, else the
    line it names (`diff.line`, "line 23" in its words) while the file is as that run left it."""
    off = s.last_offtrack
    if not off or off.get("stepId") not in (None, step.get("id")):
        return None
    title = re.sub(r"[`*_]", "", str(off.get("title") or "")).strip()
    diff = off.get("diff") or {}
    pair = spot_lines.first_change(diff.get("yours"), diff.get("expected"))
    if pair is not None:
        n = spot_lines.find_line(lines, pair[0])
        if n is not None:
            cap = f"Change to: {spot_lines.clip(pair[1])}" if pair[1] else "Delete this line"
            return {"first": n, "last": n, "caption": cap, "why": "diagnosis"}
        return None  # the diagnosed line is gone: they changed it, a rerun is next
    f = diff.get("file")
    n = diff.get("line") if isinstance(diff.get("line"), int) and (not f or Path(str(f)).name == path.name) else None
    if n is None:
        m = _LINE_N.search(f"{title} {off.get('body') or ''}")
        n = int(m.group(1)) if m else None
    if n is None or not 1 <= n <= len(lines) or _changed_since(s, step, path, run):
        return None
    cap = title if title and len(title.split()) <= 8 else f"Look at line {n}"
    return {"first": n, "last": n, "caption": cap, "why": "diagnosis"}


def _name_error(s: Any, step: dict, path: Path, lines: list[str], run: Any) -> dict | None:
    """The last run stopped on a NameError raised in the step's file: the traceback's line there (a name used before
    its def, t6), while the file is as that run left it."""
    if run is None or run.exit_code in (0, None) or _changed_since(s, step, path, run):
        return None
    tail = [str(x) for x in run.output_tail or []]
    err = next((m for ln in reversed(tail) if (m := _NAME_ERR.search(ln))), None)
    if err is None:
        return None
    here = [int(m.group(2)) for ln in tail if (m := _TB.match(ln)) and Path(m.group(1)).name == path.name]
    if not here or not 1 <= here[-1] <= len(lines):
        return None
    n, name = here[-1], err.group(1)
    later = re.compile(rf"^\s*(?:(?:async\s+)?def\s+{re.escape(name)}\b|{re.escape(name)}\s*=(?!=))")
    cap = (f"{name} is used before it's defined" if any(later.match(ln) for ln in lines[n:])
           else f"{name} isn't defined")
    return {"first": n, "last": n, "caption": cap, "why": "name_error"}


def culprit(s: Any, step: dict | None) -> dict | None:
    """A run step's "Not yet" whose cause is in the code -> {path, first, last, caption, why} (1-based lines of the
    step's file, VS Code's unsaved text when the companion has it); None: not such a step, nothing fails, or the cause
    was changed since (a rerun is next)."""
    if (step is None or not getattr(s, "lesson_mode", False) or s.step is not step or s.passed
            or not s._run_command(step)):
        return None
    run = _last_run(s)
    if not _failing(s, run):
        return None
    path, lines = s._step_lines(step)
    if path is None or not lines:
        return None
    got = (_stuck_lines(lines) if _stuck(s, step) else None) \
        or _named_line(s, step, path, lines, run) or _name_error(s, step, path, lines, run)
    return {**got, "path": path} if got else None


def _line_location(s: Any, path: Path, line: int) -> dict:
    """The editor row of `line` on screen (wsmod.line_location: Accessibility, else the OCR'd gutter): {rect | None,
    direction / reason when it's scrolled off}. {} without the real screen reader (tests patch this)."""
    if getattr(s.screen, "reader", None) is None:
        return {}
    from . import workspace as wsmod

    return wsmod.line_location(path, line)


async def _rows(s: Any, path: Path, first: int, last: int) -> tuple[dict | None, dict | None]:
    a = await asyncio.to_thread(_line_location, s, path, first)
    b = a if last == first else await asyncio.to_thread(_line_location, s, path, last)
    return (a or {}).get("rect"), (b or {}).get("rect")


async def reveal(s: Any, path: Path, line: int) -> bool:
    """Scroll the lesson's VS Code window to `line` without taking the focus: the companion's /open (preserveFocus),
    else `code -g` through the workspace (only while VS Code is in front). -> asked."""
    ext = await asyncio.to_thread(s._vscode_ext)
    if ext is not None and hasattr(ext, "open_file"):
        try:
            res = await asyncio.to_thread(ext.open_file, str(path), line, folder=s.workdir, preserve_focus=True)
        except Exception:  # noqa: BLE001 - the workspace's jump below
            log.exception("revealing line %d of %s failed", line, path.name)
            res = None
        if isinstance(res, dict) and res.get("ok", True):
            return True
    if s.workspace is not None and getattr(s, "editor_open", False):
        s.workspace.goto(str(path), line)
        return True
    return False


async def culprit_spot(s: Any, step: dict) -> dict | None:
    """Hint / Show me / Explain on a run step whose "Not yet" is in the code: the box on those lines. None: no such
    culprit (the caller boxes the ▷ / terminal as before). {}: there is one, but its lines can't be found on screen:
    no box (never the ▷, which would say "run it again")."""
    c = culprit(s, step)
    if c is None:
        return None
    path, first, last = c["path"], c["first"], c["last"]
    log.info("run step %s: the Not yet is in the code (%s): lines %d-%d of %s, not the Run ▷", step.get("id"),
             c["why"], first, last, path.name)
    r1, r2 = await _rows(s, path, first, last)
    if (r1 is None or r2 is None) and await reveal(s, path, (first + last) // 2):
        await asyncio.sleep(REVEAL_WAIT_S)  # measured after VS Code scrolled (t7: a box placed before a scroll stayed)
        r1, r2 = await _rows(s, path, first, last)
    if r1 is None and r2 is None:
        log.info("run step %s: lines %d-%d of %s aren't on screen: no box", step.get("id"), first, last, path.name)
        return {}
    r1 = r1 or {**r2, "y": float(r2["y"]) - float(r2["h"]) * (last - first)}
    r2 = r2 or {**r1, "y": float(r1["y"]) + float(r1["h"]) * (last - first)}
    x = min(float(r1["x"]), float(r2["x"]))
    y = float(r1["y"])
    w = max(float(r1["x"]) + float(r1["w"]), float(r2["x"]) + float(r2["w"])) - x
    h = max(float(r1["h"]), float(r2["y"]) + float(r2["h"]) - y)
    s._culprit_box = (s.step_gen, c["caption"], c["why"])
    return {"rect": {"x": x, "y": y, "w": w, "h": h}, "caption": c["caption"], "app": "Code"}


async def follow(s: Any) -> None:
    """On a frame: once the cause behind a culprit box this module put up has changed (a rerun is next; not under a
    keystroke), the ▷ box comes back, also when a save took the culprit box down (_acted); that ▷ box goes once the
    rerun starts (E17). It is a box of the press (owner "answer") but not an `_action_spot`: a save keeps it."""
    again = getattr(s, "_rerun_box", None)
    if again is not None:
        gen, cap, runs, t = again
        if gen != s.step_gen or s.spot_rect is None or s._spot_caption != cap:
            s._rerun_box = None
        elif len(s.step_runs or []) > runs or getattr(s, "_ext_run_t", 0.0) > t:
            s._rerun_box = None
            async with s._spot_lock():
                if s.spot_rect is not None and s._spot_caption == cap:
                    await s.emit("spotlight", {"clear": True})
        return
    step, mine = s.step, getattr(s, "_culprit_box", None)
    if mine is None or step is None:
        return
    if mine[0] != s.step_gen or s.passed or (s.spot_rect is not None and s._spot_caption != mine[1]):
        s._culprit_box = None  # another box took its place, or the step moved on
        return
    if s.typing() or culprit(s, step) is not None:
        return
    s._culprit_box = None
    cmd = s._run_command(step)
    spot = await s._run_spot(step, cmd) if cmd else {}
    spot.pop("kind", None)
    if not spot or step is not s.step or s.passed or (s.spot_rect is not None and s._spot_caption != mine[1]):
        return
    log.info("run step %s: the code changed since the run: the ▷ box is back (%r)", step.get("id"), spot.get("caption"))
    await s._show_spot(spot, owner="answer")
    if s.spot_rect is not None and s._spot_caption == spot.get("caption"):
        s._rerun_box = (s.step_gen, s._spot_caption, len(s.step_runs or []), time.time())
