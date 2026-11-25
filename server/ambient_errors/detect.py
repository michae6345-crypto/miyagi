"""Spot errors in rows of screen text (ambient help, Nov 24: shared/contracts/AMBIENT-HELP.md section 1).

Pure Python, no I/O, no model, no network. `find_errors(rows, app=..., title=...)` reads the rows of one window (OCR
rows with their rects, or exact Accessibility rows without) and returns every error block it recognises:

  python_traceback   "Traceback (most recent call last):" ... "ModuleNotFoundError: No module named 'pandas'", and a
                     bare SyntaxError block ("File "x.py", line 3" ... "SyntaxError: ...")
  notebook_cell      the same in a notebook: "NameError    Traceback (most recent call last)" / "Cell In[4], line 1"
                     / "<ipython-input-4-...>", or any traceback in an .ipynb / Jupyter / Colab window
  js_error           "TypeError: ..." followed by "at f (file.js:12:5)" frames, "Error: Cannot find module 'x'",
                     a browser console's "Uncaught TypeError: ..."
  compiler           tsc ("src/a.ts(14,7): error TS2322: ..." and "src/a.ts:14:7 - error TS2322: ..."), gcc / clang
                     / javac ("a.c:3:5: error: ..."), rustc ("error[E0308]: ..." + "--> src/main.rs:4:18")
  shell_exit         pip ("ERROR: No matching distribution found for x", "error: externally-managed-environment"),
                     npm ("npm error code E404" / "npm ERR! ..."), git ("fatal: ...", "error: failed to push ...",
                     "! [rejected]", "CONFLICT (content): ..."), the shell's "command not found" and
                     "can't open file"

OCR loses indentation and sometimes quotes or a letter, so every pattern is anchored on words, not on columns, and
the id a watcher derives from a block (`key()`) ignores case, quotes and punctuation. Which rows of a window are read
at all (a terminal, VS Code's terminal panel, a notebook) is the caller's choice (watcher.rows_to_read).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

try:  # the contract's limit on error.seen.lines
    from shared.contracts.events import AMBIENT_ERROR_LINES_MAX
except Exception:  # pragma: no cover - the contract always ships with the engine
    AMBIENT_ERROR_LINES_MAX = 8

TITLE_MAX = 80  # error.seen.title: at most 80 characters
SCAN_MAX = 40  # rows read after a block's first row before it is closed regardless


@dataclass
class Row:
    """One visual row: its text and, from OCR, where it is (screen points, top-left; None for Accessibility rows)."""

    text: str
    rect: Any = None  # server.screen.types.Rect | None


@dataclass
class Found:
    """One error block. `rows` are the block's own rows (all of them, for the rect); `lines` the first
    AMBIENT_ERROR_LINES_MAX as read. `command`: the shell command typed before it, when a prompt row is above it
    (kept on this Mac; Explain sends it redacted as context)."""

    kind: str
    title: str
    rows: list[Row] = field(default_factory=list)
    file: str | None = None
    line: int | None = None
    col: int | None = None
    lang: str | None = None
    command: str | None = None
    exit_code: int | None = None
    module: str | None = None  # python_traceback: the module a ModuleNotFoundError names; js_error: the package
    copies: int = 1  # how many times one frame shows this error (a re-run prints it again)

    @property
    def lines(self) -> list[str]:
        return [r.text for r in self.rows][:AMBIENT_ERROR_LINES_MAX]

    def rect(self) -> Any:
        """The union of the block's row rects (None when no row has one)."""
        out = None
        for r in self.rows:
            if r.rect is None:
                continue
            out = r.rect if out is None else out.union(r.rect)
        return out

    def key(self, app: str) -> str:
        """Stable for the same app + kind + title + file:line, with OCR noise (case, quotes, punctuation, a path's
        folders) taken out, so the same error read twice is one id."""
        base = (self.file or "").replace("\\", "/").rsplit("/", 1)[-1]
        raw = "|".join([_norm(app), self.kind, _norm(self.title), _norm(base), str(self.line or "")])
        return "err-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _clean(text: str) -> str:
    # OCR's typographic quotes and stray spacing, so the patterns below see one spelling
    t = (text or "").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return t.rstrip()


def _title(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= TITLE_MAX else t[: TITLE_MAX - 1].rstrip() + "…"


# ---------------------------------------------------------------- shared patterns
# "rror" not "Error": OCR reads NameError as "NameFrror" now and then
_EXC_NAME = r"(?:[A-Za-z_][\w]*\.)*(?:[A-Z]\w*(?:rror|Exception|Exit|Interrupt|Warning)|Exception|KeyboardInterrupt|StopIteration)"
PY_ERROR_LINE = re.compile(rf"^\s*(?P<name>{_EXC_NAME})(?::\s*(?P<msg>.*))?$")
PY_TB_HEAD = re.compile(r"Traceback\s*\(most\s+recent\s+call\s+last\)", re.I)
PY_FRAME = re.compile(r"""File\s+["']?(?P<file>[^"',]+?)["']?\s*,\s*line\s+(?P<line>\d+)""")
NB_HEAD = re.compile(rf"^\s*(?P<name>{_EXC_NAME})\s+Traceback\s*\(most\s+recent\s+call\s+last\)", re.I)
NB_CELL = re.compile(r"(?:Cell\s+In\s*\[\s*(?P<cell>\d*)\s*\]\s*,\s*line\s+(?P<line>\d+)|"
                     r"<ipython-input-(?P<cell2>\d+)-[0-9a-f]+>|Input\s+In\s*\[\s*(?P<cell3>\d*)\s*\])", re.I)
NB_ARROW = re.compile(r"^\s*-+>\s*(?P<line>\d+)\b")
NO_MODULE = re.compile(r"No module named\s+['\"`]?(?P<mod>[A-Za-z_][\w.]*)")

JS_ERROR_LINE = re.compile(r"^\s*(?:Uncaught\s+(?:\(in promise\)\s+)?)?(?P<name>(?:[A-Z]\w*)?Error)(?:\s*\[(?P<code>[A-Z0-9_]+)\])?:\s*(?P<msg>.+)$")
JS_UNCAUGHT = re.compile(r"^\s*Uncaught\s+(?:\(in promise\)\s+)?(?:[A-Z]\w*)?Error\b")
JS_FRAME = re.compile(r"^\s*at\s+(?:.+?\s+\()?(?P<file>(?:file://)?[^\s()]+?):(?P<line>\d+):(?P<col>\d+)\)?\s*$")
JS_HEAD = re.compile(r"^\s*(?P<file>(?:/|~/|\./|[A-Za-z]:\\|node:)[^\s:]+\.[cm]?[jt]sx?|node:internal/[\w/]+):(?P<line>\d+)\s*$")
JS_NO_MODULE = re.compile(r"Cannot find (?:module|package)\s+['\"`](?P<mod>[^'\"`]+)['\"`]")

TSC_PAREN = re.compile(r"^\s*(?P<file>[^\s()]+\.(?:[cm]?tsx?|vue|svelte))\((?P<line>\d+),(?P<col>\d+)\):\s*error\s+(?P<code>TS\d+):\s*(?P<msg>.+)$")
TSC_PRETTY = re.compile(r"^\s*(?P<file>[^\s:]+\.(?:[cm]?tsx?|vue|svelte)):(?P<line>\d+):(?P<col>\d+)\s*-\s*error\s+(?P<code>TS\d+):\s*(?P<msg>.+)$")
CC_ERROR = re.compile(r"^\s*(?P<file>[^\s:]+\.(?:c|cc|cpp|cxx|h|hpp|m|mm|java|go|swift|kt|cs|zig)):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?:fatal\s+)?error:\s*(?P<msg>.+)$")
RUST_ERROR = re.compile(r"^\s*error(?:\[(?P<code>E\d{4})\])?:\s*(?P<msg>.+)$")
RUST_AT = re.compile(r"^\s*-->\s*(?P<file>[^\s:]+):(?P<line>\d+):(?P<col>\d+)")
TSC_SUMMARY = re.compile(r"^\s*Found\s+\d+\s+errors?\b", re.I)

# Case matters: pip shouts "ERROR:", git and the shell say "error:" / "fatal:", JavaScript's "Error:" is not theirs
PIP_ERROR = re.compile(r"^\s*(?:ERROR:\s*\S|error:\s*(?:externally-managed-environment|subprocess-exited-with-error|"
                       r"metadata-generation-failed|legacy-install-failure))")
NPM_ERROR = re.compile(r"^\s*npm\s+(?:ERR!|error)\s*(?P<msg>.*)$")
GIT_ERROR = re.compile(r"^\s*(?:fatal:\s*\S|error:\s*\S|!\s*\S{0,2}(?:rejected|remote rejected)\]|CONFLICT\s*\(|"
                       r"Automatic merge failed)")
SHELL_ERROR = re.compile(r"^\s*(?:(?:zsh|bash|sh|fish):\s*(?:command not found:|permission denied:|no such file or "
                         r"directory:)|(?:zsh|bash|sh):\s*\S+:\s*command not found|\S+:\s*command not found\s*$|"
                         r"\S*python3?(?:\.\d+)?:\s*can't open file)", re.I)
SHELL_FOLLOW = re.compile(r"^\s*(?:hint:|error:|fatal:|ERROR:|npm\s+(?:ERR!|error)|note:|╰─>|×|\|)")
EXIT_CODE = re.compile(r"(?:exit(?:ed)?\s+(?:with\s+)?(?:code|status)\s*|exit code:\s*)(?P<code>\d{1,3})\b", re.I)

# a shell prompt with the command after it: "$ python3 app.py", "% git push", "❯ npm i", "➜ api git:(main) npm i",
# "sam@mac weather-app % python3 app.py", "(.venv) $ pip install x"
PROMPT = re.compile(r"^\s*(?:\([^)]{1,40}\)\s*)?(?:[\w.\-]+@[\w.\-]+(?:[:\s][^$%#❯>]{0,60})?\s*)?"
                    r"(?:➜\s+\S+(?:\s+git:\([^)]*\))?(?:\s*✗)?|[$%#❯>»λ])\s+(?P<cmd>\S.{0,300})$")


def _int(v: Any) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _lib_path(path: str) -> bool:
    p = (path or "").replace("\\", "/")
    return any(s in p for s in ("site-packages/", "dist-packages/", "/lib/python", "<frozen", "node_modules/",
                                "node:internal", "/usr/lib/", "/Library/Frameworks/"))


def _strip_file_url(path: str) -> str:
    return path[7:] if path.startswith("file://") else path


# ---------------------------------------------------------------- python
def _python(rows: list[Row], i: int, notebook: bool) -> tuple[Found, int, int] | None:
    """A traceback whose header is row i, or None. -> (block, its first row, the row after it). A chained traceback
    ("During handling of the above exception, another exception occurred:") is one block ending on the last error."""
    text = _clean(rows[i].text)
    nb_head = NB_HEAD.search(text)
    if not (nb_head or PY_TB_HEAD.search(text)):
        return None
    kind = "notebook_cell" if (nb_head or notebook) else "python_traceback"
    frames: list[tuple[str, int]] = []
    cell_line: int | None = None
    end = None
    j = i + 1
    while j < len(rows) and j <= i + SCAN_MAX:
        t = _clean(rows[j].text)
        if m := PY_FRAME.search(t):
            frames.append((m.group("file").strip(), int(m.group("line"))))
        if m := NB_CELL.search(t):
            kind = "notebook_cell"
            cell_line = _int(m.group("line")) or cell_line
        if (m := NB_ARROW.match(t)) and cell_line is None:
            cell_line = _int(m.group("line"))
        m = PY_ERROR_LINE.match(t)
        if m and m.group("msg") is not None and not NB_HEAD.search(t):
            end = j
            nxt = next((k for k in range(j + 1, min(len(rows), j + 4))
                        if re.search(r"During handling of the above exception|above exception was the direct cause",
                                     _clean(rows[k].text), re.I)), None)
            if nxt is None:
                break
            j = nxt  # a chained traceback: read on to its last error
        j += 1
    if end is None:
        return None
    last = _clean(rows[end].text).strip()
    f = Found(kind=kind, title=_title(last), rows=rows[i:end + 1], lang="python")
    user = [fr for fr in frames if not _lib_path(fr[0])]
    pick = (user or frames or [None])[-1]
    if kind == "notebook_cell":
        f.line = cell_line if cell_line is not None else (pick[1] if pick else None)
    elif pick:
        f.file, f.line = pick
    if m := NO_MODULE.search(last):
        f.module = m.group("mod").split(".")[0]
    return f, i, end + 1


def _syntax_error(rows: list[Row], i: int) -> tuple[Found, int, int] | None:
    """`File "x.py", line 3` + the code + `^` + `SyntaxError: ...` with no traceback header (a file that never ran)."""
    m = PY_FRAME.search(_clean(rows[i].text))
    if not m:
        return None
    for j in range(i + 1, min(len(rows), i + 5)):
        t = _clean(rows[j].text).strip()
        e = PY_ERROR_LINE.match(t)
        if e and e.group("msg") is not None and re.search(r"(Syntax|Indentation|Tab)Error", e.group("name")):
            f = Found(kind="python_traceback", title=_title(t), rows=rows[i:j + 1], file=m.group("file").strip(),
                      line=int(m.group("line")), lang="python")
            return f, i, j + 1
    return None


# ---------------------------------------------------------------- javascript
def _js(rows: list[Row], i: int) -> tuple[Found, int, int] | None:
    t = _clean(rows[i].text)
    m = JS_ERROR_LINE.match(t)
    if not m:
        return None
    uncaught = bool(JS_UNCAUGHT.match(t))
    frames: list[tuple[str, int, int]] = []
    j = i + 1
    while j < len(rows) and j <= i + SCAN_MAX:
        fm = JS_FRAME.match(_clean(rows[j].text))
        if fm:
            frames.append((_strip_file_url(fm.group("file")), int(fm.group("line")), int(fm.group("col"))))
            j += 1
            continue
        if re.match(r"^\s*(?:\{|\}|code:|requireStack|Require stack:|- [/~.]|\[|'|\"|Node\.js\s+v)",
                    _clean(rows[j].text)) and j - i <= 12:
            j += 1  # the error object's own fields, node's require stack and version line belong to the block
            continue
        break
    if not frames and not uncaught:
        return None
    start = i
    head_file = head_line = None
    for k in range(max(0, i - 6), i):  # node prints "/path/file.js:12" + the code + "^" above the error
        hm = JS_HEAD.match(_clean(rows[k].text))
        if hm:
            start, head_file, head_line = k, hm.group("file"), int(hm.group("line"))
            break
    f = Found(kind="js_error", title=_title(re.sub(r"^\s*Uncaught\s+(?:\(in promise\)\s+)?", "", t)),
              rows=rows[start:j], lang="javascript")
    user = [fr for fr in frames if not _lib_path(fr[0])]
    if user:
        f.file, f.line, f.col = user[0]
    elif head_file and not _lib_path(head_file):
        f.file, f.line = head_file, head_line
    elif frames:
        f.file, f.line, f.col = frames[0]
    if f.file and re.search(r"\.[cm]?tsx?$", f.file):
        f.lang = "typescript"
    if nm := JS_NO_MODULE.search(t):
        f.module = nm.group("mod")
    return f, start, j


# ---------------------------------------------------------------- compilers
def _compiler(rows: list[Row], i: int) -> tuple[Found, int, int] | None:
    t = _clean(rows[i].text)
    m = TSC_PRETTY.match(t) or TSC_PAREN.match(t)
    lang = "typescript"
    if m:
        title = f"error {m.group('code')}: {m.group('msg').strip()}"
    elif m := CC_ERROR.match(t):
        title = f"error: {m.group('msg').strip()}"
        ext = m.group("file").rsplit(".", 1)[-1].lower()
        lang = {"java": "java", "go": "go", "swift": "swift", "kt": "kotlin", "cs": "csharp", "zig": "zig",
                "m": "objective-c", "mm": "objective-c"}.get(ext, "c" if ext in ("c", "h") else "cpp")
    elif RUST_ERROR.match(t):
        at = next(((k, am) for k in range(i + 1, min(len(rows), i + 4))
                   if (am := RUST_AT.match(_clean(rows[k].text)))), None)
        if at is None:
            return None
        k, am = at
        end = _block_end(rows, k + 1)
        f = Found(kind="compiler", title=_title(t.strip()), rows=rows[i:end], file=am.group("file"),
                  line=int(am.group("line")), col=int(am.group("col")), lang="rust")
        return f, i, end
    else:
        return None
    end = _block_end(rows, i + 1, stop=lambda s: bool(TSC_PRETTY.match(s) or TSC_PAREN.match(s) or CC_ERROR.match(s)))
    f = Found(kind="compiler", title=_title(title), rows=rows[i:end], file=m.group("file"), line=int(m.group("line")),
              col=_int(m.groupdict().get("col")), lang=lang)
    # tsc's summary ("Found 3 errors in 2 files.") a few rows on belongs to the block
    for k in range(end, min(len(rows), end + 12)):
        if TSC_SUMMARY.match(_clean(rows[k].text)):
            f.rows = rows[i:k + 1]
            end = k + 1
            break
    return f, i, end


def _block_end(rows: list[Row], j: int, stop: Any = None, limit: int = 8) -> int:
    """The row after a compiler message's code frame: the next blank row, prompt or next error, at most `limit` on."""
    k = j
    while k < len(rows) and k < j + limit:
        s = _clean(rows[k].text)
        if not s.strip() or PROMPT.match(s) or (stop is not None and stop(s)) or TSC_SUMMARY.match(s):
            break
        k += 1
    return k


# ---------------------------------------------------------------- shell commands (pip, npm, git, the shell itself)
def _shell(rows: list[Row], i: int) -> tuple[Found, int, int] | None:
    t = _clean(rows[i].text)
    tool = None
    if NPM_ERROR.match(t):
        tool = "npm"
    elif PIP_ERROR.match(t):
        tool = "pip"
    elif GIT_ERROR.match(t):
        tool = "git"
    elif SHELL_ERROR.match(t):
        tool = "shell"
    if tool is None:
        return None
    def follows(s: str) -> bool:
        return bool(SHELL_FOLLOW.match(s) or PIP_ERROR.match(s) or GIT_ERROR.match(s))

    j = i + 1
    while j < len(rows) and j <= i + SCAN_MAX and tool != "shell":
        s = _clean(rows[j].text)
        if PROMPT.match(s) or not s.strip():
            break
        if tool == "npm" and not NPM_ERROR.match(s):
            break
        if tool in ("pip", "git") and not follows(s):
            # one or two rows of the same output between error rows ("main -> main (fetch first)", a wrapped line)
            nxt = [_clean(r.text) for r in rows[j + 1:j + 3]]
            if not any(follows(x) and not PROMPT.match(x) for x in nxt):
                break
        j += 1
    block = rows[i:j]
    texts = [_clean(r.text).strip() for r in block]
    if tool == "npm":
        title = _npm_title(texts)
    elif tool == "pip" and (errs := [x for x in texts if x.startswith("ERROR:")]):
        title = errs[-1]  # pip's last ERROR line says what failed ("No matching distribution found for x")
    elif errs := [x for x in texts if re.match(r"^(?:fatal:|error:|CONFLICT)", x)]:
        title = errs[0]
    else:
        title = texts[0]
    f = Found(kind="shell_exit", title=_title(title), rows=block, lang="shell")
    for x in texts:
        if em := EXIT_CODE.search(x):
            f.exit_code = int(em.group("code"))
    if tool == "npm" and (nm := re.search(r"(?:'|\")(?P<pkg>@?[\w.\-/]+)@[^'\"]*(?:'|\") is not in this registry", " ".join(texts))):
        f.module = nm.group("pkg")
    start = i
    if tool == "git" and i > 0 and re.match(r"^\s*To\s+\S+", _clean(rows[i - 1].text)):
        start = i - 1  # "To github.com:sam/api.git" above "! [rejected]"
        f.rows = rows[start:j]
    return f, start, j


def _npm_title(texts: list[str]) -> str:
    """npm's useful line ("'reactt@*' is not in this registry."), with its code: never `code E404`, `errno`, the log
    path, a bare `404` or the "Note that you can also install from a tarball" advice."""
    code = None
    msgs: list[str] = []
    for x in texts:
        m = NPM_ERROR.match(x)
        msg = (m.group("msg") if m else x).strip()
        if cm := re.match(r"^code\s+(\S+)", msg):
            code = cm.group(1)
            continue
        msg = re.sub(r"^\d{3}\b\s*", "", msg).strip()  # npm's HTTP status prefix ("404 Not Found - GET ...")
        if not msg or re.match(r"^(?:errno\b|syscall\b|path\b|A complete log|Log files|Note that|tarball|"
                               r"\d{4}-\d\d-\d\dT|/)", msg, re.I):
            continue
        msgs.append(msg)
    best = next((m for m in msgs if re.search(r"not in this registry|could not resolve|Missing script|ERESOLVE|"
                                              r"ENOENT|EACCES|Unsupported|conflicting", m, re.I)), None)
    head = best or (msgs[0] if msgs else "npm failed")
    return f"npm error {code}: {head}" if code and code not in head else f"npm error: {head}"


# ---------------------------------------------------------------- the command before a failed one
def command_before(rows: list[Row], start: int, look: int = 40) -> str | None:
    """The command typed at the nearest shell prompt above row `start` (None without one)."""
    for k in range(start - 1, max(-1, start - 1 - look), -1):
        m = PROMPT.match(_clean(rows[k].text))
        if m:
            cmd = m.group("cmd").strip()
            return cmd[:300] if cmd else None
    return None


# ---------------------------------------------------------------- entry point
def find_errors(rows: list[Row], *, notebook: bool = False, browser: bool = False) -> list[Found]:
    """Every error block in one window's rows, top to bottom. `notebook`: the window shows a notebook (a traceback
    there is a cell's error). `browser`: only notebook tracebacks and the console's `Uncaught ...` count (a web page's
    own text is never read as a terminal)."""
    out: list[Found] = []
    i = 0
    n = len(rows)
    while i < n:
        got = _python(rows, i, notebook)
        if got is None and not browser:
            got = _syntax_error(rows, i) or _compiler(rows, i) or _shell(rows, i)
        if got is None and (not browser or JS_UNCAUGHT.match(_clean(rows[i].text))):
            got = _js(rows, i)
        if got is None or (browser and got[0].kind not in ("notebook_cell", "js_error")):
            i += 1
            continue
        found, start, nxt = got
        if found.kind != "notebook_cell":
            found.command = command_before(rows, start)
        out.append(found)
        i = max(nxt, i + 1)
    return out
