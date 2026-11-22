"""Truthful code verdicts for "Just teach me" lesson steps (live test 3, E1 / E19).

A step's checks are loose regexes, so a step passed with `print("You rolled:" roll)` on line 6 while VS Code showed
1 error, and "Requests.get call written" passed without `params={"format": "j1"}` and `response.raise_for_status()`
(the later `.json()` step then crashed). Before a lesson code step passes, two more facts are read from the step
file's exact text (VS Code's buffer, else the disk):

* syntax: the .py file compiles. A SyntaxError is a fail row "<file> has no syntax errors" with "line N: msg".
* key pieces: every call, keyword argument and dict-literal string of each statement of the step's code is in the
  file (spacing and quote style ignored). A statement missing a piece un-passes the check row whose pattern matches
  it ("line 7 still needs params={"format": "j1"}"), else one row "All of this step's code in <file>".

    rows = review(step, results, text, "main.py", syntax=True, whole=True)  -> (results, failing code rows)

Pure: no I/O but `read`, no network, never raises on odd code (a fragment / non-Python step is skipped).
"""

from __future__ import annotations

import keyword
import os
import re
import textwrap
from collections.abc import Container
from pathlib import Path

from server.safety.patterns import safe_compile

_STR = re.compile(r"""(?<!\w)(?P<pre>[rRbBuUfF]{0,2})(?P<lit>"{3}[\s\S]*?"{3}|'{3}[\s\S]*?'{3}"""
                  r"""|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')""")
_CALL = re.compile(r"([A-Za-z_]\w*)\s*\(")
_KWARG = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\s*=(?!=)")
# shell lines (a run step's command), prompts and REPL output are not the file's Python
_NOT_PY = re.compile(r"^\s*(\$\s|>>>|(python3?|pip3?|uv|npm|npx|node|yarn|pnpm|git|cd|ls|cargo|go|ruby|bash|sh|make|"
                     r"pytest|flask|streamlit|jupyter)\b(?!\s*[.(=\[]))")
_PY_RUN = re.compile(r"\bpython3?(?:\.\d+)?\s+([\w./-]+\.py)\b")
SHOWN_MAX = 48


def read(path: Path, buffer_text: str | None) -> str | None:
    """The file's exact text: VS Code's buffer when it has the file open, else the disk (None: unreadable)."""
    if buffer_text is not None:
        return buffer_text
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def python_code(code: str) -> str:
    """The step's code without shell / prompt lines (a run step's `python3 main.py` is not file content)."""
    return "\n".join(ln for ln in (code or "").splitlines() if not _NOT_PY.match(ln))


def self_contained(code: str) -> bool:
    """Does the step's code compile by itself (or as a function body)? A fragment ("def add(a, b):" whose body is
    the next step) means the file may not compile yet at this step: no syntax gate then."""
    src = textwrap.dedent(code or "").strip("\n")
    if not src.strip():
        return True
    for text in (src, "async def _step():\n" + textwrap.indent(src, "    ")):
        try:
            compile(text, "<step>", "exec")
            return True
        except (SyntaxError, ValueError):
            continue
    return False


def syntax_problem(text: str, name: str) -> tuple[int, str] | None:
    """(line, message) of the file's first SyntaxError, else None."""
    try:
        compile(text or "", name, "exec")
    except SyntaxError as e:
        return int(e.lineno or 1), (e.msg or "invalid syntax").strip()
    except ValueError as e:  # e.g. a NUL byte
        return 1, str(e)
    return None


def _norm(s: str) -> str:
    """Spacing and quote style don't matter: 'print( "a" , x )' == 'print("a",x)'; 'def f' keeps its space."""
    s = re.sub(r"\s+", " ", (s or "").replace("'", '"'))
    return re.sub(r" ?([^\w ]) ?", r"\1", s)


def _mask(code: str) -> tuple[str, list[tuple[int, int, str, str]]]:
    """String literals blanked to same-length placeholders (positions line up) and comments to spaces;
    -> (masked, [(start, end, prefix, literal)])."""
    out, lits, last = [], [], 0
    for m in _STR.finditer(code):
        out.append(code[last:m.start()])
        n = m.end() - m.start()
        out.append('"' + "_" * max(0, n - 2) + '"' if n >= 2 else "_" * n)
        lits.append((m.start(), m.end(), m.group("pre"), m.group("lit")))
        last = m.end()
    out.append(code[last:])
    masked = re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), "".join(out))
    return masked, lits


def _close(masked: str, i: int) -> int:
    """Index just past the bracket that closes the one opened at `i` (len(masked) when unclosed)."""
    depth = 0
    for j in range(i, len(masked)):
        if masked[j] in "([{":
            depth += 1
        elif masked[j] in ")]}":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(masked)


def _arg_end(masked: str, i: int) -> int:
    """End of the argument starting at `i`: the next "," or closing bracket at its own depth."""
    depth = 0
    for j in range(i, len(masked)):
        ch = masked[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return j
            depth -= 1
        elif ch == "," and depth == 0:
            return j
    return len(masked)


def _shown(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip().rstrip(",")
    return t if len(t) <= SHOWN_MAX else t[:SHOWN_MAX - 1].rstrip() + "…"


def _statements(code: str) -> list[tuple[str, str, int]]:
    """Logical statements of the step's code -> (original, masked, offset); a call spanning lines is one."""
    masked, _ = _mask(code)
    out, start, depth = [], 0, 0
    for i, ch in enumerate(masked + "\n"):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == "\n" and depth == 0:
            if masked[start:i].strip():
                out.append((code[start:i], masked[start:i], start))
            start = i + 1
    return out


def _pieces(code: str) -> list[dict]:
    """Per statement of the step's code, its behaviour-changing pieces:
    [{"line": statement, "pieces": [(needle regex on _norm text, shown text, (start, end))]}]."""
    masked_all, lits = _mask(code)
    out = []
    for orig, masked, off in _statements(code):
        inner: list[str] = []  # innermost open bracket at each position
        stack: list[str] = []
        for ch in masked:
            inner.append(stack[-1] if stack else "")
            if ch in "([{":
                stack.append(ch)
            elif ch in ")]}" and stack:
                stack.pop()
        found: list[tuple[str, str, tuple[int, int]]] = []
        for m in _CALL.finditer(masked):
            name = m.group(1)
            if keyword.iskeyword(name):
                continue
            s = m.start()
            while s > 0 and (masked[s - 1].isalnum() or masked[s - 1] in "_."):
                s -= 1
            if d := re.search(r"(?:async\s+)?(?:def|class)\s+$", masked[:s]):
                s = d.start()  # a definition reads "def roll_die()", not "roll_die()"
            e = _close(masked, m.end() - 1)
            text = orig[s:e] if e - s <= SHOWN_MAX else orig[s:m.end()] + "…)"
            found.append((rf"(?<!\w){re.escape(name)}\(", _shown(text), (s, e)))
        for m in _KWARG.finditer(masked):
            if inner[m.start()] != "(":
                continue
            e = _arg_end(masked, masked.index("=", m.start()) + 1)
            found.append((rf"(?<![\w.]){re.escape(m.group(1))}=(?!=)", _shown(orig[m.start():e]), (m.start(), e)))
        for start, end, pre, lit in lits:
            s, e = start - off, end - off
            if 0 <= s < len(masked) and "f" not in pre.lower() and inner[s] == "{" and len(lit) <= 40:
                found.append((re.escape(_norm(lit)), lit, (s, e)))
        if found:
            out.append({"line": orig.strip(), "pieces": found})
    return out


def missing_code(code: str, text: str) -> list[dict]:
    """Statements of the step's (Python) code whose pieces aren't all in `text`:
    [{"line": statement, "needs": [shown piece, ...]}] (a piece inside a missing outer piece is not repeated)."""
    norm = _norm(text or "")
    out = []
    for st in _pieces(code):
        miss = [p for p in st["pieces"] if not re.search(p[0], norm)]
        miss.sort(key=lambda p: (p[2][0], -p[2][1]))
        needs, spans = [], []
        for _needle, shown, (s, e) in miss:
            if any(a <= s and e <= b for a, b in spans):
                continue  # inside a missing call / argument already named
            spans.append((s, e))
            if shown not in needs:
                needs.append(shown)
        if needs:
            out.append({"line": st["line"], "needs": needs})
    return out


def _claims(pattern: str, line: str) -> bool:
    try:  # a step check's pattern: the regex worker's deadline (server.safety.regex_worker), never plain re
        rx = safe_compile(pattern, re.MULTILINE)
        return any(rx.search(t) for t in (line, re.sub(r"\s+", " ", line)))
    except (re.error, TypeError):
        return False


def _line_of(pattern: str, text: str) -> int | None:
    try:
        m = safe_compile(pattern, re.MULTILINE).search(text)
    except (re.error, TypeError):
        return None
    return text.count("\n", 0, m.start()) + 1 if m else None


def _needs(items: list[dict]) -> str:
    needs = [n for it in items for n in it["needs"]]
    return ", ".join(needs[:2]) + (" …" if len(needs) > 2 else "")


def review(step: dict, results: list[dict], text: str | None, name: str, *, syntax: bool, whole: bool,
           shown: Container[str] = ()) -> tuple[list[dict], list[dict]]:
    """The step's rows made truthful on the file's exact `text` -> (results, failing code rows, syntax first).

    * a check row that passes on its pattern while the statement it matches lacks a piece of the step's code turns
      "fail" ("line 7 still needs params={"format": "j1"}"), always: its pattern was too loose to say "written";
    * syntax (the step would pass now / Check / the row was shown): the file must compile, else a fail row
      "<file> has no syntax errors" / "line 6: invalid syntax. Perhaps you forgot a comma?". Skipped for a step
      whose own code is a fragment (its file may not compile until the next step);
    * whole (same moments): statements no row claims add one row "All of this step's code in <file>".
    `shown`: row ids the app already has (a row shown failing turns green once fixed, never just disappears)."""
    sid = step.get("id", "")
    if text is None or step.get("setup"):
        return results, []
    code = python_code(step.get("code") or "")
    out = [dict(r) for r in results]
    bad: list[dict] = []
    defs = {c["id"]: c for c in (step.get("checks") or []) + (step.get("precision_checks") or [])
            if c.get("id") and c.get("type") in ("screen_contains", "file_contains")}  # rows about the code
    loose = []
    for item in missing_code(code, text) if code.strip() else []:
        claimed = False
        for i, r in enumerate(out):
            c = defs.get(r.get("checkId")) or {}
            if not c.get("pattern") or not _claims(c["pattern"], item["line"]):
                continue
            claimed = True
            if out[i].get("status") == "pass":
                n = _line_of(c["pattern"], text)
                out[i] = {**out[i], "status": "fail",
                          "detail": (f"line {n} still needs " if n else "still needs ") + _needs([item])}
                bad.append(out[i])
        if not claimed:
            loose.append(item)
    rows = []
    if syntax and self_contained(code) and name.endswith(".py"):
        cid = f"{sid}-syntax"
        err = syntax_problem(text, name)
        if err or cid in shown:
            row = {"checkId": cid, "label": f"{name} has no syntax errors", "file": name,
                   "status": "fail" if err else "pass",
                   "detail": f"line {err[0]}: {err[1]}" if err else "it compiles"}
            rows.append(row)
            if err:
                bad.insert(0, row)
    cid = f"{sid}-code"
    if (whole and loose) or (cid in shown):
        row = {"checkId": cid, "label": f"All of this step's code in {name}", "file": name,
               "status": "fail" if loose else "pass",
               "detail": f"still needs {_needs(loose)}" if loose else "all there"}
        rows.append(row)
        if loose and whole:
            bad.append(row)
        elif loose:
            row["status"] = "pending"  # shown before, not at a verdict moment: watching, never green
    return out + rows, bad


# ---------------------------------------------------------------------------------- "Not yet" card text (E19)

def whole_sentences(text: str, limit: int = 30) -> str:
    """Whole sentences, at most ~`limit` words; never a cut mid-sentence with "…". A first sentence longer than
    that ends at its last clause boundary (", " / "; ") inside the limit."""
    text = re.sub(r"[ \t]+", " ", (text or "").strip()).rstrip("…").strip()
    if len(text.split()) <= limit:
        return text
    parts = re.split(r"(?<=[.!?])\s+", text)
    keep: list[str] = []
    for p in parts:
        if len(" ".join(keep + [p]).split()) > limit:
            break
        keep.append(p)
    if keep:
        return " ".join(keep)
    words = parts[0].split()[:limit]
    cut = " ".join(words)
    m = re.search(r"^(.*\S)[,;:]\s", cut)
    head = m.group(1) if m and len(m.group(1).split()) >= 4 else cut
    return head.rstrip(",;:—- ") + "."


def with_command(text: str, cmd: str) -> str:
    """The step's exact command where the text names its script another way ("python main.py" -> "python3
    main.py" when the step says python3: this Mac may have only python3)."""
    m = _PY_RUN.search(cmd or "")
    if not m or not text:
        return text
    script = os.path.basename(m.group(1))
    return _PY_RUN.sub(lambda x: m.group(0) if os.path.basename(x.group(1)) == script else x.group(0), text)


def _period(s: str) -> str:
    s = s.strip()
    return s if not s or s[-1] in ".!?" else s + "."


_SHELL_CMD = re.compile(r"^\s*(\$\s*)?(python3?|pip3?|uv|npm|npx|node|yarn|pnpm|git|cd|ls|cargo|go|ruby|bash|sh|"
                        r"make|pytest|flask|streamlit|jupyter|source|\.)\s")  # as LessonSession.SHELL_CMD (+ source)
_RUN_VERB = re.compile(r"^(?:run|execute|press|hit|click)\b\s*", re.I)
_CELL_RUN = re.compile(r"shift\s*\+\s*enter|\bcells?\b|\bnotebook\b", re.I)


def ran_part(cmd: str, label: str, detail: str = "") -> str:
    """The "Ran it" row as a thing to do. A shell command: "run python3 app.py in the terminal". t11 (s5): a video
    build's run_command can be the action in words ("Run the cell (Shift+Enter)"): never "run Run the cell
    (Shift+Enter) in the terminal"; a notebook cell runs in the notebook."""
    cmd = (cmd or "").strip()
    m = _RUN_VERB.match(cmd)
    shell = bool(cmd) and bool(_SHELL_CMD.match((cmd[m.end():] if m else cmd) + " "))
    if not shell and _CELL_RUN.search(f"{cmd} {detail}"):
        return "run the cell (Shift+Enter)"
    if not cmd:
        return label
    if m and not shell:  # an action in words ("Click Run"): said as it is
        return cmd[0].lower() + cmd[1:]
    return f"run {cmd[m.end():] if m else cmd} in the terminal"


def not_yet_body(missing: str, rows: list[dict], *, sid: str, cmd: str = "", forced: bool = False) -> str:
    """The "Not yet" card body, from the failing rows the drawer shows (never the judge's free text when a row
    says what's left: "line 7 still needs ..." / the run), whole sentences, the step's exact command; a syntax
    error on its own line. Rows that only carry a label ("Requests.get call written", a finished fact) yield to
    the judge's own sentence when there is one. `missing`: the judge's text; `forced`: it is the engine's own
    (save / type / run), which then leads."""
    syntax = next((r for r in rows if r.get("checkId") == f"{sid}-syntax"), None)
    rest = [r for r in rows if r is not syntax]
    says = any(r.get("checkId") == f"{sid}-ran" or re.match(r"(?:line \d+ )?still needs ", str(r.get("detail") or ""))
               for r in rest)
    if forced and missing:
        main = missing
    elif rest and (says or not missing):
        parts = []
        for r in rest[:3]:
            label, detail = str(r.get("label") or r.get("checkId") or ""), str(r.get("detail") or "")
            needs = re.match(r"(?:line (\d+) )?still needs (.+)$", detail)
            if r.get("checkId") == f"{sid}-ran":
                parts.append(ran_part(cmd, label, detail))
            elif needs and r.get("checkId") == f"{sid}-code":
                parts.append(f"type {needs.group(2)} from the drawer")
            elif needs:
                parts.append(f"add {needs.group(2)}" + (f" on line {needs.group(1)}" if needs.group(1) else ""))
            else:
                parts.append(label)
        main = "Still to do: " + "; ".join(p for p in parts if p)
    elif syntax:
        main = f"Fix the syntax error in {syntax.get('file') or 'your file'}"
    else:
        main = missing or "The checks haven't passed yet"
    lines = [_period(with_command(whole_sentences(main), cmd))]
    if syntax:
        d = str(syntax.get("detail") or "")
        lines.append(_period(f"{syntax.get('file') or 'Your file'} {d}" if d.startswith("line ") else d))
    return "\n".join(x for x in lines if x)
