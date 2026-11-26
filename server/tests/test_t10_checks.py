"""Desktop test 10 (Nov 15 07:33-07:39, "Watch a video": Kie Codes' TensorFlow MNIST video, Jupyter notebook in VS Code):
step checks of the generated video lesson graded the learner's notebook wrongly. The lesson is the cached build the test
used (demo/cache/lessons/5c0ea8a49f419487.json); the notebook is the learner's real mnist.ipynb from the run
(fixtures/t10_mnist.ipynb, Keras progress output with its ANSI codes and the two matplotlib PNGs). Earlier moments of
the run are the first N cells of it. No model call anywhere.

  1  BLOCKER s5 "Training accuracy reaches 0.95" never passed: the metric path read the screen and the terminal, never
     the notebook cell that printed `accuracy: 0.9858` (as ANSI-coloured Keras lines).
  2  s6 "Class Probability title shown" passed only once the plot PNG was scrolled into view (the title is in the image).
  3  output checks read the whole notebook: s6 "predict progress printed" passed on the training cell's "ms/step",
     s7 "evaluate progress output shown" on the training progress bars.
  4  vacuous passes: s1 "confirmed by your files" (Miyagi's own .venv) / "Already installed"; "No X errors · not showing
     on screen" before the step's cell ran.

Run from the repo root:  python -m pytest server/tests/test_t10_checks.py -q"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from server.checks.evaluator import RunContext, evaluate_gate, evaluate_step
from server.checks.notebook import read_notebook

ROOT = Path(__file__).resolve().parents[2]
LESSON = json.loads((ROOT / "demo" / "cache" / "lessons" / "5c0ea8a49f419487.json").read_text(encoding="utf-8"))
NOTEBOOK = json.loads((Path(__file__).parent / "fixtures" / "t10_mnist.ipynb").read_text(encoding="utf-8"))
PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY",
             "TIGER_DATABASE_URL")
# the editor scrolled to the top of the notebook (CP14: the screen showed the compile cell, not the plot)
TOP = {"Code": ["model.compile(optimizer='adam',", "loss='sparse_categorical_crossentropy',", "metrics=['accuracy'])"]}


@pytest.fixture(autouse=True)
def _free(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path_factory.mktemp("miyagi-state")))
    for k in PAID_KEYS:  # an accidental live call fails at once, for free
        monkeypatch.setenv(k, "")


def step(sid: str) -> dict:
    return copy.deepcopy(next(s for s in LESSON["steps"] if s["id"] == sid))


def notebook(folder: Path, cells: int, edit=None) -> Path:
    """The learner's mnist.ipynb as it was with its first `cells` cells (edit(cells) may change them)."""
    nb = copy.deepcopy(NOTEBOOK)
    nb["cells"] = nb["cells"][:cells]
    if edit:
        edit(nb["cells"])
    p = folder / "mnist.ipynb"
    p.write_text(json.dumps(nb), encoding="utf-8")
    return p


def checks(sid: str, folder: Path, screen=TOP) -> dict[str, dict]:
    return {r["checkId"]: r for r in evaluate_step(step(sid), RunContext(workdir=str(folder), screen=screen))}


# ------------------------------------------------------------------ 1  the s5 blocker
def test_1_training_accuracy_passes_on_the_notebook_keras_output(tmp_path):
    notebook(tmp_path, 4)  # CP12: training done, 5 epochs in the notebook, nothing about it on screen
    out = read_notebook(tmp_path / "mnist.ipynb").cells[3].outputs[0]
    assert "\x1b" not in out and "accuracy: 0.9858" in out  # the saved stream has ANSI codes; the checks never see them
    res = checks("s5", tmp_path)
    assert res["s5c3"]["status"] == "pass", res["s5c3"]
    assert res["s5c3"]["detail"] == "accuracy 0.9858 >= 0.95 in mnist.ipynb"  # the last epoch, as Keras printed it
    assert evaluate_gate(step("s5"), RunContext(workdir=str(tmp_path), screen=TOP))["passed"]
    # a run that missed the target doesn't pass
    def low(cells):
        cells[3]["outputs"][0]["text"] = [t.replace("accuracy: 0.9", "accuracy: 0.8") for t in cells[3]["outputs"][0]["text"]]
    notebook(tmp_path, 4, low)
    assert checks("s5", tmp_path)["s5c3"]["status"] != "pass"
    # the training cell typed, not run: still waiting
    notebook(tmp_path, 4, lambda cells: cells[3].update(outputs=[], execution_count=None))
    assert checks("s5", tmp_path)["s5c3"]["status"] == "pending"


def test_1_keras_progress_redrawn_with_backspaces_reads_line_by_line():
    from server.checks.notebook import clean_output

    raw = ("Epoch 1/5\n\x1b[1m 100/1875\x1b[0m - accuracy: 0.7012\x08\x08\x08\x08\x1b[1m1875/1875\x1b[0m"
           " - accuracy: 0.9310 - loss: 0.2344\r\n")
    assert clean_output(raw).splitlines() == ["Epoch 1/5", " 100/1875 - accuracy: 0.7012",
                                              "1875/1875 - accuracy: 0.9310 - loss: 0.2344"]


def test_1_test_accuracy_metric_reads_the_evaluate_cell(tmp_path):
    notebook(tmp_path, 6)
    assert checks("s7", tmp_path)["s7c4"]["status"] == "pass"


# ------------------------------------------------------------------ 2  a title that exists only in the plot
def test_2_title_in_the_plot_passes_once_the_cell_ran_with_an_image(tmp_path):
    notebook(tmp_path, 5)  # CP14: s6's cell ran, the PNG is below the fold, the editor shows the compile cell
    res = checks("s6", tmp_path)
    assert res["s6c3"] == {**res["s6c3"], "status": "pass", "detail": "plotted in mnist.ipynb"}
    # not run yet: no figure, no pass (whatever its source says)
    notebook(tmp_path, 5, lambda cells: cells[4].update(outputs=[], execution_count=None))
    assert checks("s6", tmp_path)["s6c3"]["status"] != "pass"
    # it ran into an error: no figure was drawn
    err = {"output_type": "error", "ename": "NameError", "evalue": "name 'np' is not defined", "traceback": []}
    notebook(tmp_path, 5, lambda cells: cells[4].update(outputs=[err]))
    assert checks("s6", tmp_path)["s6c3"]["status"] != "pass"


def test_2_ocr_of_the_plot_still_passes_it(tmp_path):
    # a title the source doesn't spell out (a variable): OCR of the figure, once on screen, is the second way
    def var_title(cells):
        cells[4]["source"] = [ln.replace("ax2.set_title('Class Probability')", "ax2.set_title(TITLE)")
                              for ln in cells[4]["source"]]
    notebook(tmp_path, 5, var_title)
    assert checks("s6", tmp_path)["s6c3"]["status"] != "pass"
    res = checks("s6", tmp_path, screen={"Code": ["ax2.set_title(TITLE)", "Class Probability"]})
    assert res["s6c3"]["status"] == "pass", res["s6c3"]


# ------------------------------------------------------------------ 3  only the step's own cell's output counts
def test_3_predict_progress_never_passes_on_the_training_cell(tmp_path):
    notebook(tmp_path, 4)  # CP13: s6 just started, no s6 code anywhere; the training cell printed "556us/step"
    training = {"Code": ["1875/1875 ━━━━━━━━━━━━━━━━━━━━ 1s 556us/step - accuracy: 0.9310 - loss: 0.2344"]}
    for screen in (TOP, training):
        res = checks("s6", tmp_path, screen)
        assert res["s6c4"]["status"] != "pass", res["s6c4"]
    notebook(tmp_path, 5)  # s6's cell ran: its own "1/1 ... 23ms/step"
    assert checks("s6", tmp_path)["s6c4"] == {**checks("s6", tmp_path)["s6c4"], "status": "pass",
                                              "detail": "printed in mnist.ipynb"}


def test_3_evaluate_progress_never_passes_on_earlier_progress_bars(tmp_path):
    notebook(tmp_path, 5)  # CP15: s7 just started; training and predict printed "accuracy: 0.9…" progress bars
    training = {"Code": ["1875/1875 ━━━━━━━━━━━━━━━━━━━━ 1s 593us/step - accuracy: 0.9858 - loss: 0.0433"]}
    for screen in (TOP, training):
        res = checks("s7", tmp_path, screen)
        assert res["s7c3"]["status"] != "pass", res["s7c3"]
        assert res["s7c2"]["status"] != "pass"
    notebook(tmp_path, 6)
    res = checks("s7", tmp_path)
    assert res["s7c3"]["status"] == "pass" and res["s7c2"]["status"] == "pass"


def test_3_step_cells_are_found_by_the_steps_code(tmp_path):
    from server.checks.evaluator import step_cells

    nb = read_notebook(notebook(tmp_path, 6))
    assert {sid: step_cells(nb, step(sid)) for sid in ("s2", "s3", "s4", "s5", "s6", "s7")} == {
        "s2": [0], "s3": [1], "s4": [2], "s5": [3], "s6": [4], "s7": [5]}


# ------------------------------------------------------------------ 4  no verdict before the learner did anything
def test_4_no_errors_check_waits_for_the_steps_cell(tmp_path):
    notebook(tmp_path, 4)  # CP13: "No predict errors · not showing on screen" passed before any s6 code
    res = checks("s6", tmp_path)
    assert res["s6c5"] == {**res["s6c5"], "status": "pending", "detail": "checked when the cell runs"}
    notebook(tmp_path, 5)
    assert checks("s6", tmp_path)["s6c5"]["status"] == "pass"
    # CP7: s2's corrected cell written with its outputs cleared, NOT run: the step must not pass on typed code alone
    notebook(tmp_path, 1, lambda cells: cells[0].update(outputs=[], execution_count=None))
    s2 = {"Code": ["import tensorflow as tf", "(train_images, train_labels), (test_images, test_labels) = "
                   "tf.keras.datasets.mnist.load_data()", "train_images = train_images.astype('float32') / 255"]}
    res = checks("s2", tmp_path, s2)
    assert res["s2c4"]["status"] == "pending" and res["s2c5"]["status"] == "pending", res
    assert not evaluate_gate(step("s2"), RunContext(workdir=str(tmp_path), screen=s2))["passed"]
    notebook(tmp_path, 1)
    assert evaluate_gate(step("s2"), RunContext(workdir=str(tmp_path), screen=s2))["passed"]


def lesson_s1(tmp_path) -> dict:
    from server.lesson.venv_steps import use_lesson_venv

    g = copy.deepcopy(LESSON)
    use_lesson_venv(g)
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "activate").write_text("# Miyagi's own .venv\n", encoding="utf-8")
    return g


def test_4_s1_never_passes_on_miyagis_own_venv(tmp_path):
    s1 = lesson_s1(tmp_path)["steps"][0]
    assert not any(".venv" in str(c.get("file") or "") for c in s1.get("precision_checks") or [])
    gate = evaluate_gate(s1, RunContext(workdir=str(tmp_path), screen=TOP), precision_mode=True)
    assert not gate["passed"], gate  # was: via "precision", shown as "confirmed by your files"
    # the terminal isn't on screen: "No terminal errors" waits for the command, never "nothing to flag"
    res = {r["checkId"]: r for r in gate["checks"]}
    assert res["s1c3"] == {**res["s1c3"], "status": "pending", "detail": "checked when it runs"}


def test_4_s1_never_passes_as_already_installed(tmp_path, monkeypatch):
    from server.orchestrator.tests.test_session import Rig

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    rig = Rig(tmp_path)

    async def go():
        await rig.s.load_graph(copy.deepcopy(LESSON))
        await rig.settle()
        rig.s.reqs = [{"tool": t, "label": t.capitalize(), "kind": "library", "needed": True, "ok": True}
                      for t in ("jupyter", "tensorflow", "numpy", "matplotlib")]
        await rig.s._maybe_pass_setup_step()
        await rig.settle()

    asyncio.run(go())
    assert not rig.of("step.passed"), rig.of("step.passed")
    assert not any(p.get("detail") == "Already installed" for p in rig.of("check.updated"))


def test_4_a_pure_install_step_still_passes_as_already_installed():
    from server.orchestrator.session import LessonSession as Session

    assert not Session._runs_more_than_setup({"run_command": "pip install numpy matplotlib"})
    assert not Session._runs_more_than_setup({"run_command": "brew install node && node -v"})
    assert not Session._runs_more_than_setup({"run_command": "source .venv/bin/activate && pip install -r requirements.txt"})
    assert Session._runs_more_than_setup({"run_command": "source .venv/bin/activate && jupyter notebook"})
    assert Session._runs_more_than_setup({"run_command": "npm install && npm run dev"})


# ------------------------------------------------------------------ the clip plays: nothing passes at a step's start
def test_no_row_passes_at_step_start_so_the_clip_is_not_skipped(tmp_path):
    """session.py's "ahead" rule skipped a step's clip when any row passed at step start (s4, s6, s7 started with the
    segment done). With the earlier steps' cells run and nothing of the new step typed, no row of it passes."""
    neutral = {"Code": ["mnist.ipynb"]}
    for sid, before in (("s3", 1), ("s4", 2), ("s5", 3), ("s6", 4), ("s7", 5)):
        notebook(tmp_path, before)
        res = checks(sid, tmp_path, neutral)
        assert not [r for r in res.values() if r["status"] == "pass"], (sid, res)


def test_ahead_rule_ignores_screen_absent_rows():
    import inspect

    from server.orchestrator.session import LessonSession

    src = inspect.getsource(LessonSession)
    assert 'ahead = any(r.get("status") == "pass" and r.get("checkId") not in absent' in src


def test_run_the_cell_step_never_passes_on_typed_code(tmp_path):
    """CP7: s2's corrected cell was written (outputs cleared) and never run; the step passed. A "Run the cell" step
    whose cell hasn't run can't pass, on either list; a row says why when none does."""
    s2 = {"Code": ["import tensorflow as tf", "(train_images, train_labels), (test_images, test_labels) = "
                   "tf.keras.datasets.mnist.load_data()", "train_images = train_images.astype('float32') / 255"]}
    notebook(tmp_path, 1, lambda cells: cells[0].update(outputs=[], execution_count=None))
    st = step("s2")
    st["checks"] = [c for c in st["checks"] if c["type"] != "screen_absent"]  # only code rows: all green
    (tmp_path / "Untitled.ipynb").write_text((tmp_path / "mnist.ipynb").read_text(encoding="utf-8"), encoding="utf-8")  # precision's file too
    gate = evaluate_gate(st, RunContext(workdir=str(tmp_path), screen=s2), precision_mode=True)
    assert not gate["passed"], gate
    assert gate["checks"][-1] == {"checkId": "s2-cell", "label": "Cell run", "status": "pending",
                                  "detail": "run the cell (Shift+Enter)"}
    notebook(tmp_path, 1)
    (tmp_path / "Untitled.ipynb").unlink()
    gate = evaluate_gate(st, RunContext(workdir=str(tmp_path), screen=s2), precision_mode=True)
    assert gate["passed"] and not any(r["checkId"] == "s2-cell" for r in gate["checks"])


# ------------------------------------------------------------------ the learner's notebook, wherever the video named it
def test_notebook_file_checks_read_the_learners_notebook_never_the_tutorials(tmp_path):
    """07:38:48 "Still to do: evaluate saved in notebook": s7p1 read the video's Untitled.ipynb literally. And a
    downloaded presenter notebook in tutorial/ (the finished answers) is never the learner's."""
    notebook(tmp_path, 6)
    res = {r["checkId"]: r for r in evaluate_step(step("s7"), RunContext(workdir=str(tmp_path)), which="precision")}
    assert res["s7p1"]["status"] == "pass" and "mnist.ipynb" in res["s7p1"]["detail"], res["s7p1"]
    (tmp_path / "mnist.ipynb").unlink()
    (tmp_path / "tutorial").mkdir()
    (tmp_path / "tutorial" / "answers.ipynb").write_text(json.dumps(NOTEBOOK), encoding="utf-8")
    from server.checks.notebook import find_notebook

    assert find_notebook(tmp_path, ["Untitled.ipynb"]) is None
    res = {r["checkId"]: r for r in evaluate_step(step("s7"), RunContext(workdir=str(tmp_path)), which="precision")}
    assert res["s7p1"]["status"] == "fail"
    assert checks("s7", tmp_path)["s7c2"]["status"] != "pass"
