"""State-machine tests. Run from the repo root:  python -m pytest server/orchestrator -q"""

from __future__ import annotations

import asyncio
import types
from pathlib import Path

import pytest

from server.orchestrator import stubs
from server.orchestrator.hub import Hub
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

    def __init__(self, workdir: Path, modules: Modules | None = None, screen: FakeScreen | None = None):
        self.hub = Hub(strict=True)
        self.clock = Clock()
        self.workdir = workdir
        self.screen = screen
        self.s = LessonSession(self.hub.emit, modules or Modules(demo=False, force_stubs="all"),
                               clock=self.clock, idle_gate_s=5, advance_delay_s=0, metric_eval_s=0,
                               result_stagger_s=0, build_tick_s=0.01, screen=screen, seen_interval_s=0)

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


def test_already_done_step_waits_for_segment_end(rig):
    rig.write("# already here\n")

    async def go():
        await rig.start_lesson()
        assert rig.s.step["id"] == "s1"  # checks pass, but the clip is still playing
        assert rig.of("check.updated")[-1]["status"] == "pass"
        assert not rig.of("step.passed")
        await rig.end_segment()

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"
    assert "video.pause" not in rig.types()


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
    rig = Rig(tmp_path, screen=screen)

    async def go():
        await rig.start_lesson()
        await rig.end_segment()
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
    assert not [e for e in first if e["type"] == "offtrack"]
    assert all(e["payload"]["status"] != "fail" for e in first if e["type"] == "check.updated")
    assert [e["payload"]["status"] for e in second if e["type"] == "check.updated"] == ["fail", "fail"]
    off = [e["payload"] for e in second if e["type"] == "offtrack"]
    assert len(off) == 1 and off[0]["stepId"] == "s2"
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


def test_hero_plateau_then_curriculum(rig):
    rig.s.screen = FakeScreen()
    rig.s.screen.text["Code"] = ["def train(model):", "    beta = 30", "    for epoch in range(4000):"]

    async def go():
        await _to_step(rig, 5)
        assert rig.s.step["id"] == "s6"
        rig.write("def train(model):\n    beta = 30\n    for epoch in range(4000):\n        pass\n")
        await rig.end_segment()
        m = rig.mark()
        await rig.run("r-plateau", PLATEAU)
        plateau = rig.since(m)
        m = rig.mark()
        await rig.run("r-curriculum", CONVERGE)
        return plateau, rig.since(m)

    plateau, fixed = run(go())
    off = [e["payload"] for e in plateau if e["type"] == "offtrack"]
    assert len(off) == 1
    assert off[0]["citation"]["url"] == "https://arxiv.org/abs/2109.01050"
    assert off[0]["diff"]["yours"] == "beta = 30" and off[0]["diff"]["line"] == 2
    spot = [e["payload"] for e in plateau if e["type"] == "spotlight"][-1]
    assert spot["matched"] == "    beta = 30" and spot["caption"] == off[0]["title"]
    assert any(e["type"] == "metric" for e in plateau)
    passed = [e["payload"] for e in fixed if e["type"] == "step.passed"]
    assert passed == [{"stepId": "s6"}]  # last step: no nextStepId
    assert rig.s.phase == "done"
    assert fixed[-1]["type"] == "video.play"


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
    import os

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


def test_action_without_lesson_is_an_error(rig):
    run(rig.s.action("hint"))
    assert rig.of("error")


# ---------------------------------------------------------------- resilience

def test_real_module_failure_falls_back_to_stub(rig, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("api down")

    mods = Modules(demo=False, force_stubs="")
    mods.real["coach"] = types.SimpleNamespace(diagnose=boom)
    mods.real["checks"] = types.SimpleNamespace(evaluate_step=boom)
    r2 = Rig(rig.workdir, mods)

    async def go():
        await _to_step(r2, 5)
        r2.write("beta = 30\n")
        await r2.run("r1", PLATEAU)

    run(go())
    assert r2.of("offtrack")[0]["title"] == "Loss plateaued at large β"


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
            assert seen.count("search.result") == 3
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
