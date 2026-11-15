"""Stable screen regions of VS Code for lesson-mode spotlights: "terminal", "editor", "explorer",
"run_button", "terminal_menu" (any menu-bar item: "menu:<Title>"). Pure Python (no pyobjc) except
the run button, which only AX can see.

    find_region(obs, "terminal")  -> Region | None     (one frame, raw)
    RegionStabilizer().update(key, rect, frame)          (4 pt grid, keeps the last rect if it moved < 12 pt)
    ScreenReader.locate_region("terminal") -> Rect | None (live, stabilized)

How each is found (OCR of the frontmost VS Code window):
- terminal: the panel tab header row ("PROBLEMS  OUTPUT  DEBUG CONSOLE  TERMINAL  PORTS") down to the
  status bar; if the header isn't readable, from the top-most shell prompt below the editor. None
  when neither is on screen (panel closed). Terminal.app/iTerm2 only when asked for (`app="Terminal"`).
- terminal_prompt: the live (last) shell prompt line inside that panel, clamped to the panel's own
  edges (never the status bar or a side bar such as Chat): where a run step's command is typed.
- editor: below the tab bar + breadcrumb, from the editor's left edge (tab row / line-number gutter)
  to the window's right edge, down to the panel (or the status bar).
- explorer: the side bar under its "EXPLORER" header (or OUTLINE / TIMELINE / OPEN EDITORS sections),
  from its left edge to the editor's left edge.
- run_button: the editor-title "Run" action: AX when granted (reader), else the ▷ icon on the tab
  row, which Vision reads as "D" / "D •".
- without readable line numbers (small text), the editor is laid out from the tab row (left edge),
  the breadcrumb (top) and a side bar header such as "Chat" on the tab row (right edge).

All rects: screen points, top-left origin of the primary display (same space as locate()).
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from . import lines as L
from . import match as M
from .types import Block, Rect, ScreenObservation, Window

REGIONS = ("terminal", "editor", "explorer", "run_button", "terminal_menu", "terminal_prompt")
# a tab: "calculator.py", "calculator.py X", "calculator.py ●", "calculator.py 1" (problem count)
_TAB = re.compile(r"^[\w.\-]+\.[A-Za-z0-9]{1,6}(?:\s*[xX×●•]|\s+\d{1,2})?$")
# secondary side bar headers that sit on the editor's tab row (its right edge is the editor's)
_SIDE_TITLES = {"chat", "copilot", "github copilot", "copilot chat", "outline", "timeline", "sessions"}
_RUN_ICON = re.compile(r"^[D▷▶⊳►](?:\s|$)")     # Vision reads the run triangle as "D" (+ "•" for the chevron)
MENU_BAR_H = 40.0          # the macOS menu bar is 24-37 pt (notch Macs: 37)
_MENUS = ("File", "Edit", "Selection", "View", "Go", "Run", "Terminal", "Window", "Help")
ALIASES = {"panel": "terminal", "integrated_terminal": "terminal", "sidebar": "explorer", "side_bar": "explorer",
           "files": "explorer", "code": "editor", "run": "run_button", "run button": "run_button",
           "terminal menu": "terminal_menu", "menu:terminal": "terminal_menu"}


def menu_title(name: str) -> str | None:
    """"terminal_menu" -> "Terminal"; "menu:Run" -> "Run"; anything else -> None."""
    n = canonical(name)
    if n == "terminal_menu":
        return "Terminal"
    if name.lower().startswith("menu:"):
        return name.split(":", 1)[1].strip()
    return None


def find_menu_item(obs: ScreenObservation, title: str, app: str | None = None) -> Region | None:
    """`title` in the macOS menu bar, read by OCR, when it is VS Code's menu bar: the frontmost
    window is VS Code (or `app`) and the strip shows its menus (File / Edit / View / Run / Terminal ...).
    None when the menu bar is hidden (full screen) or belongs to another app. A word inside a merged
    Vision block ("Run Terminal Window") gets its share of the block's width."""
    front = obs.windows[0] if obs.windows else None
    wanted = app or "Code"
    if front is not None and not M.app_matches(wanted, front.app) and not (
            app is None and any(M.app_matches(e, front.app) for e in L.EDITOR_APPS)):
        return None
    if front is None and not M.app_matches(wanted, obs.app):
        return None
    top = obs.screen.y if obs.screen.h else 0.0
    # menu-bar blocks are outside every window, or over a full-screen window when the bar is revealed
    strip = [b for b in obs.blocks if b.rect.y2 <= top + MENU_BAR_H]
    words = " ".join(b.text for b in strip).split()
    if sum(1 for m in _MENUS if m in words) < 3:
        return None
    for b in sorted(strip, key=lambda b: b.rect.x):
        toks = b.text.split()
        if title not in toks:
            continue
        if len(toks) == 1:
            x, w = b.rect.x, b.rect.w
        else:   # proportional share of the merged block
            before = len(" ".join(toks[:toks.index(title)])) + (1 if toks.index(title) else 0)
            cw = b.rect.w / max(1, len(b.text))
            x, w = b.rect.x + before * cw, len(title) * cw
        bar_h = max(24.0, min(MENU_BAR_H - 3, b.rect.y2 + 8 - top))
        return Region(f"menu:{title}", Rect(x - 8, top, w + 16, bar_h), front.app if front else obs.app, "menu_bar_ocr")
    return None

STATUS_BAR = 22.0
_PANEL_TABS = ("PROBLEMS", "OUTPUT", "DEBUG CONSOLE", "TERMINAL", "PORTS", "GITLENS", "COMMENTS")
_SIDEBAR_MARKERS = re.compile(r"^(?:[›>v]\s*)?(EXPLORER|Explorer|OUTLINE|Outline|TIMELINE|Timeline|OPEN EDITORS"
                              r"|Open Editors)\b")
_PROMPT = re.compile(r"^\S*@\S+.*?[%$#❯➜]\s|(?:^|\s)[%$❯➜]\s+\S|^\(\S+\)\s.*[%$#]\s|^PS [A-Z]:\\")
# the live prompt may be empty (nothing typed yet): "tripi@mac calc %" ends the line; VS Code's Python extension
# auto-activates the lesson's .venv, so it is usually "(.venv) tripi@mac calc %"
_PROMPT_END = re.compile(r"^(?:\(\S+\)\s+)?\S*@\S+.*\s[%$#❯➜]\s*$|^\s*(?:\(\S+\)\s*)?(?:\S+\s+)?[%$❯➜]\s*$")


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
    right_edge: float = 0.0          # editor's right edge (window, or a side bar such as Chat)
    side_left: float | None = None   # left edge of a secondary side bar on the tab row (Chat ...)
    tabs: list[Block] = None         # the editor's tab blocks
    actions: list[Block] = None      # editor-title action icons on the tab row (run ▷ ...)

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
    blocks = [b for b in obs.blocks_in(None) if b.app == win.app and b.window == win.title]
    rows = M.group_lines(blocks)
    panes = [p for p in L.find_panes(obs, win.app) if p.window == win.title]
    pane = min(panes, key=lambda p: p.gutter_x) if panes else None   # left-most editor group
    editor_left = chrome_bottom = None
    tabs, tab_row = _tab_row(win, blocks)
    side_left, actions = _tab_row_extras(tabs, tab_row)
    if pane is None and tabs:
        # no readable line numbers (small text, scale 1): the tab row gives the editor's left edge,
        # the breadcrumb under it the top of the text area
        editor_left = max(win.rect.x, min(b.rect.x for b in tabs) - 12)
        th = max(b.rect.h for b in tabs)
        row_y2 = max(b.rect.y2 for b in tab_row)
        crumb = [b for b in blocks if row_y2 - 2 <= b.rect.y <= row_y2 + 2.5 * th
                 and editor_left - 4 <= b.rect.x <= editor_left + 90
                 and (M.is_breadcrumb(b.text) or _TAB.match(b.text.strip()) or "›" in b.text)]
        chrome_bottom = max(b.rect.y2 for b in crumb) if crumb else row_y2 + 4
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
    right = max(p.right_edge for p in panes) if panes else (side_left if side_left is not None else win.rect.x2)
    if side_left is not None:
        right = min(right, side_left)
    return _Layout(win, blocks, rows, pane, panes, editor_left, chrome_bottom, right, side_left, tabs, actions)


def _tab_row(win: Window, blocks: list[Block]) -> tuple[list[Block], list[Block]]:
    """(tab blocks, every block on the tab row). The tab row is the highest row with a file-name
    tab in the window's top band (explorer entries are file names too, but lower down)."""
    cands = [b for b in blocks if win.rect.y - 2 <= b.rect.y <= win.rect.y + 140 and _TAB.match(b.text.strip())]
    # never Explorer entries: tabs sit right of the side bar header ("EXPLORER") and are laid out
    # side by side, not in a vertical list (README.md under notes.py is the Explorer, not a tab row)
    heads = [b for b in blocks if _SIDEBAR_MARKERS.match(b.text.strip()) and b.rect.y <= win.rect.y + 140]
    if heads:
        side_x2 = max(b.rect.x2 for b in heads)
        cands = [b for b in cands if b.rect.x > side_x2 + 40]

    def in_list(b: Block) -> bool:   # 2+ file names stacked at the same x: an Explorer list (a tab has
        return sum(1 for o in blocks if o is not b and abs(o.rect.x - b.rect.x) <= 8   # at most its breadcrumb)
                   and _TAB.match(o.text.strip()) and 0 < abs(o.rect.cy - b.rect.cy) < 4.4 * b.rect.h) >= 2
    cands = [b for b in cands if not in_list(b)]
    if not cands:
        return [], []
    first = min(cands, key=lambda b: b.rect.y)
    row = [b for b in blocks if abs(b.rect.cy - first.rect.cy) < 0.6 * first.rect.h]
    return sorted((b for b in row if _TAB.match(b.text.strip())), key=lambda b: b.rect.x), row


def _tab_row_extras(tabs: list[Block], row: list[Block]) -> tuple[float | None, list[Block]]:
    """(left edge of a side bar header on the tab row, editor action icons between the tabs and it)."""
    if not tabs:
        return None, []
    tabs_x2 = max(b.rect.x2 for b in tabs)
    side = [b for b in row if b.rect.x > tabs_x2 and b.text.strip().lower() in _SIDE_TITLES]
    side_left = min(b.rect.x for b in side) - 14 if side else None
    acts = [b for b in row if b.rect.x > tabs_x2 + 10 and (side_left is None or b.rect.x2 < side_left)
            and len(b.text.strip()) <= 6 and not _TAB.match(b.text.strip())]
    return side_left, sorted(acts, key=lambda b: b.rect.x)


def _run_icon(lay: _Layout) -> Region | None:
    for b in lay.actions or []:
        if _RUN_ICON.match(b.text.strip()):
            s = b.rect.h
            return Region("run_button", Rect(b.rect.x - 5, b.rect.cy - s / 2 - 5, s + 10, s + 10), lay.win.app,
                          "tab_row_icon")
    return None


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
    r = Rect(left, top, lay.right_edge - left, lay.status_top - top)    # the panel is as wide as the editor
    return Region("terminal", r, lay.win.app, src) if r.h > 20 else None


def _terminal_prompt(lay: _Layout) -> Region | None:
    """The live (bottom-most) prompt line in the integrated terminal panel, as a one-line box clamped to
    the panel's own edges and kept above the status bar; None when no prompt line is readable."""
    panel = _terminal(lay)
    if panel is None:
        return None
    p = panel.rect
    bottom = min(p.y2, lay.status_top) - 2
    lines = [ln for ln in lay.rows if ln.rect.y >= p.y and ln.rect.y2 <= bottom + 2 and p.x - 4 <= ln.rect.x < p.x2
             and "›" not in ln.text and (_PROMPT.search(ln.text) or _PROMPT_END.search(ln.text))]
    if not lines:
        return None
    ln = max(lines, key=lambda ln: ln.rect.y)
    x = max(p.x + 2, ln.rect.x - 6)
    x2 = min(p.x2 - 2, max(ln.rect.x2 + 160, x + 420))   # room for the command typed after the prompt
    y, y2 = max(p.y, ln.rect.y - 3), min(bottom, ln.rect.y2 + 3)
    r = Rect(x, y, x2 - x, y2 - y)
    return Region("terminal_prompt", r, lay.win.app, "prompt_line") if r.w > 20 and r.h > 6 else None


def _editor(lay: _Layout) -> Region | None:
    if lay.pane is None:
        if lay.editor_left is None or lay.chrome_bottom is None:
            return None
        top = lay.chrome_bottom + 4
        term = _terminal(lay)
        bottom = term.rect.y - 2 if term is not None else lay.status_top
        return Region("editor", Rect(lay.editor_left, top, lay.right_edge - lay.editor_left, bottom - top),
                      lay.win.app, "tabs")
    pane = lay.pane
    # below the tab bar + breadcrumb (an unread breadcrumb: line 1's row top is the editor's top)
    top = max(lay.chrome_bottom + 4, pane.rect.y - 3) if lay.chrome_bottom is not None else pane.rect.y - 4
    term = _terminal(lay)
    bottom = term.rect.y - 2 if term is not None else lay.status_top
    bottom = max(bottom, pane.rect.y2) if term is None else bottom
    left = lay.editor_left if lay.editor_left is not None else pane.gutter_x - 20
    return Region("editor", Rect(left, top, lay.right_edge - left, bottom - top), lay.win.app, "gutter")


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
    if menu_title(name) is not None:
        return find_menu_item(obs, menu_title(name), app)
    name = canonical(name)
    if name not in REGIONS:
        raise ValueError(f"unknown region {name!r} (one of {', '.join(REGIONS)})")
    if name == "terminal" and app and M.is_terminal_app(app):
        w = next((w for w in obs.windows if M.app_matches(app, w.app)), None)
        if w is None:
            return None
        return Region("terminal", Rect(w.rect.x, w.rect.y + 28, w.rect.w, w.rect.h - 28), w.app, "window")
    lay = _layout(obs, app)
    if lay is None:
        return None
    reg = {"terminal": _terminal, "editor": _editor, "explorer": _explorer, "run_button": _run_icon,
           "terminal_prompt": _terminal_prompt}[name](lay)
    if reg is not None and obs.screen.w:
        reg.rect = reg.rect.clamp(obs.screen)
    return reg


def side_bar(obs: ScreenObservation, app: str | None = None) -> Rect | None:
    """A secondary side bar right of the editor (Chat / Copilot / Outline), from its tab-row header
    to the status bar; None if there is none."""
    lay = _layout(obs, app)
    if lay is None or lay.side_left is None:
        return None
    top = min((b.rect.y for b in lay.tabs), default=lay.win.rect.y) - 8
    return Rect(lay.side_left, top, lay.win.rect.x2 - lay.side_left, lay.status_top - top)


# ---------------------------------------------------------------------- editor rows (for set-of-marks)

@dataclass
class EditorRow:
    line: int | None        # 1-based file line (None when the gutter couldn't be read)
    text: str               # "" for a blank row
    rect: Rect              # full-width row of the editor text area
    app: str | None


def editor_rows(obs: ScreenObservation, app: str | None = None) -> list[EditorRow]:
    """Every editor row on screen, blank ones included ("type X here" needs the empty line).
    With a readable gutter: each visible file line. Without: rows found in the editor region from the
    code blocks' spacing, blank rows between them and one after the last (line=None)."""
    lay = _layout(obs, app)
    if lay is None:
        return []
    out: list[EditorRow] = []
    if lay.panes:
        for pane in sorted(lay.panes, key=lambda p: p.gutter_x):
            for n in range(pane.first, pane.last + 1):      # numbers Vision missed are interpolated
                r = pane.row_rect(n)
                if r is not None:
                    out.append(EditorRow(n, pane.row_text(n).strip(), r.clamp(obs.screen) if obs.screen.w else r,
                                         pane.app))
        return out
    ed = _editor(lay)
    if ed is None:
        return []
    inside = [ln for ln in lay.rows if ed.rect.contains(ln.rect) and ln.text.strip()]
    if not inside:
        # no text in the editor at all: an EMPTY file (a brand-new lesson file). Its line 1 is where
        # the learner types; VS Code puts it at the editor's top, ~76 pt right of the edge at 12 pt.
        th = sorted(b.rect.h for b in (lay.tabs or [])) or [12.6]
        lh = round(1.43 * th[len(th) // 2], 1)
        left = ed.rect.x + 76 * lh / 18
        return [EditorRow(1, "", Rect(left - 4, ed.rect.y, ed.rect.x2 - left + 4, lh), lay.win.app)]
    inside.sort(key=lambda ln: ln.rect.cy)
    h = sorted(ln.rect.h for ln in inside)[len(inside) // 2]
    gaps = [b.rect.cy - a.rect.cy for a, b in itertools.pairwise(inside)]
    est = 1.3 * h
    steps = [g / max(1, round(g / est)) for g in gaps if g > 0.5 * est]
    lh = sorted(steps)[len(steps) // 2] if steps else est
    left = min(ln.rect.x for ln in inside) - 4
    right = ed.rect.x2

    def row(cy: float, text: str) -> EditorRow:
        return EditorRow(None, text, Rect(left, cy - lh / 2, right - left, lh), lay.win.app)
    for i, ln in enumerate(inside):
        out.append(row(ln.rect.cy, ln.text.strip()))
        nxt = inside[i + 1].rect.cy if i + 1 < len(inside) else None
        k = round((nxt - ln.rect.cy) / lh) if nxt is not None else 2      # one blank row after the last
        for j in range(1, k):
            cy = ln.rect.cy + j * lh
            if cy + lh / 2 <= ed.rect.y2:
                out.append(row(cy, ""))
    return out


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
