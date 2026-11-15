"""Every definition a step's code makes is checked on its key expression (QA test 5, 02:16).

Test 5's step 2 typed two functions, sigmoid() and sigmoid_slope(), but its checks covered only the two def lines and
sigmoid's formula: a wrong slope body `s * (1 + s)` passed Check (only Diagram caught it) and silently broke the
training three steps later. Deterministic, no model call, Python files only:

* every top-level def gets a check on its key expression (its last `return`, else its last statement), and every
  top-level assignment one on its whole statement, unless a check of the step already matches most of it;
* a check that matches only a small part of it (`np\\.exp\\(` for `1 / (1 + np.exp(-x))`) is tightened to the whole
  expression, keeping its id and label;
* the same for precision_checks (file_contains), where a def's pattern also requires its key expression inside that
  def's own block, and that no later `def` of the same name overrides it (test 5's Do it for me left a wrong duplicate
  `def sigmoid_slope` at the end of main.py, after the right one). Regex on the normalized body: importing the
  learner's main.py to call the function would run the whole script.

Screen patterns stay within schema.MAX_SCREEN_PATTERN (80 chars); a pattern that already matches the file before this
step (it would pass the moment the step starts) is never added.
"""

from __future__ import annotations

import ast
import io
import keyword
import re
import tokenize

from .schema import MAX_SCREEN_PATTERN

MAX_CHECKS = 8  # screen checks per step once definitions are covered (defs first, then assignments, in code order)
MAX_PRECISION = 10
COVERED = 0.6  # a check covers a definition when it matches >= 60% of its key expression's characters...
OWNED = 0.4  # ...and that match is mostly (>= 40%) inside the key expression (not a `[\s\S]*` span over many lines)
_SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
_WORDY = re.compile(r"\w")


def _tokens(src: str) -> list[tuple[int, str]]:
    """Python tokens of `src` as (type, text), comments and layout left out. [] when it doesn't tokenize."""
    try:
        return [(t.type, t.string) for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type not in _SKIP]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []


def _piece(kind: int, text: str) -> str:
    if kind == tokenize.STRING and len(text) >= 2 and text[-1] in "'\"":  # 'a' or "a": either quote
        head = re.match(r"[rRbBuUfF]*", text).group(0)
        q = 3 if text[len(head):].startswith(("'''", '"""')) else 1
        body = text[len(head) + q:len(text) - q]
        return re.escape(head) + "[\"']" * q + re.escape(body).replace("\\ ", r"\s*") + "[\"']" * q
    return re.escape(text)


def code_pattern(src: str, limit: int | None = None) -> str:
    """Code as a regex that tolerates any spacing between tokens (`return s * (1 - s)` ->
    `return\\s+s\\s*\\*\\s*\\(\\s*1\\s*\\-\\s*s\\s*\\)`), either quote, no comments. Dotted names and calls stay
    tight (`np.exp(`). With `limit`, the longest token prefix that fits."""
    toks = _tokens(src)
    out, prev = "", ""
    for kind, text in toks:
        piece = _piece(kind, text)
        if not out:
            sep = ""
        elif text == "." or prev == "." or (text in ("(", "[") and _WORDY.match(prev[-1:] or " ")
                                            and not keyword.iskeyword(prev)):
            sep = ""  # np.exp(  W2.T  X[0]  (but `return (`)
        elif _WORDY.match(prev[-1:] or " ") and _WORDY.match(text[:1] or " "):
            sep = r"\s+"  # return s, def f, in range
        else:
            sep = r"\s*"
        if limit and len(out) + len(sep) + len(piece) > limit:
            break
        out += sep + piece
        prev = text
    return out


def _nonspace(s: str) -> int:
    return len(re.sub(r"\s+", "", s or ""))


def _collapsed(text: str) -> tuple[str, list[int]]:
    """Whitespace runs as one space, with each character's offset in `text` (search_screen also tries this form)."""
    out, idx, last_space = [], [], False
    for i, ch in enumerate(text):
        if ch.isspace():
            if last_space:
                continue
            out.append(" ")
            last_space = True
        else:
            out.append(ch)
            last_space = False
        idx.append(i)
    return "".join(out), idx


def _spans(pattern: str, text: str) -> list[tuple[int, int]]:
    """Where `pattern` matches `text` (re.M, as the checks are graded), as offsets in `text`."""
    try:
        rx = re.compile(pattern, re.M)
    except re.error:
        return []
    spans = [m.span() for m in rx.finditer(text) if m.end() > m.start()]
    if spans:
        return spans
    flat, idx = _collapsed(text)
    return [(idx[m.start()], idx[m.end() - 1] + 1) for m in rx.finditer(flat) if m.end() > m.start()]


def _matches(pattern: str, text: str) -> bool:
    return bool(text) and bool(_spans(pattern, text))


def _segment(lines: list[str], offsets: list[int], node: ast.AST) -> tuple[int, int]:
    """A node's (start, end) offsets in the code (ast columns count UTF-8 bytes)."""
    def at(line: int, col: int) -> int:
        return offsets[line - 1] + len(lines[line - 1].encode()[:col].decode(errors="ignore"))
    return at(node.lineno, node.col_offset), at(node.end_lineno, node.end_col_offset)


def _key_node(fn: ast.AST) -> ast.AST | None:
    """A def's key expression: its last `return <value>` (nested defs left out), else its last real statement."""
    rets = []

    def walk(n: ast.AST) -> None:
        for ch in ast.iter_child_nodes(n):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(ch, ast.Return) and ch.value is not None:
                rets.append(ch)
            walk(ch)

    walk(fn)
    if rets:
        return max(rets, key=lambda r: (r.lineno, r.col_offset))
    node: ast.AST | None = fn
    while node is not None and getattr(node, "body", None):  # a loop / if / with at the end: its last simple line
        body = [b for b in (getattr(node, "orelse", None) or node.body) if not isinstance(b, ast.Pass)
                and not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str))]
        node = body[-1] if body else None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return None
    return node


def definitions(code: str) -> list[dict]:
    """The top-level definitions in a step's Python code, in order: {kind: def|assign, name, start, end (the key
    expression's offsets in `code`), key (its source), value (the returned / assigned expression's source), node}."""
    if not code.strip() or code.lstrip("\n")[:1].isspace():  # an indented fragment goes inside existing code
        return []
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return []
    lines = [ln + "\n" for ln in code.split("\n")]  # ast counts lines at \n only (str.splitlines also splits at \x0c)
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)
    offsets.append(pos)
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            key = _key_node(node)
            if key is None:
                continue
            a, b = _segment(lines, offsets, key)
            val = key.value if isinstance(key, ast.Return) else key
            va, vb = _segment(lines, offsets, val)
            out.append({"kind": "def", "name": node.name, "start": a, "end": b, "key": code[a:b], "value": code[va:vb],
                        "returns": isinstance(key, ast.Return), "node": key})
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)) and getattr(node, "value", None) is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if not names:
                continue  # x[0] = ..., self.a = ...: not a new name
            a, b = _segment(lines, offsets, node)
            va, vb = _segment(lines, offsets, node.value)
            op = "=" if not isinstance(node, ast.AugAssign) else _AUG.get(type(node.op), "") + "="
            out.append({"kind": "assign", "name": names[0], "start": a, "end": b, "key": code[a:b], "value": code[va:vb],
                        "op": op, "node": node})
    return out


_AUG = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.MatMult: "@", ast.Mod: "%", ast.Pow: "**",
        ast.FloorDiv: "//"}


def _shown(expr: str, words: int) -> str:
    """An expression for a label: as written when it fits in `words` words and 28 characters, else without spaces,
    else its call (`np.sum(…)`)."""
    e = " ".join((expr or "").split())
    if len(e.split()) <= words and len(e) <= 28:
        return e
    tight = re.sub(r"\s*([-+*/@%=<>,()\[\]{}:])\s*", r"\1", e)
    if len(tight) <= 28:
        return tight
    if m := re.match(r"([A-Za-z_][\w.]*)\(", tight):
        return f"{m.group(1)}(…)"
    return tight[:24].rstrip() + "…"


def label_for(d: dict) -> str:
    """<= 6 words, what was made, names in backticks: "`sigmoid_slope()` returns `s*(1-s)`", "`b1` = `np.zeros((1, 3))`"."""
    if d["kind"] == "def":
        if d.get("returns"):
            return f"`{d['name']}()` returns `{_shown(d['value'], 4)}`"
        call = d["node"].value if isinstance(d["node"], ast.Expr) and isinstance(d["node"].value, ast.Call) else None
        if call is not None and (m := re.match(r"([A-Za-z_][\w.]*)", d["value"])):
            return f"`{d['name']}()` calls `{m.group(1)}()`"
        return f"`{d['name']}()` body complete"
    return f"`{d['name']}` {d.get('op') or '='} `{_shown(d['value'], 4)}`"


def _coverage(pattern: str, code: str, d: dict, defs: list[dict] = ()) -> float:
    """How much of definition d's key expression `pattern` matches in the step's code (0..1), counting only matches
    that are mostly inside it. 0 when the pattern also matches another definition's (`float\(\s*input\(` for both
    `a = float(input())` and `b = float(input())`): one of them typed would pass it."""
    total = _nonspace(d["key"])
    spans = _spans(pattern, code)
    if sum(1 for o in defs if any(min(b, o["end"]) > max(a, o["start"]) for a, b in spans)) > 1:
        return 0.0
    best = 0.0
    for a, b in spans:
        lo, hi = max(a, d["start"]), min(b, d["end"])
        if hi <= lo:
            continue
        inside = _nonspace(code[lo:hi])
        if inside >= OWNED * max(1, _nonspace(code[a:b])):
            best = max(best, inside / total if total else 0.0)
    return best


def screen_pattern(d: dict) -> str:
    """A short (<= MAX_SCREEN_PATTERN) pattern for definition d: the whole statement / return line when it fits, else
    the returned / assigned expression, cut at a token when even that is too long."""
    whole = code_pattern(d["key"])
    if whole and len(whole) <= MAX_SCREEN_PATTERN:
        return whole
    if d["kind"] == "assign":  # keep the name: `W1\s*=\s*rng.standard_normal\(...`
        return code_pattern(d["key"], MAX_SCREEN_PATTERN)
    value = code_pattern(d["value"])
    return value if value and len(value) <= MAX_SCREEN_PATTERN else code_pattern(d["value"], MAX_SCREEN_PATTERN)


def file_pattern(d: dict) -> str:
    """The precision pattern for definition d in the file: an assignment as a whole top-level statement; a def's key
    expression inside that def's own block, with no later `def` of the same name after it (the last one wins)."""
    key = code_pattern(d["key"])
    if not key:
        return ""
    if d["kind"] == "assign":
        return "^" + key
    name = re.escape(d["name"])
    return (rf"^(?:async\s+)?def\s+{name}\b(?:(?!^\S)[\s\S])*?{key}"
            rf"(?![\s\S]*^(?:async\s+)?def\s+{name}\b)")


def _useful(pattern: str, code: str, before: str, taken: set[str]) -> bool:
    """Matches the step's own code, isn't already true of the file before the step, isn't a duplicate."""
    return bool(pattern) and pattern not in taken and _matches(pattern, code) and not _matches(pattern, before)


def cover_definitions(step: dict, before: str = "") -> list[str]:
    """Add / tighten checks so each definition in a Python code step is checked on its key expression (see module
    docstring). `before`: the step's file before this step. Returns the names left unchecked (over MAX_CHECKS)."""
    f = (step.get("file") or "").strip()
    code = step.get("code") or ""
    if not f.endswith(".py") or not code.strip() or (step.get("run_command") or "").strip() == code.strip():
        return []
    defs = definitions(code)
    if not defs:
        return []
    left: list[str] = []
    sid = step.get("id") or ""
    for key, tag, kind, cap in (("checks", "c", "screen", MAX_CHECKS), ("precision_checks", "p", "file", MAX_PRECISION)):
        checks = step.setdefault(key, [])
        mine = [c for c in checks if c.get("pattern") and (
            (kind == "screen" and c.get("type") == "screen_contains" and c.get("app") in ("Code", None))
            or (kind == "file" and c.get("type") == "file_contains" and (c.get("file") or f) == f))]
        taken = {c.get("pattern") for c in checks if c.get("pattern")}
        tightened: set[int] = set()
        new: list[tuple[dict, dict]] = []
        for d in defs:
            pat = screen_pattern(d) if kind == "screen" else file_pattern(d)
            # covered on the key expression already (screen patterns are read on the code; a file pattern on it too)
            scores = [(_coverage(c["pattern"], code, d, defs), c) for c in mine if id(c) not in tightened]
            best, owner = max(scores, key=lambda x: x[0], default=(0.0, None))
            if best >= COVERED and (kind == "screen" or d["kind"] == "assign"):
                continue
            if kind == "file" and any(c["pattern"] == pat for c in mine):
                continue
            if not _useful(pat, code, before, taken) or (kind == "screen" and _coverage(pat, code, d, defs) <= best):
                continue  # vacuous, a duplicate, or (cut to 80 chars) no better than the check it has
            if owner is not None and best > 0 and id(owner) not in tightened:  # a loose check on it: tighten that one
                owner["pattern"] = pat
                tightened.add(id(owner))
                taken.add(pat)
                continue
            c = {"id": "", "type": "screen_contains" if kind == "screen" else "file_contains", "label": label_for(d),
                 **({"app": "Code"} if kind == "screen" else {"file": f}), "pattern": pat}
            new.append((d, c))
            taken.add(pat)
        room = max(0, cap - len(checks))
        keep = sorted(new, key=lambda x: (x[0]["kind"] != "def", defs.index(x[0])))[:room]
        keep_ids = {id(c) for _, c in keep}
        checks.extend(c for _, c in new if id(c) in keep_ids)
        if kind == "screen":
            left = [d["name"] for d, c in new if id(c) not in keep_ids]
        if keep or tightened:  # the checklist reads like the code, top to bottom (other kinds of check after)
            def where(k: int) -> tuple[int, int]:
                c = checks[k]
                spans = _spans(c["pattern"], code) if c in mine or id(c) in keep_ids else []
                return (0, spans[0][0]) if spans else (1, k)
            checks[:] = [checks[k] for k in sorted(range(len(checks)), key=where)]
        for j, c in enumerate(checks, 1):
            c["id"] = f"{sid}{tag}{j}"
    return left
