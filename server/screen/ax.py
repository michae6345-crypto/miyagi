"""Accessibility (AX) reader: exact editor/terminal state without OCR.

One serial worker thread polls the frontmost app at ~10 Hz with a short messaging timeout:
- VS Code / Cursor (Electron): turns the AX tree on ONCE per process (AXManualAccessibility),
  then reads the focused editor's live buffer page (AXValue), caret (AXSelectedTextRange),
  the caret line's exact rect (the hidden textarea sits on it: AXPosition/AXSize), the window's
  file (AXDocument) and dirty flag ("●" in the title).
- Terminal.app / iTerm2: the scrollback text (AXValue of the AXTextArea), last N lines.
- Anything: the element under the mouse (AXUIElementCopyElementAtPosition).

Coordinates are top-left global screen points, the same as OCR rects and the spotlight.
Needs macOS Accessibility permission for the responsible app; without it `trusted()` is False,
`AX_HELP` says what to grant, and the reader produces nothing (OCR keeps working).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import HIServices as AX
import Quartz
from AppKit import NSRunningApplication, NSWorkspace

from .types import Rect

log = logging.getLogger("server.screen.ax")

AX_HELP = (
    "Accessibility access is off, so the engine can't read the editor/terminal directly "
    "(falling back to OCR). Grant it:\n"
    "  System Settings > Privacy & Security > Accessibility > enable the app that runs the engine\n"
    "  (Claude / Terminal / iTerm2 / our Electron app), then restart the engine.\n"
    "In VS Code also set \"editor.accessibilitySupport\": \"on\" (never click 'No' on its screen-reader prompt)."
)

ELECTRON_EDITORS = {"com.microsoft.VSCode", "com.microsoft.VSCodeInsiders", "com.visualstudio.code.oss",
                    "com.todesktop.230313mzl4w4u92", "com.exafunction.windsurf", "com.vscodium"}
TERMINALS = {"com.apple.Terminal", "com.googlecode.iterm2"}
MESSAGING_TIMEOUT = 0.2
VSCODE_PAGE = 500  # editor.accessibilityPageSize default
TERMINAL_TAIL = 200


# ---------------------------------------------------------------------- low-level helpers

def trusted(prompt: bool = False) -> bool:
    if prompt:
        return bool(AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: True}))
    return bool(AX.AXIsProcessTrusted())


def attr(el, name):
    if el is None:
        return None
    err, v = AX.AXUIElementCopyAttributeValue(el, name, None)
    return v if err == 0 else None


def _point(v):
    ok, p = AX.AXValueGetValue(v, AX.kAXValueCGPointType, None)
    return p if ok else None


def _size(v):
    ok, s = AX.AXValueGetValue(v, AX.kAXValueCGSizeType, None)
    return s if ok else None


def rect_of(el) -> Rect | None:
    p, s = attr(el, "AXPosition"), attr(el, "AXSize")
    if p is None or s is None:
        return None
    p, s = _point(p), _size(s)
    if p is None or s is None:
        return None
    return Rect(float(p.x), float(p.y), float(s.width), float(s.height))


def selected_range(el) -> tuple[int, int] | None:
    v = attr(el, "AXSelectedTextRange")
    if v is None:
        return None
    ok, r = AX.AXValueGetValue(v, AX.kAXValueCFRangeType, None)
    return (int(r.location), int(r.length)) if ok else None


def bounds_for_range(el, loc: int, length: int) -> Rect | None:
    rng = AX.AXValueCreate(AX.kAXValueCFRangeType, AX.CFRange(loc, length))
    err, v = AX.AXUIElementCopyParameterizedAttributeValue(el, "AXBoundsForRange", rng, None)
    if err != 0 or v is None:
        return None
    ok, r = AX.AXValueGetValue(v, AX.kAXValueCGRectType, None)
    return Rect(r.origin.x, r.origin.y, r.size.width, r.size.height) if ok else None


def _s(v, limit: int = 300) -> str | None:
    if v is None:
        return None
    s = str(v)
    return s if len(s) <= limit else s[:limit] + "…"


def mouse_location() -> tuple[float, float]:
    """Cursor position, top-left global points. No permission needed."""
    loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return float(loc.x), float(loc.y)


# ---------------------------------------------------------------------- snapshot types

@dataclass
class EditorState:
    text: str                       # live (unsaved) buffer page around the caret
    page_start_line: int            # 1-based file line of text's first line
    caret: int                      # offset in `text`
    selection_len: int
    caret_line: int                 # 1-based FILE line of the caret
    line_rect: Rect | None          # exact rect of the caret line (None if caret scrolled off)
    line_height: float | None

    def rect_for_line(self, line: int) -> Rect | None:
        """Rect of file line `line` from the caret-line anchor (wrong with folding/word wrap:
        cross-check with OCR locate())."""
        if self.line_rect is None or not self.line_height:
            return None
        return Rect(self.line_rect.x, self.line_rect.y + (line - self.caret_line) * self.line_height,
                    self.line_rect.w, self.line_height)

    def line_at_y(self, y: float) -> int | None:
        if self.line_rect is None or not self.line_height:
            return None
        return self.caret_line + int((y - self.line_rect.y) // self.line_height)

    def line_text(self, line: int) -> str | None:
        lines = self.text.split("\n")
        i = line - self.page_start_line
        return lines[i] if 0 <= i < len(lines) else None

    def to_dict(self, with_text: bool = False) -> dict:
        d = {"page_start_line": self.page_start_line, "caret": self.caret, "selection_len": self.selection_len,
             "caret_line": self.caret_line, "line_rect": self.line_rect.to_dict() if self.line_rect else None,
             "line_height": self.line_height, "caret_line_text": self.line_text(self.caret_line)}
        if with_text:
            d["text"] = self.text
        return d


@dataclass
class Element:
    role: str | None
    subrole: str | None
    title: str | None
    value: str | None
    description: str | None
    rect: Rect | None
    app: str | None = None

    def to_dict(self) -> dict:
        return {"role": self.role, "subrole": self.subrole, "title": self.title, "value": self.value,
                "description": self.description, "rect": self.rect.to_dict() if self.rect else None,
                "app": self.app}


@dataclass
class AXSnapshot:
    t: float
    app: str
    bundle_id: str | None
    pid: int
    window_title: str | None = None
    document: str | None = None          # file path (AXDocument), VS Code sets it per active editor
    dirty: bool | None = None            # unsaved changes ("●" in the title)
    focused_role: str | None = None
    editor: EditorState | None = None
    terminal_lines: list[str] = field(default_factory=list)
    terminal_rect: Rect | None = None
    under_mouse: Element | None = None
    mouse: tuple[float, float] = (0.0, 0.0)
    read_ms: float = 0.0

    @property
    def text_len(self) -> int:
        return len(self.editor.text) if self.editor else sum(len(s) for s in self.terminal_lines)

    def to_dict(self, with_text: bool = False) -> dict:
        return {"t": self.t, "app": self.app, "bundle_id": self.bundle_id, "window_title": self.window_title,
                "document": self.document, "dirty": self.dirty, "focused_role": self.focused_role,
                "editor": self.editor.to_dict(with_text) if self.editor else None,
                "terminal_tail": self.terminal_lines[-20:], "under_mouse": self.under_mouse.to_dict()
                if self.under_mouse else None, "mouse": {"x": self.mouse[0], "y": self.mouse[1]},
                "read_ms": round(self.read_ms, 1)}


# ---------------------------------------------------------------------- reading

_enabled_pids: dict[int, float] = {}   # pid -> time AXManualAccessibility was set
_ready_pids: set[int] = set()          # pids whose AX mode read back on (or that ran out the wait)
_SETTLE_MAX_S = 4.0                    # Electron waits ~2 s before it builds the tree; don't wait forever


def enable_electron_ax(app_el, pid: int) -> bool:
    """Ask an Electron app (VS Code) to build its AX tree. ONCE per pid: re-setting it every frame
    makes Chromium rebuild the tree (and can commit phantom text). Returns True once settled: the
    AXManualAccessibility read-back says the full AX mode is on, or _SETTLE_MAX_S passed.
    No AXEnhancedUserInterface fallback: on Electron it can break window snapping and animations."""
    t = _enabled_pids.get(pid)
    if t is None:
        err = AX.AXUIElementSetAttributeValue(app_el, "AXManualAccessibility", True)
        _enabled_pids[pid] = time.time()
        log.info("enabled AX tree for pid %d (err=%s)", pid, err)
        return False
    if pid in _ready_pids:
        return True
    if bool(attr(app_el, "AXManualAccessibility")) or time.time() - t >= _SETTLE_MAX_S:
        _ready_pids.add(pid)
        return True
    return False


# t7 (Nov 15, 03:56:31.121): the Run ▷ lookup that switched VS Code's tree on found nothing 2 ms later, and the miss was
# kept for 6 s ("no Python extension?"); the ▷ was on screen. Chromium fills the tree in over the next seconds, so a
# lookup that finds nothing then says "settling" (the reader keeps that miss only for a moment and looks again).
_FILL_S = 8.0       # after AXManualAccessibility goes on, the tree may still be filling in this long
_SPARSE_NODES = 40  # a walk of a VS Code window that saw fewer nodes than this saw a tree that isn't filled in yet
_misses: dict[str, str] = {}  # lookup key ("run_button", "ui:<key>") -> why its last lookup found nothing


def settling(pid: int) -> bool:
    """Is `pid`'s AX tree still being switched on or filled in (enabled by this process in the last _FILL_S)?"""
    t = _enabled_pids.get(pid)
    return t is None or pid not in _ready_pids or time.time() - t < _FILL_S


def _missed(key: str, pid: int | None, seen: int | None) -> None:
    """Note why `key`'s lookup found nothing: "settling" (the tree is being switched on / filled in, or the walk saw
    an almost empty tree) or "absent" (VS Code isn't running, or its filled-in tree has no such element)."""
    filling = pid is not None and (settling(pid) or (seen is not None and seen < _SPARSE_NODES))
    _misses[key] = "settling" if filling else "absent"


def last_miss(key: str = "run_button") -> str | None:
    """Why the last lookup of `key` found nothing ("settling" / "absent"); None after it found it."""
    return _misses.get(key)


def _page_start(text: str, document: str | None) -> int:
    """1-based file line where VS Code's 500-line AX page starts. Small files: 1. Big files: match the
    page's first lines against the file on disk (pages are aligned to multiples of 500)."""
    if not document or not os.path.isfile(document):
        return 1
    try:
        with open(document, encoding="utf-8", errors="replace") as f:
            file_lines = f.read().split("\n")
    except OSError:
        return 1
    if len(file_lines) <= VSCODE_PAGE:
        return 1
    head = text.split("\n")[:3]
    for start in range(0, len(file_lines), VSCODE_PAGE):
        if file_lines[start:start + len(head)] == head:
            return start + 1
    for i in range(len(file_lines) - len(head) + 1):  # unsaved edits shifted things: any match
        if file_lines[i:i + len(head)] == head:
            return i + 1
    return 1


def read_editor(focused, document: str | None) -> EditorState | None:
    role = _s(attr(focused, "AXRole"))
    if role not in ("AXTextArea", "AXTextField"):
        return None
    text = attr(focused, "AXValue")
    if not text:  # "" = accessibilitySupport "off" (Monaco/xterm empty their AX text): no line or caret to trust
        return None
    text = str(text)
    sel = selected_range(focused) or (0, 0)
    caret = max(0, min(sel[0], len(text)))
    start = _page_start(text, document)
    caret_line = start + text[:caret].count("\n")
    r = rect_of(focused)
    line_rect, h = None, None
    if r is not None and r.h > 2 and r.w > 2:   # parked at the top-left with height 1 = caret off-screen
        line_rect, h = r, r.h
    return EditorState(text=text, page_start_line=start, caret=caret, selection_len=sel[1],
                       caret_line=caret_line, line_rect=line_rect, line_height=h)


def element_info(el, app: str | None = None) -> Element | None:
    if el is None:
        return None
    return Element(role=_s(attr(el, "AXRole")), subrole=_s(attr(el, "AXSubrole")), title=_s(attr(el, "AXTitle")),
                   value=_s(attr(el, "AXValue")), description=_s(attr(el, "AXDescription")),
                   rect=rect_of(el), app=app)


def element_at(x: float, y: float) -> Element | None:
    sysw = AX.AXUIElementCreateSystemWide()
    AX.AXUIElementSetMessagingTimeout(sysw, MESSAGING_TIMEOUT)
    err, el = AX.AXUIElementCopyElementAtPosition(sysw, x, y, None)
    if err != 0:
        return None
    app = None
    e2, pid = AX.AXUIElementGetPid(el, None)
    if e2 == 0:
        ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        app = str(ra.localizedName()) if ra else None
    return element_info(el, app)


def _find_terminal_area(root, depth: int = 0, budget: list | None = None):
    """Find the Terminal.app / iTerm2 text area under `root` (shallow, bounded walk)."""
    budget = budget if budget is not None else [150]
    if root is None or depth > 8 or budget[0] <= 0:
        return None
    budget[0] -= 1
    if _s(attr(root, "AXRole")) == "AXTextArea":
        return root
    for ch in attr(root, "AXChildren") or []:
        hit = _find_terminal_area(ch, depth + 1, budget)
        if hit is not None:
            return hit
    return None


def _xterm_rows(focused, max_up: int = 6) -> list[str]:
    """VS Code integrated terminal: xterm.js exposes each visible row as a list item near the focused
    helper textarea. Walk up a few levels and collect the row texts (bounded)."""
    el = focused
    for _ in range(max_up):
        el = attr(el, "AXParent")
        if el is None:
            return []
        for ch in attr(el, "AXChildren") or []:
            if _s(attr(ch, "AXRole")) == "AXList":
                rows = []
                for row in (attr(ch, "AXChildren") or [])[:400]:
                    t = attr(row, "AXValue") or attr(row, "AXTitle") or attr(row, "AXDescription")
                    if t is None:
                        kids = attr(row, "AXChildren") or []
                        t = " ".join(str(attr(k, "AXValue") or "") for k in kids[:4]).strip() or None
                    if t is not None:
                        rows.append(str(t))
                if rows:
                    return rows
    return []


def menu_bar_item(title: str) -> Element | None:
    """The frontmost app's menu-bar item called `title` ("Terminal"): AXMenuBar > AXMenuBarItem."""
    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is None:
        return None
    app_el = AX.AXUIElementCreateApplication(int(front.processIdentifier()))
    AX.AXUIElementSetMessagingTimeout(app_el, MESSAGING_TIMEOUT)
    for item in attr(attr(app_el, "AXMenuBar"), "AXChildren") or []:
        if _s(attr(item, "AXTitle")) == title:
            return element_info(item, str(front.localizedName() or ""))
    return None


def find_button(pattern, max_nodes: int = 1500) -> Element | None:
    """First AXButton in the frontmost app's focused window whose title/description/help matches
    `pattern` (compiled regex), e.g. VS Code's editor-title "Run Python File". Bounded BFS."""
    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is None:
        return None
    pid = int(front.processIdentifier())
    app_el = AX.AXUIElementCreateApplication(pid)
    AX.AXUIElementSetMessagingTimeout(app_el, MESSAGING_TIMEOUT)
    if str(front.bundleIdentifier() or "") in ELECTRON_EDITORS and not enable_electron_ax(app_el, pid):
        return None
    queue, seen = [attr(app_el, "AXFocusedWindow")], 0
    while queue and seen < max_nodes:
        el = queue.pop(0)
        if el is None:
            continue
        seen += 1
        if _s(attr(el, "AXRole")) == "AXButton":
            for a in ("AXDescription", "AXTitle", "AXHelp"):
                label = _s(attr(el, a))
                if label and pattern.search(label):
                    return element_info(el, str(front.localizedName() or ""))
        queue.extend(attr(el, "AXChildren") or [])
    return None


# VS Code's editor-title Run ▷: the Python extension's "Run Python File" (its dropdown's chevron is "Run or Debug...",
# the activity bar's "Run and Debug": never those), or Code Runner's "Run Code".
RUN_BUTTON_LABEL = re.compile(r"\bRun Python File\b|^Run Code\b", re.IGNORECASE)
_RUN_SKIP_ROLES = {"AXTextArea", "AXTextField", "AXStaticText", "AXOutline", "AXTable", "AXList", "AXRow", "AXImage",
                   "AXMenu", "AXScrollBar"}  # an editor's text, the Explorer tree, terminal rows: no buttons inside
_run_cache: dict = {}  # {"pid", "el"}: the button found last time, re-checked (rect + label) instead of a new walk
_VSCODE_BUNDLES = ("com.microsoft.VSCode", "com.microsoft.VSCodeInsiders", "com.visualstudio.code.oss", "com.vscodium")


def _alive(app) -> bool:
    """Is this NSRunningApplication's process still running (a signal-0 probe)? NSWorkspace.frontmostApplication is
    frozen in the engine (no AppKit run loop, see macos.frontmost_app): t11 08:42, the engine had started while VS Code
    pid 62432 was in front, VS Code was quit and reopened (pid 3452), and every Run ▷ lookup still asked the dead 62432
    (no window: "isn't found (yet)", the terminal box for the whole step)."""
    try:
        pid = int(app.processIdentifier())
    except Exception:  # noqa: BLE001
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:  # EPERM: it runs (another user's process)
        return True
    return True


def _code_app(folder: str | None = None):
    """(pid, window) of VS Code's window for `folder` (its AXDocument inside it), else VS Code's focused window. The
    frontmost app when it is VS Code, else the running one: the learner may be on Miyagi's drawer. VS Code only, and
    only a VS Code that still runs (t11: the stale front app was a VS Code quit minutes before).
    (None, None) without VS Code; (pid, None) while its AX tree is being switched on (t7: settling)."""
    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    apps = [front] if (front is not None and str(front.bundleIdentifier() or "") in _VSCODE_BUNDLES
                       and _alive(front)) else []
    if not apps:
        for b in _VSCODE_BUNDLES:
            apps = [a for a in NSRunningApplication.runningApplicationsWithBundleIdentifier_(b) or [] if _alive(a)]
            if apps:
                break
    if not apps:
        return None, None
    pid = int(apps[0].processIdentifier())
    app_el = AX.AXUIElementCreateApplication(pid)
    AX.AXUIElementSetMessagingTimeout(app_el, MESSAGING_TIMEOUT)
    if not enable_electron_ax(app_el, pid):
        return pid, None
    if folder:
        from urllib.parse import unquote
        root = os.path.realpath(os.path.expanduser(str(folder)))
        for win in attr(app_el, "AXWindows") or []:
            doc = attr(win, "AXDocument")
            path = os.path.realpath(unquote(str(doc).removeprefix("file://"))) if doc is not None else ""
            if path == root or path.startswith(root + os.sep):
                return pid, win
    return pid, attr(app_el, "AXFocusedWindow") or attr(app_el, "AXMainWindow")


def _run_label(el) -> str | None:
    for a in ("AXDescription", "AXTitle", "AXHelp"):
        label = _s(attr(el, a))
        if label and RUN_BUTTON_LABEL.search(label) and "debug" not in label.lower():
            return label
    return None


def find_run_button(folder: str | None = None, max_nodes: int = 2500) -> Element | None:
    """VS Code's editor-title Run ▷ ("Run Python File") in the lesson's window (`folder`), even while another app
    (Miyagi's drawer) is in front. Bounded BFS that skips text areas, trees and lists; the element found is kept
    and only re-checked next time (its rect and label: 3 AX reads instead of a walk). None without one (last_miss
    says whether VS Code's tree was still filling in)."""
    pid, win = _code_app(folder)
    if win is None:
        _missed("run_button", pid, None)
        return None
    el = _run_cache.get("el") if _run_cache.get("pid") == pid else None
    if el is not None and _run_label(el) and (r := rect_of(el)) is not None and r.w > 2 and r.h > 2:
        _misses.pop("run_button", None)
        return Element(role="AXButton", subrole=None, title=None, value=None, description=_run_label(el), rect=r,
                       app="Code")
    _run_cache.clear()
    queue, seen = [win], 0
    while queue and seen < max_nodes:
        el = queue.pop(0)
        if el is None:
            continue
        seen += 1
        role = _s(attr(el, "AXRole"))
        if role == "AXButton":
            if _run_label(el) and (r := rect_of(el)) is not None and r.w > 2 and r.h > 2:
                _run_cache.update(pid=pid, el=el)
                _misses.pop("run_button", None)
                return element_info(el, "Code")
            continue
        if role in _RUN_SKIP_ROLES:
            continue
        queue.extend(attr(el, "AXChildren") or [])
    _missed("run_button", pid, seen)
    return None



# Michael (desktop test 6) on the Run ▷ box: "it really actually selects it, actually finds it". The other VS Code
# controls a learner must click, found the same way (the lesson's window only, VS Code only, a bounded BFS; the element
# found is kept and re-checked next time: its rect and label, 3 AX reads instead of a walk):
# - "terminal_tab": the panel's "Terminal" tab (the panel is open on Problems / Output)
# - "toggle_panel": the title bar's layout control "Toggle Panel (⌘J)" (the panel is closed)
# - "tab:<name>": the editor tab of <name>; "dirty:<name>": its close button, where VS Code draws the unsaved dot
# - "explorer:<name>": <name>'s row in the Explorer tree
# - "problems": the status bar's errors / warnings item (else the panel's "Problems" tab)
# - "interpreter": the Python extension's notification button "Select Interpreter" (never the status bar's item)
_TAB_ROLES = {"AXRadioButton", "AXTab", "AXButton"}  # role="tab" is AXRadioButton (subrole AXTabButton) in Chromium
_UI_SKIP = {"AXTextArea", "AXTextField", "AXStaticText", "AXImage", "AXMenu", "AXScrollBar"}
_UI_TERMINAL = re.compile(r"^Terminal(?:\s*\([^)]*\))?$", re.IGNORECASE)
_UI_TOGGLE_PANEL = re.compile(r"^Toggle Panel\b", re.IGNORECASE)
_UI_PROBLEMS = re.compile(r"\bErrors?:\s*\d+|\b\d+\s+errors?\b|^Problems\b", re.IGNORECASE)
_UI_INTERPRETER = re.compile(r"^Select (?:a )?(?:Python )?Interpreter$", re.IGNORECASE)
_UI_NOTE = re.compile(r"interpreter|notification", re.IGNORECASE)  # the toast around the button says so
_UI_CLOSE = re.compile(r"^Close\b", re.IGNORECASE)
_ui_cache: dict = {}  # {key: {"pid", "el"}}


def _labels(el) -> list[str]:
    return [lb for a in ("AXDescription", "AXTitle", "AXHelp") if (lb := _s(attr(el, a)))]


def _name_rx(name: str) -> re.Pattern:
    """A tab / tree row of file `name`: "nn.py", "nn.py, preview", "● nn.py", never "nn.py.bak" / "my_nn.py"."""
    return re.compile(r"^[●•\s]*" + re.escape(name) + r"(?:$|[\s,(•●])", re.IGNORECASE)


def _in_notification(el, up: int = 8) -> bool:
    """`el` sits in a notification toast (an ancestor labelled "... interpreter ..." / "..., notification" or a dialog),
    not in the status bar."""
    for _ in range(up):
        el = attr(el, "AXParent")
        if el is None:
            return False
        if _s(attr(el, "AXSubrole")) in ("AXApplicationDialog", "AXDialog", "AXApplicationAlert"):
            return True
        if any(_UI_NOTE.search(lb) for lb in _labels(el)):
            return True
    return False


def _ui_spec(key: str):
    """key -> (roles, label test(el, labels) -> bool, roles not descended into, the child to return: None = itself)."""
    kind, _, name = key.partition(":")
    run_skip = _RUN_SKIP_ROLES
    if kind == "terminal_tab":
        return {"AXRadioButton", "AXTab", "AXButton", "AXCheckBox"}, \
            lambda el, lbs: any(_UI_TERMINAL.search(lb) for lb in lbs), run_skip, None
    if kind == "toggle_panel":
        return {"AXButton", "AXCheckBox"}, lambda el, lbs: any(_UI_TOGGLE_PANEL.search(lb) for lb in lbs), run_skip, None
    if kind in ("tab", "dirty") and name:
        rx = _name_rx(name)
        return _TAB_ROLES, lambda el, lbs: any(rx.search(lb) for lb in lbs), run_skip, ("close" if kind == "dirty" else None)
    if kind == "explorer" and name:
        rx = _name_rx(name)
        return {"AXRow"}, lambda el, lbs: any(rx.search(lb) for lb in lbs) or any(
            rx.search(str(attr(k, "AXValue") or attr(k, "AXTitle") or "")) for k in (attr(el, "AXChildren") or [])[:4]
        ), _UI_SKIP | {"AXList", "AXTable"}, None
    if kind == "problems":
        return {"AXButton", "AXRadioButton", "AXTab"}, lambda el, lbs: any(_UI_PROBLEMS.search(lb) for lb in lbs), \
            run_skip, None
    if kind == "interpreter":
        return {"AXButton", "AXLink"}, lambda el, lbs: any(_UI_INTERPRETER.search(lb) for lb in lbs) and \
            _in_notification(el), _UI_SKIP | {"AXOutline", "AXTable"}, None
    return None


def _close_button(tab):
    """The close button inside an editor tab (where VS Code draws the unsaved ●), else None."""
    for ch in attr(tab, "AXChildren") or []:
        for el in [ch, *(attr(ch, "AXChildren") or [])]:
            if _s(attr(el, "AXRole")) in ("AXButton", "AXLink") and any(_UI_CLOSE.search(lb) for lb in _labels(el)):
                return el
    return None


def _ui_hit(el, test, roles, child) -> Element | None:
    if el is None or _s(attr(el, "AXRole")) not in roles:
        return None
    lbs = _labels(el)
    if not test(el, lbs):
        return None
    if child == "close" and (btn := _close_button(el)) is not None:
        r = rect_of(btn)
        if r is not None and r.w > 2 and r.h > 2:
            return Element(role="AXButton", subrole=None, title=None, value=None, description=lbs[0] if lbs else None,
                           rect=r, app="Code")
    r = rect_of(el)
    if r is None or r.w <= 2 or r.h <= 2:
        return None
    return Element(role=_s(attr(el, "AXRole")), subrole=_s(attr(el, "AXSubrole")), title=None, value=None,
                   description=lbs[0] if lbs else None, rect=r, app="Code")


def find_ui(key: str, folder: str | None = None, max_nodes: int = 2500) -> Element | None:
    """One of VS Code's own controls (`key`: see above) in the lesson's window (`folder`), even while Miyagi's drawer
    is in front, as find_run_button finds the Run ▷. None when it isn't there (or an unknown key)."""
    spec = _ui_spec(key)
    if spec is None:
        return None
    roles, test, skip, child = spec
    pid, win = _code_app(folder)
    if win is None:
        _missed(f"ui:{key}", pid, None)
        return None
    cached = _ui_cache.get(key)
    if cached is not None and cached.get("pid") == pid and (hit := _ui_hit(cached["el"], test, roles, child)) is not None:
        _misses.pop(f"ui:{key}", None)
        return hit
    _ui_cache.pop(key, None)
    queue, seen = [win], 0
    while queue and seen < max_nodes:
        el = queue.pop(0)
        if el is None:
            continue
        seen += 1
        role = _s(attr(el, "AXRole"))
        if role in roles and (hit := _ui_hit(el, test, roles, child)) is not None:
            _ui_cache[key] = {"pid": pid, "el": el}
            _misses.pop(f"ui:{key}", None)
            return hit
        if role in skip:
            continue
        queue.extend(attr(el, "AXChildren") or [])
    _missed(f"ui:{key}", pid, seen)
    return None


# t9: VS Code's quick-pick (the input box at the top centre: the command palette, the kernel picker, "Select Interpreter")
# opens under Miyagi's overlay; the engine reports where it is (screen.avoid) so the app moves its card and step pill off
# it. While it is open VS Code keeps focus in its input (role combobox: AXComboBox); its list is a listbox labelled
# "Quick Input" (AXList); the widget's div has class "quick-input-widget" (Chromium's AXDOMClassList). Found from the
# focused element UP (a dozen AX reads: cheap enough for the 0.5 s poll), never by a walk of the whole tree.
_QP_INPUT_ROLES = {"AXComboBox", "AXTextField", "AXSearchField"}
_QP_HINT = re.compile(r"quick[\s_-]?(?:input|pick|open)", re.IGNORECASE)
_QP_TOP = 0.4      # the widget's top edge is in the window's top 40%
_QP_CENTRE = 0.12  # its centre is within 12% of the window's width of the window's centre
_QP_MAX_W = 0.9    # and it is narrower than 90% of the window (the workbench around it is not it)


def _qp_hint(el, get) -> bool:
    """`el` says it is (part of) the quick input: its label / id / DOM class."""
    labels = [str(v) for a in ("AXDescription", "AXTitle", "AXHelp", "AXIdentifier", "AXDOMIdentifier")
              if (v := get(el, a))]
    labels += [str(c) for c in (get(el, "AXDOMClassList") or [])]
    return any(_QP_HINT.search(lb) for lb in labels)


def _qp_placed(r: Rect | None, win: Rect | None) -> bool:
    """Where the quick-pick sits: top 40% of its window, horizontally centred, not the full width."""
    if r is None or r.w < 120 or r.h < 12:
        return False
    if win is None or win.w <= 0 or win.h <= 0:
        return True
    return (win.y - 2 <= r.y <= win.y + _QP_TOP * win.h and r.w <= _QP_MAX_W * win.w
            and abs((r.x + r.w / 2) - (win.x + win.w / 2)) <= _QP_CENTRE * win.w)


def _inside(outer: Rect, inner: Rect) -> bool:
    return (outer.x - 1 <= inner.x and outer.y - 1 <= inner.y and inner.x + inner.w <= outer.x + outer.w + 1
            and inner.y + inner.h <= outer.y + outer.h + 1)


def quickpick_in(win, focused, get=None, rect=None) -> Rect | None:
    """The open quick-pick's rect (the whole widget: input + list), from `focused` (the app's focused element: the
    picker's input while it is open) up its parents; None when the focus is anywhere else. `win`: the window it is in.
    `get(el, attr)` / `rect(el)` default to the real AX reads (tests pass a fake tree)."""
    get, rect = get or attr, rect or rect_of
    if focused is None or _s(get(focused, "AXRole")) not in _QP_INPUT_ROLES:
        return None
    wr = rect(win) if win is not None else None
    ir = rect(focused)
    if not _qp_placed(ir, wr):
        return None
    hinted = _s(get(focused, "AXRole")) == "AXComboBox" or _qp_hint(focused, get)
    box, el = ir, focused
    for _ in range(8):  # input -> filter -> header -> quick-input-widget -> workbench (too wide: stop)
        el = get(el, "AXParent")
        r = rect(el) if el is not None else None
        if r is None or not _qp_placed(r, wr) or not _inside(r, ir):
            break
        box = r
        hinted = hinted or _qp_hint(el, get) or any(
            _s(get(k, "AXRole")) == "AXList" and _qp_hint(k, get) for k in (get(el, "AXChildren") or [])[:8])
    return box if hinted else None


def find_quickpick(folder: str | None = None) -> Element | None:
    """VS Code's open quick-pick (see quickpick_in) in the lesson's VS Code (`folder`), also while Miyagi's drawer is in
    front. None when it is closed or VS Code isn't running."""
    pid, win = _code_app(folder)
    if win is None:
        return None
    app_el = AX.AXUIElementCreateApplication(pid)
    AX.AXUIElementSetMessagingTimeout(app_el, MESSAGING_TIMEOUT)
    focused = attr(app_el, "AXFocusedUIElement")
    r = quickpick_in(attr(focused, "AXWindow") or win, focused)
    return Element(role="AXGroup", subrole=None, title=None, value=None, description="quickpick", rect=r,
                   app="Code") if r is not None else None


def snapshot() -> AXSnapshot | None:
    """One read of the frontmost app + the element under the mouse. ~5-30 ms."""
    t0 = time.perf_counter()
    ws = NSWorkspace.sharedWorkspace()
    front = ws.frontmostApplication()
    if front is None:
        return None
    pid = int(front.processIdentifier())
    bundle = str(front.bundleIdentifier() or "") or None
    snap = AXSnapshot(t=time.time(), app=str(front.localizedName() or ""), bundle_id=bundle, pid=pid)
    snap.mouse = mouse_location()
    app_el = AX.AXUIElementCreateApplication(pid)
    AX.AXUIElementSetMessagingTimeout(app_el, MESSAGING_TIMEOUT)
    ready = True
    if bundle in ELECTRON_EDITORS:
        ready = enable_electron_ax(app_el, pid)
    win = attr(app_el, "AXFocusedWindow")
    snap.window_title = _s(attr(win, "AXTitle"), 500)
    doc = attr(win, "AXDocument")
    if doc is not None:
        doc = str(doc)
        snap.document = doc.removeprefix("file://")
        from urllib.parse import unquote
        snap.document = unquote(snap.document)
    if snap.window_title is not None:
        snap.dirty = snap.window_title.lstrip().startswith("●")
    if ready:
        focused = attr(app_el, "AXFocusedUIElement")
        snap.focused_role = _s(attr(focused, "AXRole"))
        if bundle in TERMINALS:
            area = focused if snap.focused_role == "AXTextArea" else _find_terminal_area(win)
            val = attr(area, "AXValue")
            if val is not None:
                snap.terminal_lines = str(val).rstrip("\n").split("\n")[-TERMINAL_TAIL:]
                snap.terminal_rect = rect_of(area)
        else:
            snap.editor = read_editor(focused, snap.document)
            if snap.focused_role in ("AXTextArea", "AXTextField") and bundle in ELECTRON_EDITORS and \
                    _s(attr(focused, "AXRoleDescription")) not in (None, "editor"):
                # the focused textarea is xterm's helper, not Monaco: read terminal rows instead. Gate on the role,
                # not on snap.editor: xterm empties the helper on Enter/Ctrl-C/blur, so read_editor gave None there
                rows = _xterm_rows(focused)
                if rows:
                    snap.editor, snap.terminal_lines = None, rows
    snap.under_mouse = element_at(*snap.mouse)
    snap.read_ms = (time.perf_counter() - t0) * 1000
    return snap


# ---------------------------------------------------------------------- worker

class AXReader:
    """Serial 10 Hz worker. `latest()` is the newest snapshot; `on_change(cb)` fires cb(snap, what)
    with what in {"app", "document", "text", "caret", "dirty", "terminal"} when those change, and
    "typing_pause" once the editor text has been stable for `pause_s` after a change."""

    def __init__(self, hz: float = 10.0, pause_s: float = 1.0):
        self.period = 1.0 / hz
        self.pause_s = pause_s
        self._latest: AXSnapshot | None = None
        self._cbs: list[Callable[[AXSnapshot, str], object]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.available = False
        self.last_error: str | None = None
        self._last_text_change = 0.0
        self._pause_fired = True

    def start(self) -> AXReader:
        self.available = trusted()
        if not self.available:
            self.last_error = AX_HELP
            log.warning(AX_HELP)
            return self
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ax-reader", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def latest(self) -> AXSnapshot | None:
        return self._latest

    def on_change(self, cb: Callable[[AXSnapshot, str], object]) -> None:
        self._cbs.append(cb)

    def _emit(self, snap: AXSnapshot, what: str) -> None:
        for cb in list(self._cbs):
            try:
                cb(snap, what)
            except Exception:
                log.exception("ax on_change callback failed")

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.time()
            try:
                snap = snapshot()
                if snap is not None:
                    self._diff(self._latest, snap)
                    self._latest = snap
                    self.last_error = None
            except Exception as e:  # noqa: BLE001
                self.last_error = f"{e.__class__.__name__}: {e}"
                log.debug("ax snapshot failed: %s", e)
            self._stop.wait(max(0.01, self.period - (time.time() - t0)))

    def _diff(self, old: AXSnapshot | None, new: AXSnapshot) -> None:
        now = time.time()
        if old is None or old.pid != new.pid:
            self._emit(new, "app")
            return
        if old.document != new.document:
            self._emit(new, "document")
        if old.dirty != new.dirty:
            self._emit(new, "dirty")
        ot, nt = (old.editor.text if old.editor else None), (new.editor.text if new.editor else None)
        if ot != nt and nt is not None:
            self._last_text_change, self._pause_fired = now, False
            self._emit(new, "text")
        elif old.editor and new.editor and old.editor.caret != new.editor.caret:
            self._emit(new, "caret")
        if old.terminal_lines[-3:] != new.terminal_lines[-3:]:
            self._emit(new, "terminal")
        if not self._pause_fired and now - self._last_text_change >= self.pause_s:
            self._pause_fired = True
            self._emit(new, "typing_pause")
