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
_SETTLE_S = 1.0


def enable_electron_ax(app_el, pid: int) -> bool:
    """Ask an Electron app (VS Code) to build its AX tree. ONCE per pid: re-setting it every frame
    makes Chromium rebuild the tree (and can commit phantom text). Returns True once settled."""
    t = _enabled_pids.get(pid)
    if t is None:
        err = AX.AXUIElementSetAttributeValue(app_el, "AXManualAccessibility", True)
        if err != 0:
            AX.AXUIElementSetAttributeValue(app_el, "AXEnhancedUserInterface", True)
        _enabled_pids[pid] = time.time()
        log.info("enabled AX tree for pid %d (err=%s)", pid, err)
        return False
    return time.time() - t >= _SETTLE_S


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
    if text is None:
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
            if snap.editor is not None and bundle in ELECTRON_EDITORS and \
                    _s(attr(focused, "AXRoleDescription")) not in (None, "editor"):
                # the focused textarea is xterm's helper, not Monaco: read terminal rows instead
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
