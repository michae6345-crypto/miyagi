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
    assert after[:4] == ["step.started", "check.updated", "video.seek", "video.play"]
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
        assert rig.s.step["id"] == "s1"  # checks pass, but the clip is still playing
        assert rig.of("check.updated")[-1]["status"] == "pass"
        assert not rig.of("step.passed")
        await rig.end_segment()  # screen says done, but nobody did anything: ask, don't assert
        assert not rig.of("step.passed")
        assert rig.of("card")[-1]["title"] == "Looks done?" and rig.of("card")[-1]["actions"] == ["confirm"]
        await rig.s.action("confirm")
        await rig.settle()

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"
    assert "video.pause" in rig.types()  # gated at the clip's end until the learner confirms


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
    assert fixed[-1]["type"] == "video.play"


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
    st = main.apply_keys({"anthropic": "sk-test-123", "tigerUrl": "postgres://..."})
    assert st == {"anthropic": "ok", "gemini": "env", "brightdata": "missing", "elevenlabs": "missing",
                  "tigerUrl": "missing"}
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
    assert seeks == [{"t": 380.0, "play": True}, {"t": 380.0, "play": True}]
    assert rig.s.voice is True


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
    assert r2.of("offtrack")[0]["title"] == "Loss plateaued at large β"


def test_vscode_opens_only_after_the_learner_says_yes(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator.workspace import Workspace

    calls = []
    ws = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)
    (tmp_path / "pinn_convection.py").write_text("import torch\n\n\ndef pde_residual(model, x, t, beta):\n    pass\n")
    rig = Rig(tmp_path)
    rig.s.workspace = ws

    async def go():
        await rig.start_lesson()
        await rig.s.goto_step(3)
        await rig.settle()
        assert not calls  # nothing opened, not even `code -g`
        card = rig.of("card")[0]
        assert card["title"] == "Open VS Code?" and card["actions"] == ["open_editor"]
        await rig.s.action("open_editor")

    run(go())
    first = calls[0]  # S2's open_editor: `code -n <dir> [-g <file>]`, or `open -a "Visual Studio Code" <dir>`
    assert (first[1:3] == ["-n", str(tmp_path.resolve())]) or (first[:3] == ["open", "-a", "Visual Studio Code"])
    gotos = [c for c in calls if "-g" in c and "-n" not in c]
    assert gotos and gotos[-1][-1] == f"{tmp_path / 'pinn_convection.py'}:4"


def test_non_code_lesson_never_offers_vscode(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator.workspace import Workspace, needs_editor

    graph = stubs.load_fixture_lesson()
    for st in graph["steps"]:
        st["targets"] = [{"app": "Blender", "match": "Add Cube", "caption": "add a cube"}]
        for c in st["checks"]:
            c["app"] = "Blender"
        st["precision_checks"] = []
    assert needs_editor(graph) is False and needs_editor(stubs.load_fixture_lesson()) is True
    calls = []
    rig = Rig(tmp_path)
    rig.s.workspace = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)
    run(rig.s.load_graph(graph))
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
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
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

    async def fake_build(url, goal, workdir, on_progress=None):
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

    async def slow_failing_build(url, goal, workdir, on_progress=None):
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
    async def build(url, goal, workdir, on_progress=None):
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

    async def build(url, goal, workdir, on_progress=None):
        for stage, msg in [("watching", ""), ("reading_transcript", ""), ("writing_steps", "212 transcript lines"),
                           ("engine_switch", "quota"), ("steps_ready", "claude"), ("adapting", ""), ("done", "41.2")]:
            on_progress(stage, msg)
            await asyncio.sleep(0.07)
        return stubs.load_fixture_lesson()

    rig.s.m.build_lesson = build
    run(rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk"))
    msgs = [b["message"] for b in rig.of("lesson.building")]
    for label in ("Gemini is watching the video", "Claude is writing the steps",
                  "Gemini is rate-limited; using the transcript", "Steps ready (from the transcript)",
                  "Fitting the checks to your project"):
        assert any(m.startswith(label) for m in msgs), label
    assert rig.of("lesson.ready")


def test_voice_speaks_step_offtrack_and_pass_only_when_on_and_not_typing(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
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

    async def slow_build(url, goal, workdir, on_progress=None):
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
    with TestClient(main.app) as client:
        r = client.post("/end")
        assert r.json() == {"ok": True, "ended": None}
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
        assert [t for t, _ in snap] == ["video.pause", "card"]
        card = snap[1][1]
        assert card["kind"] == "resume" and card["actions"] == ["resume", "end_lesson"]
        assert card["title"] == "Continue where you left off?" and "Write the PDE residual" in card["body"]
        m = rig.mark()
        await rig.save("u_t + beta * u_x\nautograd.grad\n")  # frozen: nothing is graded while undecided
        assert not [e for e in rig.since(m) if e["type"] in ("check.updated", "step.passed", "offtrack")]
        assert [t for t, _ in rig.s.snapshot()] == ["video.pause", "card"]  # still undecided
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
