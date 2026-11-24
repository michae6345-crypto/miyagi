"""Regression tests for the review of the round-3 step-check fixes: the general rules added there must not fail a
learner who did the step (a quote closed on the next row, a notebook cell re-run for another reason, a Pylance error
in another file, a skip the project ships). Offline: no model, no network."""
from __future__ import annotations

import json
import os
import time

from server.checks import RunContext, blocks, evaluate_gate


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _term(*rows):
    return {"Terminal": list(rows)}


# -- terminal: a continuation prompt the learner finished --------------------------------------------------------------

_COMMIT_STEP = {"id": "s5", "targets": [{"app": "Terminal", "match": "git commit -m"}],
                "checks": [{"id": "c", "type": "screen_contains", "label": "Commit recorded", "app": "Terminal",
                            "pattern": r"Add\s+waffles"}]}


def test_a_multi_line_quoted_commit_the_learner_closed_ran():
    rows = ['me@mac p % git commit -m "Add waffles', 'dquote> to the menu"', "[main 1a2b3c4] Add waffles to the menu",
            " 1 file changed, 2 insertions(+)", "me@mac p % "]
    assert blocks.parse(rows)[0].failure() is None
    assert _gate(_COMMIT_STEP, screen=_term(*rows))["passed"]
    # closed on the next row and printed nothing yet: still not waiting
    assert blocks.parse(['me@mac p % echo "a', 'dquote> b" > f.txt', "me@mac p % "])[0].failure() is None


def test_a_completed_heredoc_ran():
    rows = ["me@mac p % cat > notes.txt <<EOF", "heredoc> hello", "heredoc> EOF", "me@mac p % "]
    assert blocks.parse(rows)[0].failure() is None
    assert blocks.parse(["me@mac p % cat > notes.txt <<'END'", "heredoc> a \"quote", "heredoc> END",
                         "me@mac p % "])[0].failure() is None
    # no end word yet: the shell is still waiting, the file was never written
    assert blocks.parse(["me@mac p % cat > notes.txt <<EOF", "heredoc> hello"])[0].failure() is not None


def test_a_continuation_prompt_left_open_or_cancelled_never_ran():
    open_rows = ['me@mac p % git commit -m "Add waffles', "dquote> to the menu"]
    assert blocks.parse(open_rows)[0].failure() is not None
    assert not _gate(_COMMIT_STEP, screen=_term(*open_rows))["passed"]
    cancelled = ['me@mac p % git commit -m "Add waffles', "dquote> to the menu^C", "me@mac p % "]
    assert blocks.parse(cancelled)[0].failure() is not None
    assert not _gate(_COMMIT_STEP, screen=_term(*cancelled))["passed"]
    assert blocks.parse(['me@mac p % git commit -m "Add waffles', "dquote> x", "^C", "me@mac p % "])[0].failure()
    # a pipe finished on its continuation row ran
    assert blocks.parse(["me@mac p % ls |", "pipe> wc -l", "       3", "me@mac p % "])[0].failure() is None


# -- Jupyter: a missing run count that need not be the self-updating cell's ------------------------------------------

_NORMALIZE = "x = x.astype('float32') / 255"
_NB_STEP = {"id": "s2", "run_command": "Run the cell (Shift+Enter)", "code": _NORMALIZE,
            "targets": [{"app": "Code", "file": "mnist.ipynb", "match": _NORMALIZE}],
            "checks": [{"id": "c", "type": "file_contains", "label": "typed", "file": "mnist.ipynb", "pattern": r"\w"}]}


def _nb(tmp_path, *cells):
    out = [{"cell_type": "code", "metadata": {}, "source": src, "outputs": [], "execution_count": n}
           for src, n in cells]
    (tmp_path / "mnist.ipynb").write_text(json.dumps({"cells": out, "metadata": {}, "nbformat": 4,
                                                      "nbformat_minor": 5}))


def test_an_inspect_cell_re_run_does_not_count_as_a_second_normalize(tmp_path):
    _nb(tmp_path, ("x = load()", 1), ("print(x.max())", 4), (_NORMALIZE, 3))
    assert _gate(_NB_STEP, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, ("x = load()", 1), ("plt.imshow(x[0])", 4), (_NORMALIZE, 3))
    assert _gate(_NB_STEP, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, ("x = load()", 1), ("print(x.shape)", 3), (_NORMALIZE, 5))  # [2] or [4] may be the inspect cell
    assert _gate(_NB_STEP, workdir=str(tmp_path))["passed"]


def test_a_typo_fixed_and_re_run_is_not_blocked(tmp_path):
    # [2] raised a NameError before its assignment (a typo), the fixed cell ran at [3]; a deleted scratch cell leaves
    # the same counts
    _nb(tmp_path, ("x = load()", 1), (_NORMALIZE, 3))
    assert _gate(_NB_STEP, workdir=str(tmp_path))["passed"]


def test_a_self_updating_cell_run_three_times_with_nothing_else_run_still_fails(tmp_path):
    _nb(tmp_path, ("x = load()", 1), (_NORMALIZE, 4))
    gate = _gate(_NB_STEP, workdir=str(tmp_path))
    assert not gate["passed"] and "3 times" in gate["checks"][-1]["detail"]
    _nb(tmp_path, ("x = load()", 3), (_NORMALIZE, 4))  # the load ran again first
    assert _gate(_NB_STEP, workdir=str(tmp_path))["passed"]


# -- TypeScript: VS Code's error count is the whole workspace's ------------------------------------------------------

_TSC_STEP = {"id": "ts4", "run_command": "npx tsc && node dist/invoice.js", "file": "src/invoice.ts",
             "checks": [{"id": "c", "type": "screen_contains", "label": "total printed", "app": "Terminal",
                         "pattern": r"Invoice\s+total"}]}
_TSC_TERM = ["me@mac i % node dist/invoice.js", "Invoice total: $30.50", "me@mac i % "]


def test_a_pylance_error_in_the_problems_panel_does_not_fail_a_tsc_step():
    code = ["invoice.ts", "PROBLEMS 1", "scratch.py 1", '"np" is not defined Pylance(reportUndefinedVariable)',
            "⊗ 1 ⚠ 0"]
    assert _gate(_TSC_STEP, screen={"Code": code, "Terminal": _TSC_TERM})["passed"]
    ts = ["invoice.ts", "PROBLEMS 1", "Argument of type 'string' is not assignable to parameter of type 'number'. "
          "ts(2345)", "⊗ 1 ⚠ 0"]
    gate = _gate(_TSC_STEP, screen={"Code": ts, "Terminal": _TSC_TERM})
    assert not gate["passed"] and "1 error" in gate["checks"][-1]["detail"]


def test_an_error_count_in_a_workspace_with_python_files_needs_a_ts_error_on_screen(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "invoice.ts").write_text("console.log('Invoice total: $30.50')\n")
    (tmp_path / "tools.py").write_text("print(np)\n")
    screen = {"Code": ["invoice.ts", "⊗ 1 ⚠ 0"], "Terminal": _TSC_TERM}
    assert _gate(_TSC_STEP, screen=screen, workdir=str(tmp_path))["passed"]
    (tmp_path / "tools.py").unlink()
    assert not _gate(_TSC_STEP, screen=screen, workdir=str(tmp_path))["passed"]


# -- tests the project skips on purpose --------------------------------------------------------------------------------

_PYTEST_STEP = {"id": "t4", "instructions": "Run pytest. Every test should pass.", "run_command": "pytest",
                "targets": [{"app": "Terminal", "match": "pytest"}],
                "checks": [{"id": "c", "type": "screen_contains", "label": "Tests pass", "app": "Terminal",
                            "pattern": r"\d+\s+passed"}]}
_PYTEST_RUN = _term("me@mac s % pytest", "tests/test_io.py ..s", "===== 2 passed, 1 skipped in 0.1s =====",
                    "me@mac s % ")


def test_a_platform_skip_the_project_ships_does_not_fail_every_test_passes(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_io.py").write_text(
        "import sys, pytest\n\n\ndef test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n\n\n"
        "@pytest.mark.skipif(sys.platform == 'darwin', reason='windows only')\ndef test_c():\n    assert 3\n")
    assert _gate(_PYTEST_STEP, screen=_PYTEST_RUN, workdir=str(tmp_path))["passed"]


def test_a_skip_the_learner_added_still_fails_and_a_shipped_one_does_not(tmp_path):
    (tmp_path / "tests").mkdir()
    test = tmp_path / "tests" / "test_io.py"
    test.write_text("import pytest\n\n\ndef test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n\n\n"
                    "@pytest.mark.skip\ndef test_c():\n    assert 0\n")
    gate = _gate(_PYTEST_STEP, screen=_PYTEST_RUN, workdir=str(tmp_path))
    assert not gate["passed"] and "skipped" in gate["checks"][0]["detail"]
    started = time.time()
    os.utime(test, (started - 3600, started - 3600))  # the file came with the lesson and was not edited
    assert _gate(_PYTEST_STEP, screen=_PYTEST_RUN, workdir=str(tmp_path), lesson_started_at=started)["passed"]


def test_a_skip_the_step_expects_does_not_fail():
    step = {**_PYTEST_STEP, "instructions": "Run pytest. All tests pass (2 passed, 1 skipped: the Windows one)."}
    assert _gate(step, screen=_PYTEST_RUN)["passed"]
    more = _term("me@mac s % pytest", "===== 1 passed, 2 skipped in 0.1s =====", "me@mac s % ")
    assert not _gate(step, screen=more)["passed"]
