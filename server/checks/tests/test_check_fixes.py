"""Regression tests for the false passes / false not-yets the step-check evals found (server/evals/checks). Offline."""
from __future__ import annotations

import math

import pytest

from server.checks import RunContext, evaluate_gate, extract_metrics
from server.checks.code_text import canonical_params, function_scope, strip_comments
from server.checks.evaluator import _absent_hit, _without_typed_input


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


# -- 1. nan / inf in a metric line ------------------------------------------------------------------------------------
LOSS = r"epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>[0-9Oo.eE+-]+)"


@pytest.mark.parametrize("word", ["nan", "NaN", "-inf", "inf", "Infinity"])
def test_a_nonfinite_metric_value_is_read_not_skipped(word):
    pts = extract_metrics(LOSS, f"epoch 10 loss 0.5\nepoch 20 loss {word}")
    assert [s for s, _ in pts] == [10, 20] and not math.isfinite(pts[1][1])


def test_a_pattern_whose_value_group_has_nested_parens_still_reads_nan():
    pts = extract_metrics(r"loss=(?P<value>(?:\d+\.\d+)|[a-z]+)", "loss=nan")
    assert len(pts) == 1 and math.isnan(pts[0][1])


def test_a_nan_loss_after_a_good_one_fails_the_threshold():
    step = {"id": "s", "checks": [{"id": "c", "type": "metric_threshold", "label": "loss", "metric": "loss", "op": "<",
                                   "value": 0.01, "metric_pattern": LOSS, "app": "Terminal"}]}
    screen = {"Terminal": ["epoch 1 loss 0.004", "epoch 2 loss nan"]}
    g = evaluate_gate(step, RunContext(screen=screen))
    assert not g["passed"] and "diverged" in g["checks"][0]["detail"]


# -- 2. a hidden terminal: only the step's own command's output counts ------------------------------------------------
RUN_STEP = {"id": "s2", "run_command": "python3 calculator.py",
            "checks": [{"id": "c", "type": "screen_contains", "label": "prints 5", "app": "Terminal",
                        "pattern": r"^\s*5\s*$"}]}


def test_another_scripts_output_does_not_pass_a_hidden_terminal_step():
    screen = {"Code": ["scratch.py"]}
    other = _gate(RUN_STEP, screen=screen, command="python3 scratch.py", exit_code=0, output_tail=["5"])
    own = _gate(RUN_STEP, screen=screen, command="python3 calculator.py", exit_code=0, output_tail=["5"])
    assert not other["passed"] and "calculator.py" in other["checks"][0]["detail"]
    assert own["passed"]


# -- 3. typed at the prompt, Enter not pressed ------------------------------------------------------------------------
BRANCH = {"id": "s7", "checks": [{"id": "c", "type": "screen_contains", "label": "branch", "app": "Terminal",
                                  "pattern": "update-name"}]}


def test_a_command_typed_at_the_prompt_is_not_a_run_one():
    typed = {"Terminal": ["me@mac x % git status", "On branch main", "me@mac x % git checkout -b update-name"]}
    ran = {"Terminal": ["me@mac x % git checkout -b update-name", "Switched to a new branch 'update-name'",
                        "me@mac x % "]}
    assert not evaluate_gate(BRANCH, RunContext(screen=typed))["passed"]
    assert evaluate_gate(BRANCH, RunContext(screen=ran))["passed"]


def test_a_command_with_no_output_followed_by_a_new_prompt_counts():
    ran = {"Terminal": ["me@mac x % git checkout -b update-name", "me@mac x %"]}
    assert evaluate_gate(BRANCH, RunContext(screen=ran))["passed"]


@pytest.mark.parametrize("text,out", [
    ("a % ls\nfile\nb % echo hi", "a % ls\nfile"),
    ("a % ls\nfile\nb %", "a % ls\nfile\nb %"),
    ("100% done", "100% done"),
    ("➜  nn git:(main) ✗ python3 x.py", ""),
])
def test_without_typed_input(text, out):
    assert _without_typed_input(text) == out


# -- 4. commented-out code ----------------------------------------------------------------------------------------------
ADD = {"id": "s1", "code": "def add(a, b):\n    return a + b\n\nprint(add(2, 3))",
       "checks": [{"id": "c1", "type": "screen_contains", "label": "The add function is typed", "app": "Code",
                   "pattern": r"def\s+add\(a,\s*b\):"},
                  {"id": "c2", "type": "screen_contains", "label": "add() returns a + b", "app": "Code",
                   "pattern": r"return\s+a\s*\+\s*b"}],
       "precision_checks": [{"id": "p1", "type": "file_contains", "label": "add() is in calculator.py",
                             "file": "calculator.py", "pattern": r"def\s+add\(a,\s*b\):"}]}


def test_commented_out_code_does_not_pass():
    lines = ["calculator.py", "# def add(a, b):", "#     return a + b"]
    assert not evaluate_gate(ADD, RunContext(screen={"Code": lines}))["passed"]


def test_commented_out_code_in_the_file_does_not_pass(tmp_path):
    (tmp_path / "calculator.py").write_text("# def add(a, b):\n#     return a + b\n")
    g = evaluate_gate(ADD, RunContext(workdir=str(tmp_path)), precision_mode=True)
    assert not g["passed"]
    (tmp_path / "calculator.py").write_text("def add(a, b):  # sum\n    return a + b\n")
    assert evaluate_gate(ADD, RunContext(workdir=str(tmp_path)), precision_mode=True)["precision"][0]["status"] == "pass"


def test_strip_comments_keeps_strings_and_lines():
    py = 'x = "# not a comment"  # real\n# whole\ny = 2\n'
    assert strip_comments(py, "py") == 'x = "# not a comment"  \n\ny = 2\n'
    js = 'const u = "http://a.b"; // c\n/* x\n y */ let z = 1;'
    assert strip_comments(js, "c") == 'const u = "http://a.b"; \n\n let z = 1;'
    assert strip_comments("# a\nint x;\n#include <a.h>", None) == "\nint x;\n#include <a.h>"


def test_a_check_about_a_comment_still_sees_it():
    step = {"id": "s", "checks": [{"id": "c", "type": "screen_contains", "label": "x", "app": "Code",
                                   "file": "a.py", "pattern": "# Step 1"}]}
    assert evaluate_gate(step, RunContext(screen={"Code": ["# Step 1: go"]}))["passed"]


# -- 5. the guard went into the wrong function -----------------------------------------------------------------------
GUARD = {"id": "s4", "code": 'if b == 0:\n    raise ValueError("Cannot divide by zero")',
         "checks": [{"id": "c", "type": "screen_contains", "label": "divide() raises a ValueError", "app": "Code",
                     "pattern": r"raise\s+ValueError"}]}


def test_a_guard_in_another_function_does_not_pass():
    wrong = ["calculator.py", "def multiply(a, b):", "if b == 0:", 'raise ValueError("x")', "return a * b",
             "def divide(a, b):", "return a / b"]
    right = ["calculator.py", "def divide(a, b):", "if b == 0:", 'raise ValueError("x")', "return a / b"]
    assert not evaluate_gate(GUARD, RunContext(screen={"Code": wrong}))["passed"]
    assert evaluate_gate(GUARD, RunContext(screen={"Code": right}))["passed"]


def test_function_scope_uses_ast_then_indentation_then_next_def():
    src = "def a():\n    return 1\n\ndef b():\n    raise ValueError\n"
    assert "ValueError" not in function_scope(src, "a") and "ValueError" in function_scope(src, "b")
    broken = "def a(:\n    x = 1\n  y\ndef b():\n    raise E\n"  # does not parse: indentation decides
    assert "raise" not in function_scope(broken, "a")
    flat = "def a():\nx = 1\ndef b():\nraise E"  # OCR text without indentation: ends at the next def
    assert function_scope(flat, "a") == "def a():\nx = 1\n"
    assert function_scope(src, "missing") is None


# -- 6. a printed "Error" label is not an error ---------------------------------------------------------------------------
@pytest.mark.parametrize("line,hit", [
    ("Relative L2 Error: 3.1e-02", False),
    ("final error rate 0.02", False),
    ("Traceback (most recent call last):", True),
    ("ValueError: bad", True),
    ("Error: cannot find module", True),
    ("gcc: error: no input files", True),
    ("npm ERR! code ELIFECYCLE", True),
])
def test_screen_absent_error_forms(line, hit):
    assert bool(_absent_hit("Traceback|Error|error|ERR!|NotImplementedError", "ok\n" + line)) is hit


def test_a_script_that_prints_its_error_metric_passes_no_errors():
    step = {"id": "s", "checks": [{"id": "c", "type": "screen_absent", "label": "No terminal errors",
                                   "app": "Terminal", "pattern": "Traceback|Error"}]}
    ok = {"Terminal": ["epoch 3900 loss 0.02", "Relative L2 Error: 3.1e-02"]}
    bad = {"Terminal": ["epoch 3900 loss 0.02", "NameError: name 'x' is not defined"]}
    assert evaluate_gate(step, RunContext(screen=ok))["passed"]
    assert not evaluate_gate(step, RunContext(screen=bad))["passed"]


# -- 7. trend windows follow the logging cadence ---------------------------------------------------------------------
def test_a_small_trend_window_widens_to_the_logging_cadence():
    step = {"id": "s", "checks": [{"id": "c", "type": "metric_trend", "label": "loss falls", "metric": "loss",
                                   "trend": "decreasing", "window": 5}]}
    falling = [(i * 100, 1.2 * 0.9 ** i) for i in range(40)]
    flat = [(i * 100, 0.25 + (0.0005 if i % 2 else 0)) for i in range(40)]
    assert evaluate_gate(step, RunContext(metrics={"loss": falling}))["passed"]
    assert not evaluate_gate(step, RunContext(metrics={"loss": flat}))["passed"]


# -- 8. other parameter names ---------------------------------------------------------------------------------------------
def test_other_parameter_names_pass_for_the_same_function():
    xy = ["calculator.py", "def add(x, y):", "return x + y"]
    assert evaluate_gate(ADD, RunContext(screen={"Code": xy}))["passed"]


def test_other_names_do_not_hide_a_wrong_body_or_arity():
    wrong_body = ["calculator.py", "def add(x, y):", "return x - y"]
    other_arity = ["calculator.py", "def add(x, y, z):", "return x + y"]
    assert not evaluate_gate(ADD, RunContext(screen={"Code": wrong_body}))["passed"]
    assert not evaluate_gate(ADD, RunContext(screen={"Code": other_arity}))["passed"]


def test_canonical_params_renames_only_inside_the_function():
    text = "def add(x, y):\n    return x + y\n\nx = 5\n"
    assert canonical_params(text, {"add": ["a", "b"]}) == "def add(a, b):\n    return a + b\n\nx = 5\n"
    assert canonical_params("def swap(a, b):\n    return b, a\n", {"swap": ["b", "a"]}) \
        == "def swap(b, a):\n    return a, b\n"


# -- notebook: a finished cell below the bar fails; details name the learner's notebook --------------------------------
def _nb_step():
    pat = r"accuracy:\s*(?P<value>[0-9.]+)"
    return {"id": "s5", "run_command": "Run the cell (Shift+Enter)", "code": "model.fit(x, y, epochs=3)",
            "targets": [{"app": "Code", "file": "Untitled.ipynb", "match": "model.fit(x, y, epochs=3)"}],
            "checks": [{"id": "c", "type": "metric_threshold", "label": "accuracy over 95%", "metric": "accuracy",
                        "op": ">", "value": 0.95, "metric_pattern": pat, "app": "Code"}]}


def _nb(tmp_path, name, stdout):
    from server.evals.checks.runner import build_workdir

    build_workdir({name: {"notebook": {"cells": [{"source": "model.fit(x, y, epochs=3)", "stdout": stdout}]}}},
                  tmp_path)


def test_a_finished_notebook_cell_below_the_metric_bar_fails_not_pends(tmp_path):
    _nb(tmp_path, "mnist.ipynb", "accuracy: 0.80\naccuracy: 0.91\n")
    g = evaluate_gate(_nb_step(), RunContext(workdir=str(tmp_path)))
    assert g["checks"][0]["status"] == "fail"


def test_a_notebook_cell_that_met_the_bar_passes_naming_the_learners_notebook(tmp_path):
    _nb(tmp_path, "mnist.ipynb", "accuracy: 0.97\n")
    r = evaluate_gate(_nb_step(), RunContext(workdir=str(tmp_path)))["checks"][0]
    assert r["status"] == "pass" and "mnist.ipynb" in r["detail"] and "Untitled" not in r["detail"]


def test_a_missing_notebook_detail_names_the_learners_notebook_not_the_videos(tmp_path):
    _nb(tmp_path, "mnist.ipynb", "")
    step = {"id": "s", "targets": [{"app": "Code", "file": "Untitled.ipynb"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "x", "app": "Code",
                        "pattern": "nothing like this"}]}
    r = evaluate_gate(step, RunContext(workdir=str(tmp_path), screen={"Code": ["print(1)"]}))["checks"][0]
    assert r["status"] == "fail" and "Untitled" not in r["detail"]
