"""Step check evaluator: ``evaluate_step(step, ctx) -> list[CheckResult]``.

Pure function: it reads the workdir and the run context it is given and never
calls the network, the DB or a model. The orchestrator builds the ``RunContext``
from ``tut run`` events (``/ingest``) and calls this on file saves and run ends.

Status semantics (``CheckStatus`` in ``shared/contracts/events.ts``):

* ``pass``    the check is satisfied.
* ``fail``    the check is definitely not satisfied right now (file missing,
              regex absent, run exited non-zero, loss curve flat, threshold
              missed by ``by_step``...). The orchestrator's don't-nag gate decides
              when a fail becomes an ``offtrack`` card.
* ``pending`` not enough evidence yet (no run, still collecting points, visual
              verdict not supplied).
"""
from __future__ import annotations

import ast
import bisect
import dataclasses
import json
import math
import os
import re
import shlex
import statistics
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from server.safety import regex_worker
from server.safety.patterns import MAX_PATTERN_LEN, pattern_problem, safe_compile  # noqa: F401 - re-exported

from . import blocks, code_equiv, model_files
from .code_text import code_view, lang_of, signatures, strip_comments
from .notebook import Notebook, find_notebook, read_notebook
from .screen import extract_metrics, screen_lines, screen_text, search_screen, search_wrapped

CheckStatus = Literal["pending", "pass", "fail"]


class CheckResult(TypedDict):
    checkId: str
    label: str
    status: CheckStatus
    detail: str


@dataclass
class RunContext:
    """Everything a check may look at.

    ``metrics`` maps a metric name to ``[(step, value), ...]`` in arrival order
    (the evaluator sorts by step itself). ``output_tail`` is the last lines of the
    most recent run (str or list of lines). ``exit_code`` is None while running or
    before any run. ``visual`` holds verdicts the orchestrator obtained from a
    vision model: ``{check_id: {"pass": bool, "detail": str}}``.

    Screen-first: ``screen`` is the latest ScreenObservation from ``server.screen``
    (dict or object, or ``{app: [lines]}``; see ``screen.py``). Metrics read off
    the screen by E6 should be merged into ``metrics`` by the orchestrator; when a
    metric check has a ``metric_pattern`` and ``metrics`` has nothing for it, the
    evaluator parses the visible terminal text (and the run output) itself.
    """

    workdir: str = "."
    exit_code: int | None = None
    output_tail: list[str] | str = field(default_factory=list)
    metrics: dict[str, list[tuple[int, float]]] = field(default_factory=dict)
    command: str | None = None
    running: bool = False
    visual: dict[str, dict[str, Any]] = field(default_factory=dict)
    screen: Any = None
    # True once the step's video segment has played (the learner has been told what to do).
    # None = the orchestrator doesn't say: treated as done, so a hidden app never leaves a
    # check pending forever. See _not_visible().
    segment_done: bool | None = None
    # The lesson's editor app ("Code" in a "Just teach me" VS Code lesson), else None. Its terminal is then the
    # learner's terminal: the details say "VS Code's terminal", never Terminal.app.
    editor: str | None = None
    # t9: the learner's notebook (server.checks.notebook.Notebook) on a notebook step; evaluate_step reads it from
    # the lesson folder when the orchestrator doesn't hand one in. False: none (looked, nothing there). t10:
    # evaluate_step narrows it to the step's own cells (Notebook.only): outputs / errors / ran are those cells' only.
    notebook: Any = None
    # When the step (else the lesson) began, epoch seconds, when the orchestrator knows: a file whose mtime is older
    # was there before the step, so it is never the file the step saved under a name of its own (_claim_any_names).
    step_started_at: float | None = None
    lesson_started_at: float | None = None

    @property
    def after_segment(self) -> bool:
        return self.segment_done is not False

    @property
    def has_run(self) -> bool:
        return self.running or self.exit_code is not None or self.command is not None

    @property
    def run_finished(self) -> bool:
        return not self.running and self.exit_code is not None

    def add_metric(self, name: str, step: int, value: float) -> None:
        self.metrics.setdefault(name, []).append((int(step), float(value)))

    def output_text(self) -> str:
        if isinstance(self.output_tail, str):
            return self.output_tail
        return "\n".join(self.output_tail)


# ---------------------------------------------------------------- tunables
# metric_threshold: compare the median of the last N points (<= by_step) so a single
# noisy minibatch can neither pass nor fail the check.
THRESHOLD_SMOOTH_POINTS = 5

# metric_trend: see _metric_trend() for the full test. A trend passes only when it is BOTH
# statistically significant (Mann-Kendall) AND big enough to matter (Theil-Sen effect size).
TREND_MIN_POINTS = 8           # need at least this many finite points in the window
TREND_MIN_COVERAGE = 0.5       # ...spanning at least half of `window` steps
NOT_FLAT_MIN_REL_CHANGE = 0.05  # |relative change| over the window must be >= 5%
DECREASING_MIN_REL_DROP = 0.02  # "decreasing" needs >= 2% robust drop
MK_Z_TWO_SIDED = 2.576         # not_flat: Mann-Kendall p < 0.01 (two-sided)
MK_Z_ONE_SIDED = 2.326         # decreasing: Mann-Kendall p < 0.01 (one-sided, downward)
DEFAULT_TREND_WINDOW = 1000
MAX_TS_POINTS = 200            # Theil-Sen / Mann-Kendall are O(n^2); thin longer windows

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def _result(check: dict, status: CheckStatus, detail: str) -> CheckResult:
    return {
        "checkId": str(check.get("id", "")),
        "label": str(check.get("label", check.get("id", ""))),
        "status": status,
        "detail": detail,
    }


def _fmt(v: float) -> str:
    """A value the way a training script prints it: plain decimals (test 8: 0.0009, never 9.00e-04)."""
    if v == 0 or not math.isfinite(v) or 1e-3 <= abs(v) < 1e4:
        return f"{v:.4g}"
    if abs(v) >= 1e4:
        return f"{v:.0f}"
    digits = 3 - math.floor(math.log10(abs(v)))  # 4 significant digits, no exponent
    return f"{v:.{digits}f}".rstrip("0").rstrip(".")


def _resolve(workdir: str, rel: str) -> str:
    """workdir/rel when it stays in the lesson folder (server.safety.paths: relative, no `..` / `~`, symlinks
    followed), else "": a lesson's check never reads ~/.aws/credentials or ../../.ssh/id_rsa."""
    from server.safety.paths import safe_lesson_path

    if not rel or os.path.isabs(rel) or safe_lesson_path(workdir or ".", rel) is None:
        return ""
    return os.path.normpath(os.path.join(workdir, rel))


def _compile(pattern: str) -> re.Pattern[str]:
    return safe_compile(pattern, re.MULTILINE)  # re.error for a refused (catastrophic / too long) pattern


# ---------------------------------------------------------------- regex safety (ReDoS)
# A lesson's patterns come from a model (or a stored / shared lesson) and run on every screen frame and file save.
# server.safety.patterns refuses a catastrophic shape before it runs (no `regex` module, so no timeout), and the text
# a pattern scans is capped here, which bounds what an accepted pattern can cost.
SCREEN_SCAN_CHARS = 4096  # a screen pattern sees at most the last 4 KB of a window's text
FILE_SCAN_CHARS = 64 * 1024  # one search: a run output's last 64 KB, a file in 64 KB windows (scan_windows)
LINE_SCAN_CHARS = 2048  # and no line longer than 2 KB (a notebook's base64 image, a minified bundle)


LINE_OVERLAP_CHARS = 256  # a long line is split into 2 KB pieces that overlap this much (a match across a split)


@dataclass(frozen=True)
class Scan:
    """Text as a lesson pattern may search it (scan()), and how to map a match back to the original line."""
    text: str
    dropped_lines: int = 0  # whole lines cut from the top (only the last `limit` characters are kept)
    breaks: tuple[int, ...] = ()  # offsets in `text` of the newlines scan() inserted to split long lines

    def line_of(self, pos: int) -> int:
        """The 1-based line, in the original text, of offset `pos` in `text`."""
        inserted = bisect.bisect_left(self.breaks, pos)
        return self.dropped_lines + self.text.count("\n", 0, pos) - inserted + 1


def scan(text: str | None, limit: int = FILE_SCAN_CHARS) -> Scan:
    """`text` as a lesson pattern may search it: its last `limit` characters (cut at a line start), with every line
    longer than LINE_SCAN_CHARS split into overlapping pieces (one-line JSON notebooks, minified bundles, base64), so
    no pattern ever scans more than 64 KB or a line over 2 KB."""
    if not text:
        return Scan("")
    dropped = 0
    if len(text) > limit:
        tail = text[-limit:]
        cut = tail.find("\n")
        if 0 <= cut < len(tail) - 1:
            tail = tail[cut + 1:]
        dropped = text.count("\n", 0, len(text) - len(tail))
        text = tail
    if len(text) <= LINE_SCAN_CHARS or not any(len(ln) > LINE_SCAN_CHARS for ln in text.split("\n")):
        return Scan(text, dropped)
    out: list[str] = []
    breaks: list[int] = []
    pos = 0
    step = LINE_SCAN_CHARS - LINE_OVERLAP_CHARS
    for k, ln in enumerate(text.split("\n")):
        if k:
            out.append("\n")
            pos += 1
        pieces = [ln[i:i + LINE_SCAN_CHARS] for i in range(0, max(len(ln) - LINE_OVERLAP_CHARS, 1), step)] or [""]
        for j, piece in enumerate(pieces):
            if j:
                breaks.append(pos)
                out.append("\n")
                pos += 1
            out.append(piece)
            pos += len(piece)
    return Scan("".join(out), dropped, tuple(breaks))


def scan_text(text: str | None, limit: int = FILE_SCAN_CHARS) -> str:
    """scan(text, limit).text: what a lesson pattern may search."""
    return scan(text, limit).text


FILE_SCAN_TOTAL = 1024 * 1024  # a larger file: overlapping FILE_SCAN_CHARS windows, newest first, up to this much
WINDOW_OVERLAP_CHARS = 4096  # how much two neighbouring windows share (a match across their boundary)
NOTEBOOK_OUTPUT_CHARS = 4096  # a big notebook: each output's printed text keeps its last 4 KB (3000 epoch lines)


def scan_windows(text: str | None, limit: int = FILE_SCAN_CHARS,
                 total: int = FILE_SCAN_TOTAL) -> Iterator[tuple[int, Scan]]:
    """`text` as lesson-pattern-sized pieces: (offset in `text`, scan() of the piece). One piece when it fits in
    `limit`; else windows of `limit` characters from the end backwards (each starting at a line start when one is
    near), overlapping by WINDOW_OVERLAP_CHARS, until `total` characters are covered. Each window is what one search
    may cost, so a big file costs a few searches instead of hiding everything above its last 64 KB."""
    if not text or len(text) <= limit:
        yield 0, scan(text, limit)
        return
    end, covered, overlap = len(text), 0, min(WINDOW_OVERLAP_CHARS, limit // 4)
    while end > 0 and covered < total:
        start = max(0, end - limit)
        if start:
            cut = text.find("\n", start, end)
            if 0 <= cut - start < limit // 2:  # start at the next line (never drop more than half the window)
                start = cut + 1
        yield start, scan(text[start:end], limit)
        covered += end - start
        if start == 0:
            break
        end = start + overlap


def _search_file(rx: Any, text: str, accept: Any = None) -> tuple[Any, int] | None:
    """(the first match, its 1-based line in `text`) over scan_windows(text), newest window first; None. With
    ``accept(line, matched_text)``, the first match it accepts."""
    for off, sc in scan_windows(text):
        for m in rx.finditer(sc.text) if accept is not None else filter(None, [rx.search(sc.text)]):
            line = text.count("\n", 0, off) + sc.line_of(m.start())
            if accept is None or accept(line, m.group(0)):
                return m, line
    return None


def read_for_scan(path: str | os.PathLike) -> str:
    """A lesson file's text for its checks. A big notebook (over FILE_SCAN_CHARS) is written out again as two parts:
    first every cell's printed output, without image / binary payloads (base64 PNGs are most of an .ipynb and never
    what a pattern looks for) and each output's text cut to its last NOTEBOOK_OUTPUT_CHARS, then the notebook with
    its cells' code whole and their outputs left out. scan_windows reads from the end (newest first), so the code is
    always searched before any output, and a check on code never depends on how much output the notebook keeps (200
    cells of df.head() tables are over FILE_SCAN_TOTAL). OSError as open() raises it."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if not os.fspath(path).lower().endswith(".ipynb") or len(text) <= FILE_SCAN_CHARS:
        return text
    try:
        nb = json.loads(text)
    except ValueError:
        return text
    if not isinstance(nb, dict):
        return text
    outputs = []
    for i, cell in enumerate(nb.get("cells") or []):
        if not isinstance(cell, dict) or not isinstance(cell.get("outputs"), list):
            continue
        outs = cell.pop("outputs")
        for out in outs:
            if not isinstance(out, dict):
                continue
            if "text" in out:  # a stream output (print, a progress log)
                out["text"] = _tail_text(out["text"])
            data = out.get("data")
            if isinstance(data, dict):
                for k in list(data):
                    data[k] = _tail_text(data[k]) if str(k).startswith("text/") else ""
        if outs:
            outputs.append({"cell": i, "outputs": outs})
        cell["outputs"] = []
    code = json.dumps(nb, indent=1, ensure_ascii=False)
    if not outputs:
        return code
    return json.dumps({"outputs": outputs}, indent=1, ensure_ascii=False) + "\n" + code


def _tail_text(v: Any) -> Any:
    """A notebook output's text (a string or a list of lines) cut to its last NOTEBOOK_OUTPUT_CHARS, whole lines."""
    s = "".join(str(x) for x in v) if isinstance(v, list) else v if isinstance(v, str) else ""
    if len(s) <= NOTEBOOK_OUTPUT_CHARS:
        return v
    tail = s[-NOTEBOOK_OUTPUT_CHARS:]
    tail = tail[tail.find("\n") + 1:] if "\n" in tail[:-1] else tail
    return tail.splitlines(keepends=True) if isinstance(v, list) else tail


def unsafe_patterns(check: dict) -> str | None:
    """Why one of a check's regexes (pattern, metric_pattern) may not run, else None."""
    for key in ("pattern", "metric_pattern"):
        p = check.get(key)
        if p is not None and (why := pattern_problem(p)) is not None:
            return f"{key}: {why}"
    return None


# ---------------------------------------------------------------- per type
def _learner_file(name: str, ctx: RunContext) -> str:
    """The file name a detail should say: the video's ``Untitled.ipynb`` is the learner's own notebook (``mnist.ipynb``),
    so name that one when it exists."""
    if not name.lower().endswith(".ipynb"):
        return name
    if isinstance(ctx.notebook, Notebook):
        return ctx.notebook.path.name
    if os.path.isabs(str(ctx.workdir or "")) and (found := find_notebook(ctx.workdir, [name])) is not None:
        return found.name
    return name


def _file_exists(check: dict, ctx: RunContext) -> CheckResult:
    rel = check.get("file")
    if not rel:
        return _result(check, "fail", "check has no 'file'")
    if not _resolve(ctx.workdir, rel):
        return _result(check, "fail", f"{rel} is outside the lesson folder")
    path = _resolve(ctx.workdir, rel)
    if os.path.exists(path):
        # an export with nothing in it, or an open shell where the step prints it, is not the model saved
        if why := model_files.empty_mesh(path) or (check.get("_print") and model_files.open_mesh(path)):
            return _result(check, "fail", why)
        return _result(check, "pass", f"{rel} exists")
    if isinstance(other := check.get("_any_name"), str) and os.path.isfile(os.path.join(os.path.dirname(path), other)):
        # the step never named the file ("save it as a PNG next to mug.blend"): Blender's untitled.png is that PNG
        return _result(check, "pass", f"{other} saved (any name will do)")
    return _result(check, "fail", f"{rel} not found")


# What an app writes out under a name of its own (a render, an export, a plot saved from a viewer): the only kinds of
# file a step may leave unnamed. Never code, a notebook, a project or a text file: "a new Python file for the math
# helpers" is the operations.py the lesson goes on to import, and main.py beside it is not that file.
EXPORT_EXTS = frozenset(""".png .jpg .jpeg .webp .tif .tiff .bmp .gif .exr .hdr .pdf .mp4 .mov .webm .mkv .avi
.stl .obj .3mf .ply .fbx .glb .gltf .dae .usd .usdz .abc .step .stp .iges .igs .sat .dwg .dxf .dwf .gcode .bgcode
.gco""".split())


def _name_words(name: str) -> set[str]:
    """The words of a file name, lower case (``Box_Base.stl`` / ``BoxBase.stl`` -> {box, base}; ``lid.stl`` ->
    {lid}); words under 3 letters dropped."""
    stem = os.path.splitext(os.path.basename(name))[0]
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", stem)
    return {w.lower() for w in parts if len(w) >= 3}


def _fresh(entry: os.DirEntry, since: float | None) -> bool:
    if since is None:
        return True
    try:
        return entry.stat().st_mtime >= since - 1.0  # 1 s of file-system time granularity
    except OSError:
        return False


def _claim_any_names(checks: list[dict], about: str, ctx: RunContext) -> list[dict]:
    """The file_exists checks of one list whose file the step never names (not in its title, instructions or the
    check's label) and whose kind an app writes out under a name of its own (EXPORT_EXTS) may pass on another file of
    that kind in that folder. Each such check gets ``_any_name``: the file it may take, else False.

    A file counts once per step (two exports, base.stl and lid.stl, are never both one Box_Base.stl), and a check takes
    a file whose name holds its own word first (Box_Base.stl for base.stl); never a file another check names, one whose
    name holds another check's word, or (when the context says when the step or lesson began) one that was already
    there before."""
    if not about.strip() or not os.path.isabs(str(ctx.workdir or "")):
        return checks
    since = ctx.step_started_at if ctx.step_started_at is not None else ctx.lesson_started_at
    exists = [(i, c) for i, c in enumerate(checks) if c.get("type") == "file_exists" and c.get("file")]
    named = {os.path.normcase(p) for _, c in exists if (p := _resolve(ctx.workdir, str(c["file"])))}
    words = {i: _name_words(str(c["file"])) for i, c in exists}
    want: dict[int, list[os.DirEntry]] = {}
    for i, c in exists:
        rel = str(c["file"])
        base, ext = os.path.basename(rel).lower(), os.path.splitext(rel)[1].lower()
        path = _resolve(ctx.workdir, rel)
        if ext not in EXPORT_EXTS or not path or os.path.exists(path) \
                or base in f"{about} {c.get('label') or ''}".lower():
            continue
        try:
            found = [e for e in os.scandir(os.path.dirname(path)) if e.is_file() and not e.name.startswith(".")
                     and e.name.lower().endswith(ext) and os.path.normcase(e.path) not in named
                     and _fresh(e, since) and not model_files.empty_mesh(e.path)]
            found.sort(key=lambda e: e.stat().st_mtime, reverse=True)  # newest first
        except OSError:
            found = []
        want[i] = found
    if not want:
        return checks
    taken: set[str] = set()
    got: dict[int, str] = {}
    for own_word in (True, False):  # a file named for the check first, then any file named for no other check
        for i, found in want.items():
            if i in got:
                continue
            others = set().union(*(w for j, w in words.items() if j != i)) - words[i]
            for e in found:
                ws = _name_words(e.name)
                if e.path in taken or (ws & others) or (own_word and not ws & words[i]):
                    continue
                got[i] = e.name
                taken.add(e.path)
                break
    return [{**c, "_any_name": got.get(i, False)} if i in want else c for i, c in enumerate(checks)]


# a file_contains pattern for Markdown syntax at a line's start (a "# title", "## heading", "- item" in a saved .ipynb's
# source strings)
_MD_PATTERN = re.compile(r'^(?:\(\?[a-zA-Z]+\))?(?:\\?"|\^)?(?:\\?#|\[[-*+]{1,3}\]|\\[-*+]|[-+]\\s|\\?>)')
_HEADING_LABEL = re.compile(r"\bheadings?\b", re.I)
_LEVEL_WORDS = re.compile(r"\blevel\b|\bh[1-6]\b|#", re.I)


def _markdown_cells(text: str, check: dict) -> str:
    """A notebook's Markdown cells only, written as VS Code saves them (one JSON string per source line): a ``#`` line
    in a code cell is a Python comment, never a title. A check about headings (not "the title", not a level) reads any
    heading below the title as one (``### Results`` is a heading)."""
    try:
        nb = json.loads(text)
    except ValueError:
        return text
    cells = nb.get("cells") if isinstance(nb, dict) else None
    if not isinstance(cells, list):
        return text
    label = str(check.get("label") or "")
    any_level = bool(_HEADING_LABEL.search(label)) and not _LEVEL_WORDS.search(label) \
        and not re.search(r"\btitle\b", label, re.I)
    out = []
    for c in cells:
        if not isinstance(c, dict) or c.get("cell_type") != "markdown":
            continue
        src = c.get("source")
        src = "".join(str(x) for x in src) if isinstance(src, list) else str(src or "")
        lines = src.splitlines(keepends=True)
        if any_level:
            lines = [re.sub(r"^#{3,6}(?=\s)", "##", ln) for ln in lines]
        out.append({"cell_type": "markdown", "source": lines})
    return json.dumps({"cells": out}, indent=1, ensure_ascii=False)


_CODE_LABEL = re.compile(r"\b(?:code|source|input|function|import|def|class|cells?)\b", re.I)
_NB_EXPORT = re.compile(r"jp-Notebook|jp-CodeCell|class=\"input_area\"|jp-InputArea")
_HTML_CODE_INPUT = re.compile(r"<div class=\"(?:highlight|input_area)[^\"]*\">\s*<pre>.*?</pre>\s*</div>", re.S)


def _without_code_inputs(html: str) -> str:
    """A notebook exported to HTML (nbconvert / Jupyter's Export) without its cells' code: what is left is what the
    page shows as notes and outputs. A chart's title in ``plt.title('Steps per day')`` is code, not a chart. Line
    structure kept. Any other HTML is left as it is."""
    if not _NB_EXPORT.search(html):
        return html
    return _HTML_CODE_INPUT.sub(lambda m: "\n" * m.group(0).count("\n"), html)


def _jsonc(text: str) -> Any:
    """A JSON-with-comments file (tsconfig.json, VS Code settings) as data, else None."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    from .code_text import strip_comments

    try:
        return json.loads(re.sub(r",(\s*[}\]])", r"\1", strip_comments(text, "c")))
    except ValueError:
        return None


def _key_paths(node: Any, key: str, path: tuple = ()) -> list[tuple]:
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                out.append(path)
            out += _key_paths(v, key, path + (k,))
    elif isinstance(node, list):
        for v in node:
            out += _key_paths(v, key, path)
    return out


def _misplaced_key(check: dict, text: str, rel: str) -> str | None:
    """A config option at the wrong level: the step's own code shows where its key goes (``"strict": true`` inside
    ``compilerOptions``), and the learner's file has that key only somewhere else, where the tool ignores it."""
    code = check.get("_json_code")
    m = model_files._KEY_PATTERN.match(str(check.get("pattern") or ""))
    if not code or not m:
        return None
    want = _key_paths(_jsonc(str(code)), m.group(1))
    if len(want) != 1 or not want[0]:
        return None
    doc = _jsonc(text)
    if doc is None:
        return None
    got = _key_paths(doc, m.group(1))
    if not got or want[0] in got:
        return None
    where = "the top level" if got[0] == () else f"inside {got[0][-1]}"
    return f'"{m.group(1)}" is at {where} of {os.path.basename(rel)}, not inside {want[0][-1]}: it is ignored there'


def _file_contains(check: dict, ctx: RunContext) -> CheckResult:
    rel, pattern = check.get("file"), check.get("pattern")
    if not rel or not pattern:
        return _result(check, "fail", "check needs 'file' and 'pattern'")
    path = _resolve(ctx.workdir, rel)
    if not path:
        return _result(check, "fail", f"{rel} is outside the lesson folder")
    if rel.strip().lower().endswith(".ipynb") and not os.path.exists(path) and os.path.isabs(str(ctx.workdir or "")):
        # t10: the video's Untitled.ipynb is the learner's mnist.ipynb ("Still to do: evaluate saved in notebook")
        if (found := find_notebook(ctx.workdir, [rel])) is not None:
            path, rel = str(found), found.name
    try:
        full = read_for_scan(path)
    except FileNotFoundError:
        return _result(check, "fail", f"{rel} not found")
    except OSError as exc:
        return _result(check, "fail", f"cannot read {rel}: {exc.strerror}")
    if why := model_files.empty_mesh(path) or (check.get("_print") and model_files.open_mesh(path)):
        return _result(check, "fail", why)
    view = code_view(full, check, rel, check.get("_sigs")) if lang_of(rel) else full  # no comments, one function
    if rel.lower().endswith((".json", ".jsonc")) and not re.search(r"//|/\\?\*|\\/\\/", pattern):
        # tsconfig.json / settings.json are JSON with comments: a key commented out (// "strict": true) is not set
        view = strip_comments(view, "c")
    if rel.lower().endswith(".ipynb") and check.get("_markdown") and _MD_PATTERN.match(pattern):
        view = _markdown_cells(full, check)  # a Markdown title / heading / list is one only in a Markdown cell
    if rel.lower().endswith((".html", ".htm")) and not _CODE_LABEL.search(str(check.get("label") or "")):
        view = _without_code_inputs(view)  # an exported notebook's code is not its output
    subjects: list[str] = []
    if rel.lower().endswith(".json"):
        if (sem := model_files.scene_view(view, str(check.get("_subject") or ""))) is not None:
            view = sem  # the scene as the app evaluates it (keyed values, used materials, the body's own sketches)
        if why := _misplaced_key(check, view, rel):
            return _result(check, "fail", why)
    if rel.lower().endswith(".json") and (sc := model_files.scoped_json(view, str(check.get("_subject") or ""))):
        view, subjects = sc  # a scene dump: only what the step is about (the Mug, not the default Cube)
    on = f" for {', '.join(subjects)}" if subjects else ""
    accept = None
    lines = view.split("\n")
    if rel.lower().endswith(".dxf"):
        accept = lambda n, s: model_files.dxf_numeric_ok(lines, n, s)  # noqa: E731
    try:  # 64 KB windows (up to 1 MB), no line over 2 KB: what one lesson search may cost is bounded
        rx = _compile(pattern)
        # float noise in a model / data dump (90.00000250447816 is 90.0); never in code, where 0.0010004 is a value
        dump = model_files.is_dump(rel)
        if why := model_files.every_instance(check, model_files.rounded(view) if dump else view, rx):
            return _result(check, "fail", f"{why} in {rel}{on}")
        hit = _search_file(rx, view, accept)
        if hit is None and dump and (r := model_files.rounded(view)) != view:
            hit = _search_file(rx, r, accept)
        if hit is None and rel.lower().endswith(".json"):
            for alt in model_files.alt_views(view):  # an applied scale, a Radius for a Diameter: the same model
                if (hit := _search_file(rx, model_files.rounded(alt))) is not None:
                    break
        if hit is None and rel.lower().endswith(".dxf"):  # AutoCAD names (layers, blocks) ignore case
            hit = _search_file(safe_compile(pattern, re.MULTILINE | re.IGNORECASE), view,
                               lambda n, s: model_files.dxf_name_ok(lines, n))
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if hit:
        line = hit[1]
        if subjects:
            return _result(check, "pass", f"found in {rel}{on}")
        if view.count("\n") != full.count("\n") and (at := full.find(hit[0].group(0))) >= 0:
            line = full.count("\n", 0, at) + 1  # the check was scoped to a function: the line in the whole file
        return _result(check, "pass", f"found in {rel}:{line}")
    return _result(check, "fail", f"not in {rel}{on} yet")


def _script_tokens(command: str) -> list[str]:
    """Tokens that identify *what* is run: drop flags/values, interpreter wrappers."""
    try:
        toks = shlex.split(command)
    except ValueError:
        toks = command.split()
    skip = {"python", "python3", "uv", "run", "tut", "-m", "-u", "node", "bash", "sh", "npx"}
    out = []
    for t in toks:
        if t.startswith("-"):
            if out:
                break  # flags after the script/module may legitimately differ
            continue  # interpreter flags (-u, -O, ...) before the script
        if "=" in t and not out:
            continue  # env assignments like CUDA_VISIBLE_DEVICES=0
        if os.path.basename(t) in skip or re.fullmatch(r"python3(\.\d+)?", os.path.basename(t)):
            continue
        out.append(os.path.basename(t))
    return out


def _command_matches(expected: str | None, actual: str | None) -> bool:
    if not expected or not actual:
        return True
    want = _script_tokens(expected)
    if not want:
        return True
    got = _script_tokens(actual)
    return all(w in got for w in want)


def _command_exit_ok(check: dict, ctx: RunContext) -> CheckResult:
    want = check.get("command")
    hint = f"run `tut run {want}`" if want else "run your script with `tut run`"
    if not ctx.has_run:
        return _result(check, "pending", hint)
    if not _command_matches(want, ctx.command):
        return _result(check, "pending", f"last run was `{ctx.command}`; {hint}")
    if ctx.running or ctx.exit_code is None:
        return _result(check, "pending", "running…")
    if ctx.exit_code == 0:
        return _result(check, "pass", "exited 0")
    return _result(check, "fail", f"exited with code {ctx.exit_code}")


def _output_contains(check: dict, ctx: RunContext) -> CheckResult:
    pattern = check.get("pattern")
    if not pattern:
        return _result(check, "fail", "check has no 'pattern'")
    text = scan_text(ctx.output_text())
    try:
        m = _compile(pattern).search(text)
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if m:
        return _result(check, "pass", f"output matched: {m.group(0)[:80]!r}")
    if not ctx.has_run:
        return _result(check, "pending", "no run yet")
    if ctx.run_finished:
        return _result(check, "fail", "pattern not in output")
    return _result(check, "pending", "waiting for output…")


def _metric_name(check: dict) -> str | None:
    return check.get("metric") or (str(check.get("id")) if check.get("metric_pattern") else None)


def _notebook_points(ctx: RunContext, check: dict | None) -> list[tuple[int, float]]:
    """t10 (the s5 blocker): a metric the step's own notebook cell printed, e.g. Keras's `accuracy: 0.9858` epoch lines
    (ANSI codes stripped by notebook.read_notebook). The run happened in the kernel, so no `tut run` / terminal
    output and often no screen ever shows them: the notebook file is where they are."""
    nb, pattern = ctx.notebook, (check or {}).get("metric_pattern")
    if not pattern or not isinstance(nb, Notebook) or not nb.outputs:
        return []
    text = "\n".join(nb.outputs)
    pts = [(int(s), float(v)) for s, v in extract_metrics(pattern, text)]
    if not pts and (bare := _bare_metric_pattern(check or {}, nb)):
        pts = [(int(s), float(v)) for s, v in extract_metrics(bare, text)]
    return pts


_BARE_ROW = r"^\s*(?P<step>\d+)\s*[,:;|]?\s+(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*$"
_BARE_VALUE = r"^\s*(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*$"
_PRINT_ARGS = re.compile(r"\bprint\s*\(([^\n]*)\)")


def _bare_metric_pattern(check: dict, nb: Notebook) -> str | None:
    """The learner printed the metric their own way, without the words the check's pattern expects
    (``print(epoch, loss.item())`` -> ``0 0.2614``): rows of a step number and a value count when the step's own cell
    prints the metric (a print( call naming it) and the pattern reads a step and a value. A print of the metric alone
    (``fit(..., verbose=0)`` then ``print(history.history['accuracy'][-1])`` -> ``0.9858000040054321``) is its value,
    when the pattern reads one."""
    name, pattern = str(check.get("metric") or ""), str(check.get("metric_pattern") or "")
    if not re.fullmatch(r"\w+", name) or "(?P<value>" not in pattern:
        return None
    for c in nb.cells:
        for m in _PRINT_ARGS.finditer(c.source):
            args = [a.strip() for a in m.group(1).split(",")]
            if len(args) == 2 and "(?P<step>" in pattern and re.search(rf"\b{re.escape(name)}\b", args[1]) \
                    and not re.search(r"['\"]", m.group(1)):
                return _BARE_ROW
            # one argument naming the metric (a variable, or a history key) and no text of its own around it
            if len(args) == 1 and not re.match(r"[fbr]?['\"]", args[0]) \
                    and re.search(rf"(?<![\w.])['\"]?{re.escape(name)}['\"]?(?!\w)", args[0]):
                return _BARE_VALUE
    return None


# Keras names a metric after the string it was given: metrics=['acc'] prints `acc: 0.9858`, ['mse'] prints `mse: ...`
_METRIC_ALIASES = {"accuracy": "acc(?:uracy)?", "mean_squared_error": "(?:mean_squared_error|mse)",
                   "mean_absolute_error": "(?:mean_absolute_error|mae)"}


def _alias_pattern(pattern: str) -> str | None:
    """The check's metric pattern with Keras's short metric names allowed too (``accuracy:`` -> ``acc(?:uracy)?:``),
    or None when it names none of them."""
    out = pattern
    for long, either in _METRIC_ALIASES.items():
        out = re.sub(rf"(?<!\w){re.escape(long)}(?!\w)", lambda _m: either, out)
    return out if out != pattern else None


def _metric_texts(ctx: RunContext, check: dict) -> list[str]:
    texts = list(ctx.notebook.outputs) if isinstance(ctx.notebook, Notebook) else []
    return texts + [screen_text(ctx.screen, check.get("app")) or "", ctx.output_text()]


def _metric_view(check: dict, ctx: RunContext) -> tuple[dict, RunContext]:
    """(the check, ctx) as a metric check reads them:

    * the pattern names the metric its long way (``accuracy:``) and nothing on record prints that, while the short name
      Keras prints for ``metrics=['acc']`` is there (``acc: 0.9858``): the pattern takes either;
    * the step's metric is printed by more than one of its cells (a run that blew up to ``loss: nan`` in one cell, then a
      rebuilt model fit again in a new cell below): only the cell that ran last is the model in the kernel now."""
    pattern = str(check.get("metric_pattern") or "")
    if pattern and (alias := _alias_pattern(pattern)) is not None:
        try:
            rx, arx = _compile(pattern), _compile(alias)
            texts = [scan_text(t) for t in _metric_texts(ctx, check)]
            if not any(rx.search(t) for t in texts) and any(arx.search(t) for t in texts):
                check = {**check, "metric_pattern": alias}
                pattern = alias
        except re.error:
            pass
    nb = ctx.notebook
    if pattern and isinstance(nb, Notebook) and len(nb.cells) > 1:
        printing = [i for i, c in enumerate(nb.cells) if c.outputs
                    and extract_metrics(pattern, "\n".join(c.outputs))]
        if len(printing) > 1:
            counted = [i for i in printing if nb.cells[i].count is not None]
            newest = max(counted, key=lambda i: nb.cells[i].count) if len(counted) == len(printing) else printing[-1]
            ctx = dataclasses.replace(ctx, notebook=nb.only([newest]))
    return check, ctx


# an accuracy / precision / recall / F1 is a fraction of 0..1 (a percentage up to 100); a bar the step sets at 1 or below
# means the fraction
_FRACTION_METRIC = re.compile(r"(?:^|_|\b)(?:acc|accuracy|precision|recall|f1|auc|iou|dice)(?:$|_|\b)", re.I)


def _as_fraction(check: dict, name: str, value: float) -> tuple[float, str | None]:
    """(the metric's value on the check's 0..1 scale, why it can't be one): a printed ``98.6`` accuracy is 98.6 % =
    0.986; a printed ``121.0`` is no accuracy at all (a count of right answers never divided by how many there were)."""
    target = check.get("value")
    if not _FRACTION_METRIC.search(name) or not isinstance(target, (int, float)) or not 0 < float(target) <= 1 \
            or value <= 1:
        return value, None
    if value <= 100:
        return value / 100.0, None
    return value, (f"{name.replace('_', ' ')} {_fmt(value)} is not a fraction: that is a count; divide it by the "
                   f"number of examples")


_EPOCH_HEADER = re.compile(r"^\s*Epoch\s+(\d+)\s*/\s*(\d+)\b", re.I | re.M)


def _unfinished_fit(check: dict, ctx: RunContext) -> CheckResult | None:
    """A Keras fit whose output stops before its last epoch (``Epoch 4/5`` with nothing after, or ``Epoch 2/5`` and an
    interrupt): the model has not trained the epochs the step asks for, whatever accuracy a half-done epoch shows. It
    is still running (pending) or it stopped with an error / a crashed kernel (fail)."""
    if not _notebook_points(ctx, check):
        return None
    nb = ctx.notebook
    heads = _EPOCH_HEADER.findall("\n".join(nb.outputs))
    if not heads or int(heads[-1][0]) >= int(heads[-1][1]):
        return None
    k, n = heads[-1]
    if nb.errors or _kernel_crashed(ctx):
        return _result(check, "fail", f"training stopped in epoch {k} of {n}: run the cell again")
    return _result(check, "pending", f"training is at epoch {k} of {n}")


_KERNEL_CRASH = re.compile(r"\bThe Kernel crashed\b|\bkernel (?:has )?died\b|\bKernel Restarting\b|\bkernel crashed\b",
                           re.I)


def _kernel_crashed(ctx: RunContext) -> str | None:
    """The notebook's kernel crashed on screen (VS Code: "The Kernel crashed while executing code ..."; Jupyter: "The
    kernel appears to have died"): everything the kernel held (the model, its weights) is gone."""
    text = screen_text(ctx.screen, "Code") if ctx.screen is not None else None
    if not text:
        return None
    m = _KERNEL_CRASH.search(text) or re.search(r"\bkernel appears to have died\b", text, re.I)
    return m.group(0) if m else None


def _raw_series(ctx: RunContext, name: str, check: dict | None = None) -> list[tuple[int, float]]:
    """All points sorted by step, None/NaN/inf kept as float (NaN for None)."""
    raw = list(ctx.metrics.get(name, []))
    pattern = (check or {}).get("metric_pattern")
    if pattern and (nb_pts := _notebook_points(ctx, check)):
        raw = nb_pts  # the step's cell output on disk is exact; the screen / a terminal only saw part of it
    elif not raw and pattern:
        texts = [screen_text(ctx.screen, check.get("app")) or "", ctx.output_text()]
        merged: dict[int, float] = {}
        for t in texts:
            merged.update(extract_metrics(pattern, t))
        raw = sorted(merged.items())
    pts = [(int(s), math.nan if v is None else float(v)) for s, v in raw]
    pts.sort(key=lambda p: p[0])
    return pts


def _series(ctx: RunContext, name: str, check: dict | None = None) -> list[tuple[int, float]]:
    return [p for p in _raw_series(ctx, name, check) if math.isfinite(p[1])]


def _diverged(ctx: RunContext, name: str, check: dict, since_step: int | None = None) -> CheckResult | None:
    """Fail when the metric went NaN/inf: as its latest point, or anywhere at/after ``since_step``.

    A diverged run must never be graded on the stale finite values logged before it blew up.
    """
    raw = _raw_series(ctx, name, check)
    if not raw:
        return None
    bad = [p for p in raw if not math.isfinite(p[1]) and (since_step is None or p[0] >= since_step)]
    if not math.isfinite(raw[-1][1]):
        bad.append(raw[-1])
    if not bad:
        return None
    s, v = bad[-1]
    return _result(check, "fail", f"{name} diverged: {v} at step {s}")


_NONFINITE_FIELD = re.compile(r"(?<![\w.])([A-Za-z_][\w]*)\s*[:=]?\s*[-+]?(nan|inf(?:inity)?)\b", re.I)
_FIRST_EPOCH = re.compile(r"^\s*Epoch\s+1\s*/\s*\d+", re.I)  # Keras's header row of a run's first epoch


def _newest_run(text: str, rx: Any, check: dict, ctx: RunContext) -> list[str]:
    """The rows of the newest run in ``text`` (as _diverged reads only from ``since_step``): in a terminal's history,
    the output of the newest command that printed a metric row (of the step's run command, when one is known); then,
    in that, the rows from the last restart on (a run's ``Epoch 1/`` header again, or the pattern's step going back).
    A finished re-run is never judged on the NaN of the run before it."""
    rows = text.split("\n")
    bl = blocks.parse(rows)
    if blocks.has_commands(bl):
        printed = [b for b in bl if b.command and any(rx.search(r) for r in b.output)]
        rc = [s for c in (ctx.command, check.get("_run_command")) if c for s in blocks.segments(str(c))]
        own = [b for b in printed if any(blocks.runs(s, t) for s in blocks.segments(b.command or "") for t in rc)]
        if own or printed:
            rows = (own or printed)[-1].output
    start, prev = 0, None
    for i, row in enumerate(rows):
        if _FIRST_EPOCH.match(row):
            start, prev = i, None
            continue
        if not (m := rx.search(row)) or m.groupdict().get("step") is None:
            continue
        try:
            step = float(m.group("step"))
        except ValueError:
            continue
        if prev is not None and step < prev:
            start = i
        prev = step
    return rows[start:]


def _sibling_divergence(ctx: RunContext, check: dict) -> str | None:
    """Another metric on the check's own metric lines went NaN / inf (Keras: ``accuracy: 0.9563 - loss: nan``): the
    weights are NaN, whatever this metric's epoch average still says. ``"loss: nan"``, else None."""
    pattern = check.get("metric_pattern")
    if not pattern:
        return None
    if _notebook_points(ctx, check):
        texts = list(ctx.notebook.outputs)
    else:
        texts = [screen_text(ctx.screen, check.get("app")) or "", ctx.output_text()]
    try:
        rx = _compile(pattern)
    except re.error:
        return None
    for line in (ln for t in texts for ln in _newest_run(scan_text(t), rx, check, ctx)):
        if not (m := rx.search(line)):
            continue
        rest = line[:m.start()] + " " + line[m.end():]
        if f := _NONFINITE_FIELD.search(rest):
            return f"{f.group(1)}: {f.group(2)}"
    return None


def _no_metric(ctx: RunContext, name: str) -> str:
    """A finished run that printed no `name`, in plain words (test 7: a crash has no loss; the row says so and never
    shows an older run's): "no loss: the run stopped with an error" / "the run printed no loss"."""
    label = name.replace("_", " ")
    return f"no {label}: the run stopped with an error" if ctx.exit_code else f"the run printed no {label}"


def _waiting_for_metric(check: dict, ctx: RunContext, name: str) -> CheckResult:
    """No points yet. A screen-read metric whose app isn't on screen can't arrive by waiting:
    say which app to open, and (once the segment is over) fail so stuck/idle help can kick in."""
    app = check.get("app")
    if (check.get("metric_pattern") and app and ctx.screen is not None and not ctx.running
            and screen_text(ctx.screen, app) is None):
        return _result(check, "fail" if ctx.after_segment else "pending", f"open {app} so I can read {name}")
    where = f" in {app}" if app and check.get("metric_pattern") else ""
    return _result(check, "pending", f"waiting for the run's {name.replace('_', ' ')} lines{where}")  # t8: plain words


def _metric_threshold(check: dict, ctx: RunContext) -> CheckResult:
    name, op, target = _metric_name(check), check.get("op"), check.get("value")
    if not name or op not in _OPS or target is None:
        return _result(check, "fail", "check needs 'metric' (or 'metric_pattern'), 'op' and 'value'")
    by_step = check.get("by_step")
    check, ctx = _metric_view(check, ctx)
    div = _diverged(ctx, name, check)
    if div:
        return div
    if sib := _sibling_divergence(ctx, check):
        return _result(check, "fail", f"{sib} on the {name.replace('_', ' ')} lines: the run diverged")
    pts = _series(ctx, name, check)
    if not pts:
        if ctx.run_finished:
            return _result(check, "fail", _no_metric(ctx, name))
        return _waiting_for_metric(check, ctx, name)
    if unfinished := _unfinished_fit(check, ctx):
        return unfinished
    eligible = [p for p in pts if by_step is None or p[0] <= by_step]
    latest_step = pts[-1][0]
    # a notebook cell's Keras lines are per-epoch averages already: its last one is the result (t10: 0.9858)
    nb = ctx.notebook if _notebook_points(ctx, check) else None
    if eligible:
        recent = [v for _, v in eligible[-(1 if nb is not None else THRESHOLD_SMOOTH_POINTS):]]
        current, not_fraction = _as_fraction(check, name, statistics.median(recent))
        at = eligible[-1][0]
        if not_fraction:
            return _result(check, "fail", not_fraction)
        if _OPS[op](current, float(target)):
            where = f"in {nb.path.name}" if nb is not None else f"at step {at}"
            return _result(check, "pass", f"{name} {_fmt(current)} {op} {_fmt(float(target))} {where}")
        msg = f"{name} {_fmt(current)} at step {at}, need {op} {_fmt(float(target))}"
    else:
        msg = f"no '{name}' points at or before step {by_step}"
    if by_step is not None and latest_step >= by_step:
        return _result(check, "fail", msg + f" by step {by_step}")
    if ctx.run_finished or (nb is not None and nb.executed and not ctx.running):
        # a notebook cell that finished (it has run, and nothing is running) below the bar is a fail: stuck-help can fire
        return _result(check, "fail", msg)
    return _result(check, "pending", msg)


def _theil_sen_slope(xs: list[float], ys: list[float]) -> float:
    slopes = []
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[j] - xs[i]
            if dx != 0:
                slopes.append((ys[j] - ys[i]) / dx)
    return statistics.median(slopes) if slopes else 0.0


def _thin(pts: list[tuple[int, float]], k: int) -> list[tuple[int, float]]:
    if len(pts) <= k:
        return pts
    stride = len(pts) / k
    return [pts[int(i * stride)] for i in range(k - 1)] + [pts[-1]]


def trend_stats(pts: list[tuple[int, float]]) -> dict[str, float]:
    """Robust trend statistics over a window of (step, value) points.

    Two independent estimates of the relative change across the window:

    * ``rel_median``: 1 - median(last third) / median(first third). Insensitive to
      spikes and minibatch noise.
    * ``rel_theil_sen``: relative change implied by the Theil–Sen slope (median of
      pairwise slopes) across the window span. Fit on log10(value) when every value
      is positive (losses span decades), else on raw values scaled by |first median|.

    Positive numbers mean the metric went *down* (improvement for a loss).
    """
    pts = _thin(pts, MAX_TS_POINTS)
    xs = [float(s) for s, _ in pts]
    ys = [v for _, v in pts]
    third = max(1, len(ys) // 3)
    first, last = statistics.median(ys[:third]), statistics.median(ys[-third:])
    span = xs[-1] - xs[0]
    positive = all(v > 0 for v in ys)
    if positive:
        slope = _theil_sen_slope(xs, [math.log10(v) for v in ys])
        rel_ts = 1.0 - 10 ** (slope * span)
        rel_med = 1.0 - last / first
    else:
        slope = _theil_sen_slope(xs, ys)
        scale = abs(first) or 1e-12
        rel_ts = -(slope * span) / scale
        rel_med = (first - last) / scale
    return {"rel_median": rel_med, "rel_theil_sen": rel_ts, "first": first, "last": last, "span": span,
            "slope": slope, "mk_z": mann_kendall_z(ys), "n": len(ys)}


def mann_kendall_z(ys: list[float]) -> float:
    """Mann-Kendall trend statistic as a z-score (negative = downward trend).

    S = sum over pairs of sign(y_j - y_i); Var(S) = n(n-1)(2n+5)/18 minus the tie
    correction; z = (S -/+ 1)/sqrt(Var). Rank-based, so it is immune to the noise scale
    and to outliers: noise alone stays below |z| ~ 2.6 in 99% of windows.
    """
    n = len(ys)
    if n < 3:
        return 0.0
    s = 0
    for i in range(n - 1):
        yi = ys[i]
        for j in range(i + 1, n):
            d = ys[j] - yi
            s += (d > 0) - (d < 0)
    ties: dict[float, int] = {}
    for y in ys:
        ties[y] = ties.get(y, 0) + 1
    var = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in ties.values() if t > 1)) / 18
    if var <= 0 or s == 0:
        return 0.0
    return (s - 1) / math.sqrt(var) if s > 0 else (s + 1) / math.sqrt(var)


def _window_steps(window: int, pts: list[tuple[int, float]]) -> int:
    """A trend window is written in steps, but a script logs every N: ``window: 5`` over a loss printed every 100
    steps holds one point and could never be judged. The window is widened to span at least TREND_MIN_POINTS of the
    run's own samples (its median logging gap), so it counts what was observed, not raw steps."""
    gaps = sorted(b[0] - a[0] for a, b in zip(pts, pts[1:]) if b[0] > a[0])
    if not gaps:
        return window
    return max(window, gaps[len(gaps) // 2] * (TREND_MIN_POINTS - 1))


def _metric_trend(check: dict, ctx: RunContext) -> CheckResult:
    """``not_flat`` / ``decreasing`` over the last ``window`` training steps.

    Window = points with step >= latest_step - window. Pending until the window
    has >= TREND_MIN_POINTS finite points covering >= TREND_MIN_COVERAGE of it.

    Two gates, both required (the classic Mann-Kendall + Sen's slope pairing):

    1. **Significance**: the Mann-Kendall z-score of the window. Rank-based, so it scales
       with the noise automatically; pure noise passes this in about 1% of windows.
    2. **Effect size**: the Theil–Sen relative change across the window (on log10 values
       when all are positive). This keeps a real but negligible drift (a PINN plateau
       creeping 0.2504 → 0.2490, which MK flags as "significant" when there are
       thousands of points) from counting as progress.

    * ``not_flat``: |z| >= MK_Z_TWO_SIDED (p<0.01) and |Theil–Sen change| >= 5%, same
      direction. Direction-agnostic (literally "not flat"); use ``decreasing`` when the
      direction matters.
    * ``decreasing``: z <= -MK_Z_ONE_SIDED (p<0.01) and a Theil–Sen drop >= 2%.

    A NaN/inf anywhere in the window (or as the latest point) fails the check: divergence.
    """
    name = _metric_name(check)
    trend = check.get("trend")
    if not name or trend not in ("not_flat", "decreasing"):
        return _result(check, "fail", "check needs 'metric' (or 'metric_pattern') and trend 'not_flat'|'decreasing'")
    window = int(check.get("window") or DEFAULT_TREND_WINDOW)
    check, ctx = _metric_view(check, ctx)
    pts = _series(ctx, name, check)
    if not pts:
        if ctx.run_finished:
            return _result(check, "fail", _no_metric(ctx, name))
        return _waiting_for_metric(check, ctx, name)
    window = _window_steps(window, pts)
    latest = pts[-1][0]
    div = _diverged(ctx, name, check, since_step=latest - window)
    if div:
        return div
    if sib := _sibling_divergence(ctx, check):
        return _result(check, "fail", f"{sib} on the {name.replace('_', ' ')} lines: the run diverged")
    win = [p for p in pts if p[0] >= latest - window]
    span = win[-1][0] - win[0][0]
    if len(win) < TREND_MIN_POINTS or span < TREND_MIN_COVERAGE * window:
        msg = f"collecting {name}: {len(win)} pts over {span}/{window} steps"
        if ctx.run_finished:
            return _result(check, "fail", msg + " (run ended)")
        return _result(check, "pending", msg)

    st = trend_stats(win)
    rt, z = st["rel_theil_sen"], st["mk_z"]
    desc = (f"{name} {_fmt(st['first'])} → {_fmt(st['last'])} over last {int(st['span'])} steps "
            f"({-rt * 100:+.1f}%, trend z={z:+.1f})")
    if trend == "decreasing":
        ok = z <= -MK_Z_ONE_SIDED and rt >= DECREASING_MIN_REL_DROP
        return _result(check, "pass" if ok else "fail", desc + ("" if ok else " — not decreasing"))
    ok = abs(z) >= MK_Z_TWO_SIDED and abs(rt) >= NOT_FLAT_MIN_REL_CHANGE and (rt > 0) == (z < 0)
    return _result(check, "pass" if ok else "fail", desc + ("" if ok else " — plateau"))


# t11: the notebook kernel check (server.lesson.notebook_steps: "Notebook kernel is .venv"), and the kernel VS Code saves
# in the notebook's metadata once it connected one: ".venv (3.12.16)" / ".venv" (older: "Python 3.12.16 ('.venv': venv)")
_KERNEL_LABEL = re.compile(r"^Notebook kernel is \.?venv\b", re.I)
_VENV_KERNEL = re.compile(r"^\s*\.?venv\b|['‘’]\.?venv['‘’]", re.I)


def _is_kernel_check(check: dict) -> bool:
    return check.get("type") == "screen_contains" and bool(_KERNEL_LABEL.match(str(check.get("label") or "")))


def _saved_kernel(check: dict, ctx: RunContext) -> str | None:
    """t11: the .venv kernel as the step's notebook on disk says it, before any OCR of the picker's label: VS Code writes
    kernelspec.display_name and language_info.version when it connects the kernel (Miyagi's template has no version,
    so an untouched template never passes). None: not known from the file."""
    if not os.path.isabs(str(ctx.workdir or "")):
        return None
    nb = read_notebook(find_notebook(ctx.workdir, [str(check.get("_nb_file") or check.get("file") or "")]))
    if nb is None or not nb.kernel_version or not _VENV_KERNEL.search(nb.kernel):
        return None
    return f"kernel {nb.kernel} in {nb.path.name}"


def _screen(check: dict, ctx: RunContext, absent: bool) -> CheckResult:
    pattern, app = check.get("pattern"), check.get("app")
    if not pattern:
        return _result(check, "fail", "check has no 'pattern'")
    if not absent and _is_kernel_check(check) and (k := _saved_kernel(check, ctx)):
        return _result(check, "pass", k)
    where = f" in {_app_name(app, ctx)}" if app else " on screen"
    # the notebook as this step sees it (t10): every cell's source, but the outputs of the cells holding its own code
    nb = ctx.notebook if isinstance(ctx.notebook, Notebook) and app not in _TERMINAL_APPS else None
    output = not absent and app not in _TERMINAL_APPS and is_output_check(check)
    try:
        if nb is not None and absent and nb.errors and (e := search_screen(pattern, scan_text("\n".join(nb.errors)))):
            return _result(check, "fail", f"the cell printed {e.group(0)[:80]!r}")  # t9 V3: a cell's error output
        if nb is not None and absent and not nb.executed:
            # t10: "No predict errors · not showing on screen" passed before the step's cell existed: no run, no verdict
            return _result(check, "pending", "checked when the cell runs")
        if nb is not None and not absent:  # t9 V2/V3: the notebook's cells as typed / what they printed decide first
            src = nb.output_text if output else code_view(nb.source_text, check, ".py", check.get("_sigs"))
            if search_wrapped(pattern, scan_text(src)):
                return _result(check, "pass", f"{'printed' if output else 'typed'} in {nb.path.name}")
            if output and _plotted(pattern, nb):
                return _result(check, "pass", f"plotted in {nb.path.name}")
            if output and _drawn_matrix(pattern, nb, screen_lines(ctx.screen, app) or []):
                return _result(check, "pass", f"drawn as a figure in {nb.path.name}")
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if output and nb is not None and not nb.executed:
        # t10: the step's cell hasn't run (or isn't written): whatever the screen shows is another cell's output
        # ("predict progress printed" passed on the TRAINING cell's "ms/step" before any s6 code existed)
        return _result(check, "fail", "not printed yet: run the cell")
    text = screen_text(ctx.screen, app)
    if text is None:
        return _not_visible(check, ctx, absent)
    if not absent and not output and app not in _TERMINAL_APPS:  # the learner's code: no comments, one function
        text = code_view(text, check, check.get("file"), check.get("_sigs"))
    if not absent and app in _TERMINAL_APPS and not ctx.running:  # typed at the prompt, Enter not pressed: not run
        text = _without_typed_input(text)
    if output:  # t9 V3: the print() line on screen is code, never the output it promises
        text = "\n".join(ln for ln in screen_lines(ctx.screen, app) or [] if not _code_line(ln, check.get("_code")))
    text = scan_text(text, SCREEN_SCAN_CHARS)  # the newest 4 KB of the window(s): never a whole scrollback
    try:
        if not output and app != "Code" and (by_block := _on_blocks(check, ctx, absent, text, where)) is not None:
            return by_block  # a terminal's (or AutoCAD's) history: read per command and its own output
        m = _absent_hit(pattern, text) if absent else search_wrapped(pattern, text)
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if output and not m:
        return _result(check, "fail", "not printed yet: run the cell" if nb is not None and not nb.executed
                       else "not printed yet")
    if absent:
        if m:
            return _result(check, "fail", f"still showing {m.group(0)[:80]!r}{where}")
        return _result(check, "pass", f"not showing{where}")
    if m and not output and app == "Code" and (other := _in_another_file(check, ctx, text)):
        return _result(check, "fail", other)
    if m and not output and app not in ("Code", *_TERMINAL_APPS) and _only_in_open_menu(pattern, text):
        return _result(check, "fail", f"{m.group(0)[:60]!r} is only an item of an open menu{where}: not added yet")
    if m:
        return _result(check, "pass", f"seen{where}")
    if app == "Code" and not output and (disk := _off_screen_file(check, ctx, text)):
        return disk
    if app in _TERMINAL_APPS:  # the terminal is on screen, the output isn't: say that, not where to open it
        if made := _ran_and_made(check, ctx, blocks.parse(text.split("\n"))):
            return made
        if ctx.running:  # t11: the step's run is still live (a server never exits): not a fail yet
            return _result(check, "pending", f"not printed{where} yet: still running")
        return _result(check, "fail", "not printed by the last run: run it again" if ctx.run_finished
                       else f"not printed{where} yet")
    # learner words (E2): the file the code goes in when known ("not in calculator.py yet"), else the app
    f = _learner_file(os.path.basename(str(check.get("file") or "")), ctx)
    return _result(check, "fail", f"not in {f} yet" if f else f"not{where} yet" if app else "not showing yet")


# an app's "add something" menu: its header row ("Add", "Add Modifier", "Insert") then a long column of short labels
_MENU_HEADER = re.compile(r"^\s*(?:Add|Insert|New|Create)(?:\s+[A-Z][A-Za-z]*)?\s*$")
_MENU_ITEM = re.compile(r"^\s*[A-Z][A-Za-z]*(?:[ -][A-Za-z]+){0,2}\s*$")  # 1-3 words, letters only (no "Levels 2")
MENU_MIN_ITEMS = 8


def _only_in_open_menu(pattern: str, text: str) -> bool:
    """Is every line the pattern matches an item of an open menu (Blender's Add Modifier > Generate list, Shift+A >
    Light)? A word in a menu is something the learner could add, not something added. A match across lines, or any
    match outside a menu, is not."""
    lines = text.split("\n")
    menu: set[int] = set()
    for i, ln in enumerate(lines):
        if _MENU_HEADER.match(ln):
            j = i + 1
            while j < len(lines) and _MENU_ITEM.match(lines[j]):
                j += 1
            if j - i - 1 >= MENU_MIN_ITEMS:
                menu |= set(range(i + 1, j))
    if not menu:
        return False
    hits = [i for i, ln in enumerate(lines) if search_screen(pattern, ln)]
    return bool(hits) and all(i in menu for i in hits)


def _off_screen_file(check: dict, ctx: RunContext, screen: str) -> CheckResult | None:
    """A code check whose label names another lesson file ("main.py calls add_numbers(2, 3)") that isn't open on
    screen (its name nowhere in VS Code's text): that file on disk answers it (F2 renamed every file; only
    operations.py is open)."""
    rel = code_equiv.file_in_label(str(check.get("label") or ""))
    if not rel or not os.path.isabs(str(ctx.workdir or "")) or os.path.basename(rel) in screen:
        return None
    path = code_equiv.find_file(ctx.workdir, rel)
    text = code_equiv.read(path) if path is not None else None
    if not text:
        return None
    try:
        if search_wrapped(str(check.get("pattern") or ""), scan_text(code_view(text, check, path.name,
                                                                                check.get("_sigs")))):
            return _result(check, "pass", f"found in {path.name} (not open on screen)")
    except re.error:
        return None
    return None


def _in_another_file(check: dict, ctx: RunContext, screen: str) -> str | None:
    """A code line seen in VS Code that belongs to another file of the lesson (a split editor: the import is at the
    top of test_operations.py, the call in main.py). The check's file (the one its label names, else the step's) is on
    disk without the pattern, and another lesson file of the same language whose name is on screen (an open tab) has
    it: why the screen doesn't count."""
    if not os.path.isabs(str(ctx.workdir or "")):
        return None
    rel = code_equiv.file_in_label(str(check.get("label") or "")) or str(check.get("file") or "")
    if code_equiv.kind_of(rel) is None or (own := code_equiv.find_file(ctx.workdir, rel)) is None:
        return None
    pattern, sigs = str(check.get("pattern") or ""), check.get("_sigs")

    def has(path) -> bool:
        text = code_equiv.read(path)
        return bool(text) and bool(search_wrapped(pattern, scan_text(code_view(text, check, path.name, sigs))))

    if code_equiv.read(own) is None or has(own):
        return None
    for p in code_equiv.lesson_files(ctx.workdir):
        if p != own and code_equiv.kind_of(p.name) == code_equiv.kind_of(own.name) and p.name in screen and has(p):
            return f"not in {own.name} yet (that line on screen is in {p.name})"
    return None


# What an error looks like in a terminal (server.checks.blocks.ERROR_FORM): a traceback, `XError:`, `error:` starting a
# line, npm's `ERR!`, "command not found", a test run's `1 failed`, a compiler's `error TS2305:`. The bare word anywhere
# else ("Relative L2 Error: 3.1e-02", "error rate", "no errors") is a number the program prints, not a crash.
_ERROR_FORM = blocks.ERROR_FORM
_BARE_ERROR_WORD = re.compile(r"(?:errors?|exceptions?|failed|failure|fatal|traceback)", re.I)


def _absent_hit(pattern: str, text: str) -> re.Match[str] | None:
    """The first match of a screen_absent ``pattern`` that is really there. A match that is only the bare word
    ``Error`` / ``error`` / ``Exception`` counts when its line is an error form (_ERROR_FORM), never when a program
    prints it as a label (``Relative L2 Error: 3.1e-02``); every longer match (``Traceback``, ``NotImplementedError``,
    a lesson's own wording) counts as before."""
    rx = safe_compile(pattern, re.MULTILINE)
    for hay in (text, re.sub(r"\s+", " ", text)):
        for m in rx.finditer(hay):
            if not _BARE_ERROR_WORD.fullmatch(m.group(0).strip()):
                return m
            start = hay.rfind("\n", 0, m.start()) + 1
            end = hay.find("\n", m.end())
            if _ERROR_FORM.search(hay[start:len(hay) if end < 0 else end]):
                return m
    return None


def _on_blocks(check: dict, ctx: RunContext, absent: bool, text: str, where: str) -> CheckResult | None:
    """A screen check on a terminal's history (or a command-line app's ``Command:`` rows), read per command
    (server.checks.blocks). None when the text has no command rows, or the pattern only matches across commands:
    the plain search decides then.

    * screen_contains: the step's own terminal command (its Terminal target) must be among the commands that ran,
      when any ran (``git branch x`` is not ``git checkout -b x``; ``touch`` / ``ls`` are not ``git add``); and the
      match counts only in a command's newest run whose output shows no failure (``fatal:``, ``! [rejected]``,
      ``nothing added to commit``, ``*Cancel*``) unless that failure is what the pattern looks for. Seen only in an
      earlier run while the newest is still live (``ctx.running``, no prompt back under it): pending, not a fail.
    * screen_absent: a match counts unless its command got past it (pip's resolver notice, then ``Successfully
      installed``), was run again since, or repeats an earlier command that already succeeded (``fatal: No rebase in
      progress?``)."""
    bl = blocks.parse(text.split("\n"))
    if not blocks.has_commands(bl):
        return None
    pattern = str(check.get("pattern") or "")
    if absent:
        hit = None
        for i, b in enumerate(bl):
            m = _absent_hit(pattern, b.text)
            if not m:
                continue
            if b.command and (blocks.superseded(bl, i) or blocks.redundant(bl, i) or b.recovered()
                              or blocks.cured(bl, i)):
                continue
            hit = hit or m
        if hit:
            return _result(check, "fail", f"still showing {hit.group(0)[:80]!r}{where}")
        return _result(check, "pass", f"not showing{where}")
    targets = check.get("_target_cmds") or []
    ran = [s for b in bl if b.command for s in blocks.segments(b.command)]
    if targets and ran and not any(blocks.runs(s, t) for s in ran for t in targets):
        return _ran_and_made(check, ctx, bl) or _result(check, "fail", f"`{targets[0]}` hasn't run yet")
    hits = [i for i, b in enumerate(bl) if search_wrapped(pattern, b.text)]
    if not hits:  # the learner's own quoted text (a commit message) keeps the case they typed it in
        hits = [i for i, b in enumerate(bl) if b.command and _quoted_hit(pattern, b.command)]
    if not hits:  # the result printed its other way (a rebasing git pull: no "Fast-forward", no diffstat)
        hits = [i for i, b in enumerate(bl) if blocks.same_outcome(lambda x: bool(search_wrapped(pattern, x)), b)]
    if not hits:
        return None
    why, live, refused = "", False, False
    gone = blocks.undone(bl)
    for i in hits:
        b = bl[i]
        if blocks.is_undo(b) or i in gone:  # AutoCAD's UNDO took that command back (its output names it too)
            why = why or f"`{b.command}` was undone"
            continue
        if b.command and blocks.superseded(bl, i):
            why = why or f"that was an earlier `{b.command}`: the newest one didn't print it"
            me = blocks.norm(b.command)
            newest = next(n for n in reversed(bl) if n.command and blocks.norm(n.command) == me)
            # live: the newest run is the terminal's last command row (no prompt came back under it) and hasn't failed
            last = next(n for n in reversed(bl) if n.command is not None)
            live = live or (newest is last and newest.failure() is None)
            continue
        bad = b.failure()
        if bad and not search_wrapped(pattern, bad):
            why = why or f"`{b.command or 'the command'}` failed: {bad.strip()[:80]!r}"
            continue
        if other := _not_the_steps_result(check, ctx, bl, i, pattern):
            why, refused = why or other, True
            continue
        if left := _abandoned(check, bl):
            return _result(check, "fail", left)
        return _result(check, "pass", f"seen{where}")
    if not refused and (made := _ran_and_made(check, ctx, bl)):  # its words on screen say it isn't so: never
        return made
    if live and ctx.running:  # the newest run is still live (a dev server, a long build): it may print it yet
        return _result(check, "pending", f"not printed by the newest run{where} yet: still running")
    return _result(check, "fail", why)


_QUOTED = re.compile(r"\"([^\"\n]+)\"|'([^'\n]+)'")


def _quoted_hit(pattern: str, command: str) -> bool:
    """Is ``pattern`` (case aside) in a quoted argument of ``command`` (``git commit -m "Add waiting file"``)? Text the
    learner chose (a message, a name) is theirs to capitalise."""
    try:
        rx = safe_compile(pattern, re.MULTILINE | re.IGNORECASE)
    except re.error:
        return False
    return any(q and rx.search(q) for m in _QUOTED.finditer(command) for q in m.groups())


_UNIVERSAL_LABEL = re.compile(r"\b(?:each|every|all|per)\b", re.I)
_LITERAL_NUMBER = re.compile(r"(?<![\\{,\d])\d+(?![\d,}])")
_HOME_PATH = re.compile(r"^\s*/(?:Users|home)/([^/\s]+)\s*$")
_GIT_SECTION_WORDS = {"untracked": "Untracked files", "staged": "Changes to be committed"}


def _scan_steps_cmds(check: dict) -> list[str]:
    return [*(check.get("_target_cmds") or []), *([check["_run_command"]] if check.get("_run_command") else [])]


def _not_the_steps_result(check: dict, ctx: RunContext, bl: list[blocks.Block], i: int, pattern: str) -> str | None:
    """Why a command's clean output that matches the check is still not what the step asked for, else None:

    * it ran in another folder of the lesson than the one the step's files go in (a dev server of another project,
      a clone inside project1);
    * a test run of part of the suite (``pytest x.py::test_add``) for a step that runs every test;
    * the label names a ``git status`` section ("untracked", "staged") and the file is listed under another;
    * the label is about the home folder and the path printed is another user's folder (``/Users/Shared``);
    * the label says every / each / per and another row of the same shape doesn't match (``2 notes/summit.txt``)."""
    b = bl[i]
    label = str(check.get("label") or "")
    cmds = _scan_steps_cmds(check)
    segs = blocks.segments(b.command or "")
    if b.command and (where := _ran_elsewhere(check, ctx, bl, i)):
        return where
    for s in segs:
        for t in cmds:
            if blocks.runs(s, t) and blocks.narrows(s, t):
                return f"`{s}` ran only some of the tests; run `{t}`"
            if blocks.runs(s, t) and blocks.dry_run(s) and not blocks.dry_run(t):
                return f"`{s}` only showed what it would do (a dry run): run `{t}`"
            if blocks.runs(s, t) and (skipped := blocks.skipped_tests(b.output)) > _expected_skips(check) \
                    and _ALL_TESTS.search(str(check.get("_instructions") or "")) \
                    and (skipped > blocks.skipped_tests(b.output, in_files=True) or _learner_skips(ctx) is not False):
                # a skip the project ships in its test files (skipif) is exempt; deselected / todo tests are not: they
                # come from the command line (pytest -m "not slow") or are not tests yet
                return (f"{skipped} test(s) skipped, so not every test ran (a .only or .skip left in a test file?): "
                        f"remove it and run `{t}` again")
    if wrong := _commit_on_other_branch(cmds, bl, i, pattern):
        return wrong
    want = next((sec for word, sec in _GIT_SECTION_WORDS.items() if re.search(rf"\b{word}\b", label, re.I)), None)
    status_shown = any(blocks.git_section(e.rows, len(e.rows)) for e in bl)  # a git status listing is on screen
    if want and status_shown and not re.search(r"\b(?:un|not\s+)staged\b", label, re.I):
        rows = [k for k, r in enumerate(b.rows) if search_wrapped(pattern, r)]
        if not any(blocks.git_section(b.rows, k) == want for k in rows):
            return f"not listed under {want!r} in git status"
    if re.search(r"\bhome\b", label, re.I) and b.command is not None and (user := blocks.prompt_user(b.rows[0])):
        paths = [m for r in b.output if (h := search_screen(pattern, r)) and (m := _HOME_PATH.match(h.group(0)))]
        if paths and all(m.group(1) != user for m in paths):
            return f"{paths[-1].group(0).strip()} is not your home folder (/Users/{user})"
    if _UNIVERSAL_LABEL.search(label) and (shape_p := _LITERAL_NUMBER.sub(r"\\d+", pattern)) != pattern:
        try:
            shape, rx = safe_compile(shape_p, re.MULTILINE), safe_compile(pattern, re.MULTILINE)
        except re.error:
            return None
        for r in b.output:
            if shape.search(r) and not rx.search(r):
                return f"not every one: {r.strip()[:80]!r}"
    return None


_ALL_TESTS = re.compile(r"\b(?:every|all)\b[^.;]{0,30}\btests?\b|\btests?\b[^.;]{0,20}\ball\s+pass", re.I)
# a test file: Jest / Vitest / Mocha (x.test.ts, x.spec.js, __tests__/x.js), pytest / unittest (test_x.py, x_test.py)
_TEST_FILE = re.compile(r"(?:\.(?:test|spec)\.[cm]?[jt]sx?|^test_\w*\.py|_test\.py)$")
# a skip or focus a learner adds to a test file and can take out again: test.skip / it.only / xit / fdescribe,
# pytest's / unittest's unconditional skip. Never a conditional one a project ships (skipif, importorskip, a platform
# check), nor test.todo.
_LEARNER_SKIP = re.compile(r"\b(?:it|test|describe|context|suite)\.(?:only|skip)\s*\(|\b(?:xit|xtest|xdescribe|fit"
                           r"|fdescribe|xcontext)\s*\(|@pytest\.mark\.skip\b(?!if)|@unittest\.skip\b(?!If|Unless)")


def _expected_skips(check: dict) -> int:
    """How many skipped tests the step itself expects (its instructions or the check's pattern say "1 skipped"), else
    0: a suite that ships a skipped test says so."""
    text = f"{check.get('_instructions') or ''} {check.get('pattern') or ''}"
    return max((int(m.group(1)) for m in blocks._SKIPPED.finditer(text)), default=0)


def _learner_skips(ctx: RunContext) -> bool | None:
    """Did the learner skip tests? True when a test file in the lesson folder has a skip or focus the learner can
    remove (``test.skip``, ``it.only``, ``@pytest.mark.skip``) and the file was saved during the lesson (or the lesson's
    start is not known); False when the lesson's test files have none (the skips are platform skips the project
    ships: ``skipif``, ``importorskip``) or only files from before the lesson started have them; None when it can't
    tell (no lesson folder, no test file in it)."""
    if not os.path.isabs(str(ctx.workdir or "")):
        return None
    root, found, marked = os.path.abspath(ctx.workdir), False, []
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS]
        if os.path.relpath(here, root).count(os.sep) >= 5:
            dirs[:] = []
        for f in files:
            if not (_TEST_FILE.search(f) or (os.path.basename(here) == "__tests__"
                                             and re.search(r"\.[cm]?[jt]sx?$", f))):
                continue
            path = os.path.join(here, f)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read(FILE_SCAN_TOTAL)
            except OSError:
                continue
            found = True
            if _LEARNER_SKIP.search(text):
                marked.append(path)
    if not found:
        return None
    if not marked:
        return False
    if ctx.lesson_started_at is None:
        return True
    try:
        return any(os.path.getmtime(p) >= ctx.lesson_started_at for p in marked)
    except OSError:
        return True
_COMMIT_ROW = re.compile(r"^\s*\[([^\s\]]+)(?:\s+\(root-commit\))?\s+[0-9a-f]{7,40}\]")


def _commit_on_other_branch(cmds: list[str], bl: list[blocks.Block], i: int, pattern: str) -> str | None:
    """The step makes a branch of its own (its command is ``git switch -c add-waffles``) for the commit it checks, and
    the commit row the check matched (``[main 5d6e7f8] Add waffles``) went onto another branch, before that branch was
    made: the new branch has nothing the old one lacks."""
    made = {n for t in cmds for s in blocks.segments(t) if (n := blocks.new_branch(s))}
    if not made:
        return None
    for r in bl[i].output:
        m = _COMMIT_ROW.match(r)
        if not m or not search_wrapped(pattern, r) or m.group(1) in made:
            continue
        later = [n for b in bl[i + 1:] for s in blocks.segments(b.command or "") if (n := blocks.new_branch(s)) in made]
        if later:
            return f"that commit went onto {m.group(1)}, before {later[0]} was made: switch to {later[0]} first, then commit"
    return None


def _lesson_dirs(workdir: str, name: str, depth: int = 3) -> list[str]:
    """The folders of the lesson folder named ``name`` (case aside), as paths relative to it, ``depth`` levels down at
    most (never .git / node_modules / .venv)."""
    out: list[str] = []
    root = os.path.abspath(workdir)
    for here, dirs, _ in os.walk(root):
        rel = os.path.relpath(here, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", "__pycache__")]
        if level >= depth:
            dirs[:] = []
        for d in dirs:
            if d.casefold() == name.casefold():
                out.append(os.path.join(rel, d).replace(os.sep, "/").removeprefix("./"))
    return out


def _ran_elsewhere(check: dict, ctx: RunContext, bl: list[blocks.Block], i: int) -> str | None:
    """The step's own command ran with the prompt in a folder of the lesson that holds none of the files the step makes
    (its file_exists proofs) and isn't inside their folder: ``npm run dev`` in ~/shop for my-react-app, ``git clone`` in
    project1 for gitgoing/. None when it can't tell (the prompt shows no folder, or the folder is not in the lesson), or
    when an earlier command on screen made or named that folder (``npm create vite my-app``: the learner's own name
    for the step's project)."""
    b = bl[i]
    proof, cmds = check.get("_file_proof") or [], check.get("_target_cmds") or []
    if not proof or not cmds or not os.path.isabs(str(ctx.workdir or "")) or not b.rows:
        return None
    if not any(blocks.runs(s, t) for s in blocks.segments(b.command or "") for t in cmds):
        return None
    d = blocks.prompt_dir(b.rows[0])
    if not d or d in ("~", "/"):
        return None
    found = _lesson_dirs(str(ctx.workdir), d)
    if not found:
        return None
    for e in bl[:i]:
        for s in blocks.segments(e.command or ""):
            ws = blocks.words(s)
            if ws and blocks.program_and_sub(s)[0] != "cd" \
                    and any(w.rstrip("/").rsplit("/", 1)[-1].casefold() == d.casefold() for w in ws[1:]):
                return None
    for c in found:
        for p in proof:
            top = p.replace("\\", "/").strip("/").split("/")[0]
            pdir = os.path.dirname(p.replace("\\", "/").strip("/"))
            if pdir == c or pdir.startswith(c + "/") or (pdir and (c == top or c.startswith(top + "/"))):
                return None
    return f"`{b.command}` ran in {d}, not where {proof[0]} goes"


def _abandoned(check: dict, bl: list[blocks.Block]) -> str | None:
    """A command the step asks for by name ("commit the edit ... and push": ``git commit``) whose newest run failed
    (``no changes added to commit``) and was never run again: that part of the step never happened, whatever later
    commands printed."""
    text = str(check.get("_instructions") or "")
    progs = {blocks.program_and_sub(t)[0] for t in _scan_steps_cmds(check)} - {""}
    if not text or not progs:
        return None
    newest: dict[tuple[str, str], int] = {}
    for i, b in enumerate(bl):
        for s in blocks.segments(b.command or ""):
            p, sub = blocks.program_and_sub(s)
            if p in progs and sub and re.fullmatch(r"[a-z][\w-]*", sub) \
                    and re.search(rf"(?<![\w-]){re.escape(sub)}(?![\w-])", text, re.I):
                newest[(p, sub)] = i
    for i in newest.values():
        if (bad := bl[i].failure()) and not blocks.redundant(bl, i) and not blocks.cured(bl, i):
            return f"`{bl[i].command}` failed: {bad.strip()[:80]!r}"
    return None


def _ran_and_made(check: dict, ctx: RunContext, bl: list[blocks.Block]) -> CheckResult | None:
    """A terminal check whose words aren't on screen, passed on what the step's command made: its newest run (the
    step's Terminal target) shows no failure, and every file the step's precision checks expect exists (they are all
    file_exists: ``git init`` printed "Reinitialized existing Git repository", and project1/.git is there)."""
    proof, targets = check.get("_file_proof") or [], check.get("_target_cmds") or []
    if not proof or not targets or not os.path.isabs(str(ctx.workdir or "")):
        return None
    last = next((b for b in reversed(bl) if b.command
                 and any(blocks.runs(s, t) for s in blocks.segments(b.command) for t in targets)), None)
    if last is None or last.failure():
        return None
    paths = [_resolve(ctx.workdir, p) for p in proof]
    if not all(p and os.path.exists(p) for p in paths):
        return None
    return _result(check, "pass", f"ran `{last.command}`; {proof[0]} is there")


def _without_typed_input(text: str) -> str:
    """Terminal text without its bottom row when that row is a prompt with text after it: a command typed (or being
    typed) and not run yet. Only a row followed by more output, or by a new prompt, was executed. A multi-line
    command whose bottom rows are the shell's continuation rows (``dquote> to the menu"``, Enter not pressed yet, or
    the shell still waiting) loses those rows and the prompt row they continue: it has not run either."""
    lines = text.split("\n")
    last = max((i for i, ln in enumerate(lines) if ln.strip()), default=None)
    if last is None:
        return text
    if blocks.continuation(lines[last]):
        top = last  # the first of the bottom continuation rows: the row above it is the prompt row they continue
        while top > 0 and (not lines[top - 1].strip() or blocks.continuation(lines[top - 1])):
            top -= 1
        return "\n".join(lines[:max(top - 1, 0)] + lines[last + 1:])
    words = lines[last].split()
    if words and words[0] == "➜":  # oh-my-zsh: arrow, <dir>, [git:(branch)], [dirty mark], <command>
        rest = words[2:]
        if rest and rest[0].startswith("git:("):
            rest = rest[1:]
        if rest and rest[0] == "✗":
            rest = rest[1:]
        typed = bool(rest)
    else:
        typed = any(w not in _SHELL_JOIN and _after_prompt(w) for w in words[:-1])
    return "\n".join(lines[:last] + lines[last + 1:]) if typed else text


# a plot's own words, set in the cell's source: ax2.set_title('Class Probability'), plt.xlabel("Epoch"), ...
_PLOT_TEXT = re.compile(r"\b(?:set_title|suptitle|title|set_xlabel|set_ylabel|xlabel|ylabel|text|annotate|legend|"
                        r"set_label)\s*\(")


def _plotted(pattern: str, nb: Notebook) -> bool:
    """t10 (s6 "Class Probability title shown"): words that exist only inside a figure (a PNG output: no text the
    notebook holds, and OCR sees it only once the learner scrolls the plot into view). Passes when one of the step's
    cells ran without an error, displayed an image, and its source puts those words on the plot (set_title, xlabel,
    legend ...). OCR of the plot stays a second way to pass."""
    rx = _compile(pattern)
    for c in nb.cells:
        if not c.executed or c.errors or not any(str(m).startswith("image/") for m in c.images):
            continue
        if any(_PLOT_TEXT.search(ln) and rx.search(ln) for ln in scan_text(c.source).splitlines()):
            return True
    return False


_TRAILING_INTS = re.compile(r"(?:^|\s)(-?\d+(?:\s+-?\d+)+)\s*$")
MATRIX_MAX_ROWS = 200
MATRIX_MAX_RUN = 30  # rows one printed matrix spans at most (a 10-class confusion matrix is 10)


def _drawn_matrix(pattern: str, nb: Notebook, lines: list[str]) -> bool:
    """A matrix check written for numpy's printout (``[[13  0  1] [ 1 11  4] ...]``) on a matrix the step's cell drew
    as a figure (``ConfusionMatrixDisplay``, a heatmap): the figure's cells read on screen as rows of numbers (OCR:
    ``0 13 0 1`` with the row's tick label first, ``True label 1 1 11 4``). Consecutive rows ending in numbers are
    written as numpy prints them (their last N numbers each) and searched. Only when one of the step's cells ran
    without an error and displayed an image."""
    if r"\[\[" not in pattern and "[[" not in pattern:
        return False
    if not any(c.executed and not c.errors and any(str(m).startswith("image/") for m in c.images) for c in nb.cells):
        return False
    rows = [(m.group(1).split() if (m := _TRAILING_INTS.search(ln)) else None) for ln in lines[-MATRIX_MAX_ROWS:]]
    try:
        rx = _compile(pattern)
    except re.error:
        return False
    flat = re.sub(r"\\[sn][*+?]?|\\|\s", "", pattern)
    # a pattern that closes the matrix ("]]") matches only a text of exactly its rows: as many as it opens ("][" + 1)
    closes, size = "]]" in flat, flat.count("][") + 1
    i = 0
    while i < len(rows):
        if rows[i] is None:
            i += 1
            continue
        j = i
        while j < len(rows) and rows[j] is not None:
            j += 1
        run = rows[i:j]
        for a in range(len(run)):
            for n in range(2, len(run[a]) + 1):
                # the rows from a that have n numbers, at most MATRIX_MAX_RUN of them. A match starts at the text's
                # "[[", so the longest text holds every shorter one's match, unless the pattern closes the matrix:
                # then the text of its own number of rows (each end, when that number can't be read off it).
                k = a
                while k < len(run) and k - a < MATRIX_MAX_RUN and len(run[k]) >= n:
                    k += 1
                if k - a < 2:
                    break
                ends = (k,) if not closes else (a + size,) if size >= 2 else range(a + 2, k + 1)
                for b in ends:
                    if b > k:
                        continue
                    text = "[[" + "]\n [".join(" ".join(r[-n:]) for r in run[a:b]) + "]]"
                    if rx.search(text):
                        return True
        i = j
    return False


def _not_visible(check: dict, ctx: RunContext, absent: bool) -> CheckResult:
    """The check's app (or the whole screen) can't be seen. Never "pending forever":

    * screen_absent: nothing bad is visible, so once the segment is over it passes (a hidden
      Terminal can't be showing a Traceback). It fails only when the pattern is actually seen.
    * screen_contains: waiting can't help, so it says which app to open, and once the segment is
      over it fails with that hint (a fail is what lets the orchestrator's idle/stuck help fire).
      With no screen reading at all it stays pending: that's not the learner's fault.
    * A terminal check is graded on the step's last finished run instead (VS Code's command_end,
      `tut run`, Run it for me: the real output), and on a run step (``run``, set by evaluate_step)
      a screen_absent one waits for that run: nothing has run yet that could show the error (t3:
      "No Python error shown" passed 2 ms into the step, then stayed green over a SyntaxError).
    """
    app = check.get("app")
    no_screen = ctx.screen is None
    if app in _TERMINAL_APPS and ctx.run_finished:
        return _on_run_output(check, ctx, absent)
    if no_screen:
        # t9 V1: no frame yet (the reader resumes ~10 ms after step.started, or is off): nothing was looked at, so
        # nothing passes or fails. A screen_absent row passed "screen reading is off, so nothing to flag" and the
        # app kept it green (a pass never goes back to pending); the next real frame grades it.
        return _result(check, "pending", "checked when it runs" if absent and check.get("run") and app in _TERMINAL_APPS
                       else "waiting for the screen")
    if absent:
        if check.get("run") and app in _TERMINAL_APPS:
            return _result(check, "pending", "checked when it runs")
        if ctx.after_segment:
            why = f"{app} is not on screen" if app else "nothing on screen"
            return _result(check, "pass", f"{why}, so nothing to flag")
        return _result(check, "pending", f"{app} not open yet")
    if not app:
        hint = "nothing on screen yet"
    elif app in _TERMINAL_APPS and ctx.editor == "Code":  # a VS Code lesson runs code in VS Code's own terminal
        hint = "Open VS Code's terminal (⌃`) so I can check it."
    else:
        hint = f"Open {_APP_NAMES.get(app, app)} so I can check it."
    return _result(check, "fail" if ctx.after_segment and app else "pending", hint)


def _on_run_output(check: dict, ctx: RunContext, absent: bool) -> CheckResult:
    """A terminal check the screen can't read, graded on the output of the step's last finished run, and only when
    that run is the step's own command (a different script that printed the same line is not the learner's work)."""
    want = check.get("_run_command")
    if want and ctx.command and not command_matches(want, ctx.command):
        return _result(check, "pending", f"the last run was `{ctx.command}`; run `{want}`")
    try:
        m = search_screen(str(check.get("pattern") or ""), scan_text(ctx.output_text()))
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if absent:
        if _stopped(ctx):
            # t5: a run stopped by ^C prints "Traceback … KeyboardInterrupt": not the learner's error, and no verdict
            return _result(check, "pending", "it stopped before it finished: run it again")
        if m:
            return _result(check, "fail", f"the last run printed {m.group(0)[:80]!r}")
        return _result(check, "pass", "not in the last run's output")
    return _result(check, "pass", "printed by the last run") if m else \
        _result(check, "fail", "the last run didn't print it")


def _stopped(ctx: RunContext) -> bool:
    """The step's last run was stopped by Ctrl+C: exit 130, or its output ends with ^C / KeyboardInterrupt
    (server.orchestrator.terminal_run.interrupted's rule, kept here so the checks import nothing of the engine)."""
    if ctx.exit_code == 130:
        return True
    if ctx.exit_code == 0:
        return False
    tail = ctx.output_tail.splitlines() if isinstance(ctx.output_tail, str) else [str(x) for x in ctx.output_tail]
    return any(_CTRL_C_ROW.match(x) or _KEYBOARD_INTERRUPT.match(x) for x in tail[-3:])


_APP_NAMES = {"Code": "VS Code", "Terminal": "the Terminal", "iTerm2": "iTerm"}  # what the learner calls them
_TERMINAL_APPS = ("Terminal", "iTerm2")


def _app_name(app: str, ctx: RunContext) -> str:
    """What the learner calls the check's app; in a VS Code lesson the terminal is VS Code's own."""
    if app in _TERMINAL_APPS and ctx.editor == "Code":
        return "VS Code's terminal"
    return _APP_NAMES.get(app, app)


def _screen_contains(check: dict, ctx: RunContext) -> CheckResult:
    return _screen(check, ctx, absent=False)


def _screen_absent(check: dict, ctx: RunContext) -> CheckResult:
    # a search that timed out (or was skipped right after a strike) answers "no match" without having looked: an
    # absent row would pass while a Traceback may be showing, so it waits for the next frame instead
    with regex_worker.count_skips() as skipped:
        res = _screen(check, ctx, absent=True)
    if res["status"] == "pass" and skipped[0]:
        return _result(check, "pending", "couldn't finish checking in time: checking again")
    return res


def _visual(check: dict, ctx: RunContext) -> CheckResult:
    verdict = ctx.visual.get(str(check.get("id")))
    if not verdict:
        return _result(check, "pending", "awaiting visual check")
    status: CheckStatus = "pass" if verdict.get("pass") else "fail"
    return _result(check, status, str(verdict.get("detail", "")))


_HANDLERS = {
    "screen_contains": _screen_contains,
    "screen_absent": _screen_absent,
    "file_exists": _file_exists,
    "file_contains": _file_contains,
    "command_exit_ok": _command_exit_ok,
    "output_contains": _output_contains,
    "metric_threshold": _metric_threshold,
    "metric_trend": _metric_trend,
    "visual": _visual,
}
FILE_CHECK_TYPES = frozenset({"file_exists", "file_contains"})
SCREEN_CHECK_TYPES = frozenset({"screen_contains", "screen_absent"})
RUN_CHECK_TYPES = frozenset({"command_exit_ok", "output_contains", "metric_threshold", "metric_trend"})


def evaluate_check(check: dict, ctx: RunContext) -> CheckResult:
    handler = _HANDLERS.get(check.get("type", ""))
    if handler is None:
        return _result(check, "fail", f"unsupported check type {check.get('type')!r}")
    if why := unsafe_patterns(check):  # a lesson that skipped validation still never runs a catastrophic regex
        return _result(check, "fail", f"invalid pattern: {why}")
    try:
        return handler(check, ctx)
    except Exception as exc:  # noqa: BLE001 — a malformed check must never crash the engine
        return _result(check, "fail", f"check error: {type(exc).__name__}: {exc}")


CheckList = Literal["checks", "precision", "all"]


def evaluate_step(step: dict, ctx: RunContext | None = None, types: Iterable[str] | None = None,
                  screen: Any = None, which: CheckList = "checks") -> list[CheckResult]:
    """Evaluate a step's checks (or only those whose type is in ``types``).

    ``which`` picks the list: ``"checks"`` (default, the screen-gradable list that gates the
    step), ``"precision"`` (the optional ``precision_checks`` backups: file_*, command_exit_ok,
    ::metric:: names; only meaningful with a workdir or ``tut run``), or ``"all"`` (both).
    ``screen`` (a ScreenObservation) overrides ``ctx.screen``; ``ctx`` may be omitted.
    """
    ctx = ctx or RunContext()
    if screen is not None:
        ctx = dataclasses.replace(ctx, screen=screen)
    if which == "checks":
        checks = step.get("checks") or []
    elif which == "precision":
        checks = step.get("precision_checks") or []
    elif which == "all":
        checks = [*(step.get("checks") or []), *(step.get("precision_checks") or [])]
    else:
        raise ValueError(f"which must be 'checks', 'precision' or 'all', not {which!r}")
    wanted = set(types) if types is not None else None
    f = _step_file(step)  # a VS Code check not seen yet names the file the code goes in ("not in calculator.py yet")
    checks = [{**c, "file": f} if f and c.get("type") == "screen_contains" and c.get("app") == "Code"
              and not c.get("file") else c for c in checks]
    checks = [{**c, "_nb_file": f} if f and _is_kernel_check(c) else c for c in checks]  # t11: _saved_kernel reads it
    # a run step's "no error in the terminal" waits for the run (_not_visible) instead of passing on a hidden terminal
    run = step.get("kind") == "run" or any(str(t.get("file") or "").strip().lower() in ("(terminal)", "terminal")
                                           for t in step.get("targets") or []) or _command_step(step)
    checks = [{**c, "run": True} if run and c.get("type") == "screen_absent" and c.get("app") in _TERMINAL_APPS
              else c for c in checks]
    # the step's own terminal commands (its Terminal targets), and the files they make when that is all its precision
    # checks look for: _on_blocks / _ran_and_made read them
    # what the step is about, in its own words: a scene dump is read for the objects it names (model_files), and a file
    # it never names ("save it as a PNG next to mug.blend") may have any name
    about = " ".join(str(step.get(k) or "") for k in ("title", "instructions"))
    checks = [{**c, "_subject": f"{about} {c.get('label') or ''}"} if c.get("type") == "file_contains"
              and str(c.get("file") or "").lower().endswith(".json") else c for c in checks]
    # the step's own JSON code says where a config key goes (strict inside compilerOptions)
    if str(step.get("code") or "").strip().startswith("{"):
        checks = [{**c, "_json_code": step["code"]} if c.get("type") == "file_contains"
                  and str(c.get("file") or "").lower().endswith(".json") else c for c in checks]
    # a mesh the step prints must be a closed shell; a Markdown step's "# title" is one only in a Markdown cell
    checks = [{**c, "_print": True} if c.get("type") in FILE_CHECK_TYPES and str(c.get("file") or "").lower()
              .endswith(".stl") and model_files.PRINT_WORDS.search(f"{about} {c.get('label') or ''}") else c
              for c in checks]
    checks = [{**c, "_markdown": True} if c.get("type") == "file_contains" and str(c.get("file") or "").lower()
              .endswith(".ipynb") and re.search(r"\bmarkdown\b", f"{about} {c.get('label') or ''}", re.I) else c
              for c in checks]
    if which == "all":  # each list on its own: a file counts once in a list, and the lists are alternatives
        n = len(step.get("checks") or [])
        checks = [*_claim_any_names(checks[:n], about, ctx), *_claim_any_names(checks[n:], about, ctx)]
    else:
        checks = _claim_any_names(checks, about, ctx)
    own = blocks.programs_of(str(step.get("run_command") or ""))
    cmds = [str(t.get("match")).strip() for t in step.get("targets") or [] if t.get("app") in _TERMINAL_APPS
            and blocks.is_command(str(t.get("match") or ""), own)]
    prec = step.get("precision_checks") or []
    proof = [str(c.get("file")) for c in prec if c.get("file")] \
        if prec and all(c.get("type") == "file_exists" for c in prec) else []
    if cmds:
        checks = [{**c, "_target_cmds": cmds, **({"_file_proof": proof} if proof else {})}
                  if c.get("type") == "screen_contains" and c.get("app") in _TERMINAL_APPS else c for c in checks]
    checks = [{**c, "_instructions": about} if c.get("type") == "screen_contains" and c.get("app") in _TERMINAL_APPS
              else c for c in checks]
    if os.path.isabs(str(ctx.workdir or "")):  # the lesson folder: a code file's project config (path aliases)
        checks = [{**c, "_root": str(ctx.workdir)} if c.get("type") in ("screen_contains", "file_contains")
                  and c.get("app") not in _TERMINAL_APPS else c for c in checks]
    rc = str(step.get("run_command") or "").strip()
    if rc and not _CELL_ACTION.search(rc):  # a hidden terminal's output only counts when it is this command's run
        checks = [{**c, "_run_command": rc} if c.get("app") in _TERMINAL_APPS
                  and c.get("type") in ("screen_contains", "screen_absent") else c for c in checks]
    if sigs := signatures(step.get("code")):  # the step's own parameter names: a check reads add(x, y) as add(a, b)
        checks = [{**c, "_sigs": sigs} if c.get("type") in ("screen_contains", "file_contains")
                  and c.get("app") not in _TERMINAL_APPS else c for c in checks]
    ctx = _with_step_notebook(step, ctx)
    if isinstance(ctx.notebook, Notebook) and not str(step.get("code") or "").strip():
        # t10-flow's s1 (select the .venv kernel) has no cell of its own: the screen decides, never "when the cell runs"
        ctx = dataclasses.replace(ctx, notebook=False)
    code = "\n".join([str(step.get("code") or "")] + [str(t.get("match") or "") for t in step.get("targets") or []]
                     + (ctx.notebook.sources if isinstance(ctx.notebook, Notebook) else []))
    checks = [{**c, "_code": code} if c.get("type") == "screen_contains" and is_output_check(c) else c for c in checks]
    results = [evaluate_check(c, ctx) for c in checks if wanted is None or c.get("type") in wanted]
    return _no_cell_yet(step, checks, results, ctx)


def _no_cell_yet(step: dict, checks: list[dict], results: list[CheckResult], ctx: RunContext) -> list[CheckResult]:
    """t11 (CP4, s2): "No import or load errors · not showing in VS Code" passed 0.4 s into the step, before the
    learner's notebook existed: with no notebook on disk the step's cell can't have run, so a screen_absent row (an
    error the cell would print) has nothing to grade. It waits ("checked when the cell runs") until the step's code is
    at least on screen (every code row passes: a notebook that lives only in a browser still gets graded then).
    Only on a notebook step with code whose lesson folder was searched and held no notebook."""
    if ctx.notebook is not False or not str(step.get("code") or "").strip() or not is_notebook_step(step) \
            or not os.path.isabs(str(ctx.workdir or "")):
        return results
    absent = {str(c.get("id")) for c in checks if c.get("type") == "screen_absent" and c.get("app") not in _TERMINAL_APPS}
    if not any(r["checkId"] in absent and r["status"] == "pass" for r in results):
        return results
    code_rows = [c for c in checks if c.get("type") == "screen_contains" and c.get("app") not in _TERMINAL_APPS
                 and not is_output_check(c) and not _is_kernel_check(c)]
    if not code_rows:  # nothing would ever see the code (a Colab / browser notebook): the screen decides, as before
        return results
    if all(evaluate_check(c, ctx)["status"] == "pass" for c in code_rows):
        return results
    return [{**r, "status": "pending", "detail": "checked when the cell runs"}
            if r["checkId"] in absent and r["status"] == "pass" else r for r in results]


_NOTEBOOK_RUN = re.compile(r"shift\s*\+\s*enter|\bcells?\b|\bnotebook\b|\bjupyter\b|\bcolab\b", re.I)
# printed / shown results, never "output layer" / "print statement" (t9: s4c4 "Softmax output layer added" is code)
_OUTPUT_LABEL = re.compile(r"\b(printed|prints|shown|shows|displayed|logged|rendered|plotted)\b"
                           r"|\b(cell|run|program|console|terminal|printed|progress)\s+output\b"
                           r"|\boutput\s+(shown|printed|appears|visible|displayed)\b", re.I)
# a pattern that looks like code: an escaped ( ) or =, an attribute dot (mnist\.load_data), a CamelCase name
_CODE_PATTERN = re.compile(r"\\[()]|=|\\\.[A-Za-z_]|[a-z][A-Z]")
# a JSX / HTML tag in a pattern (<Header, <\/footer), on a step whose file is markup or a component
_MARKUP_TAG = re.compile(r"<\\?/?\s*[A-Za-z]")
_MARKUP = (".jsx", ".tsx", ".html", ".htm", ".vue", ".svelte", ".astro")
# a code line on screen: a print( call, a string literal opening after ( or closing before , / ), an f-string
_CODE_MARK = re.compile(r"\bprint\s*\(|\(\s*[fbr]?['\"]|['\"]\s*[,)]|\bf['\"]")


def _with_step_notebook(step: dict, ctx: RunContext) -> RunContext:
    """ctx with the step's notebook: read from the lesson folder on a notebook step (t9), then narrowed to the cells
    holding the step's own code (t10: its output / error / metric checks never read another cell's output; s7
    "evaluate progress output shown" passed on the training cell's progress bars). Idempotent."""
    if ctx.notebook is None and is_notebook_step(step) and os.path.isabs(str(ctx.workdir or "")):
        ctx = dataclasses.replace(ctx, notebook=read_notebook(find_notebook(ctx.workdir, _files(step))) or False)
    if isinstance(ctx.notebook, Notebook) and ctx.notebook.cells:
        ctx = dataclasses.replace(ctx, notebook=ctx.notebook.only(step_cells(ctx.notebook, step)))
    return ctx


_RUN_THE_CELL = re.compile(r"shift\s*\+\s*enter|\brun\s+(?:the|this|each|all|every)\s+cells?\b", re.I)


def cell_not_run(step: dict, ctx: RunContext | None) -> bool:
    """t10 (CP7: s2 passed with its corrected cell written but never run): a "Run the cell (Shift+Enter)" step whose
    code is in the notebook, in cells none of which has run (no execution count, no output). Such a step can't pass,
    whichever list or route says green."""
    if ctx is None or not _RUN_THE_CELL.search(str(step.get("run_command") or "")):
        return False
    nb = _with_step_notebook(step, ctx).notebook
    if not isinstance(nb, Notebook) or not nb.cells:
        return False
    # every one of its cells: "run both" with the second still unrun is not done. An unrun copy of a cell below it
    # that ran (an abandoned attempt above: each of its lines is in that cell) is not another cell to run; an unrun
    # copy below the one that ran is the user's new cell (its output on screen is the older cell's), so it still counts.
    # A cell the file has as unrun but the editor shows with a run count ([4]) ran since the notebook was last saved:
    # an unsaved notebook is not an unrun cell (no Cmd+S chores)
    lines = screen_lines(ctx.screen, "Code") if ctx.screen is not None else None
    cells = [(_code_lines(c.source), c.executed or _count_on_screen(c.source, lines)) for c in nb.cells
             if c.source.strip()]
    if not any(done for _, done in cells):
        return True
    return any(not done and not any(ran and mine <= theirs for theirs, ran in cells[k + 1:])
               for k, (mine, done) in enumerate(cells))


_RUN_COUNT_ROW = re.compile(r"^\s*\[\s*\d+\s*\]\s*:?\s*$")


def _count_on_screen(source: str, lines: list[str] | None) -> bool:
    """Does the editor show this cell with a run count: a ``[4]`` row right above the cell's first line?"""
    first = next((" ".join(ln.split()) for ln in source.splitlines() if ln.strip()), "")
    if not lines or not first:
        return False
    rows = [" ".join(str(ln).split()) for ln in lines]
    return any(r == first and any(_RUN_COUNT_ROW.match(p) for p in rows[max(0, k - 2):k])
               for k, r in enumerate(rows))


def _code_lines(src: str) -> set[str]:
    """A cell's non-blank lines with every space taken out: an unrun cell is a copy of another when all of its lines
    are in that one."""
    return {"".join(ln.split()) for ln in src.splitlines() if ln.strip()}


# methods that only read an object (show it, summarise it, plot it, predict with it): a statement calling one leaves
# it as it was. Any other method a statement calls on a name (model.fit / add / compile / to, df.dropna(inplace=True))
# may change it, so it sets that name up as much as binding it does.
_READ_ONLY_METHODS = frozenset("""
    summary describe head tail info show imshow plot print display render repr count value_counts nunique unique
    isna isnull notna notnull mean median std var sum min max corr cov hist scatter bar barh pie boxplot
    figure subplot subplots title suptitle xlabel ylabel set_title set_xlabel set_ylabel legend grid xticks yticks
    tight_layout colorbar axis savefig evaluate predict predict_proba score get_params get_config count_params
    parameters named_parameters state_dict to_csv to_json to_excel to_numpy tolist keys values items get
""".split())


def _py_names(src: str) -> tuple[set[str], set[str], set[str]] | None:
    """(names a cell's code binds, names it binds or changes, names it reads): assignment targets, def / class / import
    names; changed, too, a name a statement calls a method on that isn't in _READ_ONLY_METHODS (``model.add(...)``,
    ``history = model.fit(...)``, ``df.dropna(inplace=True)`` change ``model`` / ``df``; ``model.summary()`` doesn't),
    or assigns an item or attribute of (``df['b'] = ...``, ``layer.trainable = False``). IPython magics and shell
    lines are left out. None when it doesn't parse."""
    code = "\n".join("pass" if ln.lstrip().startswith(("%", "!")) else ln for ln in src.splitlines())
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return None
    writes: set[str] = set()
    reads: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            (writes if isinstance(node.ctx, ast.Store) else reads).add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            writes.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            writes |= {(a.asname or a.name).split(".")[0] for a in node.names}
    changes = set(writes)
    for stmt in tree.body:
        call = stmt.value if isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign)) else None
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) \
                and isinstance(call.func.value, ast.Name) and call.func.attr not in _READ_ONLY_METHODS:
            changes.add(call.func.value.id)
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] \
            if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)) else []
        for t in targets:
            while isinstance(t, (ast.Subscript, ast.Attribute)):
                t = t.value
            if isinstance(t, ast.Name):
                changes.add(t.id)
    return writes, changes, reads


def stale_inputs(step: dict, ctx: RunContext | None) -> str | None:
    """A notebook step's cell ran in a kernel where a cell above it, that sets up what it uses, had not run: after a
    restart the counts [1], [2], [3] above and the step's cell at [4] are that kernel's whole history, so the training
    cell still showing [19] (from the kernel before) never ran in it, and the model that predicted was never trained.
    Why, else None. Only when the counts before the step's cell's own are all on cells above it (nothing else can have
    run in that kernel).

    A cell above that didn't run before it is blamed when it binds or changes a name the step's cell uses, unless it
    is a copy of a cell that did run (each of its lines is in that cell: an unrun duplicate of
    ``df = pd.read_csv(...)``). Another cell that ran binding the same name doesn't excuse it (``df = df.dropna()``
    never run after ``df = pd.read_csv(...)`` ran). A cell that only reads a name (``model.summary()``,
    ``plt.imshow(...)``, ``print(model)``) is never blamed."""
    if ctx is None or not os.path.isabs(str(ctx.workdir or "")):
        return None
    nb = ctx.notebook if isinstance(ctx.notebook, Notebook) else None
    if nb is None or not nb.cells:
        nb = read_notebook(find_notebook(ctx.workdir, _files(step)))
    if nb is None or not nb.cells:
        return None
    for i in step_cells(nb, step):
        cell = nb.cells[i]
        if cell.count is None or not cell.executed:
            continue
        above = [c for c in nb.cells[:i] if c.source.strip()]
        if not all(any(c.count == k for c in above) for k in range(1, cell.count)):
            continue
        mine = _py_names(cell.source)
        if mine is None:
            continue
        ran = [_code_lines(c.source) for c in [*above, cell] if c.count is not None and c.count <= cell.count]
        for c in above:
            if c.count is not None and c.count <= cell.count:  # ran before it (an equal count: can't tell)
                continue
            theirs = _py_names(c.source)
            if not theirs or any(_code_lines(c.source) <= r for r in ran):
                continue
            need = sorted((theirs[1] & mine[2]) - mine[0])
            if need:
                when = f"[{c.count}], from before a kernel restart" if c.count is not None else "never run"
                first = c.source.strip().splitlines()[0][:60]
                return (f"the cell that sets up {need[0]} ({first!r}, {when}) didn't run before this one: run it, "
                        f"then this cell again")
    return None


def _step_notebook(step: dict, ctx: RunContext | None) -> Notebook | None:
    if ctx is None or not os.path.isabs(str(ctx.workdir or "")):
        return None
    nb = read_notebook(find_notebook(ctx.workdir, _files(step)))
    return nb if nb is not None and nb.cells else None


def _first_line(src: str) -> str:
    return next((ln.strip() for ln in src.splitlines() if ln.strip()), "")[:60]


def undone_setup(step: dict, ctx: RunContext | None) -> str | None:
    """A cell above the step's cell that changes something the step's cell uses (``model.fit(...)`` trains ``model``)
    ran, and then a cell above IT that binds that name afresh ran again (the model cell re-run "to look at it": a new
    network with random weights): the step's cell then used the fresh one, and the change is gone. Their counts say so
    ([4] the fit, [5] the model cell above it, [6] the predict). Why, else None."""
    nb = _step_notebook(step, ctx)
    if nb is None:
        return None
    for i in step_cells(nb, step):
        cell = nb.cells[i]
        mine = _py_names(cell.source) if cell.count is not None and cell.executed else None
        if mine is None:
            continue
        uses = mine[2] - mine[0]
        before = [(k, c, _py_names(c.source)) for k, c in enumerate(nb.cells[:i])
                  if c.count is not None and c.count < cell.count and c.source.strip()]
        for ka, a, na in before:
            if not na:
                continue
            for name in sorted((na[1] - na[0]) & uses):  # it changes the name (a method call) without binding it
                for kb, b, nbs in before:
                    if kb < ka and nbs and name in nbs[0] and b.count > a.count:
                        return (f"{_first_line(b.source)!r} ran again ([{b.count}]) after {_first_line(a.source)!r} "
                                f"([{a.count}]) and made a new {name}: run {_first_line(a.source)!r} again, then this "
                                f"cell")
    return None


def _self_updates(src: str) -> set[str]:
    """Names a cell's code computes from themselves with arithmetic (``x = x.astype('float32') / 255``, ``x += 1``,
    ``x = (x - mean) / std``): running the cell again applies it again."""
    code = "\n".join("pass" if ln.lstrip().startswith(("%", "!")) else ln for ln in src.splitlines())
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return set()
    out: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            out.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) \
                and isinstance(stmt.value, ast.BinOp):
            n = stmt.targets[0].id
            if any(isinstance(x, ast.Name) and x.id == n and isinstance(x.ctx, ast.Load) for x in ast.walk(stmt.value)):
                out.add(n)
    return out


def rerun_self_update(step: dict, ctx: RunContext | None) -> str | None:
    """The step's cell rewrites what it uses from itself (``train_images = train_images.astype('float32') / 255``) and
    its run count says it ran again and again since the cell that made that value last ran: the counts between the two
    are on no cell ([1] the load, then [4] here: [2] and [3] were this cell too), so the arithmetic was applied three
    times. Why, else None.

    A missing count is only this cell's when nothing else can have taken it: no cell above this one has run since the
    maker (a count above the maker's on a cell between the two: an inspect cell re-run, ``plt.imshow(x[0])`` [4], may
    have taken [2] too). A cell below this one with a higher count ran after it (the next step's cell, [5]): it
    explains nothing in the gap. And one missing count alone is not blamed: a run that raised before its assignment (a typo fixed, then
    re-run) or a deleted scratch cell leaves the same [1], [3]. Two or more (three runs, none of them on another cell)
    are."""
    nb = _step_notebook(step, ctx)
    if nb is None:
        return None
    counts = {c.count for c in nb.cells if c.count is not None}
    for i in step_cells(nb, step):
        cell = nb.cells[i]
        if cell.count is None or not cell.executed:
            continue
        for name in sorted(_self_updates(cell.source)):
            makers = [c.count for k, c in enumerate(nb.cells) if k != i and c.count is not None and c.count < cell.count
                      and (names := _py_names(c.source)) and name in names[0]]
            if not makers:
                continue
            made = max(makers)
            if any(c.count is not None and c.count > made for c in nb.cells[:i]):
                continue  # a cell above this one ran after the maker: it may have taken the missing counts too
            gap = [k for k in range(made + 1, cell.count) if k not in counts]
            if len(gap) >= 2 and len(gap) == cell.count - made - 1:
                return (f"this cell ran {len(gap) + 1} times since {name} was made ([{max(makers)}]), so "
                        f"{_first_line(cell.source)!r} was applied {len(gap) + 1} times: run the cell that makes "
                        f"{name} again, then this cell once")
    return None


def _broken_imports(step: dict, ctx: RunContext | None) -> list[str]:
    """server.checks.code_equiv.broken_imports over the step's code files in the lesson folder: its targets', checks'
    and own file, and the files its check labels name ("main.py calls add_numbers(2, 3)")."""
    if ctx is None or not os.path.isabs(str(ctx.workdir or "")):
        return []
    files = [f for f in _files(step) if code_equiv.kind_of(f)]
    files += [f for c in [*(step.get("checks") or []), *(step.get("precision_checks") or [])]
              if (f := code_equiv.file_in_label(str(c.get("label") or "")))]
    if not files:
        return []
    try:
        return code_equiv.broken_imports(ctx.workdir, list(dict.fromkeys(files)))
    except (OSError, ValueError, RecursionError):
        return []


def _scene_claims(step: dict, ctx: RunContext | None) -> list[str]:
    """model_files.claims over the JSON scene dumps the step's file checks read: what its own words compare between two
    of the scene's things that the saved scene contradicts."""
    if ctx is None or not os.path.isabs(str(ctx.workdir or "")):
        return []
    file_checks = [c for c in [*(step.get("checks") or []), *(step.get("precision_checks") or [])]
                   if c.get("type") in FILE_CHECK_TYPES and str(c.get("file") or "").lower().endswith((".json", ".dxf"))]
    # the step's words and its file checks' labels ("Cube at X 2", "Dimension reads 120")
    text = " ".join([*(str(step.get(k) or "") for k in ("title", "instructions", "what", "action")),
                     *(f"{c.get('label') or ''}." for c in file_checks)])
    out: list[str] = []
    for rel in sorted({str(c.get("file")) for c in file_checks}):
        path = _resolve(ctx.workdir, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                raw = fh.read(FILE_SCAN_TOTAL)
            if rel.lower().endswith(".dxf"):
                out += model_files.dxf_claims(text, raw)
                continue
            doc = json.loads(model_files.scene_view(raw, text) or raw)
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict):
            out += model_files.claims(text, doc)
    return out


# VS Code's status bar problem counts: "⊗ 1 ⚠ 0" (errors, then warnings); OCR reads the circled x a few ways
_PROBLEM_COUNT = re.compile(r"(?:⊗|Ⓧ|ⓧ|✖|⨂|⊘)\s*(\d+)\s*(?:⚠|△|▲|⚠️)\s*\d+")
_TSC = re.compile(r"(?<![\w-])tsc(?![\w-])")
# a TypeScript diagnostic on screen: VS Code's Problems panel / hover ("... ts(2345)"), tsc's "error TS2345:"
_TS_DIAGNOSTIC = re.compile(r"\bts\(\d{3,5}\)|\berror\s+TS\d{3,5}\b")
# another checker's row in the Problems panel (it feeds the same status-bar count)
_OTHER_DIAGNOSTIC = re.compile(r"\b(?:Pylance|Pyright|pylint|flake8|[Rr]uff|mypy|ESLint|eslint|stylelint|rust-analyzer"
                               r"|gopls|clangd|cSpell)\b|\(report[A-Z]\w+\)")
# a lesson folder's files another language server or linter checks (its errors count in the status bar too)
_OTHER_SOURCES = (".py", ".ipynb", ".go", ".rs", ".java", ".kt", ".c", ".cc", ".cpp", ".h", ".cs", ".rb", ".php",
                  ".swift", ".scala", ".lua", ".r", ".dart")
_LINTER_CONFIG = re.compile(r"^(?:\.eslintrc(?:\.\w+)?|eslint\.config\.[cm]?[jt]s|\.stylelintrc(?:\.\w+)?)$")
_SKIP_DIRS = frozenset({"node_modules", "dist", "build", "out", "venv", "__pycache__"})


def _count_is_typescript(code_text: str, ctx: RunContext) -> bool:
    """Is VS Code's status-bar error count tsc's? The count covers the whole workspace in every language (Pylance on a
    .py file, ESLint, another project's file), so it is taken as tsc's when a TypeScript error is on screen (the
    Problems panel's ``ts(2345)``, the terminal's ``error TS2345:``), else only when nothing else can have made it: no
    other checker's row on screen, and no file in the lesson folder another checker reads (a .py file, an ESLint
    config).

    The tradeoff: any ESLint config (``eslint.config.js`` ships with Vite's react-ts template) or any .py file in the
    lesson folder turns this status-bar rule off unless a ``ts(NNNN)`` / ``error TSNNNN`` is on screen too, so a tsc
    error seen only as the status-bar count then passes; a Pylance or ESLint error never fails a tsc step."""
    term = "\n".join(t for app in _TERMINAL_APPS if (t := screen_text(ctx.screen, app)))
    if _TS_DIAGNOSTIC.search(code_text) or _TS_DIAGNOSTIC.search(term):
        return True
    if _OTHER_DIAGNOSTIC.search(code_text):
        return False
    if not os.path.isabs(str(ctx.workdir or "")):
        return True
    root, seen = os.path.abspath(ctx.workdir), 0
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS]
        if os.path.relpath(here, root).count(os.sep) >= 4:
            dirs[:] = []
        for f in files:
            seen += 1
            if f.lower().endswith(_OTHER_SOURCES) or _LINTER_CONFIG.match(f):
                return False
        if seen > 2000:
            break
    return True


def editor_problems(step: dict, ctx: RunContext | None) -> str | None:
    """A TypeScript step (it compiles with tsc, or its code is a .ts / .tsx file it says must have no errors) whose
    VS Code status bar counts errors (``⊗ 1``): tsc reports the same errors, whatever the terminal shows now (cleared,
    or only the ``node dist/...`` run after it: tsc still writes the .js when there are errors), when the count is
    tsc's (_count_is_typescript: not a Pylance or ESLint error elsewhere in the workspace). Why, else None."""
    if ctx is None or ctx.screen is None:
        return None
    ts_file = _step_file(step).lower().endswith((".ts", ".tsx", ".mts", ".cts"))
    error_check = any(c.get("type") == "screen_absent" and re.search(r"error|TS", str(c.get("pattern") or ""))
                      for c in step.get("checks") or [])
    if not (_TSC.search(str(step.get("run_command") or "")) or (ts_file and error_check)):
        return None
    m = None
    code_text = screen_text(ctx.screen, "Code") or ""
    for m in _PROBLEM_COUNT.finditer(code_text):
        pass
    if m is None or int(m.group(1)) == 0:
        return None
    if not _count_is_typescript(code_text, ctx):
        return None
    n = int(m.group(1))
    return f"VS Code shows {n} error{'s' if n != 1 else ''} in the code (⊗ {n}): fix it, then compile again"


_RUN_ALL = re.compile(r"\brun\s+all\b|\brestart\b.{0,40}\brun\b", re.I)


def run_all_out_of_order(step: dict, ctx: RunContext | None) -> str | None:
    """A "Restart the kernel and run all" step: the notebook's code cells must have run top to bottom in one go, so
    their run counts go up in cell order starting at [1] (the counts [1], [5], [4] mean cells re-run by hand,
    bottom-up, without a restart). Why it isn't so, else None (not such a step, or no notebook to read)."""
    if ctx is None or not _RUN_ALL.search(str(step.get("run_command") or "")) \
            or not os.path.isabs(str(ctx.workdir or "")):
        return None
    nb = ctx.notebook if isinstance(ctx.notebook, Notebook) else read_notebook(find_notebook(ctx.workdir, _files(step)))
    cells = [c for c in (nb.cells if nb is not None else []) if c.source.strip()]
    if not cells:
        return None
    if any(c.count is None for c in cells):
        return "not every cell has run: Restart, then Run All"
    counts = [c.count for c in cells]
    if counts[0] != 1 or any(b <= a for a, b in zip(counts, counts[1:])):
        shown = ", ".join(f"[{n}]" for n in counts)
        return f"the run counts read {shown}: Restart the kernel, then Run All so they go 1, 2, 3"
    # Run All stops at the first cell that raises: its error is in the notebook even when it is scrolled off screen
    if bad := next((c for c in cells if c.errors), None):
        return f"cell [{bad.count}] stopped with {bad.errors[0].splitlines()[0][:80]!r}: fix it, then Restart and Run All"
    return None


_CELL_ACTION = re.compile(r"shift\s*\+\s*enter|^\s*(?:run|execute|press|click)\s+(?:the|a|all|each|this)\b", re.I)


def _command_step(step: dict) -> bool:
    """A step whose work is a shell command (no code to type): its "No terminal errors" waits for that run instead of
    passing on a hidden terminal (t10: s1 "source .venv/bin/activate && jupyter notebook"). Never "Run the cell"."""
    rc = str(step.get("run_command") or "").strip()
    return bool(rc) and not _CELL_ACTION.search(rc) and not str(step.get("code") or "").strip()


def _anchors(step: dict) -> tuple[list[re.Pattern[str]], list[re.Pattern[str]]]:
    """The step's own code as patterns: (its targets' match text, whitespace aside; its code checks' regexes, never an
    output check's (that is what it prints), plus its notebook file_contains patterns)."""
    def rx(p: str) -> re.Pattern[str] | None:
        try:
            return _compile(p)
        except re.error:
            return None

    targets = []
    for t in step.get("targets") or []:
        flat = "".join(str(t.get("match") or "").split())
        if len(flat) >= 6:
            targets.append(rx(r"\s*".join(re.escape(ch) for ch in flat)))
    code = [rx(str(c["pattern"])) for c in step.get("checks") or [] if c.get("type") == "screen_contains"
            and c.get("pattern") and c.get("app") not in _TERMINAL_APPS and not is_output_check(c)]
    code += [rx(str(c["pattern"])) for c in step.get("precision_checks") or [] if c.get("type") == "file_contains"
             and c.get("pattern") and str(c.get("file") or "").lower().endswith(".ipynb")]
    return [r for r in targets if r], [r for r in code if r]


def step_cells(nb: Notebook, step: dict) -> list[int]:
    """t10: indices (into nb.cells) of the code cells holding the step's own code. The cells with its target text
    (model.fit(, plt.subplots(1, 10 ...) plus any cell with two or more of its code patterns; when no cell has the
    target text, any cell with one of its code patterns (s3's plt.subplots( is in s6's view_classify too, so a lone
    code pattern only counts without a target match). No patterns at all: a line of its `code`. [] = not there yet."""
    targets, code = _anchors(step)

    def hits(rxs: list[re.Pattern[str]], src: str) -> int:
        src = scan_text(src)
        flat = re.sub(r"\s+", " ", src)
        return sum(1 for r in rxs if r.search(src) or r.search(flat))

    lines = {" ".join(ln.split()) for ln in str(step.get("code") or "").splitlines() if len(ln.strip()) >= 16}
    by_line = [i for i, c in enumerate(nb.cells) if lines and any(" ".join(ln.split()) in lines
                                                                  for ln in c.source.splitlines())]
    by_target = [i for i, c in enumerate(nb.cells) if hits(targets, c.source)]
    if by_target:
        # its code may span cells ("one with %timeit sum(steps), and one that makes steps_array ..."): a cell holding a
        # whole line of the step's code, right after the step's own cells, is one of them too
        own = set(by_target) | {i for i, c in enumerate(nb.cells) if hits(code, c.source) >= 2}
        for i in by_line:
            if i - 1 in own:
                own.add(i)
        return sorted(own)
    if code:
        return [i for i, c in enumerate(nb.cells) if hits(code, c.source)]
    return by_line


def _files(step: dict) -> list[str]:
    return [str(x.get("file") or "") for x in [*(step.get("targets") or []), *(step.get("checks") or []),
                                               *(step.get("precision_checks") or [])]] + [str(step.get("file") or "")]


def is_notebook_step(step: dict) -> bool:
    """A step done in a Jupyter notebook: a target / check file is an .ipynb, or its run is a cell run."""
    if any(f.strip().lower().endswith(".ipynb") for f in _files(step)):
        return True
    return bool(_NOTEBOOK_RUN.search(str(step.get("run_command") or "")))


def is_output_check(check: dict) -> bool:
    """t9 V3: a screen_contains check about what the code PRINTS ("Image shape line printed"), graded on output only,
    never on the code that prints it. An explicit ``output`` (bool) on the check decides; else its label says so
    (printed / output / shown / displayed ...). Terminal checks keep their own rules."""
    if check.get("type") != "screen_contains" or check.get("app") in _TERMINAL_APPS:
        return False
    if isinstance(check.get("output"), bool):
        return check["output"]
    if _CODE_PATTERN.search(str(check.get("pattern") or "")):
        return False  # a pattern for code (model\.predict\(): a code check, whatever its label says
    if _MARKUP_TAG.search(str(check.get("pattern") or "")) and str(check.get("file") or "").lower().endswith(_MARKUP):
        return False  # "Header component rendered" = <Header in App.jsx: a component is rendered by the code that uses it
    return bool(_OUTPUT_LABEL.search(str(check.get("label") or "")))


def _code_line(line: str, code: str | None) -> bool:
    """Is this OCR line the learner's code rather than output? A print( / string-literal line, or a whole line of the
    step's code / the notebook's cells (whitespace aside)."""
    if _CODE_MARK.search(line):
        return True
    norm = " ".join(line.split())
    return bool(norm) and any(norm == " ".join(c.split()) for c in (code or "").splitlines())


def _step_file(step: dict) -> str:
    """The step's file (its first target's, check's or own ``file``), for the learner-worded details. A run step's
    "(terminal)" / "terminal" is a place, not a file."""
    names = [t.get("file") for t in step.get("targets") or []]
    names += [c.get("file") for c in (step.get("checks") or []) + (step.get("precision_checks") or [])]
    for n in [*names, step.get("file")]:
        n = str(n or "").strip()
        if n and not n.startswith("(") and n.lower() not in ("terminal", "the terminal", "shell"):
            return n
    return ""


class StepGate(TypedDict):
    passed: bool
    via: Literal["checks", "precision"] | None
    checks: list[CheckResult]
    precision: list[CheckResult]


def evaluate_gate(step: dict, ctx: RunContext | None = None, screen: Any = None,
                  precision_mode: bool = False) -> StepGate:
    """Does the step pass? The one call the orchestrator needs.

    * Screen mode (default): only ``checks`` are evaluated and they alone decide.
      ``precision_checks`` are not evaluated, so they can never block the step.
    * Precision mode: both lists are evaluated; the step passes when ALL ``checks`` pass
      OR (``precision_checks`` is non-empty and ALL of them pass). Precision is an extra
      route to green (e.g. OCR misses a line), never an extra hurdle.
    """
    checks = evaluate_step(step, ctx, screen=screen, which="checks")
    prec = evaluate_step(step, ctx, screen=screen, which="precision") if precision_mode else []
    if cell_not_run(step, ctx):
        # t10: typed is not run. When no row already says why (an error / output check waits for the run), one does.
        if step_passed(checks):
            checks = [*checks, {"checkId": f"{step.get('id', '')}-cell", "label": "Cell run", "status": "pending",
                                "detail": "run the cell (Shift+Enter)"}]
        return {"passed": False, "via": None, "checks": checks, "precision": prec}
    if (step_passed(checks) or step_passed(prec)) and is_notebook_step(step) and ctx is not None:
        # the kernel that ran the step's cell is gone, or ran it without a cell above it that the cell needs
        crash = _kernel_crashed(ctx)
        why = f"{crash} on screen: restart the kernel and run the notebook again" if crash else (
            stale_inputs(step, ctx) or undone_setup(step, ctx) or rerun_self_update(step, ctx))
        if why:
            checks = [*checks, {"checkId": f"{step.get('id', '')}-kernel", "label": "The kernel has what the cell needs",
                                "status": "fail", "detail": why}]
            return {"passed": False, "via": None, "checks": checks, "precision": prec}
    if (step_passed(checks) or step_passed(prec)) and (broken := _broken_imports(step, ctx)):
        # the step's files look finished, but one imports what its module no longer has: it crashes when run
        checks = [*checks, {"checkId": f"{step.get('id', '')}-imports", "label": "Imports resolve",
                            "status": "fail", "detail": broken[0]}]
        return {"passed": False, "via": None, "checks": checks, "precision": prec}
    if (step_passed(checks) or step_passed(prec)) and (wrong := _scene_claims(step, ctx)):
        # every fact the checks look for is there, but the step's own comparison ("Key at least twice the Fill's
        # power") is not what the saved scene says
        checks = [*checks, {"checkId": f"{step.get('id', '')}-scene", "label": "Scene matches the step",
                            "status": "fail", "detail": wrong[0]}]
        return {"passed": False, "via": None, "checks": checks, "precision": prec}
    if (step_passed(checks) or step_passed(prec)) and (problems := editor_problems(step, ctx)):
        # the terminal looks clean (cleared, or only the run after the compile is on screen), but VS Code counts errors
        checks = [*checks, {"checkId": f"{step.get('id', '')}-problems", "label": "No problems in the code",
                            "status": "fail", "detail": problems}]
        return {"passed": False, "via": None, "checks": checks, "precision": prec}
    if (order := run_all_out_of_order(step, ctx)) is not None:
        checks = [*checks, {"checkId": f"{step.get('id', '')}-order", "label": "Cells ran in order from [1]",
                            "status": "fail", "detail": order}]
        return {"passed": False, "via": None, "checks": checks, "precision": prec}
    if step_passed(checks):
        via: Literal["checks", "precision"] | None = "checks"
    elif precision_mode and step_passed(prec):
        via = "precision"
    else:
        via = None
    return {"passed": via is not None, "via": via, "checks": checks, "precision": prec}


def step_passed(results: list[CheckResult]) -> bool:
    """A step passes only when it has checks and ALL of them pass."""
    return bool(results) and all(r["status"] == "pass" for r in results)


# ---------------------------------------------------------------- lesson-file and run evidence
# Used by the orchestrator in "Just teach me" lessons, where the step's file in the lesson folder is the truth and
# the screen is only one way of seeing it (QA 11-14: a second VS Code window in front un-passed checks, and a run
# step passed on the code alone).

def screen_check_on_file(check: dict, path: str | os.PathLike | None, window_open: bool = True) -> CheckResult:
    """Grade a ``screen_contains`` check on the lesson's file on disk instead of the screen, for when the screen
    can't show the lesson's editor window (another folder's window is the one in front, or no editor text is in the
    frame). ``path`` is the step's file in the lesson folder (missing = empty). ``window_open``: a lesson editor
    window exists somewhere (another Space, behind, still opening).

    pass when the pattern is in the file; otherwise fail "not in <file> yet", or "Open VS Code so I can check it."
    only when no lesson window exists at all AND the file can't be read (live test 3: s2c3 said "Open VS Code so I
    can check it." while the rows above it said "found in weather.py": a readable file answers the question)."""
    pattern = check.get("pattern")
    if not pattern:
        return _result(check, "fail", "check has no 'pattern'")
    name = os.path.basename(os.fspath(path)) if path else "the lesson file"
    text, readable, m = "", False, None
    if path:
        try:
            text, readable = read_for_scan(path), True
        except OSError:
            text = ""
    try:
        for _, sc in scan_windows(text) if text else ():  # 64 KB windows, newest first (a big notebook's code too)
            if m := search_screen(pattern, sc.text):
                break
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if m:
        return _result(check, "pass", f"found in {name}")
    if not window_open and not readable:
        app = check.get("app")
        return _result(check, "fail", f"Open {_APP_NAMES.get(app, app)} so I can check it." if app
                       else f"not in {name} yet")
    return _result(check, "fail", f"not in {name} yet")


def command_matches(expected: str | None, actual: str | None) -> bool:
    """Does the command that ran (``actual``) run what ``expected`` runs? Interpreter wrappers and flags are ignored
    (``python3 calculator.py`` == ``tut run python calculator.py``); an empty side never matches. A command with no
    script (``python3 --version``, ``node -v``, ``python3``) must end ``actual`` as a whole (python == python3)."""
    if not expected or not actual:
        return False
    if not _script_tokens(expected):
        return _ends_with(actual, _seq(expected))
    # A Python run is ANY python invocation of the script: VS Code's Run ▷ ("/abs/.venv/bin/python" "/abs/nn.py"),
    # `tut run python nn.py`, `uv run nn.py`; never another program that names the file (`cat nn.py`, `code nn.py`).
    if _runs_python(expected) and not _runs_python(actual):
        return False
    return _command_matches(expected, actual)


_INTERP = re.compile(r"python(3(\.\d+)?)?")
_PY_RUNNERS = {"python", "tut", "uv", "ipython", "pipenv", "poetry"}


def _runs_python(command: str) -> bool:
    """Does ``command`` start Python: a python interpreter (any path / version: ``.venv/bin/python``,
    ``python3.12``) or a runner that does (``tut``, ``uv``)?"""
    for t in _words(command):
        if "=" in t and not t.startswith(("/", ".")):
            continue  # env assignments (X=1 python3 nn.py)
        name = os.path.basename(t)
        if name in _PY_RUNNERS or re.fullmatch(r"python[\d.]*t?", name):
            return True
    return False
# Python's crash output (a traceback, or a SyntaxError / IndentationError line) and the shell's "can't run it"
_RUN_ERROR = re.compile(r"^\s*[A-Z]\w*(Error|Exception):|Traceback \(most recent call last\)|command not found"
                        r"|No such file or directory|can't open file")


def _words(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _program(token: str) -> str:
    """``/usr/bin/python3.12`` -> ``python``; other programs by their file name."""
    name = os.path.basename(token)
    return "python" if _INTERP.fullmatch(name) else name


def _seq(text: str) -> list[str]:
    """A command as words for a whole-command match: programs by name (``python3`` -> ``python``), flags without
    their dashes (OCR may read ``--version`` as ``—version``)."""
    return [w for w in (_program(t).lstrip("-\u2013\u2014") for t in _words(text)) if w]


def _ends_with(text: str, whole: list[str]) -> bool:
    """Does ``text`` (a terminal row, or a command line such as ``cd x && python3 --version``) end with the command
    ``whole`` (from ``_seq``)?"""
    got = _seq(text)
    return bool(whole) and got[-len(whole):] == whole


def run_output(lines: Iterable[str], expect: Iterable[str] = ()) -> tuple[bool, bool]:
    """``(error, shows)`` for a run's output ``lines``: ``shows`` = one of the ``expect`` regexes (the step's expected
    output) is in it; ``error`` = it shows a crash (a traceback, an ``XError:`` line, "command not found", ...) that
    the step didn't ask for. An expected pattern found in the error lines ("run it and see the ZeroDivisionError")
    makes the crash the step's point, not a failure; expected output printed before a crash doesn't."""
    lines = [str(x) for x in lines]
    text = scan_text("\n".join(lines))
    errs = scan_text("\n".join(x for x in lines if _RUN_ERROR.search(x)))
    shows = wanted = False
    for pattern in expect:
        try:
            shows = shows or bool(search_screen(pattern, text))
            wanted = wanted or bool(errs and search_screen(pattern, errs))
        except re.error:
            continue
    return bool(errs) and not wanted, shows


_CTRL_C_ROW = re.compile(r"^\s*\^C")
_KEYBOARD_INTERRUPT = re.compile(r"^\s*KeyboardInterrupt\b")
# VS Code's Python extension activating the venv in a new terminal: it sends ^C (no echo in zsh), then this line
# (a path with a space comes quoted: source "/Users/a b/.venv/bin/activate")
_ACTIVATION_ROW = re.compile(r"""(?:^|\s)(?:source|\.)\s+(?:\S*|"[^"]*|'[^']*)bin/activate(?:\.\w+)?["']?\s*$"""
                             r"|(?:^|\s)conda\s+activate\s+\S+\s*$")


_SHELL_JOIN = blocks.SHELL_JOIN
_PROMPT_MARKS = blocks.PROMPT_MARKS
_after_prompt = blocks.after_prompt


def _starts_command(program: str, rest: list[str]) -> bool:
    """With no prompt or shell join before it, is a row whose first word is ``program`` a command line? Only when
    the next word looks like one: nothing (the REPL), a flag (``-m``, ``-c``, ``--version``), a ``*.py`` path, or
    for ``tut`` a ``*.py`` later on. Output that starts with the word (``python 3.12.1 ready``) is not."""
    if not rest or rest[0].startswith("-") or rest[0].lower().endswith(".py"):
        return True
    return program == "tut" and any(t.lower().endswith(".py") for t in rest)


def _command_line_runs(row: str, programs: set[str]) -> bool:
    """Is ``row`` a command line that runs one of ``programs``: the program comes right after a shell prompt marker
    or a shell join (and oh-my-zsh's ``<arrow>  nn git:(main) x python3 a.py``), or is the row's first word followed
    by what a command has (``_starts_command``: a script, a flag, nothing)? A row that only contains the word
    (``I love python``), or starts with it as output (``python 3.12.1 ready``), is not."""
    words = _words(row)
    if words and words[0] == "➜":  # oh-my-zsh: arrow, <dir>, [git:(branch)], [dirty mark], <command>
        rest = words[2:]
        if rest and rest[0].startswith("git:("):
            rest = rest[1:]
        if rest and rest[0] == "✗":
            rest = rest[1:]
        if rest and _program(rest[0]) in programs:
            return True
    return any(_program(t) in programs and (_starts_command(_program(t), words[1:]) if j == 0
                                            else _after_prompt(words[j - 1])) for j, t in enumerate(words))


def _interrupted_rows(out: list[str]) -> bool:
    """A run's output rows (up to the next command line that runs python/tut, the command's program) show it stopped
    by Ctrl+C: the first row is ^C
    (the shell cancelled it at once) or the venv activation that sent that ^C (t5: the command swallowed, nothing
    printed), or Python ended it with KeyboardInterrupt in its last 3 rows (terminal_run.interrupted's rule)."""
    if not out:
        return False
    first = str(out[0])
    tail = [str(r) for r in out if str(r).strip()][-3:]
    return bool(_CTRL_C_ROW.match(first) or _ACTIVATION_ROW.search(first)) \
        or any(_KEYBOARD_INTERRUPT.match(r) for r in tail)


def terminal_runs(command: str, rows: list[str], expect: Iterable[str] = ()) -> tuple[int, bool, bool]:
    """``(runs, error, shows)`` for terminal ``rows`` (visual lines, top to bottom): how many times they show
    ``command`` being RUN, and for the output after the last such run ``run_output``'s ``(error, shows)``: a crash
    the step didn't ask for, and the step's expected output (``expect`` regexes, e.g. ``^5$``).

    A run is a row that names what the command runs (its script tokens, plus its program: ``python``/``python3``,
    or ``tut``; a command with no script, ``python3 --version``, ends the row whole) with at least one row after it
    (Enter was pressed: output or a new prompt). A command typed but not yet run is the bottom row, so it never
    counts; neither does a traceback line that mentions the file, nor a run stopped by ^C / KeyboardInterrupt (t5).
    When a later command line runs the same program
    (another script, or this one misread by OCR: ``calculator.pv``), the output under the last run seen may not be the latest
    run's, so it never counts as shown."""
    want = _script_tokens(command)
    head = next((_program(t) for t in _words(command) if "=" not in t), "")  # skip env assignments (X=1 cmd)
    whole = [] if want else _seq(command)
    if not head or not (want or whole):
        return 0, False, False

    def runs_program(row: str) -> bool:
        names = {_program(t) for t in _words(row)}
        return head in names or "tut" in names

    def is_run(row: str) -> bool:
        if whole:
            return _ends_with(row, whole)
        return all(w in _script_tokens(row) for w in want) and runs_program(row)

    starts = [i for i, row in enumerate(rows[:-1]) if is_run(row)]
    # t5 (CP12): `python3 main.py` then a "^C" row (the venv activation cancelled it) passed "Ran python3 main.py"
    # with nothing run. A run stopped by ^C / KeyboardInterrupt never counts (terminal_run.verdict's rule for VS
    # Code's own reports): its output starts with ^C or ends the program that way. A run's output ends at the next
    # command line that runs python/tut, the command's program (not only the next run of this command): another
    # script's or a REPL's ^C / KeyboardInterrupt in between never cancels an earlier good run, nor reads as its
    # crash. A command line means the program comes right after a prompt marker or shell join, or is the row's
    # first word followed by a script, a flag or nothing; a row that merely contains the word (the program printing
    # "I love python" or "python 3.12.1 ready", then crashing) never ends the window, so that crash is the run's. Other programs (`node x.js`, `bash y.sh`) don't end it either.
    progs = {head, "tut"}
    start_set = set(starts)

    def bounds(k: int) -> bool:
        return k in start_set or _command_line_runs(rows[k], progs)

    def end_of(i: int) -> int:
        return next((k for k in range(i + 1, len(rows)) if bounds(k)), len(rows))

    kept = [i for i in starts if not _interrupted_rows(rows[i + 1:end_of(i)])]
    n, last = len(kept), (kept[-1] if kept else None)
    if last is None:
        return 0, False, False
    err, shows = run_output(rows[last + 1:end_of(last)], expect)  # never a later run's traceback
    if shows and any(bounds(k) for k in range(last + 1, len(rows) - 1)):
        shows = False
    return n, err, shows
