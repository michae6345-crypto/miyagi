"""The learner's code as a check should read it: comments removed, parameter names canonical, one function scoped.

A lesson's code pattern is written against the step's own code. Matched on the raw text it was fooled three ways:

* commented-out code (``# def add(a, b):``) matched as if it were written;
* a guard typed into the wrong function (``raise ValueError`` inside ``multiply()``) matched a check about
  ``divide()``;
* the same function with other parameter names (``add(x, y)`` for ``add(a, b)``) matched nothing.

Everything here is general (Python / JS / TS / C-style text; ``def`` scoping is Python's) and works on a file on disk or
on OCR'd screen text (no indentation, one visual line per line).
"""
from __future__ import annotations

import ast
import re

_PY_EXT = (".py", ".pyw")
_C_EXT = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".go",
          ".rs", ".swift", ".kt", ".php", ".scala")


def lang_of(filename: str | None) -> str | None:
    """``"py"`` / ``"c"`` (``//`` and ``/* */`` comments) from a file name, else None."""
    low = str(filename or "").strip().lower()
    if low.endswith(_PY_EXT):
        return "py"
    if low.endswith(_C_EXT):
        return "c"
    return None


_FULL_LINE_COMMENT = re.compile(r"^[ \t]*(?:#(?!\w)|//).*$", re.M)  # language unknown: whole-line comments only


def strip_comments(text: str, lang: str | None) -> str:
    """``text`` without comments, line structure kept (a block comment keeps its newlines). Strings are left whole
    (docstrings too: a docstring is not always a comment). A single-quoted string ends at its line's end, so one OCR
    misread quote cannot swallow the rest of the screen. Unknown language: only whole-line ``#`` / ``//`` comments."""
    if lang is None:
        return _FULL_LINE_COMMENT.sub("", text)
    out: list[str] = []
    i, n = 0, len(text)
    quote = ""  # the open string's delimiter ('"', "'", '"""', "'''", "`")
    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and i + 1 < n:
                out.append(text[i:i + 2])
                i += 2
                continue
            if text.startswith(quote, i):
                out.append(quote)
                i += len(quote)
                quote = ""
                continue
            if c == "\n" and len(quote) == 1 and quote != "`":
                quote = ""  # unterminated: stop at the line end
            out.append(c)
            i += 1
            continue
        if c in "\"'`":
            tri = text[i:i + 3]
            quote = tri if lang == "py" and tri in ('"""', "'''") else c
            out.append(quote)
            i += len(quote)
            continue
        if lang == "py" and c == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if lang == "c" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if lang == "c" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, end))
            i = end
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- functions

def _def_re(name: str) -> re.Pattern[str]:
    return re.compile(rf"^[ \t]*(?:async[ \t]+)?def[ \t]+{re.escape(name)}[ \t]*\(", re.M)


_ANY_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?(?:def|class)[ \t]+\w", re.M)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def function_spans(text: str, name: str) -> list[tuple[int, int]]:
    """Character spans (start, end) of every ``def name(...)`` in ``text``, def line through its last body line.
    A Python source that parses is cut by ``ast``; otherwise (partial code, OCR text) by indentation when the body is
    indented, else down to the next ``def`` / ``class`` line (OCR drops the indentation)."""
    lines = text.splitlines(keepends=True)
    starts = [0]
    for ln in lines:
        starts.append(starts[-1] + len(ln))
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        tree = None
    spans: list[tuple[int, int]] = []
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                a, b = node.lineno - 1, getattr(node, "end_lineno", None) or node.lineno
                spans.append((starts[a], starts[min(b, len(lines))]))
        return sorted(spans)
    rx = _def_re(name)
    for k, ln in enumerate(lines):
        if not rx.match(ln):
            continue
        base = _indent(ln)
        body = next((x for x in lines[k + 1:] if x.strip()), "")
        end = len(lines)
        if body and _indent(body) > base:  # an indented body: ends at the first line back at (or left of) the def
            end = next((j for j in range(k + 1, len(lines)) if lines[j].strip() and _indent(lines[j]) <= base),
                       len(lines))
        else:  # flat OCR lines: ends at the next def / class
            end = next((j for j in range(k + 1, len(lines)) if _ANY_DEF.match(lines[j])), len(lines))
        spans.append((starts[k], starts[end]))
    return spans


def function_scope(text: str, name: str) -> str | None:
    """The text of ``def name(...)`` (all of them, joined), or None when ``text`` defines no such function."""
    spans = function_spans(text, name)
    return "\n".join(text[a:b] for a, b in spans) if spans else None


# a function a check is about: "divide() raises a ValueError", "add() returns a + b"
_LABEL_FUNCTION = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\(\)")


def function_of(check: dict) -> str | None:
    explicit = check.get("function")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    m = _LABEL_FUNCTION.search(str(check.get("label") or ""))
    return m.group(1) if m else None


# ---------------------------------------------------------------- parameter names

def param_names(params: str) -> list[str]:
    """``"a, b=2, *args: int"`` -> ``["a", "b", "args"]`` (self / cls and the bare ``*`` / ``/`` left out)."""
    out = []
    for part in params.split(","):
        word = re.match(r"\s*\**\s*([A-Za-z_]\w*)", part)
        if word and word.group(1) not in ("self", "cls"):
            out.append(word.group(1))
    return out


_SIG = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+(\w+)[ \t]*\(([^)]*)\)", re.M)


def signatures(code: str | None) -> dict[str, list[str]]:
    """``{function name: [parameter names]}`` of the ``def`` lines in a step's code (first definition wins)."""
    sigs: dict[str, list[str]] = {}
    for m in _SIG.finditer(code or ""):
        sigs.setdefault(m.group(1), param_names(m.group(2)))
    return sigs


def canonical_params(text: str, sigs: dict[str, list[str]]) -> str:
    """``text`` with the learner's parameter names for each function of ``sigs`` renamed to the step's own (same
    function name, same arity, other names: ``add(x, y)`` -> ``add(a, b)`` everywhere in its body), so a check
    written against ``a`` / ``b`` still reads the same function. Anything the names don't map (another arity) is
    left alone: that is a different function."""
    for name, canon in sigs.items():
        if not canon:
            continue
        for a, b in reversed(function_spans(text, name)):
            seg = text[a:b]
            m = _SIG.search(seg)
            if not m or m.group(1) != name:
                continue
            mine = param_names(m.group(2))
            if len(mine) != len(canon) or mine == canon:
                continue
            mapping = dict(zip(mine, canon))
            seg = re.sub(r"(?<![\w.])[A-Za-z_]\w*", lambda w: mapping.get(w.group(0), w.group(0)), seg)
            text = text[:a] + seg + text[b:]
    return text


# ---------------------------------------------------------------- the one entry point

_COMMENT_PATTERN = re.compile(r"#|//|/\\\*|\bcomments?\b", re.I)


def code_view(text: str, check: dict, filename: str | None = None, sigs: dict[str, list[str]] | None = None) -> str:
    """What a code check should search: ``text`` without comments (unless the check is about a comment), with the
    step's parameter names, narrowed to the function the check names when ``text`` defines it."""
    pattern, label = str(check.get("pattern") or ""), str(check.get("label") or "")
    lang = lang_of(filename or check.get("file"))
    if not _COMMENT_PATTERN.search(pattern) and not re.search(r"\bcomments?\b", label, re.I):
        text = strip_comments(text, lang)
    if lang in (None, "py"):
        if sigs:
            text = canonical_params(text, sigs)
        if (fn := function_of(check)) and (scoped := function_scope(text, fn)) is not None:
            text = scoped
    # the same code in its canonical form too (import aliases, one name per import, <Fragment> as <>): code_equiv
    from .code_equiv import equivalent_view

    if (same := equivalent_view(text, filename or check.get("file"))) is not None:
        text = text + "\n" + same
    return text
