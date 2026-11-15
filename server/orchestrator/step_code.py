"""Lesson-mode "Do it for me" helpers: type a step's code into its file, or say in plain words what to change.

- `code_complete(code, text)`: every meaningful line of the step's code is in the file (spacing ignored).
- `place_code(code, text, anchors)`: the file with the step's code typed in, over the learner's partial / wrong copy
  of it when there is one, else below the step's target line, else at the end. Pure text; never writes.
- `fix_in_words(yours, expected, line, text)`: "Change `tasks.add` to `tasks.append` on line 8." for a fix card
  when no safe patch could be made (the learner never sees the coach's internal reasons).
- `place_step` / `by_name` / `code_done`: the same for a Python file, by name first (py_blocks): the step's defs,
  classes and assignments go in place of the file's ones, never as second copies (T5: a multi-function step).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from difflib import SequenceMatcher

from . import py_blocks

HEAD_MIN = 0.85  # the learner's copy starts with (nearly) the step's first line
LINE_MIN = 0.6  # a later line of their copy is a version of one of the step's lines ("tasks.add(task)")
TOKEN = re.compile(r"[\w.]+|\S")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b), autojunk=False).ratio()


def _indent(s: str) -> str:
    return s[: len(s) - len(s.lstrip())]


def _meaningful(code: str) -> list[str]:
    return [ln for ln in (code or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def anchors(step: dict) -> list[str]:
    """The step's target lines ("tasks = []", caption "Type below this line")."""
    return [t["match"] for t in step.get("targets") or [] if isinstance(t.get("match"), str) and t["match"].strip()]


def code_complete(code: str, text: str) -> bool:
    have = {_norm(ln) for ln in (text or "").splitlines() if ln.strip()}
    want = [_norm(ln) for ln in _meaningful(code)]
    return bool(want) and all(w in have for w in want)


def _partial_copy(lines: list[str], want: list[str]) -> tuple[int, int] | None:
    """[start, end) of the learner's copy of the step's code: a line like its first line, then the following
    non-blank lines while each is a version of a later step line (lines they skipped are allowed)."""
    best, best_key = None, None
    for s, ln in enumerate(lines):
        head = _sim(ln, want[0]) if ln.strip() else 0.0
        if head < HEAD_MIN:
            continue
        k, e, j = 1, s + 1, s + 1
        while j < len(lines) and k < len(want):
            if not lines[j].strip():
                j += 1
                continue
            hit = next((m for m in range(k, len(want)) if _sim(lines[j], want[m]) >= LINE_MIN), None)
            if hit is None:
                break
            k, e, j = hit + 1, j + 1, j + 1
        key = (head, e - s)
        if best_key is None or key > best_key:
            best, best_key = (s, e), key
    return best


def place_code(code: str, text: str, anchor_lines: list[str] | None = None) -> tuple[str, int, bool]:
    """(new_text, 1-based line of the code, replaced_their_copy)."""
    code_lines = (code or "").rstrip("\n").splitlines()
    want = _meaningful(code)
    lines = (text or "").splitlines()
    if not want:
        return text, 1, False
    span = _partial_copy(lines, want)
    if span is not None:
        s, e = span
        old, new = _indent(want[0]), _indent(lines[s])
        block = [(new + ln[len(old):] if ln.startswith(old) else ln) if ln.strip() else "" for ln in code_lines]
        return "\n".join(lines[:s] + block + lines[e:]) + "\n", s + 1, True
    at = None
    for a in anchor_lines or []:
        at = next((i for i, ln in enumerate(lines) if _norm(ln) and _norm(a) == _norm(ln)), None)
        if at is None:
            at = next((i for i, ln in enumerate(lines) if _norm(a) and _norm(a) in _norm(ln)), None)
        if at is not None:
            break
    if at is None:  # nowhere better: the end of the file
        body = (text or "").rstrip("\n")
        return (body + "\n\n" if body else "") + "\n".join(code_lines) + "\n", (len(body.splitlines()) + 2 if body else 1), False
    after = lines[at + 1:]
    block = [""] + code_lines + ([""] if after and after[0].strip() else [])
    return "\n".join(lines[: at + 1] + block + after) + "\n", at + 3, False


def _one_line(a: str, b: str, where: str) -> str:
    ta, tb = list(TOKEN.finditer(a)), list(TOKEN.finditer(b))
    ops = [o for o in SequenceMatcher(None, [m.group() for m in ta], [m.group() for m in tb], autojunk=False).get_opcodes()
           if o[0] != "equal"]
    if len(ops) == 1 and ops[0][0] == "replace":
        _, i1, i2, j1, j2 = ops[0]
        old, new = a[ta[i1].start():ta[i2 - 1].end()], b[tb[j1].start():tb[j2 - 1].end()]
        if min(len(old), len(new)) >= 3 and "`" not in old + new:
            return f"Change `{old}` to `{new}`{where}."
    if max(len(a), len(b)) <= 70 and "`" not in a + b:
        return f"Change `{a}` to `{b}`{where}."
    return ""


def fix_in_words(yours: str | None, expected: str | None, line: int | None = None, text: str | None = None) -> str:
    """One plain sentence naming the change, or '' when the fix isn't one changed line."""
    a = [ln for ln in (yours or "").splitlines() if ln.strip()]
    b = [ln for ln in (expected or "").splitlines() if ln.strip()]
    if not a or not b or len(a) != len(b):
        return ""
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x.strip() != y.strip()]
    if len(changed) != 1:
        return ""
    i = changed[0]
    line = line if isinstance(line, int) and line > 0 else None  # the diagnosis says 0 for "no line"
    if not line and text:
        first = a[0].strip()
        line = next((n for n, ln in enumerate(text.splitlines(), 1) if ln.strip() == first), None)
    return _one_line(a[i].strip(), b[i].strip(), f" on line {line + i}" if line else "")


def by_name(code: str, text: str, py: bool, others: Iterable[str] = ()) -> tuple[str, int] | None:
    """Python: (new_text, line) with the step's blocks in place of the file's blocks of the same names, when the file
    has some, the code changes (not just spacing / comments) and the result checks out (one copy of each of the
    step's defs; it compiles)."""
    if not py or not (code or "").strip():
        return None
    hit = py_blocks.replace_by_name(code, text, others)
    if hit is None or py_blocks.same_code(hit[0], text) or py_blocks.verify(code, hit[0], text):
        return None
    return hit


def place_step(code: str, text: str, anchor_lines: list[str] | None = None, py: bool = False,
               others: Iterable[str] = ()) -> tuple[str, int, bool]:
    """place_code, by name first in a Python file (by_name). The caller still verifies (py_blocks.verify)."""
    if (hit := by_name(code, text, py, others)) is not None:
        return hit[0], hit[1], True
    return place_code(code, text, anchor_lines)


def code_done(code: str, text: str, py: bool = False) -> bool:
    """Every meaningful line of the step's code is in the file and (Python) no def / class of it has a second copy:
    T5's file had every line of the step's code AND an old sigmoid_slope below the new one, overriding it."""
    return code_complete(code, text) and not (py and any(n > 1 for n in py_blocks.copies(code, text).values()))
