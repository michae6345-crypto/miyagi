"""Regression tests for the review of the round-1 step-check fixes: false passes from the "any name will do" file
fallback, false fails from the step's-own-command rule, a NaN from an older run, a live run's pending, and float
rounding kept to model dumps. Offline: no model, no network."""
from __future__ import annotations

import json
import os
import time

import pytest

from server.checks import RunContext, blocks, evaluate_gate


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _term(*rows):
    return {"Terminal": list(rows)}


def _rows(step, **ctx):
    return [(r["status"], r["detail"]) for r in _gate(step, **ctx)["checks"]]


STL = "solid Mesh\nfacet normal 0 0 1\nouter loop\nendloop\nendfacet\nendsolid Mesh\n"


# -- 1. "any name will do" only for an app's exports, a file once, never one that was already there ----------------------

def test_a_new_python_file_is_not_the_main_py_beside_it(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n")
    step = {"id": "m2", "title": "A module for the math", "instructions":
            "Create a new Python file for the math helpers next to main.py",
            "checks": [{"id": "c", "type": "file_exists", "label": "Math helpers file created",
                        "file": "operations.py"}]}
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_new_notebook_is_not_another_notebook_already_there(tmp_path):
    (tmp_path / "mnist.ipynb").write_text(json.dumps({"cells": [], "metadata": {}, "nbformat": 4,
                                                      "nbformat_minor": 5}))
    step = {"id": "s1", "instructions": "create a new Jupyter notebook for your experiments",
            "checks": [{"id": "c", "type": "file_exists", "label": "Notebook created", "file": "experiments.ipynb"}]}
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_one_exported_file_satisfies_one_export_check(tmp_path):
    (tmp_path / "Box_Base.stl").write_text(STL)
    step = {"id": "s9", "instructions": "Export both parts as STL files for printing.",
            "checks": [{"id": "a", "type": "file_exists", "label": "Base exported", "file": "base.stl"},
                       {"id": "b", "type": "file_exists", "label": "Lid exported", "file": "lid.stl"}]}
    rows = _rows(step, workdir=str(tmp_path))
    assert rows[0] == ("pass", "Box_Base.stl saved (any name will do)")  # the file named for the base
    assert rows[1][0] == "fail"
    (tmp_path / "Box_Lid.stl").write_text(STL)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_check_prefers_the_file_named_for_it_whatever_the_order(tmp_path):
    (tmp_path / "Box_Base.stl").write_text(STL)
    (tmp_path / "Box_Lid.stl").write_text(STL)
    step = {"id": "s9", "instructions": "Export both parts as STL files for printing.",
            "checks": [{"id": "b", "type": "file_exists", "label": "Lid exported", "file": "lid.stl"},
                       {"id": "a", "type": "file_exists", "label": "Base exported", "file": "base.stl"}]}
    details = [d for _, d in _rows(step, workdir=str(tmp_path))]
    assert details == ["Box_Lid.stl saved (any name will do)", "Box_Base.stl saved (any name will do)"]


def test_a_file_another_check_names_is_not_taken_by_the_fallback(tmp_path):
    (tmp_path / "base.stl").write_text(STL)
    step = {"id": "s9", "instructions": "Export both parts as STL files for printing.",
            "checks": [{"id": "a", "type": "file_exists", "label": "Base exported", "file": "base.stl"},
                       {"id": "b", "type": "file_exists", "label": "Lid exported", "file": "lid.stl"}]}
    assert [s for s, _ in _rows(step, workdir=str(tmp_path))] == ["pass", "fail"]


def test_an_export_saved_before_the_step_began_is_not_this_steps(tmp_path):
    old = tmp_path / "untitled.png"
    old.write_bytes(b"PNG")
    started = time.time()
    os.utime(old, (started - 600, started - 600))
    step = {"id": "s10", "instructions": "Render with F12, then Image > Save As a PNG next to mug.blend.",
            "checks": [{"id": "c", "type": "file_exists", "label": "PNG render saved", "file": "mug.png"}]}
    assert _gate(step, workdir=str(tmp_path))["passed"]  # no start time known: any PNG there
    assert not _gate(step, workdir=str(tmp_path), step_started_at=started)["passed"]
    assert not _gate(step, workdir=str(tmp_path), lesson_started_at=started)["passed"]
    (tmp_path / "render.png").write_bytes(b"PNG")
    assert _gate(step, workdir=str(tmp_path), step_started_at=started)["passed"]


# -- 2. the step's own command, under another runner -------------------------------------------------------------------

PYTEST = {"id": "s4", "targets": [{"app": "Terminal", "match": "pytest"}],
          "checks": [{"id": "c", "type": "screen_contains", "label": "Tests pass", "app": "Terminal",
                      "pattern": r"\d+\s+passed"}]}


@pytest.mark.parametrize("cmd", ["python3 -m pytest", "python -m pytest -q", "pytest"])
def test_python_dash_m_runs_the_module(cmd):
    screen = _term(f"me@mac calc % {cmd}", "...", "3 passed in 0.02s", "me@mac calc % ")
    assert _gate(PYTEST, screen=screen)["passed"]


def test_a_test_target_still_needs_a_test_run():
    screen = _term("me@mac calc % python3 main.py", "3 passed to the printer", "me@mac calc % ")
    assert not _gate(PYTEST, screen=screen)["passed"]


DEV = {"id": "s1", "targets": [{"app": "Terminal", "match": "npm run dev"}],
       "checks": [{"id": "c", "type": "screen_contains", "label": "Dev server running", "app": "Terminal",
                   "pattern": r"localhost:\d+"}]}


@pytest.mark.parametrize("cmd", ["npx vite", "yarn dev", "pnpm dev", "bun run dev", "npm run dev"])
def test_another_js_runner_runs_the_dev_script(cmd):
    screen = _term(f"me@mac app % {cmd}", "  VITE v5.4.0  ready in 300 ms", "  ➜  Local:   http://localhost:5173/")
    assert _gate(DEV, screen=screen, running=True)["passed"]


def test_another_script_or_an_install_is_not_the_dev_server():
    for cmd in ("npm run build", "npm install"):
        screen = _term(f"me@mac app % {cmd}", "see http://localhost:5173/ for docs", "me@mac app % ")
        assert not _gate(DEV, screen=screen)["passed"], cmd


def test_runner_equivalence():
    assert blocks.runs("python3 -m pytest", "pytest") and blocks.runs("pytest -q", "python -m pytest")
    assert blocks.runs("npx vite", "npm run dev") and blocks.runs("yarn dev", "npm run dev")
    assert blocks.runs("npm t", "npm test")
    assert not blocks.runs("npm run build", "npm run dev") and not blocks.runs("yarn add vite", "npm run dev")
    assert not blocks.runs("git branch x", "git checkout -b x")
    assert blocks.is_command("python -m http.server")


# -- 3. a NaN from an earlier run is not the newest run's -------------------------------------------------------------

ACC = {"id": "s5", "run_command": "python3 train.py",
       "checks": [{"id": "c", "type": "metric_threshold", "label": "Accuracy reaches 0.95", "app": "Terminal",
                   "metric": "accuracy", "metric_pattern": r"accuracy:\s*(?P<value>\d+\.\d+)", "op": ">=",
                   "value": 0.95}]}


def test_a_nan_in_an_earlier_run_does_not_fail_a_finished_rerun():
    screen = _term("me@mac m % python3 train.py", "Epoch 1/1", "1875/1875 - accuracy: 0.9561 - loss: nan",
                   "me@mac m % python3 train.py", "Epoch 1/1", "1875/1875 - accuracy: 0.9702 - loss: 0.10",
                   "me@mac m % ")
    assert _gate(ACC, screen=screen, exit_code=0, command="python3 train.py")["passed"]


def test_a_nan_in_an_earlier_run_without_prompts_does_not_fail_the_rerun():
    out = ["Epoch 1/2", "accuracy: 0.9561 - loss: 0.2", "Epoch 2/2", "accuracy: 0.9563 - loss: nan",
           "Epoch 1/2", "accuracy: 0.9601 - loss: 0.2", "Epoch 2/2", "accuracy: 0.9702 - loss: 0.1"]
    assert _gate(ACC, screen={"Terminal": out}, exit_code=0)["passed"]


def test_a_nan_in_the_newest_run_still_fails():
    screen = _term("me@mac m % python3 train.py", "Epoch 1/1", "1875/1875 - accuracy: 0.9702 - loss: 0.10",
                   "me@mac m % python3 train.py", "Epoch 1/1", "1875/1875 - accuracy: 0.9563 - loss: nan",
                   "me@mac m % ")
    g = _gate(ACC, screen=screen, exit_code=0, command="python3 train.py")
    assert not g["passed"] and "loss: nan" in g["checks"][0]["detail"]


# -- 4. an earlier run's line while the newest run is still live: pending ------------------------------------------------

BUILT = {"id": "s6", "targets": [{"app": "Terminal", "match": "npm run build"}],
         "checks": [{"id": "c", "type": "screen_contains", "label": "Build finished", "app": "Terminal",
                     "pattern": r"built in \d+"}]}
TWO_BUILDS = ["me@mac app % npm run build", "✓ built in 812ms", "me@mac app % npm run build", "vite v5.4.0 building"]


def test_an_earlier_runs_line_is_pending_while_the_newest_run_is_live():
    row = _gate(BUILT, screen=_term(*TWO_BUILDS), running=True)["checks"][0]
    assert row["status"] == "pending"


def test_an_earlier_runs_line_fails_once_the_newest_run_is_over():
    row = _gate(BUILT, screen=_term(*TWO_BUILDS, "error during build", "me@mac app % "), exit_code=1)["checks"][0]
    assert row["status"] == "fail" and "earlier" in row["detail"]


# -- 5. float rounding only in model / data dumps -----------------------------------------------------------------------

def test_a_code_value_is_not_rounded(tmp_path):
    (tmp_path / "train.py").write_text("LEARNING_RATE = 0.0010004\n")
    step = {"id": "s3", "instructions": "Set the learning rate to 0.001 in train.py.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Learning rate 0.001", "file": "train.py",
                        "pattern": r"LEARNING_RATE\s*=\s*0\.001\b"}]}
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    (tmp_path / "train.py").write_text("LEARNING_RATE = 0.001\n")
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_dump_value_is_still_rounded(tmp_path):
    (tmp_path / "params.json").write_text(json.dumps({"learning_rate": 0.0010000000474974513}))
    step = {"id": "s3", "instructions": "Save the learning rate.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Learning rate 0.001", "file": "params.json",
                        "pattern": r"\"learning_rate\":\s*0\.001\b"}]}
    assert _gate(step, workdir=str(tmp_path))["passed"]
