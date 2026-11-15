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
    # never reach a paid API from tests: no .env, no keys (the shared .env has real Bright Data keys)
    monkeypatch.setattr(llm, "_load_env", lambda: None)
    for k in ("COACH_REPLAY_DIR", "DEMO", "ORCH_STUBS", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "BRIGHTDATA_API_KEY",
              "BRIGHTDATA_SERP_ZONE", "BRIGHTDATA_UNLOCKER_ZONE", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "TUT_ENV"):
        monkeypatch.delenv(k, raising=False)
    from server.coach.diagnose import LAST, reset_memo

    reset_memo()
    LAST.clear()
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
    assert not j.should_judge(S1, pending, idle_s=30, video_playing=False, screen=None)  # screen reader down
    assert not j.should_judge(S1, pending, idle_s=30, video_playing=False, screen=SCREEN, display_asleep=True)
    assert not j.should_judge(S1, pending, idle_s=30, video_playing=False, screen=SCREEN, screen_ok=False)
    assert j.should_judge(S1, pending, idle_s=9, video_playing=False, screen=SCREEN)
    j.gate.started("s1", screen="x")
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
    r = run(StepJudge().judge(S2, [{"checkId": "c2", "status": "fail", "detail": "calc.py not found in workdir"}], screen=SCREEN,
                              files={"calc.py": "def add(a, b):\n    return a + b\n"}))
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


def _vscode_saved() -> ScreenContext:
    boxes = [Box(0, "calc.py — calculator", 300, 8, 200, 14, source="ax", app="Code", role="AXTitle"),
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
    r = run(coach.judge_step(S3, _vscode_saved(), files={"calc.py": "def add(a, b):\n    return a + b\n"},
                             check_results=[{"checkId": "c3", "status": "pending"}]))
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
        ({"id": "c", "type": "metric_threshold", "label": "loss < 1e-2", "metric": "loss"}, "Is loss heading the right way"),
        ({"id": "d", "type": "visual", "label": "chart shows two lines"}, "What on screen would show that this step is done"),
        ({"id": "e", "type": "output_contains", "label": "add function is written in the"}, "What does the output show"),
    ]:
        h = coach.hint({"id": "x", "title": "T", "checks": [check]}, 0, {})
        assert h["body"].startswith(want) and h["body"].endswith("?")
        assert "“" not in h["body"] or check["type"] in ("file_exists",)  # never quotes a check label



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


def test_hint_after_a_not_started_card_moves_up_a_rung():
    nudge = {"stepId": "q1", "title": "Not yet: calculator.py created", "body": "How do you display text…?", "_meta": {"route": "template"}}
    h = coach.hint(CALC1, 0, nudge)  # the auto card already said "start": Hint gives the full step, never the same line
    assert h["title"] == "Step details · Create calculator.py"
    assert h["body"] == CALC1["instructions"] and "Not yet:" not in h["body"]
    h = coach.hint(CALC1, 0, nudge, screen=_vscode_untitled())  # and says where, from the screen
    assert h["where"] == "You're in VS Code on an unsaved file. Save it as calculator.py in the lesson folder"
    assert "Not yet:" not in coach.hint(CALC1, 1, nudge)["body"]



# ---------- Michael's live misdiagnosis: unsaved, OCR'd `def add(a, b):` in another folder ---------------

OCR_CODE = "def(a, b)\n(function) def add(a: Any, b: Any) -> None"


def _no_model(monkeypatch):
    async def boom(**kw):
        raise AssertionError("a held diagnosis must not call a model")

    monkeypatch.setattr(llm, "structured_call", boom)


def test_unsaved_file_only_asks_to_save(monkeypatch):
    _no_model(monkeypatch)
    failed = [{"checkId": "c3", "label": "add() defined", "status": "fail"}]
    card = run(coach.diagnose(S3, failed, None, OCR_CODE, file_state={"path": "calc.py", "saved": False}))
    assert card["hold"] == "unsaved" and card["body"] == "Save with ⌘S so I can check it." and "Line 1" not in card["body"]
    unsaved_tab = _vscode_untitled()  # the screen alone shows it: Untitled-1 / ●
    assert run(coach.diagnose(S3, failed, None, OCR_CODE, screen=unsaved_tab))["hold"] == "unsaved"
    assert coach.diagnose.__module__  # LAST is not polluted by holds
    from server.coach.diagnose import LAST

    assert "s3" not in LAST


def test_wrong_folder_is_not_diagnosed(monkeypatch):
    _no_model(monkeypatch)
    card = run(coach.diagnose(S3, [{"checkId": "c3", "status": "fail"}], None, "def add(a, b):\n    return a + b",
                              file_state={"path": "/other/calc.py", "saved": True, "wrong_folder": True}))
    assert card["hold"] == "wrong_folder"


def test_screen_code_needs_two_agreeing_reads(monkeypatch):
    calls = []

    async def call(**kw):
        calls.append(kw["purpose"])
        if kw["purpose"] == "triage":
            return llm.CallResult(data={"route": "opus", "playbook_id": "none", "reason": ""}, model="h")
        return llm.CallResult(data={"playbook_id": "none", "severity": "warn", "title": "t", "body": "b. Do x.", "citation_id": "none",
                                    "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0, "diff_command": "",
                                    "actions": [], "guiding_question": "q?"}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    failed = [{"checkId": "c3", "status": "fail"}]
    step = {**S3, "id": "s3-ocr"}
    assert run(coach.diagnose(step, failed, None, OCR_CODE, code_source="screen"))["hold"] == "unconfirmed"  # first read
    assert run(coach.diagnose(step, failed, None, "def add(a, b):", code_source="screen"))["hold"] == "unconfirmed"  # disagrees
    assert calls == []
    card = run(coach.diagnose(step, failed, None, "def add(a,  b):", code_source="screen"))  # agrees with the previous read
    assert "hold" not in card  # no longer held: normal routing (here: nothing run yet → the start nudge)


def test_prompt_distrusts_ocr_syntax():
    from server.coach.diagnose import COACH_SYSTEM

    assert "hover tooltips" in COACH_SYSTEM and "Never claim a line is malformed" in COACH_SYSTEM


def test_judge_never_passes_unsaved_empty_or_unseen_files(monkeypatch):
    done = {"checks": [{"check_id": "c2", "verdict": "done", "confidence": 0.95, "reason": "calc.py tab is open", "evidence": "calc.py"}],
            "on_step_id": "", "summary": "calc.py open", "missing": ""}
    pending = [{"checkId": "c2", "status": "pending"}]
    fake(monkeypatch, done)
    unsaved = ScreenContext(image=Image.new("RGB", (10, 10)), cursor=(1, 1), scale=1.0, app="Code",
                            boxes=[Box(0, "● calc.py — calculator", 300, 8, 200, 14, source="ax", app="Code", role="AXTitle")]).numbered()
    r = run(StepJudge().judge(S2, pending, screen=unsaved, files={"calc.py": "x = 1"}))
    assert r["events"] == [] and r["card"]["title"] == "Save so I can check" and r["card"]["body"] == "Save with ⌘S so I can check it."
    for files in (None, {"calc.py": "   \n"}, {"other.py": "x = 1"}):  # not seen / empty
        r = run(StepJudge().judge(S2, pending, screen=SCREEN, files=files))
        assert r["events"] == [] and r["card"] is None
    r = run(StepJudge().judge(S2, pending, screen=SCREEN, files={"/lesson/calc.py": "def add(a, b): ..."}))
    assert r["events"][0]["payload"]["status"] == "pass"  # saved, non-empty → may pass
    j = run(coach.judge_step(S2, unsaved, files={"calc.py": "x = 1"}, check_results=pending))
    assert j["done"] is False and j["checks"]["c2"]["verdict"] == "unsure" and j["missing"] == "Save with ⌘S so I can check it"



# ---------- cost gate (Michael: Haiku every ~20 s while he was away, display asleep) -------------------------

from server.coach.gate import PeriodicGate, screen_signature


def test_clock_and_order_noise_is_not_change():
    a = "Code\ncalc.py — calculator\n4:37 PM\nThu Nov 14\n87%\ndef add(a, b):"
    b = "def add(a, b):\nCode\n4:38 PM\ncalc.py — calculator\nThu Nov 14\n86%"
    assert screen_signature(a) == screen_signature(b)
    assert screen_signature(a) != screen_signature(a + "\n    return a + b")


def test_backoff_and_stop_after_three_identical_verdicts(monkeypatch):
    clock = Clock()
    j = StepJudge(clock=clock)
    fake(monkeypatch, {"checks": [{"check_id": "c2", "verdict": "not_done", "confidence": 0.9, "reason": "no file", "evidence": ""}],
                       "on_step_id": "", "summary": "", "missing": "create calc.py"})
    pending = [{"checkId": "c2", "status": "pending"}]
    calls, waits = 0, []
    for n in range(1, 201):  # 200 ticks of 10 s; the screen changes a little every tick (a scrolling log)
        scr = SCREEN | {"Terminal": [f"log line {n}"]}
        if j.should_judge(S2, pending, idle_s=60, video_playing=False, screen=scr):
            run(j.judge(S2, pending, screen=scr))
            calls += 1
            waits.append(j.gate.state("s2")["interval_s"])
        clock.t += 10
    assert waits[:3] == [20.0, 40.0, 80.0] and calls == 3  # doubled each time, then stopped after 3 identical verdicts
    assert j.gate.state("s2")["stopped"] is True
    # a real change (a save) restarts it at the base interval
    clock.t += 1
    assert j.should_judge(S2, pending, idle_s=60, video_playing=False, screen=SCREEN, file_mtimes={"calc.py": 1731600000.0})
    other_app = {"Safari": [f"docs line {i}" for i in range(12)]}  # an app switch also wakes it
    assert j.should_judge(S2, pending, idle_s=60, video_playing=False, screen=other_app)


def test_backoff_caps_at_five_minutes():
    g = PeriodicGate(stop_after=99, clock=Clock())
    for _ in range(12):
        g.record("k", "same")
    assert g.state("k")["interval_s"] == 300.0
    g.record("k", "different")
    assert g.state("k")["interval_s"] == 20.0


def test_diagnose_identical_repeat_is_free(monkeypatch):
    calls = []

    async def call(**kw):
        calls.append(kw["purpose"])
        if kw["purpose"] == "triage":
            return llm.CallResult(data={"route": "opus", "playbook_id": "none", "reason": ""}, model="h")
        return llm.CallResult(data={"playbook_id": "none", "severity": "warn", "title": "t", "body": "b. Do x.", "citation_id": "none",
                                    "diff_expected": "", "diff_yours": "", "diff_file": "", "diff_line": 0, "diff_command": "",
                                    "actions": [], "guiding_question": "q?"}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    step = {"id": "m1", "title": "Run", "instructions": "Run it.", "checks": [{"id": "x", "type": "command_exit_ok", "label": "runs"}]}
    failed = [{"checkId": "x", "status": "fail", "detail": "exit 1"}]
    run(coach.diagnose(step, failed, None, "x = 1", error_text="TypeError: bad operand"))
    n = len(calls)
    again = run(coach.diagnose(step, failed, None, "x = 1", error_text="TypeError: bad operand"))
    assert len(calls) == n and again["_meta"]["memo"] is True  # no second paid call
    run(coach.diagnose(step, failed, None, "x = 2", error_text="TypeError: bad operand"))
    assert len(calls) > n  # the code changed → a fresh diagnosis



# ---------- DEMO / stubbed coach = zero cost (S11: 19 Claude calls in one DEMO rehearsal take) ---------------

import httpx

from server.coach import voice, web


@pytest.mark.parametrize("env", [{"DEMO": "1"}, {"ORCH_STUBS": "lesson,coach"}, {"ORCH_STUBS": "all"}])
def test_offline_mode_makes_no_paid_call(monkeypatch, tmp_path, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for k in ("ANTHROPIC_API_KEY", "BRIGHTDATA_API_KEY", "BRIGHTDATA_SERP_ZONE", "BRIGHTDATA_UNLOCKER_ZONE", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
        monkeypatch.setenv(k, "real-looking")
    monkeypatch.setenv("COACH_TTS_DIR", str(tmp_path))
    monkeypatch.setattr(llm, "_load_env", lambda: None)

    def no_network(*a, **kw):
        raise AssertionError("a paid call left the coach in offline mode")

    monkeypatch.setattr(llm, "get_client", no_network)
    monkeypatch.setattr(web, "_bd_request", no_network)
    monkeypatch.setattr(voice, "_transport", httpx.MockTransport(no_network))
    monkeypatch.setattr(voice, "_client", None)

    from server.coach import case_diffusion as d

    common.set_lesson(d.LESSON)
    card = run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    assert card["_meta"]["route"] == "playbook" and card["_meta"]["playbook_id"] == "lr_too_high"  # the offline answer
    assert run(coach.explain(d.STEP, "why?", {}))["_meta"]["fallback_reason"]
    assert run(coach.warm()) == {"skipped": "offline"}
    j = StepJudge()
    pending = [{"checkId": "c1", "status": "pending"}]
    assert not j.should_judge(S1, pending, idle_s=60, video_playing=False, screen=SCREEN)  # never on a timer
    r = run(coach.judge_step(S2, SCREEN, check_results=[{"checkId": "c2", "status": "pending"}]))
    assert r["offline"] is True and r["done"] is False and r["checks"]["c2"]["verdict"] == "unsure"
    assert run(coach.judge_step(S2, SCREEN, check_results=[{"checkId": "c2", "status": "pass"}]))["done"] is True
    from server.coach.tests.screen_case import make_screen

    assert run(coach.locate("the learning rate", make_screen())) == []  # no exact text → no model
    assert run(coach.point(d.STEP, make_screen(), about="x"))["via"] in ("exact", "fallback")
    assert run(web.gather("pandas", "Series.iteritems", "q")) == []
    assert run(voice.speak("Nice, step passed.")) is None  # nothing new synthesized


def test_offline_mode_flags():
    import os

    for env, want in [({}, False), ({"ORCH_STUBS": "lesson"}, False), ({"ORCH_STUBS": "lesson, coach"}, True), ({"DEMO": "1"}, True)]:
        old = {k: os.environ.pop(k, None) for k in ("DEMO", "ORCH_STUBS")}
        os.environ.update(env)
        try:
            assert llm.offline_mode() is want
        finally:
            for k in ("DEMO", "ORCH_STUBS"):
                os.environ.pop(k, None)
                if old[k] is not None:
                    os.environ[k] = old[k]


def test_demo_replay_fixtures_still_work(monkeypatch):
    """The demo CLI replays recorded answers under DEMO=1: replay is free, so it isn't blocked."""
    monkeypatch.setenv("DEMO", "1")
    monkeypatch.setenv("COACH_REPLAY_DIR", str(llm.FIXTURES_DIR))
    from server.coach import case_diffusion as d

    common.set_lesson(d.LESSON)
    card = run(coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    assert card["_meta"].get("source") == "replay"


# ---------- S9 "Just teach me" copy QA (text lessons; zero cost) -------------------------------------------

T1 = {"id": "t1", "title": "Add the add function", "file": "calculator.py",
      "instructions": "In calculator.py, below the comment, write def add(a, b): that returns a + b, then add print(add(2, 3)) at the bottom.",
      "code": "def add(a, b):\n    return a + b\n\nprint(add(2, 3))",
      "checks": [{"id": "t1a", "type": "file_contains", "label": "add function is written in the", "file": "calculator.py", "pattern": r"def add\("}],
      "targets": [{"file": "calculator.py", "match": "def add", "caption": "add function"}], "hints": []}
T3 = {"id": "t3", "title": "Run the calculator", "file": "(terminal)", "instructions": "Run the program and check that it prints 5.",
      "code": "", "run_command": "python3 calculator.py",
      "checks": [{"id": "t3a", "type": "output_contains", "label": "The add function is still in", "pattern": "5"}], "hints": []}
TEXT_LESSON = {"lesson": {"id": "calc-text", "title": "Build a calculator", "goal": "calculator", "mode": "lesson"}, "sources": [], "steps": [T1, T3]}


def _rules(text: str):
    assert len(text.split()) <= 12, text
    assert "Cursor" not in text and "“" not in text, text


def test_start_is_one_short_action_from_the_code():
    common.set_lesson(TEXT_LESSON)
    from server.coach.pointing import start_instruction

    a = start_instruction(T1)
    assert a == "In VS Code, type `def add(a, b):` in calculator.py." and "VS Code" in a
    _rules(a)
    b = start_instruction(T3)
    assert b == "Run `python3 calculator.py` in the VS Code terminal."
    _rules(b)
    card = run(coach.diagnose(T1, [{"checkId": "t1a", "status": "fail"}], None, ""))
    assert card["notStarted"] and card["body"] == a  # not the 22-word raw instructions


def test_hint_after_the_auto_card_moves_up_and_never_quotes_labels():
    common.set_lesson(TEXT_LESSON)
    nudge = {"stepId": "t1", "title": "Start: Add the add function", "notStarted": True}
    h = coach.hint(T1, 0, nudge)
    assert h["title"] == "Type this · Add the add function" and h["code"] == T1["code"] and h["actions"] == ["show_me"]
    _rules(h["body"])
    assert coach.hint(T3, 0, {"notStarted": True})["title"].startswith("Run this")
    q = coach.hint(T1, 0, {})["body"]  # no diagnosis yet: a question about the code
    assert q == "Which line of calculator.py defines add, and is it there yet?"
    assert "add function is written in the" not in coach.hint(T3, 0, {})["body"]
    assert coach.hint(T3, 0, {})["body"] == "What does `python3 calculator.py` print right now?"


def test_show_me_opens_the_existing_lesson_file():
    common.set_lesson(TEXT_LESSON)
    from server.coach.pointing import where_hint

    assert where_hint(T1) == "Open calculator.py in VS Code"  # lesson mode created it: not "Create …"
    r = run(coach.show_me(T1, None))
    assert r["where"] == "Open calculator.py in VS Code"


def test_offline_visible_syntax_error_names_it(monkeypatch):
    monkeypatch.setenv("DEMO", "1")
    common.set_lesson(TEXT_LESSON)
    code = "# a tiny calculator\n\n# add your functions below\ndef(a, b):\n    return a + b\n"
    err = 'Traceback (most recent call last):\n  File "/lesson/calculator.py", line 4\n    def(a, b):\n       ^\nSyntaxError: invalid syntax'
    card = run(coach.diagnose(T1, [{"checkId": "t1a", "status": "fail"}], None, code, error_text=err))
    assert card["_meta"]["route"] == "error_offline" and "notStarted" not in card
    assert card["body"] == "`def` needs a name: line 4 of calculator.py." and card["title"] == "SyntaxError in calculator.py"
    _rules(card["body"])
    other = run(coach.diagnose(T3, [{"checkId": "t3a", "status": "fail"}], None, "print(ad(2, 3))",
                               error_text='File "calculator.py", line 1\nNameError: name \'ad\' is not defined'))
    assert other["body"].startswith("NameError on line 1 of calculator.py") and len(other["body"].split()) <= 12


def test_lesson_mode_card_is_one_action_with_the_why_behind_explain(monkeypatch):
    seen = {}

    async def call(**kw):
        seen[kw["purpose"]] = kw["user_text"]
        if kw["purpose"] == "triage":
            return llm.CallResult(data={"route": "opus", "playbook_id": "none", "reason": ""}, model="h")
        return llm.CallResult(data={"playbook_id": "none", "severity": "fail", "title": "The function has no name",
                                    "body": "Python needs a name between def and the parentheses, so line 4 is a syntax error. In VS Code, name the function add on line 4 of calculator.py.",
                                    "citation_id": "none", "diff_expected": "def add(a, b):", "diff_yours": "def(a, b):", "diff_file": "calculator.py",
                                    "diff_line": 4, "diff_command": "", "actions": ["apply_fix"], "guiding_question": "q?"}, model="o")

    monkeypatch.setattr(llm, "structured_call", call)
    common.set_lesson(TEXT_LESSON)
    card = run(coach.diagnose(T1, [{"checkId": "t1a", "status": "fail"}], None, "def(a, b):\n    return a + b",
                              error_text="SyntaxError: invalid syntax"))
    assert card["body"] == "In VS Code, name the function add on line 4 of calculator.py."
    _rules(card["body"])
    assert card["why"].startswith("Python needs a name between def") and 'LESSON MODE ("Just teach me")' in seen["diagnose"]
