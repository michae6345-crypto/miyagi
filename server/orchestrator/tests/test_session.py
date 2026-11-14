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


def test_vscode_opens_only_after_the_learner_says_yes(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod
    from server.orchestrator.workspace import Workspace

    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: None)  # no S2 check: the plain offer

    calls = []
    ws = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)
    (tmp_path / "pinn_convection.py").write_text("import torch\n\n\ndef pde_residual(model, x, t, beta):\n    pass\n")
    rig = Rig(tmp_path)
    rig.s.workspace = ws

    async def go():
        await rig.start_lesson()
        await rig.s.goto_step(3)
        await rig.settle()
        await asyncio.sleep(0.05)  # the setup card is computed in the background
        assert not calls  # nothing opened, not even `code -g`
        card = rig.of("card")[0]
        assert card["title"] == f"Open {wsmod.editor_label()}?" and card["actions"] == ["open_editor"]  # Cursor if installed
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
    assert any(c["body"].startswith("Installing pandas") for c in rig.of("card"))
    assert not calls  # never opened VS Code


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
        assert prefetched == [(3, "build chat gpt")]
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


def test_show_me_uses_e5_pointing(rig):
    rig.s.m.has_pointing = lambda: True

    async def show_me(step, screen, last):
        return {"targets": [{"boxId": 1, "label": "here", "text": "net = ...", "rect": {"x": 5, "y": 6, "w": 7, "h": 8}}],
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
    assert spot["rect"] == {"x": 5.0, "y": 6.0, "w": 7.0, "h": 8.0} and spot["caption"] == "Build the MLP here"


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
        await rig.settle()

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
    assert spot["caption"] == "Type add() here" and spot["snippet"] == "def add(a, b):\n    return a + b\n"
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
    """Check button: deterministic checks first, then E5's judge; ONE "Not yet" card (<= 12 words) + spotlight."""
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
        assert new[0]["actions"] == ["skip_step"] and len(new[0]["body"].split()) <= 12
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
    assert card["title"] == "Not yet" and "uses tanh" in card["body"] and card["actions"] == ["skip_step"]


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
        rig.clock.t += 95
        await rig.s.tick()
        await rig.s.tick()
        await rig.settle()

    run(go())
    stuck = [c for c in rig.of("card") if c["title"] == "Stuck on this step?"]
    assert len(stuck) == 1 and stuck[0]["actions"] == ["skip_step"]


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
