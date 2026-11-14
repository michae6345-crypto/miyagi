"""Claude step judge: offline tests only (mocked client; cost freeze)."""

from __future__ import annotations

import asyncio

import pytest

from server import coach
from server.coach import common, llm
from server.coach.judge import JUDGE_SYSTEM, StepJudge, screen_text

LESSON = {"lesson": {"id": "calc", "title": "Build a calculator in Python", "goal": "calculator"}, "sources": [],
          "steps": [{"id": "s1", "title": "Install Python and VS Code", "instructions": "Install Python 3 and open VS Code.",
                     "checks": [{"id": "c1", "type": "visual", "label": "VS Code open"}]},
                    {"id": "s2", "title": "Create calc.py", "instructions": "Create calc.py in your project folder.",
                     "checks": [{"id": "c2", "type": "file_exists", "label": "calc.py exists", "file": "calc.py"}]},
                    {"id": "s3", "title": "Write add and subtract", "instructions": "Define add(a, b) and subtract(a, b).",
                     "checks": [{"id": "c3", "type": "file_contains", "label": "add() defined", "file": "calc.py", "pattern": r"def add\("}]}]}
S1, S2, S3 = LESSON["steps"]
SCREEN = {"Code": ["calc.py — calculator", "1 def add(a, b):", "2     return a + b", "3 def subtract(a, b):", "4     return a - b"],
          "Terminal": ["$ python --version", "Python 3.12.4"]}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv("COACH_REPLAY_DIR", raising=False)
    common.set_lesson(LESSON)
    yield
    common.set_lesson(None)


def run(coro):
    return asyncio.run(coro)


def fake(monkeypatch, data, seen=None):
    async def call(**kw):
        if seen is not None:
            seen.update(kw)
        return llm.CallResult(data=data, model=kw["model"], usage={"input_tokens": 900, "output_tokens": 60}, latency_s=0.8)

    monkeypatch.setattr(llm, "structured_call", call)


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_gate():
    clock = Clock()
    j = StepJudge(clock=clock)
    pending = [{"checkId": "c1", "status": "pending"}]
    assert not j.should_judge(S1, pending, idle_s=3, video_playing=False, screen=SCREEN)  # learner busy
    assert not j.should_judge(S1, pending, idle_s=30, video_playing=True, screen=SCREEN)  # video playing
    assert not j.should_judge(S1, [{"checkId": "c1", "status": "pass"}], idle_s=30, video_playing=False, screen=SCREEN)
    assert j.should_judge(S1, pending, idle_s=9, video_playing=False, screen=SCREEN)
    j._last_t["s1"], j._last_sig["s1"] = clock.t, "x"
    clock.t += 10
    assert not j.should_judge(S1, pending, idle_s=30, video_playing=False, screen=SCREEN)  # < 20 s since the last one
    clock.t += 15
    assert j.should_judge(S1, pending, idle_s=30, video_playing=False, screen=SCREEN)


def test_unchanged_screen_is_not_judged_again(monkeypatch):
    clock = Clock()
    j = StepJudge(clock=clock)
    fake(monkeypatch, {"checks": [], "on_step_id": "", "summary": ""})
    pending = [{"checkId": "c1", "status": "pending"}]
    run(j.judge(S1, pending, screen=SCREEN))
    clock.t += 60
    assert not j.should_judge(S1, pending, idle_s=30, video_playing=False, screen=SCREEN)
    assert j.should_judge(S1, pending, idle_s=30, video_playing=False, screen=SCREEN | {"Terminal": ["$ ls", "calc.py"]})
    assert j.should_judge(S1, pending, idle_s=30, video_playing=False, screen=SCREEN, files={"calc.py": "x = 1"})


def test_setup_step_passes_when_the_tool_is_open(monkeypatch):
    seen = {}
    fake(monkeypatch, {"checks": [{"check_id": "c1", "verdict": "done", "confidence": 0.93, "reason": "VS Code window is open",
                                   "evidence": "calc.py — calculator (Code)"}], "on_step_id": "", "summary": "VS Code open with calc.py"}, seen)
    r = run(StepJudge().judge(S1, [{"checkId": "c1", "status": "pending"}], screen=SCREEN, focused_app="Code"))
    assert r["events"] == [{"type": "check.updated", "payload": {
        "stepId": "s1", "checkId": "c1", "label": "VS Code open", "status": "pass",
        "detail": "Claude saw it on screen: calc.py — calculator (Code)"}}]
    assert r["card"] is None and r["_meta"]["usage"]["input_tokens"] == 900
    assert seen["model"] == "claude-haiku-5-5" and seen["purpose"] == "judge"
    assert "Setup / install steps" in JUDGE_SYSTEM and "visibly open or installed" in JUDGE_SYSTEM
    u = seen["user_text"]
    assert "Install Python and VS Code" in u and "- c1: VS Code open [pending]" in u and "APP: Code (focused)" in u and "Python 3.12.4" in u


def test_low_confidence_or_cant_tell_does_nothing(monkeypatch):
    fake(monkeypatch, {"checks": [{"check_id": "c1", "verdict": "done", "confidence": 0.55, "reason": "r", "evidence": "e"},
                                  {"check_id": "zz", "verdict": "done", "confidence": 1.0, "reason": "unknown id", "evidence": "e"}],
                       "on_step_id": "", "summary": ""})
    r = run(StepJudge().judge(S1, [{"checkId": "c1", "status": "pending"}], screen=SCREEN))
    assert r["events"] == [] and r["card"] is None and [v["check_id"] for v in r["checks"]] == ["c1"]


def test_done_but_a_deterministic_check_disagrees_asks(monkeypatch):
    fake(monkeypatch, {"checks": [{"check_id": "c2", "verdict": "done", "confidence": 0.9, "reason": "file open in editor",
                                   "evidence": "calc.py — calculator"}], "on_step_id": "", "summary": "calc.py is open in VS Code"})
    r = run(StepJudge().judge(S2, [{"checkId": "c2", "status": "fail", "detail": "calc.py not found in workdir"}], screen=SCREEN))
    assert r["events"] == []  # never overrule a machine check
    assert r["card"] == {"stepId": "s2", "kind": "answer", "title": "Looks done?", "body": "calc.py is open in VS Code",
                         "actions": ["confirm", "skip_step"], "checkIds": ["c2"]}
    assert len(r["card"]["body"].split()) <= 12


def test_learner_already_on_a_later_step(monkeypatch):
    fake(monkeypatch, {"checks": [{"check_id": "c1", "verdict": "cant_tell", "confidence": 0.3, "reason": "r", "evidence": ""}],
                       "on_step_id": "s3", "summary": "writing add() and subtract() in calc.py"})
    r = run(StepJudge().judge(S1, [{"checkId": "c1", "status": "pending"}], screen=SCREEN))
    assert r["card"]["title"] == "Already ahead?" and r["card"]["actions"] == ["skip_step"] and r["card"]["targetStepId"] == "s3"
    assert "Write add and subtract" in r["card"]["body"] and len(r["card"]["body"].split()) <= 12
    # an earlier step on screen → no card
    fake(monkeypatch, {"checks": [], "on_step_id": "s1", "summary": ""})
    assert run(StepJudge().judge(S3, [{"checkId": "c3", "status": "pending"}], screen=SCREEN))["card"] is None


def test_files_and_screen_inputs(monkeypatch):
    seen = {}
    fake(monkeypatch, {"checks": [], "on_step_id": "", "summary": ""}, seen)
    from server.coach.tests.screen_case import make_screen

    run(StepJudge().judge(S3, [], screen=make_screen(), files={"calc.py": "def add(a, b):\n    return a + b\n"}))
    assert "APP: Terminal (focused)" in seen["user_text"] and "FILE calc.py:\ndef add(a, b):" in seen["user_text"]
    assert screen_text("plain text") == "plain text" and screen_text(None) == ""


def test_judge_never_raises(monkeypatch):
    async def down(**kw):
        raise llm.CoachLLMError("x", "connection")

    monkeypatch.setattr(llm, "structured_call", down)
    assert run(StepJudge().judge(S1, [{"checkId": "c1", "status": "pending"}], screen=SCREEN)) is None


def test_exported():
    assert coach.StepJudge is StepJudge and llm.model_for("judge") == "claude-haiku-5-5"


# ---------- the Check button + reading the editor state (Michael: VS Code on Untitled-1) ----------------

from types import SimpleNamespace

from PIL import Image

from server.coach.pointing import editor_state, where_hint
from server.coach.screen import Box, ScreenContext

CALC = {"id": "k2", "title": "Create the calculator file", "instructions": "Create a new file and save it as calculator.py in the lesson folder.",
        "checks": [{"id": "k2a", "type": "visual", "label": "calculator.py saved"}]}


def _vscode_untitled() -> ScreenContext:
    boxes = [Box(0, "Untitled-1 — Visual Studio Code", 300, 8, 260, 14, source="ax", app="Code", role="AXTitle"),
             Box(0, "def add(a, b):", 60, 80, 120, 13, app="Code"), Box(0, "return a + b", 80, 95, 100, 13, app="Code")]
    return ScreenContext(image=Image.new("RGB", (10, 10)), cursor=(100, 90), boxes=boxes, scale=1.0, app="Code").numbered()


def test_where_reads_the_editor_state():
    assert where_hint(CALC, None, _vscode_untitled()) == "You're in VS Code on an unsaved file. Save it as calculator.py in the lesson folder"
    obs = SimpleNamespace(app="Code", windows=[SimpleNamespace(app="Code", title="● calc.py — calculator")],
                          lines_by_app=lambda: {"Code": ["def add(a, b):"]})
    assert editor_state(obs) == {"app": "VS Code", "file": "calc.py", "untitled": "", "unsaved": True}
    assert where_hint(CALC, None, obs) == "You're in VS Code on calc.py. Open calculator.py from the lesson folder"
    no_editor = {"Terminal": ["$ ls"]}
    assert where_hint(CALC, None, no_editor) == "Create calculator.py in the lesson folder"  # a creation step, file named only in the instructions


def test_hint_and_point_use_the_editor_state(monkeypatch):
    h = coach.hint(CALC, 0, {}, screen=_vscode_untitled())
    assert h["where"].startswith("You're in VS Code on an unsaved file") and h["title"] == "Open your code first"

    async def call(**kw):
        return llm.CallResult(data={"box_ids": [], "where": "Open the lesson file in your editor, such as VS Code, first"}, model="h")

    monkeypatch.setattr(llm, "structured_call", call)
    p = run(coach.point(CALC, _vscode_untitled(), about="the calculator file"))
    assert p["where"] == "You're in VS Code on an unsaved file. Save it as calculator.py in the lesson folder"


def test_judge_step_not_done_says_what_and_where(monkeypatch):
    seen = {}
    fake(monkeypatch, {"checks": [{"check_id": "k2a", "verdict": "not_done", "confidence": 0.9, "reason": "file is still Untitled-1",
                                   "evidence": "Untitled-1 — Visual Studio Code"}],
                       "on_step_id": "", "summary": "code typed in an unsaved tab", "missing": "Save the Untitled-1 tab as calculator.py"}, seen)
    r = run(coach.judge_step(CALC, _vscode_untitled()))
    assert r["done"] is False and r["missing"] == "Save the Untitled-1 tab as calculator.py"
    assert r["checks"] == {"k2a": {"verdict": "not_done", "reason": "file is still Untitled-1", "evidence": "Untitled-1 — Visual Studio Code"}}
    assert r["where"] == "You're in VS Code on an unsaved file. Save it as calculator.py in the lesson folder"
    assert "EDITOR ON SCREEN: VS Code showing an unsaved Untitled-1" in seen["user_text"] and "EXPECTED FILE: calculator.py" in seen["user_text"]


def test_judge_step_done_points_at_the_evidence(monkeypatch):
    fake(monkeypatch, {"checks": [{"check_id": "c3", "verdict": "done", "confidence": 0.9, "reason": "add is defined", "evidence": "def add(a, b):"}],
                       "on_step_id": "", "summary": "add() defined", "missing": ""})
    r = run(coach.judge_step(S3, _vscode_untitled(), check_results=[{"checkId": "c3", "status": "pending"}]))
    assert r["done"] is True and r["missing"] == "" and r["where"] is None
    assert r["target"]["text"] == "def add(a, b):" and set(r["target"]["rect"]) == {"x", "y", "w", "h"}


def test_judge_step_unsure_and_machine_pass(monkeypatch):
    fake(monkeypatch, {"checks": [{"check_id": "c3", "verdict": "done", "confidence": 0.4, "reason": "maybe", "evidence": ""}],
                       "on_step_id": "", "summary": "", "missing": "add() not visible"})
    r = run(coach.judge_step(S3, SCREEN))
    assert r["checks"]["c3"]["verdict"] == "unsure" and r["done"] is False and r["missing"] == "add() not visible"
    r = run(coach.judge_step(S3, SCREEN, check_results=[{"checkId": "c3", "status": "pass"}]))
    assert r["done"] is True  # the machine already passed it


def test_judge_step_ignores_gates_and_never_raises(monkeypatch):
    async def down(**kw):
        raise llm.CoachLLMError("x", "connection")

    monkeypatch.setattr(llm, "structured_call", down)
    assert run(coach.judge_step(S1, SCREEN)) is None


# ---------- S1 actions QA: the hint ladder must not read canned ------------------------------------------

NB_STEP = {"id": "n1", "title": "Import the libraries", "instructions": "In the first cell, import numpy, pandas and matplotlib.",
           "video": {"sourceId": "yt", "start": 44, "end": 90},
           "explanations": [{"topic": "Linear model f(x) = wx + b", "t": 44, "sourceId": "yt"}],
           "checks": [{"id": "n1a", "type": "file_contains", "label": "numpy imported", "file": "lesson.ipynb", "pattern": "import numpy"}],
           "hints": ["In the first cell, import numpy as np, pandas as pd, and matplotlib.pyplot as plt."]}


def test_three_presses_give_three_different_rungs():
    common.set_lesson({"lesson": {}, "sources": [], "steps": [NB_STEP]})
    ladder = [coach.hint(NB_STEP, i, {}) for i in range(3)]
    assert [h["level"] for h in ladder] == [0, 1, 2]  # level 2 is no longer skipped without a paper
    assert len({h["title"] for h in ladder}) == 3 and all("Import the libraries" in h["title"] for h in ladder)
    q = ladder[0]["body"]
    assert q.endswith("?") and "lesson.ipynb" in q and not q.startswith("In the first cell")  # a question, not the instruction
    assert ladder[1]["body"] == "Rewatch 0:44, where the tutorial shows linear model f(x) = wx + b."
    assert ladder[1]["videoJump"] == {"t": 44.0, "label": "Rewatch 0:44"}
    assert ladder[2]["title"].startswith("Key idea") and ladder[2]["body"] == NB_STEP["hints"][0]
    assert coach.hint(NB_STEP, 3, {})["title"].startswith("Compare with the tutorial · ")


def test_level0_questions_by_check_type():
    for check, want in [
        ({"id": "a", "type": "file_exists", "label": "calc.py exists", "file": "calc.py"}, "Is calc.py in your lesson folder yet"),
        ({"id": "b", "type": "command_exit_ok", "label": "runs", "command": "npm test"}, "What happens when you run `npm test`"),
        ({"id": "c", "type": "metric_threshold", "label": "loss < 1e-2", "metric": "loss"}, "Is loss heading toward “loss < 1e-2”"),
        ({"id": "d", "type": "visual", "label": "chart shows two lines"}, "What would you point at on screen to show “chart shows two lines”"),
    ]:
        h = coach.hint({"id": "x", "title": "T", "checks": [check]}, 0, {})
        assert h["body"].startswith(want) and h["body"].endswith("?")



# ---------- Michael's live calculator screenshot: a step not started yet ------------------------------------

CALC1 = {"id": "q1", "title": "Create calculator.py", "instructions": "Create a new file named calculator.py and print a welcome message with print().",
         "checks": [{"id": "q1a", "type": "file_exists", "label": "calculator.py created", "file": "calculator.py"}],
         "hints": ["How do you display text on screen and ask the user for input in Python?"]}


def test_not_started_is_a_plain_instruction_not_an_offtrack(monkeypatch):
    async def boom(**kw):
        raise AssertionError("no model for a step that hasn't started")

    monkeypatch.setattr(llm, "structured_call", boom)
    card = run(coach.diagnose(CALC1, [{"checkId": "q1a", "label": "calculator.py created", "status": "fail"}], None, ""))
    assert card["notStarted"] is True and card["title"] == "Start: Create calculator.py"
    assert card["body"] == "Create calculator.py in the lesson folder, then print a welcome message with print()."
    assert not card["body"].endswith("?")


def test_hint_after_a_not_started_card_is_the_instruction():
    nudge = {"stepId": "q1", "title": "Not yet: calculator.py created", "body": "How do you display text…?", "_meta": {"route": "template"}}
    h = coach.hint(CALC1, 0, nudge)  # the live bug: "Not yet: calculator.py created: what in your code makes that happen…"
    assert h["title"] == "Start · Create calculator.py"
    assert h["body"] == "Create calculator.py in the lesson folder, then print a welcome message with print()."
    h = coach.hint(CALC1, 0, nudge, screen=_vscode_untitled())  # reads the screen: the unsaved tab
    assert h["body"] == "You're in VS Code on an unsaved file. Save it as calculator.py in the lesson folder, then print a welcome message with print()."
    assert "Not yet:" not in coach.hint(CALC1, 1, nudge)["body"]
