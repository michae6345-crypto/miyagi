"""Desktop test 9 (Nov 15 06:12-06:19, "Watch a video": Kie Codes' TensorFlow MNIST video, 7 generated steps): the step
checks of a generated video lesson were graded wrongly. The lesson is the cached build the test used
(fixtures/t9_lesson_5c0ea8a4.json = demo/cache/lessons/5c0ea8a49f419487.json). No model call anywhere.

  V1  the checks ran at step start before the screen reader resumed: "screen reading is off: can't see Terminal" and the
      screen_absent "No terminal errors" PASSED ("screen reading is off, so nothing to flag"), then stayed green.

Run from the repo root:  python -m pytest server/tests/test_t9_checks.py -q"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from server.checks.evaluator import RunContext, evaluate_gate, evaluate_step

FIXTURE = Path(__file__).parent / "fixtures" / "t9_lesson_5c0ea8a4.json"


def lesson() -> dict:
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))


def step(sid: str) -> dict:
    return next(s for s in lesson()["steps"] if s["id"] == sid)


def by_id(results: list[dict]) -> dict[str, dict]:
    return {r["checkId"]: r for r in results}


# ------------------------------------------------------------------ V1: no real look, no verdict
def test_v1_no_frame_yet_leaves_every_screen_check_pending():
    s1 = step("s1")
    for seg in (None, True, False):
        res = by_id(evaluate_step(s1, RunContext(segment_done=seg)))  # screen None: the reader isn't live yet
        assert {r["status"] for r in res.values()} == {"pending"}, res
        assert res["s1c3"]["status"] == "pending"  # "No terminal errors" never passes on nothing
        assert not any("screen reading is off" in r["detail"] for r in res.values())
    # the first real frame grades them: the terminal shows no error yet, the command hasn't printed anything
    res = by_id(evaluate_step(s1, RunContext(screen={"Terminal": ["tripi@mac lesson % "]})))
    assert res["s1c1"]["status"] == "fail" and res["s1c3"]["status"] == "pass"


def test_v1_session_step_start_before_the_reader_resumes(tmp_path, monkeypatch):
    """The real session: step.started's first evaluation runs while the FakeScreen has no frame (lines() -> None)."""
    from server.orchestrator.modules import Modules
    from server.orchestrator.screen_bridge import FakeScreen
    from server.orchestrator.tests.test_session import Rig

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    screen = FakeScreen()  # no text: no frame yet
    rig = Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,coach,finder,diagrams"), screen=screen)

    async def go():
        await rig.s.load_graph(lesson())
        await rig.settle()
        first = {p["checkId"]: p for p in rig.of("check.updated") if p["stepId"] == "s1"}
        assert first["s1c3"]["status"] == "pending", first
        assert not any("screen reading is off" in (p.get("detail") or "") for p in rig.of("check.updated"))
        # the reader is live: a Terminal frame with an error in it fails the row (it was never latched green)
        screen.text["Terminal"] = ["$ pip3 install jupyter", "ERROR: Could not find a version"]
        await rig.s.evaluate("screen")
        await rig.settle()
        rows = [p for p in rig.of("check.updated") if p["checkId"] == "s1c3"]
        assert all(p["status"] != "pass" for p in rows), rows

    asyncio.run(go())


# ------------------------------------------------------------------ V2: the code the learner wrote survives clipping / wrap
CELL1 = ["import tensorflow as tf\n", "from tensorflow.keras import layers, models\n", "import matplotlib.pyplot as plt\n",
         "import numpy as np\n", "\n",
         "(train_images, train_labels), (test_images, test_labels) = tf.keras.datasets.mnist.load_data()\n",
         "train_images = train_images.astype('float32') / 255\n", "test_images = test_images.astype('float32') / 255"]
CELL2 = ["print('Number of images in the training dataset:', train_images.shape[0])\n",
         "print('Number of images in the testing dataset:', test_images.shape[0])\n",
         "print('Shape of the images in the training dataset:', train_images[0].shape)\n", "\n",
         "fig, axes = plt.subplots(1, 10, figsize=(10, 10))\n", "for i in range(10):\n",
         "    axes[i].imshow(train_images[i].reshape(28, 28), cmap='gray')\n", "plt.show()"]
PRINTED = ["Number of images in the training dataset: 60000\n", "Number of images in the testing dataset: 10000\n",
           "Shape of the images in the training dataset: (28, 28)\n"]


def notebook(folder: Path, cells: list[tuple[list[str], list[dict]]], name: str = "mnist.ipynb") -> Path:
    """The learner's notebook as VS Code saves it (test 9: mnist.ipynb, not the video's Untitled.ipynb)."""
    nb = {"cells": [{"cell_type": "code", "execution_count": (i + 1) if outs else None, "metadata": {},
                     "outputs": outs, "source": src} for i, (src, outs) in enumerate(cells)],
          "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    p = folder / name
    p.write_text(json.dumps(nb), encoding="utf-8")
    return p


def stream(lines: list[str]) -> dict:
    return {"output_type": "stream", "name": "stdout", "text": lines}


def test_v2_wrapped_line_still_matches_on_screen():
    s2 = step("s2")
    # word wrap in the narrow editor: "…datasets.mnist." / "load_data()" (test 9 06:17, frames)
    wrapped = {"Code": ["(train_images, train_labels), (test_images, test_labels) = tf.keras.datasets.mnist.",
                        "load_data()", "train_images = train_images.astype('float32') / 255"]}
    res = by_id(evaluate_step(s2, RunContext(screen=wrapped)))
    assert res["s2c2"]["status"] == "pass", res["s2c2"]
    # OCR also splits a token mid-word or puts a space after the dot
    for rows in (["tf.keras.datasets.mnist.load_da", "ta()"], ["tf.keras.datasets.mnist. load_data()"]):
        assert by_id(evaluate_step(s2, RunContext(screen={"Code": rows})))["s2c2"]["status"] == "pass", rows


def test_v2_clipped_line_passes_on_the_notebook_cells(tmp_path):
    s2 = step("s2")
    notebook(tmp_path, [(CELL1, [])])
    clipped = {"Code": ["(train_images, train_labels), (test_images, test_labels) = tf.keras.datasets.mnist.load_d"]}
    res = by_id(evaluate_step(s2, RunContext(workdir=str(tmp_path), screen=clipped)))
    assert res["s2c2"] == {**res["s2c2"], "status": "pass", "detail": "typed in mnist.ipynb"}
    assert res["s2c1"]["status"] == "pass" and res["s2c3"]["status"] == "pass"
    # not in the notebook and not on screen: still a fail
    notebook(tmp_path, [(CELL1[:4], [])])
    res = by_id(evaluate_step(s2, RunContext(workdir=str(tmp_path), screen=clipped)))
    assert res["s2c2"]["status"] == "fail"


# ------------------------------------------------------------------ V3: an output check is graded on output, never the code
SOURCE_ON_SCREEN = {"Code": [
    "print('Number of images in the training dataset:', train_images.shape[0])",
    "print('Number of images in the testing dataset:', test_images.shape[0])",
    "print('Shape of the images in the training dataset:', train_images[0].shape)",
    "fig, axes = plt.subplots(1, 10, figsize=(10, 10))"]}


def test_v3_source_line_never_passes_an_output_check(tmp_path):
    s3 = step("s3")
    for ctx in (RunContext(screen=SOURCE_ON_SCREEN),  # no notebook found
                RunContext(workdir=str(tmp_path), screen=SOURCE_ON_SCREEN)):
        res = by_id(evaluate_step(s3, ctx))
        assert res["s3c4"]["status"] != "pass", res["s3c4"]  # test 9's false pass: "Image shape line printed"
        assert res["s3c1"]["status"] == "pass"  # "subplots call typed" is a code check: the code passes it
    notebook(tmp_path, [(CELL1, []), (CELL2, [])])  # cells typed, not run: nothing printed
    res = by_id(evaluate_step(s3, RunContext(workdir=str(tmp_path), screen=SOURCE_ON_SCREEN)))
    assert [res[c]["status"] for c in ("s3c1", "s3c2", "s3c3", "s3c4")] == ["pass", "fail", "fail", "fail"]
    assert res["s3c4"]["detail"] == "not printed yet: run the cell"


def test_v3_cell_outputs_in_the_notebook_pass_output_checks(tmp_path):
    s3 = step("s3")
    notebook(tmp_path, [(CELL1, [stream(["Downloading data from https://storage.googleapis.com/...\n"])]),
                        (CELL2, [stream(PRINTED), {"output_type": "display_data", "data": {
                            "image/png": "iVBOR...", "text/plain": ["<Figure size 1000x1000 with 10 Axes>"]}}])])
    res = by_id(evaluate_step(s3, RunContext(workdir=str(tmp_path), screen={"Code": ["fig, axes = plt.subplots(1, 10"]})))
    assert {c: r["status"] for c, r in res.items()} == {"s3c1": "pass", "s3c2": "pass", "s3c3": "pass", "s3c4": "pass"}
    assert res["s3c4"]["detail"] == "printed in mnist.ipynb"


def test_v3_output_on_screen_counts_the_code_does_not():
    s7 = step("s7")
    code = ["test_loss, test_accuracy = model.evaluate(test_images, test_labels)",
            "print(f'Accuracy of the neural network on the {test_images.shape[0]} test images: {test_accuracy * 100:.2f}%')"]
    assert by_id(evaluate_step(s7, RunContext(screen={"Code": code})))["s7c2"]["status"] != "pass"
    out = code + ["313/313 [==============================] - 1s 2ms/step - loss: 0.0815 - accuracy: 0.9764",
                  "Accuracy of the neural network on the 10000 test images: 97.64%"]
    res = by_id(evaluate_step(s7, RunContext(screen={"Code": out})))
    assert res["s7c2"]["status"] == "pass" and res["s7c3"]["status"] == "pass" and res["s7c1"]["status"] == "pass"
    # the plot's own title (OCR of the figure) is output; set_title('Class Probability') is code
    s6 = step("s6")
    src = ["    ax2.set_title('Class Probability')"]
    assert by_id(evaluate_step(s6, RunContext(screen={"Code": src})))["s6c3"]["status"] != "pass"
    assert by_id(evaluate_step(s6, RunContext(screen={"Code": src + ["Class Probability"]})))["s6c3"]["status"] == "pass"


def test_v3_a_cell_error_in_the_notebook_fails_the_absent_check(tmp_path):
    s2 = step("s2")
    err = {"output_type": "error", "ename": "ModuleNotFoundError", "evalue": "No module named 'tensorflow'",
           "traceback": ["\x1b[0;31m---------------------------------------------------------------------------\x1b[0m",
                         "\x1b[0;31mModuleNotFoundError\x1b[0m: No module named 'tensorflow'"]}
    notebook(tmp_path, [(CELL1, [err])])
    res = by_id(evaluate_step(s2, RunContext(workdir=str(tmp_path), screen={"Code": ["import tensorflow as tf"]})))
    assert res["s2c4"]["status"] == "fail" and "ModuleNotFoundError" in res["s2c4"]["detail"]


def test_v3_notebook_lessons_autosave(tmp_path):
    """Learners never press ⌘S, and a notebook's outputs reach the file only when it is saved: a notebook lesson's
    folder turns on files.autoSave (a value already there wins)."""
    from server.workspace import core

    assert core.ensure_notebook_autosave(tmp_path) is True
    st = json.loads((tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert st["files.autoSave"] == "afterDelay"
    (tmp_path / ".vscode" / "settings.json").write_text(json.dumps({"files.autoSave": "off", "x": 1}), encoding="utf-8")
    core.ensure_notebook_autosave(tmp_path)
    assert json.loads((tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8")) == {"files.autoSave": "off", "x": 1}


def test_v3_only_printed_results_are_output_checks():
    """2b236a5 read s4c4 "Softmax output layer added" (a code check) as output-only: s4 could never pass."""
    from server.checks.evaluator import is_output_check

    out = {c["id"] for s in lesson()["steps"] for c in s.get("checks") or [] if is_output_check(c)}
    assert out == {"s3c2", "s3c3", "s3c4", "s6c3", "s6c4", "s7c2", "s7c3"}, out
    s4 = step("s4")
    code = {"Code": ["model = models.Sequential([", "    layers.Flatten(input_shape=(28, 28, 1)),",
                     "    layers.Dense(128, activation='relu'),", "    layers.Dense(10, activation='softmax')", "])"]}
    res = by_id(evaluate_step(s4, RunContext(screen=code)))
    assert res["s4c4"]["status"] == "pass" and evaluate_gate(s4, RunContext(screen=code))["passed"]
    assert not is_output_check({"type": "screen_contains", "label": "Output layer uses softmax", "pattern": "softmax"})
    assert not is_output_check({"type": "screen_contains", "label": "Loss printed", "pattern": r"print\(loss\)"})
    assert is_output_check({"type": "screen_contains", "label": "Loss printed", "pattern": r"loss:\s*0\.\d+"})
    assert is_output_check({"type": "screen_contains", "label": "Cell output shown", "pattern": r"60000"})
    assert is_output_check({"type": "screen_contains", "label": "x", "pattern": r"model\.fit\(", "output": True})
