"""Contract validation for step graphs, plus the JSON schemas we hand to Gemini.

The contract schemas live in shared/contracts/ and are the boundary with the
orchestrator and the checks module; never edit them from here.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from server.safety.patterns import safe_search

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "shared" / "contracts"

# Screen-first (contract change, Sat 1 PM): a step's `checks` are graded from what is on
# the learner's screen (Apple Vision OCR), so they use screen_* and metric_* (+ metric_pattern).
# file_*/command_* need a known workdir or `tut run`; they go in the optional per-step
# `precision_checks` list (extra field, allowed by the contract) so they never block a step
# in screen mode. `visual` is not machine-checkable, so the builder never emits it.
SCREEN_TYPES = ["screen_contains", "screen_absent", "metric_threshold", "metric_trend"]
PRECISION_TYPES = ["file_exists", "file_contains", "command_exit_ok", "output_contains", "metric_threshold", "metric_trend"]
CHECK_TYPES = sorted(set(SCREEN_TYPES) | set(PRECISION_TYPES))
SCREEN_APPS = ["Code", "Terminal", "iTerm2", "Google Chrome", "Safari", "Jupyter", "PyCharm", "Cursor"]
MAX_SCREEN_PATTERN = 80  # long regexes break on OCR noise


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    graph = json.loads((CONTRACTS / "step-graph.schema.json").read_text())
    check = json.loads((CONTRACTS / "check.schema.json").read_text())
    registry = Registry().with_resource("check.schema.json", Resource.from_contents(check))
    return Draft202012Validator(graph, registry=registry)


def validate_untrusted_lesson(graph: dict, workdir_hint: str | None = None) -> list[str]:
    """Make a step graph from a model, a cache, a saved session or a shared library safe to run (OWASP LLM06).
    In place; returns what it changed (for logs). Called by the lesson build (builder.build_lesson: every graph it
    returns or streams, cache hits included) and on every stored / cached graph load (sessions.store.load_graph,
    lesson.library.load_graph).

    THE FUTURE CLOUD-CACHE CONSUMER (shared lessons from miyagi-cloud /v1/lessons/*) MUST CALL THIS on every graph it
    downloads, before the graph reaches LessonSession.load_graph.

      * lesson.workdir: a home folder, an ancestor of it, a dot-folder (~/.ssh), ~/Library or a system folder is
        replaced by `workdir_hint` (or removed: the engine's default folder)
      * step / target / check files that fail the lesson-folder path rules (server.safety.paths: absolute, `~`,
        `..`, NUL) are dropped; a check reading such a file is dropped
      * a run_command that can never run (server.safety.commands: shell syntax, a URL, curl / bash / npx ..., a path
        out of the folder) is marked step["run_command_manual"] = {command, reason}: Run it for me shows that command, never runs it
      * checks whose regex is too long or catastrophic ((x+)+, (a|aa)+) are dropped; a target's bad `match` too
      * sources whose url is not https are removed
    The sinks check again at run time (parse_run_command, safe_lesson_path, the evaluator's regex guard)."""
    from server.checks.evaluator import pattern_problem
    from server.safety.commands import is_structural_manual
    from server.safety.paths import rel_problem

    notes: list[str] = []
    if not isinstance(graph, dict):
        return ["not a lesson graph"]
    les = graph.get("lesson")
    if isinstance(les, dict) and les.get("workdir") not in (None, ""):
        if why := _workdir_problem(les.get("workdir")):
            notes.append(f"lesson.workdir {str(les.get('workdir'))[:80]!r}: {why}")
            if workdir_hint and not _workdir_problem(workdir_hint):
                les["workdir"] = str(workdir_hint)
            else:
                les.pop("workdir", None)
    if isinstance(graph.get("sources"), list):
        keep = []
        for s in graph["sources"]:
            url = s.get("url") if isinstance(s, dict) else None
            if not isinstance(s, dict) or (url not in (None, "") and not str(url).startswith("https://")):
                notes.append(f"source {str(url)[:80]!r}: not https")
                continue
            keep.append(s)
        graph["sources"] = keep
    for step in graph.get("steps") or []:
        if not isinstance(step, dict):
            continue
        sid = step.get("id") or "?"
        for key in ("file", "notebook"):  # the files Miyagi creates and Do it for me writes
            f = step.get(key)
            why = rel_problem(str(f)) or _protected_dir(str(f)) if f not in (None, "") else None
            if why:
                notes.append(f"{sid}.{key} {str(f)[:80]!r}: {why}")
                step.pop(key, None)
        if isinstance(step.get("files"), list):
            ok = [f for f in step["files"] if isinstance(f, str) and rel_problem(f) is None]
            if len(ok) != len(step["files"]):
                notes.append(f"{sid}.files: {len(step['files']) - len(ok)} unsafe path(s) dropped")
            step["files"] = ok
        if isinstance(step.get("targets"), list):
            targets = []
            for t in step["targets"]:
                if not isinstance(t, dict):
                    continue
                f = t.get("file")
                if f not in (None, "") and rel_problem(str(f)) is not None:
                    notes.append(f"{sid} target {str(f)[:80]!r}: {rel_problem(str(f))}")
                    continue
                m = t.get("match")  # literal text first, a regex only when it compiles (workspace.anchor_line)
                why = pattern_problem(m, re.IGNORECASE) if isinstance(m, str) and m else None  # screen.match: re.I
                if why and not why.startswith("invalid pattern"):
                    notes.append(f"{sid} target match: {why}")
                    t = {k: v for k, v in t.items() if k != "match"}
                targets.append(t)
            step["targets"] = targets
        for key in ("checks", "precision_checks"):
            if not isinstance(step.get(key), list):
                continue
            kept = []
            for c in step[key]:
                if not isinstance(c, dict):
                    continue
                f = c.get("file")
                if f not in (None, "") and rel_problem(str(f)) is not None:
                    notes.append(f"{sid} check {c.get('id')}: file {str(f)[:80]!r}: {rel_problem(str(f))}")
                    continue
                bad = next((f"{k}: {why}" for k in ("pattern", "metric_pattern")
                            if c.get(k) is not None and (why := pattern_problem(c.get(k)))), None)
                if bad:
                    notes.append(f"{sid} check {c.get('id')}: {bad}")
                    continue
                kept.append(c)
            step[key] = kept
        rc = step.get("run_command")
        if isinstance(rc, str) and rc.strip():
            manual = is_structural_manual(rc)
            if manual is not None:
                step["run_command_manual"] = {"command": rc, "reason": manual.reason}
                notes.append(f"{sid} run_command {rc[:80]!r}: shown, never run ({manual.reason})")
            else:
                step.pop("run_command_manual", None)
    return notes


def _protected_dir(rel: str) -> str | None:
    """A step file inside .git/, .vscode/, .venv/, node_modules/, .github/ ...: never one the lesson creates or writes
    (a plain dotfile such as .env stays: Do it for me's own write rules refuse it at the sink)."""
    from pathlib import PurePosixPath

    from server.safety.paths import WRITE_DENY_DIRS

    hit = next((p for p in PurePosixPath(rel).parts[:-1] if p.casefold() in WRITE_DENY_DIRS), None)  # APFS
    return f"{hit}/ is never a step file" if hit else None


def _workdir_problem(workdir) -> str | None:
    """Why a lesson's workdir may not be used as a lesson folder (None: fine)."""
    if not isinstance(workdir, str) or not workdir.strip() or "\x00" in workdir:
        return "not a folder path"
    p = Path(workdir).expanduser()
    if not p.is_absolute():
        return "goes up out of the repo" if ".." in p.parts else None  # repo-relative (curated / demo lessons)
    try:
        p, home = p.resolve(), Path.home().resolve()
    except (OSError, RuntimeError):
        return "not a folder path"
    if p == home or p in home.parents or p == Path("/"):
        return "a home or system root, not a lesson folder"
    try:
        inside = p.relative_to(home).parts
    except ValueError:
        inside = ()
    if inside and (inside[0].startswith(".") or inside[0] == "Library"):
        return f"~/{inside[0]} is never a lesson folder"
    for root in ("/System", "/usr", "/bin", "/sbin", "/etc", "/private/etc", "/Library", "/Applications", "/cores"):
        if p == Path(root) or Path(root) in p.parents:
            return f"{root} is never a lesson folder"
    return None


def schema_errors(graph: dict) -> list[str]:
    """Contract violations, as short human-readable strings (empty = valid)."""
    out = []
    for err in sorted(_validator().iter_errors(graph), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{path}: {err.message}")
    return out


def lint(graph: dict, known_metrics: set[str] | None = None, known_files: set[str] | None = None) -> list[str]:
    """Semantic problems the JSON schema can't catch: a check must be *runnable*.

    known_files / known_metrics come from scanning the learner's workdir; when they
    are empty (fresh or unknown workdir) the corresponding checks are not enforced.
    """
    problems: list[str] = []
    seen_ids: set[str] = set()
    steps = graph.get("steps", [])
    if known_metrics and steps and not any(c.get("type", "").startswith("metric_") for s in steps for c in s.get("checks", [])):
        problems.append(
            f"no metric check: the workdir prints {sorted(known_metrics)}; the training step needs a metric_threshold/metric_trend "
            "with a metric_pattern that parses those lines"
        )
    if steps and vague_setup(steps[0]):
        problems.append(f"{steps[0].get('id', 's1')}: setup step says to clone/download/get the tutorial's code or data but gives "
                        "no URL and no exact commands; give the link from the description, or the commands/files that recreate it")
    prev: set | None = None
    for step in steps:
        sid = step.get("id", "?")
        sig = {(c.get("type"), c.get("app"), c.get("pattern")) for c in step.get("checks", []) if c.get("type", "").startswith("screen_")}
        if prev and sig and sig <= prev and not any(c.get("type", "").startswith("metric_") for c in step.get("checks", [])):
            problems.append(f"{sid}: its checks repeat the previous step's, so it passes the moment it starts; check what THIS step adds")
        prev = sig
        if len(step.get("title", "").split()) > 6:
            problems.append(f"{sid}: title longer than 6 words")
        checks = step.get("checks", [])
        if not checks:
            problems.append(f"{sid}: no screen checks (every step needs at least one screen_* or metric_* check)")
        v = step.get("video")
        if v and not (0 <= v.get("start", 0) < v.get("end", 0)):
            problems.append(f"{sid}: video.start must be < video.end")
        for c in checks:
            problems += [f"{sid}/{c.get('id', '?')}: {p}" for p in step_check_problems(c, step)]
        cmd = (step.get("run_command") or "").strip()
        if cmd and not any(is_output_check(c, step) for c in checks):
            problems.append(f"{sid}: runs `{cmd[:60]}` but has no check on its output (what it prints, a count, a metric)")
        for key, allowed in (("checks", SCREEN_TYPES), ("precision_checks", PRECISION_TYPES)):
            for c in step.get(key, []):
                cid = c.get("id", "?")
                if cid in seen_ids:
                    problems.append(f"{sid}/{cid}: duplicate check id")
                seen_ids.add(cid)
                problems += [f"{sid}/{cid}: {p}" for p in check_problems(c, allowed, key, known_metrics, known_files)]
    return problems


TERMINAL_APPS = (None, "Terminal", "iTerm2")
_NOTEBOOK = re.compile(r"\bcells?\b|shift\s*\+\s*enter|run\s+all|notebook|jupyter|colab", re.I)
_BACKTICKS = re.compile(r"`([^`]+)`")


def _search(pattern: str, text: str) -> bool:
    try:
        return bool(text) and safe_search(pattern, text, re.M) is not None  # lint runs before validation
    except re.error:
        return False


def is_notebook_step(step: dict) -> bool:
    return bool(_NOTEBOOK.search(step.get("run_command") or ""))


def code_texts(step: dict) -> list[str]:
    """What the learner TYPES in this step: its code, backticked code in the instructions, Code targets."""
    out = [step.get("code") or ""]
    out += _BACKTICKS.findall(step.get("instructions") or "")
    out += [t.get("match") or "" for t in step.get("targets") or [] if t.get("app") in (None, "Code")]
    return [t for t in out if t]


def echoes_command(c: dict, cmd: str) -> bool:
    """A screen check on the terminal whose pattern already matches the typed command line."""
    if c.get("type") != "screen_contains" or c.get("app") not in TERMINAL_APPS or not c.get("pattern") or not cmd:
        return False
    if _NOTEBOOK.search(cmd):  # "run each cell" is an instruction, not a typed command
        return False
    return _search(c["pattern"], cmd)


def echoes_code(c: dict, step: dict) -> bool:
    """An output check with no app scope (any window, the editor included) that matches the code the
    learner types, so it passes as soon as the code is visible (e.g. `Country` for df['Country'])."""
    if c.get("type") != "screen_contains" or c.get("app") is not None or not c.get("pattern"):
        return False
    return any(_search(c["pattern"], t) for t in code_texts(step))


def literal_strength(pattern: str) -> tuple[int, int]:
    """(weakest, strongest) count of literal letters/digits over the pattern's top-level alternatives."""
    alts, depth, cur, i = [], 0, "", 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            cur += pattern[i:i + 2]
            i += 2
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "|" and depth == 0:
            alts.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    alts.append(cur)

    def lits(a: str) -> int:
        a = re.sub(r"\(\?(?:P<\w+>|[:=!]|<[=!]|[aiLmsux-]+\))", "(", a)  # group syntax / inline flags
        a = re.sub(r"\[(?:\\.|[^\]])*\]", "", a)  # character classes
        a = re.sub(r"\{\d*,?\d*\}", "", a)  # counted quantifiers
        a = re.sub(r"\\[sSdDwWbBAZ]", "", a)  # class escapes
        a = re.sub(r"\\(.)", r"\1", a)  # escaped literal
        return sum(ch.isalnum() for ch in a)

    counts = [lits(a) for a in alts] or [0]
    return min(counts), max(counts)


MIN_LITERAL_ALT, MIN_LITERAL_BEST = 3, 5

# Well-known output lines per tool: (detects the tool in a step's command/code, app, label, output regex).
# Used in the adapt prompt and by repair for run steps the model left without an output check.
STANDARD_OUTPUTS = [
    (r"\b(vite|npm\s+run\s+dev|yarn\s+dev|pnpm\s+dev)\b", "Terminal", "dev server running", r"Local:\s+http://localhost:\d+"),
    (r"\bnext\s+dev\b", "Terminal", "dev server ready", r"(Ready|ready)\s+in|Local:\s+http://localhost:\d+"),
    (r"\b(jest|vitest|npm\s+(run\s+)?test)\b", "Terminal", "tests passed", r"Tests?:?\s+\d+\s+passed|\d+\s+passed"),
    (r"\bpytest\b", "Terminal", "tests passed", r"\d+\s+passed"),
    (r"\bcargo\s+(run|build|test|check)\b", "Terminal", "cargo finished", r"Finished\s+\S*\s*(dev|release|test)"),
    (r"\b(uvicorn|fastapi\s+(dev|run))\b", "Terminal", "server running", r"Uvicorn\s*running\s*on|Application\s+startup\s+complete"),
    (r"\bflask\s+run\b", "Terminal", "server running", r"Running\s+on\s+http"),
    (r"\b(pd\.|pandas|DataFrame|read_csv|df\b)", "Code", "table printed", r"\d+\s*rows\s*[x×]\s*\d+\s*columns|dtype:\s*\w+|RangeIndex:\s*\d+"),
]


# What failure looks like in each stack's terminal, for screen_absent "it runs" checks.
STANDARD_ERRORS = [
    ("rust", r"\b(cargo|rustc)\b|\.rs\b|\bfn\s+main\b", r"error\[E\d+\]|error:\s"),
    ("node", r"\b(npm|npx|node|vite|yarn|pnpm|next|react|jsx|tsx)\b", r"ERR!|Error:|error\s+TS\d+"),
    ("go", r"\bgo\s+(run|build|test)\b|\.go\b", r"panic:|\bFAIL\b"),
    ("git", r"^\s*git\s|\bgit\s+(init|add|commit|rebase|merge|push|pull|clone|switch|checkout)\b", r"fatal:|error:\s"),
    ("python", r"\b(python3?|pytest|pip|uvicorn|flask|pandas|import)\b|\.py\b", r"Traceback|Error:"),
]


def stack_of(step: dict, libraries: dict | None = None) -> str | None:
    text = " ".join([step.get("run_command") or "", step.get("code") or "", " ".join((libraries or {}).keys())])
    for name, detect, _err in STANDARD_ERRORS:
        if re.search(detect, text, re.I | re.M):
            return name
    return None


def standard_error_pattern(stack: str) -> str:
    return next(err for name, _d, err in STANDARD_ERRORS if name == stack)


def standard_output_check(step: dict) -> dict | None:
    """A stack-standard output check for a run step, if its command/code names a known tool."""
    text = " ".join([step.get("run_command") or "", step.get("code") or ""])
    for detect, app, label, pattern in STANDARD_OUTPUTS:
        if re.search(detect, text, re.I):
            if app == "Code" and not is_notebook_step(step):
                app = "Terminal"  # a script prints the table to the terminal; a notebook renders it in the editor
            return {"type": "screen_contains", "label": label, "app": app, "pattern": pattern}
    return None


def standard_outputs_for_prompt() -> str:
    return "\n".join(f"  - {label} ({app}): {pattern}" for _d, app, label, pattern in STANDARD_OUTPUTS)


def is_weak(c: dict) -> bool:
    """Too generic to mean anything: e.g. `\\*\\s*\\S+`, `\\bmain\\b`, `\\S+\\s+0\\.1\\.0`."""
    if c.get("type") != "screen_contains" or not c.get("pattern"):
        return False
    if c["pattern"].startswith("^") and c["pattern"].endswith("$"):  # an exact whole line (e.g. a program printing 5)
        return False
    weakest, best = literal_strength(c["pattern"])
    return weakest < MIN_LITERAL_ALT or best < MIN_LITERAL_BEST


def step_check_problems(c: dict, step: dict) -> list[str]:
    out = []
    cmd = (step.get("run_command") or "").strip()
    if echoes_command(c, cmd):
        out.append(f"Terminal pattern matches the command the learner types (`{cmd[:60]}`), so it passes before "
                   "anything runs; match the command's output instead")
    if echoes_code(c, step):
        out.append("pattern with no app scope matches the step's own code, so it passes when the code is merely visible; "
                   "scope it to the app that shows the output or match text only the output contains")
    if is_weak(c):
        out.append(f"pattern {c['pattern']!r} is too generic (each alternative needs >= {MIN_LITERAL_ALT} literal "
                   f"letters/digits and the best >= {MIN_LITERAL_BEST}); match a distinctive word of the output or code")
    return out


def is_output_check(c: dict, step: dict) -> bool:
    if c.get("type", "").startswith("metric_"):
        return True
    if c.get("type") != "screen_contains" or step_check_problems(c, step):
        return False
    if c.get("app") == "Code":  # notebook output is rendered inside the editor
        return is_notebook_step(step) and not any(_search(c["pattern"], t) for t in code_texts(step))
    return True


_SETUP_VERB = re.compile(r"\b(clone|download|grab|get|fetch|put|place|copy|use|initiali[sz]e|init|set\s*up|create|make|prepare)\b"
                         r"[^.]*\b(repo(sitory)?|dataset|csv|data|project|starter|example|file|branch(es)?|commits?|folder|app)s?\b", re.I)
_CONCRETE = re.compile(r"https?://|`[^`]+`|\bgit\s+(init|clone|checkout|switch|add|commit|branch|merge|rebase|push|pull)\b"
                       r"|\b(npm|npx|pip|curl|wget|cargo|mkdir|touch|echo)\s+\S", re.I)


def vague_setup(step: dict) -> bool:
    """Step 1 tells the learner to obtain the tutorial's code/data without saying how (no URL, no command)."""
    text = step.get("instructions") or ""
    if (step.get("code") or "").strip():  # the exact commands/files are in the step's code
        return False
    return bool(_SETUP_VERB.search(text)) and not _CONCRETE.search(text)


def check_problems(c: dict, allowed: list[str], where: str, known_metrics=None, known_files=None) -> list[str]:
    out: list[str] = []
    t = c.get("type")
    if t not in allowed:
        return [f"type {t!r} not allowed in `{where}` (use one of {allowed})"]
    need = {
        "screen_contains": ("pattern",), "screen_absent": ("pattern",),
        "file_exists": ("file",), "file_contains": ("file", "pattern"), "command_exit_ok": ("command",),
        "output_contains": ("pattern",), "metric_threshold": ("metric", "op", "value"), "metric_trend": ("metric", "trend"),
    }[t]
    out += [f"{t} needs `{k}`" for k in need if c.get(k) in (None, "")]
    if c.get("pattern"):
        if err := _regex_error(c["pattern"]):
            out.append(f"pattern does not compile ({err})")
        elif t.startswith("screen_") and len(c["pattern"]) > MAX_SCREEN_PATTERN:
            out.append(f"screen pattern longer than {MAX_SCREEN_PATTERN} chars; OCR text is noisy, match a short distinctive fragment")
    if t in ("metric_threshold", "metric_trend"):
        mp = c.get("metric_pattern")
        if where == "checks" and not mp:
            out.append("screen metric check needs `metric_pattern` (regex with (?P<value>...), plus (?P<step>...) for trends) to read it off the screen")
        if mp:
            if err := _regex_error(mp):
                out.append(f"metric_pattern does not compile ({err})")
            elif "value" not in re.compile(mp).groupindex:
                out.append("metric_pattern must have a named group `value`")
            elif spans_lines(mp):
                out.append("metric_pattern spans lines ([\\s\\S], \\n or the s flag), but the checker reads ONE printed line at a "
                           "time: match only the line that holds the number; when the step/epoch is printed on a line of its "
                           "own (Keras: 'Epoch 1/5'), use metric_threshold on the value's line instead of metric_trend")
            elif t == "metric_trend" and "step" not in re.compile(mp).groupindex:
                out.append("metric_trend's metric_pattern needs a named group `step` (a trend is over steps)")
        if t == "metric_trend" and (w := _int(c.get("window"))) is not None and w < TREND_MIN_POINTS - 1:
            out.append(f"metric_trend window {w} can never hold the {TREND_MIN_POINTS} points a trend needs; for a run that "
                       f"prints a few values (5 epochs), use metric_threshold on the final value")
        if where == "precision_checks" and known_metrics and c.get("metric") and not _metric_known(c["metric"], known_metrics):
            out.append(f"metric {c['metric']!r} is never printed by the workdir code (known: {sorted(known_metrics)})")
    if t in ("file_exists", "file_contains") and known_files and c.get("file"):
        if c["file"] not in known_files and not _creatable(c["file"]):
            out.append(f"file {c['file']!r} is not in the workdir (files: {sorted(known_files)[:20]})")
    return out


# The checks module reads a metric off ONE printed line at a time (server.checks.extract_metrics, also the screen
# reader), and a trend needs TREND_MIN_POINTS points inside `window` steps (server/checks/evaluator.py, kept equal by a
# test). A metric check that breaks either can never pass: the step's video stays paused for good (Nov 15: a Keras
# lesson's "Epoch\s*(?P<step>\d+)/\d+[\s\S]*?loss:..." over 5 epochs, window 5).
TREND_MIN_POINTS = 8
_ANY_CHAR = r"\[(?:\\s\\S|\\S\\s|\\w\\W|\\W\\w|\\d\\D|\\D\\d)\]"  # [\s\S] and friends: any character, newlines too
_SPANS_LINES = re.compile(_ANY_CHAR + r"|(?<!\\)\\[nr]|\(\?[aiLmux]*s[aiLmux]*[:)]")
_CROSS_LINE_TOKEN = re.compile(r"(?:" + _ANY_CHAR + r"|(?<!\\)\\[nr])+(?:[*+?]|\{\d*,?\d*\})?\??")


def spans_lines(pattern: str) -> bool:
    """True when a regex is written to match across lines ([\\s\\S], \\n, the s flag)."""
    return "\n" in pattern or bool(_SPANS_LINES.search(pattern))


def value_line(pattern: str) -> str | None:
    """The part of a line-spanning metric_pattern that matches the line holding (?P<value>...), or None.
    "Epoch\\s*(?P<step>\\d+)/\\d+[\\s\\S]*?loss:\\s*(?P<value>\\d+\\.\\d+)" -> "loss:\\s*(?P<value>\\d+\\.\\d+)"."""
    for part in _CROSS_LINE_TOKEN.split(pattern.replace("\n", r"\n")):
        part = part.strip()
        if "(?P<value>" not in part or spans_lines(part) or _regex_error(part):
            continue
        return part if "value" in re.compile(part).groupindex else None
    return None


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _regex_error(p: str) -> str | None:
    try:
        re.compile(p)
    except re.error as e:
        return str(e)
    return None


def _metric_known(name: str, known: set[str]) -> bool:
    if name in known:
        return True
    # f-string metric names are recorded as prefixes, e.g. "grad_norm/*"
    return any(k.endswith("*") and name.startswith(k[:-1]) for k in known)


def _creatable(path: str) -> bool:
    # Steps may legitimately ask the learner to create new files; allow simple
    # source-file names, flag anything that looks like a typo'd existing path.
    return "/" not in path and path.endswith((".py", ".ipynb", ".txt", ".png"))


# --------------------------------------------------------------------------- #
# Schemas for Gemini structured output. Gemini supports a subset of JSON Schema
# (no $ref across files, no additionalProperties maps), so these are inlined
# and flatter than the contract; builder.py converts them to the contract shape.
# --------------------------------------------------------------------------- #

_CHECK_DRAFT = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": CHECK_TYPES},
        "label": {"type": "string", "description": "<= 6 words, shown in a checklist; unique within the step, naming the thing built (e.g. 'X inputs typed')"},
        "app": {"type": "string", "description": "screen_*: app whose window must show the text, e.g. Code, Terminal"},
        "metric_pattern": {"type": "string", "description": "regex with named group value (and step when printed per step/epoch) that reads the number off one printed line"},
        "file": {"type": "string"},
        "pattern": {"type": "string", "description": "Python regex"},
        "command": {"type": "string"},
        "metric": {"type": "string"},
        "op": {"type": "string", "enum": ["<", "<=", ">", ">="]},
        "value": {"type": "number"},
        "by_step": {"type": "integer"},
        "trend": {"type": "string", "enum": ["decreasing", "not_flat"]},
        "window": {"type": "integer"},
    },
    "required": ["type", "label"],
}

VIDEO_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "lesson title"},
        "summary": {"type": "string"},
        "libraries": {
            "type": "array",
            "description": "libraries the tutorial uses, with the version if shown or inferable (pip output, imports, API style)",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "version": {"type": "string"}},
                "required": ["name", "version"],
            },
        },
        "files": {"type": "array", "items": {"type": "string"}, "description": "file names the tutorial creates/edits"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "MM:SS where the step's explanation/coding starts"},
                    "end": {"type": "string", "description": "MM:SS where the step is complete (code written / run finished)"},
                    "title": {"type": "string", "description": "imperative, <= 6 words"},
                    "instructions": {"type": "string", "description": "<= 2 sentences telling the learner what to do"},
                    "file": {"type": "string", "description": "file edited in this step, if any"},
                    "code": {"type": "string", "description": "the key code written in this step, as seen on screen"},
                    "run_command": {"type": "string", "description": "command run at the end of the step, if any"},
                    "expected_output": {"type": "string", "description": "terminal lines printed by the run, verbatim as on screen (format matters: checks parse it)"},
                    "checks": {"type": "array", "items": _CHECK_DRAFT},
                    "targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"app": {"type": "string"}, "file": {"type": "string"}, "match": {"type": "string"}, "caption": {"type": "string"}},
                            "required": ["match", "caption"],
                        },
                    },
                    "explanations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"topic": {"type": "string"}, "t": {"type": "string", "description": "MM:SS"}},
                            "required": ["topic", "t"],
                        },
                    },
                    "hints": {"type": "array", "items": {"type": "string"}},
                    "common_mistakes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start", "end", "title", "instructions", "checks", "hints"],
            },
        },
    },
    "required": ["title", "libraries", "steps"],
}

DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string", "description": "file name visible in the editor tab, if any"},
        "code": {"type": "string", "description": "the code on screen at the end of this clip, transcribed exactly"},
        "run_command": {"type": "string"},
        "terminal_output": {"type": "string", "description": "training/progress lines visible in the terminal or notebook output, verbatim"},
        "printed_metrics": {"type": "array", "items": {"type": "string"}, "description": "names of numbers the run prints (loss, accuracy, tests passed, latency...)"},
        "library_versions": {
            "type": "array",
            "items": {"type": "object", "properties": {"name": {"type": "string"}, "version": {"type": "string"}}, "required": ["name", "version"]},
        },
    },
    "required": ["code"],
}

ADAPTED_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "instructions": {"type": "string"},
                    "checks": {"type": "array", "items": _CHECK_DRAFT, "description": "screen-first: screen_contains / screen_absent / metric_* with metric_pattern"},
                    "precision_checks": {"type": "array", "items": _CHECK_DRAFT, "description": "backup when the workdir is known: file_* / command_exit_ok / metric_* by ::metric:: name"},
                    "targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"app": {"type": "string"}, "file": {"type": "string"}, "match": {"type": "string"}, "caption": {"type": "string"}},
                            "required": ["match", "caption"],
                        },
                    },
                },
                "required": ["index", "checks", "targets"],
            },
        }
    },
    "required": ["steps"],
}
