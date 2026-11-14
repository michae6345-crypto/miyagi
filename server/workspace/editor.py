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
PREFERENCE = ["cursor", "vscode"]
ENV_NAMES = {"cursor": "cursor", "code": "vscode", "vscode": "vscode", "vs code": "vscode", "visual studio code": "vscode"}
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
            out.append({"id": eid, "label": ed["label"], "app": ed["app"], "app_path": app_path, "cli": cli})
    return out


def preferred_editor(installed: list[dict] | None = None) -> dict | None:
    """MIYAGI_EDITOR (cursor | code) if installed, else Cursor, else VS Code, else None."""
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

    def exit_fullscreen(self, win) -> bool:
        return self.A.AXUIElementSetAttributeValue(win, "AXFullScreen", False) == 0

    def set_frame(self, win, x: float, y: float, w: float, h: float) -> bool:
        A = self.A
        pos = A.AXValueCreate(A.kAXValueCGPointType, (x, y))
        size = A.AXValueCreate(A.kAXValueCGSizeType, (w, h))
        ok1 = A.AXUIElementSetAttributeValue(win, "AXPosition", pos) == 0
        ok2 = A.AXUIElementSetAttributeValue(win, "AXSize", size) == 0
        return ok1 and ok2


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


def find_pid(app_name: str) -> int | None:
    try:
        import AppKit
    except ImportError:
        return None
    for a in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if (a.localizedName() or "") == app_name:
            return int(a.processIdentifier())
    return None


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
        pid = find_pid(editor["app"])
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
                       trusted: Callable[[], bool] = ax_trusted, previous: dict | None = None) -> dict:
    """Open the folder in the preferred editor and bring it frontmost; arrange windows when allowed.

    Returns {opened, editor, label, command, frontmost, ax_trusted, arrange, unfullscreened?, arranged?, frame?}.
    The Accessibility part runs in a background thread unless wait=True (it polls for the editor's window)."""
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
    prev = previous if previous is not None else frontmost_app(skip={ed["app"]})
    if ed.get("cli"):
        argv = [ed["cli"], "-n", str(folder)] + (["-g", str(target)] if target else [])
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
