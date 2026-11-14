"""Pure text/geometry logic over OCR blocks: app matching, line grouping, locate, contains.

No pyobjc here, so the evaluator and tests can use it on any OS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .types import Block, Rect, ScreenObservation, Window

# ----------------------------------------------------------------- apps

_APP_ALIASES = {
    "vscode": "code", "vs code": "code", "visual studio code": "code", "code": "code",
    "terminal": "terminal", "iterm": "iterm2", "iterm2": "iterm2",
    "jupyter": "jupyter",  # usually a browser tab; matched by window title below
}
TERMINAL_APPS = {"terminal", "iterm2", "warp", "ghostty", "alacritty", "kitty", "wezterm", "hyper", "tabby"}


def _norm_app(name: str | None) -> str:
    n = (name or "").strip().lower()
    return _APP_ALIASES.get(n, n)


def app_matches(wanted: str | None, actual: str | None, title: str | None = None) -> bool:
    """Is `actual` (a window owner name) the app the check asked for? Case/alias-insensitive."""
    if not wanted:
        return True
    w, a = _norm_app(wanted), _norm_app(actual)
    if not a:
        return False
    if w == a or w in a or a in w:
        return True
    return bool(title) and w in title.lower()


def is_terminal_app(app: str | None) -> bool:
    return _norm_app(app) in TERMINAL_APPS


# ----------------------------------------------------------------- block bookkeeping

def assign_windows(blocks: list[Block], windows: list[Window]) -> list[Block]:
    """Tag each block with the front-most window that contains its centre."""
    out = []
    for b in blocks:
        owner = next((w for w in windows if w.rect.contains(b.rect)), None)
        out.append(Block(b.text, b.rect, b.confidence, owner.app if owner else None, owner.title if owner else None))
    return out


def drop_inside(blocks: list[Block], rects: list[Rect]) -> list[Block]:
    """Remove blocks whose centre lies in any of `rects` (our own overlay)."""
    if not rects:
        return blocks
    return [b for b in blocks if not any(r.contains(b.rect) for r in rects)]


def reading_order(blocks: list[Block]) -> list[Block]:
    return sorted(blocks, key=lambda b: (round(b.rect.y / 4), b.rect.x))


# ----------------------------------------------------------------- lines

@dataclass
class Line:
    text: str
    rect: Rect
    app: str | None
    window: str | None
    blocks: list[Block]

    @property
    def confidence(self) -> float:
        return min(b.confidence for b in self.blocks)


def group_lines(blocks: list[Block]) -> list[Line]:
    """Merge blocks that sit on the same visual row of the same window into one Line.

    Vision often splits a row at gaps (`epoch` | `2500` | `loss 2.5e-01` in a terminal, or a
    line number vs. the code). Blocks are bucketed into rows per window (centre within half a
    line height), then joined left-to-right; a horizontal gap wider than 4 line heights starts
    a new Line so side-by-side panes don't get glued together.
    """
    by_win: dict[tuple, list[Block]] = {}
    for b in blocks:
        by_win.setdefault((b.app, b.window), []).append(b)
    lines: list[Line] = []
    for (app, win), bs in by_win.items():
        bs.sort(key=lambda b: b.rect.cy)
        rows: list[list[Block]] = []
        for b in bs:
            if rows:
                row = rows[-1]
                row_cy = sum(x.rect.cy for x in row) / len(row)
                h = min(min(x.rect.h for x in row), b.rect.h)
                if abs(b.rect.cy - row_cy) < 0.5 * h:
                    row.append(b)
                    continue
            rows.append([b])
        for row in rows:
            row.sort(key=lambda b: b.rect.x)
            cur: Line | None = None
            for b in row:
                h = min(cur.rect.h, b.rect.h) if cur else b.rect.h
                if cur is not None and b.rect.x - cur.rect.x2 < 4 * h:
                    cur.text += " " + b.text
                    cur.rect = cur.rect.union(b.rect)
                    cur.blocks.append(b)
                else:
                    cur = Line(b.text, b.rect, app, win, [b])
                    lines.append(cur)
    lines.sort(key=lambda ln: (round(ln.rect.y / 4), ln.rect.x))
    return lines


# ----------------------------------------------------------------- normalisation + fuzzy match

_CONFUSABLES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "—": "-", "–": "-", "·": ".", "，": ","})
_WS = re.compile(r"\s+")


def norm(s: str) -> str:
    """Normalise OCR text for matching: unify quotes/dashes, collapse whitespace, casefold."""
    return _WS.sub(" ", s.translate(_CONFUSABLES)).strip().casefold()


def squash(s: str) -> str:
    """norm() and then drop all whitespace: `f(x, t)` == `f(x,t)`."""
    return _WS.sub("", norm(s))


_REGEX_HINT = re.compile(r"[\\\[\]()?*+{}|^$]")


def _as_regex(match: str) -> re.Pattern | None:
    if not _REGEX_HINT.search(match):
        return None
    try:
        return re.compile(match, re.IGNORECASE)
    except re.error:
        return None


def line_score(needle: str, hay: str, rx: re.Pattern | None = None) -> float:
    """0..100: how well `needle` appears inside the line `hay`."""
    if rx is not None and (rx.search(hay) or rx.search(norm(hay))):
        return 100.0
    n, h = norm(needle), norm(hay)
    if not n:
        return 0.0
    if n in h or squash(needle) in squash(hay):
        return 100.0
    if len(squash(needle)) < 4:
        return 0.0  # too short to fuzz safely
    # partial_ratio aligns the needle against the best substring of the line.
    # Ignore lines much shorter than the needle (they can't contain it).
    sn, sh = squash(needle), squash(hay)
    if len(sh) < 0.6 * len(sn):
        # a long code line cut off by a narrow editor pane: compare the visible prefix
        if len(sh) >= 12:
            sh_code = _GUTTER.sub("", sh)
            return 0.97 * float(fuzz.ratio(sn[:len(sh_code)], sh_code))
        return 0.0
    return float(fuzz.partial_ratio(sn, sh))


_GUTTER = re.compile(r"^\d{1,5}(?=\D)")  # editor line number glued to the code


def _is_gutter(ln: Line) -> bool:
    return ln.text.strip().isdigit()


def _rect_without_gutter(ln: Line) -> Rect:
    bs = ln.blocks
    if len(bs) > 1 and bs[0].text.strip().isdigit():
        bs = bs[1:]
    r = bs[0].rect
    for b in bs[1:]:
        r = r.union(b.rect)
    return r


# ----------------------------------------------------------------- locate

@dataclass
class LocateResult:
    rect: Rect            # padded union of the matched lines, screen points
    app: str | None
    matched: str          # the OCR text that matched (lines joined with \n)
    score: float
    lines: list[Line]

    def to_dict(self) -> dict:
        return {"rect": self.rect.to_dict(), "app": self.app, "matched": self.matched, "score": round(self.score, 1)}


def _adjacent(a: Line, b: Line) -> bool:
    if a.app != b.app or a.window != b.window:
        return False
    h = max(a.rect.h, b.rect.h)
    return -0.5 * h <= b.rect.y - a.rect.y2 < 1.6 * h + 4 and abs(a.rect.x - b.rect.x) < 40 * h


def locate_match(obs: ScreenObservation, match: str, app: str | None = None, *,
                 threshold: float = 82.0, pad: float = 6.0) -> LocateResult | None:
    """Find `match` (substring, regex, or a multi-line snippet) on screen.

    - single-line needle: every line that matches is a hit; hits on consecutive rows of the
      same window are unioned into one rect (so `def pde_residual` + its body, when the needle
      is a regex like `pde_residual|u_t \\+`, highlights one block).
    - multi-line needle: lines of the needle must match consecutive screen lines, in order.
    Ties are broken by: higher score, then the frontmost app, then top-most position.
    """
    lines = [ln for ln in group_lines(obs.blocks_in(app)) if ln.text.strip() and not _is_gutter(ln)]
    if not lines or not match.strip():
        return None
    front_rank = {}
    for i, w in enumerate(obs.windows):
        front_rank.setdefault((w.app, w.title), i)

    needle_lines = [s for s in match.strip().splitlines() if s.strip()]
    groups: list[tuple[float, list[Line]]] = []

    if len(needle_lines) == 1:
        rx = _as_regex(match.strip())
        hits = [(line_score(match, ln.text, rx), ln) for ln in lines]
        hits = [(s, ln) for s, ln in hits if s >= threshold]
        if hits:  # an exact hit beats near-misses (`loss 2.5068` must not pull in `loss 2.5070`)
            best_s = max(s for s, _ in hits)
            hits = [(s, ln) for s, ln in hits if s >= best_s - 3]
        # order by window, then y so consecutive rows are neighbours
        hits.sort(key=lambda p: (p[1].app or "", p[1].window or "", p[1].rect.y))
        for s, ln in hits:
            if groups and _adjacent(groups[-1][1][-1], ln):
                prev_s, prev = groups[-1]
                groups[-1] = (max(prev_s, s), prev + [ln])
            else:
                groups.append((s, [ln]))
    else:
        by_win: dict[tuple, list[Line]] = {}
        for ln in lines:
            by_win.setdefault((ln.app, ln.window), []).append(ln)
        k = len(needle_lines)
        for wl in by_win.values():
            wl.sort(key=lambda ln: ln.rect.y)
            for i in range(len(wl) - k + 1):
                seq = wl[i:i + k]
                if not all(_adjacent(seq[j], seq[j + 1]) for j in range(k - 1)):
                    continue
                scores = [line_score(needle_lines[j], seq[j].text) for j in range(k)]
                s = sum(scores) / k
                if s >= threshold and min(scores) >= threshold - 15:
                    groups.append((s, seq))

    if not groups:
        return None
    groups.sort(key=lambda g: (-g[0], front_rank.get((g[1][0].app, g[1][0].window), 99), g[1][0].rect.y))
    score, best = groups[0]
    r = _rect_without_gutter(best[0])
    for ln in best[1:]:
        r = r.union(_rect_without_gutter(ln))
    r = r.pad(pad)
    if obs.screen.w > 0:
        r = r.clamp(obs.screen)
    return LocateResult(r, best[0].app, "\n".join(ln.text for ln in best), score, best)


def locate(obs: ScreenObservation, match: str, app: str | None = None, **kw) -> Rect | None:
    res = locate_match(obs, match, app, **kw)
    return res.rect if res else None


# ----------------------------------------------------------------- screen_contains helper for checks

def screen_contains(obs: ScreenObservation, pattern: str, app: str | None = None, *, fuzzy: float = 90.0) -> bool:
    """Regex search over the OCR text (scoped to `app`), tolerant to OCR whitespace noise.

    Tries, in order: the regex on the raw text; on whitespace-normalised text; and, if the
    pattern has no regex syntax, a fuzzy line match (score >= `fuzzy`).
    """
    text = obs.text(app)
    try:
        rx = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        if rx.search(text) or rx.search("\n".join(norm(t) for t in text.splitlines())):
            return True
    except re.error:
        rx = None
    # literal fallback: a pattern with regex characters (`u_t+beta*u_x`) may be meant literally;
    # those must match exactly (modulo whitespace), plain text may fuzzy-match.
    need = 100.0 if _REGEX_HINT.search(pattern) else fuzzy
    return any(line_score(pattern, ln.text) >= need for ln in group_lines(obs.blocks_in(app)))


# ----------------------------------------------------------------- cursor

def line_at_point(obs: ScreenObservation, x: float, y: float, slop: float = 6.0) -> Line | None:
    """The OCR line under (x, y), or the nearest one within `slop` points."""
    best, best_d = None, slop + 1
    for ln in group_lines(obs.blocks):
        r = ln.rect
        dx = max(r.x - x, 0, x - r.x2)
        dy = max(r.y - y, 0, y - r.y2)
        d = max(dx, dy)
        if d < best_d:
            best, best_d = ln, d
    return best if best_d <= slop else None


def window_at_point(obs: ScreenObservation, x: float, y: float) -> Window | None:
    return next((w for w in obs.windows if w.rect.contains_point(x, y)), None)
