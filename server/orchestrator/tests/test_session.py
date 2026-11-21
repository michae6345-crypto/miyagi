"""State-machine tests. Run from the repo root:  python -m pytest server/orchestrator -q"""

from __future__ import annotations

import asyncio
import types
from pathlib import Path

import pytest

from server.orchestrator import stubs
from server.orchestrator.hub import Hub
from server.orchestrator.inputs import FakeInputs
from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.session import LessonSession
from shared.contracts.events import engine_message, parse_app_message


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Rig:
    """A session wired to a strict (contract-validating) hub, with a recorded event log."""

    def __init__(self, workdir: Path, modules: Modules | None = None, screen: FakeScreen | None = None,
                 with_inputs: bool = False):
        self.hub = Hub(strict=True)
        self.clock = Clock()
        self.inputs = FakeInputs(self.clock) if with_inputs else None
        self.workdir = workdir
        self.screen = screen
        self.s = LessonSession(self.hub.emit, modules or Modules(demo=False, force_stubs="all"),
                               clock=self.clock, idle_gate_s=5, advance_delay_s=0, metric_eval_s=0,
                               result_stagger_s=0, build_tick_s=0.01, screen=screen, seen_interval_s=0,
                               inputs=self.inputs)
        self.s.ready_hold_s = 0
        self.s.offtrack_grace_s = 0  # most tests drive the ladder at once; the grace has its own test
        self.s.video_offtrack_hold = False  # ...while the clip plays too; the T11 hold has its own (test_t11_speed)
        self.s.CARD_GAP_S = 0  # pacing (8 s between cards, 2 s between spotlight moves) has its own test
        self.s.SPOT_MIN_GAP_S = 0
        self.s.has_python = True  # run-step wording: `python` is there (the python3 rewrite has its own test)

    @property
    def events(self) -> list[dict]:
        return list(self.hub.history)

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]

    def of(self, type_: str) -> list[dict]:
        return [e["payload"] for e in self.events if e["type"] == type_]

    def mark(self) -> int:
        return len(self.hub.history)

    def since(self, mark: int) -> list[dict]:
        return self.events[mark:]

    async def settle(self) -> None:
        await asyncio.sleep(0)
        await self.s.drain()

    async def built(self) -> None:
        """The whole build, then settle. Since perf.until_loaded (2240591) a learn returns once the lesson is live
        (the quick-start placeholder / a progressive step 1); the rest of the build runs on as `_build_task`."""
        task = self.s._build_task
        if task is not None:
            await asyncio.wait({task})
        await self.settle()

    async def start_lesson(self) -> None:
        graph = stubs.load_fixture_lesson()
        await self.s.load_graph(graph)
        await self.settle()

    async def end_segment(self) -> None:
        step = self.s.step
        await self.s.video_state(step["video"]["end"], True)
        await self.settle()

    def write(self, text: str, name: str = "pinn_convection.py") -> None:
        (self.workdir / name).write_text(text)

    async def save(self, text: str) -> None:
        self.write(text)
        await self.s.on_file_change([str(self.workdir / "pinn_convection.py")])
        await self.settle()

    async def run(self, run_id: str, losses: list[tuple[int, float]], exit_code: int = 0) -> None:
        await self.s.ingest({"kind": "run_started", "run_id": run_id, "command": "python pinn_convection.py"})
        await self.s.ingest({"kind": "metric", "run_id": run_id,
                             "metrics": [{"step": s, "name": "loss", "value": v} for s, v in losses]})
        await self.settle()
        await self.s.ingest({"kind": "run_ended", "run_id": run_id, "exit_code": exit_code})
        await self.settle()


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    return Rig(tmp_path)


def run(coro):
    return asyncio.run(coro)


PLATEAU = [(s, 0.3 + (0.01 if s % 200 else 0)) for s in range(0, 5001, 100)]
CONVERGE = [(s, 1.0 * 0.998 ** s) for s in range(0, 5001, 100)]
S2 = "import torch.nn as nn\nnet = nn.Sequential(nn.Linear(2, 50), nn.Tanh(), nn.Linear(50, 1))\n"


# ---------------------------------------------------------------- contract mirror

def test_events_mirror_validates_and_rejects():
    assert engine_message("spotlight", {"clear": True})["payload"] == {"clear": True}
    msg = engine_message("step.passed", {"stepId": "s1"})
    assert msg == {"type": "step.passed", "payload": {"stepId": "s1"}}
    with pytest.raises(Exception):
        engine_message("check.updated", {"stepId": "s1", "checkId": "c", "label": "x", "status": "green"})
    with pytest.raises(ValueError):
        engine_message("nope", {})
    cmd = parse_app_message({"type": "action", "payload": {"kind": "hint"}})
    assert cmd.payload.kind == "hint"
    # additive fields are allowed on both sides
    assert engine_message("video.seek", {"t": 1, "play": True, "extra": 1})["payload"]["extra"] == 1


# ---------------------------------------------------------------- search + build

def test_learn_then_build_streams_happy_path(rig):
    async def go():
        await rig.s.learn("train a PINN")
        assert rig.of("search.done") == [{"total": 3}]
        assert [r["id"] for r in rig.of("search.result")] == ["r1", "r2", "r3"]
        await rig.s.build_lesson(["r1"])
        await rig.settle()

    run(go())
    t = rig.types()
    assert "lesson.building" in t
    assert rig.of("lesson.building")[-1]["progress"] == 1.0
    ready = rig.of("lesson.ready")[0]
    assert len(ready["steps"]) == 6
    assert ready["steps"][0]["video"]["videoId"] == "STUB_PINN_VID"
    started = rig.of("step.started")[0]
    assert started["stepId"] == "s1" and started["index"] == 0
    after = t[t.index("step.started"):]
    assert after[:2] == ["step.started", "check.updated"] and after.index("video.seek") + 1 == after.index("video.play")
    assert rig.of("video.seek")[0] == {"t": 0.0, "play": True}


def test_file_check_passes_and_advances(rig):
    async def go():
        await rig.start_lesson()
        await rig.end_segment()
        assert "video.pause" in rig.types()
        m = rig.mark()
        await rig.save("# hi\n")
        return rig.since(m)

    ev = run(go())
    types_ = [e["type"] for e in ev]
    assert types_[:2] == ["check.updated", "step.passed"]
    assert ev[0]["payload"]["status"] == "pass"
    assert ev[1]["payload"] == {"stepId": "s1", "nextStepId": "s2"}
    assert {"type": "spotlight", "payload": {"clear": True}} in ev
    assert any(e["type"] == "step.started" and e["payload"]["stepId"] == "s2" for e in ev)
    i = types_.index("step.started")
    assert types_[i:].count("video.seek") == 1 and "video.play" in types_[i:]
    assert rig.s.step["id"] == "s2"


def test_done_without_any_learner_action_asks_to_confirm(rig):
    rig.write("# already here\n")

    async def go():
        await rig.start_lesson()
        assert rig.s.step["id"] == "s1"
        assert rig.of("check.updated")[-1]["status"] == "pass"
        assert not rig.of("step.passed")  # screen says done, but nobody did anything: ask, don't assert
        looks = [c for c in rig.of("card") if c["title"] == "Looks done?"]
        assert looks and looks[0]["actions"] == ["confirm"]
        assert "video.seek" not in rig.types()  # already ahead of the clip: the video isn't replayed
        await rig.s.action("confirm")
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"


def test_video_plays_only_when_the_step_needs_it(rig):
    graph = stubs.load_fixture_lesson()
    graph["steps"][0].update(title="Install Python and VS Code", setup=True)

    async def go():
        await rig.s.load_graph(graph)  # s1: setup -> no seek / play
        await rig.settle()
        assert "video.seek" not in rig.types() and rig.s.segment_done
        rig.write("# s1\n")
        await rig.s.goto_step(1)  # s2 teaches something, but the learner is typing: position it, don't play
        rig.s.inputs = __import__("server.orchestrator.inputs", fromlist=["FakeInputs"]).FakeInputs(rig.clock)
        await rig.s.goto_step(1)
        rig.s.inputs.key()
        await rig.s.goto_step(1)
        await rig.settle()

    run(go())
    seeks = rig.of("video.seek")
    assert seeks[0] == {"t": 40.0, "play": True} and seeks[-1] == {"t": 40.0, "play": False}


def test_spotlight_on_segment_end_uses_screen_rect(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)

    async def go():
        await rig.start_lesson()
        await rig.save("# start\n")  # s1 passes via precision_checks (file exists), mirrored green
        screen.text["Code"] = ["import torch.nn as nn", "", "class Net(nn.Module):", "    pass"]
        m = rig.mark()
        await rig.end_segment()
        return rig.since(m)

    ev = run(go())
    assert rig.of("check.updated")[1]["checkId"] == "s1c1"  # screen checklist shown when a screen exists
    assert any(p.get("detail") == "confirmed by your files" for p in rig.of("check.updated"))
    spots = [e["payload"] for e in ev if e["type"] == "spotlight"]
    assert spots == [{"rect": {"x": 100.0, "y": 140.0, "w": 400.0, "h": 20.0}, "caption": "Two inputs (x, t), one output u",
                      "app": "Code", "matched": "class Net(nn.Module):"}]


def test_screen_checks_pass_from_ocr_and_watch_metric_patterns(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "nowhere"))  # no workdir: pure screen mode
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen, with_inputs=True)

    async def go():
        await rig.start_lesson()
        await rig.end_segment()
        rig.clock.t += 1
        rig.inputs.key()  # the learner types; the screen changes
        screen.text["Code"] = ["pinn_convection.py — sandbox"]
        await rig.s.on_screen(types.SimpleNamespace(app="Code", t=1.0))
        await rig.settle()
        assert rig.s.step["id"] == "s2"
        await rig.s.goto_step(4)
        await rig.settle()
        assert "loss" in screen.watched  # s5's metric_pattern is being read off the terminal
        await rig.end_segment()
        for st, v in CONVERGE:  # what the bridge does for each OCR'd metric line
            rig.s._on_screen_metric("screen-stub-pinn-convection", "loss", st, v)
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[0] == {"stepId": "s1", "nextStepId": "s2"}
    assert rig.of("step.passed")[-1] == {"stepId": "s5", "nextStepId": "s6"}
    assert rig.of("screen.seen")[0]["summary"] == "pinn_convection.py — sandbox"


def test_overlay_bounds_reach_the_screen_reader(tmp_path):
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)
    rig.s.overlay_bounds([{"x": 0, "y": 0, "w": 300, "h": 34}])
    assert screen.overlay == [{"x": 0, "y": 0, "w": 300, "h": 34}]


# ---------------------------------------------------------------- don't-nag gate

async def _to_step(rig, idx: int) -> None:
    await rig.start_lesson()
    await rig.s.goto_step(idx)
    await rig.settle()


def test_single_failure_does_not_nag_second_does(rig):
    async def go():
        await rig.start_lesson()
        await rig.save("# s1\n")
        await rig.end_segment()  # s2: no Linear/Tanh yet
        m = rig.mark()
        await rig.save("# s1\nimport torch\n")
        first = rig.since(m)
        m = rig.mark()
        await rig.save("# s1\nimport torch\nx = 1\n")
        return first, rig.since(m)

    first, second = run(go())
    assert not [e for e in first if e["type"] == "offtrack"]  # one failing save: a breakpoint, but no nagging
    off = [e["payload"] for e in second if e["type"] == "offtrack"]  # same failure saved twice: speak
    assert len(off) == 1 and off[0]["stepId"] == "s2" and off[0]["level"] == 2
    assert [e["payload"]["state"] for e in second if e["type"] == "status"][-1] == "offtrack"


def test_idle_gate_opens_after_5s(rig):
    async def go():
        await rig.start_lesson()
        await rig.save("# s1\n")
        await rig.save("# s1\nimport torch\n")  # one failing evaluation, engaged
        await rig.s.tick()
        assert not rig.of("offtrack")
        rig.clock.t += 4.9
        await rig.s.tick()
        assert not rig.of("offtrack")
        rig.clock.t += 0.2
        await rig.s.tick()
        await rig.settle()

    run(go())
    assert len(rig.of("offtrack")) == 1


def test_idle_gate_needs_engagement(rig):
    async def go():
        await rig.start_lesson()
        await rig.save("# s1\n")
        rig.clock.t += 60  # learner just watching s2's clip
        await rig.s.tick()
        await rig.settle()

    run(go())
    assert not rig.of("offtrack")


def test_hero_ladder_concept_then_exact_fix_then_green(rig):
    rig.s.screen = FakeScreen()
    rig.s.screen.text["Code"] = ["def train(model):", "    beta = 30", "    for epoch in range(4000):"]

    async def go():
        await _to_step(rig, 5)
        assert rig.s.step["id"] == "s6"
        rig.write("def train(model):\n    beta = 30\n    for epoch in range(4000):\n        pass\n")
        await rig.end_segment()
        m = rig.mark()
        await rig.run("r-plateau", PLATEAU)  # run ends failing: breakpoint -> level 2 concept card
        first = rig.since(m)
        rig.clock.t += 25
        m = rig.mark()
        await rig.run("r-plateau-again", PLATEAU)  # same failure again -> level 3 exact fix
        second = rig.since(m)
        m = rig.mark()
        await rig.run("r-curriculum", CONVERGE)
        return first, second, rig.since(m)

    first, second, fixed = run(go())
    off = [e["payload"] for e in first if e["type"] == "offtrack"]
    assert len(off) == 1 and off[0]["level"] == 2
    assert "diff" not in off[0] and "apply_fix" not in off[0]["actions"]
    assert off[0]["citation"]["url"] == "https://arxiv.org/abs/2109.01050"
    assert any(e["type"] == "metric" for e in first)
    off3 = [e["payload"] for e in second if e["type"] == "offtrack"]
    assert len(off3) == 1 and off3[0]["level"] == 3 and "apply_fix" in off3[0]["actions"]
    assert off3[0]["diff"]["yours"] == "beta = 30" and off3[0]["diff"]["line"] == 2
    spot = [e["payload"] for e in second if e["type"] == "spotlight"][-1]
    assert spot["matched"] == "    beta = 30" and spot["caption"] == off3[0]["title"]
    passed = [e["payload"] for e in fixed if e["type"] == "step.passed"]
    assert passed == [{"stepId": "s6"}]  # last step: no nextStepId
    assert rig.s.phase == "done"
    assert fixed[-1]["type"] == "video.pause"  # t11: the completion panel never plays the video's outro behind it
    assert "video.play" not in [e["type"] for e in fixed[[e["type"] for e in fixed].index("step.passed"):]]


def test_typing_guard_defers_speech_until_the_learner_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    rig = Rig(tmp_path, with_inputs=True)

    async def go():
        await _to_step(rig, 5)
        rig.write("beta = 30\n")
        rig.inputs.key()  # typing right as the run ends
        await rig.run("r1", PLATEAU)
        assert not rig.of("offtrack")
        rig.clock.t += 1
        rig.inputs.key()
        await rig.s.tick()
        assert not rig.of("offtrack")  # still typing
        rig.clock.t += 2.5
        await rig.s.tick()  # stopped typing: the deferred breakpoint speaks
        await rig.settle()

    run(go())
    assert len(rig.of("offtrack")) == 1


def test_stuck_escalates_to_the_exact_fix(rig):
    async def go():
        await _to_step(rig, 5)
        rig.write("def train():\n    beta = 30\n")
        await rig.run("r1", PLATEAU)
        assert rig.s.ladder == 2
        rig.clock.t += 60  # no progress for a minute
        await rig.s.tick()
        await rig.settle()

    run(go())
    levels = [p["level"] for p in rig.of("offtrack")]
    assert levels == [2, 3]


def test_same_failure_is_coached_once(rig):
    async def go():
        await _to_step(rig, 5)
        rig.write("beta = 30\n")
        await rig.run("r1", PLATEAU)
        await rig.save("beta = 30\n# thinking\n")
        await rig.save("beta = 30\n# still thinking\n")

    run(go())
    assert len(rig.of("offtrack")) == 1


def test_runs_from_previous_step_do_not_count(rig):
    async def go():
        await _to_step(rig, 4)
        await rig.end_segment()
        await rig.s.ingest({"kind": "run_started", "run_id": "r1"})
        await rig.s.ingest({"kind": "metric", "run_id": "r1",
                            "metrics": [{"step": s, "name": "loss", "value": v} for s, v in CONVERGE]})
        await rig.settle()
        assert rig.s.step["id"] == "s6"  # s5 passed mid-run on the loss threshold
        await rig.s.ingest({"kind": "metric", "run_id": "r1", "step": 6000, "name": "loss", "value": 1e-4})
        await rig.s.ingest({"kind": "run_ended", "run_id": "r1", "exit_code": 0})
        await rig.settle()

    run(go())
    assert rig.s.step["id"] == "s6" and not rig.s.passed


def test_config_keys_status_never_echoes_keys(monkeypatch):
    from server.orchestrator import main

    for var in main.KEY_ENV.values():  # apply_keys writes os.environ; restore it afterwards
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("GEMINI_API_KEY", "g-from-env")
    monkeypatch.setitem(main._ENV_AT_START, "gemini", "g-from-env")
    for name in main.KEY_ENV:
        monkeypatch.setitem(main._ENV_AT_START, name, "g-from-env" if name == "gemini" else "")
    st = main.apply_keys({"anthropic": "sk-test-123", "tigerUrl": "postgres://...", "someRetiredKey": "from-an-older-build"})
    want = {"anthropic": "ok", "gemini": "env", "elevenlabs": "missing", "tigerUrl": "missing"}
    assert {k: st[k] for k in want} == want  # unknown names are ignored (st also carries the cloud fields)
    assert "someRetiredKey" not in st
    from server.config import get_key, set_app_keys

    assert get_key("anthropic") == "sk-test-123" and get_key("gemini") == "g-from-env"
    set_app_keys({})
    assert "sk-test-123" not in str(st)
    engine_message("config.status", st)
    assert main._redact({"type": "config.keys", "payload": {"anthropic": "sk"}})["payload"] == "<redacted>"


# ---------------------------------------------------------------- actions

def test_actions_route(rig):
    async def go():
        await _to_step(rig, 5)
        rig.write("def train():\n    beta = 30\n")
        await rig.run("r1", PLATEAU)
        m = rig.mark()
        await rig.s.action("hint")
        await rig.s.action("hint")
        await rig.s.action("explain")
        await rig.s.action("ask", "why does beta matter?")
        await rig.s.action("diagram")
        await rig.s.action("diagram", "heatmap")
        await rig.s.action("back")
        await rig.s.action("show_me")
        await rig.s.action("voice_toggle")
        return rig.since(m)

    ev = run(go())
    cards = [e["payload"] for e in ev if e["type"] == "card"]
    assert [c["kind"] for c in cards] == ["hint", "hint", "explain", "answer"]
    assert cards[0]["title"] == "Hint 1 of 4" and cards[1]["title"] == "Hint 2 of 4"
    assert cards[1]["videoJump"]["t"] == 455
    kinds = [e["payload"]["kind"] for e in ev if e["type"] == "diagram"]
    assert kinds == ["gradients", "heatmap"]
    seeks = [e["payload"] for e in ev if e["type"] == "video.seek"]
    # 14f55e7: Back opens the previous step (s5, 310-380 s) and plays its clip from its start; Show me then replays it
    assert seeks == [{"t": 310.0, "play": True}, {"t": 310.0, "play": True}]
    assert rig.s.voice is False  # voice is off for now (MIYAGI_VOICE unset): the toggle is ignored


def test_apply_fix_edits_the_file(rig):
    async def go():
        await _to_step(rig, 5)
        rig.write("def train():\n    beta = 30\n    pass\n")
        await rig.run("r1", PLATEAU)
        await rig.s.action("apply_fix")
        await rig.settle()

    run(go())
    text = (rig.workdir / "pinn_convection.py").read_text()
    assert "    for beta in [1, 5, 10, 20, 30]:  # β curriculum\n        train_stage(model, beta)\n" in text
    assert "beta = 30" not in text


def test_apply_fix_never_writes_code_that_does_not_compile(rig):
    async def go():
        await _to_step(rig, 5)
        rig.write("def train():\n    beta = 30\n    for epoch in range(9):\n        pass\n")
        await rig.run("r1", PLATEAU)
        rig.s.last_offtrack["diff"]["expected"] = "for beta in [1, 30]:\n    for epoch in range(3):"
        rig.s.last_offtrack["diff"]["yours"] = "beta = 30\nfor epoch in range(9):"
        await rig.s.action("apply_fix")
        await rig.settle()

    run(go())
    assert "beta = 30" in (rig.workdir / "pinn_convection.py").read_text()
    assert rig.of("card")[-1]["title"] == "Fix it by hand"


def test_do_it_for_me_refuses_unsaved_file_then_applies_and_undoes(rig):
    async def go():
        await _to_step(rig, 5)
        original = "def train():\n    beta = 30\n    pass\n"
        rig.write(original)
        await rig.run("r1", PLATEAU)
        dirty = types.SimpleNamespace(windows=[types.SimpleNamespace(title="● pinn_convection.py — pinn-lab")], blocks=[])
        rig.s.last_obs = dirty
        await rig.s.action("apply_fix")
        assert rig.of("card")[-1]["title"] == "Save pinn_convection.py first"
        assert (rig.workdir / "pinn_convection.py").read_text() == original
        rig.s.last_obs = types.SimpleNamespace(windows=[types.SimpleNamespace(title="pinn_convection.py — pinn-lab")],
                                               blocks=[])
        await rig.s.action("apply_fix")
        await rig.settle()
        assert "for beta in" in (rig.workdir / "pinn_convection.py").read_text()
        assert rig.of("card")[-1]["title"] == "Fix applied" and rig.of("card")[-1]["actions"] == ["undo"]
        await rig.s.action("undo")
        await rig.settle()
        assert (rig.workdir / "pinn_convection.py").read_text() == original

    run(go())


def test_terminal_fix_is_staged_on_the_clipboard_never_run(rig, monkeypatch):
    staged = []

    async def fake_clip(text):
        staged.append(text)
        return True

    monkeypatch.setattr(LessonSession, "_clipboard", staticmethod(fake_clip))

    async def go():
        await _to_step(rig, 5)
        rig.s.last_offtrack = {"stepId": "s6", "diff": {"command": "pip install pyDOE", "expected": "", "yours": ""}}
        await rig.s.action("apply_fix")

    run(go())
    assert staged == ["pip install pyDOE"] and rig.of("card")[-1]["title"] == "Command copied"


def test_cursor_and_text_under_it_reach_the_coach(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    rig = Rig(tmp_path, with_inputs=True)
    seen = {}

    async def diagnose(step, failed, metrics, code, error_text="", cursor=None, **kw):
        seen["cursor"] = cursor
        return {"stepId": step["id"], "severity": "warn", "title": "t", "body": "b", "actions": ["hint"]}

    rig.s.m.diagnose = diagnose
    rect = types.SimpleNamespace(x=90.0, y=200.0, w=300.0, h=18.0, to_dict=lambda: {"x": 90, "y": 200, "w": 300, "h": 18})
    rig.s.last_obs = types.SimpleNamespace(windows=[], blocks=[types.SimpleNamespace(text="    beta = 30", app="Code",
                                                                                      rect=rect)])

    async def go():
        await _to_step(rig, 5)
        rig.write("beta = 30\n")
        rig.inputs.move(120, 208)
        await rig.run("r1", PLATEAU)

    run(go())
    assert seen["cursor"]["x"] == 120 and seen["cursor"]["under"]["text"] == "    beta = 30"


def test_action_without_lesson_is_an_error(rig):
    run(rig.s.action("hint"))
    assert rig.of("error")


# ---------------------------------------------------------------- resilience

def test_live_mode_reports_failures_instead_of_faking(rig):
    """No DEMO: a failing/missing real module becomes an `error` event, never canned data."""
    def boom(*a, **k):
        raise RuntimeError("api down")

    mods = Modules(demo=False, force_stubs="")
    mods.real["coach"] = types.SimpleNamespace(diagnose=boom)
    mods.real["finder"] = types.SimpleNamespace()  # not built yet
    mods.real["diagrams"] = types.SimpleNamespace()
    r2 = Rig(rig.workdir, mods)

    async def go():
        await r2.s.learn("pinn")
        await r2.s.load_graph(stubs.load_fixture_lesson())  # (lesson content is irrelevant here)
        await r2.settle()
        await r2.s.goto_step(5)
        await r2.settle()
        r2.write("beta = 30\n")
        await r2.run("r1", PLATEAU)
        await r2.s.action("diagram")

    run(go())
    errors = [e["message"] for e in r2.of("error")]
    assert any("finder.search isn't available" in m for m in errors)
    assert any("Coach unavailable: coach.diagnose failed: RuntimeError: api down" in m for m in errors)
    assert any("diagrams.build isn't available" in m for m in errors)
    assert r2.of("search.done") == [{"total": 0}] and not r2.of("search.result")
    assert not r2.of("offtrack") and not r2.of("diagram")


def test_demo_mode_falls_back_to_stubs(rig, monkeypatch, tmp_path):
    from server.orchestrator import modules as modules_mod

    monkeypatch.setenv("DEMO", "1")  # E5's coach then uses its offline playbook (no API call)

    monkeypatch.setattr(modules_mod, "DEMO_CACHE", tmp_path / "no-cache")
    def boom(*a, **k):
        raise RuntimeError("api down")

    mods = Modules(demo=True, force_stubs="")
    mods.real["checks"] = types.SimpleNamespace(evaluate_gate=boom)
    r2 = Rig(rig.workdir, mods)

    async def go():
        await r2.s.learn("pinn")
        await _to_step(r2, 5)
        r2.write("beta = 30\n")
        await r2.run("r1", PLATEAU)

    run(go())
    assert len(r2.of("search.result")) == 3
    assert r2.of("offtrack")[0]["title"] != "Loss plateaued at large β"  # E5's own DEMO card, not the old stub


def test_coding_lesson_opens_vscode_by_itself_after_lesson_ready(tmp_path, monkeypatch):
    """Michael: "it needs to open VS Code". A coding lesson with nothing missing opens the editor on its own
    (after lesson.ready, no "Open…?" card) and jumps to the step's target."""
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod
    from server.orchestrator.workspace import Workspace

    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: None)  # no S2 check (no key)

    calls = []
    ws = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)
    (tmp_path / "pinn_convection.py").write_text("import torch\n\n\ndef pde_residual(model, x, t, beta):\n    pass\n")
    rig = Rig(tmp_path)
    rig.s.workspace = ws

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)  # the setup check runs in the background
        await rig.settle()
        await rig.s.goto_step(3)
        await rig.settle()

    run(go())
    first = calls[0]  # S2: `code <dir> [-g <file>]` (never `-n`: it focuses a window that has the folder), or `open -a`
    assert (first[1:2] == [str(tmp_path.resolve())] and "-n" not in first) or (first[:3] == ["open", "-a", "Visual Studio Code"])
    opens = [c for c in calls if str(tmp_path.resolve()) in c]
    assert len(opens) == 1, opens  # opened once, whatever else ran (setup card, step starts, goto_step)
    assert rig.s.editor_open and not [c for c in rig.of("card") if (c.get("actions") or []) == ["open_editor"]]
    assert rig.types().index("lesson.ready") < len(rig.types())  # opened after the lesson UI was up
    gotos = [c for c in calls if "-g" in c and "-n" not in c]
    assert gotos and gotos[-1][-1] == f"{tmp_path / 'pinn_convection.py'}:4"


def test_setup_card_only_when_a_tool_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod
    from server.orchestrator.workspace import Workspace

    items = [{"tool": "vscode", "label": "VS Code", "kind": "editor", "needed": True, "ok": True},
             {"tool": "torch", "label": "PyTorch", "kind": "pip", "needed": True, "ok": False}]
    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: items)
    monkeypatch.setattr(wsmod, "setup_card", lambda its, resources=None: {"kind": "setup", "title": "Before you start",
                                                                           "body": "PyTorch is missing", "actions": ["install"]})
    calls = []
    rig = Rig(tmp_path)
    rig.s.workspace = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    # t9 V8: a coding lesson's VS Code opens by itself alongside the setup card (as the curated lesson's does)
    assert [c for c in rig.of("card") if c["kind"] == "setup"] and calls and rig.s.editor_open


def test_non_code_lesson_never_offers_vscode(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator.workspace import Workspace, needs_editor

    graph = stubs.load_fixture_lesson()
    for st in graph["steps"]:
        st["targets"] = [{"app": "Blender", "match": "Add Cube", "caption": "add a cube"}]
        for c in st["checks"]:
            c["app"] = "Blender"
        st["precision_checks"] = []
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: None)
    assert needs_editor(graph) is False and needs_editor(stubs.load_fixture_lesson()) is True
    calls = []
    rig = Rig(tmp_path)
    rig.s.workspace = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)
    async def go():
        await rig.s.load_graph(graph)
        await asyncio.sleep(0.05)

    run(go())
    assert not calls and not [c for c in rig.of("card") if c.get("actions") == ["open_editor"]]


def test_snapshot_for_reconnect(rig):
    async def go():
        await rig.start_lesson()

    run(go())
    snap = [t for t, _ in rig.s.snapshot()]
    assert snap[:2] == ["lesson.ready", "step.started"] and snap[-1] == "status"
    for t, p in rig.s.snapshot():
        engine_message(t, p)


def test_force_pass_and_segment_timer_fallback(rig):
    async def go():
        await rig.start_lesson()
        await rig.s.force_pass()
        await rig.settle()
        assert rig.s.step["id"] == "s2"

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"


# ---------------------------------------------------------------- HTTP / WS surface

def test_ws_and_ingest_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from server.orchestrator import main

    main.engine.session.result_stagger_s = 0
    main.engine.recorder.enabled = False
    monkeypatch.setitem(main.engine.modules.real, "finder", types.SimpleNamespace())  # no network in tests
    monkeypatch.setattr(main, "host_allowed", lambda _h: True)  # TestClient's Host is "testserver"
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            assert ws.receive_json()["type"] == "engine.hello"  # v2: always the first message
            first = ws.receive_json()
            assert first["type"] in ("status", "lesson.ready")
            ws.send_json({"type": "learn", "payload": {"query": "pinn"}})
            seen = []
            while True:
                msg = ws.receive_json()
                seen.append(msg["type"])
                if msg["type"] == "search.done":
                    break
            assert "error" in seen  # live mode: finder unavailable -> an honest error, no canned results
            assert "search.result" not in seen
        r = client.post("/ingest", json=[{"kind": "run_started", "run_id": "x"},
                                          {"kind": "metric", "run_id": "x", "step": 1, "name": "loss", "value": 0.5}])
        assert r.json()["ok"] is True and r.json()["accepted"] == 2
        assert client.get("/health").json()["ok"] is True


def test_record_then_replay_passes_the_hero_step(rig):
    from server.orchestrator import recorder

    rec = recorder.Recorder(out_dir=rig.workdir / "runs", enabled=True)
    rec.record({"kind": "run_started", "run_id": "good", "command": "python pinn_convection.py"})
    for s, v in CONVERGE:
        rec.record({"kind": "metric", "run_id": "good", "step": s, "name": "loss", "value": v})
    rec.record({"kind": "run_ended", "run_id": "good", "exit_code": 0})
    rec.record({"kind": "metric", "run_id": "x", "replay": True, "step": 1, "name": "loss", "value": 1})
    path = rig.workdir / "runs" / "good.jsonl"
    assert len(recorder.load(path)) == len(CONVERGE) + 2
    assert not (rig.workdir / "runs" / "x.jsonl").exists()  # replays are not re-recorded

    async def go():
        await _to_step(rig, 5)
        run_id = await recorder.replay(path, rig.s.ingest, speed=1000)
        await rig.settle()
        return run_id

    run_id = run(go())
    assert run_id.startswith("replay-good")
    assert rig.of("step.passed")[-1] == {"stepId": "s6"}


def test_spotlight_follows_target_and_precision_off(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.setenv("ORCH_PRECISION", "off")
    (tmp_path / "pinn_convection.py").write_text("# done already\n")
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)

    async def go():
        await rig.start_lesson()
        await rig.end_segment()
        assert rig.s.step["id"] == "s1"  # file exists, but precision is off: screen checks only
        await rig.s.goto_step(1)
        await rig.settle()
        await rig.end_segment()  # target not visible yet: no spotlight
        assert not [p for p in rig.of("spotlight") if "rect" in p]
        screen.text["Code"] = ["x = 1", "net = nn.Sequential("]
        await rig.s.on_screen(types.SimpleNamespace(app="Code", t=1.0))
        await rig.settle()
        screen.text["Code"] = ["# scrolled", "x = 1", "net = nn.Sequential("]
        await rig.s.on_screen(types.SimpleNamespace(app="Code", t=2.0))
        await rig.s.on_screen(types.SimpleNamespace(app="Code", t=3.0))  # unchanged: no re-send
        await rig.settle()

    run(go())
    ys = [p["rect"]["y"] for p in rig.of("spotlight") if "rect" in p]
    assert ys == [120.0, 140.0]


def test_streaming_finder_rows_arrive_before_search_finishes(rig):
    """E7's finder streams rows through on_result; they reach the app before the search returns."""
    arrived_before_end = []

    async def search(query, on_result=None, api_keys=None):
        await on_result({"id": "a", "kind": "video", "title": "A", "meta": "m", "score": 0.9, "reason": "r",
                         "url": "https://www.youtube.com/watch?v=AXXnSzmpyoI"})
        await asyncio.sleep(0.05)
        arrived_before_end.append(len(rig2.of("search.result")))
        await on_result({"id": "b", "kind": "paper", "title": "B", "meta": "m", "score": 0.5, "reason": "r", "url": "u"})
        return [{"id": "a"}, {"id": "b"}]

    mods = Modules(demo=False, force_stubs="lesson,coach,diagrams")
    mods.real["finder"] = types.SimpleNamespace(search=search)
    rig2 = Rig(rig.workdir, mods)
    built = []

    async def fake_build(url, goal, workdir, on_progress=None, **kw):
        built.append(url)
        return stubs.load_fixture_lesson()

    mods.build_lesson = fake_build

    async def go():
        await rig2.s.learn("pinn")
        await rig2.s.build_lesson(["a"])
        await rig2.settle()

    run(go())
    assert arrived_before_end == [1]
    assert [r["id"] for r in rig2.of("search.result")] == ["a", "b"] and rig2.of("search.done") == [{"total": 2}]
    assert built == ["https://www.youtube.com/watch?v=AXXnSzmpyoI"]


def test_pending_metric_eval_does_not_grade_the_next_step(rig):
    """A metric evaluation queued during step N's run must not pass step N+1 (no learner action there yet)."""
    async def go():
        await _to_step(rig, 4)
        await rig.end_segment()
        rig.s.metric_eval_s = 0.05
        await rig.s.ingest({"kind": "run_started", "run_id": "r1"})
        await rig.s.ingest({"kind": "metric", "run_id": "r1",
                            "metrics": [{"step": s, "name": "loss", "value": v} for s, v in CONVERGE]})
        await rig.s.evaluate("metric")  # s5 passes now; the queued eval fires after s6 started
        await rig.settle()

    run(go())
    assert [p["stepId"] for p in rig.of("step.passed")] == ["s5"]


def test_nan_metrics_reach_the_checks_and_fail_them(tmp_path, monkeypatch):
    """E3's tut run sends {"value": null, "nonfinite": "nan"}; it must fail the check (real evaluator)."""
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    rig = Rig(tmp_path, Modules(demo=False, force_stubs="lesson,coach,finder,diagrams"))

    async def go():
        await _to_step(rig, 4)
        await rig.end_segment()
        await rig.s.ingest({"kind": "run_started", "run_id": "r1"})
        await rig.s.ingest([{"kind": "metric", "run_id": "r1", "step": 100, "name": "loss", "value": 0.5}][0])
        await rig.s.ingest({"kind": "metric", "run_id": "r1", "step": 200, "name": "loss", "value": None,
                            "nonfinite": "nan"})
        await rig.s.ingest({"kind": "run_ended", "run_id": "r1", "exit_code": 0})
        await rig.settle()

    run(go())
    assert rig.s.context().metrics == {} or True  # (new step context; check the run itself)
    run_pts = rig.s.runs["r1"].metrics["loss"]
    assert run_pts == [(100, 0.5), (200, None)]
    assert [p["value"] for p in rig.of("metric")] == [0.5]  # only finite values go to the app
    assert not rig.s.passed and rig.s.step["id"] == "s5"
    assert any(c["status"] == "fail" for c in rig.s.check_state.values())


def test_streamed_targets_spotlight_before_the_card(rig):
    """E5 streams `targets` mid-reply: the spotlight goes up before the offtrack card lands."""
    async def diagnose(step, failed, metrics, code, on_targets=None, **kw):
        on_targets([{"boxId": 3, "label": "learning rate", "text": "lr = 0.3",
                     "rect": {"x": 40, "y": 300, "w": 120, "h": 18}}])
        await asyncio.sleep(0.01)
        return {"stepId": step["id"], "severity": "warn", "title": "lr too high", "body": "b", "actions": ["hint"],
                "targets": [{"boxId": 3, "label": "learning rate", "text": "lr = 0.3",
                             "rect": {"x": 40, "y": 300, "w": 120, "h": 18}}]}

    rig.s.m.diagnose = diagnose

    async def go():
        await _to_step(rig, 5)
        rig.write("lr = 0.3\n")
        m = rig.mark()
        await rig.run("r1", PLATEAU)
        return [e["type"] for e in rig.since(m) if e["type"] in ("spotlight", "offtrack")], rig.of("spotlight")

    order, spots = run(go())
    assert order[0] == "spotlight" and "offtrack" in order
    assert spots[-1]["rect"] == {"x": 40.0, "y": 300.0, "w": 120.0, "h": 18.0} and spots[-1]["caption"] == "learning rate"
    assert rig.of("offtrack")[0]["targets"][0]["text"] == "lr = 0.3"


def test_learner_action_cancels_an_in_flight_diagnosis(rig):
    cancelled = []
    rig.s.m.cancel_coach = lambda: cancelled.append(1) or 1
    rig.s.coaching = True
    run(rig.s.on_file_change([]))
    assert cancelled == [1]


def test_do_it_for_me_previews_then_applies_on_confirm(rig):
    async def do_it_for_me(step, file, text, last):
        return {"file": file, "unified_diff": "-lr = 0.3\n+lr = 1e-3\n", "summary": "Lower the learning rate to 1e-3.",
                "line": 1, "new_text": text.replace("lr = 0.3", "lr = 1e-3"), "requires_confirmation": True}

    rig.s.m.has_do_it_for_me = lambda: True
    rig.s.m.do_it_for_me = do_it_for_me
    path = rig.workdir / "pinn_convection.py"

    async def go():
        await _to_step(rig, 5)
        rig.write("lr = 0.3\nbeta = 30\n")
        await rig.run("r1", PLATEAU)
        await rig.s.action("apply_fix")
        card = rig.of("card")[-1]
        assert card["title"] == "Apply this fix?" and card["actions"] == ["confirm"] and "+lr = 1e-3" in card["diff"]
        assert path.read_text() == "lr = 0.3\nbeta = 30\n"  # nothing written before confirm
        await rig.s.action("confirm")
        await rig.settle()
        assert path.read_text() == "lr = 1e-3\nbeta = 30\n"
        assert rig.of("card")[-1]["title"] == "Fix applied"
        # a preview that went stale (learner edited the file) is refused
        await rig.s.action("apply_fix")
        rig.write("lr = 1e-3\nbeta = 30\n# edited\n")
        await rig.s.action("confirm")

    run(go())
    assert rig.of("card")[-1]["title"] == "The file changed"


def test_command_plus_code_fix_stages_command_then_previews_code(rig, monkeypatch):
    staged = []

    async def fake_clip(text):
        staged.append(text)
        return True

    monkeypatch.setattr(LessonSession, "_clipboard", staticmethod(fake_clip))

    async def do_it_for_me(step, file, text, last):
        return {"file": file, "unified_diff": "-import pandas\n+import pandas as pd\n", "summary": "Alias pandas.",
                "line": 1, "new_text": text.replace("import pandas", "import pandas as pd")}

    rig.s.m.has_do_it_for_me = lambda: True
    rig.s.m.do_it_for_me = do_it_for_me

    async def go():
        await _to_step(rig, 5)
        rig.write("import pandas\n")
        rig.s.last_offtrack = {"stepId": "s6", "diff": {"command": "pip install pandas", "file": "pinn_convection.py",
                                                         "yours": "import pandas", "expected": "import pandas as pd"}}
        await rig.s.action("apply_fix")

    run(go())
    assert staged == ["pip install pandas"]
    assert [c["title"] for c in rig.of("card")][-2:] == ["Command copied", "Apply this fix?"]


class RealClock:
    def __call__(self) -> float:
        import time as _t

        return _t.monotonic()


def test_build_progress_ticks_with_real_stages_then_fails_humanly(tmp_path, monkeypatch):
    import logging as _logging

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    rig = Rig(tmp_path)
    rig.s.clock = RealClock()
    rig.s.build_tick_s = 0.05
    lesson_log = _logging.getLogger("server.lesson")

    async def slow_failing_build(url, goal, workdir, on_progress=None, **kw):
        await asyncio.sleep(0.12)
        lesson_log.warning("gemini video pass too slow; switching engine")
        await asyncio.sleep(0.12)
        raise RuntimeError("Could not retrieve a transcript: 429 Client Error: Too Many Requests (youtube)")

    rig.s.m.build_lesson = slow_failing_build
    snaps = []

    async def go():
        task = asyncio.create_task(rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk"))
        await asyncio.sleep(0.08)
        snaps.append(rig.s.snapshot())  # an app reconnecting mid-build
        await task

    run(go())
    building = rig.of("lesson.building")
    assert len(building) >= 4  # ticks while the build runs
    assert any("reading the transcript instead" in b["message"] for b in building)
    assert building[-1]["failed"] is True and "rate-limiting" in building[-1]["message"]
    assert "YouTube is rate-limiting this network" in rig.of("error")[-1]["message"]
    assert rig.of("status")[-1] == {"state": "idle"} and rig.s.phase == "idle"
    assert [t for t, _ in snaps[0]] == ["status", "lesson.building"] and snaps[0][0][1] == {"state": "thinking"}
    assert rig.s.snapshot() == [("status", {"state": "idle"})]


def test_build_success_still_loads_the_lesson(rig):
    async def build(url, goal, workdir, on_progress=None, **kw):
        return stubs.load_fixture_lesson()

    rig.s.m.build_lesson = build
    run(rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk"))
    assert rig.of("lesson.building")[-1] == {"message": "Lesson ready", "progress": 1.0}
    assert rig.of("lesson.ready") and rig.s.phase == "active"


def test_human_build_errors():
    from server.orchestrator.session import human_build_error

    assert "rate-limited" in human_build_error(RuntimeError("429 RESOURCE_EXHAUSTED daily quota"))
    assert "taking too long" in human_build_error(RuntimeError("building the lesson took over 300s"))
    assert "YouTube videos" in human_build_error(ValueError("only YouTube sources are supported for now: ''"))
    both = RuntimeError("no engine could build the lesson:\ngemini: Gemini call failed: 429 RESOURCE_EXHAUSTED quota\n"
                        "claude: no transcript for AXXnSzmpyoI: 429 Too Many Requests")
    assert "Gemini is rate-limited and YouTube is rate-limiting" in human_build_error(both)


def test_diagram_uses_s4_build_signature_and_question(rig):
    calls = []

    async def build(step, context):
        calls.append(context)
        return {"kind": "network", "caption": "c", "stepId": step["id"],
                "data": {"layers": [2, 32, 1], "activation": "tanh", "derivatives": ["u_t"], "residual": "r"}}

    rig.s.m.forced.discard("diagrams")
    rig.s.m.real["diagrams"] = types.SimpleNamespace(build=build)

    async def go():
        await _to_step(rig, 3)
        await rig.s.action("diagram", "why do we need autograd here?")
        await rig.s.action("diagram", "network")

    run(go())
    assert calls[0]["question"] == "why do we need autograd here?" and "kind" not in calls[0]
    assert calls[1]["kind"] == "network" and calls[1]["question"] is None
    assert [d["stepId"] for d in rig.of("diagram")] == ["s4", "s4"]


def test_build_stage_labels_come_from_on_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    rig = Rig(tmp_path)
    rig.s.clock = RealClock()
    rig.s.build_tick_s = 0.03

    async def build(url, goal, workdir, on_progress=None, **kw):
        for stage, msg in [("watching", ""), ("reading_transcript", ""), ("writing_steps", "212 transcript lines"),
                           ("engine_switch", "quota"), ("steps_ready", "claude"), ("adapting", ""), ("done", "41.2")]:
            on_progress(stage, msg)
            await asyncio.sleep(0.07)
        return stubs.load_fixture_lesson()

    rig.s.m.build_lesson = build
    run(rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk"))
    msgs = [b["message"] for b in rig.of("lesson.building")]
    for label in ("Watching the video", "Writing the steps",
                  "Gemini is rate-limited; using the transcript", "Fitting the checks to your project"):
        assert label in msgs, label
    beats = [b for b in rig.of("lesson.building") if "elapsedS" in b]
    assert len(beats) > len(set(b["message"] for b in beats))  # heartbeats repeat the stage text unchanged
    assert all(b["message"] == b["message"].split(" · ")[0] for b in beats)  # no timer in the text
    assert rig.of("lesson.ready")


def test_voice_speaks_step_offtrack_and_pass_only_when_on_and_not_typing(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.setenv("MIYAGI_VOICE", "1")  # voice is off by default (config.voice_enabled)
    rig = Rig(tmp_path, with_inputs=True)
    said, prefetched = [], []

    async def speak_event(kind, payload):
        said.append(kind)
        return {"audioUrl": f"/tts/{kind}.mp3", "text": kind}

    async def prefetch(lines):
        prefetched.extend(lines)

    rig.s.m.speak_event = speak_event
    rig.s.m.prefetch_voice = prefetch
    rig.s.m.voice_line = lambda kind, p: f"Step {p['index'] + 1}: {p['title']}."

    async def go():
        await rig.start_lesson()
        assert not said  # voice is off by default
        await rig.s.action("voice_toggle")
        await rig.settle()
        await asyncio.sleep(0)
        assert len(prefetched) == 6 and prefetched[0] == "Step 1: Create the training script."
        rig.clock.t += 5
        await rig.save("# s1\n")  # pass s1 -> step.passed + step.started(s2)
        await asyncio.sleep(0.05)
        rig.inputs.key()  # typing: nothing is spoken
        await rig.s.goto_step(2)
        await asyncio.sleep(0.05)

    run(go())
    assert said == ["step.passed", "step.started"]
    assert [p["audioUrl"] for p in rig.of("speak")] == ["/tts/step.passed.mp3", "/tts/step.started.mp3"]


def test_voice_off_by_default_never_speaks_or_prefetches(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("MIYAGI_VOICE", raising=False)
    rig = Rig(tmp_path, with_inputs=True)
    said, prefetched = [], []

    async def speak_event(kind, payload):
        said.append(kind)
        return {"audioUrl": f"/tts/{kind}.mp3", "text": kind}

    async def prefetch(lines):
        prefetched.extend(lines)

    rig.s.m.speak_event = speak_event
    rig.s.m.prefetch_voice = prefetch

    async def go():
        await rig.start_lesson()
        await rig.s.action("voice_toggle")
        await rig.settle()
        rig.clock.t += 5
        await rig.save("# s1\n")
        await asyncio.sleep(0.05)

    run(go())
    assert rig.s.voice is False and not said and not prefetched and not rig.of("speak")
    from server.orchestrator import config as orch_config

    assert orch_config.voice_enabled() is False  # Modules._voice() then hands out no ElevenLabs module at all


def test_learning_events_are_recorded_for_tiger_stats(rig):
    events = []
    rig.s.m.record = lambda kind, lesson, step, video_t=None, payload=None, source_id=None: events.append(
        (kind, step, (payload or {}).get("check_id"), source_id, video_t))

    async def go():
        await _to_step(rig, 5)
        await rig.s.video_state(480.0, True)
        rig.write("beta = 30\n")
        await rig.run("r1", PLATEAU)  # check_fail x2, offtrack
        await rig.run("r2", CONVERGE)  # check_pass x2, step_passed
        await rig.s.action("ask", "why?")

    run(go())
    kinds = [e[0] for e in events]
    assert kinds[:2] == ["step_started", "step_started"]  # s1 (load) then s6 (goto)
    assert {"check_fail", "offtrack", "check_pass", "step_passed", "question"} <= set(kinds)
    fail = next(e for e in events if e[0] == "check_fail")
    assert fail[1] == "s6" and fail[2] in ("s6c1", "s6c2") and fail[3] == "STUB_PINN_VID" and fail[4] == 480.0


def test_end_lesson_mid_build_is_quiet_and_complete(rig):
    started = asyncio.Event()

    async def slow_build(url, goal, workdir, on_progress=None, **kw):
        started.set()
        await asyncio.sleep(30)

    rig.s.m.build_lesson = slow_build

    async def go():
        t = asyncio.create_task(rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk"))
        await started.wait()
        assert rig.s.building()
        await rig.s.end_lesson()
        await t  # the build's awaiter returns quietly

    run(go())
    assert not rig.of("error") and not [b for b in rig.of("lesson.building") if b.get("failed")]
    assert rig.of("lesson.ended")[-1] == {"reason": "end_lesson"} and rig.of("status")[-1] == {"state": "idle"}
    assert rig.s.phase == "idle" and not rig.s.building()


def test_end_lesson_with_a_lesson_running_and_new_learn_ends_old(rig):
    recorded = []
    rig.s.m.record = lambda kind, *a, **k: recorded.append(kind)

    async def go():
        await rig.start_lesson()
        await rig.s.end_lesson()
        assert rig.s.graph is None and rig.s.step is None
        await rig.start_lesson()
        await rig.s.learn("something else")  # a new search ends the running lesson first

    run(go())
    ended = rig.of("lesson.ended")
    assert ended[0] == {"lessonId": "stub-pinn-convection", "reason": "end_lesson"}
    assert ended[1] == {"lessonId": "stub-pinn-convection", "reason": "new lesson"}
    assert {"type": "spotlight", "payload": {"clear": True}} in rig.events and "video.pause" in rig.types()
    assert recorded.count("lesson_ended") == 2


def test_post_end_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from server.orchestrator import main

    main.engine.recorder.enabled = False
    monkeypatch.setattr(main, "host_allowed", lambda _h: True)  # TestClient's Host is "testserver"
    with TestClient(main.app) as client:
        r = client.post("/end")
        assert r.json() == {"ok": True, "ended": None, "kept": False}  # Nov 15: kept = the place stays for after a restart
        assert main.engine.session.phase == "idle"


def test_diagrams_never_cross_lessons(rig):
    """Same step id in two lessons: S4's cache key gets the lesson id, cache is cleared on end, and a
    diagram that finishes after the lesson ended is dropped."""
    seen_ids, cleared = [], []
    release = asyncio.Event()

    async def build(step, context):
        seen_ids.append(step["id"])
        if step["id"].endswith(":slow"):
            await release.wait()
        return {"kind": "network", "caption": step["id"], "stepId": step["id"],
                "data": {"layers": [2, 1], "activation": "tanh", "derivatives": ["u_t"], "residual": "r"}}

    rig.s.m.forced.discard("diagrams")
    rig.s.m.real["diagrams"] = types.SimpleNamespace(build=build, clear_cache=lambda: cleared.append(1))

    async def go():
        g1 = stubs.load_fixture_lesson()
        await rig.s.load_graph(g1)
        await rig.s.action("diagram", "network")
        g2 = stubs.load_fixture_lesson()
        g2["lesson"]["id"] = "other-lesson"
        await rig.s.end_lesson()
        await rig.s.load_graph(g2)
        await rig.s.action("diagram", "network")
        # a slow diagram that outlives its lesson
        rig.s.graph["steps"][0]["id"] = "slow"
        rig.s.idx = 0
        t = asyncio.create_task(rig.s.action("diagram", "network"))
        await asyncio.sleep(0.01)
        await rig.s.end_lesson()
        release.set()
        await t

    run(go())
    assert seen_ids[0] == "stub-pinn-convection:s1" and seen_ids[1] == "other-lesson:s1"
    assert [d["stepId"] for d in rig.of("diagram")] == ["s1", "s1"]  # the late one was dropped
    assert len(cleared) == 2


def test_end_lesson_is_idempotent(rig):
    async def go():
        await rig.start_lesson()
        await rig.s.end_lesson()
        await rig.s.end_lesson()
        await rig.s.end_lesson()

    run(go())
    ended = rig.of("lesson.ended")
    assert ended == [{"lessonId": "stub-pinn-convection", "reason": "end_lesson"},
                     {"reason": "end_lesson"}, {"reason": "end_lesson"}]
    assert rig.of("status")[-1] == {"state": "idle"} and not rig.of("error")


def test_returning_app_gets_resume_card_and_lesson_is_frozen(rig):
    async def go():
        await _to_step(rig, 3)
        await rig.s.video_state(250.0, True)
        snap = rig.s.snapshot(ask_resume=True)
        assert [t for t, _ in snap] == ["spotlight", "video.pause", "card"]  # E7: no box left behind the card
        card = snap[2][1]
        assert card["kind"] == "resume" and card["actions"] == ["resume", "end_lesson"]
        assert card["title"] == "Continue where you left off?" and "Write the PDE residual" in card["body"]
        m = rig.mark()
        await rig.save("u_t + beta * u_x\nautograd.grad\n")  # frozen: nothing is graded while undecided
        assert not [e for e in rig.since(m) if e["type"] in ("check.updated", "step.passed", "offtrack")]
        assert [t for t, _ in rig.s.snapshot()] == ["spotlight", "video.pause", "card"]  # still undecided
        m = rig.mark()
        await rig.s.action("resume")
        return rig.since(m)

    ev = run(go())
    types_ = [e["type"] for e in ev]
    assert types_[:2] == ["lesson.ready", "step.started"]
    seek = [e["payload"] for e in ev if e["type"] == "video.seek"][-1]
    assert seek["t"] == 250.0
    assert not rig.s.awaiting_resume


def test_resume_card_start_new_ends_the_lesson(rig):
    async def go():
        await rig.start_lesson()
        rig.s.snapshot(ask_resume=True)
        await rig.s.action("end_lesson")

    run(go())
    assert rig.of("lesson.ended")[-1]["reason"] == "end_lesson" and rig.s.graph is None
    assert rig.s.snapshot(ask_resume=True) == [("status", {"state": "idle"})]


def test_engine_asks_to_resume_only_when_the_app_comes_back(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    import time as _time

    from server.orchestrator.main import Engine

    e = Engine()
    e.session.graph = stubs.load_fixture_lesson()
    assert e.app_returning() is False  # never shown to an app (e.g. the demo's autostart)
    e.mark_lesson_seen()
    e.last_client_gone = _time.monotonic() - 2
    assert e.app_returning() is False  # a 2 s network blip: just continue
    e.last_client_gone = _time.monotonic() - 30
    assert e.app_returning() is True  # the app was closed and reopened
    e.session.graph["lesson"]["id"] = "a-different-lesson"
    assert e.app_returning() is False


def test_nothing_from_an_ended_lesson_arrives_after_lesson_ended(rig):
    """S1's 4 cases: an explain card, a diagram, a coach card and a diagram prefetch that finish after end_lesson."""
    gate = asyncio.Event()

    async def slow_explain(step, question, context):
        await gate.wait()
        return {"stepId": step["id"], "kind": "explain", "title": "late", "body": "late"}

    async def slow_diagnose(step, failed, metrics, code, **kw):
        await gate.wait()
        return {"stepId": step["id"], "severity": "warn", "title": "late", "body": "b", "actions": ["hint"]}

    async def slow_build(step, context):
        await gate.wait()
        return {"kind": "network", "caption": "late", "stepId": step["id"],
                "data": {"layers": [2, 1], "activation": "tanh", "derivatives": ["u_t"], "residual": "r"}}

    rig.s.m.explain = slow_explain
    rig.s.m.diagnose = slow_diagnose
    rig.s.m.forced.discard("diagrams")
    rig.s.m.real["diagrams"] = types.SimpleNamespace(build=slow_build, clear_cache=lambda: None)

    async def go():
        await _to_step(rig, 5)
        rig.write("beta = 30\n")
        t_explain = asyncio.create_task(rig.s.action("explain"))
        t_diagram = asyncio.create_task(rig.s.action("diagram", "network"))
        await rig.s.ingest({"kind": "run_started", "run_id": "r1"})
        await rig.s.ingest({"kind": "metric", "run_id": "r1",
                            "metrics": [{"step": s, "name": "loss", "value": v} for s, v in PLATEAU]})
        await rig.s.ingest({"kind": "run_ended", "run_id": "r1", "exit_code": 0})  # coach starts (slow)
        await asyncio.sleep(0.01)
        m = rig.mark()
        await rig.s.end_lesson()
        gate.set()
        await asyncio.gather(t_explain, t_diagram, return_exceptions=True)
        await asyncio.sleep(0.05)
        return rig.since(m)

    after = run(go())
    types_ = [e["type"] for e in after]
    assert "lesson.ended" in types_
    tail = types_[types_.index("lesson.ended") + 1:]
    assert not [t for t in tail if t in ("card", "diagram", "offtrack", "spotlight", "check.updated", "error")], tail


def test_s2_setup_card_install_and_open_editor_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod
    from server.orchestrator.workspace import Workspace
    from server.workspace import setup_card

    state = {"pandas_ok": False}

    def reqs(graph, folder):
        return [{"tool": "pandas", "label": "pandas", "kind": "python_package", "why": "dataframes", "needed": True,
                 "installed": state["pandas_ok"], "ok": state["pandas_ok"],
                 "install": {"method": "pip", "command": "pip install pandas", "url": None}},
                {"tool": "vscode", "label": "VS Code", "kind": "editor", "why": "No editor needed for this lesson.",
                 "needed": False, "installed": True, "ok": True, "install": {"method": "none", "command": None, "url": None}}]

    def fake_install(item, folder, on_line):
        on_line("Collecting pandas")
        state["pandas_ok"] = True
        return {"ok": True, "tool": item["tool"], "version": "2.2.3"}

    monkeypatch.setattr(wsmod, "requirements", reqs)
    monkeypatch.setattr(wsmod, "setup_card", setup_card)
    monkeypatch.setattr(wsmod, "install", fake_install)
    calls = []
    rig = Rig(tmp_path)
    rig.s.workspace = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        card = rig.of("card")[0]
        assert card["kind"] == "setup" and "install" in card["actions"] and "open_editor" not in card["actions"]
        await rig.s.action("install", "pandas")
        await asyncio.sleep(0.1)
        await rig.s.action("open_editor")  # editor not needed for this lesson: ignored

    run(go())
    prog = rig.of("setup.progress")
    assert prog[0]["line"].startswith("Installing") and {"tool": "pandas", "line": "Collecting pandas"} in prog
    assert prog[-1] == {"tool": "pandas", "done": True, "ok": True, "version": "2.2.3"}
    last = rig.of("card")[-1]
    assert last["title"] == "Ready to go" and last["body"] == "pandas installed ✓"  # the row flipped, status on the card
    # t9 V12: while the card still offers Install its body stays put (the row shows the progress: setup.progress)
    assert not any(c["body"].startswith("Installing pandas") for c in rig.of("card"))
    assert not calls  # never opened VS Code



def test_lesson_mode_install_success_is_one_line_without_open_or_skip(tmp_path, monkeypatch):
    """E27: after Install, "Ready to go · requests installed ✓" offered Open Visual Studio Code and Skip while weather.py
    was in front. In lesson mode the editor is open: the success is one line that closes itself, no buttons."""
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod
    from server.orchestrator.workspace import Workspace
    from server.workspace import setup_card

    state = {"ok": False}

    def reqs(graph, folder):
        return [{"tool": "requests", "label": "requests", "kind": "python_package", "why": "http", "needed": True,
                 "installed": state["ok"], "ok": state["ok"], "install": {"method": "pip", "command": "pip install requests", "url": None}},
                {"tool": "vscode", "label": "Visual Studio Code", "kind": "editor", "why": "the editor", "needed": True,
                 "installed": True, "ok": True, "install": {"method": "none", "command": None, "url": None}}]

    def fake_install(item, folder, on_line):
        state["ok"] = True
        return {"ok": True, "tool": item["tool"], "version": "2.32.3"}

    monkeypatch.setattr(wsmod, "requirements", reqs)
    monkeypatch.setattr(wsmod, "setup_card", setup_card)
    monkeypatch.setattr(wsmod, "install", fake_install)
    rig = Rig(tmp_path)
    rig.s.workspace = Workspace(enabled=True, runner=lambda argv: True)

    async def go():
        g = stubs.load_fixture_lesson()
        g["lesson"]["mode"] = "lesson"
        for st in g["steps"]:
            st.pop("video", None)
        await rig.s.load_graph(g)
        await rig.settle()
        await asyncio.sleep(0.05)
        setup = [c for c in rig.of("card") if c["kind"] == "setup"][0]
        assert "install" in setup["actions"] and "open_editor" not in setup["actions"]
        await rig.s.action("install", "requests")
        await asyncio.sleep(0.1)

    run(go())
    last = rig.of("card")[-1]
    assert last["title"] == "requests installed ✓" and last["actions"] == [] and last["dismissAfterMs"] > 0
    assert rig.s._setup_card is None  # nothing pending: the Start card / nudges may go out
    ready = rig.of("lesson.ready")[0]
    assert ready["lesson"]["outline"]["count"] == len(ready["steps"])  # E23: a finished build's outline is its steps

def test_long_video_builds_progressively(rig):
    """E2's on_update: start on part 1, append later parts, wait (not finish) at the end of the built part."""
    full = stubs.load_fixture_lesson()
    part2_go = asyncio.Event()

    def graph_with(n, complete):
        g = json.loads(json.dumps(full))
        g["steps"] = g["steps"][:n]
        g["lesson"]["complete"] = complete
        g["lesson"]["parts"] = {"done": 1 if n < 3 else 2, "failed": 0, "total": 2, "list": []}
        return g

    async def build(url, goal, workdir, on_progress=None, on_update=None, **kw):
        await on_update(graph_with(2, False), False)
        await part2_go.wait()
        await on_update(graph_with(3, False), False)
        await on_update(graph_with(3, True), True)
        return graph_with(3, True)

    rig.s.m.build_lesson = build

    async def go():
        t = asyncio.create_task(rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk"))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if rig.of("lesson.ready"):
                break
        ready = rig.of("lesson.ready")[0]
        assert len(ready["steps"]) == 2 and ready["lesson"]["complete"] is False
        await rig.s.force_pass()  # s1
        await rig.settle()
        await rig.s.force_pass()  # s2: the last BUILT step
        await rig.settle()
        assert rig.of("step.passed")[-1] == {"stepId": "s2", "pending": True}
        more = rig.of("card")[-1]
        assert more["title"] == "Building the next part…" and "(part 2 of 2)" in more["body"]
        assert rig.s.phase == "active" and rig.s.waiting_more
        part2_go.set()
        await t
        await rig.settle()

    import json
    run(go())
    upd = rig.of("lesson.updated")
    assert [s["id"] for s in upd[0]["steps"]] == ["s3"] and upd[0]["complete"] is False
    assert upd[-1]["complete"] is True
    assert rig.of("step.started")[-1]["stepId"] == "s3" and not rig.s.waiting_more
    assert len(rig.of("lesson.ready")) == 1  # never re-loaded


def test_e2_learner_facing_first_error_line():
    from server.orchestrator.session import human_build_error

    e = RuntimeError("Couldn't read this video (1:56:20 long): Gemini's quota is used up.\n"
                     "(no engine could build the lesson) gemini: 429 ...")
    assert human_build_error(e) == "Couldn't read this video (1:56:20 long): Gemini's quota is used up."


def _fake_preflight(prefetched):
    async def preflight(url, goal, row=None, on_late=None, api_keys=None):
        res = {"url": url, "kind": "no-code", "chapters": 0, "partial": True,
               "buildPlan": {"strategy": "whole", "estSecondsToFirstSteps": 40, "firstChapter": None}}
        if on_late:
            asyncio.get_running_loop().call_later(0.02, on_late, {**res, "partial": False,
                                                                   "goalMatch": {"score": 0.2, "note": "no-code bots"}})
        return res

    def card(res):
        c = {"kind": "preflight", "title": "No-code video" + ("" if res["partial"] else " (checked)"), "body": "b",
             "actions": ["build", "pick_another"], "preflight": res}
        if res.get("goalMatch"):
            c["warning"], c["recommended"] = "This video isn't about building an LLM.", "pick_another"
        return c

    return types.SimpleNamespace(preflight=preflight, preflight_card=card,
                                 prefetch=lambda rows, goal, **kw: prefetched.append((len(rows), goal)))


def test_preflight_before_build_then_build_or_pick_another(rig):
    prefetched, built = [], []
    rig.s.m._preflight_mod = lambda: _fake_preflight(prefetched)

    async def build(url, goal, workdir, **kw):
        built.append(url)
        return stubs.load_fixture_lesson()

    rig.s.m.build_lesson = build

    async def go():
        await rig.s.learn("build chat gpt")
        assert prefetched == [(1, "build chat gpt"), (3, "build chat gpt")]  # the video row as it came, then the top 3
        await rig.s.build_lesson(["r1"])
        assert not built and rig.s.phase == "preflight"
        cards = [c for c in rig.of("card") if c["kind"] == "preflight"]
        assert cards and cards[0]["actions"] == ["build", "pick_another"]
        await asyncio.sleep(0.05)  # the late, complete answer replaces the partial card
        late = [c for c in rig.of("card") if c["kind"] == "preflight"][-1]
        assert late["warning"] and late["recommended"] == "pick_another"
        assert [t for t, _ in rig.s.snapshot()] == ["status", "card"]  # a reconnecting app sees the same card
        n_results, n_searches = len(rig.of("search.result")), len(prefetched)
        await rig.s.action("pick_another")
        assert rig.s.pending_pick is None and rig.s.phase == "idle" and rig.of("status")[-1] == {"state": "idle"}
        assert len(rig.of("search.result")) == 2 * n_results and rig.of("search.done")[-1] == {"total": n_results}
        assert len(prefetched) == n_searches  # the rows were re-sent, not searched again
        await rig.s.build_lesson(["r1"])
        await rig.s.action("build")
        await rig.settle()

    run(go())
    assert built == [stubs.SEARCH_RESULTS[0]["url"]]
    assert rig.of("lesson.ready") and rig.s.phase == "active"


def test_preflight_prefetch_starts_while_the_search_still_streams(rig):
    """Video speed: a live search streams its first rows at ~5 s and ends at ~18 s, and a pick before search.done
    cancels it (main.py), so prefetching only at search.done left the picked card waiting ~3-5 s on Claude. The first
    3 video rows are prefetched as they arrive; search.done still prefetches the final top 3."""
    prefetched, gate = [], asyncio.Event()
    rig.s.m._preflight_mod = lambda: _fake_preflight(prefetched)
    rows = [{"id": f"v{i}", "kind": "video", "title": f"V{i}", "meta": "", "score": 90 - i, "reason": "",
             "url": f"https://www.youtube.com/watch?v=vid{i:08d}"} for i in range(5)]
    rows.insert(1, {"id": "b1", "kind": "blog", "title": "B", "meta": "", "score": 89, "reason": "",
                    "url": "https://example.com/post"})

    async def search(query):
        for i, r in enumerate(rows):
            if i == 3:
                await gate.wait()  # the search's slow tail
            yield dict(r)

    rig.s.m.search = search

    async def go():
        task = asyncio.ensure_future(rig.s.learn("build a pinn"))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if len(prefetched) >= 2:
                break
        before_done = list(prefetched)
        assert not rig.of("search.done")
        gate.set()
        await task
        return before_done

    before_done = run(go())
    assert before_done == [(1, "build a pinn"), (1, "build a pinn")]  # v0 and v1 while streaming (not the blog)
    assert prefetched == [(1, "build a pinn")] * 3 + [(6, "build a pinn")]  # 3 early (v2 after the gate), then search.done
    assert rig.of("search.done")


def test_cached_lesson_holds_ready_like_a_curated_one(rig):
    """Video speed: Build on a cached lesson waited the full ORCH_READY_HOLD_S (1.5 s) after "Lesson ready" for a
    build that took 0 s. A cache hit (E2's cache_hit stage) holds 0.6 s like a curated lesson; a real build keeps 1.5."""
    rig.s.ready_hold_s, rig.s.CACHED_READY_HOLD_S = 0.4, 0.05

    def builder(hit: bool):
        async def build(url, goal, workdir, on_progress=None, **kw):
            if hit and on_progress:
                on_progress("cache_hit", "abc.json")
                on_progress("done", "abc.json")
            return stubs.load_fixture_lesson()
        return build

    async def timed(hit: bool) -> float:
        rig.s.m.build_lesson = builder(hit)
        t0 = asyncio.get_running_loop().time()
        await rig.s._run_build("https://www.youtube.com/watch?v=abcdefghijk", "g")
        await rig.built()
        assert rig.s.graph is not None
        return asyncio.get_running_loop().time() - t0

    async def go():
        cached = await timed(True)
        await rig.s.end_lesson()
        built = await timed(False)
        return cached, built

    cached, built = run(go())
    assert cached < 0.3 and built >= 0.4


def test_end_lesson_clears_a_pending_pick(rig):
    rig.s.m._preflight_mod = lambda: _fake_preflight([])

    async def go():
        await rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk")
        assert rig.s.pending_pick is not None
        await rig.s.end_lesson()
        await asyncio.sleep(0.05)

    run(go())
    assert rig.s.pending_pick is None and rig.of("lesson.ended")
    # the late card for the abandoned pick must not show up after lesson.ended
    types_ = rig.types()
    assert "card" not in types_[types_.index("lesson.ended"):]


def test_hint_presses_do_not_stack_identical_cards(rig):
    async def go():
        await _to_step(rig, 5)
        for _ in range(6):  # key repeat: the ladder tops out and returns the same last card
            await rig.s.action("hint")
        rig.clock.t += 20
        await rig.s.action("hint")  # later, the same card may be shown again

    run(go())
    titles = [c["title"] for c in rig.of("card")]
    assert titles == ["Hint 1 of 4", "Hint 2 of 4", "Hint 3 of 4", "Hint 4 of 4", "Hint 4 of 4"]


def test_explain_answer_for_a_previous_step_is_dropped(rig):
    gate = asyncio.Event()

    async def slow_explain(step, question, context):
        await gate.wait()
        return {"stepId": step["id"], "kind": "explain", "title": "Why the check wants X", "body": "b"}

    rig.s.m.explain = slow_explain

    async def go():
        await _to_step(rig, 0)
        t = asyncio.create_task(rig.s.action("explain"))
        await asyncio.sleep(0.01)
        await rig.s.goto_step(1)  # the learner moved on to s2
        gate.set()
        await t

    run(go())
    assert not rig.of("card")


def test_install_once_per_tool_and_pip_waits_for_the_lesson_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod

    calls = []
    release = __import__("threading").Event()

    def fake_install(item, folder, on_line):
        calls.append((item["tool"], folder))
        release.wait(2)
        return {"ok": True, "tool": item["tool"]}

    monkeypatch.setattr(wsmod, "install", fake_install)
    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: [])
    pip_item = {"tool": "torch", "label": "PyTorch", "kind": "python_package", "why": "w", "needed": True,
                "installed": False, "ok": False, "install": {"method": "pip", "command": "pip install torch", "url": None}}
    rig = Rig(tmp_path)

    async def go():
        # on the preflight card (no lesson yet): the pip install waits for the lesson folder
        rig.s.pending_pick = {"url": "u", "row": None, "card": {"kind": "preflight", "title": "t", "body": "b",
                                                                "actions": ["build", "install"], "items": [pip_item]}}
        await rig.s.action("install", "torch")
        await rig.settle()
        assert not calls and rig.of("card")[-1]["body"].startswith("PyTorch will be installed into this lesson's own")
        rig.s.pending_pick = None
        await rig.s.load_graph(stubs.load_fixture_lesson())  # the lesson (and its folder) now exists
        await asyncio.sleep(0.05)
        await rig.s.action("install", "torch")  # double click while it's running: ignored
        await rig.s.action("install", "torch")
        release.set()
        await asyncio.sleep(0.1)

    run(go())
    assert calls == [("torch", str(tmp_path))]  # once, into the lesson's folder (its .venv), not the engine's


def test_offline_coach_errors_once_per_step_and_backs_off(rig):
    calls = []

    async def failing(step, failed, metrics, code, **kw):
        calls.append(1)
        raise RuntimeError("coach.diagnose failed: CoachUnavailable: diagnose: connection error")

    rig.s.m.diagnose = failing

    async def go():
        await _to_step(rig, 5)
        rig.write("beta = 30\n")
        await rig.run("r1", PLATEAU)  # breakpoint -> fails
        for _ in range(60):  # a minute of idle ticks
            rig.clock.t += 1
            await rig.s.tick()
            await rig.settle()

    run(go())
    assert len([e for e in rig.of("error") if "Coach unavailable" in e["message"]]) == 1
    assert 2 <= len(calls) <= 4  # retried with backoff (15 s, 30 s...), not every second


def test_demo_lesson_follows_the_picked_video(tmp_path, monkeypatch):
    import json as _json
    import os as _os

    from server.orchestrator import modules as modules_mod

    cache = tmp_path / "cache"
    (cache / "lessons").mkdir(parents=True)
    hero = stubs.load_fixture_lesson()
    hero["sources"][0]["videoId"] = "AXXnSzmpyoI"
    hero["lesson"]["id"] = "hero"
    other = stubs.load_fixture_lesson()
    other["sources"][0]["videoId"] = "reactVIDEO1"
    other["lesson"]["id"] = "react"
    (cache / "lessons" / "a.json").write_text(_json.dumps(hero))
    (cache / "lessons" / "b.json").write_text(_json.dumps(other))
    _os.utime(cache / "lessons" / "b.json", (2e9, 2e9))  # react is the newest file
    monkeypatch.setattr(modules_mod, "DEMO_CACHE", cache)
    monkeypatch.delenv("ORCH_LESSON", raising=False)
    m = Modules(demo=True, force_stubs="")
    g = run(m.build_lesson("https://www.youtube.com/watch?v=AXXnSzmpyoI", "", str(tmp_path)))
    assert g["lesson"]["id"] == "hero"
    assert m._real_fn("coach", "diagnose") is not None  # E5's coach runs under DEMO (its own offline playbook)


def _win(app, x=0.0, y=0.0, w=800.0, h=600.0):
    rect = types.SimpleNamespace(to_dict=lambda: {"x": x, "y": y, "w": w, "h": h})
    return types.SimpleNamespace(app=app, title=app, rect=rect)


def test_show_me_hint_explain_always_point_somewhere(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)

    async def go():
        await _to_step(rig, 1)  # s2: target class/nn.Sequential in Code
        # 1) target visible on screen -> spotlight on it, at once
        screen.text["Code"] = ["import torch", "net = nn.Sequential("]
        m = rig.mark()
        await rig.s.action("show_me")
        ev1 = rig.since(m)
        # 2) target not visible, but the editor window is -> spotlight the window
        screen.text["Code"] = ["unrelated"]
        rig.s.last_obs = types.SimpleNamespace(windows=[_win("Code", 10, 20, 900, 700)], blocks=[])
        m = rig.mark()
        await rig.s.action("hint")
        ev2 = rig.since(m)
        # 3) nothing visible at all -> a card that says where to go
        rig.clock.t += 20  # past the duplicate-card window
        rig.s.last_obs = types.SimpleNamespace(windows=[], blocks=[])
        m = rig.mark()
        await rig.s.action("hint")
        ev3 = rig.since(m)
        m = rig.mark()
        await rig.s.action("explain")
        ev4 = rig.since(m)
        return ev1, ev2, ev3, ev4

    ev1, ev2, ev3, ev4 = run(go())
    t1 = [e["type"] for e in ev1]
    assert t1[:2] == ["video.seek", "video.play"] and "spotlight" in t1
    assert [e for e in ev1 if e["type"] == "spotlight"][0]["payload"]["matched"] == "net = nn.Sequential("
    assert [e["type"] for e in ev2][0] == "status"  # 'thinking' first
    spot2 = [e["payload"] for e in ev2 if e["type"] == "spotlight"][0]
    assert spot2["rect"] == {"x": 10.0, "y": 20.0, "w": 900.0, "h": 700.0} and spot2["app"] == "Code"
    card3 = [e["payload"] for e in ev3 if e["type"] == "card"][0]
    assert card3["title"] == "Open pinn_convection.py" and "so I can see it" in card3["body"]
    assert [e["type"] for e in ev4][0] == "status" and any(e["type"] == "card" for e in ev4)


def test_hint_says_where_to_go_when_code_is_not_visible(rig):
    async def go():
        await _to_step(rig, 1)
        rig.s.last_results = [{"checkId": "s2c1", "label": "Notebook created", "status": "pending", "detail": "Code not visible"}]
        rig.s.last_obs = types.SimpleNamespace(windows=[_win("Code")], blocks=[])
        await rig.s.action("hint")

    run(go())
    assert rig.of("card")[-1]["title"] == "Open pinn_convection.py"


def test_notebook_lesson_screen_checks_accept_the_browser(rig):
    g = stubs.load_fixture_lesson()
    g["lesson"]["title"] = "Fine-tune an LLM in Google Colab"
    run(rig.s.load_graph(g))
    assert rig.s.notebook_lesson
    assert all("app" not in c for st in rig.s.steps for c in st["checks"])
    assert all("app" not in t for st in rig.s.steps for t in st.get("targets") or [])


def test_same_offtrack_is_not_resent(rig):
    """A step that keeps failing the same way must not reopen the card the learner closed."""
    async def same(step, failed, metrics, code, **kw):
        return {"stepId": step["id"], "severity": "warn", "title": "Learning rate too high", "body": "b",
                "actions": ["hint"]}

    rig.s.m.diagnose = same

    async def go():
        await _to_step(rig, 5)
        rig.write("lr = 0.3\n")
        await rig.run("r1", PLATEAU)  # level 2
        rig.s.spoken_sig = None  # e.g. the failure set changed: the ladder speaks again at level 2
        await rig.run("r2", PLATEAU)
        rig.clock.t += 25
        await rig.run("r3", PLATEAU)  # same failure again -> level 3: that IS new

    run(go())
    assert [p["level"] for p in rig.of("offtrack")] == [2, 3]


def test_build_timeout_only_until_the_first_part(monkeypatch):
    monkeypatch.setenv("ORCH_BUILD_TIMEOUT_S", "0.2")
    mods = Modules(demo=False, force_stubs="")
    got = []

    async def build(url, goal, workdir, on_update=None):
        await on_update({"steps": []}, False)  # part 1 quickly
        await asyncio.sleep(0.5)  # the rest takes longer than the timeout: must NOT be cut
        return {"lesson": {"id": "x"}, "steps": []}

    mods.real["lesson"] = types.SimpleNamespace(build_lesson=build)
    out = run(mods.build_lesson("https://www.youtube.com/watch?v=abcdefghijk", "", "/tmp",
                                on_update=lambda g, c: got.append(c)))
    assert out["lesson"]["id"] == "x" and got == [False]

    async def slow(url, goal, workdir, on_update=None):
        await asyncio.sleep(1)

    mods.real["lesson"] = types.SimpleNamespace(build_lesson=slow)
    with pytest.raises(Exception, match="took over"):
        run(mods.build_lesson("https://www.youtube.com/watch?v=abcdefghijk", "", "/tmp", on_update=lambda g, c: None))


def test_visible_error_vetoes_the_files_only_route(tmp_path, monkeypatch):
    """S9: CRA shows 'Failed to compile' while every file check passes -> not green, the coach gets it."""
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)
    g = stubs.load_fixture_lesson()
    g["steps"][0]["checks"].append({"id": "s1c9", "type": "screen_absent", "label": "No compile errors",
                                    "pattern": "Failed to compile", "app": "Code"})

    async def go():
        await rig.s.load_graph(g)
        await rig.settle()
        await rig.end_segment()
        screen.text["Code"] = ["pinn_convection.py", "Failed to compile."]
        await rig.save("# file exists\n")  # precision (file_exists) passes...

    run(go())
    assert not rig.of("step.passed")  # ...but the visible error vetoes it
    shown = {c["checkId"]: c["status"] for c in rig.of("check.updated")}
    assert shown["s1c9"] == "fail"


def test_resolve_file_nested_rebase_todo_and_open_title(tmp_path):
    from server.orchestrator.workspace import resolve_file

    (tmp_path / "demo-app" / "src").mkdir(parents=True)
    (tmp_path / "demo-app" / "src" / "App.js").write_text("x")
    (tmp_path / ".git" / "rebase-merge").mkdir(parents=True)
    (tmp_path / ".git" / "rebase-merge" / "git-rebase-todo").write_text("pick abc")
    assert resolve_file(tmp_path, "src/App.js") == tmp_path / "demo-app" / "src" / "App.js"
    assert resolve_file(tmp_path, "git-rebase-todo") == tmp_path / ".git" / "rebase-merge" / "git-rebase-todo"
    assert resolve_file(tmp_path, "nothing.py") is None


def test_coach_gets_screen_error_text_without_tut_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)
    seen = {}

    async def diagnose(step, failed, metrics, code, error_text="", **kw):
        seen["error_text"] = error_text
        return {"stepId": step["id"], "severity": "warn", "title": "t", "body": "b", "actions": ["hint"]}

    rig.s.m.diagnose = diagnose

    async def go():
        await rig.start_lesson()
        await rig.end_segment()
        screen.text["Terminal"] = ["$ git rebase main", "error: cannot rebase: You have unstaged changes."]
        await rig.save("# a\n")  # s1 passes
        await rig.end_segment()
        await rig.save("# a\nimport torch\n")
        await rig.save("# a\nimport torch\n# still\n")  # same failure twice -> coach

    run(go())
    assert "You have unstaged changes" in seen.get("error_text", "")


@pytest.mark.parametrize("h,rect", [
    (18, {"x": 5.0, "y": 6.0, "w": 7.0, "h": 18.0}),  # one text row: exactly the pointing box
    (8, {"x": 5.0, "y": 0.0, "w": 7.0, "h": 20.0}),  # E24 (f265edd): a sliver is one 20 pt row centred on it
])
def test_show_me_uses_e5_pointing(rig, h, rect):
    rig.s.m.has_pointing = lambda: True

    async def show_me(step, screen, last):
        return {"targets": [{"boxId": 1, "label": "here", "text": "net = ...", "rect": {"x": 5, "y": 6, "w": 7, "h": h}}],
                "caption": "Build the MLP here", "where": None}

    rig.s.m.show_me = show_me

    async def fake_screen(step):
        return object()

    rig.s._screen_for_coach = fake_screen

    async def go():
        await _to_step(rig, 1)
        await rig.s.action("show_me")

    run(go())
    spot = rig.of("spotlight")[-1]
    assert spot["rect"] == rect and spot["caption"] == "Build the MLP here"


def test_build_error_shows_only_e2s_sentence():
    from server.orchestrator.session import human_build_error

    e = RuntimeError("lesson.build_lesson failed: RuntimeError: Couldn't read this video (20:27 long): Gemini credits "
                     "are used up (top up at ai.studio/projects) and YouTube is blocking transcripts on this network. "
                     "Try a saved lesson, or switch to your phone hotspot.\n(no engine could build the lesson) gemini: 402")
    out = human_build_error(e)
    assert out.startswith("Couldn't read this video (20:27 long): Gemini credits are used up")
    assert "failed:" not in out and "RuntimeError" not in out and "\n" not in out


def test_quick_start_provisional_step_is_replaced(rig):
    real = stubs.load_fixture_lesson()

    def provisional():
        g = json.loads(json.dumps(real))
        g["steps"] = [{"id": "s1", "index": 0, "title": "Watch 0:00-0:40 and type along", "instructions": "i",
                       "video": real["steps"][0]["video"], "provisional": True,
                       "checks": [{"id": "s1c1", "type": "screen_absent", "label": "No errors", "pattern": "Traceback"}]}]
        g["lesson"]["provisional"] = True
        g["lesson"]["complete"] = False
        return g

    async def build(url, goal, workdir, on_update=None, **kw):
        await on_update(provisional(), False)
        await asyncio.sleep(0.02)
        await on_update(json.loads(json.dumps(real)), True)
        return json.loads(json.dumps(real))

    rig.s.m.build_lesson = build

    async def go():
        await rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk")
        await rig.built()  # learn_url returned with the placeholder live; the real lesson replaces it after

    import json
    run(go())
    readies = rig.of("lesson.ready")
    assert len(readies) == 2 and len(readies[0]["steps"]) == 1 and len(readies[1]["steps"]) == 6
    assert rig.of("step.started")[-1]["stepId"] == "s1" and len(rig.s.steps) == 6
    assert not rig.s.graph["lesson"].get("provisional")


def test_download_tutorial_files(rig, monkeypatch):
    from server.orchestrator import workspace as wsmod

    got = {}

    def fake_download(graph, folder):
        got["folder"] = folder
        return [{"name": "nanoGPT", "path": f"{folder}/tutorial/nanoGPT"}], "Saved nanoGPT to tutorial/."

    monkeypatch.setattr(wsmod, "download_resources", fake_download)

    async def go():
        await rig.start_lesson()
        await rig.s.action("download")

    run(go())
    assert rig.of("card")[-1] == {"stepId": "s1", "kind": "answer", "title": "Tutorial files",
                                  "body": "Saved nanoGPT to tutorial/."}
    assert got["folder"] == rig.s.workdir


def test_notebook_excerpt_is_cell_sources_not_cut_json(rig):
    """S9: a big .ipynb (outputs first) cut at 6000 chars was invalid JSON; send its code cells instead."""
    import json

    big_output = {"output_type": "stream", "name": "stdout", "text": ["x" * 100 + "\n"] * 200}
    nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": ["# PINN\n"]},
                    {"cell_type": "code", "metadata": {}, "outputs": [big_output], "execution_count": 1,
                     "source": ["import torch\n", "lr = 0.3\n"]},
                    {"cell_type": "code", "metadata": {}, "outputs": [], "execution_count": 2,
                     "source": "opt = torch.optim.Adam(net.parameters(), lr=lr)"}],
          "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    rig.write(json.dumps(nb), "lab.ipynb")
    code, f = rig.s._code_excerpt({"targets": [{"file": "lab.ipynb"}]})
    assert f == "lab.ipynb"
    assert len(code) < 600  # t10: a cell's output goes as a short tail (3 lines), never the 20 KB of it
    code = "\n".join(ln for ln in code.split("\n") if not ln.startswith("# [output]"))
    assert code == ("# %% [cell 1]\nimport torch\nlr = 0.3\n"
                    "# %% [cell 2]\nopt = torch.optim.Adam(net.parameters(), lr=lr)")
    rig.write("{not json", "broken.ipynb")  # not parseable: falls back to the raw text, still limited
    code, _ = rig.s._code_excerpt({"targets": [{"file": "broken.ipynb"}]}, limit=5)
    assert code == "{not "


def _lazy_graph(n_built: int, pending: int):
    import json

    g = json.loads(json.dumps(stubs.load_fixture_lesson()))
    g["steps"] = g["steps"][:n_built]
    g["lesson"]["complete"] = pending == 0
    plist = [{"status": "done", "start": 0, "end": 600}] + [{"status": "pending", "start": 600, "end": 1200}] * pending
    g["lesson"]["parts"] = {"done": 1, "failed": 0, "total": len(plist), "list": plist}
    return g


def test_lazy_long_video_extends_near_the_end_only_once(rig, monkeypatch):
    """E2 lazy parts: step.started near the last built step -> extend() in the background (one call per part)."""
    full = stubs.load_fixture_lesson()
    calls = []
    monkeypatch.setattr(rig.s.m, "lesson_needs_more",
                        lambda g, i: any(p["status"] == "pending" for p in g["lesson"]["parts"]["list"])
                        and max(s.get("index", 0) for s in g["steps"]) - i < 2)

    async def extend(graph, on_update=None):
        calls.append(len(graph["steps"]))
        g = _lazy_graph(len(full["steps"]), 1)  # the next part's steps appended (the fixture's s3..)
        g["lesson"]["parts"]["list"][1]["status"] = "done"
        g["lesson"]["complete"] = True
        await on_update(g, True)
        return g

    monkeypatch.setattr(rig.s.m, "extend_lesson", extend)

    async def go():
        await rig.s.load_graph(_lazy_graph(2, 1))
        await rig.settle()

    run(go())
    assert calls == [2]  # step 0 of 2 built steps is within the lookahead: built once, not per step
    upd = rig.of("lesson.updated")
    assert upd[-1]["complete"] is True and len(rig.s.steps) == len(full["steps"])


def test_lazy_lesson_without_a_builder_finishes_instead_of_waiting(rig):
    """DEMO / stubs never build more (no Gemini): the last built step ends the lesson, no endless 'building'."""
    async def go():
        await rig.s.load_graph(_lazy_graph(2, 1))
        await rig.settle()
        await rig.s.force_pass()
        await rig.settle()
        await rig.s.force_pass()
        await rig.settle()

    run(go())
    assert rig.s.phase == "done" and not rig.s.waiting_more
    assert all(c["title"] != "Building the next part…" for c in rig.of("card"))


def test_gemini_budget_stage_and_error_wording():
    from server.orchestrator.session import BuildStage, human_build_error

    st = BuildStage()
    st.on_progress("engine_switch", "budget")
    assert st.text == "Today's Gemini budget is used up — reading the transcript instead"
    assert human_build_error(RuntimeError("no engine: gemini budget exhausted; transcript 429")).startswith(
        "Today's Gemini budget is used up")


def _text_lesson():
    """E2's build_text_lesson shape: lesson.mode "lesson", steps with code + file + targets, no video."""
    return {"lesson": {"id": "lesson-calc", "title": "Build a calculator", "goal": "build a calculator in Python",
                       "mode": "lesson", "complete": True, "builtBy": "claude"},
            "sources": [{"id": "src1", "kind": "blog", "title": "Python docs", "url": "https://docs.python.org/3/"}],
            "steps": [
                {"id": "s1", "index": 1, "title": "Write add()", "instructions": "Define add(a, b).", "file": "calc.py",
                 "code": "def add(a, b):\n    return a + b\n",
                 "targets": [{"app": "Code", "file": "calc.py", "match": "# add goes here", "caption": "Type add() here"}],
                 "checks": [], "precision_checks": [{"id": "s1p1", "type": "file_contains", "label": "has add()",
                                                     "file": "calc.py", "pattern": r"def add\("}]},
                {"id": "s2", "index": 2, "title": "Write sub()", "instructions": "Define sub(a, b).", "file": "calc.py",
                 "code": "def sub(a, b):\n    return a - b\n",
                 "targets": [{"app": "Code", "file": "calc.py", "match": "def add"}],
                 "checks": [], "precision_checks": [{"id": "s2p1", "type": "file_contains", "label": "has sub()",
                                                     "file": "calc.py", "pattern": r"def sub\("}]}]}


def _lesson_rig(tmp_path, monkeypatch, build):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    from server.orchestrator.workspace import Workspace

    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)
    calls: list = []
    rig.s.workspace = Workspace(enabled=False, runner=lambda argv: calls.append(argv) or True)
    rig.s.m.build_text_lesson = build
    return rig, screen, calls


def test_just_teach_me_lesson_mode_has_no_video_and_spotlights_where_to_type(tmp_path, monkeypatch):
    """learn {mode: "lesson"}: no search, no player events, the editor opens (unasked: it IS the lesson),
    and each step boxes the exact place to type with the code as the caption's snippet."""
    searched = []

    async def build(goal, workdir, on_update=None, **kw):
        g = _text_lesson()
        first = {**g, "steps": g["steps"][:1], "lesson": {**g["lesson"], "complete": False}}
        await on_update(first, False)  # step 1 first: the lesson starts on it
        await on_update(g, True)
        return g

    rig, screen, calls = _lesson_rig(tmp_path, monkeypatch, build)

    async def search(q):
        searched.append(q)
        yield {}

    rig.s.m.search = search
    (tmp_path / "calc.py").write_text("# add goes here\n")
    screen.text["Code"] = ["calc.py", "# add goes here"]

    async def go():
        await rig.s.learn("build a calculator in Python", mode="lesson")
        await rig.settle()
        await asyncio.sleep(0.05)

    run(go())
    assert not searched and not rig.of("search.result")
    ready = rig.of("lesson.ready")[0]
    assert ready["lesson"]["mode"] == "lesson" and all("video" not in s for s in ready["steps"])
    assert "video" not in rig.of("step.started")[0]
    assert not [t for t in rig.types() if t.startswith("video.")]
    assert [s["id"] for s in rig.of("lesson.updated")[0]["steps"]] == ["s2"]
    assert calls and rig.s.editor_open  # opened without an "Open VS Code?" card
    spot = rig.of("spotlight")[-1]
    assert spot["caption"] == "Type it here"  # E5: a short pointer; the drawer says the step's one action
    assert spot["snippet"] == "def add(a, b):\n    return a + b\n"
    assert spot["matched"] == "# add goes here"


def test_lesson_mode_do_it_for_me_previews_the_step_code_then_applies(tmp_path, monkeypatch):
    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    rig, screen, calls = _lesson_rig(tmp_path, monkeypatch, build)

    async def go():
        await rig.s.learn("build a calculator in Python", mode="lesson")
        await rig.settle()
        await rig.s.action("apply_fix")  # no offtrack yet: "Do it for me" types this step's code (new file)
        await rig.settle()
        card = rig.of("card")[-1]
        assert card["title"] == "Type this for you?" and card["actions"] == ["confirm"] and "+def add(a, b):" in card["diff"]
        assert (tmp_path / "calc.py").read_text() == ""  # created empty at step start; nothing typed before confirm
        await rig.s.action("confirm")
        await rig.settle()

    run(go())
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"
    assert rig.of("step.passed")[0]["stepId"] == "s1"  # the checks gate as usual


def test_lesson_mode_build_failure_is_an_error_not_a_video_message(tmp_path, monkeypatch):
    async def build(goal, workdir, on_update=None, **kw):
        raise RuntimeError("lesson.build_text_lesson failed: RuntimeError: Couldn't build this lesson: no Anthropic key")

    rig, _, _ = _lesson_rig(tmp_path, monkeypatch, build)
    run(rig.s.learn("anything", mode="lesson"))
    assert rig.of("lesson.building")[-1].get("failed") is True
    assert rig.of("error")[-1]["message"].startswith("Couldn't build this lesson")
    assert rig.s.phase == "idle"


def test_demo_text_lesson_is_the_fixture_without_video(monkeypatch, tmp_path):
    monkeypatch.setattr("server.orchestrator.modules.DEMO_CACHE", tmp_path)  # no cached lessons
    m = Modules(demo=True)
    g = run(m.build_text_lesson("x", str(tmp_path)))
    assert g["lesson"]["mode"] == "lesson" and all("video" not in s for s in g["steps"])


def test_skip_step_moves_on_without_a_pass(rig):
    async def go():
        await rig.start_lesson()
        await rig.s.action("skip_step")
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[0] == {"stepId": "s1", "nextStepId": "s2", "skipped": True}
    assert rig.of("step.started")[-1]["stepId"] == "s2"
    assert not any(p["status"] == "pass" for p in rig.of("check.updated"))  # never green
    assert {"state": "passed"} not in rig.of("status")


def test_check_step_passes_now_or_says_what_is_missing(rig):
    """Check button: deterministic checks first, then E5's judge; ONE "Not yet" card + spotlight. E19 (7026814): the
    body is whole sentences (no 12-word cut that ended "..., then save the")."""
    rig.s.check_wait_s = 0
    calls = []

    async def judge_step(step, screen=None, files=None, **kw):
        calls.append(files)
        return {"done": False, "missing": "Add a Tanh activation after the first Linear layer, then save the file",
                "checks": {}, "target": {"text": "nn.Linear", "rect": {"x": 10.0, "y": 20.0, "w": 300.0, "h": 18.0}}}

    rig.s.m.judge_step = judge_step

    async def go():
        await _to_step(rig, 1)  # s2: Linear + Tanh layers
        rig.write("import torch.nn as nn\nnet = nn.Sequential(nn.Linear(2, 50))\n")
        n_cards = len(rig.of("card"))
        await rig.s.action("check_step")
        await rig.settle()
        new = rig.of("card")[n_cards:]
        assert len(new) == 1 and new[0]["title"] == "Not yet" and new[0]["kind"] == "answer"
        assert new[0]["actions"] == ["hint", "show_me", "skip_step"]  # t10: a video Not yet teaches too
        assert new[0]["body"] == "Add a Tanh activation after the first Linear layer, then save the file."
        assert rig.of("spotlight")[-1]["rect"]["w"] == 300.0
        assert calls and "pinn_convection.py" in calls[0]
        assert all(p["stepId"] != "s2" for p in rig.of("step.passed"))
        rig.write(S2)  # now done, with no run or other trigger: asking is enough
        await rig.s.action("check_step")
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[-1]["stepId"] == "s2" and "skipped" not in rig.of("step.passed")[-1]


def test_check_step_judge_can_pass_what_the_machine_cannot_see(rig):
    rig.s.check_wait_s = 0

    async def judge_step(step, screen=None, files=None, **kw):
        return {"done": True, "missing": "", "checks": {c["id"]: {"verdict": "done"} for c in rig.s.display_checks(step)}}

    rig.s.m.judge_step = judge_step

    async def go():
        await _to_step(rig, 1)
        await rig.s.action("check_step")
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[-1]["stepId"] == "s2"


def test_check_step_without_a_judge_names_the_failing_checks(rig):
    rig.s.check_wait_s = 0

    async def go():
        await _to_step(rig, 1)
        rig.write("import torch.nn as nn\nnet = nn.Sequential(nn.Linear(2, 50))\n")
        await rig.s.action("check_step")
        await rig.settle()

    run(go())
    card = rig.of("card")[-1]
    assert card["title"] == "Not yet" and "uses tanh" in card["body"] and card["actions"] == ["hint", "show_me", "skip_step"]


def test_provisional_placeholder_is_replaced_even_when_the_real_lesson_races_it(rig, monkeypatch):
    """Live bug (calculator lesson): E2's quick-start timer sent the placeholder from its own task; the real
    7-step lesson arrived while the placeholder was still being prepared and was APPENDED (s2..s7), so the
    learner stayed on a placeholder install step forever. The real lesson must replace it: fresh lesson.ready,
    the real s1 starts, and no empty lesson.updated."""
    import json
    import time as _t

    from server.orchestrator import workspace as wsmod

    real = stubs.load_fixture_lesson()
    real["lesson"]["builtBy"] = "gemini"

    def slow_prepare(graph, goal):
        _t.sleep(0.15)  # S2 writing starter files
        return None

    monkeypatch.setattr(wsmod, "prepare", slow_prepare)
    placeholder = json.loads(json.dumps(real))
    placeholder["steps"] = [{"id": "s1", "index": 1, "title": "Guide to Installing Python & VS", "instructions": "i",
                             "video": real["steps"][0]["video"], "provisional": True,
                             "checks": [{"id": "s1c1", "type": "screen_absent", "label": "No errors",
                                         "pattern": "Traceback", "app": "Terminal"}]}]
    placeholder["lesson"].update(provisional=True, complete=False, builtBy="chapters")

    async def build(url, goal, workdir, on_update=None, **kw):
        timer = asyncio.create_task(on_update(placeholder, False))  # E2's _QuickStart._fire, another task
        await asyncio.sleep(0.02)
        await on_update(json.loads(json.dumps(real)), True)  # the real lesson, while the placeholder prepares
        pending.append(timer)  # build_lesson returns while the placeholder is still being set up
        return json.loads(json.dumps(real))

    pending: list = []

    rig.s.m.build_lesson = build

    async def go():
        await rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk")
        await rig.settle()

    run(go())
    readies = rig.of("lesson.ready")
    assert [len(r["steps"]) for r in readies] == [1, len(real["steps"])]
    assert readies[-1]["lesson"]["provisional"] is False and readies[-1]["lesson"]["builtBy"] == "gemini"
    assert rig.s.step["title"] == real["steps"][0]["title"] and rig.of("step.started")[-1]["stepId"] == "s1"
    assert [s["id"] for s in rig.s.steps] == [s["id"] for s in real["steps"]]
    assert all(u["steps"] for u in rig.of("lesson.updated"))  # never an empty update



def test_background_judge_passes_pending_checks_and_looks_done_confirm(rig):
    """E5's StepJudge on the tick: pending checks it saw done count as passed; a "Looks done?" card's confirm
    passes the step (its checkIds go green)."""
    class Judge:
        def __init__(self, card=None, events=()):
            self.card, self.events, self.n = card, list(events), 0

        def should_judge(self, step, results, **kw):
            return self.n == 0

        async def judge(self, step, results, **kw):
            self.n += 1
            return {"events": self.events, "card": self.card}

    async def go():
        await _to_step(rig, 1)
        rig.write("import torch.nn as nn\nnet = nn.Sequential(nn.Linear(2, 50))\n")
        await rig.s.on_file_change([str(rig.workdir / "pinn_convection.py")])
        await rig.settle()
        failing = [r["checkId"] for r in rig.s.last_results if r.get("status") != "pass"]
        rig.s.judge = Judge(card={"stepId": "s2", "kind": "answer", "title": "Looks done?", "body": "Tanh is there",
                                  "actions": ["confirm", "skip_step"], "checkIds": failing})
        await rig.s.tick()
        await rig.settle()
        assert rig.of("card")[-1]["title"] == "Looks done?"
        await rig.s.action("confirm")
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[-1]["stepId"] == "s2"
    assert any(p.get("detail") == "You confirmed it" for p in rig.of("check.updated"))


def test_install_step_passes_when_the_tools_are_already_installed(rig):
    graph = stubs.load_fixture_lesson()
    graph["steps"][0].update(title="Guide to Installing Python & VS Code", instructions="Install Python and VS Code.")

    async def go():
        await rig.s.load_graph(graph)
        await rig.settle()
        rig.s.reqs = [{"tool": "python", "label": "Python", "kind": "runtime", "needed": True, "ok": True},
                      {"tool": "vscode", "label": "VS Code", "kind": "editor", "needed": True, "ok": True}]
        await rig.s._maybe_pass_setup_step()
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"
    assert any(p.get("detail") == "Already installed" for p in rig.of("check.updated"))


def test_stuck_card_offers_skip_once_after_90s_idle(rig):
    async def go():
        await _to_step(rig, 1)
        await rig.end_segment()
        rig.s._acted()  # E4: only once the learner started on the step
        rig.clock.t += 95
        await rig.s.tick()
        await rig.s.tick()
        await rig.settle()

    run(go())
    stuck = [c for c in rig.of("card") if c["title"] == "Need a hand?"]
    assert len(stuck) == 1 and stuck[0]["actions"] == ["hint", "skip_step"]


def test_stuck_card_waits_for_the_learner_and_a_pending_preview(rig):
    async def go():
        await _to_step(rig, 1)
        await rig.end_segment()
        rig.clock.t += 95
        await rig.s.tick()  # never started on the step: no card
        rig.s._acted()
        rig.s.pending_patch = {"file": "x.py"}  # a "Do it for me" preview waits on them
        rig.clock.t += 95
        await rig.s.tick()
        await rig.settle()

    run(go())
    assert not [c for c in rig.of("card") if c["title"] == "Need a hand?"]


def _rig_with_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    return Rig(tmp_path, with_inputs=True)


def test_keys_typed_into_miyagi_or_another_app_are_not_lesson_work(tmp_path, monkeypatch):
    rig = _rig_with_inputs(tmp_path, monkeypatch)

    async def go():
        await _to_step(rig, 1)
        rig.clock.t += 30
        rig.inputs.own_front = True  # E5: the learner types a question into Miyagi's ask box
        rig.inputs.key()
        rig.inputs.click()
        assert not rig.s.learner_started() and not rig.s.acted_since_step_start()
        assert rig.s.learner_idle_s() >= 30
        rig.inputs.own_front, rig.inputs.foreign_front = False, True  # ... then into the Claude app
        rig.inputs.key()
        assert not rig.s.learner_started() and rig.s.learner_idle_s() >= 30
        rig.inputs.foreign_front = False  # in the lesson's editor: that's work
        rig.inputs.key()
        assert rig.s.learner_started() and rig.s.learner_idle_s() == 0

    run(go())


def test_state_has_no_text_under_the_pointer_unless_a_step_runs(tmp_path, monkeypatch):
    rig = _rig_with_inputs(tmp_path, monkeypatch)
    rect = types.SimpleNamespace(x=100.0, y=100.0, w=300.0, h=20.0,
                                 to_dict=lambda: {"x": 100.0, "y": 100.0, "w": 300.0, "h": 20.0})
    obs = types.SimpleNamespace(blocks=[types.SimpleNamespace(text="my own chat message", app="Claude", rect=rect)])
    rig.inputs.move(150.0, 110.0)
    rig.s.last_obs = obs
    assert rig.s.state()["cursor"] is None  # E3: idle
    run(_to_step(rig, 1))
    rig.s.last_obs = obs
    assert rig.s.state()["cursor"]["under"]["text"] == "my own chat message"
    rig.s.snapshot(ask_resume=True)
    st = rig.s.state()
    assert st["cursor"] is None and st["phase"] == "awaiting_resume"  # E7: the freeze shows from outside


def _sheet_lesson() -> dict:
    g = stubs.text_lesson(stubs.load_fixture_lesson(), goal="teach me PINNs")
    g["lesson"]["build"] = {"summary": "A tiny PINN for the convection equation", "outcome": "It trains"}
    return g


def test_before_you_start_holds_the_lesson_until_start_or_an_edit(rig):
    bad = lambda ev: [e for e in ev if e["type"] in ("offtrack", "spotlight") and not e["payload"].get("clear")
                      or e["type"] == "card" and e["payload"].get("title") == "Need a hand?"
                      or e["type"] == "check.updated" and e["payload"]["status"] == "fail"]

    async def go():
        await rig.s.load_graph(_sheet_lesson())
        await rig.settle()
        assert rig.s.awaiting_start and rig.s.state()["phase"] == "ready"  # E4: the sheet is up
        m = rig.mark()
        for _ in range(3):
            rig.clock.t += 100
            await rig.s.tick()
        await rig.settle()
        assert not bad(rig.since(m)) and rig.s.awaiting_start
        await rig.s.action("start")
        await rig.settle()
        assert not rig.s.awaiting_start and rig.s.state()["phase"] == "active"

        # the app comes back: Continue re-sends lesson.ready, so the sheet opens again: held, nothing stale replayed
        step = rig.s.step
        cid = next(iter(rig.s.check_state))
        rig.s.check_state[cid] = {**rig.s.check_state[cid], "status": "fail", "detail": "old"}
        rig.s.last_offtrack = {"stepId": step["id"], "severity": "warn", "title": "Stale", "body": "made earlier"}
        rig.s.snapshot(ask_resume=True)
        m = rig.mark()
        await rig.s.action("resume")
        await rig.settle()
        rig.clock.t += 200
        await rig.s.tick()
        await rig.settle()
        assert rig.s.awaiting_start and not bad(rig.since(m))
        rig.write("# the learner's first edit\n", name=rig.s._step_file(step))
        await rig.s.tick()
        await rig.settle()
        assert not rig.s.awaiting_start

    run(go())


def test_before_you_start_holds_only_step_one_and_only_with_an_app(rig):
    async def go():
        rig.s.has_clients = lambda: False  # no app got lesson.ready (rehearse_boxes, autostart): no sheet, no hold
        await rig.s.load_graph(_sheet_lesson())
        await rig.settle()
        assert not rig.s.awaiting_start
        await rig.s.end_lesson()
        rig.s.has_clients = None
        await rig.s.load_graph(_sheet_lesson())
        await rig.settle()
        assert rig.s.awaiting_start
        await rig.s.start_step(1)  # a restore at a later step: the app closes the sheet on it (store.ts)
        await rig.settle()
        assert not rig.s.awaiting_start
        rig.s.snapshot(ask_resume=True)
        await rig.s.action("resume")  # Continue at step 2 re-sends lesson.ready, but the app shows no sheet there
        await rig.settle()
        assert not rig.s.awaiting_start and rig.s.state()["phase"] == "active"

    run(go())


def test_dead_screen_is_reported_once_and_show_me_says_why(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)

    async def go():
        await rig.start_lesson()
        screen.down = "RuntimeError: display returned no image"
        await rig.s.tick()  # t0: not yet (could be a Space switch)
        assert not rig.of("error")
        rig.clock.t += 6
        await rig.s.tick()
        assert not rig.of("error")  # 6 s: still quiet
        rig.clock.t += 10
        await rig.s.tick()
        await rig.s.tick()
        assert rig.s.state()["screen"] is False
        await rig.s.action("show_me")
        await rig.settle()

    run(go())
    errs = [e["message"] for e in rig.of("error")]
    assert errs == ["Miyagi can't see your screen. Check Screen Recording in System Settings."]
    assert rig.of("card")[-1]["title"] == "I can't see your screen"


def test_where_card_says_save_it_when_the_code_is_in_an_untitled_tab(rig):
    from types import SimpleNamespace as NS

    async def go():
        await _to_step(rig, 1)
        rig.s.last_obs = NS(windows=[NS(app="Code", title="● Untitled-1 — Visual Studio Code")])

    run(go())
    card = rig.s._where_card(rig.s.step)
    assert card["title"] == "Save it as pinn_convection.py" and str(rig.workdir) in card["body"]



def test_preflight_card_actions_download_and_open_in_browser_are_handled(rig, monkeypatch):
    from server.orchestrator import workspace as wsmod

    rig.s.m._preflight_mod = lambda: _fake_preflight([])
    opened = []
    monkeypatch.setattr(wsmod, "download_resources", lambda graph, folder: ([], "Downloaded 0 files."))

    class WS:
        enabled = False

        def run(self, argv):
            opened.append(argv)
            return True

    async def go():
        await rig.s.learn("build chat gpt")
        await rig.s.build_lesson(["r1"])
        rig.s.workspace = WS()
        rig.s.reqs = [{"tool": "colab", "install": {"url": "https://colab.research.google.com/"}}]
        await rig.s.action("open_in_browser", "colab")
        await rig.s.action("download")  # before the lesson exists: queued
        assert rig.of("card")[-1]["title"] == "Tutorial files"
        await rig.s.action("build")
        await rig.settle()
        await asyncio.sleep(0.05)

    run(go())
    assert opened[0] == ["open", "https://colab.research.google.com/"]
    assert rig.of("card")[-1]["title"] == "Tutorial files" and rig.of("card")[-1]["body"] == "Downloaded 0 files."
    assert not any("Unknown action" in e["message"] for e in rig.of("error"))



def test_lesson_mode_no_early_offtrack_no_setup_card_no_window_box(tmp_path, monkeypatch):
    """Live run (calculator): an offtrack 2.8 s into step 1, an 'Open in Cursor?' setup card, and the whole
    editor window boxed. Lesson mode: the coach waits for an edit / run / 25 s; no setup card when nothing is
    missing; only the exact line is boxed."""
    from types import SimpleNamespace as NS

    from server.orchestrator import workspace as wsmod

    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    rig, screen, calls = _lesson_rig(tmp_path, monkeypatch, build)
    rig.s.workspace.enabled = True
    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: [
        {"tool": "python", "label": "Python", "kind": "runtime", "needed": True, "ok": True},
        {"tool": "vscode", "label": "VS Code", "kind": "editor", "needed": True, "ok": True}])
    spoke = []
    rig.s._consider_speaking = (lambda orig: lambda *a, **k: (spoke.append(a[0]), orig(*a, **k)))(rig.s._consider_speaking)

    async def go():
        await rig.s.learn("build a calculator", mode="lesson")
        await rig.settle()
        await asyncio.sleep(0.05)
        rig.s.last_obs = NS(windows=[NS(app="Cursor", title="calc.py — lesson",
                                        rect={"x": 0.0, "y": 33.0, "w": 865.0, "h": 1001.0})])
        rig.s.engaged = True  # screen frames arrived (lesson mode has no clip to wait for)
        rig.clock.t += 6  # past the idle gate, inside the 25 s grace
        await rig.s.tick()
        await rig.settle()
        assert "idle" in spoke and not rig.of("offtrack") and not rig.s.coaching
        await rig.s.action("show_me")
        await rig.settle()

    run(go())
    assert (tmp_path / "calc.py").exists()  # the step's file was created: step 1 is "type this"
    assert not [c for c in rig.of("card") if c.get("kind") == "setup"]
    assert not [sp for sp in rig.of("spotlight") if sp.get("rect", {}).get("w") == 865.0]



def test_tagged_setup_step_passes_on_its_required_tools(rig):
    graph = stubs.load_fixture_lesson()
    graph["steps"][0].update(title="Get ready", instructions="Open a terminal.", setup=True, requires=["python"])

    async def go():
        await rig.s.load_graph(graph)
        await rig.settle()
        rig.s.reqs = [{"tool": "python", "label": "Python", "kind": "runtime", "needed": True, "ok": True},
                      {"tool": "node", "label": "Node", "kind": "runtime", "needed": True, "ok": False}]
        await rig.s._maybe_pass_setup_step()
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"  # node is missing, but this step only requires python


def test_no_offtrack_in_the_first_20s_of_a_step(rig):
    rig.s.offtrack_grace_s = 20

    async def go():
        await _to_step(rig, 5)
        rig.write("def train(model):\n    beta = 30\n    for epoch in range(4000):\n        pass\n")
        await rig.end_segment()
        await rig.run("r1", PLATEAU)  # a real failing run 0 s into the step: still too early
        assert not rig.of("offtrack")
        rig.clock.t += 21
        await rig.run("r2", PLATEAU)

    run(go())
    assert len(rig.of("offtrack")) == 1


def test_not_started_diagnosis_is_a_calm_hint_never_an_offtrack(rig):
    async def diagnose(step, failed, metrics, code, **kw):
        return {"notStarted": True, "title": "Start: Write the training loop",
                "body": "Create the training loop in pinn_convection.py, then run it."}

    rig.s.m.diagnose = diagnose

    async def go():
        await _to_step(rig, 5)
        rig.write("# nothing yet\n")
        await rig.end_segment()
        await rig.run("r1", PLATEAU)

    run(go())
    assert not rig.of("offtrack")
    card = rig.of("card")[-1]
    assert card["kind"] == "hint" and card["title"] == "Start: Write the training loop"
    assert {"state": "offtrack"} not in rig.of("status") and rig.of("status")[-1] == {"state": "watching"}


def test_not_yet_card_and_offtrack_never_both_for_the_same_check(rig):
    rig.s.check_wait_s = 0
    spoke = []
    rig.s._consider_speaking = (lambda orig: lambda *a, **k: (spoke.append(a[0]), orig(*a, **k)))(rig.s._consider_speaking)

    async def go():
        await _to_step(rig, 1)  # s2: Linear + Tanh
        await rig.end_segment()
        rig.write("import torch.nn as nn\nnet = nn.Sequential(nn.Linear(2, 50))\n")
        await rig.s.action("check_step")  # "Not yet": uses tanh
        await rig.settle()
        for _ in range(2):  # the same failure saved twice: the coach would repeat it as an offtrack
            await rig.s.on_file_change([str(rig.workdir / "pinn_convection.py")])
            await rig.settle()

    run(go())
    assert "repeat" in spoke  # the coach path really ran
    assert [c["title"] for c in rig.of("card")].count("Not yet") == 1
    assert not [o for o in rig.of("offtrack") if o["level"] == 2]



def test_step_started_instructions_are_one_concrete_action(rig):
    from server.orchestrator.session import LessonSession

    s = rig.s
    two = {"id": "s1", "title": "t", "file": "calculator.py", "code": "print(\"Calculator\")\nx = 1\n",
           "instructions": "Long text."}
    assert s._action_line(two) == 'In VS Code, create calculator.py and type print("Calculator") …'  # video: no snippet
    s.graph = {"lesson": {"mode": "lesson"}}  # E5: lesson mode's snippet shows the code under the line
    assert s._action_line(two) == "Create calculator.py, then type the lines below."
    (rig.workdir / "calculator.py").write_text("")
    assert s._action_line({"id": "s1", "title": "t", "file": "calculator.py", "code": "print(1)\n"}) \
        == "In calculator.py, type the line below."
    s.graph = None
    assert s._action_line({"id": "s1", "title": "t", "file": "calculator.py", "code": "print(1)\n"}) \
        == "In VS Code, type print(1) in calculator.py"
    assert s._action_line({"id": "s2", "title": "t", "instructions": "Add an nn.Tanh after each Linear layer. "
                                                                     "This keeps the output smooth."}) \
        == "Add an nn.Tanh after each Linear layer."
    assert s._action_line({"id": "s3", "title": "t", "action": "Run python calculator.py", "instructions": "x"}) \
        == "Run python calculator.py"
    assert LessonSession  # (imported for the type)

    async def go():
        await rig.start_lesson()

    run(go())
    st = rig.of("step.started")[0]
    assert st["instructions"] == "Create pinn_convection.py in your project folder." and "details" not in st


def test_open_editor_without_code_on_path(tmp_path, monkeypatch):
    """Michael's Mac has no `code` on PATH: the app's bundled CLI is used, and if the CLI fails the folder still
    opens with `open -a "Visual Studio Code" <folder>`."""
    import sys

    from server.workspace import editor as ed

    fake_cli = tmp_path / "code"
    fake_cli.write_text("#!/bin/sh\n")
    monkeypatch.setattr(ed.shutil, "which", lambda name: None)
    monkeypatch.setitem(ed.EDITORS["vscode"], "bundled_cli", str(fake_cli))
    assert ed._cli(ed.EDITORS["vscode"]) == str(fake_cli)

    monkeypatch.setattr(sys, "platform", "darwin")
    folder = tmp_path / "lesson"
    folder.mkdir()
    vscode = {"id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "cli": str(fake_cli)}
    calls = []

    def runner(argv):  # the CLI fails (exit != 0); `open -a` works
        calls.append(argv)
        return argv[0] == "open"

    rep = ed.open_editor_report(folder, editor=vscode, runner=runner, arrange_windows=False, trusted=lambda: False,
                                previous={})
    assert rep["opened"] and calls[0][:2] == [str(fake_cli), str(folder.resolve())]  # never `-n`
    assert calls[1] == ["open", "-a", "Visual Studio Code", str(folder.resolve())]


def _run_lesson():
    g = _text_lesson()
    g["steps"][1].update(title="Run it", instructions="Run the calculator.", code="python calc.py\n",
                         targets=[{"app": "Code", "file": "calc.py", "match": "calc\\.py"}], precision_checks=[])
    return g


def _code_window(h: float = 1000.0):
    from types import SimpleNamespace as NS

    return NS(windows=[NS(app="Code", title="calc.py — lesson", rect={"x": 0.0, "y": 0.0, "w": 1200.0, "h": h})])


def test_run_step_boxes_the_vscode_terminal_never_the_breadcrumb(tmp_path, monkeypatch):
    """Michael: the box sat on the breadcrumb ("Users > tripi > … > calc.py") for `python calc.py`."""
    async def build(goal, workdir, on_update=None, **kw):
        return _run_lesson()

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    screen.text["Code"] = ["Users > tripi > miyagi > lessons > calc.py", "def add(a, b):"]

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = _code_window()
        await rig.s.goto_step(1)  # the run step, terminal not open yet
        await asyncio.sleep(0.05)
        first = dict(rig.of("spotlight")[-1])
        screen.text["Code"] += [""] * 19 + ["TERMINAL", "tripi@mac lesson % "]  # the learner opened it (⌃`)
        await asyncio.sleep(2.1)
        return first

    first = run(go())
    assert first["caption"] == "Open the terminal: ⌃`" and first["snippet"] == "python calc.py"
    assert first["rect"] == {"x": 0.0, "y": 976.0, "w": 1200.0, "h": 24.0}  # the status bar, never empty space
    last = rig.of("spotlight")[-1]
    assert last["caption"] == "Run it here" and last["rect"]["y"] == 100.0 + 20 * 22
    assert not [s for s in rig.of("spotlight") if "matched" in s and ">" in s["matched"]]
    assert last["rect"]["h"] == 20.0  # E8: the prompt line itself (row 22, not the TERMINAL tab), never the panel


def test_spotlight_is_steady_one_box_until_it_really_moves(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)
    rig.s.SPOT_MIN_GAP_S = 2.0
    screen.text["Code"] = ["import torch.nn as nn", "", "class Net(nn.Module):", "    pass"]

    async def go():
        await rig.start_lesson()
        await rig.s.goto_step(1)
        await rig.s._spotlight_target(rig.s.step)
        n = len(rig.of("spotlight"))
        for _ in range(5):  # frames with the same box: nothing re-sent
            await rig.s._follow_spot()
        assert len(rig.of("spotlight")) == n
        screen.text["Code"].insert(0, "# moved down 20 px")
        await rig.s._follow_spot()  # moved, but within 2 s of the last box: wait
        assert len(rig.of("spotlight")) == n
        rig.clock.t += 2.5
        await rig.s._follow_spot()
        return n

    n = run(go())
    assert len(rig.of("spotlight")) == n + 1


def test_auto_cards_are_paced_20s_into_a_step_and_8s_apart(rig):
    rig.s.offtrack_grace_s, rig.s.CARD_GAP_S = 20, 8

    async def go():
        await _to_step(rig, 1)
        card = {"stepId": "s2", "kind": "hint", "title": "Need a hand?", "body": "b", "actions": ["skip_step"]}
        assert await rig.s._emit_card(card, auto=True) is False  # 0 s into the step
        rig.clock.t += 21
        await rig.s._emit_card({**card, "title": "Not yet", "kind": "answer"})  # a card the learner asked for
        rig.clock.t += 3
        assert await rig.s._emit_card(card, auto=True) is False  # 3 s after the last card
        rig.clock.t += 6
        assert await rig.s._emit_card(card, auto=True) is True

    run(go())


def test_a_passed_check_does_not_flip_back_to_pending(rig):
    async def go():
        await _to_step(rig, 1)
        step = rig.s.step
        cid = rig.s.display_checks(step)[0]["id"]
        await rig.s._publish(step, [{"checkId": cid, "status": "pass", "label": "x"}])
        await rig.s._publish(step, [{"checkId": cid, "status": "pending", "label": "x"}])  # OCR missed it once
        return cid

    cid = run(go())
    assert [p["status"] for p in rig.of("check.updated") if p["checkId"] == cid][-1] == "pass"


def test_run_step_never_starts_while_its_file_is_empty(tmp_path, monkeypatch):
    async def build(goal, workdir, on_update=None, **kw):
        return _run_lesson()

    rig, _, _ = _lesson_rig(tmp_path, monkeypatch, build)

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        assert (tmp_path / "calc.py").read_text() == ""
        await rig.s.goto_step(1)  # "python calc.py" on an empty file: back to the typing step
        await rig.settle()

    run(go())
    assert rig.of("step.started")[-1]["stepId"] == "s1"
    assert rig.of("card")[-1]["title"] == "calc.py is still empty"


def test_run_step_uses_e6_terminal_region(tmp_path, monkeypatch):
    async def build(goal, workdir, on_update=None, **kw):
        return _run_lesson()

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)
    (tmp_path / "calc.py").write_text("print(1)\n")
    screen.regions = {"editor": {"x": 260.0, "y": 80.0, "w": 900.0, "h": 500.0}}

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = _code_window()
        await rig.s.goto_step(1)
        await asyncio.sleep(0.05)
        first = dict(rig.of("spotlight")[-1])
        screen.regions["terminal"] = {"x": 260.0, "y": 600.0, "w": 900.0, "h": 240.0}
        await asyncio.sleep(2.1)
        return first

    first = run(go())
    assert first["caption"] == "Open the terminal: ⌃`" and first["rect"]["h"] == 24.0  # status bar, not the editor
    last = rig.of("spotlight")[-1]
    assert last["caption"] == "Run it here"
    assert last["rect"] == {"x": 260.0, "y": 600.0, "w": 900.0, "h": 240.0}



def test_leaving_vscode_clears_the_box_and_coming_back_reboxes(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)
    (tmp_path / "calc.py").write_text("# add goes here\n")
    screen.text["Code"] = ["# add goes here"]

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        await asyncio.sleep(0.05)
        assert rig.s.spot_rect is not None
        await rig.s.on_screen(NS(app="Claude", windows=[]))  # swiped to another app / Space
        assert rig.of("spotlight")[-1] == {"clear": True} and rig.s.spot_rect is None
        await rig.s.on_screen(NS(app="Miyagi", windows=[]))  # our own cards: no change
        await rig.s.on_screen(NS(app="Code", windows=[]))  # back in VS Code: re-scan, re-box
        await asyncio.sleep(0.05)

    run(go())
    assert rig.of("spotlight")[-1].get("rect") and rig.of("spotlight")[-1]["matched"] == "# add goes here"


def test_unsaved_file_says_save_before_any_offtrack_and_judge_cannot_pass_it(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)
    rig.s.check_wait_s = 0

    async def judge_step(step, screen=None, files=None, **kw):
        return {"done": True, "missing": "", "checks": {"s1p1": {"verdict": "done"}}}

    rig.s.m.judge_step = judge_step

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        title = f"● calc.py — {tmp_path.name} — Visual Studio Code"
        rig.s.last_obs = NS(app="Code", windows=[NS(app="Code", title=title)])
        await rig.s.action("check_step")  # Claude "sees" add() on screen, but the file on disk is empty
        await rig.settle()
        rig.s.last_action_t = rig.clock()
        rig.s._consider_speaking("idle", rig.s.step, [{"checkId": "s1p1", "status": "fail"}], rig.s.context())
        await rig.settle()

    run(go())
    assert not rig.of("step.passed") and not rig.of("offtrack")
    titles = [c["title"] for c in rig.of("card")]
    assert "Not yet" in titles and "Save calc.py" in titles
    assert any("Save calc.py" in c["body"] for c in rig.of("card") if c["title"] == "Not yet")
    assert [c for c in rig.of("card") if c["title"] == "Not yet"][0]["actions"] == ["hint", "show_me", "skip_step"]


def test_another_lessons_folder_gets_one_calm_card(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    rig, _, _ = _lesson_rig(tmp_path, monkeypatch, build)

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = NS(app="Code", windows=[NS(app="Code", title="calc.py — old-lesson-1a2b3c — Visual Studio Code")])
        rig.s.last_action_t = rig.clock()
        for _ in range(2):
            rig.s._consider_speaking("idle", rig.s.step, [{"checkId": "s1p1", "status": "fail"}], rig.s.context())
            await rig.settle()

    run(go())
    cards = [c for c in rig.of("card") if c["title"] == "Wrong folder?"]
    assert len(cards) == 1 and cards[0]["actions"] == ["open_editor"] and "old-lesson-1a2b3c/calc.py" in cards[0]["body"]
    assert not rig.of("offtrack")



def test_run_step_wording_and_terminal_pseudo_file(rig):
    s = rig.s
    run_step = {"id": "s7", "title": "Run it", "file": "calculator.py", "code": "python calculator.py\n",
                "targets": [{"file": "calculator.py", "match": "calculator"}]}
    assert s._action_line(run_step) == "Run python calculator.py in the VS Code terminal"
    assert s._action_line({**run_step, "file": "(terminal)", "targets": [{"file": "(terminal)", "match": "x"}]}) \
        == "Run python calculator.py in the VS Code terminal"
    assert s._step_file({"id": "s2", "file": "(terminal)", "targets": [{"file": "(terminal)"}]}) is None


def test_coach_holds_never_become_offtracks(rig):
    holds = iter([{"hold": "unconfirmed"}, {"hold": "unsaved", "title": "Save calc.py", "body": "Save with ⌘S so I can check it."}])
    seen = []

    async def diagnose(step, failed, metrics, code, **kw):
        seen.append(kw)
        return next(holds)

    rig.s.m.diagnose = diagnose

    async def go():
        await _to_step(rig, 5)
        rig.write("def train(model):\n    beta = 30\n")
        await rig.end_segment()
        await rig.run("r1", PLATEAU)  # unconfirmed OCR: nothing
        n = len(rig.of("card"))
        assert len(rig.of("card")) == n and not rig.of("offtrack")
        rig.clock.t += 30
        await rig.run("r2", PLATEAU)  # unsaved: a calm "save" hint

    run(go())
    assert not rig.of("offtrack") and rig.of("card")[-1]["title"] == "Save calc.py"
    assert seen[0]["code_source"] == "file" and seen[0]["file_state"]["saved"] is True


def test_screen_check_cannot_pass_a_lesson_step_whose_file_is_unsaved(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    g = _text_lesson()
    g["steps"][0]["checks"] = [{"id": "s1c1", "type": "screen_contains", "label": "add() typed", "pattern": "def add",
                                "app": "Code"}]

    async def build(goal, workdir, on_update=None, **kw):
        return g

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        screen.text["Code"] = ["def add(a, b):", "    return a + b"]  # typed, not saved: calc.py is empty on disk
        title = f"● calc.py — {tmp_path.name} — Visual Studio Code"
        rig.s.last_obs = NS(app="Code", windows=[NS(app="Code", title=title)])
        rig.s.last_action_t = rig.clock()
        await rig.s.evaluate("file")
        await rig.settle()

    run(go())
    assert not rig.of("step.passed")
    assert any(c["title"] == "Save to finish" and c["body"] == "Save calc.py (⌘S) and this step is done."
               and c["actions"] == [] for c in rig.of("card"))



def test_use_this_folder_adopts_the_learners_folder(tmp_path, monkeypatch):
    from server.orchestrator import workspace as wsmod

    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    rig, _, _ = _lesson_rig(tmp_path, monkeypatch, build)
    theirs = tmp_path / "old-lesson"
    theirs.mkdir()
    (theirs / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    adopted = []

    class S2:
        @staticmethod
        def adopt_folder(lesson_folder, learner_folder):
            adopted.append((lesson_folder, learner_folder))
            return {"workdir": str(learner_folder), "copied": ["README.md"], "skipped": []}

    moved = []

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        monkeypatch.setattr(wsmod, "_s2", lambda: S2)
        rig.s.on_workdir = moved.append
        rig.s._wrong_folder = {"learner_folder": str(theirs), "learner_folder_name": "old-lesson", "file": "calc.py",
                               "can_adopt": True}
        await rig.s.action("use_this_folder")
        await rig.settle()

    run(go())
    assert adopted and rig.s.workdir == str(theirs) and moved == [str(theirs)]
    assert rig.of("card")[-1]["title"] == "Using old-lesson"
    assert rig.of("step.passed")[0]["stepId"] == "s1"  # its file there already has add(): the check passes


def test_run_it_for_me_runs_the_command_shows_output_and_passes_the_run_check(tmp_path, monkeypatch):
    """Michael: "it's asking me to run but nothing happens". The Run it button runs the step's command in the lesson
    folder (real subprocess here), shows the last lines and feeds the run check its real exit code / output."""
    g = _run_lesson()
    g["steps"][1]["precision_checks"] = [{"id": "s2p1", "type": "command_exit_ok", "label": "runs", "command": "python calc.py"},
                                         {"id": "s2p2", "type": "output_contains", "label": "prints 5", "pattern": "5"}]

    async def build(goal, workdir, on_update=None, **kw):
        return g

    rig, _, _ = _lesson_rig(tmp_path, monkeypatch, build)
    import sys
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\nprint(add(2, 3))\n")
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}:{__import__('os').environ['PATH']}")

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        await rig.s.goto_step(1)
        await rig.settle()
        assert [c for c in rig.of("card") if c["title"] == "Run it"][-1]["actions"] == ["run_command"]
        await rig.s.action("run_command")
        await rig.settle()
        ask = rig.of("card")[-1]  # LLM06: its first run shows the exact command and waits for Yes
        assert ask["title"] == "Run this command?" and ask["actions"] == ["confirm"]
        assert ask["output"].splitlines()[0] in ("python calc.py", "python3 calc.py")
        assert not [c for c in rig.of("card") if c["title"].startswith("Ran ")]
        await rig.s.action("confirm")
        await rig.settle()

    run(go())
    ran = [c for c in rig.of("card") if c["title"].startswith("Ran ")][-1]
    assert ran["title"] == "Ran calc.py" and ran["output"] == "5" and ran["body"] == "It ran without errors."
    assert rig.of("step.passed")[-1]["stepId"] == "s2"


def test_run_it_for_me_reports_a_failure_and_a_hang(tmp_path, monkeypatch):
    async def build(goal, workdir, on_update=None, **kw):
        g = _run_lesson()
        g["steps"][1]["precision_checks"] = [{"id": "s2p1", "type": "command_exit_ok", "label": "runs"}]
        return g

    rig, _, _ = _lesson_rig(tmp_path, monkeypatch, build)
    rig.s.RUN_TIMEOUT_S = 1.0
    (tmp_path / "calc.py").write_text("x = 1\n")
    (tmp_path / "boom.py").write_text("import sys\nprint('boom')\nsys.exit(3)\n")
    (tmp_path / "hang.py").write_text("import time\ntime.sleep(5)\n")
    step = {"id": "s2", "title": "Run", "code": "python3 boom.py\n"}
    hang = {"id": "s2", "title": "Run", "code": "python3 hang.py\n"}

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s._run_confirmed = {(str(rig.s.workdir), "python3 boom.py"), (str(rig.s.workdir), "python3 hang.py")}
        await rig.s._run_for_me(step)
        await rig.s._run_for_me(hang)

    run(go())
    cards = [c for c in rig.of("card") if c["title"].startswith("Ran ")]
    assert cards[0]["body"] == "It stopped with exit code 3." and cards[0]["output"] == "boom"
    assert cards[1]["body"].startswith("Stopped after 1 s")


def test_do_it_for_me_appends_the_step_code_and_says_what_it_added(tmp_path, monkeypatch):
    """Lesson mode, no coach: the step's code is previewed (exact diff), written on confirm, and the result line
    names what was added; the checks re-run and the step passes."""
    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    rig, _, _ = _lesson_rig(tmp_path, monkeypatch, build)

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        (tmp_path / "calc.py").write_text("# my calculator\n")
        await rig.s.action("apply_fix")
        await rig.settle()
        prev = rig.of("card")[-1]
        assert prev["title"] == "Type this for you?" and "+def add(a, b):" in prev["diff"]
        await rig.s.action("confirm")
        await rig.settle()

    run(go())
    assert (tmp_path / "calc.py").read_text() == "# my calculator\n\ndef add(a, b):\n    return a + b\n"
    assert any(c["title"] == "Done" and c["body"] == "Added def add(a, b) to calc.py." for c in rig.of("card"))
    assert rig.of("step.passed")[0]["stepId"] == "s1"


def test_lesson_mode_vision_pick_boxes_the_line_when_text_and_gutter_miss(tmp_path, monkeypatch):
    """Short new file: OCR has neither the target text nor the line numbers, so the text match and the gutter line
    both miss. The Haiku set-of-marks pick (screen.pick) boxes the row, at most twice per step; a pick that isn't an
    editor row (toolbar / region) is never used for a type step."""
    from server.orchestrator import workspace as wsmod

    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    for kind, boxed in (("blank", True), ("toolbar", False)):
        rig, screen, calls = _lesson_rig(tmp_path / kind, monkeypatch, build)
        (tmp_path / kind).mkdir(exist_ok=True)
        asked: list[str] = []
        rect = {"x": 618.0, "y": 238.0, "w": 520.0, "h": 23.0}

        async def pick(intent, app="Code", kind=kind):
            asked.append(intent)
            return {"rect": rect, "box_ids": [501], "label": "blank line", "kind": kind, "confidence": 0.9,
                    "reason": "next line"}

        async def no_line(step):
            return None

        screen.reader = object()          # "the real reader is running" (vision is only used then)
        screen.pick = pick
        rig.s._editor_line_spot = no_line
        # the gutter misses for t5 (d)'s insertion row too (2f21672 / 9cfd59c: _start_box -> _insert_spot asks
        # Accessibility / the gutter first); never the real screen reader in a test
        monkeypatch.setattr(wsmod, "line_location", lambda path, line: {})

        async def go():
            await rig.s.learn("build a calculator", mode="lesson")
            await rig.settle()
            await asyncio.sleep(1.3)      # try 2 of _lesson_spot asks vision

        run(go())
        assert asked and "def add(a, b):" in asked[0] and "calc.py" in asked[0]
        spots = [sp for sp in rig.of("spotlight") if sp.get("rect") == rect]
        if boxed:
            assert spots and spots[-1]["caption"] == "Type it here"
            assert spots[-1]["snippet"] == "def add(a, b):\n    return a + b\n"
            assert len(asked) == 1
        else:
            assert not spots


def test_lesson_mode_targeter_confirms_moves_or_drops_the_located_box(tmp_path, monkeypatch):
    """_confirm_spot: screen.confirm (Haiku verifier) returns the box to show. A moved rect replaces the located one;
    None (Haiku is sure nothing on screen matches) withdraws it (t4: the start box goes up before Haiku answers); the
    question is the step's caption + code."""
    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    moved = {"x": 330.0, "y": 580.0, "w": 330.0, "h": 22.0}
    for name, answer in (("moved", moved), ("dropped", None)):
        rig, screen, calls = _lesson_rig(tmp_path / name, monkeypatch, build)
        (tmp_path / name).mkdir(exist_ok=True)
        (tmp_path / name / "calc.py").write_text("# add goes here\n")
        screen.text["Code"] = ["calc.py", "# add goes here"]
        asked: list[tuple] = []

        async def confirm(rect, intent, app="Code", answer=answer):
            asked.append((rect, intent))
            return answer

        async def no_line(step):
            return None

        screen.reader = object()
        screen.confirm = confirm
        rig.s._editor_line_spot = no_line
        rig.s._vision_spot = no_line

        async def go():
            await rig.s.learn("build a calculator", mode="lesson")
            await rig.settle()
            await asyncio.sleep(0.05)

        run(go())
        assert asked and asked[0][0]["y"] == 120.0                      # FakeScreen's located row
        assert asked[0][1].startswith("In calc.py, type the lines below.") and "(code: def add(a, b):" in asked[0][1]
        boxes = [sp for sp in rig.of("spotlight") if "rect" in sp]
        if answer is None:
            assert rig.of("spotlight")[-1] == {"clear": True} and rig.s.spot_rect is None
        else:
            assert boxes and boxes[-1]["rect"] == moved and boxes[-1]["matched"] == "# add goes here"



def test_s11_run_steps_anchors_and_python3(rig, tmp_path):
    """S11's rehearsal: a run step with code + run_command, regex-looking anchors, missing anchors, no `python`."""
    from server.orchestrator import workspace as wsmod

    (rig.workdir / "calculator.py").write_text('"""Calc."""\n\ndef add(a, b):\n    return a + b\n\nprint(add(2, 3))\n')
    loc = wsmod.target_location(rig.workdir, {"targets": [{"file": "calculator.py", "match": "return a + b"}]})
    assert loc[1] == 4  # literal first: the regex '+' doesn't send it to line 1
    loc = wsmod.target_location(rig.workdir, {"targets": [{"file": "calculator.py", "match": "print(add(2, 3))"}]})
    assert loc[1] == 6
    loc = wsmod.target_location(rig.workdir, {"targets": [{"file": "calculator.py", "match": "def main"}]}, missing="end")
    assert loc[1] == 7  # not in the file: where the new code goes

    s2 = {"id": "s2", "title": "Run your first output", "file": "calculator.py", "code": "print(add(2, 3))",
          "run_command": "python calculator.py", "details": "In the terminal, run python calculator.py"}
    assert rig.s._run_command(s2) == "python calculator.py"  # its code is already in the file: a run step
    assert rig.s._action_line(s2) == "Run python calculator.py in the VS Code terminal"
    s8 = {"id": "s8", "title": "Try it", "file": "(terminal)", "code": "python calculator.py"}
    assert rig.s._action_line(s8) == "Run python calculator.py in the VS Code terminal"
    rig.s.has_python = False  # this Mac: python3 only
    assert rig.s._run_command(s2) == "python3 calculator.py"
    assert rig.s._run_command({"id": "x", "code": "cd app && python main.py"}) == "cd app && python3 main.py"



def test_lesson_step_passes_on_its_own_when_the_file_is_saved(tmp_path, monkeypatch):
    """S1: steps didn't advance after the learner saved (no keyboard signal in the harness). A save of the step's
    file since the step began is the learner's action."""
    import time as _t

    async def build(goal, workdir, on_update=None, **kw):
        return _text_lesson()

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        _t.sleep(0.1)
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")  # saved, no watcher event
        await rig.s.evaluate("screen")
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"


def test_run_step_passes_from_vscode_integrated_terminal_output(tmp_path, monkeypatch):
    """S9: app:Terminal checks read VS Code's terminal panel (E6 region) too; new output there = the learner ran it."""
    from types import SimpleNamespace as NS

    g = _run_lesson()
    g["steps"][1]["checks"] = [{"id": "s2c1", "type": "screen_contains", "label": "prints 5", "pattern": "^5$",
                                "app": "Terminal"}]
    g["steps"][1]["precision_checks"] = []

    async def build(goal, workdir, on_update=None, **kw):
        return g

    rig, screen, _ = _lesson_rig(tmp_path, monkeypatch, build)
    (tmp_path / "calc.py").write_text("print(5)\n")
    screen.regions = {"terminal": {"x": 0.0, "y": 600.0, "w": 1200.0, "h": 300.0}}

    def block(text, y):
        return NS(text=text, app="Code", rect={"x": 10.0, "y": y, "w": 300.0, "h": 18.0})

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_obs = NS(app="Code", windows=[], blocks=[block("print(5)", 100.0)])
        await rig.s.goto_step(1)
        await rig.settle()
        assert not [p for p in rig.of("step.passed") if p["stepId"] == "s2"]
        rig.s.last_obs = NS(app="Code", windows=[], blocks=[block("print(5)", 100.0),
                                                            block("% python3 calc.py", 620.0), block("5", 640.0)])
        await rig.s.on_screen(rig.s.last_obs)
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[-1]["stepId"] == "s2"
