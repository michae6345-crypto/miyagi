"""open_editor(): open a lesson folder in the learner's editor (VS Code), bring it to the front,
and, only with Accessibility permission, make room for the overlay's video.

Editor choice: MIYAGI_EDITOR=code (vscode) if that editor is installed, else VS Code (see ALLOW_CURSOR below).

Without Accessibility (always): `<cli> -n <dir> -g <file>` (fallback `open -a <App> <dir> [<file>]`), then
`open -a <App>` so the editor is frontmost. A full-screen app the learner was in stays as it is; the editor
gets its own window (macOS switches to it).
With Accessibility (AXIsProcessTrusted) and MIYAGI_ARRANGE != 0: the lesson's window (only the one showing the
lesson folder) is laid out ONCE on the overlay's display by the pure policy in layout.py: beside the lesson panel
("Just teach me"), or on the left with the right column kept for the player and steps drawer (video lessons). Nothing
is closed, quit or taken out of macOS full screen; a full-screen lesson window is left as it is. After that Miyagi only
follows: a window the learner moved or resized is never laid out again this lesson (fit_beside_drawer).
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from server.config import safe_env

from . import layout as L

log = logging.getLogger("server.workspace")

EDITORS: dict[str, dict] = {
    "cursor": {"label": "Cursor", "app": "Cursor", "bundle": "com.todesktop.230313mzl4w4u92", "cli": "cursor",
               "bundled_cli": "/Applications/Cursor.app/Contents/Resources/app/bin/cursor",
               "cask": "cursor", "url": "https://cursor.com/downloads"},
    "vscode": {"label": "Visual Studio Code", "app": "Visual Studio Code", "bundle": "com.microsoft.VSCode", "cli": "code",
               "bundled_cli": "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
               "cask": "visual-studio-code", "url": "https://code.visualstudio.com/download"},
}
# Cursor is banned (Michael, Sat 4:15 PM: "permanently ban it from using Cursor"): Miyagi only ever opens, names or
# offers VS Code. MIYAGI_ALLOW_CURSOR=1 brings Cursor back for someone who wants it.
ALLOW_CURSOR = os.environ.get("MIYAGI_ALLOW_CURSOR", "").strip() == "1"
# What macOS calls the running process (NSRunningApplication.localizedName / window owner): VS Code is "Code".
PROCESS_NAMES = {"vscode": "Code", "cursor": "Cursor"}
PREFERENCE = ["vscode", "cursor"] if ALLOW_CURSOR else ["vscode"]
ENV_NAMES = {"code": "vscode", "vscode": "vscode", "vs code": "vscode", "visual studio code": "vscode",
             **({"cursor": "cursor"} if ALLOW_CURSOR else {})}
# Kept for older callers (orchestrator fallback).
VSCODE_APP = EDITORS["vscode"]["app"]
BUNDLED_CLI = EDITORS["vscode"]["bundled_cli"]
EDITOR_FRACTION = float(os.environ.get("MIYAGI_EDITOR_FRACTION", "0.6"))
# "Just teach me" fills the screen with a MAXIMIZED window in the current Space. MIYAGI_FULLSCREEN=native brings back
# macOS full screen, which moves the window into its own Space (where the overlay and other lesson windows get lost).
NATIVE_FULLSCREEN = os.environ.get("MIYAGI_FULLSCREEN", "").strip().lower() == "native"
# The maximized lesson window stops short of the overlay's lesson panel on the right, so the panel doesn't cover the
# editor. v2 (BUILD-PLAN E3, decision 6): the panel is 360 pt wide in every lesson mode, 16 pt in from the screen's
# right edge (theme dock.inset), with a 16 pt gap to the editor: 360 + 16 + 16 = 392. Today's v1 drawer is wider
# (PANEL_W_LESSON 420 + 8 + 8 = 436): fit_full keeps 436 until a v2 app is known (it sent a v2 command, or a panel.state
# rect), so an engine ahead of the app never puts the v1 drawer over VS Code's Run button and panel toggle.
# MIYAGI_DRAWER_W overrides both (0: the full width).
PANEL_W, PANEL_INSET, PANEL_GAP = 360.0, 16.0, 16.0
DRAWER_W_V1 = 436.0
DRAWER_W = float(os.environ.get("MIYAGI_DRAWER_W", str(PANEL_W + PANEL_INSET + PANEL_GAP)))
_DRAWER_W_SET = "MIYAGI_DRAWER_W" in os.environ
_app_v2 = False  # the app draws the v2 panel (session.note_app_v2): DRAWER_W, else DRAWER_W_V1
# The lesson panel's real place, when the app reported it (panel.state {open, rect}, screen points, top-left origin):
# fit_full keeps the editor PANEL_GAP left of its left edge instead of the DRAWER_W estimate. None: not reported.
_panel_rect: dict | None = None
_panel_lock = threading.Lock()
# E22 kept the lesson's window 112 pt above the overlay's bottom shortcut bar. The bar was retired (Michael, Nov 21:
# no bottom bar in any lesson), but the 112 pt stayed: on a 900 pt MacBook screen VS Code lost an eighth of its height
# to nothing (MacBook Neo test, Nov 25). Now the window goes down to the Dock. MIYAGI_BAR_CLEARANCE=112: the old margin.
BAR_CLEARANCE = float(os.environ.get("MIYAGI_BAR_CLEARANCE", "0"))


def above_bar(frame: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """(x, y, w, h) with its bottom BAR_CLEARANCE above the visible screen's bottom (never under half its height)."""
    x, y, w, h = frame
    return (x, y, w, max(round(h * 0.5), h - BAR_CLEARANCE))


# t10: the overlay's step pill and settings gear sit just under the menu bar (y 40-75 pt on a 1728x1117 display), on
# top of VS Code's title bar for the whole lesson (the window title and the title-bar icons hidden). The lesson's
# window starts PILL_CLEARANCE below the visible screen's top instead (and is that much shorter), as it ends
# BAR_CLEARANCE above the shortcut bar. MIYAGI_PILL_CLEARANCE=0: right under the menu bar.
PILL_CLEARANCE = float(os.environ.get("MIYAGI_PILL_CLEARANCE", "44"))


def below_pill(frame: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """(x, y, w, h) with its top PILL_CLEARANCE below the visible screen's top, the height that much less (never
    under half of it)."""
    x, y, w, h = frame
    clear = max(0.0, min(PILL_CLEARANCE, round(h * 0.5)))
    return (x, y + clear, w, h - clear)


def note_panel(open_: bool, rect: dict | None = None) -> bool:
    """The app's panel.state (v2): where the lesson panel is docked (screen points), or that it closed. The editor's
    room is kept while the panel is collapsed (Mini), so the learner's window doesn't jump each time they toggle it;
    only an open panel's rect moves the edge. -> True when the edge fit_full uses changed."""
    global _panel_rect
    new = None
    if open_ and isinstance(rect, dict):
        try:
            new = {k: float(rect[k]) for k in ("x", "y", "w", "h")}
        except (KeyError, TypeError, ValueError):
            new = None
        if new is not None and (new["w"] <= 0 or new["h"] <= 0):
            new = None
    if new is None:
        return False
    with _panel_lock:
        same = _panel_rect is not None and abs(_panel_rect["x"] - new["x"]) < 2
        _panel_rect = new
    return not same


def panel_rect() -> dict | None:
    with _panel_lock:
        return dict(_panel_rect) if _panel_rect else None


def note_app_v2(on: bool = True) -> None:
    """The app draws the v2 lesson panel (360 pt): fit_full reserves DRAWER_W (392) from now on, not the v1 436."""
    global _app_v2
    _app_v2 = bool(on)


def drawer_reserve() -> float:
    """The room fit_full keeps on the right: DRAWER_W for a v2 panel (reported, or a v2 app), else the v1 drawer's
    DRAWER_W_V1. MIYAGI_DRAWER_W, when set, is used as it is."""
    if _DRAWER_W_SET or _app_v2 or panel_rect() is not None:
        return DRAWER_W
    return DRAWER_W_V1


def fit_full(visible: tuple[float, float, float, float], panel: dict | None = None,
             *, drawer_w: float | None = None) -> tuple[float, float, float, float]:
    """The lesson's editor frame in the visible screen `visible` (x, y, w, h; AX top-left), as layout.target puts it
    (mode "lesson", no notch known: below the island's row, PANEL_GAP left of the reported panel, else drawer_reserve()
    short of the right edge). Kept for older callers; the open and the follow-ups use layout.plan directly. Pure."""
    v = L.Rect.of(visible)
    if v is None:
        return visible
    p = L.Rect.of(panel if panel is not None else panel_rect())
    reserve = drawer_reserve() if drawer_w is None else drawer_w
    scr = L.Screen(frame=L.Rect(v.x, 0.0, v.w, v.bottom), visible=v)
    if reserve <= 0:
        p, reserve = None, 0.0
    return L.target(scr, "lesson", p, reserve=reserve, pill_clearance=PILL_CLEARANCE, bar_clearance=BAR_CLEARANCE).tuple()


# Our own overlay must never be treated as "the app the learner was in".
OVERLAY_NAMES = {n.strip().lower() for n in os.environ.get("MIYAGI_OVERLAY_APPS", "Miyagi,miyagi-overlay,Electron").split(",") if n.strip()}

Runner = Callable[[list[str]], bool]
# How long the one-time layout waits for the lesson's window to show its folder. Nov 26: 8 s was too short for a cold
# VS Code start that also loads a notebook and the Jupyter extension on a low-end Mac (the layout never ran); the
# "Just teach me" layout already waited 20 s.
ARRANGE_WAIT_S = float(os.environ.get("MIYAGI_ARRANGE_WAIT_S", "20"))


# --------------------------------------------------------------------------- which editor

def _app_path(ed: dict) -> str | None:
    for base in ("/Applications", str(Path.home() / "Applications")):
        p = Path(base) / f"{ed['app']}.app"
        if p.exists():
            return str(p)
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["mdfind", f"kMDItemCFBundleIdentifier == '{ed['bundle']}'"], capture_output=True,
                                 text=True, timeout=5, check=False, env=safe_env()).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        return next((ln for ln in out.splitlines() if ln.endswith(".app")), None)
    return None


def _cli(ed: dict, app_path: str | None = None) -> str | None:
    """The editor's CLI: on PATH, else inside the app wherever it is. A fresh Mac never ran "Install 'code' command in
    PATH", and an app launched from Finder gets PATH=/usr/bin:/bin, so the app bundle's own copy is the usual one; an
    app in ~/Applications or ~/Downloads has it there, not under /Applications."""
    if found := shutil.which(ed["cli"]):
        return found
    if Path(ed["bundled_cli"]).exists():
        return ed["bundled_cli"]
    if app_path:
        inside = Path(app_path) / "Contents" / "Resources" / "app" / "bin" / ed["cli"]
        if inside.exists():
            return str(inside)
    return None


def installed_editors() -> list[dict]:
    """[{id, label, app, app_path, cli}] for the supported editors on this Mac, in preference order."""
    out = []
    for eid in PREFERENCE:
        ed = EDITORS[eid]
        app_path = _app_path(ed)
        cli = _cli(ed, app_path)
        if app_path or cli:
            out.append({"id": eid, "label": ed["label"], "app": ed["app"], "app_path": app_path, "cli": cli,
                        "bundle": ed["bundle"], "process": PROCESS_NAMES.get(eid, ed["app"])})
    return out


def preferred_editor(installed: list[dict] | None = None) -> dict | None:
    """MIYAGI_EDITOR (cursor | code) if installed, else VS Code, else Cursor, else None."""
    eds = installed if installed is not None else installed_editors()
    want = ENV_NAMES.get(os.environ.get("MIYAGI_EDITOR", "").strip().lower())
    if want:
        hit = next((e for e in eds if e["id"] == want), None)
        if hit:
            return hit
        log.warning("MIYAGI_EDITOR=%s isn't installed; using %s", os.environ.get("MIYAGI_EDITOR"), eds[0]["id"] if eds else "none")
    return eds[0] if eds else None


def editor_id() -> str:
    """The editor the setup card should name: preferred installed one, else MIYAGI_EDITOR, else vscode."""
    ed = preferred_editor()
    if ed:
        return ed["id"]
    return ENV_NAMES.get(os.environ.get("MIYAGI_EDITOR", "").strip().lower(), "vscode")


def editor_label() -> str:
    """"Visual Studio Code": for "Open Visual Studio Code?" cards."""
    return EDITORS[editor_id()]["label"]


def code_cli() -> str | None:
    """CLI of the preferred editor (`cursor` or `code`), for `-r -g file:line` jumps."""
    ed = preferred_editor()
    return ed["cli"] if ed else _cli(EDITORS["vscode"])


def is_notebook(path: str | Path | None) -> bool:
    return bool(path) and str(path).lower().endswith(".ipynb")


def file_args(target: str | Path | None) -> list[str]:
    """The CLI arguments that show `target` as a tab: `-g <file>` for a text file; a notebook goes in as a plain path
    (`-g` opened mnist.ipynb as JSON text, t10), so VS Code shows it in its notebook editor. [] for no target."""
    if not target:
        return []
    return [str(target)] if is_notebook(target) else ["-g", str(target)]


def lesson_folder_of(path: str | Path) -> Path | None:
    """The Miyagi lesson folder (a folder right under the lessons root) that holds `path`, else None."""
    try:
        from .paths import lessons_root

        root, p = lessons_root().expanduser().resolve(), Path(path).expanduser().resolve()
        if root not in p.parents:
            return None
        top = root / p.relative_to(root).parts[0]
        return top if top.is_dir() and top != p and not top.name.startswith(".") else None
    except (OSError, ValueError, IndexError):
        return None


def goto_argv(path: str | Path, line: int = 1, *, folder: str | Path | None = None) -> list[str] | None:
    """The jump to <file>:<line> in the preferred editor, or None. A file of a lesson folder (`folder`, else the lesson
    folder that holds it): `<cli> <folder> -g <file>:<line>`, so it opens as a tab of THAT folder's window (Nov 26: `-r`
    reuses whichever window was last active, the learner's own project or a separate one). A notebook: `<cli> <folder>
    <file.ipynb>` (no line: `-g` is for text files). Anything else: `<cli> -r -g <file>:<line>` as before."""
    cli = code_cli()
    if not cli:
        return None
    home = Path(folder) if folder else lesson_folder_of(path)
    if is_notebook(path):
        return [cli, str(home), str(path)] if home else [cli, "-r", str(path)]
    where = f"{path}:{max(1, int(line))}"
    return [cli, str(home), "-g", where] if home else [cli, "-r", "-g", where]


# --------------------------------------------------------------------------- Accessibility (optional)

def ax_trusted() -> bool:
    """AXIsProcessTrusted() via ctypes (no prompt, no extra dependency)."""
    if sys.platform != "darwin":
        return False
    try:
        lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except (OSError, AttributeError):
        return False


def frontmost_app(skip: set[str] | None = None) -> dict | None:
    """{pid, name} of the app owning the frontmost normal window, skipping our overlay and `skip` names."""
    try:
        import Quartz
    except ImportError:
        return None
    skip = {s.lower() for s in (skip or set())} | OVERLAY_NAMES
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
        if w.get("kCGWindowLayer", 1) != 0:
            continue
        name = str(w.get("kCGWindowOwnerName") or "")
        if name.lower() in skip or not name:
            continue
        return {"pid": int(w["kCGWindowOwnerPID"]), "name": name}
    return None


class AX:
    """Thin pyobjc wrapper (pyobjc-framework-ApplicationServices). Every call is best effort."""

    def __init__(self):
        import ApplicationServices as A

        self.A = A

    def _get(self, el, attr):
        err, val = self.A.AXUIElementCopyAttributeValue(el, attr, None)
        return val if err == 0 else None

    def focused_window(self, pid: int):
        app = self.A.AXUIElementCreateApplication(pid)
        return self._get(app, "AXFocusedWindow") or next(iter(self._get(app, "AXWindows") or []), None)

    def folder_window(self, pid: int, folder: str):
        """The app's window showing `folder`: its AXDocument (the active file) is inside the folder, else (no document)
        its title names the folder ("calculator.py — python-calculator-e430dc"). None while no window does."""
        root, by_title = Path(folder).expanduser().resolve(), None
        for win in self._get(self.A.AXUIElementCreateApplication(pid), "AXWindows") or []:
            doc = _doc_path(self._get(win, "AXDocument"))
            if doc is not None:
                if doc == root or root in doc.parents:
                    return win
            elif by_title is None and root.name in [p.strip() for p in str(self._get(win, "AXTitle") or "").lstrip("● ").split(" — ")]:
                by_title = win
        return by_title

    def other_lesson_windows(self, pid: int, folder: str) -> list[tuple[str, object]]:
        """(folder name, window) for each of the app's windows that shows ANOTHER Miyagi lesson folder: its title names
        a folder under ~/miyagi/lessons (active.vscode_windows' rule). Never a window of the learner's own projects,
        never one whose active file is inside `folder`."""
        from .active import lesson_folder_named, parse_title

        root, out = Path(folder).expanduser().resolve(), []
        for win in self._get(self.A.AXUIElementCreateApplication(pid), "AXWindows") or []:
            doc = _doc_path(self._get(win, "AXDocument"))
            if doc is not None and (doc == root or root in doc.parents):
                continue
            name = (parse_title(str(self._get(win, "AXTitle") or "")) or {}).get("folder_name")
            other = lesson_folder_named(name)
            if other is not None and other != root:
                out.append((name, win))
        return out

    def minimize(self, win) -> bool:
        """Minimize to the Dock (never closed); False when it already was or the app refused."""
        if self._get(win, "AXMinimized"):
            return False
        return self.A.AXUIElementSetAttributeValue(win, "AXMinimized", True) == 0

    def raise_window(self, win) -> bool:
        """Front window of its app (doesn't activate the app, so it never takes focus from the overlay)."""
        self.A.AXUIElementSetAttributeValue(win, "AXMain", True)
        return self.A.AXUIElementPerformAction(win, "AXRaise") == 0

    def is_fullscreen(self, win) -> bool:
        return bool(self._get(win, "AXFullScreen"))

    def enter_fullscreen(self, win) -> bool:
        return self.A.AXUIElementSetAttributeValue(win, "AXFullScreen", True) == 0

    def exit_fullscreen(self, win) -> bool:
        return self.A.AXUIElementSetAttributeValue(win, "AXFullScreen", False) == 0

    def frame(self, win) -> tuple[float, float, float, float] | None:
        """(x, y, w, h) in AX (top-left) points, or None."""
        A = self.A
        p, s = self._get(win, "AXPosition"), self._get(win, "AXSize")
        if p is None or s is None:
            return None
        ok1, pt = A.AXValueGetValue(p, A.kAXValueCGPointType, None)
        ok2, sz = A.AXValueGetValue(s, A.kAXValueCGSizeType, None)
        return (float(pt.x), float(pt.y), float(sz.width), float(sz.height)) if ok1 and ok2 else None

    def set_frame(self, win, x: float, y: float, w: float, h: float) -> bool:
        """Position, size, then the position once more if macOS clamped it while the old size didn't fit there (a
        window moved before it shrank lands short of its spot: the second, visible hop of the open)."""
        A = self.A
        pos = A.AXValueCreate(A.kAXValueCGPointType, (x, y))
        size = A.AXValueCreate(A.kAXValueCGSizeType, (w, h))
        ok1 = A.AXUIElementSetAttributeValue(win, "AXPosition", pos) == 0
        ok2 = A.AXUIElementSetAttributeValue(win, "AXSize", size) == 0
        now = self.frame(win)
        if now is not None and (abs(now[0] - x) > 2 or abs(now[1] - y) > 2):
            ok1 = A.AXUIElementSetAttributeValue(win, "AXPosition", pos) == 0
        return ok1 and ok2


# t12 (test 12: VS Code stayed narrowed after End lesson, ~40% of the screen empty): each window Miyagi arranged, as
# [window, its frame before Miyagi's first arrange, the frames Miyagi set (asked, then read back), layout mode]
_arranged: list[list] = []
_arranged_lock = threading.Lock()
RESTORE_SLACK = 4.0  # pt: a window this close to the frame Miyagi set is still where Miyagi put it
# Nov 25 (MacBook Neo test: "lay out once, then only follow"): windows the learner moved or resized after miyagi laid
# them out. They are theirs for the rest of the lesson: no panel move, run step or display change touches them again.
_released: list = []


def _same_win(a, b) -> bool:
    return a is b or a == b


def _set_frame(ax, win, x: float, y: float, w: float, h: float, *, mode: str | None = None) -> bool:
    """ax.set_frame, remembering the window's frame before Miyagi first arranged it (restore_frames puts it back) and
    the frames Miyagi set (_ownership: is it still where Miyagi put it?)."""
    read = getattr(ax, "frame", None)
    try:
        before = read(win) if read else None
    except Exception:  # noqa: BLE001 - remembering is a refinement: the arrange itself goes on
        before = None
    ok = ax.set_frame(win, x, y, w, h)
    if before is None or not ok:
        return ok
    try:
        now = read(win)
    except Exception:  # noqa: BLE001
        now = None
    with _arranged_lock:
        e = next((e for e in _arranged if _same_win(e[0], win)), None)
        if e is None:
            e = [win, before, [(x, y, w, h)] + ([now] if now else []), mode]
            _arranged.append(e)
        else:
            e[2] = [(x, y, w, h)] + ([now] if now else [])  # a later arrange (the drawer's room): its first frame stays
            e[3] = mode or e[3]
        frames = e[2]
    _later(SETTLED_READ_S, lambda: _note_settled(read, win, frames))
    return ok


# VS Code (and macOS) may still adjust a window a moment after it was moved, more so on a slow Mac right after launch
# (a title bar snap, a minimum size): that frame is Miyagi's too, not the learner moving it (_ownership).
SETTLED_READ_S = 0.4


def _later(delay_s: float, fn: Callable[[], None]) -> None:
    t = threading.Timer(delay_s, fn)
    t.daemon = True
    t.start()


def _note_settled(read, win, frames: list) -> None:
    """Add the window's frame SETTLED_READ_S after Miyagi set it to the frames Miyagi set (only while that arrange is
    the latest: a newer one replaced the list)."""
    try:
        now = read(win)
    except Exception:  # noqa: BLE001
        return
    if not now:
        return
    with _arranged_lock:
        e = next((e for e in _arranged if _same_win(e[0], win)), None)
        if e is not None and e[2] is frames and not any(L.same(L.Rect.of(now), L.Rect.of(f), 0.5) for f in frames):
            frames.append(tuple(now))


def _ownership(ax, win) -> bool | None:
    """None: Miyagi never laid this window out. True: it is where Miyagi last put it (RESTORE_SLACK). False: the
    learner moved or resized it since (remembered: theirs for the rest of the lesson, even if it comes back)."""
    with _arranged_lock:
        if any(_same_win(w, win) for w in _released):
            return False
        e = next((e for e in _arranged if _same_win(e[0], win)), None)
    if e is None:
        return None
    try:
        now = ax.frame(win)
    except Exception:  # noqa: BLE001
        now = None
    if now is None:
        return False  # can't tell where it is: don't touch it
    if any(L.same(L.Rect.of(now), L.Rect.of(f), RESTORE_SLACK) for f in e[2]):
        return True
    _release(win)
    log.info("layout: the learner moved or resized the lesson window; miyagi only follows it from now on")
    return False


def _release(win) -> None:
    with _arranged_lock:
        if not any(_same_win(w, win) for w in _released):
            _released.append(win)


def _claim(win) -> None:
    """An open lays its window out afresh (open_lesson_editor runs at most once per lesson)."""
    with _arranged_lock:
        _released[:] = [w for w in _released if not _same_win(w, win)]


def _mode_of(win) -> str | None:
    with _arranged_lock:
        e = next((e for e in _arranged if _same_win(e[0], win)), None)
    return e[3] if e is not None and len(e) > 3 else None


def _frame_of(ax, win) -> L.Rect | None:
    read = getattr(ax, "frame", None)
    try:
        return L.Rect.of(read(win)) if read else None
    except Exception:  # noqa: BLE001
        return None


def restore_frames(ax=None) -> list[tuple]:
    """t12: lesson end / stop puts each window Miyagi arranged back to its frame from before the lesson, unless the
    learner moved or resized it since (then it's theirs, left as it is). Best effort, never raises; blocking (AX):
    call it in a thread. -> the frames restored."""
    with _arranged_lock:
        saved = list(_arranged)
        _arranged.clear()
        _released.clear()
    if not saved:
        return []
    done: list[tuple] = []
    try:
        ax = ax or AX()
        for win, before, set_to, *_ in saved:
            now = ax.frame(win)
            if now is None:
                continue  # closed since
            if not any(all(abs(a - b) <= RESTORE_SLACK for a, b in zip(now, f)) for f in set_to):
                log.info("window restore: moved or resized since Miyagi arranged it; left as it is")
                continue
            if ax.set_frame(win, *before):
                done.append(tuple(before))
        if done:
            log.info("window restore: %d window(s) back to their frame from before the lesson", len(done))
    except Exception as e:  # noqa: BLE001 - tidying windows must never break ending the lesson
        log.debug("window restore failed: %r", e)
    return done


# Nov 25 (MacBook Neo test: "the overlay moved back and forth when VS Code opened"): ONE writer of the lesson window's
# frame. The open's layout (make_fullscreen / arrange) and the follow-ups (fit_beside_drawer: panel.state, a run step)
# take this lock, the follow-ups wait out a burst (RELAYOUT_SETTLE_S: only the last request of a burst acts) and stay
# out while the open's layout is still coming (it reads the latest panel rect itself). The math is layout.plan's.
_layout_lock = threading.Lock()
_relayout_gen = 0
_opening = 0  # open-time layouts in flight
_pending_fit: tuple[str, dict | None] | None = None  # a follow-up that came while one was in flight: runs after it
RELAYOUT_SETTLE_S = float(os.environ.get("MIYAGI_RELAYOUT_SETTLE_S", "0.5"))


def _opening_layout(delta: int, ax=None) -> None:
    """+1 as an open's layout starts, -1 when it ends: the last one to end runs the follow-up that came meanwhile
    (fit_beside_drawer skipped it, the panel may have moved since the open read it)."""
    global _opening, _pending_fit
    with _arranged_lock:
        _opening = max(0, _opening + delta)
        pending = _pending_fit if delta < 0 and _opening == 0 else None
        if pending is not None:
            _pending_fit = None
    if pending is not None:
        folder, ed = pending
        res = fit_beside_drawer(folder, ax=ax, editor=ed, settle_s=0)
        log.info("layout: the follow-up held during the open: %s", res)


def _settled(settle_s: float, sleep=time.sleep) -> bool:
    """Debounce: True for the last of a burst of relayout requests (each waits settle_s; a newer one wins)."""
    global _relayout_gen
    with _arranged_lock:
        _relayout_gen += 1
        mine = _relayout_gen
    if settle_s > 0:
        sleep(settle_s)
    with _arranged_lock:
        return mine == _relayout_gen


def lesson_screen() -> L.Screen | None:
    """The overlay's display, live: the PRIMARY display (v1: the overlay and the engine's screen reader live there, so
    the lesson window goes there too, even if VS Code last opened on an external display). NSScreen gives the visible
    frame (menu bar, Dock on any side) and the notch (safeAreaInsets); its frame is checked against Quartz's live
    CGDisplayBounds, since NSScreen can go stale in a process without an AppKit run loop (the engine): a resolution
    or display change since then keeps NSScreen's insets on the live frame. In AX points (top-left origin)."""
    try:
        import AppKit
    except ImportError:
        return None
    try:
        screens = AppKit.NSScreen.screens()
        if not screens:
            return None
        prim = screens[0]  # the one with the menu bar, origin (0, 0)
        f, vf = prim.frame(), prim.visibleFrame()
        fw, fh = float(f.size.width), float(f.size.height)
        top = fh - (float(vf.origin.y) + float(vf.size.height))
        left, width, height = float(vf.origin.x) - float(f.origin.x), float(vf.size.width), float(vf.size.height)
        safe_top = 0.0
        if hasattr(prim, "safeAreaInsets"):
            try:
                safe_top = float(prim.safeAreaInsets().top)
            except Exception:  # noqa: BLE001 - macOS < 12: no notch API, no notch
                safe_top = 0.0
        try:
            import Quartz

            b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
            lw, lh = float(b.size.width), float(b.size.height)
            if lw > 0 and lh > 0 and (abs(lw - fw) > 1 or abs(lh - fh) > 1):
                log.info("layout: NSScreen says %.0fx%.0f, the display is %.0fx%.0f now (stale); using the live size",
                         fw, fh, lw, lh)
                right_in, bottom_in = fw - (left + width), fh - (top + height)
                fw, fh = lw, lh
                width, height = max(0.0, fw - left - right_in), max(0.0, fh - top - bottom_in)
        except Exception:  # noqa: BLE001 - no Quartz: NSScreen's answer as it is
            pass
        frame = L.Rect(0.0, 0.0, fw, fh)
        visible = L.Rect(left, top, width, height)
        return L.Screen(frame=frame, visible=visible, safe_top=safe_top) if visible.w > 0 and visible.h > 0 else None
    except Exception as e:  # noqa: BLE001
        log.debug("lesson_screen failed: %r", e)
        return None


def _panel() -> L.Rect | None:
    return L.Rect.of(panel_rect())


def _reserve() -> float | None:
    """Room kept for the panel when the app hasn't reported it: the v1 drawer's until a v2 app is known."""
    return None if panel_rect() is not None else drawer_reserve()


def make_fullscreen(editor: dict, report: dict, *, folder: str | None = None, ax=None, wait_s: float = 20.0,
                    sleep=time.sleep) -> None:
    """With Accessibility: the lesson's window fills the overlay's display beside the lesson panel (layout.plan,
    mode "lesson": under the menu bar / notch, down to the Dock, PANEL_GAP left of the panel). Default: a normal
    window in the current Space. MIYAGI_FULLSCREEN=native: macOS full screen (AXFullScreen=true). A window already in
    macOS full screen is the learner's: left as it is. Runs ONCE per lesson open (open_lesson_editor).
    folder: act on the window showing that folder, never on whichever window had focus before it appeared."""
    try:
        ax = ax or AX()
    except ImportError:
        report["fullscreen"] = "skipped: pyobjc-framework-ApplicationServices not installed"
        return
    _opening_layout(+1)
    try:
        deadline = time.monotonic() + wait_s
        win = pid = None
        while time.monotonic() < deadline:
            pid = editor_pid(editor)
            win = (ax.folder_window(pid, folder) if folder else ax.focused_window(pid)) if pid else None
            if win is not None:
                break
            sleep(0.3)
        if win is None:
            report["fullscreen"] = f"skipped: no {editor['label']} window{' for ' + Path(folder).name if folder else ''} within {wait_s:.0f}s"
        elif ax.is_fullscreen(win):
            report["fullscreen"] = "done (already full screen)"
        elif NATIVE_FULLSCREEN:
            report["fullscreen"] = "done" if ax.enter_fullscreen(win) else "failed: the editor refused AXFullScreen"
        elif (scr := lesson_screen()) is None:
            report["fullscreen"] = "skipped: no screen info"
        else:
            with _layout_lock:
                _claim(win)
                p = L.plan(scr, mode="lesson", panel=_panel(), reserve=_reserve(),
                           editor=L.EditorState(frame=_frame_of(ax, win)), pill_clearance=PILL_CLEARANCE,
                           bar_clearance=BAR_CLEARANCE)
                if p.action == "set":
                    ok = _set_frame(ax, win, *p.bounds.tuple(), mode="lesson")
                    report["fullscreen"] = "done (maximized)" if ok else "failed: the editor refused the new frame"
                    report["frame"] = [round(v) for v in p.bounds.tuple()]
                else:
                    report["fullscreen"] = f"done ({p.reason})"
        if win is not None and folder:
            put_away_other_lessons(ax, pid, folder, win, report)
        log.info("full screen %s: %s", Path(folder).name if folder else editor["label"], report["fullscreen"])
    finally:
        _opening_layout(-1, ax)


def fit_beside_drawer(folder: str, *, ax=None, editor: dict | None = None, screen=None,
                      settle_s: float | None = None, sleep=time.sleep) -> str:
    """Follow-ups after the open (panel.state: the panel docked or moved with the display; a run step: VS Code's Run ▷
    and its top-right buttons must not sit under the panel, Michael Nov 15). Lay out once, then only follow:
      - macOS full screen: the learner's, left as it is (the overlay floats over it);
      - a window Miyagi laid out and the learner moved or resized since: theirs, never touched again this lesson;
      - a window still where Miyagi put it: re-planned (mode kept) only when the plan moved by more than layout.SLACK;
      - a window Miyagi never laid out (no Accessibility at open time, opened by the learner): narrowed once to end
        left of the panel when it reaches under it (x, y, height kept); maximized under it, or starting too far
        right: left as it is, for good.
    A burst of requests (panel.state while the panel springs, a run step right after) is one layout: the last.
    Best effort, never raises; blocking (AX): call it in a thread. -> what it found / did (also logged)."""
    if DRAWER_W <= 0:
        return "off (MIYAGI_DRAWER_W=0)"
    if not _settled(RELAYOUT_SETTLE_S if settle_s is None else settle_s, sleep):
        return "coalesced (a newer layout request follows)"
    global _pending_fit
    with _arranged_lock:
        if _opening:
            _pending_fit = (folder, editor)  # run once the open's layout is done (_opening_layout)
            return "skipped: the open's own layout is still coming (runs after it)"
    try:
        if not ax_trusted():
            return "skipped: Accessibility not granted"
        ax = ax or AX()
        ed = editor or preferred_editor()
        pid = editor_pid(ed) if ed else None
        win = ax.folder_window(pid, folder) if pid else None
        if win is None:
            return "skipped: no lesson window"
        name = Path(folder).name
        with _layout_lock:
            if ax.is_fullscreen(win):
                log.info("layout: %s is in macOS full screen (left as it is)", name)
                return "full screen (left as it is)"
            scr = screen if isinstance(screen, L.Screen) else (
                L.Screen(frame=L.Rect.of(screen), visible=L.Rect.of(screen)) if L.Rect.of(screen) else lesson_screen())
            fr = _frame_of(ax, win)
            if scr is None or fr is None:
                return "skipped: no frame"
            owned = _ownership(ax, win)
            if owned is False:
                return "the learner's layout (left as it is)"
            vis = scr.visible
            limit = L.target(scr, "lesson", _panel(), reserve=_reserve(), pill_clearance=PILL_CLEARANCE,
                             bar_clearance=BAR_CLEARANCE).right
            x, y, w, h = fr.tuple()
            mode = _mode_of(win) or "lesson"
            if owned and mode == "narrow":  # only its right edge was ever Miyagi's: keep just that beside the panel
                if x + w <= limit + 2 and x + w >= limit - 2:
                    return "ok"
                ok = _set_frame(ax, win, x, y, max(480.0, limit - x), h, mode="narrow")
                return "followed" if ok else "failed: the editor refused the new frame"
            if owned:
                p = L.plan(scr, mode=mode, panel=_panel(), reserve=_reserve(), editor=L.EditorState(frame=fr, owned=True),
                           pill_clearance=PILL_CLEARANCE, bar_clearance=BAR_CLEARANCE)
                if p.action != "set":
                    return "ok"
                ok = _set_frame(ax, win, *p.bounds.tuple(), mode=mode)
                log.info("layout: %s follows the panel / display (%s): %s", name, p.bounds.rounded().tuple(), ok)
                return "followed" if ok else "failed: the editor refused the new frame"
            # never laid out by Miyagi: narrow once, keep the rest of the learner's frame
            if x >= vis.right or x + w <= vis.x or x + w <= limit + 2:
                return "ok"
            if x <= vis.x + 2 and x + w >= vis.right - 2:
                _release(win)
                log.info("layout: %s is maximized under the panel (%.0f pt of it covered; left as it is)", name,
                         x + w - limit)
                return "maximized under the drawer (left as it is)"
            if limit - x < 480:
                _release(win)
                log.info("layout: %s starts too far right to narrow (left as it is)", name)
                return "too far right (left as it is)"
            ok = _set_frame(ax, win, x, y, limit - x, h, mode="narrow")
            log.info("layout: %s narrowed to end at x=%.0f, beside the panel: %s", name, limit, ok)
            return "narrowed" if ok else "failed: the editor refused the new frame"
    except Exception as e:  # noqa: BLE001 - a refinement: the lesson runs without it
        log.debug("fit beside drawer failed: %r", e)
        return f"failed: {e!r}"


def put_away_other_lessons(ax, pid: int, folder: str, win, report: dict, *, wait_s: float = 8.0,
                           sleep=time.sleep) -> None:
    """A lesson opened: minimize the editor's windows of OTHER Miyagi lesson folders (~/miyagi/lessons/*; never the
    learner's own projects, never a full-screen window in its own Space), then raise the lesson's window `win` last.
    win None: wait up to wait_s for the window showing `folder` (a running VS Code returns from `code <folder>` before
    the window has loaded the folder); nothing happens if none appears. Best effort: report["put_away"] = the folders
    minimized."""
    try:
        deadline = time.monotonic() + wait_s
        while win is None and (win := ax.folder_window(pid, folder)) is None and time.monotonic() < deadline:
            sleep(0.3)
        if win is None:
            return
        gone = [name for name, w in ax.other_lesson_windows(pid, folder) if not ax.is_fullscreen(w) and ax.minimize(w)]
        if gone:
            report["put_away"] = gone
            log.info("put away other lesson windows: %s", ", ".join(gone))
        ax.raise_window(win)
    except Exception as e:  # noqa: BLE001 - tidying windows must never break opening the lesson
        log.debug("put away other lesson windows failed: %r", e)


def left_frame(fraction: float = EDITOR_FRACTION) -> tuple[float, float, float, float] | None:
    """(x, y, w, h) of the left `fraction` of the overlay's display's visible area, in AX (top-left) coordinates.
    Kept for older callers; the layout itself is layout.plan on lesson_screen()."""
    scr = lesson_screen()
    if scr is None:
        return None
    v = scr.visible
    return (v.x, v.y, round(v.w * fraction), v.h)


def find_pid(app_name: str, bundle: str | None = None) -> int | None:
    """pid of a running app: by bundle id (VS Code's process is named "Code", not "Visual Studio Code"),
    else by name."""
    try:
        import AppKit
    except ImportError:
        return None
    if bundle:
        apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle) or []
        if len(apps):
            return int(apps[0].processIdentifier())
    for a in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if (a.localizedName() or "") in (app_name, PROCESS_NAMES.get("vscode") if app_name == VSCODE_APP else app_name):
            return int(a.processIdentifier())
    return None


def editor_pid(editor: dict) -> int | None:
    return find_pid(editor["app"], editor.get("bundle") or EDITORS.get(editor.get("id", ""), {}).get("bundle"))


def arrange(editor: dict, previous: dict | None, report: dict, *, ax=None, wait_s: float = ARRANGE_WAIT_S,
            fraction: float = EDITOR_FRACTION, sleep=time.sleep, folder: str | None = None) -> None:
    """Video lessons, with Accessibility: the lesson's window (the one showing `folder`; else the editor's focused
    window) takes the left of the overlay's display (layout.plan mode "video": the left `fraction`, the right column
    kept for the player and the steps drawer, app common/screenLayout.ts). Runs ONCE per lesson open.
    Nov 25: it no longer takes anyone out of macOS full screen. A lesson window in full screen is the learner's
    (left as it is; the overlay and the player float over full-screen Spaces), and the app the learner was in
    (`previous`, kept for callers) stays as it was: each of those exits was a Space switch while VS Code opened.
    folder: the lesson's folder; other lesson folders' windows are then put away (put_away_other_lessons)."""
    try:
        ax = ax or AX()
    except ImportError:
        report["arrange"] = "skipped: pyobjc-framework-ApplicationServices not installed"
        return
    _opening_layout(+1)
    try:
        deadline = time.monotonic() + wait_s
        win = pid = None
        while time.monotonic() < deadline:
            pid = editor_pid(editor)
            if pid:
                finder = getattr(ax, "folder_window", None) if folder else None
                win = finder(pid, folder) if finder else ax.focused_window(pid)
            if win is not None:
                break
            sleep(0.3)
        if win is None:
            report["arrange"] = f"skipped: no {editor['label']} window within {wait_s:.0f}s"
            return
        if ax.is_fullscreen(win):
            report["arrange"] = "left as it is: full screen (the learner's)"
        elif (scr := lesson_screen()) is None:
            report["arrange"] = "skipped: no screen info"
            return
        else:
            with _layout_lock:
                _claim(win)
                p = L.plan(scr, mode="video", editor=L.EditorState(frame=_frame_of(ax, win)), fraction=fraction,
                           pill_clearance=PILL_CLEARANCE, bar_clearance=BAR_CLEARANCE)
                if p.action == "set":
                    report["arranged"] = _set_frame(ax, win, *p.bounds.tuple(), mode="video")
                    report["frame"] = [round(v) for v in p.bounds.tuple()]
                    report["arrange"] = "done" if report["arranged"] else "failed: the editor refused the new frame"
                else:
                    report["arrange"] = f"done ({p.reason})"
        if folder:
            put_away_other_lessons(ax, pid, folder, win if getattr(ax, "folder_window", None) else None, report,
                                   sleep=sleep)
    finally:
        _opening_layout(-1, ax)


# --------------------------------------------------------------------------- open

def _run(argv: list[str]) -> bool:
    """Run and wait briefly: the editor CLI hands off to the app and exits 0 within a few seconds.
    env=safe_env(): a `code` CLI that starts VS Code hands it this environment, and VS Code hands it on to every
    integrated terminal, task and extension host, so no provider key or miyagi token may be in it."""
    try:
        r = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=15, check=False,
                           start_new_session=True, env=safe_env())
    except subprocess.TimeoutExpired:
        return True  # still handing off: the window is coming
    except OSError as e:
        log.warning("could not run %s: %s", argv[0], e)
        return False
    if r.returncode != 0:
        log.warning("%s exited %s: %s", Path(argv[0]).name, r.returncode, r.stderr.decode(errors="replace")[:200])
    return r.returncode == 0


def open_editor_report(path: Path | str, file: str | None = None, *, runner: Runner | None = None,
                       editor: dict | None = None, arrange_windows: bool | None = None, wait: bool = False,
                       trusted: Callable[[], bool] = ax_trusted, previous: dict | None = None,
                       fullscreen: bool = False, reuse_window: bool = False) -> dict:
    """Open the folder in the preferred editor and bring it frontmost; arrange windows when allowed.

    fullscreen=True ("Just teach me" mode): the lesson's window fills the screen (maximized; MIYAGI_FULLSCREEN=native:
    macOS full screen) instead of the left-60% layout (needs Accessibility and MIYAGI_ARRANGE != 0; else
    `fullscreen` says why and the editor stays a normal frontmost window).
    Returns {opened, editor, label, command, frontmost, ax_trusted, arrange, fullscreen?, unfullscreened?,
    arranged?, frame?}. The Accessibility part runs in a background thread unless wait=True."""
    run = runner or _run
    folder = Path(path).expanduser().resolve()
    ed = editor if editor is not None else preferred_editor()
    report: dict = {"opened": False, "editor": ed["id"] if ed else None, "label": ed["label"] if ed else None,
                    "frontmost": False, "ax_trusted": False, "arrange": "not attempted"}
    if not folder.is_dir():
        log.warning("open_editor: %s is not a folder", folder)
        report["error"] = "not a folder"
        return report
    if ed is None:
        report["error"] = "no supported editor installed (VS Code)"
        return report
    target = None
    if file:
        f = Path(file).expanduser()
        f = f if f.is_absolute() else folder / f
        target = f if f.is_file() else None
    prev = previous if previous is not None else frontmost_app(skip={ed["app"], ed.get("process") or PROCESS_NAMES.get(ed["id"], "")})
    if ed.get("cli"):
        # no `-n` in general: `code <folder>` focuses the window that already has this folder, and opens one only if
        # none does. reuse_window (reuse_lesson_window: the frontmost VS Code window shows an OLDER Miyagi lesson
        # folder and no window has this one) -> `-n`: this folder gets a window of its own. E21: `-r` swapped it into
        # the old lesson's window, which then asked to save weather.py under Miyagi's sheet; the old window is
        # minimized instead (put_away_other_lessons), its unsaved edits kept, no dialog.
        argv = [ed["cli"], *(["-n"] if reuse_window else []), str(folder)] + file_args(target)
        report["command"] = " ".join([Path(argv[0]).name, *argv[1:]])
        report["opened"] = run(argv)
    if not report["opened"] and sys.platform == "darwin":
        argv = ["open", "-a", ed["app"], str(folder)] + ([str(target)] if target else [])
        report["command"] = " ".join(argv)
        report["opened"] = run(argv)
    if not report["opened"]:
        return report
    if sys.platform == "darwin":  # the safe part: bring it to the front (works without Accessibility)
        report["frontmost"] = run(["open", "-a", ed["app"]])
    report["ax_trusted"] = trusted()
    if arrange_windows is None:
        arrange_windows = os.environ.get("MIYAGI_ARRANGE", "1") != "0"
    if fullscreen:
        report["arrange"] = "off (full screen requested)"
        if not arrange_windows:
            report["fullscreen"] = "off (MIYAGI_ARRANGE=0)"
        elif not report["ax_trusted"]:
            report["fullscreen"] = "skipped: Accessibility not granted (the learner can press Ctrl+Cmd+F)"
        elif wait:
            make_fullscreen(ed, report, folder=str(folder))
        else:
            report["fullscreen"] = "scheduled"
            threading.Thread(target=make_fullscreen, args=(ed, report), kwargs={"folder": str(folder)}, daemon=True,
                             name="miyagi-fullscreen").start()
        log.info("open_editor %s: %s", folder, report)
        return report
    if not arrange_windows:
        report["arrange"] = "off (MIYAGI_ARRANGE=0)"
    elif not report["ax_trusted"]:
        report["arrange"] = "skipped: Accessibility not granted"
    elif wait:
        arrange(ed, prev, report, folder=str(folder))
    else:
        report["arrange"] = "scheduled"
        threading.Thread(target=arrange, args=(ed, prev, report), kwargs={"folder": str(folder)}, daemon=True,
                         name="miyagi-arrange").start()
    log.info("open_editor %s: %s", folder, {k: v for k, v in report.items() if k != "frame"})
    return report


def open_editor(path: Path | str, file: str | None = None, *, runner: Runner | None = None, **kw) -> bool:
    """Open `path` in Cursor/VS Code focused on `file`, frontmost; arrange with Accessibility. Returns whether it opened."""
    return bool(open_editor_report(path, file, runner=runner, **kw)["opened"])


# --------------------------------------------------------------------------- where to type (Accessibility)

_ax_enabled: dict[int, float] = {}  # pid -> when AXManualAccessibility was set (once per process, like E6)


def _frontmost_editor_pid() -> tuple[int, str] | None:
    """(pid, app name) of Cursor/VS Code: the frontmost app if it is one, else the preferred editor."""
    try:
        import AppKit
    except ImportError:
        return None
    bundles = {e["bundle"]: e["app"] for e in EDITORS.values()}
    front = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is not None and front.bundleIdentifier() in bundles:
        return int(front.processIdentifier()), bundles[front.bundleIdentifier()]
    ed = preferred_editor()
    pid = editor_pid(ed) if ed else None
    return (pid, ed["app"]) if pid else None


def _doc_path(document) -> Path | None:
    if not document:
        return None
    d = str(document)
    if d.startswith("file://"):
        from urllib.parse import unquote, urlparse
        d = unquote(urlparse(d).path)
    return Path(d).expanduser().resolve()


def line_rect_from_state(state: dict, line: int, window: dict | None = None) -> dict | None:
    """Rect of file line `line` from an editor snapshot {caret_line, line_rect:{x,y,w,h}, line_height}: the caret
    line's exact rect (Monaco's hidden textarea sits on it) shifted by whole lines. None when the caret is
    off-screen or the line is outside the window. Folding/word wrap shift lines: treat as a hint, cross-check with OCR."""
    lr, h = state.get("line_rect"), state.get("line_height")
    if not lr or not h or h <= 2:
        return None
    y = lr["y"] + (int(line) - int(state["caret_line"])) * h
    rect = {"x": lr["x"], "y": y, "w": lr["w"], "h": h}
    if window and not (window["y"] <= y and y + h <= window["y"] + window["h"]):
        return None
    return rect


def editor_line_location(file: str | Path, line: int, *, snapshot: Callable[[], dict | None] | None = None,
                         screen_locate: Callable | None = None) -> dict:
    """Where `line` (1-based) of `file` is on screen in Cursor/VS Code, best source first:
    1. Accessibility (exact caret-anchored row, a few AX reads; needs the permission),
    2. E6's screen reader `server.screen.locate_line` (works without Accessibility; PR #9) when installed.
    -> {rect: {x,y,w,h} | None, source: "ax"|"screen"|None, reason, direction?, visible_lines?, line_height?}
    rect is in top-left global screen points (spotlight space). reason: None | no_editor | file_not_active |
    not_visible | not_found | unavailable. direction "up"/"down" = scrolled off: jump with goto_argv() and ask again."""
    out: dict = {"rect": None, "source": None, "reason": "unavailable", "line": int(line)}
    try:
        snap = snapshot() if snapshot else _ax_editor_snapshot()
    except Exception as e:  # noqa: BLE001 - never break a spotlight over an AX read
        log.debug("editor snapshot failed: %r", e)
        snap = None
    if snap and not _window_on_screen(snap.get("pid"), snap.get("title")):
        snap = None  # VS Code's focused window is on another Space: its caret rect would box whatever IS showing
    if snap:
        doc, want = _doc_path(snap.get("document")), Path(file).expanduser().resolve()
        if doc is not None and doc != want:
            out["reason"] = "file_not_active"
        elif (rect := line_rect_from_state(snap, line, snap.get("window"))) is not None:
            return {**out, "rect": rect, "source": "ax", "reason": None, "line_height": snap.get("line_height")}
        else:
            out["reason"] = "not_visible"
    locate = screen_locate
    if locate is None:
        try:
            from server.screen import (
                locate_line as locate,  # E6 (PR #9); absent on older builds
            )
        except ImportError:
            locate = None
    if locate is None:
        return out
    try:
        loc = locate(str(file), int(line))
    except Exception as e:  # noqa: BLE001 - screen reader not running / no permission: just no answer
        log.debug("screen locate_line failed: %s", e)
        return out
    d = loc.to_dict() if hasattr(loc, "to_dict") else dict(loc or {})
    rect = d.get("rect")
    out.update(rect=rect, source="screen" if rect else None, reason=d.get("reason") if not rect else None)
    for k in ("direction", "visible_lines", "line_height", "text_x2"):  # t8 text_x2: where the row's text ends
        if d.get(k) is not None:
            out[k] = d[k]
    return out


def editor_line_rect(file: str | Path, line: int, *, snapshot: Callable[[], dict | None] | None = None,
                     screen_locate: Callable | None = None) -> dict | None:
    """{x, y, w, h, line, source} of `line` of `file` in the open editor, or None (see editor_line_location
    for why). Accessibility first, then E6's screen reader."""
    loc = editor_line_location(file, line, snapshot=snapshot, screen_locate=screen_locate)
    if not loc["rect"]:
        return None
    return {**loc["rect"], "line": int(line), "source": loc["source"]}


def _pair(v, a: str, b: str) -> tuple[float, float]:
    """pyobjc hands AX struct values back either as structs (pt.x / r.location) or as plain tuples."""
    if isinstance(v, (tuple, list)):
        return float(v[0]), float(v[1])
    return float(getattr(v, a)), float(getattr(v, b))


def _ax_editor_snapshot() -> dict | None:
    """Best effort: any AX/pyobjc surprise means "no answer" (None), never an exception into a spotlight."""
    try:
        return _ax_editor_snapshot_unsafe()
    except Exception as e:  # noqa: BLE001
        log.debug("AX editor snapshot failed: %r", e)
        return None


def _ax_editor_snapshot_unsafe() -> dict | None:
    """One-shot AX read of the frontmost editor (the same technique as E6's server/screen/ax.py)."""
    if not ax_trusted():
        return None
    target = _frontmost_editor_pid()
    if target is None:
        return None
    pid, _app = target
    try:
        import ApplicationServices as A
    except ImportError:
        return None

    def get(el, name):
        if el is None:
            return None
        err, v = A.AXUIElementCopyAttributeValue(el, name, None)
        return v if err == 0 else None

    def rect(el):
        p, sz = get(el, "AXPosition"), get(el, "AXSize")
        if p is None or sz is None:
            return None
        ok1, pt = A.AXValueGetValue(p, A.kAXValueCGPointType, None)
        ok2, sv = A.AXValueGetValue(sz, A.kAXValueCGSizeType, None)
        if not (ok1 and ok2) or pt is None or sv is None:
            return None
        x, y = _pair(pt, "x", "y")
        w, h = _pair(sv, "width", "height")
        return {"x": x, "y": y, "w": w, "h": h}

    app = A.AXUIElementCreateApplication(pid)
    A.AXUIElementSetMessagingTimeout(app, 0.3)
    if pid not in _ax_enabled:  # no AXEnhancedUserInterface fallback: on Electron it breaks window snapping
        A.AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)
        _ax_enabled[pid] = time.monotonic()
        return None  # Chromium builds its tree now; ask again in a second
    if time.monotonic() - _ax_enabled[pid] < 1.0:
        return None
    win = get(app, "AXFocusedWindow")
    focused = get(app, "AXFocusedUIElement")
    if str(get(focused, "AXRole") or "") not in ("AXTextArea", "AXTextField"):
        return None
    text = get(focused, "AXValue")
    if not text:  # "" = accessibilitySupport "off": Monaco empties its AX text, so caret_line/line_rect would be wrong
        return None
    text = str(text)
    sr = get(focused, "AXSelectedTextRange")
    caret = 0
    if sr is not None:
        ok, r = A.AXValueGetValue(sr, A.kAXValueCFRangeType, None)
        caret = int(_pair(r, "location", "length")[0]) if ok and r is not None else 0  # NSRange or (loc, len)
    document = get(win, "AXDocument")
    start = _page_start(text, _doc_path(document))
    lr = rect(focused)
    if lr is None or lr["h"] <= 2 or lr["w"] <= 2:  # parked at the top-left = caret off-screen
        lr = None
    return {"document": document, "caret_line": start + text[:max(0, min(caret, len(text)))].count("\n"),
            "line_rect": lr, "line_height": lr["h"] if lr else None, "window": rect(win),
            "title": str(get(win, "AXTitle") or ""), "pid": pid}


def _window_on_screen(pid: int | None, title: str | None) -> bool:
    """Is the app's window titled `title` (AX's focused window) on screen on the current Space? A full-screen window
    on another Space is not. Unknown (no pid/title, no Quartz, window names unreadable): True."""
    if not pid or not title:
        return True
    try:
        import Quartz

        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        wins = [w for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
                if int(w.get("kCGWindowOwnerPID", -1)) == int(pid) and w.get("kCGWindowLayer", 1) == 0]
    except Exception:  # noqa: BLE001 - no window list: can't tell
        return True
    if not wins:
        return False
    names = [str(w.get("kCGWindowName") or "").lstrip("●•⚫ ").strip() for w in wins if w.get("kCGWindowName")]
    return not names or title.lstrip("●•⚫ ").strip() in names


def _page_start(text: str, document: Path | None, page: int = 500) -> int:
    """1-based file line where the editor's 500-line AX page starts (E6's approach): 1 for small files, else
    match the page's first lines against the file on disk."""
    if document is None or not document.is_file():
        return 1
    try:
        lines = document.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return 1
    if len(lines) <= page:
        return 1
    head = text.split("\n")[:3]
    for i in list(range(0, len(lines), page)) + list(range(len(lines))):
        if lines[i:i + len(head)] == head:
            return i + 1
    return 1


# --------------------------------------------------------------------------- open once, never steal focus

MIYAGI_BUNDLES = {"dev.sandhacks.miyagi", "com.github.electron"}
OPEN_WAIT_S = float(os.environ.get("MIYAGI_OPEN_WAIT_S", "120"))  # how long an auto-open waits for Miyagi to let go
_open_lock = threading.Lock()
_opened: dict[tuple[str, str], dict] = {}  # (lesson id, folder) -> {"state": waiting|opening|open, "t", "report"}


def _frontmost() -> tuple[str, str] | None:
    """(bundle id, name) of the active app, live. NSWorkspace.frontmostApplication goes stale in a process with
    no AppKit run loop (the uvicorn engine), so ask Launch Services (`lsappinfo`, ~15 ms, no permission)."""
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=2, check=False,
                             env=safe_env()).stdout.strip()
        if asn:
            info = subprocess.run(["lsappinfo", "info", "-only", "bundleID", "-only", "name", asn],
                                  capture_output=True, text=True, timeout=2, check=False, env=safe_env()).stdout
            bid = re.search(r'"CFBundleIdentifier"="([^"]*)"', info)
            name = re.search(r'"LSDisplayName"="([^"]*)"', info)
            if bid or name:
                return (bid.group(1) if bid else "", name.group(1) if name else "")
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        import AppKit
    except ImportError:
        return None
    a = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    return (str(a.bundleIdentifier() or ""), str(a.localizedName() or "")) if a is not None else None


_LIVE: Any = object()  # "ask the system now"; an explicit None is "no app known in front" (never a second live query)


def miyagi_focused(front: tuple[str, str] | None = _LIVE) -> bool:
    """Is our overlay (the launcher, a card's text box) the active app? Then any editor activation would blur
    it, and the launcher closes on blur. No argument: the live frontmost app. None: nothing known in front (e.g. an
    injected focus() that found nothing): not Miyagi, never a second, live lookup of this Mac's front app."""
    f = _frontmost() if front is _LIVE else front
    return bool(f) and (f[0] in MIYAGI_BUNDLES or f[1].lower() in OVERLAY_NAMES)


def editor_focused(editor: dict, front: tuple[str, str] | None = _LIVE) -> bool:
    f = _frontmost() if front is _LIVE else front
    return bool(f) and f[0] == (editor.get("bundle") or EDITORS.get(editor.get("id", ""), {}).get("bundle"))


def editor_window_up(editor: dict) -> bool:
    """Does the editor have an on-screen window yet? (window owner pids; no Screen Recording needed)"""
    pid = editor_pid(editor)
    if pid is None:
        return False
    try:
        import Quartz
    except ImportError:
        return True
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    return any(int(w.get("kCGWindowOwnerPID", -1)) == pid and w.get("kCGWindowLayer", 1) == 0
               for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or [])


def reset_open_state() -> None:
    """Forget which lessons opened the editor (tests; a new engine run starts empty anyway)."""
    with _open_lock:
        _opened.clear()


def open_state(folder: str | Path, lesson_id: str = "") -> dict | None:
    return _opened.get((lesson_id or "", str(Path(folder).expanduser().resolve())))


def open_lesson_editor(folder: str | Path, file: str | None = None, *, lesson_id: str = "", fullscreen: bool = False,
                       explicit: bool = False, runner: Runner | None = None, busy: Callable[[], bool] | None = None,
                       wait_s: float | None = None, background: bool = True, sleep=time.sleep,
                       focus: Callable[[], tuple[str, str] | None] | None = None,
                       windows: Callable[[], list[dict]] | None = None, reuse: bool | None = None,
                       miyagi_wait_s: float | None = None, cancelled: Callable[[], bool] | None = None, **kw) -> dict:
    """Open the lesson folder in the editor AT MOST ONCE per (lesson id, folder); idempotent and focus-safe.

    - First call: `code <folder> -g <file>` (no `-n`: VS Code focuses a window that already has the folder; `-n` only
      when the frontmost window shows an older lesson, E21), then the one-time arrange / full screen. An automatic
      call (explicit=False) first waits until the learner isn't in Miyagi (launcher/cards: `miyagi_focused`) and
      `busy()` (typing) is false; if that takes a while it waits in a background thread (background=True) instead
      of blocking the caller.
    - Later calls: nothing, unless explicit=True (the learner pressed "Open VS Code"): then `code <folder>
      [-g <file>]` brings that folder's existing window forward. Never a second window, never a re-arrange.
    - file: the latest call's file wins, so a deferred first open shows the file asked for last (the step's), not
      README.md (L2: the waiter's `-g README.md` landed after Open's jump to nn.py).
    - miyagi_wait_s ("Just teach me", L5): Miyagi in front holds an automatic open only this long, then only busy()
      does (the learner stays in Miyagi's drawer, so "until they leave Miyagi" was forever). cancelled(): a newer
      lesson; the waiter then opens nothing.
    Returns open_editor_report()'s dict, or {"opened": False, "already": True} / {"deferred": True}."""
    key = (lesson_id or "", str(Path(folder).expanduser().resolve()))
    front = focus or _frontmost
    with _open_lock:
        st = _opened.get(key)
        first = st is None
        if first:
            st = _opened[key] = {"state": "waiting", "t": time.monotonic(), "file": file}
        elif file:
            st["file"] = file  # L2: a first open still waiting opens on this one
    if not first and st.get("state") == "open" and windows is None and not _lesson_window_alive(key[1]):
        # The editor was quit (or the folder's window closed) since it opened: open it again. A rerun of the same
        # lesson in the same folder (Demo, a second "Just teach me") otherwise left the learner with no VS Code at
        # all (Michael, Nov 15 5:11 AM).
        with _open_lock:
            st = _opened[key] = {"state": "waiting", "t": time.monotonic(), "file": file}
        first = True
        log.info("editor for %s was closed since it opened: opening it again", Path(key[1]).name)
    if not first:
        if not explicit:
            return {"opened": False, "already": True, "state": st["state"]}
        ed = kw.get("editor") or preferred_editor()
        if not ed:
            return {"opened": False, "already": True, "error": "no supported editor installed (VS Code)"}
        target = Path(file) if file and Path(file).is_absolute() else (Path(key[1]) / file if file else None)
        if ed.get("cli"):
            argv = [ed["cli"], key[1]] + file_args(target if target and target.is_file() else None)
        elif sys.platform == "darwin":  # the app is there but no CLI (none on PATH, none inside it): macOS opens it
            argv = ["open", "-a", ed.get("app_path") or ed["app"], key[1]] + ([str(target)] if target and target.is_file() else [])
        else:
            return {"opened": False, "already": True, "error": "no editor CLI"}
        ok = (runner or _run)(argv)
        log.info("editor already open for %s: brought forward (%s)", Path(key[1]).name, ok)
        return {"opened": bool(ok), "already": True, "command": " ".join([Path(argv[0]).name, *argv[1:]])}

    t_ask = time.monotonic()

    def blocked() -> bool:
        held = miyagi_focused(front()) and (miyagi_wait_s is None or time.monotonic() - t_ask < miyagi_wait_s)
        return held or bool(busy and busy())

    def go() -> dict:
        st["state"] = "opening"
        use_r = reuse_lesson_window(key[1], windows=windows) if reuse is None else reuse
        rep = open_editor_report(key[1], st.get("file") or file, runner=runner, fullscreen=fullscreen,
                                 reuse_window=use_r, **kw)
        rep["reused_window"] = use_r
        with _open_lock:
            if rep.get("opened"):
                st.update(state="open", report=rep)
            else:
                _opened.pop(key, None)  # failed: a later call may try again
        return rep

    if explicit or not blocked():
        return go()
    limit = OPEN_WAIT_S if wait_s is None else wait_s

    def wait_then_go() -> dict:
        t0 = time.monotonic()
        while blocked():
            if time.monotonic() - t0 > limit:
                with _open_lock:
                    _opened.pop(key, None)
                log.info("auto-open of %s gave up: the learner stayed in Miyagi for %.0fs", Path(key[1]).name, limit)
                return {"opened": False, "deferred": True, "gave_up": True}
            sleep(0.5)
        if cancelled is not None and cancelled():  # L5: a newer lesson (or the lesson ended) while it waited
            with _open_lock:
                _opened.pop(key, None)
            log.info("auto-open of %s dropped: the lesson changed while it waited", Path(key[1]).name)
            return {"opened": False, "deferred": True, "cancelled": True}
        return go()

    if not background:
        return wait_then_go()
    threading.Thread(target=wait_then_go, daemon=True, name="miyagi-open-editor").start()
    log.info("auto-open of %s deferred: the learner is in Miyagi / typing", Path(key[1]).name)
    return {"opened": False, "deferred": True}


_state_editor: tuple[float, dict | None] | None = None  # (when, preferred_editor()) for lesson_window_state


def lesson_window_state(folder: str | Path) -> bool | None:
    """v2 (lesson.paused "editor_closed"): True when VS Code runs with a window on this lesson folder, False when it
    was quit or that window was closed, None when it can't tell (no window list): a pause needs a sure False. Blocking
    (process + window lists): call it in a thread. Never opens, raises or focuses anything."""
    global _state_editor
    try:
        now = time.monotonic()
        if _state_editor is None or now - _state_editor[0] > 60.0:  # polled every few seconds: no mdfind each time
            _state_editor = (now, preferred_editor())
        ed = _state_editor[1]
        if not ed:
            return None
        if editor_pid(ed) is None:
            return False  # the editor isn't running at all
        from .active import vscode_windows

        wins = vscode_windows()
    except Exception:  # noqa: BLE001
        return None
    if not wins:  # running with no window, or titles unreadable (no Screen Recording grant): not sure enough to pause
        return None
    name = Path(folder).expanduser().resolve().name
    names = [w.get("folder_name") for w in wins if isinstance(w, dict)]
    if not any(names):
        return None  # windows without a folder in their titles (a title setting): can't tell
    return name in names


def _lesson_window_alive(folder: str | Path) -> bool:
    """Is the editor running with a window on this lesson folder right now? Unknown counts as yes (keep the
    at-most-once rule); a plain `code <folder>` on a window that is there only focuses it anyway.
    The companion extension answers first (its windows list their folders exactly). Without it, an empty title list
    means "no window" only when titles are readable (Screen Recording granted); without that grant it is unknown
    (Nov 24, the 1517 demo: the window was up and `code` ran again as a first open)."""
    try:
        ed = preferred_editor()
        if ed and editor_pid(ed) is None:
            return False  # the editor isn't running at all
    except Exception:  # noqa: BLE001 - no process list: assume it's still there
        return True
    seen = _companion_has_folder(folder)
    if seen is not None:
        return seen
    try:
        from .active import vscode_windows

        wins = vscode_windows()
    except Exception:  # noqa: BLE001 - no window list: assume it's still there
        return True
    if not wins:
        return not _titles_readable()  # running with no window open, or no titles to read (unknown)
    name = Path(folder).expanduser().resolve().name
    names = [w.get("folder_name") for w in wins if isinstance(w, dict)]
    if not any(names):
        return True  # windows without a folder in their titles (a title setting): can't tell
    return name in names


def _titles_readable() -> bool:
    """Can this process read other apps' window titles (macOS Screen Recording)? Preflight only: never prompts."""
    if sys.platform != "darwin":
        return False
    try:
        import Quartz

        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:  # noqa: BLE001 - no pyobjc: unknown
        return False


def _companion_has_folder(folder: str | Path) -> bool | None:
    """True / False: a VS Code window with the companion extension has / none has `folder` open. None: no companion
    answered (not installed, or VS Code still starting), so the window list decides."""
    try:
        from . import vscode_ext

        wins = vscode_ext.windows()
    except Exception:  # noqa: BLE001 - the companion is a refinement
        return None
    if not wins:
        return None
    return any(vscode_ext._inside(folder, f) for w in wins for f in (w.get("folders") or []))


def reuse_lesson_window(folder: str | Path, *, windows: Callable[[], list[dict]] | None = None) -> bool:
    """New lesson: True when the frontmost VS Code window shows an OLDER Miyagi lesson folder (under ~/miyagi/lessons)
    and no window already has this folder. The folder then opens in a NEW window (`code -n`, E21: `-r` reused the old
    lesson's window and its save dialog) and the old one is minimized. Windows outside the lessons folder are never
    touched (then a plain `code <folder>` adds or focuses a window)."""
    from .active import vscode_windows

    try:
        wins = windows() if windows else vscode_windows()
    except Exception:  # noqa: BLE001 - window list unavailable: never reuse
        return False
    if not wins:
        return False
    name = Path(folder).expanduser().resolve().name
    if any(w.get("folder_name") == name for w in wins):
        return False  # already open somewhere: plain `code <folder>` focuses it
    top = wins[0]
    return bool(top.get("miyagi_lesson")) and top.get("folder_name") != name


def jump(path: str | Path, line: int = 1, *, explicit: bool = False, runner: Runner | None = None,
         focus: Callable[[], tuple[str, str] | None] | None = None, window_up: Callable[[dict], bool] | None = None,
         opening: Callable[[], bool] | None = None) -> bool:
    """`code -r -g <file>:<line>`, but only when it can't steal focus or spawn a window:
    automatic jumps (explicit=False) run only when the editor is ALREADY the active app, its window is up,
    and no lesson folder is still waiting to open. explicit=True (a learner action: Do it for me) always jumps."""
    ed = preferred_editor()
    argv = goto_argv(path, line)
    if not ed or not argv:
        return False
    if not explicit:
        if opening() if opening else any(st["state"] != "open" for st in list(_opened.values())):
            log.debug("jump skipped: the editor is still opening")
            return False
        f = (focus or _frontmost)()
        if not editor_focused(ed, f):
            log.debug("jump skipped: %s isn't the active app (won't steal focus)", ed["label"])
            return False
        if not (window_up or editor_window_up)(ed):
            log.debug("jump skipped: no %s window yet", ed["label"])
            return False
    return bool((runner or _run)(argv))
