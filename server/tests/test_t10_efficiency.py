"""t10 speed review: wasted model calls, counted with stubbed clients (no network, no key).

1. Diagram: the step-start prefetch serves the Diagram press (1 Sonnet call, not 2), however the screen changed.
2. Scene looks: a repeated answer backs off (5 s, 10 s ... 40 s) and stops after 3 identical answers until the learner
   acts; no look while the video plays and the learner hasn't touched anything.
3. Background judge: never before the learner does something on THIS step (the idle timer resets with the step), and
   never beside Check my work's own judge.
"""
from __future__ import annotations

import asyncio
import itertools
import json
from types import SimpleNamespace

import pytest

from server import diagrams
from server.coach.scene import FakeLook
from server.orchestrator import scene_watch
from server.orchestrator.tests.conftest import _isolated_and_free  # noqa: F401 (autouse: no paid keys, temp state)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- 1. diagram prefetch -> press

NET = {"kind": "network", "caption": "784 inputs, 10 outputs.", "graph": None,
       "network": {"layers": [784, 128, 10], "activation": "relu", "derivatives": [], "highlight": []}}


class CountingClient:
    def __init__(self, raw):
        self.raw, self.calls = raw, []
        self.messages = self.beta = self

    async def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", model="fake", usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                               content=[SimpleNamespace(type="text", text=json.dumps(self.raw))])


def test_diagram_prefetch_then_press_is_one_call(tmp_path, monkeypatch):
    import importlib

    build_mod = importlib.import_module("server.diagrams.build")
    from server.orchestrator.modules import Modules
    from server.orchestrator.tests.test_session import Rig, _to_step

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.setenv("ORCH_DIAGRAM_PREFETCH", "0")  # the prefetch is driven by hand below (no 2 s sleep)
    fake = CountingClient(NET)
    monkeypatch.setattr(build_mod, "_get_client", lambda: fake)
    diagrams.clear_cache()
    rig = Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,checks,coach,finder"))
    captions = itertools.count()
    real_sleep = asyncio.sleep

    async def go():
        await _to_step(rig, 1)
        assert rig.s.m.has_diagrams()
        # the video's captions change the screen text on every frame (t10: the cache key hashed it)
        monkeypatch.setattr(rig.s, "_screen_lines", lambda: {"Miyagi": [f"caption {next(captions)}"]})
        monkeypatch.setattr(asyncio, "sleep", lambda s, *a, **k: real_sleep(0))
        await rig.s._prefetch_diagram(rig.s.step_gen, rig.s.step)
        monkeypatch.setattr(asyncio, "sleep", real_sleep)
        assert len(fake.calls) == 1
        await rig.s.action("diagram")
        await rig.settle()

    try:
        run(go())
    finally:
        diagrams.clear_cache()
    assert len(fake.calls) == 1  # the press was served by the prefetch
    shown = rig.of("diagram")
    assert shown and shown[-1]["stepId"] == rig.s.step["id"] and shown[-1]["kind"] == "network"


# ---------------------------------------------------------------- 2. scene looks back off and stop

class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeSession:
    """Just what SceneWatch.tick reads: an active step whose screen text changes every frame (video captions)."""

    def __init__(self):
        self.clock = Clock()
        self.step = {"id": "s2", "title": "Build the model", "instructions": "Add the layers.", "file": "nn.py"}
        self.phase, self.step_gen, self.lesson_epoch = "active", 1, 1
        self.passed = self.awaiting_resume = self.awaiting_start = False
        self.video_playing, self.segment_done = False, True
        self.last_action_t, self.work_t = -1e9, None
        self.frame = 0
        self.lesson_mode, self.notebook_lesson, self.step_runs = True, False, []
        self.inputs = None
        self.screen = SimpleNamespace(reader=None)
        self.tasks: list[asyncio.Task] = []

    @property
    def last_obs(self):
        return SimpleNamespace(frame=self.frame, app="Code", windows=[], t=0)

    def _screen_lines(self):
        return {"Code": ["model = Sequential()"], "Miyagi": [f"caption {self.frame}"]}

    def _judge_gate_kwargs(self, step):
        return {"file_mtimes": {"nn.py": 1.0}, "screen_ok": True, "display_asleep": False}

    def _work_since(self, kind):
        return None if self.work_t is None else self.clock() - self.work_t

    def screen_down_reason(self):
        return None

    def _spawn(self, coro, **kw):
        t = asyncio.ensure_future(coro)
        self.tasks.append(t)
        return t

    def _run_command(self, step):
        return ""

    def _code_excerpt(self, step):
        return "", None

    def _step_file(self, step):
        return "nn.py"

    def _front_now(self):
        return "Code"


async def _ticks(s, w, seconds):
    """`seconds` 1-s engine ticks; the reader OCRs a new frame (new captions) every second."""
    for _ in range(seconds):
        s.clock.t += 1
        s.frame += 1
        await w.tick()
        if s.tasks:
            await asyncio.gather(*s.tasks)
            s.tasks.clear()


def _watch(s, look):
    w = scene_watch.attach(s, look=look, frame=lambda: ("img", s.last_obs), every_s=5.0)

    async def no_react(*a, **k):
        return None
    w._react = no_react
    return w


def test_identical_looks_back_off_and_stop_until_the_learner_acts(monkeypatch):
    monkeypatch.delenv("MIYAGI_SCENE_CAP_S", raising=False)
    monkeypatch.delenv("MIYAGI_SCENE_STOP_AFTER", raising=False)
    s = FakeSession()
    look = FakeLook([{"active_file": "nn.py", "step_file_open": True}])  # the same answer every time
    w = _watch(s, look)

    async def go():
        await _ticks(s, w, 120)  # two minutes of captions changing the screen, the learner away
        assert len(look.calls) == 3  # t=+1, +6 (5 s), +16 (10 s), then stopped: 3 identical answers
        assert w.gate.state(f"{s.lesson_epoch}:{s.step_gen}")["stopped"]
        s.work_t = s.clock()  # the learner types in the editor: looks resume
        await _ticks(s, w, 2)
        assert len(look.calls) == 4
        s.step_gen += 1  # a new step: a fresh gate
        await _ticks(s, w, 1)
        assert len(look.calls) == 5

    run(go())


def test_backoff_caps_at_about_40_s():
    s = FakeSession()
    answers = itertools.cycle([{"active_file": "nn.py"}])
    look = FakeLook([lambda step: next(answers)])
    w = scene_watch.attach(s, look=look, frame=lambda: ("img", s.last_obs), every_s=5.0, stop_after=99)

    async def no_react(*a, **k):
        return None
    w._react = no_react

    async def go():
        await _ticks(s, w, 300)

    run(go())
    assert w.gate.state(f"{s.lesson_epoch}:{s.step_gen}")["interval_s"] == 40.0
    assert len(look.calls) <= 11  # was 60 (one per 5 s): 5, 10, 20, then every 40 s


def test_no_look_while_the_video_plays_and_the_learner_is_away():
    s = FakeSession()
    look = FakeLook([lambda step: {"active_file": f"f{len(look.calls)}.py"}])  # never the same answer
    w = _watch(s, look)
    s.video_playing = True  # Show me / the lesson video, past the step's segment

    async def go():
        await _ticks(s, w, 60)
        assert look.calls == []
        s.last_action_t = s.clock()  # the learner pressed something meanwhile: looking is useful again
        await _ticks(s, w, 1)
        assert len(look.calls) == 1

    run(go())


# ---------------------------------------------------------------- 3. background judge gate

class CountingJudge:
    def __init__(self):
        self.n = 0

    def should_judge(self, step, results, **kw):
        return True

    async def judge(self, step, results, **kw):
        self.n += 1
        return {"events": [], "card": None}


@pytest.fixture
def jrig(tmp_path, monkeypatch):
    from server.orchestrator.tests.test_session import Rig

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    return Rig(tmp_path, with_inputs=True)


def test_no_background_judge_before_the_learner_starts_the_step(jrig):
    from server.orchestrator.tests.test_session import _to_step

    rig = jrig
    j = CountingJudge()

    async def go():
        await _to_step(rig, 0)
        rig.s._acted()  # worked on the last step ...
        rig.clock.t += 60
        await rig.s.goto_step(1)  # ... and the next one starts: its idle timer starts over
        await rig.settle()
        rig.s.judge = j
        rig.clock.t += 3
        assert rig.s.learner_idle_s() <= 3.0 + 1e-6
        for _ in range(5):  # the learner reads, watches: nothing done on this step
            rig.clock.t += 2
            await rig.s.tick()
            await rig.settle()
        assert j.n == 0
        rig.inputs.key()  # types in the lesson's editor
        rig.clock.t += 1
        await rig.s.tick()
        await rig.settle()
        assert j.n == 1

    run(go())


def test_no_background_judge_beside_check_my_work(jrig):
    from server.orchestrator.tests.test_session import _to_step

    rig = jrig
    j = CountingJudge()

    async def go():
        await _to_step(rig, 1)
        rig.s._acted()
        rig.s.judge = j
        rig.s._checking = 1  # Check my work is running its own judge for this step
        rig.clock.t += 10
        await rig.s.tick()
        await rig.settle()
        assert j.n == 0
        rig.s._checking = 0
        await rig.s.tick()
        await rig.settle()
        assert j.n == 1

    run(go())
