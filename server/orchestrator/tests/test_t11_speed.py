"""Desktop test 11 (Nov 15, Kie Codes "Watch a video" notebook lesson s1-s7, engine-t11.log on dd85beb):

1. Explain took 6.37 s / 5.54 s: Haiku returned 1145 / 1052 output tokens (adaptive thinking) for a 64-word card. The
   explain, judge and triage requests now go out with thinking disabled (as the pointing call already did).
2. s1 got an unasked off-track card at 08:28:36 while the video still taught the step (1:07 of 0:40-1:13). In a video
   lesson the proactive card waits for the step's gate ("Video waits at", the segment's end) or Check my work; an
   error row failing on a real traceback still speaks; a "Just teach me" lesson is unchanged.
3. s7's output rows went red at 08:35:14 while Run All still ran (the cell printed at 08:35:18) and a triage started:
   while the notebook run goes (VS Code's toolbar says Interrupt) output rows stay pending and the coach waits.
4. s1 (a setup step with no code) spent a ~4 s Sonnet diagram prefetch nobody opened: skipped; steps with code keep it.
No paid calls: the Anthropic client is a fake.
"""
from __future__ import annotations

import asyncio
import importlib
import json
from types import SimpleNamespace

from server.coach import llm
from server.orchestrator import nb_coach
from server.orchestrator.tests.test_session import rig  # noqa: F401 (fixture)
from server.orchestrator.tests.test_t10_coach import _start

explain_mod = importlib.import_module("server.coach.explain")  # server.coach re-exports the functions by these names
judge_mod = importlib.import_module("server.coach.judge")
triage_mod = importlib.import_module("server.coach.triage")

def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ 1. thinking off on short cards / verdicts
class _FakeMessages:
    def __init__(self, sent: list, data: dict):
        self.sent, self.data = sent, data

    async def create(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn", model=kwargs["model"],
            content=[SimpleNamespace(type="text", text=json.dumps(self.data))],
            usage=SimpleNamespace(input_tokens=10, output_tokens=20, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0))


class _FakeClient:
    def __init__(self, sent: list, data: dict):
        self.messages = self.beta_messages = _FakeMessages(sent, data)
        self.beta = SimpleNamespace(messages=self.messages)

    def with_options(self, **kw):
        return self


def _fake_client(monkeypatch, data: dict) -> list:
    sent: list = []
    monkeypatch.delenv("COACH_REPLAY_DIR", raising=False)
    monkeypatch.delenv("COACH_RECORD_DIR", raising=False)
    monkeypatch.setattr(llm, "offline_mode", lambda: False)
    monkeypatch.setattr(llm, "has_credentials", lambda: True)
    monkeypatch.setattr(llm, "get_client", lambda: _FakeClient(sent, data))
    return sent


STEP = {"id": "s2", "title": "Import libraries and load MNIST", "instructions": "Add a cell, then press Shift+Enter",
        "code": "import tensorflow as tf\n", "checks": [{"id": "s2c1", "type": "output_contains",
                                                        "label": "MNIST shapes printed", "pattern": "60000"}]}


def test_explain_request_has_thinking_disabled(monkeypatch):
    sent = _fake_client(monkeypatch, {"title": "Why divide by 255", "body": "Pixels run 0-255; dividing puts them in "
                                      "0-1 so training is stable.", "explanation_index": -1, "caption": "",
                                      "citation_id": ""})
    card = run(explain_mod.explain(STEP, None, {"lesson": {"title": "MNIST"}}))
    assert card["title"] and sent
    assert all(k.get("thinking") == {"type": "disabled"} for k in sent), [k.get("thinking") for k in sent]
    assert sent[0]["model"] == llm.model_for("explain")  # the model is unchanged


def test_judge_request_has_thinking_disabled(monkeypatch):
    sent = _fake_client(monkeypatch, {"checks": [{"id": "s2c1", "done": False}], "done": False})
    run(judge_mod._ask(STEP, [{"checkId": "s2c1", "status": "fail"}], None, None, "", {"steps": [STEP]}))
    assert sent and sent[0]["thinking"] == {"type": "disabled"}
    assert sent[0]["model"] == llm.model_for("judge")


def test_triage_request_has_thinking_disabled(monkeypatch):
    sent = _fake_client(monkeypatch, {"route": "opus", "playbook_id": None, "reason": "unclear"})
    failed = [{"checkId": "s2c1", "type": "output_contains", "label": "MNIST shapes printed", "status": "fail"}]
    t = run(triage_mod.triage(STEP, failed, set(), code_excerpt="import tensorflow as tf",
                              error_text="something odd printed", use_haiku=True))
    assert t.by == "haiku" and sent and sent[0]["thinking"] == {"type": "disabled"}


def test_other_requests_keep_adaptive_thinking():
    """diagnose (Sonnet) still thinks: only the short card / verdict calls changed."""
    client = _FakeClient([], {})
    _, kw = llm._request(client, llm.HAIKU, [], "x", {"type": "object"}, "low", 10)
    assert kw["thinking"] == {"type": "adaptive"}


# ------------------------------------------------------------------ 2. no unasked Not yet while the video teaches
def _outcome(s) -> str:
    return (getattr(s, "_speak_noted", None) or ("", "", ""))[2]


def _video_step(rig):  # noqa: F811
    """The fixture's step 1 (a video lesson), the learner working on it, the clip still playing."""
    rig.s.video_offtrack_hold = True  # the Rig turns it off for the older ladder tests
    step = rig.s.step
    seg = rig.s._segment(step)
    assert seg is not None and not rig.s.segment_done and not rig.s.lesson_mode
    rig.s.last_action_t = rig.clock()  # they acted (ran the command): learner_started
    rig.s.video_t = seg["start"] + 1.0
    return step, seg


NOT_RUNNING = [{"checkId": "s1c2", "label": "Jupyter server running", "status": "fail",
                "detail": "not printed in the Terminal yet"},
               {"checkId": "s1c3", "label": "No terminal errors", "status": "fail",
                "detail": "Open the Terminal so I can check it."}]


def test_offtrack_waits_for_the_videos_gate(rig):  # noqa: F811
    async def go():
        await rig.start_lesson()
        step, seg = _video_step(rig)
        rig.clock.t += 30
        rig.s._consider_speaking("idle", step, NOT_RUNNING, rig.s.context())
        assert not rig.s.coaching and "video still teaches" in _outcome(rig.s)
        await rig.s.video_state(seg["end"], True)  # the video reached "Video waits at"
        await rig.settle()
        assert rig.s.segment_done
        rig.s.coaching = False
        rig.s.spoken_sig = None
        assert not rig.s._video_still_teaching(step, rig.s.context(), NOT_RUNNING)

    run(go())


def test_check_my_work_lets_the_offtrack_speak_before_the_gate(rig):  # noqa: F811
    async def go():
        await rig.start_lesson()
        step, _ = _video_step(rig)
        rig.clock.t += 30
        assert rig.s._video_still_teaching(step, rig.s.context(), NOT_RUNNING)
        await rig.s.action("check_step")
        await rig.settle()
        if rig.s.step is step and not rig.s.passed:
            assert not rig.s._video_still_teaching(step, rig.s.context(), NOT_RUNNING)

    run(go())


def test_a_real_traceback_still_speaks_during_the_video(rig):  # noqa: F811
    async def go():
        await rig.start_lesson()
        step, _ = _video_step(rig)
        rig.clock.t += 30
        failed = [{"checkId": "s1c3", "label": "No errors", "status": "fail", "detail": "error on screen"}]
        ctx = SimpleNamespace(output_tail=["Traceback (most recent call last):", '  File "x.py", line 3',
                                           "NameError: name 'np' is not defined"])
        assert not rig.s._video_still_teaching(step, ctx, failed)
        quiet = SimpleNamespace(output_tail=["[I ServerApp] Jupyter Server is running at http://localhost:8888"])
        assert rig.s._video_still_teaching(step, quiet, failed)  # an error row, but no error: held

    run(go())


def test_just_teach_me_lesson_is_unchanged(rig):  # noqa: F811
    async def go():
        await rig.start_lesson()
        step, _ = _video_step(rig)
        rig.s.graph["lesson"]["mode"] = "lesson"
        assert rig.s.lesson_mode
        assert not rig.s._video_still_teaching(step, rig.s.context(), NOT_RUNNING)

    run(go())


# ------------------------------------------------------------------ 3. a notebook run still going
S7_CHECKS = [
    {"id": "s7c1", "type": "screen_contains", "label": "model.evaluate called", "pattern": r"model\.evaluate\("},
    {"id": "s7c2", "type": "output_contains", "label": "Accuracy summary printed", "pattern": "Accuracy"},
    {"id": "s7c3", "type": "output_contains", "label": "evaluate progress output shown", "pattern": "313/313"},
    {"id": "s7c5", "type": "screen_absent", "label": "No evaluate errors", "pattern": "Traceback"},
]
S7_ROWS = [{"checkId": "s7c1", "label": "model.evaluate called", "status": "pass"},
           {"checkId": "s7c2", "label": "Accuracy summary printed", "status": "fail", "detail": "not printed yet"},
           {"checkId": "s7c3", "label": "evaluate progress output shown", "status": "fail", "detail": "not printed yet"},
           {"checkId": "s7c5", "label": "No evaluate errors", "status": "fail", "detail": "Traceback on screen"}]
TOOLBAR_RUNNING = {"Code": ["Generate  + Code  + Markdown | Interrupt  Restart  Clear All Outputs", "[16] 0.0s"]}
TOOLBAR_IDLE = {"Code": ["Generate  + Code  + Markdown | Run All  Restart  Clear All Outputs",
                         "KeyboardInterrupt was raised earlier"]}


def test_run_in_progress_reads_the_notebook_toolbar(tmp_path):
    step = {"id": "s7", "file": "Untitled.ipynb"}
    s = SimpleNamespace(notebook_lesson=True, workdir=str(tmp_path), _step_file=lambda st: "Untitled.ipynb",
                        _screen_lines=lambda: TOOLBAR_RUNNING)
    assert nb_coach.run_in_progress(s, step)
    s._screen_lines = lambda: TOOLBAR_IDLE
    assert not nb_coach.run_in_progress(s, step)
    assert not nb_coach.run_in_progress(SimpleNamespace(notebook_lesson=False, _step_file=lambda st: "nn.py",
                                                        _screen_lines=lambda: TOOLBAR_RUNNING), {"id": "s1"})


def test_output_rows_stay_pending_while_run_all_runs(rig, monkeypatch):  # noqa: F811
    async def go():
        step = await _start(rig, monkeypatch, S7_CHECKS, S7_ROWS, code="test_loss, test_accuracy = model.evaluate(x)")
        rig.s.gate_open = rig.s.screen_gate_open = True
        lines = {"now": TOOLBAR_RUNNING}
        monkeypatch.setattr(rig.s, "_screen_lines", lambda: lines["now"])
        await rig.s._publish(step, S7_ROWS)
        shown = {k: v["status"] for k, v in rig.s.check_state.items()}
        assert shown["s7c2"] == shown["s7c3"] == "pending"
        assert shown["s7c5"] == "fail"  # an error row still fails mid-run

        rig.s.last_action_t = rig.clock()
        rig.clock.t += 30
        rig.s._consider_speaking("idle", step, [r for r in S7_ROWS if r["checkId"] in ("s7c2", "s7c3")],
                                 rig.s.context())
        assert not rig.s.coaching and "notebook run is still going" in _outcome(rig.s)

        lines["now"] = TOOLBAR_IDLE  # the run ended without printing it: now it is a failure
        await rig.s._publish(step, S7_ROWS)
        shown = {k: v["status"] for k, v in rig.s.check_state.items()}
        assert shown["s7c2"] == shown["s7c3"] == "fail"

    run(go())


# ------------------------------------------------------------------ 4. no diagram prefetch for a setup step
def test_no_diagram_prefetch_for_a_setup_step_without_code(rig, monkeypatch):  # noqa: F811
    async def go():
        await rig.start_lesson()
        calls: list = []

        async def diagram(*a, **kw):
            calls.append(a)
            return {}

        monkeypatch.setattr(rig.s.m, "diagram", diagram)
        monkeypatch.setattr(rig.s.m, "has_diagrams", lambda: True)
        s1 = {"id": "s1", "title": "Activate .venv and start Jupyter", "code": "",
              "instructions": "Run source .venv/bin/activate && jupyter notebook in the VS Code terminal"}
        assert not rig.s._setup_without_code(s1)  # a lesson whose steps carry no code at all (the old PINN fixture)
        rig.s.steps[1]["code"] = "import tensorflow as tf\n"  # t11: s2..s7 carry their code, s1 has none
        assert rig.s._setup_without_code(s1)
        await rig.s._prefetch_diagram(rig.s.step_gen, s1)
        assert not calls
        s2 = {**STEP, "id": "s2"}
        assert not rig.s._setup_without_code(s2)  # a step with code keeps its prefetch (Diagram is instant)
        assert rig.s._setup_without_code({"id": "s0", "title": "Install TensorFlow", "code": ""})  # titled setup
        rig.s.graph["lesson"]["mode"] = "lesson"
        assert not rig.s._setup_without_code({"id": "nn4", "title": "Train it", "code": ""})  # Just teach me: unchanged

    run(go())
