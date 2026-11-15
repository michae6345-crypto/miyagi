"""Desktop test 10 (video lesson, mnist.ipynb in VS Code): the coach's "Not yet" contradicted its own checks (s5 "Add
history = model.fit(...)" with "model.fit called" Passed, mid-training and after; s6 "view_classify cell not written
yet" with "view_classify defined" Passed), Check my work mid-training diagnosed a half run, a press 1.7 s into s7 got
an instant Not yet for the NEW step, video Not yet cards carried only Skip step, s2's deterministic AttributeError card
took ~13 s through Claude, and its Hint restated the diagnosis. Fixture: the run's real mnist.ipynb (read only copy).
No model calls: Modules(force_stubs="all"); the judge / diagnose are stubbed per test."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from server.coach import hints
from server.orchestrator import nb_coach, stubs
from server.orchestrator.tests.test_session import rig  # noqa: F401 (fixture)

NB = Path(__file__).parent / "fixtures" / "t10_mnist.ipynb"

S5_CHECKS = [
    {"id": "s5c1", "type": "screen_contains", "label": "model.compile called", "pattern": r"model\.compile\("},
    {"id": "s5c2", "type": "screen_contains", "label": "model.fit called", "pattern": r"model\.fit\("},
    {"id": "s5c3", "type": "metric_threshold", "label": "Training accuracy reaches 0.95", "metric": "accuracy"},
]
S6_CHECKS = [
    {"id": "s6c1", "type": "screen_contains", "label": "view_classify defined", "pattern": r"def\s+view_classify\("},
    {"id": "s6c2", "type": "screen_contains", "label": "model.predict called", "pattern": r"model\.predict\("},
    {"id": "s6c3", "type": "screen_contains", "label": "Class Probability title shown", "pattern": r"Class\s*Probability"},
]


def run(coro):
    return asyncio.run(coro)


def _cells(nb: dict, n: int) -> dict:
    return nb["cells"][n]


def _with_running_training(dst: Path) -> None:
    """The fixture with cell 3 (compile + fit) mid-run: epoch 3 of 5, its progress bar part way."""
    nb = json.loads(NB.read_text())
    c = next(c for c in nb["cells"] if "model.fit" in "".join(c.get("source") or []))
    c["outputs"] = [{"output_type": "stream", "name": "stdout", "text": [
        "Epoch 1/5\n", "\x1b[1m1875/1875\x1b[0m \x1b[32m━━━━━━━━━━━━━━━━━━━━\x1b[0m 2s 1ms/step - accuracy: 0.87\n",
        "Epoch 2/5\n", "\x1b[1m1875/1875\x1b[0m ━━━━━━━━━━━━━━━━━━━━ 2s 1ms/step - accuracy: 0.96\n",
        "Epoch 3/5\n", "\x1b[1m 412/1875\x1b[0m ━━━━\x1b[37m━━━━━━━━━━━━━━━━\x1b[0m 1s 1ms/step - accuracy: 0.97"]}]
    c["execution_count"] = None
    dst.write_text(json.dumps(nb))


# ------------------------------------------------------------------ pure helpers
def test_render_reads_the_whole_notebook_with_output_tails():
    text = nb_coach.render(nb_coach.cells(NB))
    assert "def view_classify(" in text and "model.predict(" in text and "model.evaluate(" in text
    assert "# [output] 1875/1875" in text and "accuracy: 0.9858" in text  # ANSI stripped, last lines only
    assert "\x1b[" not in text
    short = nb_coach.render(nb_coach.cells(NB), limit=600)
    assert len(short) <= 600 and "model.evaluate(" in short  # a cut keeps the END (the step's cell)


def test_running_reads_the_progress_bar(tmp_path):
    p = tmp_path / "mnist.ipynb"
    _with_running_training(p)
    assert nb_coach.running_in(nb_coach.cells(p))
    assert not nb_coach.running_in(nb_coach.cells(NB))  # the run finished: 5/5, 1875/1875


def test_guard_spots_s5_and_s6_contradictions_only():
    rows5 = [{"checkId": "s5c1", "status": "pass"}, {"checkId": "s5c2", "status": "pass"},
             {"checkId": "s5c3", "status": "pending"}]
    s5 = {"id": "s5", "checks": S5_CHECKS}
    assert nb_coach.contradicts("Add history = model.fit(train_images, train_labels, epochs=5) then Run the cell "
                                "(Shift+Enter).", s5, rows5) == ["model.fit called"]
    s6 = {"id": "s6", "checks": S6_CHECKS}
    rows6 = [{"checkId": "s6c1", "status": "pass"}, {"checkId": "s6c2", "status": "pass"},
             {"checkId": "s6c3", "status": "fail"}]
    assert nb_coach.contradicts("view_classify cell not written yet · The notebook ends at the model.compile cell, so "
                                "view_classify and model.predict have not been defined or run", s6, rows6)
    # the check failing: a real "missing" diagnosis stands
    rows_fail = [{"checkId": "s5c2", "status": "fail"}]
    assert not nb_coach.contradicts("Add history = model.fit(train_images, train_labels, epochs=5)", s5, rows_fail)
    # a typo diagnosis about other code stands
    assert not nb_coach.contradicts("load_dat is missing the a", s5, rows5)


def test_traceback_cards_are_instant_and_specific():
    s2 = {"id": "s2", "code": "(train_images, train_labels), (test_images, test_labels) = "
                              "tf.keras.datasets.mnist.load_data()\n"}
    mine = "(train_images, train_labels), (test_images, test_labels) = tf.keras.datasets.mnist.load_dat()\n"
    err = ("AttributeError                            Traceback (most recent call last)\nCell In[1], line 6\n"
           "AttributeError: module 'keras.datasets.mnist' has no attribute 'load_dat'")
    c = nb_coach.traceback_card(s2, err, mine, notebook=True)
    assert c["title"] == "load_dat is missing the a"
    assert "load_data()" in c["body"] and "run the cell again" in c["body"]
    assert c["actions"] == ["explain", "show_me", "hint"] and c["severity"] == "fail"
    assert c["diff"]["expected"].endswith("load_data()") and c["diff"]["yours"].endswith("load_dat()")

    s4 = {"id": "s4", "code": "model = models.Sequential([layers.Flatten()])\n"}
    c = nb_coach.traceback_card(s4, "NameError: name 'modles' is not defined", "model = modles.Sequential([])")
    assert c["title"] == "modles should be models" and "Change it to models" in c["body"]
    c = nb_coach.traceback_card({"id": "s5", "code": "model.fit(train_images, train_labels)"},
                                "NameError: name 'model' is not defined", "model = models.Sequential([])\n"
                                "model.fit(train_images, train_labels)", notebook=True)
    assert "hasn't run" in c["body"] and "Run All" in c["body"]
    c = nb_coach.traceback_card({"id": "s3"}, '  Cell In[3], line 2\n    print("x"\n           ^\n'
                                "SyntaxError: '(' was never closed", 'print("x"', notebook=True)
    assert c["title"] == "Syntax error on line 2"
    # no near-match: Claude diagnoses it
    assert nb_coach.traceback_card(s2, "AttributeError: module 'np' has no attribute 'zzz'", "np.zzz()") is None


def test_hint_nudges_without_restating_the_diagnosis():
    step = {"id": "s2", "title": "Import libraries and load MNIST", "code": "x = 1\n", "checks": []}
    last = {"title": "load_dat is missing the a", "body": "The error says keras.datasets.mnist has no attribute "
            "load_dat, so the name is misspelled and the cell crashes. Change it to load_data() and run the cell again."}
    card = hints._hint(step, 0, last)
    assert "load_dat" not in card["body"] and "missing the a" not in card["body"]
    assert card["body"].endswith("?") or "Compare" in card["body"]


# ------------------------------------------------------------------ the session
def _gate(rows: list[dict]):
    def gate(step, ctx, screen=None, precision_mode=False):
        return {"passed": False, "via": None, "checks": [dict(r) for r in rows], "precision": []}
    return gate


async def _start(rig, monkeypatch, checks: list[dict], rows: list[dict], code: str = "") -> dict:  # noqa: F811
    graph = stubs.load_fixture_lesson()
    for s in graph["steps"]:
        s["file"] = "Untitled.ipynb"  # the video's name: the learner's notebook is mnist.ipynb (find_notebook)
        for t in s.get("targets") or []:
            t["file"] = "Untitled.ipynb"
    s1 = graph["steps"][0]
    s1["checks"], s1["code"], s1["precision_checks"] = checks, code, []
    monkeypatch.setattr(rig.s.m, "evaluate_gate", _gate(rows))
    await rig.s.load_graph(graph)
    await rig.settle()
    rig.s.workdir = str(rig.workdir)
    await rig.end_segment()
    return s1


def _judge(calls: list, verdict: dict):
    async def judge_step(step, screen=None, files=None, **kw):
        calls.append({"files": files})
        return verdict
    return judge_step


def test_check_my_work_never_asks_for_code_whose_check_passed(rig, monkeypatch):  # noqa: F811
    """CP12: training finished (accuracy 0.9858 in the notebook), the metric row still pending, the judge said "Add
    history = model.fit(…)" -> the card says the code is in and what to wait for; Explain / Show me / Hint on it; the
    judge read the notebook's cells (mnist.ipynb, with view_classify / evaluate), not the screen."""
    shutil.copy(NB, rig.workdir / "mnist.ipynb")
    os.utime(rig.workdir / "mnist.ipynb", (time.time() - 120, time.time() - 120))
    rows = [{"checkId": "s5c1", "label": "model.compile called", "status": "pass", "detail": "typed in mnist.ipynb"},
            {"checkId": "s5c2", "label": "model.fit called", "status": "pass", "detail": "typed in mnist.ipynb"},
            {"checkId": "s5c3", "label": "Training accuracy reaches 0.95", "status": "pending",
             "detail": "waiting for the run's accuracy"}]
    calls: list = []

    async def go():
        await _start(rig, monkeypatch, S5_CHECKS, rows)
        monkeypatch.setattr(rig.s.m, "judge_step", _judge(calls, {"done": False, "missing": (
            "Add history = model.fit(train_images, train_labels, epochs=5) then Run the cell (Shift+Enter).")}))
        rig.clock.t += 30
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        cards = [e["payload"] for e in rig.since(m) if e["type"] == "card"]
        assert cards, rig.since(m)
        c = cards[-1]
        assert "Add history" not in c["body"] and "model.fit" not in c["body"], c
        assert "0.9858" in c["body"] and c["title"] == "Your code is in"
        assert c["actions"] == ["hint", "show_me", "skip_step"]
        assert not calls  # only the run's output row waits: no screenshot + Haiku judge (~4 s)
        _, files, _ = rig.s._judge_inputs(rig.s.step)  # the judge reads the notebook's cells, not the screen
        assert "def view_classify(" in files["mnist.ipynb"] and "# [output]" in files["mnist.ipynb"]

    run(go())


def test_check_my_work_guard_rebuilds_from_the_failing_code_row(rig, monkeypatch):  # noqa: F811
    """A code row still fails (compile) and the judge asks for model.fit, whose row Passed: the card names only what
    is left, never model.fit."""
    shutil.copy(NB, rig.workdir / "mnist.ipynb")
    rows = [{"checkId": "s5c1", "label": "model.compile called", "status": "fail"},
            {"checkId": "s5c2", "label": "model.fit called", "status": "pass"},
            {"checkId": "s5c3", "label": "Training accuracy reaches 0.95", "status": "pending"}]
    calls: list = []

    async def go():
        await _start(rig, monkeypatch, S5_CHECKS, rows)
        monkeypatch.setattr(rig.s.m, "judge_step", _judge(calls, {"done": False, "missing": (
            "Add history = model.fit(train_images, train_labels, epochs=5) then Run the cell (Shift+Enter).")}))
        rig.clock.t += 30
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        c = [e["payload"] for e in rig.since(m) if e["type"] == "card"][-1]
        assert calls and "model.fit" not in c["body"] and "model.compile called" in c["body"], c

    run(go())


def test_still_to_do_lists_only_rows_the_drawer_shows():
    """CP15: "Still to do: …; evaluate saved in notebook; …" named a hidden precision row."""
    from types import SimpleNamespace

    from server.orchestrator import advice_clear

    sent: list = []

    async def emit(t, p):
        sent.append(p)

    async def emit_card(card, window_s=0.0):
        sent.append(card)
        return True

    step = {"id": "s7", "checks": []}
    s = SimpleNamespace(step=step, step_gen=1, passed=False, _run_command=lambda st: "", emit=emit,
                        _emit_card=emit_card, last_offtrack=None,
                        last_results=[{"checkId": "s7c1", "label": "Accuracy summary printed", "status": "pass"},
                                      {"checkId": "s7c2", "label": "Test accuracy at least 95", "status": "fail"}],
                        last_failed=[{"checkId": "s7c2", "label": "Test accuracy at least 95", "status": "fail"},
                                     {"checkId": "s7p1", "label": "evaluate saved in notebook", "status": "fail"}])
    s._advice_up = {"gen": 1, "what": "card", "checks": {"s7c1": {}, "s7c2": {}, "s7p1": {}},
                    "card": {"stepId": "s7", "kind": "answer", "title": "Not yet", "body": "x", "actions": ["hint"]}}
    s._card_in_use = None
    run(advice_clear.checks_moved(s))
    bodies = " ".join(str(c.get("body") or "") for c in sent)
    assert "Test accuracy at least 95" in bodies and "evaluate saved in notebook" not in bodies


def test_check_my_work_mid_training_says_wait(rig, monkeypatch):  # noqa: F811
    """CP11: Check my work while the training cell runs -> "Training is still running", no judge call."""
    _with_running_training(rig.workdir / "mnist.ipynb")
    rows = [{"checkId": "s5c1", "label": "model.compile called", "status": "pass"},
            {"checkId": "s5c2", "label": "model.fit called", "status": "pass"},
            {"checkId": "s5c3", "label": "Training accuracy reaches 0.95", "status": "pending"}]
    calls: list = []

    async def go():
        await _start(rig, monkeypatch, S5_CHECKS, rows, code="history = model.fit(train_images, train_labels, epochs=5)")
        monkeypatch.setattr(rig.s.m, "judge_step", _judge(calls, {"done": False, "missing": "Add model.fit"}))
        rig.clock.t += 30
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        cards = [e["payload"] for e in rig.since(m) if e["type"] == "card"]
        assert cards and cards[-1]["title"] == "Still running" and "Training is still running" in cards[-1]["body"]
        assert not calls

    run(go())


def test_check_pressed_right_after_a_step_starts_is_for_the_step_before(rig, monkeypatch):  # noqa: F811
    """CP15: s6 passed, s7 started, the press aimed at s6 landed 1.7 s into s7 -> "Step 6 done", never a Not yet for s7;
    a press later is judged as usual."""
    rows = [{"checkId": "s5c2", "label": "model.fit called", "status": "fail"}]
    calls: list = []

    async def go():
        await _start(rig, monkeypatch, S5_CHECKS, rows)
        monkeypatch.setattr(rig.s.m, "judge_step", _judge(calls, {"done": False, "missing": "Add model.fit"}))
        rig.clock.t += 30
        await rig.s._pass_step()
        await rig.settle()
        assert rig.s.idx == 1 and not rig.s.passed
        rig.clock.t += 1.0
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        cards = [e["payload"] for e in rig.since(m) if e["type"] == "card"]
        assert cards and cards[-1]["title"] == "Step 1 done" and not any(c["title"] == "Not yet" for c in cards)
        assert not calls
        rig.clock.t += 10
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        assert calls  # judged

    run(go())


def test_coach_drops_a_diagnosis_that_contradicts_passed_checks(rig, monkeypatch):  # noqa: F811
    """CP14: diagnose says "view_classify cell not written yet" with view_classify / model.predict Passed -> no
    off-track goes out."""
    shutil.copy(NB, rig.workdir / "mnist.ipynb")
    rows = [{"checkId": "s6c1", "label": "view_classify defined", "status": "pass"},
            {"checkId": "s6c2", "label": "model.predict called", "status": "pass"},
            {"checkId": "s6c3", "label": "Class Probability title shown", "status": "fail"}]
    seen: dict = {}

    async def diagnose(step, failed, metrics, code, **kw):
        seen["code"] = code
        return {"stepId": step["id"], "severity": "warn", "title": "view_classify cell not written yet",
                "body": "The notebook ends at the model.compile cell, so view_classify and model.predict have not been "
                        "defined or run."}

    async def go():
        await _start(rig, monkeypatch, S6_CHECKS, rows)
        monkeypatch.setattr(rig.s.m, "diagnose", diagnose)
        rig.s.last_results = rows
        m = rig.mark()
        await rig.s._coach(rig.s.step_gen, rig.s.step, [rows[2]], rig.s.context(), 2)
        await rig.settle()
        assert "def view_classify(" in seen["code"]  # the notebook, not the screen
        assert not [e for e in rig.since(m) if e["type"] == "offtrack"]

    run(go())


def test_coach_builds_the_attribute_error_card_without_a_model_call(rig, monkeypatch):  # noqa: F811
    """CP5: the s2 AttributeError -> "load_dat is missing the a" from the notebook's error output, no diagnose call."""
    nb = json.loads(NB.read_text())
    c0 = nb["cells"][0]
    c0["source"] = "".join(c0["source"]).replace("load_data()", "load_dat()")
    c0["outputs"] = [{"output_type": "error", "ename": "AttributeError",
                      "evalue": "module 'keras.datasets.mnist' has no attribute 'load_dat'",
                      "traceback": ["\x1b[0;31mAttributeError\x1b[0m Traceback", "Cell In[1], line 6"]}]
    (rig.workdir / "mnist.ipynb").write_text(json.dumps(nb))
    rows = [{"checkId": "s2c4", "label": "No import or load errors", "status": "fail",
             "detail": "the cell printed 'AttributeError'"}]
    called: list = []

    async def diagnose(*a, **kw):
        called.append(1)
        return {"title": "x", "body": "y"}

    async def go():
        await _start(rig, monkeypatch, [{"id": "s2c4", "type": "screen_absent", "label": "No import or load errors",
                                         "pattern": "Traceback|AttributeError"}], rows,
                     code="(train_images, train_labels), (test_images, test_labels) = tf.keras.datasets.mnist.load_data()")
        monkeypatch.setattr(rig.s.m, "diagnose", diagnose)
        rig.s.last_results = rows
        m = rig.mark()
        await rig.s._coach(rig.s.step_gen, rig.s.step, rows, rig.s.context(), 2)
        await rig.settle()
        offs = [e["payload"] for e in rig.since(m) if e["type"] == "offtrack"]
        assert offs and offs[-1]["title"] == "load_dat is missing the a" and not called
        assert set(offs[-1]["actions"]) >= {"explain", "show_me", "hint"}

    run(go())
