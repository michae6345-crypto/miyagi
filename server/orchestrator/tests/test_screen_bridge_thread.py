"""The screen reader must come up when the engine boots it in a worker thread (Nov 24, bon trace B1).

Since Nov 21 (74bc4dfc) Engine.start boots ScreenBridge.start in asyncio.to_thread so the port opens first. The bridge
then called reader.subscribe(on_obs) with no loop; the real reader asks for the running loop for a coroutine callback,
and a worker thread has none: RuntimeError("no running event loop"), caught and logged as "screen reader unavailable",
session.screen = None. Every real lesson ran blind: the step box (_progress_spot / _locate) was always None, so the
engine sent only `spotlight {clear}` and bon never flew to a step's target. The stage worked because its mock sends
spotlight rects itself, and the engine tests' fake readers had a `subscribe(cb)` that never asked for a loop.

These tests use the real ScreenReader.subscribe / _deliver (no capture, no OCR, no pyobjc, no model, no window) on a
bare object, and boot the engine the way the installed app does (FastAPI lifespan -> Engine.start -> worker thread)."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import types

import pytest

from server.orchestrator.screen_bridge import ScreenBridge
from server.screen.reader import ScreenReader


class RealSubscribeReader:
    """server.screen's reader with the real subscribe / delivery rules and nothing that touches the screen."""

    subscribe = ScreenReader.subscribe

    def __init__(self) -> None:
        self.interval = 2.0
        self.status = "ok"
        self.last_error = None
        self.ax_trusted = None
        self.starts = 0
        self.front_cbs: list = []
        self.ax_reader = None
        self.events = None
        self._thread = None
        self._lock = threading.RLock()
        self._subs: list = []

    def start(self):
        self.starts += 1
        return self

    def stop(self) -> None:
        pass

    def on_frontmost_change(self, cb, interval: float = 0.25):
        self.front_cbs.append(cb)
        return lambda: self.front_cbs.remove(cb) if cb in self.front_cbs else None

    def latest(self):
        return None

    def set_overlay_bounds(self, rects) -> None:
        pass

    def deliver_from_capture_thread(self, obs) -> None:
        """What the capture thread does with a new frame (ScreenReader._capture -> _deliver), from its own thread."""
        with self._lock:
            subs = list(self._subs)
        t = threading.Thread(target=ScreenReader._deliver, args=(obs, subs))
        t.start()
        t.join(2)


@pytest.fixture
def reader(monkeypatch):
    r = RealSubscribeReader()
    mod = types.ModuleType("server.screen")
    mod.get_reader = lambda: r
    monkeypatch.setitem(sys.modules, "server.screen", mod)
    monkeypatch.setenv("TUT_SCREEN_FIXTURE", "fake.png")  # off macOS (CI) the bridge only starts for a fixture screen
    for k in ("ORCH_SCREEN_EAGER", "ORCH_SCREEN", "ORCH_AUTOSTART", "ORCH_AUTO_RESUME", "DEMO"):
        monkeypatch.delenv(k, raising=False)
    return r


def test_the_real_subscribe_needs_a_loop_in_a_worker_thread():
    """The rule that broke the live engine: pins it, so a reader change can't make the bridge fix silently moot."""

    async def cb(_obs) -> None:
        return None

    r = RealSubscribeReader()
    with pytest.raises(RuntimeError, match="no running event loop"):
        r.subscribe(cb)  # no loop running here, as in asyncio.to_thread's worker


def test_start_in_a_worker_thread_subscribes_on_the_engine_loop(reader):
    got: list[tuple[object, int]] = []
    seen = asyncio.Event()

    async def on_obs(obs) -> None:
        got.append((obs, threading.get_ident()))
        seen.set()

    async def go() -> None:
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        b = ScreenBridge()
        ok = await asyncio.to_thread(b.start, on_obs, loop)  # exactly Engine._start_screen
        assert ok is True, b.start_error
        assert b.active and b.reader is reader and b.start_error is None
        assert [lp for _cb, lp in reader._subs] == [loop]  # the engine's loop, not None

        frame = object()
        await asyncio.to_thread(reader.deliver_from_capture_thread, frame)
        await asyncio.wait_for(seen.wait(), 2)
        assert got == [(frame, loop_thread)]  # the frame reached the session on the engine loop

    asyncio.run(go())


def test_a_failed_start_says_why(reader, monkeypatch):
    def boom(self, cb, loop=None):
        raise RuntimeError("no running event loop")

    monkeypatch.setattr(RealSubscribeReader, "subscribe", boom)

    async def on_obs(_obs) -> None:
        return None

    async def go() -> None:
        b = ScreenBridge()
        assert await asyncio.to_thread(b.start, on_obs, asyncio.get_running_loop()) is False
        assert b.reader is None and b.start_error == "RuntimeError: no running event loop"

    asyncio.run(go())


def _engine(monkeypatch, tmp_path):
    from server.orchestrator import main

    monkeypatch.setenv("MIYAGI_SYSTEM_STATUS", "0")  # no network / health probes
    monkeypatch.setenv("MIYAGI_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "work"))
    (tmp_path / "work").mkdir()
    eng = main.Engine()
    eng.recorder.enabled = False
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "host_allowed", lambda _h: True)  # TestClient's Host is "testserver"
    return main, eng


def _wait_screen(client, want: str) -> str:
    deadline = time.monotonic() + 5
    state = ""
    while time.monotonic() < deadline:
        state = client.get("/health").json()["screen"]
        if state == want:
            return state
        time.sleep(0.02)
    return state


def test_installed_app_boot_keeps_the_screen_and_frames_reach_the_lesson(reader, monkeypatch, tmp_path):
    """The installed engine's path: FastAPI lifespan -> Engine.start -> the bridge boots in a worker thread. The lesson
    must keep a screen (else no step box, no spotlight rect, no bon at the target) and get frames on its loop."""
    from fastapi.testclient import TestClient

    main, eng = _engine(monkeypatch, tmp_path)
    frames: list[object] = []

    async def on_screen(obs=None) -> None:
        frames.append(obs)

    monkeypatch.setattr(eng.session, "on_screen", on_screen)
    with TestClient(main.app) as client:
        assert _wait_screen(client, "up") == "up"
        assert eng.screen.reader is reader and eng.session.screen is eng.screen
        assert reader.starts == 0  # launch-quiet still holds: the first lesson step starts the capture

        frame = types.SimpleNamespace(app="Code", t=time.time())
        reader.deliver_from_capture_thread(frame)
        deadline = time.monotonic() + 2
        while not frames and time.monotonic() < deadline:
            client.get("/health")  # lets the engine loop run the scheduled callback
            time.sleep(0.02)
        assert frames == [frame]


def test_a_dead_reader_is_loud_and_shows_on_health(reader, monkeypatch, tmp_path, caplog):
    from fastapi.testclient import TestClient

    def boom(self, cb, loop=None):
        raise RuntimeError("no running event loop")

    monkeypatch.setattr(RealSubscribeReader, "subscribe", boom)
    main, eng = _engine(monkeypatch, tmp_path)
    monkeypatch.setattr(main.sys, "platform", "darwin")  # the loud log is for the Mac app
    with caplog.at_level(logging.INFO, logger="orchestrator"), TestClient(main.app) as client:
        state = _wait_screen(client, "down: RuntimeError: no running event loop")
        assert state == "down: RuntimeError: no running event loop"
        assert eng.session.screen is None
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR and "SCREEN READER DOWN" in r.getMessage()]
    assert len(errors) == 1 and "no running event loop" in errors[0].getMessage()
