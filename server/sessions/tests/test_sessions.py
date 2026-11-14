"""Resume-or-new. Run from the repo root:  python -m pytest server/sessions -q"""

from __future__ import annotations

import asyncio
import json

import pytest

from server import sessions
from server.orchestrator import stubs
from server.orchestrator.hub import Hub
from server.orchestrator.modules import Modules
from server.orchestrator.session import LessonSession
from server.sessions import Resumer, resume_offer, store
from shared.contracts.events import engine_message, parse_app_message


class WallClock:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(d))
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "work"))
    (tmp_path / "work").mkdir()
    monkeypatch.delenv("DEMO", raising=False)
    return d


class Engine:
    """A fresh engine process: strict hub + session + resumer (a restart = a new Engine on the same disk)."""

    def __init__(self) -> None:
        self.hub = Hub(strict=True)
        self.clock = WallClock()
        self.s = LessonSession(self.hub.emit, Modules(demo=False, force_stubs="all"), idle_gate_s=5,
                               advance_delay_s=0, metric_eval_s=0, result_stagger_s=0, build_tick_s=0.01,
                               seen_interval_s=0)
        self.r = Resumer(self.s, clock=self.clock)

    async def settle(self) -> None:
        await asyncio.sleep(0)
        await self.s.drain()

    def since(self, mark: int) -> list[dict]:
        return list(self.hub.history)[mark:]

    def mark(self) -> int:
        return len(self.hub.history)


def test_save_load_clear_roundtrip_is_atomic(state_dir):
    assert sessions.load() is None
    graph = {"lesson": {"id": "L1", "title": "T"}, "steps": [{"id": "s1", "title": "a"}]}
    sessions.save({"lessonId": "L1", "title": "T", "stepIndex": 0, "stepCount": 1, "videoT": 12.5}, graph)
    st = sessions.load()
    assert st["lessonId"] == "L1" and st["videoT"] == 12.5 and st["lastActiveAt"] and st["version"] == 1
    assert sessions.load_graph(st) == graph
    assert sorted(p.name for p in state_dir.iterdir()) == ["current.graph.json", "current.json"]  # no temp files left
    sessions.clear()
    assert sessions.load() is None and sessions.load_graph() is None
    sessions.clear()  # clearing nothing is fine


def test_corrupt_or_foreign_files_read_as_none(state_dir):
    state_dir.mkdir(parents=True)
    (state_dir / "current.json").write_text("{not json")
    assert sessions.load() is None
    (state_dir / "current.json").write_text(json.dumps({"lessonId": "L1"}))  # no step index
    assert sessions.load() is None
    sessions.save({"lessonId": "L1", "stepIndex": 0, "stepCount": 2}, {"lesson": {"id": "OTHER"}, "steps": [{"id": "x"}]})
    assert sessions.load_graph(sessions.load()) is None  # cached graph belongs to another lesson
    (state_dir / "current.graph.json").write_text("garbage")
    assert sessions.load_graph() is None


def test_resume_offer_card_matches_the_contract():
    card = resume_offer({"lessonId": "L", "title": "PINNs for convection", "stepIndex": 2, "stepCount": 7,
                         "lastActiveAt": 1000.0}, now=1000.0 + 12 * 60 + 5)
    assert card["kind"] == "resume" and card["actions"] == ["resume", "end_lesson"]
    assert card["body"] == "PINNs for convection · Step 3 of 7 · 12 min ago"
    engine_message("card", card)
    assert parse_app_message({"type": "action", "payload": {"kind": "resume"}}).payload.kind == "resume"
    assert sessions.ago(30) == "just now" and sessions.ago(7200) == "2 h ago" and sessions.ago(86400 * 3) == "3 days ago"


def test_progress_saved_on_step_and_video_then_parked_on_reopen():
    e = Engine()

    async def go():
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        await e.s.goto_step(1)
        await e.settle()
        seg = e.s._segment(e.s.step)
        await e.s.video_state(seg["start"] + 7, True)
        st = sessions.load()
        assert st["stepIndex"] == 1 and st["videoT"] == seg["start"] + 7 and st["passedSteps"] == [e.s.steps[0]["id"]]

        n = len(e.s.steps)
        e.r.on_disconnect(0)  # the app quit
        e.clock.t += 600
        m = e.mark()
        msgs = await e.r.on_connect(0)  # the app reopened
        assert [t for t, _ in msgs] == ["spotlight", "video.pause", "status", "card"]
        assert msgs[2][1] == {"state": "idle"}
        card = msgs[3][1]
        assert card["body"].endswith("Step 2 of %d · 10 min ago" % n)
        for t, p in msgs:
            engine_message(t, p)
        assert e.s.graph is None and e.s.phase == "idle"
        assert e.since(m) == []  # parking is silent: no lesson.ended broadcast
        assert sessions.load()["stepIndex"] == 1  # parking keeps the save
        return seg

    run(go())


def test_socket_blip_keeps_the_old_snapshot():
    e = Engine()

    async def go():
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        e.r.on_disconnect(0)
        e.clock.t += 1  # reconnect within the grace period
        msgs = await e.r.on_connect(0)
        assert [t for t, _ in msgs][:2] == ["lesson.ready", "step.started"] and e.s.graph is not None
        assert [t for t, _ in await e.r.on_connect(1)][:1] == ["lesson.ready"]  # a second window: never park

    run(go())


def test_resume_after_engine_restart_restores_step_and_video():
    first = Engine()

    async def before():
        await first.s.load_graph(stubs.load_fixture_lesson())
        await first.settle()
        await first.s.goto_step(2)
        await first.settle()
        seg = first.s._segment(first.s.step)
        await first.s.video_state(seg["start"] + 20, False)
        return seg

    seg = run(before())

    second = Engine()  # engine restarted: nothing in memory
    second.clock.t = first.clock.t + 3600

    async def after():
        msgs = await second.r.on_connect(0)
        assert msgs[-1][0] == "card" and msgs[-1][1]["resume"]["stepIndex"] == 2
        m = second.mark()
        assert await second.r.resume()
        await second.settle()
        evs = second.since(m)
        types = [e["type"] for e in evs]
        assert types[0] == "lesson.ready"
        started = [e["payload"] for e in evs if e["type"] == "step.started"]
        assert len(started) == 1 and started[0]["index"] == 2  # no detour through step 0
        seeks = [e["payload"] for e in evs if e["type"] == "video.seek"]
        assert seeks[-1] == {"t": seg["start"] + 20, "play": True}
        assert second.s.idx == 2 and second.s.phase == "active"
        assert ("status", {"state": "watching"}) in [(e["type"], e["payload"]) for e in evs]

    run(after())


def test_end_lesson_clears_the_save_and_new_learn_too():
    e = Engine()

    async def go():
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        assert sessions.load() is not None
        await e.s.end_lesson("end_lesson")
        assert sessions.load() is None and sessions.load_graph() is None
        assert e.r.on_connect is not None and (await e.r.on_connect(0))[0] == ("status", {"state": "idle"})

        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        assert sessions.load() is not None
        await e.s.learn("something else")  # a new lesson ends the old one
        await e.settle()
        assert sessions.load() is None

    run(go())


def test_passing_moves_the_save_forward_and_finishing_clears_it():
    e = Engine()

    async def go():
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        n = len(e.s.steps)
        await e.s._pass_step()  # quit right after a pass -> resume on the next step
        assert sessions.load()["stepIndex"] == 1
        await e.settle()
        await e.s.goto_step(n - 1)
        await e.settle()
        await e.s._pass_step()
        assert sessions.load() is None  # lesson complete

    run(go())


def test_resume_with_nothing_saved_is_a_clear_error():
    e = Engine()

    async def go():
        m = e.mark()
        assert not await e.r.resume()
        assert [x["type"] for x in e.since(m)] == ["error", "status"]

    run(go())
