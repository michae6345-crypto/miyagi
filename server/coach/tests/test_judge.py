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
