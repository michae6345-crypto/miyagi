"""Stable screen regions of VS Code for lesson-mode spotlights: "terminal", "editor", "explorer",
"run_button". Pure Python (no pyobjc) except the run button, which only AX can see.

    find_region(obs, "terminal")  -> Region | None     (one frame, raw)
    RegionStabilizer().update(key, rect, frame)          (4 pt grid, keeps the last rect if it moved < 12 pt)
    ScreenReader.locate_region("terminal") -> Rect | None (live, stabilized)

How each is found (OCR of the frontmost VS Code window):
- terminal: the panel tab header row ("PROBLEMS  OUTPUT  DEBUG CONSOLE  TERMINAL  PORTS") down to the
  status bar; if the header isn't readable, from the top-most shell prompt below the editor. None
  when neither is on screen (panel closed). Terminal.app/iTerm2 only when asked for (`app="Terminal"`).
- editor: below the tab bar + breadcrumb, from the editor's left edge (tab row / line-number gutter)
  to the window's right edge, down to the panel (or the status bar).
- explorer: the side bar under its "EXPLORER" header (or OUTLINE / TIMELINE / OPEN EDITORS sections),
  from its left edge to the editor's left edge.
- run_button: the editor-title "Run" action via the AX tree (see reader.locate_region); no OCR.

All rects: screen points, top-left origin of the primary display (same space as locate()).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import lines as L
from . import match as M
from .types import Block, Rect, ScreenObservation, Window

REGIONS = ("terminal", "editor", "explorer", "run_button")
ALIASES = {"panel": "terminal", "integrated_terminal": "terminal", "sidebar": "explorer", "side_bar": "explorer",
           "files": "explorer", "code": "editor", "run": "run_button", "run button": "run_button"}

STATUS_BAR = 22.0
_PANEL_TABS = ("PROBLEMS", "OUTPUT", "DEBUG CONSOLE", "TERMINAL", "PORTS", "GITLENS", "COMMENTS")
_SIDEBAR_MARKERS = re.compile(r"^(?:[›>v]\s*)?(EXPLORER|Explorer|OUTLINE|Outline|TIMELINE|Timeline|OPEN EDITORS"
                              r"|Open Editors)\b")
_PROMPT = re.compile(r"^\S*@\S+.*?[%$#❯➜]\s|(?:^|\s)[%$❯➜]\s+\S|^\(\S+\)\s.*[%$#]\s|^PS [A-Z]:\\")


@dataclass
class Region:
    name: str
    rect: Rect
    app: str | None
    source: str          # how it was found: "panel_header" | "prompt" | "gutter" | "sidebar_header" | "ax" | ...

    def to_dict(self) -> dict:
        return {"name": self.name, "rect": self.rect.to_dict(), "app": self.app, "source": self.source}


def canonical(name: str) -> str:
    n = name.strip().lower().replace("-", "_")
    return ALIASES.get(n, n)


# ---------------------------------------------------------------------- one frame

@dataclass
class _Layout:
    win: Window
    blocks: list[Block]
    rows: list[M.Line]
    pane: L.EditorPane | None
    panes: list[L.EditorPane]
    editor_left: float | None
    chrome_bottom: float | None      # bottom of the tab bar + breadcrumb row(s)

    @property
    def status_top(self) -> float:
        return self.win.rect.y2 - STATUS_BAR


def _editor_window(obs: ScreenObservation, app: str | None) -> Window | None:
    for w in obs.windows:  # front to back
        wanted = M.app_matches(app, w.app, w.title) if app else any(M.app_matches(e, w.app) for e in L.EDITOR_APPS)
        if wanted and any(b.app == w.app and b.window == w.title for b in obs.blocks):
            return w
    return None


def _layout(obs: ScreenObservation, app: str | None) -> _Layout | None:
    win = _editor_window(obs, app)
    if win is None:
        return None
    blocks = [b for b in obs.blocks if b.app == win.app and b.window == win.title]
    rows = M.group_lines(blocks)
    panes = [p for p in L.find_panes(obs, win.app) if p.window == win.title]
    pane = min(panes, key=lambda p: p.gutter_x) if panes else None   # left-most editor group
    editor_left = chrome_bottom = None
    if pane is not None:
        top = pane.rect.y
        # tab bar / breadcrumb rows: text right above the first code row that starts just left of the
        # gutter (banners such as "Restricted Mode ..." span the whole window and are ignored)
        chrome = [ln for ln in rows if ln.rect.y2 <= top + 2 and ln.rect.y >= win.rect.y
                  and pane.gutter_x - 80 <= ln.rect.x <= pane.gutter_x + 4
                  and top - ln.rect.y2 < 4 * pane.line_height]
        if chrome:
            chrome_bottom = max(ln.rect.y2 for ln in chrome)
            editor_left = min(ln.rect.x for ln in chrome) - 12
        else:
            editor_left = pane.gutter_x - 20
        editor_left = max(win.rect.x, editor_left)
    return _Layout(win, blocks, rows, pane, panes, editor_left, chrome_bottom)


def _panel_header(lay: _Layout) -> M.Line | None:
    """The panel's tab-header row: has TERMINAL (upper case) and usually other panel tab names."""
    below = lay.pane.rect.y2 - 4 if lay.pane else lay.win.rect.y + lay.win.rect.h * 0.3
    best = None
    for ln in lay.rows:
        if ln.rect.y < below or "›" in ln.text:
            continue
        # Vision may split the row ("PROBLEMS" | "OUTPUT DEBUG CONSOLE TERMINAL PORTS"): join the row
        row = " ".join(x.text for x in lay.rows if abs(x.rect.cy - ln.rect.cy) < 0.5 * ln.rect.h)
        if not re.search(r"\bTERMINAL\b", row):
            continue
        others = sum(1 for t in _PANEL_TABS if t != "TERMINAL" and t in row)
        if (others >= 1 or len(row.split()) <= 3) and (best is None or ln.rect.y < best.rect.y):
            best = ln
    return best


def _prompt_line(lay: _Layout) -> M.Line | None:
    if lay.pane is not None:
        below = lay.pane.rect.y2 + 2
        cands = [ln for ln in lay.rows if ln.rect.y >= below and _PROMPT.search(ln.text)]
    else:   # no editor gutter: only unmistakable `user@host ... %` prompts in the lower half
        cands = [ln for ln in lay.rows if ln.rect.cy > lay.win.rect.cy and re.match(r"^\S*@\S+.*?[%$#]\s", ln.text)]
    cands = [ln for ln in cands if ln.rect.y2 <= lay.status_top + 2]
    return min(cands, key=lambda ln: ln.rect.y) if cands else None


def _terminal(lay: _Layout) -> Region | None:
    anchor = _panel_header(lay)
    if anchor is not None:
        top, src = anchor.rect.y - 8, "panel_header"
    else:
        anchor = _prompt_line(lay)
        if anchor is None:
            return None
        top, src = anchor.rect.y - 6, "prompt"
    left = lay.editor_left if lay.editor_left is not None else anchor.rect.x - 12
    left = max(lay.win.rect.x, min(left, anchor.rect.x - 4))
    right = max(p.right_edge for p in lay.panes) if lay.panes else lay.win.rect.x2   # panel = editor width
    r = Rect(left, top, right - left, lay.status_top - top)
    return Region("terminal", r, lay.win.app, src) if r.h > 20 else None


def _editor(lay: _Layout) -> Region | None:
    if lay.pane is None:
        return None
    pane = lay.pane
    # below the tab bar + breadcrumb (an unread breadcrumb: line 1's row top is the editor's top)
    top = max(lay.chrome_bottom + 4, pane.rect.y - 3) if lay.chrome_bottom is not None else pane.rect.y - 4
    term = _terminal(lay)
    bottom = term.rect.y - 2 if term is not None else lay.status_top
    bottom = max(bottom, pane.rect.y2) if term is None else bottom
    left = lay.editor_left if lay.editor_left is not None else pane.gutter_x - 20
    right = max(p.right_edge for p in lay.panes) if lay.panes else lay.win.rect.x2
    return Region("editor", Rect(left, top, right - left, bottom - top), lay.win.app, "gutter")


def _explorer(lay: _Layout) -> Region | None:
    limit = lay.editor_left if lay.editor_left is not None else lay.win.rect.x + lay.win.rect.w * 0.4
    marks = [b for b in lay.blocks if b.rect.x2 < limit + 4 and _SIDEBAR_MARKERS.match(b.text.strip())]
    if not marks:
        return None
    hdr = next((b for b in sorted(marks, key=lambda b: b.rect.y) if b.text.strip().lower().startswith(
        ("explorer", "› explorer", "v explorer"))), None)
    left = max(lay.win.rect.x, min(b.rect.x for b in marks) - 16)
    top = (hdr.rect.y - 10) if hdr is not None else min(b.rect.y for b in marks) - 10
    top = max(lay.win.rect.y, top)
    if limit - left < 60:
        return None
    return Region("explorer", Rect(left, top, limit - 1 - left, lay.status_top - top), lay.win.app,
                  "sidebar_header" if hdr is not None else "sidebar_sections")


def find_region(obs: ScreenObservation, name: str, app: str | None = None) -> Region | None:
    """One frame, no smoothing. `app` restricts to that app's window (default: front-most VS Code /
    Cursor window). `terminal` with app="Terminal" (or iTerm2 ...) is that app's window content."""
    name = canonical(name)
    if name not in REGIONS:
        raise ValueError(f"unknown region {name!r} (one of {', '.join(REGIONS)})")
    if name == "terminal" and app and M.is_terminal_app(app):
        w = next((w for w in obs.windows if M.app_matches(app, w.app)), None)
        if w is None:
            return None
        return Region("terminal", Rect(w.rect.x, w.rect.y + 28, w.rect.w, w.rect.h - 28), w.app, "window")
    if name == "run_button":
        return None    # icon only: AX (reader.locate_region) or nothing
    lay = _layout(obs, app)
    if lay is None:
        return None
    reg = {"terminal": _terminal, "editor": _editor, "explorer": _explorer}[name](lay)
    if reg is not None and obs.screen.w:
        reg.rect = reg.rect.clamp(obs.screen)
    return reg


# ---------------------------------------------------------------------- stability

def snap(r: Rect, grid: float = 4.0) -> Rect:
    """Round the edges to a `grid`-point lattice (edges, not x/w, so the size doesn't wobble)."""
    x1, y1 = round(r.x / grid) * grid, round(r.y / grid) * grid
    x2, y2 = round(r.x2 / grid) * grid, round(r.y2 / grid) * grid
    return Rect(x1, y1, x2 - x1, y2 - y1)


class RegionStabilizer:
    """Frame-to-frame smoothing per key (e.g. ("terminal", app)).

    - rects are snapped to a 4-point grid;
    - if every edge moved < `keep` points since the last returned rect, the last rect is returned;
    - a region that disappears for up to `miss_grace` frames keeps its last rect (one bad OCR frame
      doesn't make the spotlight blink); after that it's None.
    Calls with the same `frame` number don't count as extra misses.
    """

    def __init__(self, grid: float = 4.0, keep: float = 12.0, miss_grace: int = 1):
        self.grid, self.keep, self.miss_grace = grid, keep, miss_grace
        self._last: dict = {}     # key -> Rect
        self._miss: dict = {}     # key -> consecutive missing frames
        self._frame: dict = {}    # key -> last frame seen
        self._out: dict = {}      # key -> last output (for same-frame calls)

    def update(self, key, rect: Rect | None, frame: int | None = None) -> Rect | None:
        if frame is not None and self._frame.get(key) == frame and key in self._out:
            return self._out[key]
        self._frame[key] = frame
        last = self._last.get(key)
        if rect is None:
            n = self._miss.get(key, 0) + 1
            self._miss[key] = n
            out = last if (last is not None and n <= self.miss_grace) else None
            if out is None:
                self._last.pop(key, None)
        else:
            self._miss[key] = 0
            r = snap(rect, self.grid)
            if last is not None and max(abs(r.x - last.x), abs(r.y - last.y), abs(r.x2 - last.x2),
                                        abs(r.y2 - last.y2)) < self.keep:
                out = last
            else:
                out = r
                self._last[key] = r
        self._out[key] = out
        return out

    def reset(self) -> None:
        self._last.clear()
        self._miss.clear()
        self._frame.clear()
        self._out.clear()
