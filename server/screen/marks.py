"""Set-of-marks candidates: numbered screen targets a model (Haiku) can pick by id. Pure Python.

    from server.screen.marks import candidates, listing, by_id
    cands = candidates(obs, intent="the line that defines add")      # list[Candidate]
    prompt = listing(cands)          # "1 [region] terminal ...\n12 [code L4] def add(a, b):\n..."
    target = by_id(cands, 12)        # -> Candidate (rect in screen points)

Contents:
- regions, with FIXED ids whether or not they are on screen right now:
  1 terminal, 2 editor, 3 explorer, 4 terminal_menu (absent ones are just left out);
- text lines from id 10 up:
  - first the editor code rows, by file line: full-width row rects from the line-number gutter,
    with the FILE line number (`line`) and the gutter number left out of the text; rows partly
    hidden by a hover tooltip have `occluded=True`;
  - then every other OCR line (terminal output, explorer items, other apps' windows) in reading
    order, Vision's split blocks re-joined.
Never included: hover tooltips, the breadcrumb row, the editor tab bar / title bar, line-number-only
blocks, and our own overlay (already masked out of observations).

Ids are stable for a given observation (the same `obs` always numbers the same way, whatever the
intent). Across frames, region ids never change; line ids follow reading order.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from . import lines as L
from . import match as M
from . import regions as R
from .types import Rect, ScreenObservation

REGION_IDS = {"terminal": 1, "editor": 2, "explorer": 3, "terminal_menu": 4}
FIRST_LINE_ID = 10


@dataclass
class Candidate:
    id: int
    kind: str                 # "region" | "code" (editor row) | "text" (any other OCR line)
    text: str                 # region name for regions; the line's text otherwise
    rect: Rect                # screen points, top-left origin of the primary display
    app: str | None = None
    line: int | None = None   # code rows: 1-based file line
    region: str | None = None # regions: terminal | editor | explorer | terminal_menu; lines: the region they're in
    score: float | None = None  # relevance to `intent` (0-100) when an intent was given
    occluded: bool = False    # code rows: a hover tooltip covers part of it (text may be incomplete)

    def to_dict(self) -> dict:
        d = {"id": self.id, "kind": self.kind, "text": self.text, "rect": self.rect.to_dict(), "app": self.app}
        if self.line is not None:
            d["line"] = self.line
        if self.region is not None:
            d["region"] = self.region
        if self.score is not None:
            d["score"] = round(self.score, 1)
        if self.occluded:
            d["occluded"] = True
        return d


def _region_rects(obs: ScreenObservation, app: str | None, regions: dict | None) -> dict[str, Rect]:
    if regions is not None:     # e.g. the reader's stabilized rects
        return {k: Rect.from_any(v) for k, v in regions.items() if v is not None and k in REGION_IDS}
    out = {}
    for name in REGION_IDS:
        reg = R.find_region(obs, name, app)
        if reg is not None:
            out[name] = reg.rect
    return out


def _chrome_rows(obs: ScreenObservation, editor: Rect | None) -> list[Rect]:
    """Title bar + tab bar + breadcrumb of the front editor window: everything above the editor
    region, from the editor's left edge to the window's right edge."""
    if editor is None:
        return []
    w = next((w for w in obs.windows if w.rect.contains(editor)), None)
    top = w.rect.y if w is not None else editor.y - 80
    right = w.rect.x2 if w is not None else editor.x2
    return [Rect(editor.x - 4, top, right - editor.x + 4, editor.y - top)]


def candidates(obs: ScreenObservation, intent: str | None = None, app: str | None = None, *,
               max_lines: int = 120, regions: dict | None = None) -> list[Candidate]:
    """Numbered targets for set-of-marks prompting (see module doc). With `intent`, every candidate
    gets a `score`, and when there are more than `max_lines` text lines the best-scoring ones are
    kept; the list is always returned in id order (regions first), so prompts stay stable."""
    rects = _region_rects(obs, app, regions)
    out = [Candidate(REGION_IDS[n], "region", n, r, region=n) for n, r in sorted(rects.items(),
                                                                                    key=lambda kv: REGION_IDS[kv[0]])]
    editor = rects.get("editor")
    chrome = _chrome_rows(obs, editor)
    lines: list[Candidate] = []

    # editor code rows (exact rows from the gutter, file line numbers)
    covered: list[Rect] = []
    for pane in L.find_panes(obs, app):
        for n in sorted(pane.rows):
            r = pane.row_rect(n)
            text = pane.row_text(n).strip()
            if r is None or not text:
                continue
            r = r.clamp(obs.screen) if obs.screen.w else r
            lines.append(Candidate(0, "code", text, r, pane.app, line=n, region="editor",
                                   occluded=L._under_hover(obs, r)))
        covered.append(Rect(pane.gutter_x - 4, pane.rect.y, pane.text_right - pane.gutter_x + 8, pane.rect.h))

    # every other OCR line
    for ln in M.group_lines(obs.blocks_in(app)):
        text = ln.text.strip()
        if not text or M.is_breadcrumb(text) or re.fullmatch(r"\d{1,5}", text):
            continue
        if any(c.contains(ln.rect) for c in covered) or any(c.contains(ln.rect) for c in chrome):
            continue
        region = next((n for n in ("terminal", "explorer", "terminal_menu") if n in rects
                       and rects[n].contains(ln.rect)), None)
        lines.append(Candidate(0, "text", text, ln.rect, ln.app, region=region))

    code = sorted((c for c in lines if c.kind == "code"), key=lambda c: (c.rect.x, c.line))
    rest = sorted((c for c in lines if c.kind != "code"), key=lambda c: (round(c.rect.y / 4), c.rect.x))
    lines = code + rest
    for i, c in enumerate(lines):
        c.id = FIRST_LINE_ID + i
    if intent:
        for c in out + lines:
            c.score = _score(intent, c)
        if len(lines) > max_lines:
            keep = {c.id for c in sorted(lines, key=lambda c: -(c.score or 0))[:max_lines]}
            lines = [c for c in lines if c.id in keep]
    elif len(lines) > max_lines:
        lines = lines[:max_lines]
    return out + lines


def _score(intent: str, c: Candidate) -> float:
    words = M.norm(intent)
    if c.kind == "region":
        return 100.0 if c.text.replace("_", " ") in words or c.text in words else 0.0
    return float(fuzz.partial_ratio(M.squash(intent), M.squash(c.text))) if len(M.squash(c.text)) >= 2 else 0.0


def listing(cands: list[Candidate], max_chars: int = 120) -> str:
    """Prompt text, one candidate per line: `12 [code L4] def add(a, b):`, `1 [region] terminal`."""
    rows = []
    for c in cands:
        if c.kind == "region":
            tag = "region"
        elif c.kind == "code":
            tag = f"code L{c.line}" + (", partly under a tooltip" if c.occluded else "")
        else:
            tag = f"{c.region or c.app or 'screen'}"
        t = c.text if len(c.text) <= max_chars else c.text[: max_chars - 1] + "…"
        rows.append(f"{c.id} [{tag}] {t}")
    return "\n".join(rows)


def by_id(cands: list[Candidate], cid: int | str) -> Candidate | None:
    try:
        cid = int(str(cid).strip().lstrip("#"))
    except ValueError:
        return None
    return next((c for c in cands if c.id == cid), None)
