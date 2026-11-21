"""Replay a scripted learner against a CACHED lesson and report pass/fail per step. Offline, free.

    python -m evals.replay.harness                  # every case: replay the cached ones, list the ones needing a build
    python -m evals.replay.harness --only git-basics -v
    python -m evals.replay.harness --dry            # grade every learner script on its own expected checks only
    python -m evals.replay.harness --needs-build    # the cases whose lesson is not cached (one paid build each)
    python -m evals.replay.harness --json out.json  # full results

Nothing here builds a lesson, calls a model or opens a window. A case (cases/<id>.json) names its tutorial, the cached
lesson graph it replays (demo/cache/lessons/... or null), an expected outline with expected checks per step, and a
learner script of edits, commands and mistakes. The harness:

* makes a fresh temp lesson folder (optionally seeded from a starter folder),
* plays each step's actions into it: real files on disk, a fake Terminal (prompt rows + output, last N rows visible),
  a fake VS Code window (the open file, a viewport around the last edit), an optional browser window, notebook cells
  written to a real .ipynb with outputs,
* after every action asks the REAL checks module (server.checks.evaluate_gate) whether the step passes, as
  LessonSession does with a ScreenObservation + RunContext (precision mode on, a failing screen_absent vetoes the
  files-only route, screen_contains passes latch for the step), and records when it first passed,
* reports each step's best status (pass on screen checks > pass-precision > fail / pending), whether each mistake was
  caught (the step was not passing right after it), and the case's expected checks (`expect_checks`) as a spec.

A dry run (--dry, or a case with no cached lesson) grades the learner on the expected checks alone: it proves the
script produces what the lesson should check, before any paid build.

Stub modules: the screen reader (OCR) is the fake screen above; `tut run` / VS Code's command_end is the scripted run
(command, exit code, output tail, ::metric:: lines into ctx.metrics); the video is never played (segment_done=True).
Command output is either recorded real output (`output_ref`), produced by really running a stdlib-only Python script
(`real: true`), or written in the tool's verbatim format (`output`). Each run's source is reported.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CASES_DIR = HERE / "cases"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from server.checks import RunContext, evaluate_gate, evaluate_step

STATUSES = ("pass", "pass-precision", "fail", "pending")
ACTIONS = ("write", "edit", "insert", "append", "open", "scroll", "run", "clear", "browser", "cell", "mistake", "mkdir")
PROMPT = "me@mac {dir} % "
METRIC_LINE = re.compile(r"::metric::\s*(\{.*\})")
_SAFE_REAL = re.compile(r"^python3?\s+[\w./-]+\.py(\s+[\w.=-]+)*$")


class CaseError(ValueError):
    """A malformed case or an action that can't be applied (a script bug, never a lesson finding)."""


# ----------------------------------------------------------------------------------------------------- cases


def load_cases(only: list[str] | None = None) -> list[dict]:
    cases = []
    for p in sorted(CASES_DIR.glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        c["_path"] = str(p.relative_to(REPO))
        if only and c.get("id") not in only:
            continue
        cases.append(c)
    return cases


def lesson_path(case: dict) -> Path | None:
    rel = case.get("lesson")
    return (REPO / rel) if rel else None


def is_cached(case: dict) -> bool:
    p = lesson_path(case)
    return bool(p and p.is_file())


def load_lesson(case: dict) -> dict | None:
    p = lesson_path(case)
    if not p or not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("graph") if "graph" in data and "steps" not in data else data  # evals/lesson/results wrap it


def validate_case(case: dict) -> list[str]:
    """Problems with a case definition ([] = well formed)."""
    errs: list[str] = []
    for k in ("id", "topic", "stack", "tutorial", "outline"):
        if not case.get(k):
            errs.append(f"missing {k}")
    t = case.get("tutorial") or {}
    if t.get("kind") not in ("video", "text"):
        errs.append("tutorial.kind must be video or text")
    if not t.get("goal"):
        errs.append("tutorial.goal missing")
    if t.get("kind") == "video" and not (t.get("video_id") or t.get("find_query")):
        errs.append("a video tutorial needs video_id or find_query")
    for i, st in enumerate(case.get("outline") or []):
        where = f"outline[{i}]"
        for k in ("about", "match", "expect_checks", "actions"):
            if k not in st:
                errs.append(f"{where}: missing {k}")
        if not _expected(st) or any(e not in STATUSES for e in _expected(st)):
            errs.append(f"{where}: expect must be one of (or a list of) {STATUSES}")
        if is_cached(case) and not st.get("step"):
            errs.append(f"{where}: a cached case maps every outline item to a lesson step id")
        try:
            re.compile(st.get("match", ""), re.IGNORECASE)
        except re.error as e:
            errs.append(f"{where}: bad match regex: {e}")
        for c in st.get("expect_checks") or []:
            if c.get("type") not in ("screen_contains", "screen_absent", "file_exists", "file_contains", "output_contains",
                                     "command_exit_ok", "metric_threshold", "metric_trend"):
                errs.append(f"{where}: unsupported expected check type {c.get('type')!r}")
            if c.get("pattern"):
                try:
                    re.compile(c["pattern"])
                except re.error as e:
                    errs.append(f"{where}: bad expected pattern {c['pattern']!r}: {e}")
        errs += [f"{where}: {e}" for e in _validate_actions(st.get("actions") or [])]
    return errs


def _expected(st: dict, dry: bool = False) -> list[str]:
    """The statuses the case accepts for this step. A list when the result depends on the disk (case-insensitive
    APFS vs a case-sensitive one). A dry run grades the expected checks, which a correct learner always passes."""
    if dry:
        return ["pass"]
    e = st.get("expect", "pass")
    return list(e) if isinstance(e, list) else [e]


def _validate_actions(actions: list[dict]) -> list[str]:
    errs = []
    for j, a in enumerate(actions):
        if a.get("do") not in ACTIONS:
            errs.append(f"action {j}: unknown do={a.get('do')!r}")
        if a.get("do") == "mistake":
            if not a.get("note"):
                errs.append(f"action {j}: a mistake needs a note")
            errs += [f"mistake {j}: {e}" for e in _validate_actions(a.get("actions") or [])]
    return errs


# ----------------------------------------------------------------------------------------------------- stub world


@dataclass
class World:
    """The learner's machine as the checks see it: a real lesson folder plus fake windows."""

    root: Path
    viewport: int = 60
    terminal_rows: int = 30
    shell_dir: str = ""  # relative to root
    rows: list[str] = field(default_factory=list)  # terminal scrollback
    open_file: str | None = None
    view_top: int = 0
    browser: dict[str, list[str]] = field(default_factory=dict)
    ctx: RunContext = field(default_factory=RunContext)
    run_sources: list[str] = field(default_factory=list)
    latched: dict[str, str | None] = field(default_factory=dict)  # checkId -> the file on screen when it passed

    # -- files
    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise CaseError(f"path escapes the lesson folder: {rel}")
        return p

    def read(self, rel: str) -> str:
        p = self.path(rel)
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    def write(self, rel: str, text: str, focus: int | None = None) -> None:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        self.show(rel, focus)

    def show(self, rel: str, focus: int | None = None) -> None:
        """VS Code shows `rel`, scrolled so line `focus` (0-based) sits a few lines from the top."""
        self.open_file = rel
        self.view_top = max(0, (focus or 0) - 5)

    # -- screen
    def code_lines(self) -> list[str] | None:
        if not self.open_file:
            return None
        if self.open_file.endswith(".ipynb"):
            lines = _render_notebook(self.read(self.open_file))
        else:
            lines = self.read(self.open_file).splitlines()
        top = max(0, min(self.view_top, len(lines) - self.viewport))  # VS Code never scrolls a short file off screen
        return [f"{Path(self.open_file).name} - {self.root.name}"] + lines[top:top + self.viewport]

    def terminal_lines(self) -> list[str]:
        return (self.rows + [self.prompt()])[-self.terminal_rows:]

    def prompt(self) -> str:
        return PROMPT.format(dir=(self.root / self.shell_dir).resolve().name if self.shell_dir else self.root.name)

    def observation(self) -> dict[str, list[str]]:
        obs: dict[str, list[str]] = {"Terminal": self.terminal_lines()}
        if (code := self.code_lines()) is not None:
            obs["Code"] = code
        obs.update(self.browser)
        return obs

    def context(self) -> RunContext:
        return RunContext(workdir=str(self.root), command=self.ctx.command, exit_code=self.ctx.exit_code,
                          output_tail=list(self.ctx.output_tail), metrics=copy.deepcopy(self.ctx.metrics),
                          running=self.ctx.running, screen=self.observation(), segment_done=True)

    def new_step(self) -> None:
        """The orchestrator grades each step on its own runs: the last run and its metrics start empty."""
        self.ctx = RunContext()
        self.latched = {}


def _render_notebook(text: str) -> list[str]:
    """What VS Code shows of a notebook: each cell's source, then its text outputs."""
    try:
        nb = json.loads(text) if text else {"cells": []}
    except ValueError:
        return text.splitlines()
    out: list[str] = []
    for c in nb.get("cells", []):
        out += "".join(c.get("source") or []).splitlines()
        for o in c.get("outputs") or []:
            if o.get("output_type") == "stream":
                out += "".join(o.get("text") or []).splitlines()
            elif o.get("output_type") == "error":
                out += [f"{o.get('ename')}: {o.get('evalue')}"]
            else:
                out += "".join((o.get("data") or {}).get("text/plain") or []).splitlines()
        out.append("")
    return out


# ----------------------------------------------------------------------------------------------------- actions


def _line_of(text: str, needle: str) -> int:
    for i, ln in enumerate(text.splitlines()):
        if needle in ln:
            return i
    raise CaseError(f"anchor {needle!r} not found")


def _output_from_ref(ref: str) -> list[str]:
    """'demo/cache/stage/nn-runs.json#nn4.good' -> that list of recorded lines."""
    file, _, key = ref.partition("#")
    data: Any = json.loads((REPO / file).read_text(encoding="utf-8"))
    for k in key.split(".") if key else []:
        data = data[k]
    if not isinstance(data, list):
        raise CaseError(f"output_ref {ref} is not a list of lines")
    return [str(x) for x in data]


def _real_run(cmd: str, stdin: str, cwd: Path) -> tuple[list[str], int]:
    """Really run a stdlib-only Python script of the learner's, inside the lesson folder: `python3 calculator.py`."""
    if not _SAFE_REAL.match(cmd) or ".." in cmd:
        raise CaseError(f"real runs are limited to `python3 <script>.py [args]`, not {cmd!r}")
    argv = [sys.executable, *shlex.split(cmd)[1:]]
    env = {k: v for k, v in os.environ.items() if not re.search(r"API_KEY|TOKEN|SECRET", k)}
    p = subprocess.run(argv, input=stdin, capture_output=True, text=True, cwd=cwd, timeout=20, env=env, check=False)
    return (_echo_input(p.stdout, stdin) + p.stderr).splitlines(), p.returncode


def _echo_input(out: str, stdin: str) -> str:
    """A terminal shows what the learner typed after each input() prompt ("First number: 8"); captured stdout
    doesn't. Puts each answer after the next prompt that ends in ": " and isn't followed by a newline."""
    pos = 0
    for answer in stdin.splitlines():
        m = re.compile(r": (?=[^\n])").search(out, pos)
        if not m:
            break
        out = out[:m.end()] + answer + "\n" + out[m.end():]
        pos = m.end() + len(answer) + 1
    return out


def apply(world: World, a: dict) -> None:
    do = a.get("do")
    if do == "write":
        world.write(a["file"], a["text"], focus=a.get("focus_line"))
    elif do == "edit":
        text = world.read(a["file"])
        if a["find"] not in text:
            raise CaseError(f"edit: {a['find']!r} not in {a['file']}")
        new = text.replace(a["find"], a["replace"], 1)
        world.write(a["file"], new, focus=new.count("\n", 0, new.index(a["replace"])) if a["replace"] else None)
    elif do == "insert":  # new lines right after the first line containing `after`
        text = world.read(a["file"])
        lines = text.splitlines()
        i = _line_of(text, a["after"])
        lines[i + 1:i + 1] = a["text"].splitlines()
        world.write(a["file"], "\n".join(lines) + "\n", focus=i + 1)
    elif do == "append":
        text = world.read(a["file"])
        sep = "" if not text or text.endswith("\n") else "\n"
        world.write(a["file"], text + sep + a["text"], focus=len(text.splitlines()))
    elif do == "open":
        world.show(a["file"], _line_of(world.read(a["file"]), a["at"]) if a.get("at") else 0)
    elif do == "scroll":
        world.show(world.open_file or a["file"], _line_of(world.read(world.open_file or a["file"]), a["at"]))
    elif do == "mkdir":
        world.path(a["dir"]).mkdir(parents=True, exist_ok=True)
    elif do == "clear":
        world.rows = []
    elif do == "browser":
        world.browser = {a.get("app", "Google Chrome"): list(a["lines"])}
    elif do == "cell":
        _cell(world, a)
    elif do == "run":
        _run(world, a)
    else:
        raise CaseError(f"unknown action {do!r}")


def _run(world: World, a: dict) -> None:
    cmd = a["cmd"]
    world.rows.append(world.prompt() + cmd)
    cwd = (world.root / world.shell_dir).resolve()
    if a.get("real") and cwd != world.root.resolve() and world.root.resolve() not in cwd.parents:
        raise CaseError(f"a real run must start inside the lesson folder, not {world.shell_dir}")
    if a.get("real"):
        lines, code = _real_run(cmd, a.get("stdin", ""), cwd)
        world.run_sources.append(f"real: {cmd}")
    elif a.get("output_ref"):
        lines, code = _output_from_ref(a["output_ref"]), int(a.get("exit", 0))
        world.run_sources.append(f"recorded ({a['output_ref']}): {cmd}")
    else:
        lines, code = [str(x) for x in a.get("output", [])], int(a.get("exit", 0))
        world.run_sources.append(f"format: {cmd}")
    for rel, content in (a.get("creates") or {}).items():  # the command's side effects on disk (git init, npm create)
        if rel.endswith("/"):
            world.path(rel).mkdir(parents=True, exist_ok=True)
        else:
            p = world.path(rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    for rel in a.get("deletes") or []:
        p = world.path(rel)
        shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
    m = re.match(r"^\s*cd\s+(\S+)\s*$", cmd)
    if m and code == 0:
        target = os.path.normpath(os.path.join(world.shell_dir, m.group(1)))
        world.shell_dir = "" if target in (".", "") else target
    world.rows += lines
    running = bool(a.get("running"))  # a server that never exits (npm run dev, uvicorn, jupyter)
    metrics: dict[str, list[tuple[int, float]]] = {}
    for ln in lines:
        if mm := METRIC_LINE.search(ln):
            d = json.loads(mm.group(1))
            metrics.setdefault(d["name"], []).append((int(d["step"]), float(d["value"])))
    world.ctx = RunContext(command=cmd, exit_code=None if running else code, output_tail=lines[-200:],
                           metrics=metrics, running=running)


def _cell(world: World, a: dict) -> None:
    """Type a cell into the notebook (append, or replace cell `index`) and optionally its outputs (= it ran)."""
    rel = a["file"]
    text = world.read(rel)
    nb = json.loads(text) if text else {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    ran = "outputs" in a or "error" in a
    outputs: list[dict] = []
    for o in a.get("outputs") or []:
        if isinstance(o, dict) and o.get("image"):
            outputs.append({"output_type": "display_data", "data": {"image/png": "iVBORw0KGgo=", "text/plain": [o.get("text", "<Figure>")]},
                            "metadata": {}})
        else:
            outputs.append({"output_type": "stream", "name": "stdout", "text": [str(o) + "\n" for o in ([o] if isinstance(o, str) else o)]})
    if err := a.get("error"):
        outputs.append({"output_type": "error", "ename": err["ename"], "evalue": err["evalue"], "traceback": err.get("traceback", [])})
    count = sum(1 for c in nb["cells"] if c.get("execution_count")) + 1
    cell = {"cell_type": "code", "metadata": {}, "source": a["source"].splitlines(keepends=True),
            "execution_count": count if ran else None, "outputs": outputs}
    if isinstance(a.get("index"), int) and a["index"] < len(nb["cells"]):
        nb["cells"][a["index"]] = cell
    else:
        nb["cells"].append(cell)
    world.write(rel, json.dumps(nb, indent=1))
    world.view_top = max(0, len(_render_notebook(world.read(rel))) - world.viewport)  # the cell just typed is in view


# ----------------------------------------------------------------------------------------------------- grading


def _status(step: dict, world: World) -> tuple[str, dict]:
    """The step's verdict as LessonSession reaches it from the checks module:
    * precision mode is on (a lesson folder on disk), and a failing screen_absent row vetoes the files-only route;
    * latch (session._settle_checks): a screen_contains row that passed this step stays passed, unless it is a VS Code
      row whose file (the one on screen when it passed) no longer has the pattern: the editor's text really lacks it.
    The session's other gates (code_gate, a run step needing a run, the judge) are not replayed: this grades the
    lesson's checks."""
    gate = evaluate_gate(step, world.context(), precision_mode=bool(step.get("precision_checks")))
    defs = {c.get("id"): c for c in step.get("checks") or []}
    rows = []
    for r in gate["checks"]:
        c = defs.get(r["checkId"]) or {}
        if c.get("type") == "screen_contains":
            if r["status"] == "pass":
                world.latched[r["checkId"]] = world.open_file if c.get("app") == "Code" else None
            elif r["checkId"] in world.latched:
                f = world.latched[r["checkId"]]
                if f is None or _in_file(world, f, str(c.get("pattern") or "")):
                    r = {**r, "status": "pass", "detail": "latched: passed earlier this step"}
                else:
                    del world.latched[r["checkId"]]
        rows.append(r)
    gate = {**gate, "checks": rows}
    if rows and all(r["status"] == "pass" for r in rows) and not _cell_pending(step, world):
        return "pass", {**gate, "passed": True, "via": "checks"}
    vetoed = any(r["status"] == "fail" and (defs.get(r["checkId"]) or {}).get("type") == "screen_absent" for r in rows)
    if gate["via"] == "precision" and not vetoed:
        return "pass-precision", gate
    return ("fail" if any(r["status"] == "fail" for r in rows) else "pending"), gate


def _cell_pending(step: dict, world: World) -> bool:
    from server.checks.evaluator import cell_not_run

    return cell_not_run(step, world.context())


def _in_file(world: World, rel: str, pattern: str) -> bool:
    from server.checks.screen import search_wrapped

    text = world.read(rel)
    if rel.endswith(".ipynb"):
        text = "\n".join(_render_notebook(text))
    try:
        return bool(search_wrapped(pattern, text))
    except re.error:
        return False


def _spec_step(st: dict) -> dict:
    """The outline item's expected checks as a lesson step (for the dry run and the spec check)."""
    return {"id": "spec", "title": st.get("about", ""), "checks": [{**c, "id": c.get("id") or f"x{i}", "label": c.get("label") or c.get("pattern") or c.get("file") or c["type"]}
                                                                    for i, c in enumerate(st.get("expect_checks") or [])]}


def run_case(case: dict, dry: bool = False) -> dict:
    """Replay one case. dry=True (or no cached lesson): the expected checks stand in for the lesson's."""
    errs = validate_case(case)
    if errs:
        raise CaseError(f"{case.get('id')}: " + "; ".join(errs))
    lesson = None if dry else load_lesson(case)
    by_id = {s["id"]: s for s in (lesson or {}).get("steps", [])}
    learner = case.get("learner") or {}
    with tempfile.TemporaryDirectory(prefix=f"replay-{case['id']}-") as tmp:
        root = Path(tmp) / (learner.get("folder") or case["id"])
        root.mkdir()
        if seed := learner.get("seed"):
            shutil.copytree(REPO / seed, root, dirs_exist_ok=True)
        for rel, text in (learner.get("files") or {}).items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        world = World(root=root, viewport=int(learner.get("viewport", 60)), terminal_rows=int(learner.get("terminal_rows", 30)))
        steps_out = []
        for st in case["outline"]:
            lesson_step = by_id.get(st.get("step")) if lesson else None
            graded = lesson_step or _spec_step(st)
            if lesson and lesson_step is None:
                steps_out.append({"step": st.get("step"), "about": st["about"], "status": "missing",
                                  "detail": "no such step in the cached lesson", "expect": _expected(st)})
                continue
            steps_out.append(_play_step(world, st, graded, lesson_step, dry=lesson is None))
        return {
            "id": case["id"], "topic": case["topic"], "mode": "replay" if lesson else "dry",
            "lesson": case.get("lesson"), "lesson_steps": len(by_id) if lesson else None,
            "unscripted_steps": [s for s in by_id if s not in {o.get("step") for o in case["outline"]}],
            "steps": steps_out, "run_sources": world.run_sources,
        }


_RANK = {"pass": 3, "pass-precision": 2, "fail": 1, "pending": 1}


def _play_step(world: World, st: dict, graded: dict, lesson_step: dict | None, dry: bool) -> dict:
    """Play one step. The session advances on the first passing gate, so the step's status is the best one reached
    after any of the learner's own actions (screen checks > precision route > the final fail / pending), and a check
    that passed once stays passed for the report (the session latches screen passes). Mistake blocks are graded
    right after they are played: caught = the step does not pass then."""
    world.new_step()
    mistakes: list[dict] = []
    first_pass: int | None = None
    best: tuple[str, dict] | None = None
    spec_step = _spec_step(st)
    spec_seen: dict[str, dict] = {}
    n = 0

    def grade() -> None:
        nonlocal first_pass, best
        status, gate = _status(graded, world)
        if first_pass is None and status in ("pass", "pass-precision"):
            first_pass = n
        if best is None or _RANK[status] > _RANK[best[0]] or (_RANK[status] == _RANK[best[0]] and status not in ("pass", "pass-precision")):
            best = (status, gate)
        absent = {c["id"] for c in spec_step["checks"] if c["type"] == "screen_absent"}
        for r in evaluate_step(spec_step, world.context()):  # a pass latches, except "nothing bad showing" (as now)
            if r["checkId"] in absent or spec_seen.get(r["checkId"], {}).get("status") != "pass":
                spec_seen[r["checkId"]] = r

    for a in st.get("actions") or []:
        if a.get("do") == "mistake":
            for m in a.get("actions") or []:
                apply(world, m)
                n += 1
            status, gate = _status(graded, world)
            caught = status not in ("pass", "pass-precision")
            mistakes.append({"note": a["note"], "caught": caught, "expect_caught": a.get("caught_by_spec", True) if dry else a.get("caught", True), "status": status,
                             "finding": a.get("finding", ""),
                             "why": [f"{r['checkId']} {r['status']}: {r['detail']}" for r in gate["checks"] if r["status"] != "pass"]})
            if not caught and first_pass is None:
                first_pass = n
            continue
        apply(world, a)
        n += 1
        grade()
    if best is None:  # a step with no actions of its own: graded as the learner left it
        grade()
    status, gate = best  # type: ignore[misc]
    matched = bool(lesson_step and re.search(st["match"], f"{lesson_step.get('title', '')} {lesson_step.get('instructions', '')}", re.IGNORECASE))
    return {
        "step": st.get("step"), "about": st["about"], "status": status, "expect": _expected(st, dry),
        "note": st.get("note", ""), "finding": st.get("finding", ""), "first_pass_after_action": first_pass, "actions": n,
        "outline_match": matched if lesson_step else None,
        "checks": [{k: r[k] for k in ("checkId", "label", "status", "detail")} for r in gate["checks"]],
        "precision": [{k: r[k] for k in ("checkId", "status", "detail")} for r in gate["precision"]],
        "spec": [{k: r[k] for k in ("checkId", "label", "status", "detail")} for r in spec_seen.values()],
        "mistakes": mistakes,
    }


def problems(result: dict) -> list[str]:
    """Where a case's replay differs from what the case expects ([] = as expected)."""
    out = []
    for s in result["steps"]:
        tag = f"{result['id']}/{s.get('step') or s['about'][:30]}"
        if s["status"] not in s["expect"]:
            bad = [f"{c['checkId']} {c['status']}: {c['detail']}" for c in s.get("checks", []) if c["status"] != "pass"]
            out.append(f"{tag}: {s['status']} (expected {'/'.join(s['expect'])}) {bad}")
        if s.get("outline_match") is False:
            out.append(f"{tag}: lesson step does not match the outline ({s['about']})")
        for c in s.get("spec", []):
            if c["status"] != "pass":
                out.append(f"{tag}: expected check {c['label']!r} {c['status']}: {c['detail']}")
        for m in s.get("mistakes", []):
            if m["caught"] != m["expect_caught"]:
                out.append(f"{tag}: mistake {'caught' if m['caught'] else 'NOT caught'} (expected {'caught' if m['expect_caught'] else 'not caught'}): {m['note']}")
    return out


def findings(result: dict) -> list[str]:
    """Known lesson / checks weaknesses the case records (expected, so not failures): steps a correct learner can't
    pass, mistakes the checks don't catch."""
    out = []
    for s in result["steps"]:
        tag = f"{result['id']}/{s.get('step') or s['about'][:30]}"
        if s.get("finding"):
            out.append(f"{tag}: {s['finding']}")
        out += [f"{tag}: {m['finding']}" for m in s.get("mistakes", []) if m.get("finding")]
    return out


def needs_build(cases: list[dict]) -> list[dict]:
    return [{"id": c["id"], "topic": c["topic"], "tutorial": c["tutorial"], "steps": len(c["outline"])}
            for c in cases if not is_cached(c)]


# ----------------------------------------------------------------------------------------------------- CLI


def _report(result: dict, verbose: bool) -> str:
    lines = [f"{result['id']} [{result['mode']}] {result['topic']}"]
    for s in result["steps"]:
        mark = "ok " if s["status"] in s["expect"] else "XX "
        ms = "".join(" [mistake " + ("caught" if m["caught"] else f"missed: {m['status']}") + "]" for m in s.get("mistakes", []))
        lines.append(f"  {mark}{(s.get('step') or '-'):>5} {s['status']:<14} expect {'/'.join(s['expect']):<14} {s['about'][:52]}{ms}")
        if verbose or s["status"] not in s["expect"]:
            for c in s.get("checks", []):
                if c["status"] != "pass" or verbose:
                    lines.append(f"         {c['checkId']:<7} {c['status']:<8} {c['label']} ({c['detail']})")
    if result.get("unscripted_steps"):
        lines.append(f"  lesson steps with no learner script: {result['unscripted_steps']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append")
    ap.add_argument("--dry", action="store_true", help="grade on the expected checks only (no cached lesson needed)")
    ap.add_argument("--needs-build", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    cases = load_cases(a.only)
    if a.needs_build:
        for c in needs_build(cases):
            print(f"{c['id']:<22} {c['topic']:<12} {c['tutorial']['kind']:<5} {c['tutorial']['goal']}")
        return 0
    results, bad = [], []
    for c in cases:
        if not a.dry and not is_cached(c):
            print(f"{c['id']} [needs one paid build] {c['topic']}: lesson not cached; dry run only")
        r = run_case(c, dry=a.dry or not is_cached(c))
        results.append(r)
        bad += problems(r)
        print(_report(r, a.verbose))
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1))
    steps = [s for r in results if r["mode"] == "replay" for s in r["steps"]]
    print(f"\nreplayed {sum(r['mode'] == 'replay' for r in results)} cached lessons: "
          f"{sum(s['status'] == 'pass' for s in steps)}/{len(steps)} steps pass on screen checks, "
          f"{sum(s['status'] == 'pass-precision' for s in steps)} only via precision; "
          f"{len(needs_build(cases))} cases need one paid build")
    for r in results:
        for f in findings(r):
            print("FINDING", f)
    for p in bad:
        print("UNEXPECTED", p)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
