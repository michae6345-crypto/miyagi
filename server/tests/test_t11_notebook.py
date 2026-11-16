"""Test 11 (Nov 15) regressions, offline: the notebook kernel check (s1 "Notebook kernel is .venv"), the lesson's
notebook left as Miyagi's untouched template (the learner made Untitled.ipynb), a Terminal check while the run is live,
and the misspelling hint found in the code before any run. Run from the repo root:
    python -m pytest server/tests/test_t11_notebook.py -q"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

from server.checks.evaluator import RunContext, evaluate_check, evaluate_step
from server.checks.notebook import find_notebook, read_notebook
from server.coach.hints import nudge_question
from server.lesson.notebook_steps import KERNEL_LABEL, KERNEL_PATTERN, empty_notebook, use_lesson_notebook


def write_nb(path: Path, cells: list[str], ran: bool = False, kernel: str | None = None,
             version: str | None = None, mtime: float | None = None) -> Path:
    nb = empty_notebook()
    if cells:
        nb["cells"] = [{"cell_type": "code", "execution_count": 1 if ran else None, "id": f"c{i}", "metadata": {},
                        "outputs": [{"output_type": "stream", "name": "stdout", "text": ["ok\n"]}] if ran else [],
                        "source": [src]} for i, src in enumerate(cells)]
    if kernel is not None:
        nb["metadata"]["kernelspec"]["display_name"] = kernel
    if version is not None:
        nb["metadata"]["language_info"]["version"] = version
    path.write_text(json.dumps(nb), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# ---------------------------------------------------------------------- 2. the kernel check

@pytest.mark.parametrize("shown", [".venv (3.12.16)", ".venv (Python 3.12.16)", "Python 3.12.16 ('.venv': venv)"])
def test_kernel_pattern_reads_both_vscode_forms(shown):
    assert re.search(KERNEL_PATTERN, f"mnist.ipynb  {shown}  Run All  Outline")


@pytest.mark.parametrize("shown", [".venv", "Select Kernel", "Python 3.12.16", "venv (base)"])
def test_kernel_pattern_never_reads_a_bare_venv_or_another_kernel(shown):
    assert not re.search(KERNEL_PATTERN, f"EXPLORER  {shown}  mnist.ipynb")


def s1_step() -> dict:
    return {"id": "s1", "title": "Open mnist.ipynb with the .venv kernel", "file": "mnist.ipynb",
            "targets": [{"app": "Code", "file": "mnist.ipynb"}],
            "checks": [{"id": "s1c2", "type": "screen_contains", "label": KERNEL_LABEL, "pattern": KERNEL_PATTERN}]}


def test_kernel_check_passes_on_the_kernel_vscode_saved_without_any_screen(tmp_path):
    write_nb(tmp_path / "mnist.ipynb", [], kernel=".venv (3.12.16)", version="3.12.16")
    [r] = evaluate_step(s1_step(), RunContext(workdir=str(tmp_path), screen=None))
    assert r["status"] == "pass" and r["detail"] == "kernel .venv (3.12.16) in mnist.ipynb"


def test_kernel_check_on_miyagis_template_still_reads_the_screen(tmp_path):
    write_nb(tmp_path / "mnist.ipynb", [])  # display_name ".venv", no language_info.version: no kernel connected yet
    [r] = evaluate_step(s1_step(), RunContext(workdir=str(tmp_path), screen={"Code": ["mnist.ipynb", "Select Kernel"]}))
    assert r["status"] != "pass"
    [r] = evaluate_step(s1_step(), RunContext(workdir=str(tmp_path),
                                              screen={"Code": ["mnist.ipynb", "Run All", ".venv (3.12.16)"]}))
    assert r["status"] == "pass"  # VS Code 1.146's label, OCR'd


def test_kernel_check_on_another_saved_kernel_is_not_passed_by_the_file(tmp_path):
    write_nb(tmp_path / "mnist.ipynb", [], kernel="Python 3.13.1", version="3.13.1")
    [r] = evaluate_step(s1_step(), RunContext(workdir=str(tmp_path), screen={"Code": ["mnist.ipynb", "Python 3.13.1"]}))
    assert r["status"] != "pass"


def test_a_cached_lesson_gets_the_new_kernel_pattern():
    graph = {"lesson": {"title": "MNIST in a Jupyter notebook", "notebook": "mnist.ipynb"},
             "steps": [{**s1_step(), "checks": [{"id": "s1c2", "type": "screen_contains", "label": KERNEL_LABEL,
                                                  "pattern": r"\.?venv\s*\(\s*Python\s*3"}]},
                       {"id": "s2", "file": "mnist.ipynb", "code": "import tensorflow as tf",
                        "instructions": "Run the cell (Shift+Enter) in your notebook"}]}
    use_lesson_notebook(graph)
    assert graph["steps"][0]["checks"][0]["pattern"] == KERNEL_PATTERN
    assert use_lesson_notebook(graph) == []  # idempotent


# ---------------------------------------------------------------------- 3. the untouched template and Untitled.ipynb

def test_untouched_template_gives_way_to_the_learners_own_notebook(tmp_path):
    t = time.time()
    named = write_nb(tmp_path / "mnist.ipynb", [], mtime=t - 60)
    mine = write_nb(tmp_path / "Untitled.ipynb", ["import tensorflow as tf\nmnist.load_dat()"], mtime=t)
    assert find_notebook(tmp_path, ["mnist.ipynb"]) == mine
    assert "load_dat" in read_notebook(find_notebook(tmp_path, ["mnist.ipynb"])).source_text
    assert named.is_file()


def test_named_notebook_with_code_is_kept(tmp_path):
    t = time.time()
    named = write_nb(tmp_path / "mnist.ipynb", ["import tensorflow as tf"], mtime=t - 60)
    write_nb(tmp_path / "Untitled.ipynb", ["print(1)"], mtime=t)
    assert find_notebook(tmp_path, ["mnist.ipynb"]) == named


def test_template_is_kept_when_the_other_notebook_is_older_or_empty(tmp_path):
    t = time.time()
    named = write_nb(tmp_path / "mnist.ipynb", [], mtime=t)
    write_nb(tmp_path / "old.ipynb", ["print(1)"], mtime=t - 600)  # older than the template: an earlier lesson's
    write_nb(tmp_path / "Untitled.ipynb", [], mtime=t + 5)  # newer, but nothing typed in it
    assert find_notebook(tmp_path, ["mnist.ipynb"]) == named


def test_a_step_check_reads_untitled_when_mnist_is_the_template(tmp_path):
    t = time.time()
    write_nb(tmp_path / "mnist.ipynb", [], mtime=t - 60)
    write_nb(tmp_path / "Untitled.ipynb", ["import tensorflow as tf"], mtime=t)
    step = {"id": "s2", "file": "mnist.ipynb", "code": "import tensorflow as tf",
            "checks": [{"id": "s2c1", "type": "screen_contains", "app": "Code", "label": "TensorFlow imported",
                        "pattern": r"import\s+tensorflow\s+as\s+tf"}]}
    [r] = evaluate_step(step, RunContext(workdir=str(tmp_path), screen=None))
    assert r["status"] == "pass" and r["detail"] == "typed in Untitled.ipynb"


# ---------------------------------------------------------------------- 4. a Terminal check while the run is live

def test_terminal_check_stays_pending_while_the_run_is_live():
    check = {"id": "c1", "type": "screen_contains", "app": "Terminal", "label": "Server started",
             "pattern": r"Serving Flask app"}
    screen = {"Terminal": ["$ python app.py", " * Debug mode: on"]}
    r = evaluate_check(check, RunContext(running=True, command="python app.py", screen=screen))
    assert r["status"] == "pending"
    r = evaluate_check(check, RunContext(running=False, exit_code=0, command="python app.py", screen=screen))
    assert r["status"] == "fail"  # the run ended without printing it


# ---------------------------------------------------------------------- 6. the misspelling hint before any run

def test_misspelling_found_in_the_code_before_a_run_never_says_read_the_error():
    card = {"title": "load_dat() should be load_data()",
            "body": "The call ends in mnist.load_dat(), which is not a TensorFlow function, so the mnist.load_data() "
                    "check fails."}
    q = nudge_question(card)
    assert q == "Compare the highlighted line with the step's code, letter by letter: one name is spelled differently."
    assert "error" not in q.lower() and "—" not in q


def test_misspelling_with_an_error_output_keeps_read_the_error():
    card = {"title": "load_dat should be load_data",
            "body": "AttributeError: module 'keras.datasets.mnist' has no attribute 'load_dat'."}
    assert nudge_question(card).startswith("Read the last line of the error")
