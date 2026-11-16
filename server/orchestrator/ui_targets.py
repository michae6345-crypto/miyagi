"""More of the Run ▷ box (desktop test 6): VS Code's REAL controls, found by Accessibility, boxed with a short caption.

Michael on the Run ▷ box ("Click ▷ to run nn.py"): "it really actually selects it, actually finds it, and does all
that ... make sure we need to have more of that stuff." He also lost time where the terminal or a control wasn't
visible. Each target below is the element itself (server.screen.ax.find_ui through the reader's "ui:<key>" region:
the lesson's VS Code window only, never Cursor, cached like the Run ▷), never a guessed rectangle; when it isn't
found the box that was there before stands.

- Open the terminal (run step, panel closed): the companion's POST /terminal first (_ensure_terminal, once per
  step); still closed -> the panel's "Terminal" tab ("Click Terminal"), else the title bar's Toggle Panel.
  Fallback: the menu bar's Terminal item / status bar ("Open the terminal: ⌃`").
- Save (run step, the step's file unsaved): the companion saves it (_save_step_file) when it can; else the tab's
  unsaved dot ("Press ⌘S to save nn.py"), after "Click nn.py" when another file is in front. Fallback: the run box.
- Open nn.py (code step, another file in front once the companion had its turn): its tab, else its Explorer row
  ("Click nn.py"). Fallback: no box (the step's own box comes back once nn.py is in front).
- Select Interpreter (run step boxed on the Run ▷, the lesson has no .venv python, the Python extension's
  notification is up): its button ("Click Select Interpreter first"). Harmless otherwise (the companion selects
  .venv; a typed command doesn't need it): left alone.
- Problems (a press on a run step whose file doesn't compile): the status bar's errors item / the Problems tab
  ("Click to see the error"). Fallback: the run box.

Every box goes through _show_spot (one box, the E8 owners, never under Miyagi's drawer: _under_overlay) and carries
`zoom: true` when the element is under 32 pt (Adrian's loupe).

Hooks in LessonSession (kept tiny for merges): `_run_spot` -> run_spot(); start_step -> watch_file();
Show me -> show_open_file().
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger("orchestrator.session")

ZOOM_PT = 32.0  # a target under this (both sides) gets Adrian's loupe
TERMINAL_TAB = "Click Terminal"
TOGGLE_PANEL = "Click here to open the terminal"
OPEN_FILE = "Click {name}"
SAVE = "Press ⌘S to save {name}"
INTERPRETER = "Click Select Interpreter first"
PROBLEMS = "Click to see the error"
OPEN_KINDS = ("menu", "status")  # _open_terminal_spot's boxes: the terminal is closed


def _box(s, r: dict | None, caption: str, kind: str, extra: dict | None = None) -> dict | None:
    """A spot on element rect `r` (screen points) in the lesson's window, never under Miyagi's own UI; a tiny element is
    padded to a 28-pt square (as the Run ▷) and flagged `zoom`. None when it's off the window or covered."""
    if not r:
        return None
    win = s._editor_window()
    cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
    if win is not None and not (win["x"] <= cx <= win["x"] + win["w"] and win["y"] <= cy <= win["y"] + win["h"]):
        s._run_note(f"{caption}: the element at {r} is outside the lesson window")
        return None
    if s._under_overlay(cx, cy):
        s._run_note(f"{caption}: the element is under Miyagi's drawer")
        return None
    zoom = max(r["w"], r["h"]) < ZOOM_PT
    if zoom:
        side = max(28.0, r["w"], r["h"])
        rect = {"x": cx - side / 2, "y": cy - side / 2, "w": side, "h": side}
    else:
        rect = {k: float(r[k]) for k in ("x", "y", "w", "h")}
    return {"rect": rect, "caption": caption, "app": "Code", **(extra or {}), **({"zoom": True} if zoom else {}),
            "kind": kind}


async def _find(s, key: str) -> dict | None:
    """The reader's "ui:<key>" region (ax.find_ui; a fake screen's `regions` in tests), off the event loop."""
    region = getattr(s.screen, "region", None) if s.screen is not None else None
    if region is None or s._lesson_window_hidden():
        return None
    try:
        return await asyncio.to_thread(region, f"ui:{key}")
    except Exception:  # a failed lookup never costs the box that was there
        log.exception("ui:%s lookup failed", key)
        return None


async def file_spot(s, name: str, extra: dict | None = None) -> dict | None:
    """"Click nn.py": its editor tab, else its row in the Explorer."""
    cap = OPEN_FILE.format(name=name)
    for key in (f"tab:{name}", f"explorer:{name}"):
        if (spot := _box(s, await _find(s, key), cap, "open_file", extra)) is not None:
            return spot
    return None


async def terminal_open_spot(s, extra: dict | None = None) -> dict | None:
    """The terminal is closed: the panel's Terminal tab (the panel shows Problems / Output), else Toggle Panel."""
    spot = _box(s, await _find(s, "terminal_tab"), TERMINAL_TAB, "terminal_open", extra)
    return spot or _box(s, await _find(s, "toggle_panel"), TOGGLE_PANEL, "terminal_open", extra)


def _has_venv(s) -> bool:
    return (Path(s.workdir) / ".venv" / "bin" / "python").exists()


def _doesnt_compile(s, step: dict) -> bool:
    """The step's .py file (VS Code's unsaved buffer when the companion has it) has a syntax error."""
    try:
        p, lines = s._step_lines(step)
    except Exception:  # noqa: BLE001
        return False
    return p is not None and bool(lines) and s._syntax_error_line("\n".join(lines) + "\n", p) is not None


async def run_spot(s, step: dict, cmd: str, spot: dict) -> dict:
    """A run step's box (the Run ▷ / terminal prompt / "Open the terminal"), upgraded to the real control the learner
    must click first: save the file, open the terminal, select an interpreter, or (a press) see the error."""
    from .session import _ANSWERED

    snip = {"snippet": spot["snippet"]} if spot.get("snippet") else {}
    kind = spot.get("kind")
    if (_ANSWERED.get() is not None and _doesnt_compile(s, step)  # Show me / Hint / Explain: the error first
            and (box := _box(s, await _find(s, "problems"), PROBLEMS, "problems")) is not None):
        return box
    if (name := s._dirty_step_file(step)) is not None:  # what runs is the file on disk: save it first
        ext = await asyncio.to_thread(s._vscode_ext)
        saved = False
        tried = getattr(s, "_ui_save_failed", None) == s.step_gen
        if ext is not None and hasattr(ext, "save") and not s.typing() and not tried:
            saved = await s._save_step_file(step)  # the companion saves it for us (once it failed: the box)
            if not saved:
                s._ui_save_failed = s.step_gen
        if not saved and s._dirty_step_file(step):
            active = await asyncio.to_thread(s._active_editor_file)
            if active is not None and active != name:  # ⌘S saves the editor in front
                box = await file_spot(s, name)
            else:
                box = _box(s, await _find(s, f"dirty:{name}"), SAVE.format(name=name), "save")
            if box is not None:
                return box
            s._run_note(f"{name} is unsaved and its tab isn't found: the run box stands")
    if (kind == "run_button" and not _has_venv(s)  # the ▷ runs the selected interpreter: it must resolve
            and (box := _box(s, await _find(s, "interpreter"), INTERPRETER, "interpreter")) is not None):
        return box
    if kind in OPEN_KINDS or not spot:
        if getattr(s, "_ui_term_gen", None) != s.step_gen:  # the companion opens it (once per step) before any box
            s._ui_term_gen = s.step_gen
            if await s._ensure_terminal(step):
                region = getattr(s.screen, "region", None)
                for _ in range(8):  # the next frame shows the panel: its prompt line is the box
                    await asyncio.sleep(0.25)
                    if region is not None and await asyncio.to_thread(region, "terminal"):
                        return s._terminal_spot(step, cmd)
                return spot
        if (box := await terminal_open_spot(s, snip)) is not None:
            return box
    if kind == "run_button" and max(spot["rect"]["w"], spot["rect"]["h"]) < ZOOM_PT:
        spot = {**spot, "zoom": True}  # the ▷ is ~22 pt: Adrian's loupe
    return spot


async def _wrong_file(s, step: dict) -> str | None:
    """A code step whose .py / text file isn't the lesson window's active editor -> its name; None when it is, when
    that's unknown, or when the lesson window isn't on screen."""
    f = s._step_file(step)
    if not f or not s._real_file(f) or f.endswith(".ipynb") or s._run_command(step):
        return None
    if s._lesson_window_hidden() or s._editor_off_screen() or s._editor_window() is None:
        return None
    name = Path(f).name
    active = await asyncio.to_thread(s._active_editor_file)
    return name if active is not None and active != name else None


async def show_open_file(s, step: dict) -> bool:
    """Show me while another file is in front (the companion couldn't switch): box nn.py's tab / Explorer row."""
    name = await _wrong_file(s, step)
    spot = await file_spot(s, name) if name else None
    if spot is None:
        return False
    spot.pop("kind", None)
    s._action_spot = True
    await s._show_spot(spot, owner="answer")
    return True


async def watch_file(s, gen: int, step: dict, every_s: float = 2.0, grace_s: float = 3.0, tries: int = 30) -> None:
    """A code step whose file isn't in front once the companion had its turn (_show_step_file, ~grace_s): "Click nn.py"
    on its tab / Explorer row; once nn.py is in front that box goes and the step's own box is placed again."""
    if not s.lesson_mode:
        return
    await asyncio.sleep(grace_s)
    mine: str | None = None
    for _ in range(tries):
        if gen != s.step_gen or s.passed or s.step is not step or s._spot_frozen():
            return
        if s.typing():  # never move a box under a keystroke
            await asyncio.sleep(every_s)
            continue
        name = await _wrong_file(s, step)
        if name is None:
            if mine is not None and s._spot_caption == mine:  # nn.py is in front now: the step's box, not ours
                async with s._spot_lock():
                    if gen == s.step_gen and s._spot_caption == mine:
                        await s.emit("spotlight", {"clear": True})
                s._spawn(s._lesson_spot(gen, step, tries=3), timer=True)
            mine = None
        elif not (s._fix_active() or s._offtrack_box() == "up") and (spot := await file_spot(s, name)) is not None:
            spot.pop("kind", None)  # (a fix / off-track line up: that line stays the one box)
            mine = spot["caption"]
            if s._spot_caption != mine:
                await s._show_spot(spot, owner="step")
        await asyncio.sleep(every_s)
