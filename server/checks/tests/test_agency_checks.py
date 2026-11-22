"""A lesson's checks can't read files outside the lesson folder or run a catastrophic regex (offline)."""
from __future__ import annotations

import time

import pytest

from server.checks.evaluator import RunContext, evaluate_check, pattern_problem
from server.lesson.schema import validate_untrusted_lesson


def _graph(*checks):
    return {"lesson": {"id": "x", "title": "x"}, "sources": [],
            "steps": [{"id": "s1", "index": 1, "title": "t", "instructions": "i", "checks": [],
                       "precision_checks": list(checks)}]}


@pytest.mark.parametrize("file", ["/Users/x/.aws/credentials", "../../.ssh/id_rsa", "~/.ssh/id_rsa"])
def test_a_file_check_outside_the_folder_is_dropped_at_validation_and_refused_at_run(tmp_path, file):
    c = {"id": "p1", "type": "file_contains", "label": "x", "file": file, "pattern": "aws_secret"}
    g = _graph(c, {"id": "p2", "type": "file_contains", "label": "ok", "file": "main.py", "pattern": "def"})
    notes = validate_untrusted_lesson(g, str(tmp_path))
    assert [x["id"] for x in g["steps"][0]["precision_checks"]] == ["p2"] and notes
    r = evaluate_check(c, RunContext(workdir=str(tmp_path)))
    assert r["status"] == "fail" and "outside the lesson folder" in r["detail"]
    assert evaluate_check({**c, "type": "file_exists"}, RunContext(workdir=str(tmp_path)))["status"] == "fail"


def test_a_file_check_via_a_symlink_out_of_the_folder_is_refused(tmp_path, tmp_path_factory):
    import os

    secret = tmp_path_factory.mktemp("home") / "credentials"
    secret.write_text("aws_secret_access_key = x\n")
    os.symlink(secret, tmp_path / "creds.txt")
    c = {"id": "p1", "type": "file_contains", "label": "x", "file": "creds.txt", "pattern": "aws_secret"}
    assert evaluate_check(c, RunContext(workdir=str(tmp_path)))["status"] == "fail"


@pytest.mark.parametrize("pattern", ["(a|aa)+$", "(x+)+y", "(x*)*", "(\\w+\\s*)+$", "(a?)*b", "x" * 401])
def test_catastrophic_patterns_are_rejected_at_lesson_load(tmp_path, pattern):
    c = {"id": "c1", "type": "screen_contains", "label": "x", "app": "Terminal", "pattern": pattern}
    g = _graph()
    g["steps"][0]["checks"] = [c]
    assert validate_untrusted_lesson(g, str(tmp_path)) and g["steps"][0]["checks"] == []
    assert pattern_problem(pattern)


def test_a_bad_pattern_that_skipped_validation_never_runs(tmp_path):
    (tmp_path / "f.txt").write_text("a" * 40 + "!")
    c = {"id": "p1", "type": "file_contains", "label": "x", "file": "f.txt", "pattern": "^(a|aa)+$"}
    t0 = time.monotonic()
    r = evaluate_check(c, RunContext(workdir=str(tmp_path)))
    assert r["status"] == "fail" and "invalid pattern" in r["detail"] and time.monotonic() - t0 < 1


@pytest.mark.parametrize("pattern", [r"def add\(", r"loss[:=]\s*([0-9.]+)", r"(?:\d{1,3}\.){3}\d{1,3}",
                                     r"Hello, (World|there)!", r"(foo|bar)+", r"epoch\s+\d+/\d+"])
def test_ordinary_patterns_still_run(pattern):
    assert pattern_problem(pattern) is None


def test_screen_patterns_see_only_the_newest_4kb(tmp_path):
    screen = {"Terminal": ["SECRET-MARKER"] + ["x" * 100] * 60}
    c = {"id": "c1", "type": "screen_contains", "label": "x", "app": "Terminal", "pattern": "SECRET-MARKER"}
    assert evaluate_check(c, RunContext(workdir=str(tmp_path), screen=screen))["status"] != "pass"
    c2 = {**c, "pattern": "x{100}"}
    assert evaluate_check(c2, RunContext(workdir=str(tmp_path), screen=screen))["status"] == "pass"
