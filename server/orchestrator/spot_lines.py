"""Which editor line a lesson box goes on, from the file's text alone (desktop test 5, Nov 15).

Test 5 boxed blank lines in the middle of main.py ("Type it here" on lines 16-17 while the step's code was already on
lines 18-24), a line inside the sigmoid_slope block for step 3, and W2's line for step 6 instead of the end of the file:
the Haiku targeter "moved" the engine's box with confidence 0.7-0.85 each time. The rules here are deterministic and
model-free; session.py asks them where the insertion box goes and whether a targeter move may stand.

Lines are the file's lines (no newlines); line numbers are 1-based like the editor's gutter.
"""
from __future__ import annotations

import difflib
import re

CLOSERS = (")", "]", "}")


def _squash(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def _indented(line: str) -> bool:
    """A line that belongs to the block / expression above it: indented, or a closing bracket (`])`)."""
    return line[:1] in (" ", "\t") or line.lstrip()[:1] in CLOSERS


def last_code_line(lines: list[str]) -> int:
    """The file's last non-blank line (1-based), 0 for an empty file."""
    return next((i + 1 for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), 0)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def block_end(lines: list[str], line: int) -> int:
    """The last non-blank line (1-based) of the block `line` ends or sits in: a header's body (`def f():`), the rest of
    the def / loop the line is inside (`return s * (1 - s)`), a wrapped expression's rows (`X = np.array([[0, 0],`).
    Every following line indented deeper than that block's header (or a closing bracket) still belongs to it."""
    if not 1 <= line <= len(lines):
        return min(max(line, 0), len(lines))
    s0 = lines[line - 1]
    ind = _indent(s0)
    if s0.rstrip().endswith(":") or ind == 0:
        limit = ind  # a header's body / a top-level line's continuation rows: deeper than the line itself
    else:  # inside a block: deeper than the header that opened it (`def sigmoid_slope(s):`)
        limit = next((_indent(lines[k]) for k in range(line - 2, -1, -1)
                      if lines[k].strip() and _indent(lines[k]) < ind), 0)
    last = line
    for k in range(line, len(lines)):  # 0-based k = the line after `line`
        s = lines[k]
        if not s.strip():
            continue
        if _indent(s) <= limit and s.lstrip()[:1] not in CLOSERS:
            break
        last = k + 1
    return last


def insert_line(lines: list[str], anchor: int | None = None) -> tuple[int, int]:
    """(where the step's new code goes, the line above it), both 1-based; the line above is 0 in an empty file.
    anchor (1-based, the step's "Type below <x>" line) -> the line after that line's block (never inside a def / an
    array); None -> the line after the file's last non-blank line."""
    above = block_end(lines, anchor) if anchor else last_code_line(lines)
    return above + 1, above


def inside_block(lines: list[str], line: int) -> bool:
    """Is `line` (1-based) a place new top-level code can't go? Any existing non-blank line (code is never overwritten),
    a blank line whose next code line is indented (inside a def / loop / wrapped expression), or a row outside the
    file (above line 1, or more than one row past its end)."""
    if line < 1 or line > len(lines) + 1:
        return True
    i = line - 1
    if i < len(lines) and lines[i].strip():
        return True
    nxt = next((lines[k] for k in range(i + 1, len(lines)) if lines[k].strip()), None)
    return nxt is not None and _indented(nxt)


def first_change(yours: str | None, expected: str | None) -> tuple[str, str | None] | None:
    """The diagnosis diff's first line that really changes: (the learner's line, what it should read), or (line, None)
    when it should go. None: no such line (an insert only / no diff). Context lines both sides share are skipped (a
    diff that starts at `def sigmoid(x):` is about line 20's np.exp, not the def)."""
    a = [ln.strip() for ln in (yours or "").splitlines() if ln.strip()]
    b = [ln.strip() for ln in (expected or "").splitlines() if ln.strip()]
    if not a:
        return None
    ops = difflib.SequenceMatcher(a=[_squash(x) for x in a], b=[_squash(x) for x in b], autojunk=False).get_opcodes()
    for tag, i1, _i2, j1, j2 in ops:
        if tag == "replace":
            return a[i1], b[j1]
        if tag == "delete":
            return a[i1], None
        if tag == "insert":
            return None
    return None


def find_line(lines: list[str], text: str, start: int = 1) -> int | None:
    """The first line (1-based, from `start`) that reads `text`, spacing ignored; None when it isn't there or the
    text is too short to be sure (`)`, `return`)."""
    want = _squash(text)
    if len(want) < 4:
        return None
    for i in range(max(0, start - 1), len(lines)):
        if _squash(lines[i]) == want:
            return i + 1
    return None


def unique_text(lines: list[str], line: int) -> str | None:
    """Line `line`'s text when OCR can find it for sure: >= 4 characters, no other line of the file reads the same."""
    if not 1 <= line <= len(lines):
        return None
    t = lines[line - 1].strip()
    if len(_squash(t)) < 4 or sum(_squash(ln) == _squash(t) for ln in lines) != 1:
        return None
    return t


def clip(code: str, words: int = 6) -> str:
    """A code line short enough for a box caption (<= `words` words; short_caption would swap a longer one)."""
    w = (code or "").split()
    return " ".join(w) if len(w) <= words else " ".join(w[: words - 1]) + "…"


def takes_kw(fn, name: str) -> bool:
    """Does `fn` accept the keyword `name`? (a test double's screen.confirm may not take move_conf)"""
    import inspect

    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
