"""Top-level Python blocks by name, for a lesson's "Do it for me" and its step gate.

T5 (step "Write the sigmoid function", code: def sigmoid + def sigmoid_slope): the learner's main.py had both defs
with wrong bodies. step_code.place_code took only `def sigmoid(x):` as their copy (the comment line under it ended the
match), typed the step's code over that one line and kept the old body and the old sigmoid_slope below it: a second
`def sigmoid_slope` that overrode the right one. The step passed anyway (its patterns were all in the file).

- `blocks(text)`: the file's top-level statements as Blocks (0-based [start, end) lines, decorators and the body's
  trailing indented comments included; `lead` = the first of the comment lines right above it). ast when the text
  parses, else by indentation (a learner's half-typed copy often doesn't compile).
- `replace_by_name(code, text, others)`: (new_text, line) with each top-level block of the step's code put IN PLACE of
  the file's version of it: the def / class of the same name (its other copies deleted), an assignment to the same
  name that reads alike, a statement whose first line reads alike; an import the file already has is left out; the
  step's other blocks go right after the step block before them. A file block that is another step's code (`others`)
  is never taken, except a def / class (two copies of one never make sense). None: nothing of the step is in the
  file (the caller inserts the code instead). Pure text; never writes.
- `verify(code, new_text, old_text)`: '' when each def / class of the step's code is defined exactly once at the top
  level and the file compiles (or did not compile before either); else the reason, for the log.
- `copies(code, text)`: how many top-level copies the file has of each def / class of the step's code.
- `same_code(a, b)`: both parse to the same program (a placement that only changes spacing / comments is no fix).
- `overridden(code, text)`: the step's defs / classes that a later top-level copy overrides (the file's last copy is
  not the step's): [(name, [line, ...])]. The step gate: such a file must not pass the step.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

SIMILAR = 0.6  # an assignment reads like the step's ("W1 = rng.standard_normal((3, 2))" for "...((2, 3))")
HEAD_SIMILAR = 0.85  # another statement's first line reads like the step's ("for epoch in range(500):")
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_DEF = re.compile(r"(?:async\s+def|def|class)\s+([A-Za-z_]\w*)")
_ASSIGN = re.compile(r"([A-Za-z_]\w*)\s*(?::[^=]*)?=(?!=)")


@dataclass
class Block:
    start: int  # first line, decorators included (0-based)
    end: int  # one past the last line, the body's trailing indented comments included
    kind: str  # def (def / async def / class) | assign | import | other
    names: tuple[str, ...]
    lead: int  # first of the col-0 comment lines right above `start` (== start when none)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b), autojunk=False).ratio()


def _comment(line: str) -> bool:
    return line.strip().startswith("#")


def _parses(text: str) -> bool:
    try:
        ast.parse(text or "")
    except (SyntaxError, ValueError):
        return False
    return True


def _kind(node: ast.AST | None, head: str) -> tuple[str, tuple[str, ...]]:
    if node is not None:
        if isinstance(node, DEFS):
            return "def", (node.name,)
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
            return "assign", tuple(t.id for t in node.targets)  # type: ignore[attr-defined]
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            return "assign", (node.target.id,)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "import", ()
        return "other", ()
    if m := _DEF.match(head):
        return "def", (m.group(1),)
    if re.match(r"(?:import|from)\s", head):
        return "import", ()
    if m := _ASSIGN.match(head):
        return "assign", (m.group(1),)
    return "other", ()


def _scan(lines: list[str]) -> list[tuple[int, int]]:
    """[start, end) of the top-level statements of text that doesn't parse: a col-0 code line and the indented /
    bracket-closing lines under it (decorators stay with their def; triple-quoted strings are skipped)."""
    spans: list[tuple[int, int]] = []
    start = last = None
    quote = None
    for i, ln in enumerate(lines):
        code = ln.strip()
        if quote is not None:  # inside a multi-line string: part of the current statement
            if start is not None:
                last = i
        elif code and not code.startswith("#"):
            top = not ln[:1].isspace() and code[:1] not in ")]}"
            if top and start is not None and not all(lines[k].startswith("@") for k in range(start, last + 1)):
                spans.append((start, last + 1))
                start = None
            if top and start is None:
                start = i
            if start is not None:
                last = i
        for q in ('"""', "'''"):
            if ln.count(q) % 2 and quote in (None, q):
                quote = None if quote == q else q
    if start is not None:
        spans.append((start, last + 1))
    return spans


def blocks(text: str) -> list[Block]:
    lines = (text or "").splitlines()
    try:
        tree = ast.parse(text or "")
    except (SyntaxError, ValueError):
        spans: list[tuple[int, int, ast.AST | None]] = [(s, e, None) for s, e in _scan(lines)]
    else:
        spans = [(min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])]) - 1,
                  n.end_lineno or n.lineno, n) for n in tree.body]
    out: list[Block] = []
    floor = 0
    for start, end, node in spans:
        start = max(start, floor)
        while end < len(lines) and lines[end][:1].isspace() and _comment(lines[end]):
            end += 1  # the body's trailing comments ("    # TODO") go with it
        lead = start
        while lead > floor and lines[lead - 1].startswith("#"):
            lead -= 1  # its comment lines right above ("# 2 inputs -> 3 hidden neurons")
        head = next((ln for ln in lines[start:end] if not ln.startswith("@")), "")
        kind, names = _kind(node, head)
        out.append(Block(start, end, kind, names, lead))
        floor = end
    return out


def _code_text(lines: list[str], b: Block) -> str:
    return "\n".join(ln for ln in lines[b.start:b.end] if not _comment(ln))


def _first_code(lines: list[str], b: Block) -> str:
    return next((ln for ln in lines[b.start:b.end] if ln.strip() and not ln.startswith("@") and not _comment(ln)), "")


def _chunks(code: str) -> list[tuple[Block, list[str], int]]:
    """The step's top-level blocks: (block, its lines with the comments above it, blank lines before it)."""
    lines = code.splitlines()
    bs = blocks(code)
    out, prev = [], 0
    for k, b in enumerate(bs):
        seg = lines[prev:b.end] + (lines[b.end:] if k == len(bs) - 1 else [])
        gap = 0
        while seg and not seg[0].strip():
            seg.pop(0)
            gap += 1
        while seg and not seg[-1].strip():
            seg.pop()
        out.append((b, seg, gap))
        prev = b.end
    return out


def _owned(others: Iterable[str]) -> set[str]:
    """Other steps' top-level statements (comments and spacing ignored): a file block like one of these is theirs."""
    out: set[str] = set()
    for code in others:
        lines = (code or "").splitlines()
        out |= {_norm(_code_text(lines, b)) for b in blocks(code or "")}
    out.discard("")
    return out


def replace_by_name(code: str, text: str, others: Iterable[str] = ()) -> tuple[str, int] | None:
    code = (code or "").strip("\n")
    if not code.strip() or not _parses(code):
        return None  # an indented fragment / not Python: the caller places the text
    lines = (text or "").splitlines()
    have, want = blocks(text), _chunks(code)
    if not have or not want:
        return None
    code_lines = code.splitlines()
    owned = _owned(others)
    used: set[int] = set()
    drop: set[int] = set()
    edits: dict[int, list[str]] = {}  # file block -> the lines that replace it
    starts: dict[int, int] = {}  # file block -> its first replaced line (its comments above when the step has some)
    where: list[tuple[int, int]] = []  # per placed step block: (the file block it rides in, offset there)
    pending: list[str] = []  # step blocks before the first one the file has: they go just above it
    pending_at: list[int] = []
    last: int | None = None
    for b, seg, gap in want:
        if not seg:
            continue
        mine = _code_text(code_lines, b)
        free = [i for i, h in enumerate(have) if i not in used and i not in drop and h.kind == b.kind]
        hit: int | None = None
        if b.kind == "def":
            same = [i for i in free if have[i].names == b.names]
            if same:
                hit = same[0]
                drop |= set(same[1:])  # its other copies: the last one would override the step's
        elif b.kind == "import":
            if any(_norm(_code_text(lines, have[i])) == _norm(mine) for i in free):
                continue  # already imported
        else:
            ok = [i for i in free if _norm(_code_text(lines, have[i])) not in owned and (
                (b.kind == "assign" and set(have[i].names) & set(b.names)
                 and _sim(_code_text(lines, have[i]), mine) >= SIMILAR)
                or (b.kind == "other" and _sim(_first_code(lines, have[i]), _first_code(code_lines, b)) >= HEAD_SIMILAR))]
            if ok:
                hit = max(ok, key=lambda i: _sim(_code_text(lines, have[i]), mine))
        if hit is not None:
            used.add(hit)
            starts[hit] = have[hit].lead if seg[0].startswith("#") else have[hit].start
            body = pending + ([""] * gap if pending else [])
            where += [(hit, off) for off in pending_at]
            where.append((hit, len(body)))
            edits[hit] = body + seg
            pending, pending_at, last = [], [], hit
        elif last is not None:
            edits[last] += [""] * gap
            where.append((last, len(edits[last])))
            edits[last] += seg
        else:
            if pending:
                pending += [""] * gap
            pending_at.append(len(pending))
            pending += seg
    if not edits:
        return None
    regions = sorted([(starts[i], have[i].end, i) for i in edits] + [(have[i].lead, have[i].end, -1 - i) for i in drop])
    out: list[str] = []
    at: dict[int, int] = {}
    pos = 0
    for s, e, i in regions:
        out += lines[pos:s]
        if i >= 0:
            at[i] = len(out)
            out += edits[i]
        else:  # a second copy: gone, with the blank lines above it when blank lines (or the end) follow it
            while out and not out[-1].strip() and (e >= len(lines) or not lines[e].strip()):
                out.pop()
        pos = e
    out += lines[pos:]
    line = at[where[0][0]] + where[0][1] + 1 if where else 1  # the step's first line
    return "\n".join(out).rstrip("\n") + "\n", line


def same_code(a: str, b: str) -> bool:
    """Both parse to the same program (spacing and comments aside)."""
    try:
        return a == b or ast.dump(ast.parse(a or "")) == ast.dump(ast.parse(b or ""))
    except (SyntaxError, ValueError):
        return False


def copies(code: str, text: str) -> dict[str, int]:
    names = [n for b in blocks((code or "").strip("\n")) if b.kind == "def" for n in b.names]
    found = [n for b in blocks(text or "") if b.kind == "def" for n in b.names]
    return {n: found.count(n) for n in dict.fromkeys(names)}


def _compile_error(text: str) -> str:
    try:
        compile(text or "", "<file>", "exec")
    except (SyntaxError, ValueError) as e:
        return f"the file would not compile (line {getattr(e, 'lineno', None) or '?'})"
    return ""


def verify(code: str, new_text: str, old_text: str | None = None) -> str:
    if (bad := _compile_error(new_text)) and (old_text is None or not _compile_error(old_text)):
        return bad
    for name, n in copies(code, new_text).items():
        if n != 1:
            return f"{name} is defined {n} times" if n else f"{name} is missing"
    return ""


def overridden(code: str, text: str) -> list[tuple[str, list[int]]]:
    try:
        step, tree = ast.parse((code or "").strip("\n")), ast.parse(text or "")
    except (SyntaxError, ValueError):
        return []
    out = []
    for d in (n for n in step.body if isinstance(n, DEFS)):
        same = [n for n in tree.body if isinstance(n, DEFS) and n.name == d.name]
        if len(same) > 1 and ast.dump(same[-1]) != ast.dump(d):
            out.append((d.name, [n.lineno for n in same]))
    return out
