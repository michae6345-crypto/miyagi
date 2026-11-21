"""Nov 21 (launch-quiet): a saved lesson never comes back on connect. Run:  python -m pytest server/sessions -q

snapshot() with no lesson in memory is status idle only; pending_offer() is the resume card main.py sends after the
app's library.list (not for a stopped save); Continue restores the saved step paused (video.seek play false, no
video.play) and keeps the saved lastActiveAt."""

from __future__ import annotations

import asyncio

import pytest

from server import sessions
from server.orchestrator import stubs
from server.orchestrator.hub import Hub
from server.orchestrator.modules import Modules
from server.orchestrator.session import LessonSession
from server.sessions import Resumer


class WallClock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(d))
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "work"))
    (tmp_path / "work").mkdir()
    monkeypatch.delenv("DEMO", raising=False)
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY",
              "TIGER_DATABASE_URL"):  # cost freeze
        monkeypatch.setenv(k, "")
    return d


class Engine:
    def __init__(self, clock: WallClock | None = None) -> None:
        self.hub = Hub(strict=True)
        self.clock = clock or WallClock()
        self.s = LessonSession(self.hub.emit, Modules(demo=False, force_stubs="all"), idle_gate_s=5,
                               advance_delay_s=0, metric_eval_s=0, result_stagger_s=0, build_tick_s=0.01,
                               seen_interval_s=0)
        self.r = Resumer(self.s, clock=self.clock)

    async def settle(self) -> None:
        await asyncio.sleep(0)
        await self.s.drain()


def _save_at_step_3() -> tuple[dict, float]:
    e = Engine()

    async def go() -> dict:
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        await e.s.goto_step(2)
        await e.settle()
        seg = e.s._segment(e.s.step)
        await e.s.video_state(seg["start"] + 15, False)
        return seg

    seg = asyncio.run(go())
    return seg, float(sessions.load()["lastActiveAt"])


def test_no_lesson_in_memory_snapshot_is_idle_only():
    _save_at_step_3()
    e = Engine()
    assert e.s.snapshot() == [("status", {"state": "idle"})]
    assert e.s.snapshot(ask_resume=True) == [("status", {"state": "idle"})]
    offer = e.r.pending_offer()
    assert offer["kind"] == "resume" and offer["actions"] == ["resume", "end_lesson"]


def test_nothing_saved_or_a_stopped_save_offers_nothing():
    e = Engine()
    assert e.r.pending_offer() is None
    _save_at_step_3()
    sessions.save({**sessions.load(), "stopped": True})
    assert Engine().r.pending_offer() is None


def test_no_offer_while_a_lesson_is_in_memory():
    e = Engine()
    asyncio.run(e.s.load_graph(stubs.load_fixture_lesson()))
    assert e.r.pending_offer() is None


def test_continue_restores_paused_and_keeps_last_active():
    seg, last_active = _save_at_step_3()
    e = Engine(WallClock(1_800_000_000.0 + 7200))  # two hours later

    async def go():
        n = len(e.hub.history)
        assert await e.r.resume()
        await e.settle()
        evs = list(e.hub.history)[n:]
        seeks = [x["payload"] for x in evs if x["type"] == "video.seek"]
        assert seeks == [{"t": seg["start"] + 15, "play": False}]
        assert not [x for x in evs if x["type"] == "video.play"]
        assert e.s.idx == 2 and not e.s.restoring
        assert sessions.load()["lastActiveAt"] == last_active  # not "now": the restore isn't activity
        await e.s.video_state(seg["start"] + 16, True)  # the learner presses play: that is activity
        assert sessions.load()["lastActiveAt"] == e.clock.t

    asyncio.run(go())
