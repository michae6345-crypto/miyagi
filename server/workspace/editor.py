"""open_editor(): open a lesson folder in the learner's editor (Cursor or VS Code), bring it to the front,
and, only with Accessibility permission, make room for the overlay's video.

Editor choice: MIYAGI_EDITOR=cursor|code (vscode) if that editor is installed, else Cursor, else VS Code.

Without Accessibility (always): `<cli> -n <dir> -g <file>` (fallback `open -a <App> <dir> [<file>]`), then
`open -a <App>` so the editor is frontmost. A full-screen app the learner was in stays as it is; the editor
gets its own window (macOS switches to it).
With Accessibility (AXIsProcessTrusted) and MIYAGI_ARRANGE != 0: the previous frontmost app's focused window
leaves full screen (AXFullScreen=false; never closed, never quit), and the editor's window is moved to the
left 60% of the screen so the video player docked on the right 40% stays visible.
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
# Our own overlay must never be treated as "the app the learner was in".
OVERLAY_NAMES = {n.strip().lower() for n in os.environ.get("MIYAGI_OVERLAY_APPS", "Miyagi,miyagi-overlay,Electron").split(",") if n.strip()}

Runner = Callable[[list[str]], bool]


# --------------------------------------------------------------------------- which editor

def _app_path(ed: dict) -> str | None:
    for base in ("/Applications", str(Path.home() / "Applications")):
        p = Path(base) / f"{ed['app']}.app"
        if p.exists():
            return str(p)
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["mdfind", f"kMDItemCFBundleIdentifier == '{ed['bundle']}'"], capture_output=True,
                                 text=True, timeout=5, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        return next((ln for ln in out.splitlines() if ln.endswith(".app")), None)
    return None


def _cli(ed: dict) -> str | None:
    if found := shutil.which(ed["cli"]):
        return found
    return ed["bundled_cli"] if Path(ed["bundled_cli"]).exists() else None


def installed_editors() -> list[dict]:
    """[{id, label, app, app_path, cli}] for the supported editors on this Mac, in preference order."""
    out = []
    for eid in PREFERENCE:
        ed = EDITORS[eid]
        app_path, cli = _app_path(ed), _cli(ed)
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
    """"Cursor" / "Visual Studio Code": for "Open Cursor?" cards."""
    return EDITORS[editor_id()]["label"]


def code_cli() -> str | None:
    """CLI of the preferred editor (`cursor` or `code`), for `-r -g file:line` jumps."""
    ed = preferred_editor()
    return ed["cli"] if ed else _cli(EDITORS["vscode"])


def goto_argv(path: str | Path, line: int = 1) -> list[str] | None:
    """`<cli> -r -g <file>:<line>` for the preferred editor (reuse its window), or None."""
    cli = code_cli()
    return [cli, "-r", "-g", f"{path}:{max(1, int(line))}"] if cli else None


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

    def is_fullscreen(self, win) -> bool:
        return bool(self._get(win, "AXFullScreen"))

    def enter_fullscreen(self, win) -> bool:
        return self.A.AXUIElementSetAttributeValue(win, "AXFullScreen", True) == 0

    def exit_fullscreen(self, win) -> bool:
        return self.A.AXUIElementSetAttributeValue(win, "AXFullScreen", False) == 0

    def set_frame(self, win, x: float, y: float, w: float, h: float) -> bool:
        A = self.A
        pos = A.AXValueCreate(A.kAXValueCGPointType, (x, y))
        size = A.AXValueCreate(A.kAXValueCGSizeType, (w, h))
        ok1 = A.AXUIElementSetAttributeValue(win, "AXPosition", pos) == 0
        ok2 = A.AXUIElementSetAttributeValue(win, "AXSize", size) == 0
        return ok1 and ok2


def make_fullscreen(editor: dict, report: dict, *, ax=None, wait_s: float = 8.0, sleep=time.sleep) -> None:
    """With Accessibility: put the editor's window in macOS full screen (AXFullScreen=true)."""
    try:
        ax = ax or AX()
    except ImportError:
        report["fullscreen"] = "skipped: pyobjc-framework-ApplicationServices not installed"
        return
    deadline = time.monotonic() + wait_s
    win = None
    while time.monotonic() < deadline:
        pid = editor_pid(editor)
        win = ax.focused_window(pid) if pid else None
        if win is not None:
            break
        sleep(0.3)
    if win is None:
        report["fullscreen"] = f"skipped: no {editor['label']} window within {wait_s:.0f}s"
        return
    if ax.is_fullscreen(win):
        report["fullscreen"] = "done (already full screen)"
        return
    report["fullscreen"] = "done" if ax.enter_fullscreen(win) else "failed: the editor refused AXFullScreen"


def left_frame(fraction: float = EDITOR_FRACTION) -> tuple[float, float, float, float] | None:
    """(x, y, w, h) of the left `fraction` of the main screen's visible area, in AX (top-left) coordinates."""
    try:
        import AppKit
    except ImportError:
        return None
    screens = AppKit.NSScreen.screens()
    main = AppKit.NSScreen.mainScreen()
    if not screens or main is None:
        return None
    total_h = screens[0].frame().size.height  # AX y is measured from the top of the primary display
    vf = main.visibleFrame()
    top = total_h - (vf.origin.y + vf.size.height)
    return (vf.origin.x, top, round(vf.size.width * fraction), vf.size.height)


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


def arrange(editor: dict, previous: dict | None, report: dict, *, ax=None, wait_s: float = 8.0,
            fraction: float = EDITOR_FRACTION, sleep=time.sleep) -> None:
    """With Accessibility: un-fullscreen the previous app's window, put the editor on the left `fraction`."""
    try:
        ax = ax or AX()
    except ImportError:
        report["arrange"] = "skipped: pyobjc-framework-ApplicationServices not installed"
        return
    if previous and previous.get("name") != editor["app"]:
        win = ax.focused_window(previous["pid"])
        if win is not None and ax.is_fullscreen(win):
            report["unfullscreened"] = previous["name"] if ax.exit_fullscreen(win) else False
            sleep(1.0)  # the space animation; moving windows during it is ignored
    deadline = time.monotonic() + wait_s
    win = None
    while time.monotonic() < deadline:
        pid = editor_pid(editor)
        win = ax.focused_window(pid) if pid else None
        if win is not None:
            break
        sleep(0.3)
    if win is None:
        report["arrange"] = f"skipped: no {editor['label']} window within {wait_s:.0f}s"
        return
    if ax.is_fullscreen(win):
        ax.exit_fullscreen(win)
        sleep(1.0)
    frame = left_frame(fraction)
    if frame is None:
        report["arrange"] = "skipped: no screen info"
        return
    report["arranged"] = ax.set_frame(win, *frame)
    report["frame"] = [round(v) for v in frame]
    report["arrange"] = "done" if report["arranged"] else "failed: the editor refused the new frame"


# --------------------------------------------------------------------------- open

def _run(argv: list[str]) -> bool:
    """Run and wait briefly: the editor CLI hands off to the app and exits 0 within a few seconds."""
    try:
        r = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=15, check=False, start_new_session=True)
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

    fullscreen=True ("Just teach me" mode): the editor goes macOS full screen instead of the left-60% layout
    (needs Accessibility; without it `fullscreen` says so and the editor stays a normal frontmost window).
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
        report["error"] = "no supported editor installed (Cursor or VS Code)"
        return report
    target = None
    if file:
        f = Path(file).expanduser()
        f = f if f.is_absolute() else folder / f
        target = f if f.is_file() else None
    prev = previous if previous is not None else frontmost_app(skip={ed["app"], ed.get("process") or PROCESS_NAMES.get(ed["id"], "")})
    if ed.get("cli"):
        # no `-n`: `code <folder>` focuses the window that already has this folder, and opens one only if none does
        # reuse_window: the frontmost VS Code window is an older Miyagi lesson folder -> `-r` swaps this folder in
        argv = [ed["cli"], *(["-r"] if reuse_window else []), str(folder)] + (["-g", str(target)] if target else [])
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
    if fullscreen:
        report["arrange"] = "off (full screen requested)"
        if not report["ax_trusted"]:
            report["fullscreen"] = "skipped: Accessibility not granted (the learner can press Ctrl+Cmd+F)"
        elif wait:
            make_fullscreen(ed, report)
        else:
            report["fullscreen"] = "scheduled"
            threading.Thread(target=make_fullscreen, args=(ed, report), daemon=True, name="miyagi-fullscreen").start()
        log.info("open_editor %s: %s", folder, report)
        return report
    if arrange_windows is None:
        arrange_windows = os.environ.get("MIYAGI_ARRANGE", "1") != "0"
    if not arrange_windows:
        report["arrange"] = "off (MIYAGI_ARRANGE=0)"
    elif not report["ax_trusted"]:
        report["arrange"] = "skipped: Accessibility not granted"
    elif wait:
        arrange(ed, prev, report)
    else:
        report["arrange"] = "scheduled"
        threading.Thread(target=arrange, args=(ed, prev, report), daemon=True, name="miyagi-arrange").start()
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
    snap = snapshot() if snapshot else _ax_editor_snapshot()
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
    for k in ("direction", "visible_lines", "line_height"):
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


def _ax_editor_snapshot() -> dict | None:
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
        return {"x": float(pt.x), "y": float(pt.y), "w": float(sv.width), "h": float(sv.height)} if ok1 and ok2 else None

    app = A.AXUIElementCreateApplication(pid)
    A.AXUIElementSetMessagingTimeout(app, 0.3)
    if pid not in _ax_enabled:
        if A.AXUIElementSetAttributeValue(app, "AXManualAccessibility", True) != 0:
            A.AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface", True)
        _ax_enabled[pid] = time.monotonic()
        return None  # Chromium builds its tree now; ask again in a second
    if time.monotonic() - _ax_enabled[pid] < 1.0:
        return None
    win = get(app, "AXFocusedWindow")
    focused = get(app, "AXFocusedUIElement")
    if str(get(focused, "AXRole") or "") not in ("AXTextArea", "AXTextField"):
        return None
    text = get(focused, "AXValue")
    if text is None:
        return None
    text = str(text)
    sr = get(focused, "AXSelectedTextRange")
    caret = 0
    if sr is not None:
        ok, r = A.AXValueGetValue(sr, A.kAXValueCFRangeType, None)
        caret = int(r.location) if ok else 0
    document = get(win, "AXDocument")
    start = _page_start(text, _doc_path(document))
    lr = rect(focused)
    if lr is None or lr["h"] <= 2 or lr["w"] <= 2:  # parked at the top-left = caret off-screen
        lr = None
    return {"document": document, "caret_line": start + text[:max(0, min(caret, len(text)))].count("\n"),
            "line_rect": lr, "line_height": lr["h"] if lr else None, "window": rect(win)}


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
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=2, check=False).stdout.strip()
        if asn:
            info = subprocess.run(["lsappinfo", "info", "-only", "bundleID", "-only", "name", asn],
                                  capture_output=True, text=True, timeout=2, check=False).stdout
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


def miyagi_focused(front: tuple[str, str] | None = None) -> bool:
    """Is our overlay (the launcher, a card's text box) the active app? Then any editor activation would blur
    it, and the launcher closes on blur."""
    f = front if front is not None else _frontmost()
    return bool(f) and (f[0] in MIYAGI_BUNDLES or f[1].lower() in OVERLAY_NAMES)


def editor_focused(editor: dict, front: tuple[str, str] | None = None) -> bool:
    f = front if front is not None else _frontmost()
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
                       windows: Callable[[], list[dict]] | None = None, reuse: bool | None = None, **kw) -> dict:
    """Open the lesson folder in the editor AT MOST ONCE per (lesson id, folder); idempotent and focus-safe.

    - First call: `code <folder> -g <file>` (never `-n`: VS Code focuses a window that already has the folder),
      then the one-time arrange / full screen. An automatic call (explicit=False) first waits until the
      learner isn't in Miyagi (launcher/cards: `miyagi_focused`) and `busy()` (typing) is false; if that takes
      a while it waits in a background thread (background=True) instead of blocking the caller.
    - Later calls: nothing, unless explicit=True (the learner pressed "Open VS Code"): then `code <folder>
      [-g <file>]` brings that folder's existing window forward. Never a second window, never a re-arrange.
    Returns open_editor_report()'s dict, or {"opened": False, "already": True} / {"deferred": True}."""
    key = (lesson_id or "", str(Path(folder).expanduser().resolve()))
    front = focus or _frontmost
    with _open_lock:
        st = _opened.get(key)
        first = st is None
        if first:
            st = _opened[key] = {"state": "waiting", "t": time.monotonic()}
    if not first:
        if not explicit:
            return {"opened": False, "already": True, "state": st["state"]}
        ed = kw.get("editor") or preferred_editor()
        if not ed or not ed.get("cli"):
            return {"opened": False, "already": True, "error": "no editor CLI"}
        target = Path(file) if file and Path(file).is_absolute() else (Path(key[1]) / file if file else None)
        argv = [ed["cli"], key[1]] + (["-g", str(target)] if target and target.is_file() else [])
        ok = (runner or _run)(argv)
        log.info("editor already open for %s: brought forward (%s)", Path(key[1]).name, ok)
        return {"opened": bool(ok), "already": True, "command": " ".join([Path(argv[0]).name, *argv[1:]])}

    def blocked() -> bool:
        return miyagi_focused(front()) or bool(busy and busy())

    def go() -> dict:
        st["state"] = "opening"
        use_r = reuse_lesson_window(key[1], windows=windows) if reuse is None else reuse
        rep = open_editor_report(key[1], file, runner=runner, fullscreen=fullscreen, reuse_window=use_r, **kw)
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
        return go()

    if not background:
        return wait_then_go()
    threading.Thread(target=wait_then_go, daemon=True, name="miyagi-open-editor").start()
    log.info("auto-open of %s deferred: the learner is in Miyagi / typing", Path(key[1]).name)
    return {"opened": False, "deferred": True}


def reuse_lesson_window(folder: str | Path, *, windows: Callable[[], list[dict]] | None = None) -> bool:
    """New lesson: reuse the frontmost VS Code window (`code -r`) only if it shows an OLDER Miyagi lesson folder
    (under ~/miyagi/lessons) and no window already has this folder. Windows outside the lessons folder are
    never touched (then a plain `code <folder>` adds or focuses a window)."""
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
