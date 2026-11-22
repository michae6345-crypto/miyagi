"""eng-agency-2 leftovers (offline: no model, keys unset, no network; the processes are the regex worker's own Python
and, for the pip probe, `python -m pip install --no-index` of a name that doesn't exist)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid

import pytest

from server.checks.evaluator import RunContext, evaluate_check, evaluate_gate, screen_check_on_file
from server.orchestrator.workspace import anchor_line
from server.safety import regex_worker
from server.safety.commands import PIP_SHADOWS, Allowed, Manual, parse_run_command
from server.safety.patterns import pattern_problem, safe_compile


def _near(tag: str) -> str:
    """The reviewer's probe: passes the shape checks, about 0.1 s of CPU per search on a run of 40 'a's: under the
    250 ms deadline, so never a timeout."""
    return f"(?:id{tag})?" + "a?" * 18 + "a" * 18 + "!"


RUN = "a" * 40


# ------------------------------------------------------------------ 1. a pattern just under the deadline is charged

def test_near_deadline_patterns_pass_the_shape_checks():
    assert pattern_problem(_near("x")) is None


def test_24_near_deadline_checks_stop_after_the_lessons_cpu_allowance():
    """24 screen_contains checks that each cost ~0.1 s per search: the first frames spend about LESSON_CPU_S, then
    the lesson's slow-capable patterns stop running (no timeout was needed), and every later frame is cheap."""
    nonce = uuid.uuid4().hex[:8]
    step = {"id": "s1", "checks": [{"id": f"c{i}", "type": "screen_contains", "app": "Code", "label": f"row {i}",
                                    "pattern": _near(f"{nonce}{i}")} for i in range(24)]}
    with regex_worker.budget(("near-deadline", nonce)) as b:
        t0 = time.monotonic()
        for f in range(3):  # each frame has new text (no cache)
            evaluate_gate(step, RunContext(workdir="/nonexistent"),
                          screen={"Code": [f"frame {f} {RUN} {uuid.uuid4().hex}"]})
            if b.exhausted:
                break
        spent = time.monotonic() - t0
        assert b.exhausted and b.cpu >= regex_worker.LESSON_CPU_S
        assert spent < regex_worker.LESSON_CPU_S + 1.5  # the allowance and one search over it, not 8 s per frame
        t0 = time.monotonic()
        gate = evaluate_gate(step, RunContext(workdir="/nonexistent"),
                             screen={"Code": [f"later {RUN} {uuid.uuid4().hex}"]})
        assert time.monotonic() - t0 < 0.3
    assert all(c["status"] != "pass" for c in gate["checks"])


def test_a_real_lessons_searches_cost_a_sliver_of_the_allowance():
    text = "\n".join(f"epoch {i} loss: {1 / (i + 1):.4f} acc: {i % 100}" for i in range(80))
    with regex_worker.budget(("real", uuid.uuid4().hex)) as b:
        for i in range(2000):
            safe_compile(r"loss:\s*[\d.]+\s*(?:ok|done)?").search(f"{text}\n{i}")
    assert b.cpu < 0.1 * regex_worker.LESSON_CPU_S and not b.exhausted


def test_the_cpu_charge_expires_with_the_window(monkeypatch):
    b = regex_worker.Budget("cpu-decay")
    b.charge(regex_worker.LESSON_CPU_S)
    assert b.exhausted
    now = time.monotonic()
    monkeypatch.setattr(regex_worker.time, "monotonic", lambda: now + regex_worker.LESSON_WINDOW_S + 1)
    assert b.cpu == 0.0 and not b.exhausted


def test_anchor_line_is_one_search_however_many_lines(monkeypatch):
    """One target over 60 distinct lines: one worker request (the deadline bounds it), never one per line."""
    calls, real = [], regex_worker._WORKER.call

    def call(req, limit_s=regex_worker.DEADLINE_S):
        calls.append(limit_s)
        return real(req, limit_s)

    monkeypatch.setattr(regex_worker._WORKER, "call", call)
    text = "".join(f"row{i} = '{RUN}'  # {uuid.uuid4().hex}\n" for i in range(60))
    with regex_worker.budget(("anchor", uuid.uuid4().hex)):
        t0 = time.monotonic()
        assert anchor_line(text, _near(uuid.uuid4().hex[:8])) is None
        took = time.monotonic() - t0
    assert len(calls) <= 2  # a timeout's second try at most
    assert took < regex_worker.DEADLINE_S + regex_worker.CONFIRM_S + 0.5


def test_anchor_line_keeps_its_line_numbers():
    code = "import sys\r\n\r\ndef add(a, b):\r\n    return a + b\r\n"
    assert anchor_line(code, "return a + b") == 4  # the literal text first
    assert anchor_line(code, r"def\s+add\(") == 3
    assert anchor_line(code, r"^\s+return\b") == 4  # ^ at each line
    assert anchor_line("a\rb\x0bdef f():\n", r"^def f") == 3  # splitlines' breaks
    assert anchor_line(code, r"def\s+sub\(") is None


# ------------------------------------------------------------------ 2. a notebook's code is searched before outputs

def _cell(src: str, outputs: list | None = None) -> dict:
    return {"cell_type": "code", "execution_count": 1, "metadata": {}, "source": src.splitlines(keepends=True),
            "outputs": outputs or []}


def _nb(path, cells) -> None:
    path.write_text(json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}, indent=1))


def _table(i: int) -> dict:
    rows = "".join(f"<tr><th>{r}</th><td>{r * i}</td><td>{r / (i + 1):.6f}</td><td>{r * 0.37 + i:.4f}</td>"
                   f"<td>{(r * 7919 + i) % 1000}</td><td>label_{r % 7}</td></tr>\n" for r in range(40))
    plain = "".join(f"{r:>4}  {r * i:>8}  {r / (i + 1):.6f}  {r * 0.37 + i:>10.4f}  {(r * 7919 + i) % 1000:>4}  "
                    f"label_{r % 7}\n" for r in range(40))
    return {"output_type": "execute_result", "execution_count": i, "metadata": {},
            "data": {"text/html": f"<table class='dataframe'>\n{rows}</table>\n", "text/plain": plain}}


def test_a_notebook_with_over_1mb_of_tables_still_finds_its_first_cells_import(tmp_path):
    cells = [_cell("import numpy as np\nimport pandas as pd\n")]
    cells += [_cell(f"df{i} = make({i})\ndf{i}.head(40)\n", [_table(i)]) for i in range(200)]
    nb = tmp_path / "explore.ipynb"
    _nb(nb, cells)
    assert nb.stat().st_size > 1024 * 1024
    ctx = RunContext(workdir=str(tmp_path))
    for pattern in (r"import numpy as np", r"df199\.head\(40\)", r"label_3"):
        res = evaluate_check({"id": "c", "type": "file_contains", "file": "explore.ipynb", "pattern": pattern}, ctx)
        assert res["status"] == "pass", (pattern, res)
    res = screen_check_on_file({"id": "c", "type": "screen_contains", "pattern": "import numpy as np"}, str(nb))
    assert res["status"] == "pass", res


def test_a_notebook_with_300_cells_of_stream_output_still_finds_its_import(tmp_path):
    log = "".join(f"step {k}: loss {1 / (k + 1):.6f} accuracy {k % 100}%\n" for k in range(90))  # ~3.6 KB
    cells = [_cell("import pandas as pd\n")]
    cells += [_cell(f"train({i})\n", [{"output_type": "stream", "name": "stdout", "text": log}]) for i in range(300)]
    nb = tmp_path / "train.ipynb"
    _nb(nb, cells)
    assert nb.stat().st_size > 1024 * 1024
    res = evaluate_check({"id": "c", "type": "file_contains", "file": "train.ipynb", "pattern": r"import pandas as pd"},
                         RunContext(workdir=str(tmp_path)))
    assert res["status"] == "pass", res


# ------------------------------------------------------------------ 3. only what `-m pip` really imports is a shadow

@pytest.mark.parametrize("make", ["random.py", "json.py", "calendar.py", "code.py", "queue.py", "email/__init__.py",
                                  "keyring.py", "socks.py", "_sysconfigdata__darwin_darwin.py", "logging.py",
                                  "test.py", "turtle.py"])
def test_a_lesson_file_pip_never_imports_from_the_folder_is_not_a_shadow(tmp_path, make):
    target = tmp_path / make
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('a lesson file')\n")
    res = parse_run_command("python3 -m pip install numpy", tmp_path)
    assert isinstance(res, Allowed) and res.argv == ("python3", "-m", "pip", "install", "numpy"), res


@pytest.mark.parametrize("make", ["pip.py", "runpy.py", "types.py", "Threading.py", "traceback.pyc",
                                  "typing/__init__.py"])
def test_what_pip_imports_before_it_leaves_the_folder_is_still_manual(tmp_path, make):
    target = tmp_path / make
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('HIJACKED')\n")
    res = parse_run_command("python3 -m pip install numpy", tmp_path)
    assert isinstance(res, Manual) and not res.structural and make.split("/")[0] in res.reason, res


def _pythons_with_pip() -> list[str]:
    """Interpreters to probe: the one this venv was made from (never /usr/bin's shims, which may offer to install
    the command line tools in a window)."""
    out = []
    for cand in (getattr(sys, "_base_executable", None), shutil.which("python3.15"), "/opt/homebrew/bin/python3"):
        if not cand or cand.startswith("/usr/bin/") or not os.path.isfile(cand):
            continue
        cand = os.path.realpath(cand)
        if cand in out:
            continue
        try:
            ok = subprocess.run([cand, "-I", "-c", "import pip"], capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if ok:
            out.append(cand)
    return out


def test_a_real_pip_install_imports_only_the_listed_names_from_the_folder(tmp_path):
    """Every standard-library name not in PIP_SHADOWS as a <name>.py in the folder, each recording its import:
    `python -m pip install --no-index --target <tmp>` of a name that doesn't exist (offline, nothing installed)
    imports none of them; pip.py itself is (the probe can see a shadow)."""
    pys = _pythons_with_pip()
    if not pys:
        pytest.skip("no python with pip outside a venv")
    names = sorted({n for n in getattr(sys, "stdlib_module_names", ())
                    if n.isidentifier() and not n.startswith("_frozen")} - PIP_SHADOWS
                   - {"sys", "builtins", "_io", "marshal", "posix", "_imp", "_thread", "_warnings", "_weakref"})
    marks = tmp_path / "marks"
    marks.mkdir()
    lesson = tmp_path / "lesson"
    lesson.mkdir()
    for n in names:
        (lesson / f"{n}.py").write_text(f"open({str(marks / n)!r}, 'w').close()\n")
    (lesson / "pip.py").write_text(f"open({str(marks / 'pip')!r}, 'w').close()\nraise SystemExit(0)\n")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1",
           "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    for py in pys:
        subprocess.run([py, "-m", "pip", "install", "--no-index", "--no-deps", "--target", str(tmp_path / "t"),
                        f"miyagi-no-such-{uuid.uuid4().hex}"], cwd=lesson, env=env, capture_output=True, timeout=120)
        assert sorted(p.name for p in marks.iterdir()) == ["pip"], py  # pip.py ran (its stop: nothing else did)
        (marks / "pip").unlink()
        (lesson / "pip.py").rename(lesson / "pip_off.txt")
        real = subprocess.run([py, "-m", "pip", "install", "--no-index", "--no-deps", "--target", str(tmp_path / "t"),
                               f"miyagi-no-such-{uuid.uuid4().hex}"], cwd=lesson, env=env, capture_output=True,
                              text=True, timeout=120)
        assert "No matching distribution" in real.stdout + real.stderr, (py, real.stderr[-400:])  # pip really ran
        assert sorted(p.name for p in marks.iterdir()) == [], py  # and imported none of the others from the folder
        (lesson / "pip_off.txt").rename(lesson / "pip.py")
