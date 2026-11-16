"""Desktop test 8 (Nov 15, 05:51-05:54): row boxes as wide as the editor reached Miyagi's drawer, so the caption the
app draws beside the box was clipped ("Look at how W1,", "Click ▷ to r") or gone (steps 1 and 3 had none). The tight
"Look here" box (an OCR text match) always had room for its caption.

    fit(rect, text_x2, line_text)    a row box as wide as the row's text + PAD (text_x2: where the gutter row's OCR'd
                                     text ends, server.screen.lines.LineLocation.text_x2), an empty row's EMPTY_W
                                     ("Type it here": the code goes there), never wider than the row; unknown: as is
    line_text(s, step, path, line)   the file line the box is on (VS Code's unsaved text, else the disk); "" for the
                                     row after the file's last line; None when it can't be told

Hooks (tiny, for merges): session._progress_spot and _editor_line_spot (every "Type it here" / "Finish this function" /
"Change this line" row box), run_pointing.culprit_spot (the W1..W3 lines).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

PAD = 12.0  # right of the text's last glyph
MIN_W = 96.0  # a short line (`y = 1`) still gets a box you can see
EMPTY_W = 420.0  # an empty row where the step's code goes: room for the first lines, the caption beside it


def fit(rect: dict, text_x2: float | None, line_text: str | None) -> dict:
    x, w = float(rect["x"]), float(rect["w"])
    if line_text is not None and not line_text.strip():
        nw = min(w, EMPTY_W)
    elif text_x2 is not None and float(text_x2) > x:
        nw = min(w, max(MIN_W, float(text_x2) - x + PAD))
    else:
        return rect
    return {**rect, "w": round(nw, 1)}


def line_text(s: Any, step: dict, path: Any, line: int) -> str | None:
    try:
        p, lines = s._step_lines(step)
        if p is None or Path(str(p)).resolve() != Path(str(path)).resolve():
            return None
    except Exception:  # noqa: BLE001 - unknown: the box keeps its width
        return None
    if 1 <= int(line) <= len(lines):
        return lines[int(line) - 1]
    return "" if int(line) == len(lines) + 1 else None
