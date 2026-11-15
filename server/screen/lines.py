"""Editor line geometry: where file line N (or an anchor's line) is on screen, for boxing exactly
where to type in VS Code / Cursor. Pure Python (no pyobjc): runs on recorded OCR anywhere.

OCR path: find the editor's line-number gutter (a right-aligned column of increasing integers),
fit row centres + line height from it, extend over rows Vision missed (single-digit numbers,
blank lines) up to the chrome above/below (tabs, breadcrumbs, panel), then box a line as the
full width of the editor text area. AX path (when Accessibility is granted): the focused editor's
file, live buffer and caret-line rect; see `merge_ax` for how the two are combined.

All rects: screen points, top-left origin of the primary display (same as `locate()`).
"""
from __future__ import annotations

import itertools
import os
import re
from dataclasses import dataclass, field

from . import match as M
from .types import OVERLAY_ROLES, Block, Rect, ScreenObservation

EDITOR_APPS = ("Code", "Cursor", "Windsurf", "VSCodium", "Code - Insiders", "Visual Studio Code")
_NUM = re.compile(r"\d{1,5}")
_GLUED = re.compile(r"(\d{1,5})\s+(\S.*)")


# ---------------------------------------------------------------------- results

@dataclass
class LineLocation:
    """Where a file line is. Truthy only when the line is on screen (`rect` set).

    rect           full-width row of the editor text area (points), None if not visible
    line           1-based file line (for an anchor: the line it was found on, if known)
    visible_lines  (first, last) file lines visible in that editor pane, None if no editor found
    direction      "up" / "down": scroll that way to reach `line` (None when visible/unknown)
    reason         why rect is None: no_editor | file_not_active | not_visible | not_found
    source         "ocr" | "ax" | "ax+ocr"
    text           what's on that line (OCR, or the exact buffer text via AX)
    match_rect     locate_anchor only: the anchor text itself
    """
    file: str | None
    line: int | None
    rect: Rect | None = None
    visible_lines: tuple[int, int] | None = None
    direction: str | None = None
    reason: str | None = None
    source: str | None = None
    app: str | None = None
    text: str | None = None
    match_rect: Rect | None = None
    pane: Rect | None = None          # the editor text area (all visible rows)
    line_height: float | None = None
    occluded: bool = False            # a hover tooltip / inline chat widget covers part of the row

    def __bool__(self) -> bool:
        return self.rect is not None

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "rect": self.rect.to_dict() if self.rect else None,
                "visible_lines": list(self.visible_lines) if self.visible_lines else None,
                "direction": self.direction, "reason": self.reason, "source": self.source, "app": self.app,
                "text": self.text, "match_rect": self.match_rect.to_dict() if self.match_rect else None,
                "pane": self.pane.to_dict() if self.pane else None,
                "line_height": round(self.line_height, 2) if self.line_height else None,
                "occluded": self.occluded}


@dataclass
class _Cand:
    n: int
    cy: float
    x: float
    x2: float
    h: float
    block: Block
    glued: str | None = None       # code text glued to the number in the same Vision block


@dataclass
class EditorPane:
    """One editor group: its gutter rows (file line -> row centre y) and text-area extent."""
    app: str | None
    window: str | None
    rows: dict[int, float]          # file line -> row centre y (measured + extended)
    measured: set[int]              # lines whose number Vision actually read
    line_height: float
    gutter_x: float                 # left of the line numbers
    gutter_x2: float                # right of the line numbers
    text_left: float
    text_right: float
    blocks: list[Block] = field(default_factory=list)
    right_edge: float = 0.0          # the editor group's right boundary (window, next group, side panel)

    @property
    def first(self) -> int:
        return min(self.rows)

    @property
    def last(self) -> int:
        return max(self.rows)

    @property
    def visible(self) -> tuple[int, int]:
        return self.first, self.last

    @property
    def rect(self) -> Rect:
        top = self.rows[self.first] - self.line_height / 2
        return Rect(self.text_left, top, self.text_right - self.text_left,
                    self.rows[self.last] - self.rows[self.first] + self.line_height)

    def y_for(self, line: int) -> float | None:
        if line in self.rows:
            return self.rows[line]
        if not self.first <= line <= self.last:
            return None
        lo = max(n for n in self.rows if n < line)
        hi = min(n for n in self.rows if n > line)
        return self.rows[lo] + (self.rows[hi] - self.rows[lo]) * (line - lo) / (hi - lo)

    def row_rect(self, line: int, pad_x: float = 4.0) -> Rect | None:
        cy = self.y_for(line)
        if cy is None:
            return None
        h = self.line_height
        return Rect(self.text_left - pad_x, cy - h / 2, self.text_right - self.text_left + pad_x, h)

    def row_blocks(self, line: int) -> list[Block]:
        cy = self.y_for(line)
        if cy is None:
            return []
        h = self.line_height
        return sorted((b for b in self.blocks if abs(b.rect.cy - cy) < 0.45 * h
                       and b.rect.x2 > self.gutter_x2 + 1 and b.rect.x < self.text_right
                       and not (_NUM.fullmatch(b.text.strip()) and b.rect.x < self.text_left - 4)),
                      key=lambda b: b.rect.x)

    def row_text(self, line: int) -> str:
        parts = []
        for b in self.row_blocks(line):
            t = b.text
            if b.rect.x < self.gutter_x2 - 1:          # number glued to the code: drop it
                m = _GLUED.fullmatch(t.strip())
                t = m.group(2) if m else t
            parts.append(t)
        return " ".join(parts)

    def line_at_y(self, y: float) -> int | None:
        best = min(self.rows, key=lambda n: abs(self.rows[n] - y))
        return best if abs(self.rows[best] - y) <= self.line_height / 2 else None

    def direction_to(self, line: int) -> str | None:
        if line < self.first:
            return "up"
        if line > self.last:
            return "down"
        return None


# ---------------------------------------------------------------------- gutter detection

def _candidates(blocks: list[Block]) -> list[_Cand]:
    out = []
    for b in blocks:
        t = b.text.strip()
        if _NUM.fullmatch(t):
            out.append(_Cand(int(t), b.rect.cy, b.rect.x, b.rect.x2, b.rect.h, b))
            continue
        m = _GLUED.fullmatch(t)
        if m and len(t) > len(m.group(1)) + 1:
            frac = len(m.group(1)) / len(t)
            out.append(_Cand(int(m.group(1)), b.rect.cy, b.rect.x, b.rect.x + b.rect.w * frac, b.rect.h, b,
                             glued=m.group(2)))
    return [c for c in out if c.n >= 1]


def _longest_increasing(cands: list[_Cand]) -> list[_Cand]:
    """Longest chain (by y) with strictly increasing line numbers and plausible spacing."""
    cands = sorted(cands, key=lambda c: c.cy)
    best: list[list[_Cand]] = []
    for i, c in enumerate(cands):
        chain = [c]
        for j in range(i):
            p = best[j]
            last = p[-1]
            dy, dn = c.cy - last.cy, c.n - last.n
            if dn >= 1 and dy > 0 and 6 <= dy / dn <= 80 and len(p) + 1 > len(chain):
                chain = p + [c]
        best.append(chain)
    return max(best, key=len) if best else []


def _clusters(cands: list[_Cand], tol: float = 8.0) -> list[list[_Cand]]:
    """Group by right edge (line numbers are right-aligned)."""
    out: list[list[_Cand]] = []
    for c in sorted(cands, key=lambda c: c.x2):
        if out and abs(c.x2 - sorted(x.x2 for x in out[-1])[len(out[-1]) // 2]) <= tol:
            out[-1].append(c)
        else:
            out.append([c])
    return out


def find_panes(obs: ScreenObservation, app: str | None = None, min_rows: int = 4) -> list[EditorPane]:
    """Every editor pane with a readable line-number gutter, most rows first."""
    blocks = _editor_blocks(obs, app)
    by_win: dict[tuple, list[Block]] = {}
    for b in blocks:
        by_win.setdefault((b.app, b.window), []).append(b)
    panes: list[EditorPane] = []
    for (a, win), bs in by_win.items():
        win_rect = next((w.rect for w in obs.windows if w.app == a and w.title == win), None)
        cols = []
        for cl in _clusters(_candidates(bs)):
            chain = _longest_increasing(cl)
            if len(chain) < min_rows:
                continue
            dn = chain[-1].n - chain[0].n
            lh = (chain[-1].cy - chain[0].cy) / dn if dn else 0
            if not 8 <= lh <= 60:      # terminal columns (epoch 100, 200, ...) have tiny dy/dn
                continue
            # consecutive numbers should dominate (folding / wrapping make a few gaps)
            steps = [b.n - a_.n for a_, b in itertools.pairwise(chain)]
            if sum(1 for s in steps if s == 1) < 0.5 * len(steps):
                continue
            cols.append((chain, lh))
        cols.sort(key=lambda p: min(c.x for c in p[0]))
        for i, (chain, lh) in enumerate(cols):
            gx = min(c.x for c in chain)
            gx2 = sorted(c.x2 for c in chain)[len(chain) // 2]
            right_limit = (min(c.x for c in cols[i + 1][0]) - lh) if i + 1 < len(cols) else (
                win_rect.x2 if win_rect else obs.screen.x2 if obs.screen.w else max(b.rect.x2 for b in bs))
            side = _side_column(bs, gx2, right_limit, lh)
            if side is not None:     # a secondary side bar (Chat, Copilot, Outline) right of the editor
                right_limit = side - 8
            pane_blocks = [b for b in bs if b.rect.x2 > gx - 2 and b.rect.x < right_limit]
            panes.append(_build_pane(a, win, chain, lh, gx, gx2, right_limit, pane_blocks, obs, win_rect))
    panes.sort(key=lambda p: -len(p.measured))
    return panes


def _build_pane(app, win, chain: list[_Cand], lh: float, gx: float, gx2: float, right_limit: float,
                blocks: list[Block], obs: ScreenObservation, win_rect: Rect | None) -> EditorPane:
    rows = {c.n: c.cy for c in chain}
    # where the code starts: the left-most text right of the gutter on a measured row
    code_x, code_x2 = [], []
    for c in chain:
        if c.glued:
            code_x.append(c.block.rect.x + c.block.rect.w * (1 - len(c.glued) / len(c.block.text.strip())))
            code_x2.append(c.block.rect.x2)
        for b in blocks:
            if b is not c.block and abs(b.rect.cy - c.cy) < 0.45 * lh and b.rect.x > gx2:
                code_x.append(b.rect.x)
                code_x2.append(b.rect.x2)
    text_left = min(code_x) if code_x else gx2 + 1.5 * lh
    text_right = right_limit - SCROLLBAR
    if code_x2 and max(code_x2) < text_right - MINIMAP:   # leave the minimap out unless code runs under it
        text_right -= MINIMAP
    text_right = max(text_left + 10 * lh, text_right)
    pane = EditorPane(app, win, rows, set(rows), lh, gx, gx2, text_left, text_right, blocks, right_limit)
    _extend(pane, chain, obs, win_rect)
    return pane


def _side_column(blocks: list[Block], gx2: float, right_limit: float, lh: float) -> float | None:
    """Left edge of a text column right of the code that is NOT code: its blocks have no code
    running into them from the left, at least three of them line up, and it has its own header
    level with the editor tabs, above the first code row (VS Code's secondary side bar: "Chat",
    "Outline" ...). Lined-up trailing comments have no such header."""
    code_top = min((b.rect.cy for b in blocks if gx2 - 2 <= b.rect.x < gx2 + 80), default=None)  # line 1-ish
    if code_top is None:
        return None
    cands = []
    for b in blocks:
        if b.rect.cy < code_top - lh / 2 or b.rect.x <= gx2 + 200 or b.rect.x >= right_limit:
            continue
        if any(o is not b and abs(o.rect.cy - b.rect.cy) < 0.5 * b.rect.h and o.rect.x < b.rect.x
               and b.rect.x - o.rect.x2 < 30 for o in blocks):
            continue
        cands.append(b.rect.x)
    cands.sort()
    for i, x in enumerate(cands):
        if len([c for c in cands[i:] if c - x <= 24]) < 3:
            continue
        if any(code_top - 6 * lh <= b.rect.cy < code_top - lh / 2 and abs(b.rect.x - x) <= 30 for b in blocks):
            return x
    return None


SCROLLBAR = 14.0
MINIMAP = 110.0     # VS Code / Cursor default minimap column
TITLE_BAR = 30.0    # window top: title / tab strip
STATUS_BAR = 24.0   # window bottom: status bar


def _is_chrome(b: Block, pane: EditorPane) -> bool:
    """Tabs, breadcrumbs, panel headers and terminal rows start left of the line numbers and run
    across them; code never does."""
    return b.rect.x < pane.gutter_x - 2 and b.rect.x2 > pane.gutter_x2 + 2


def _extend(pane: EditorPane, chain: list[_Cand], obs: ScreenObservation, win_rect: Rect | None) -> None:
    """Add rows Vision didn't number (1-9 are often missed; blank lines have no text).

    Upward/downward to the chrome (breadcrumbs above, the panel header below) when there is one:
    the editor fills its viewport with rows up to it. Without chrome, only as far as the furthest
    code text (never into the window's title/tab strip or status bar)."""
    lh = pane.line_height
    first, last = chain[0], chain[-1]
    above = [b for b in pane.blocks if b.rect.cy < first.cy - 0.5 * lh]
    below = [b for b in pane.blocks if b.rect.cy > last.cy + 0.5 * lh]
    frame = win_rect or (obs.screen if obs.screen.w else None)
    lo_y = frame.y + TITLE_BAR if frame else -1e9
    hi_y = frame.y2 - STATUS_BAR if frame else 1e9
    top_walls = [b.rect.y2 for b in above if _is_chrome(b, pane)]
    bot_walls = [b.rect.y for b in below if _is_chrome(b, pane)]

    def code_row(b: Block) -> bool:
        return (not _is_chrome(b, pane) and b.rect.x >= pane.gutter_x - 2 and b.rect.x < pane.text_right
                and lo_y <= b.rect.cy <= hi_y)

    if top_walls:
        top = max(top_walls) - 2
    else:
        ev = [b.rect.cy for b in above if code_row(b)]
        top = min(ev) - lh / 2 - 2 if ev else first.cy
    i = 1
    while first.n - i >= 1 and first.cy - i * lh - lh / 2 >= top:
        pane.rows[first.n - i] = first.cy - i * lh
        i += 1
    if bot_walls:
        bottom = min(bot_walls) + 2
    else:
        ev = [b.rect.cy for b in below if code_row(b)]
        bottom = max(ev) + lh / 2 + 2 if ev else last.cy
    i = 1
    while last.cy + i * lh + lh / 2 <= bottom:
        pane.rows[last.n + i] = last.cy + i * lh
        i += 1
    # gaps inside the measured range are interpolated by y_for(); nothing to store


def _editor_blocks(obs: ScreenObservation, app: str | None) -> list[Block]:
    if app:
        return obs.blocks_in(app)
    eds = [b for b in obs.blocks_in(None) if b.app and any(M.app_matches(e, b.app) for e in EDITOR_APPS)]
    if eds:
        return eds
    return [b for b in obs.blocks_in(None) if not M.is_terminal_app(b.app)]


# ---------------------------------------------------------------------- files

def same_file(a: str | None, b: str | None) -> bool:
    """`/x/pinn_demo/pinn_convection.py` ~ `pinn_demo/pinn_convection.py` ~ `pinn_convection.py`."""
    if not a or not b:
        return False
    a, b = a.removeprefix("file://").replace("\\", "/"), b.removeprefix("file://").replace("\\", "/")
    if a == b:
        return True
    if "/" not in a or "/" not in b:
        return os.path.basename(a) == os.path.basename(b)
    return a.endswith("/" + b.lstrip("./")) or b.endswith("/" + a.lstrip("./"))


def _file_shown(obs: ScreenObservation, pane: EditorPane, file: str) -> bool | None:
    """Does this pane show `file`? Decided by the breadcrumb right above the pane (each editor group
    has its own; tabs are no good: inactive tabs are listed too), else by the window title (the
    focused editor's file). None if neither is readable."""
    base = _alnum(os.path.basename(file))       # OCR drops dots: "calculator.py" reads "calculatorpy"
    top = pane.rect.y
    crumbs = [b for b in obs.blocks if b.app == pane.app and top - 6 * pane.line_height <= b.rect.y2 <= top + 2
              and b.rect.x2 > pane.gutter_x and b.rect.x < pane.text_right and ("\u203a" in b.text or " > " in b.text)]
    if crumbs:
        return any(base in _alnum(b.text) for b in crumbs)
    if pane.window:
        return base in _alnum(pane.window)
    return None


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", s.lower())


# ---------------------------------------------------------------------- public (OCR)

def _pick_pane(obs: ScreenObservation, file: str | None, app: str | None) -> tuple[EditorPane | None, str | None]:
    panes = find_panes(obs, app)
    if not panes:
        return None, "no_editor"
    if not file:
        return panes[0], None
    shown = [(p, _file_shown(obs, p, file)) for p in panes]
    yes = [p for p, s in shown if s]
    if yes:
        return yes[0], None
    unknown = [p for p, s in shown if s is None]
    if unknown:
        return unknown[0], None
    return panes[0], "file_not_active"


def locate_line(obs: ScreenObservation, file: str | None, line: int, app: str | None = None) -> LineLocation:
    """Full-width rect of file line `line` in the editor showing `file` (OCR of `obs`)."""
    pane, why = _pick_pane(obs, file, app)
    if pane is None:
        return LineLocation(file, line, reason=why, source="ocr")
    loc = LineLocation(file, line, visible_lines=pane.visible, source="ocr", app=pane.app, pane=pane.rect,
                       line_height=pane.line_height)
    if why:
        loc.reason = why
        return loc
    r = pane.row_rect(line)
    if r is None:
        loc.reason, loc.direction = "not_visible", pane.direction_to(line)
        return loc
    loc.rect = r.clamp(obs.screen) if obs.screen.w else r
    loc.text = pane.row_text(line) or None
    loc.occluded = _under_hover(obs, loc.rect)
    return loc


def _under_hover(obs: ScreenObservation, r: Rect) -> bool:
    for role in OVERLAY_ROLES:      # one box per kind of overlay (a hover's blank interior counts too)
        hov = [b.rect for b in obs.blocks if b.role == role]
        if not hov:
            continue
        box = hov[0]
        for h in hov[1:]:
            box = box.union(h)
        if box.x < r.x2 and r.x < box.x2 + 8 and box.y - 2 < r.y2 and r.y < box.y2 + 2:
            return True
    return False


def locate_anchor(obs: ScreenObservation, text: str, app: str | None = None, file: str | None = None,
                  file_text: str | None = None, threshold: float = 82.0) -> LineLocation:
    """The editor line containing `text` (first line of a multi-line anchor): full-width row rect,
    its file line number (from the gutter), and `match_rect` for the text itself.

    `file_text` (the file's contents, e.g. read from disk or the AX buffer) lets an anchor that
    is scrolled off screen still resolve to a line number + scroll direction."""
    needle = next((s for s in text.splitlines() if s.strip()), "").strip()
    pane, why = _pick_pane(obs, file, app)
    file_lines = _find_in_text(file_text, needle) if file_text else []
    if pane is None or why:
        return LineLocation(file, file_lines[0] if file_lines else None, reason=why or "no_editor", source="ocr",
                            visible_lines=pane.visible if pane else None)
    rx = M._as_regex(needle)
    hits = []
    for n in sorted(pane.rows):
        t = pane.row_text(n)
        if t:
            s = M.line_score(needle, t, rx)
            if s >= threshold:
                hits.append((s, n))
    if file_lines:   # the file says which occurrence(s) are real; prefer those
        on_disk = [(s, n) for s, n in hits if n in file_lines]
        hits = on_disk or hits
    loc = LineLocation(file, None, visible_lines=pane.visible, source="ocr", app=pane.app, pane=pane.rect,
                       line_height=pane.line_height)
    if not hits:
        if file_lines:
            n = min(file_lines, key=lambda k: min(abs(k - pane.first), abs(k - pane.last)))
            _with_rect(loc, pane, n, obs)   # in view but OCR misread it: trust the file
        else:
            loc.reason = "not_found"
        return loc
    best = max(s for s, _ in hits)
    n = min(n for s, n in hits if s >= best - 3)
    _with_rect(loc, pane, n, obs)
    bs = pane.row_blocks(n)
    if bs:
        mr = bs[0].rect
        for b in bs[1:]:
            mr = mr.union(b.rect)
        loc.match_rect = mr.pad(3)
    return loc


def _with_rect(loc: LineLocation, pane: EditorPane, n: int, obs: ScreenObservation) -> LineLocation:
    r = pane.row_rect(n)
    loc.line = n
    if r is None:
        loc.reason, loc.direction = "not_visible", pane.direction_to(n)
        return loc
    loc.rect = r.clamp(obs.screen) if obs.screen.w else r
    loc.text = pane.row_text(n) or None
    loc.reason = loc.direction = None
    return loc


def _find_in_text(file_text: str, needle: str) -> list[int]:
    """1-based line numbers whose text contains `needle` (whitespace/case-insensitive)."""
    if not needle:
        return []
    rx = M._as_regex(needle)
    out = []
    for i, ln in enumerate(file_text.split("\n"), 1):
        if (rx is not None and rx.search(ln)) or M.squash(needle) in M.squash(ln):
            out.append(i)
    return out


# ---------------------------------------------------------------------- AX

def merge_ax(loc: LineLocation, ed, document: str | None, file: str | None, line: int) -> LineLocation:
    """Combine an OCR result with the AX editor state (`ax.EditorState`, duck-typed).

    AX knows the focused file exactly, the live (unsaved) buffer and the caret line's exact rect;
    other rows are extrapolated from the caret with a fixed line height, which folding and word
    wrap break. So:
    - AX file != `file`                      -> OCR result unchanged (another editor is focused)
    - OCR found the row, AX agrees (<= h/2)  -> OCR x-extent, AX y ("ax+ocr")
    - OCR found the row, AX disagrees        -> OCR (it read the actual gutter)
    - OCR found no editor at all             -> AX rect when it has one ("ax")
    The exact AX buffer line replaces the OCR text in every case where the file matches.
    """
    if ed is None or not (file is None or same_file(document, file)):
        return loc
    t = ed.line_text(line)
    if t is not None:
        loc.text = t
    ax_r = ed.rect_for_line(line)
    if ax_r is None:
        return loc
    if loc.rect is not None:
        if abs(ax_r.cy - loc.rect.cy) <= 0.5 * loc.rect.h:
            loc.rect = Rect(loc.rect.x, ax_r.y, loc.rect.w, ax_r.h)
            loc.source = "ax+ocr"
        return loc
    if loc.reason == "no_editor":
        loc.rect, loc.source, loc.reason, loc.line_height = ax_r, "ax", None, ed.line_height
    return loc


def ax_anchor_line(ed, needle: str) -> int | None:
    """File line of the first occurrence of `needle` in the AX buffer page (unsaved text too)."""
    if ed is None or not needle.strip():
        return None
    hits = _find_in_text(ed.text, needle.strip().splitlines()[0])
    return ed.page_start_line + hits[0] - 1 if hits else None
