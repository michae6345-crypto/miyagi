"""Nov 21 (launch-quiet): the screen reader is created at boot but starts only with the first lesson step.

Michael, every launch of the installed app: "Right when it opens, it just opens up everything" (prompts to control
the screen among them). Before a lesson: no capture, no Accessibility reader, no event taps (no keyboard tap without
Input Monitoring), no frontmost poller, and no "Check Screen Recording" error. Offline: a fake server.screen module,
never the real reader, never a real event tap."""

from __future__ import annotations

import asyncio
import sys
import threading
import types

import pytest

from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import ScreenBridge
from server.orchestrator.session import LessonSession


class FakeReader:
    def __init__(self, status: str = "ok") -> None:
        self.interval = 2.0
        self.status = status
        self.last_error = None
        self.starts = 0
        self.stops = 0
        self.subs: list = []
        self.front_cbs: list = []
        self.ax_reader = None
        self.events = None
        self._thread = None

    def start(self):
        self.starts += 1
        return self

    def stop(self) -> None:
        self.stops += 1

    def subscribe(self, cb):
        self.subs.append(cb)
        return lambda: self.subs.remove(cb)

    def on_frontmost_change(self, cb, interval: float = 0.25):
        self.front_cbs.append(cb)
        return lambda: self.front_cbs.remove(cb) if cb in self.front_cbs else None

    def latest(self):
        return None


@pytest.fixture
def fake_screen(monkeypatch):
    reader = FakeReader()
    mod = types.ModuleType("server.screen")
    mod.get_reader = lambda: reader
    monkeypatch.setitem(sys.modules, "server.screen", mod)
    monkeypatch.delenv("ORCH_SCREEN_EAGER", raising=False)
    monkeypatch.delenv("ORCH_SCREEN", raising=False)
    return reader


async def _on_obs(_obs) -> None:
    return None


async def _on_front(_app: str) -> None:
    return None


def test_start_never_starts_the_reader_the_first_resume_does_once(fake_screen):
    async def go():
        b = ScreenBridge()
        assert b.start(_on_obs) is True  # session.screen stays the real bridge
        b.watch_frontmost(_on_front)
        assert fake_screen.starts == 0 and b.paused and not b.started  # no capture, taps, AX reader
        assert fake_screen.front_cbs == []  # no frontmost poller before a lesson
        assert len(fake_screen.subs) == 1 and b.reader is fake_screen
        assert b.latest() is None and b.fresh() is None  # reads answer "nothing" while not started

        b.resume("step s1")  # a lesson step started (session._sync_screen_soon)
        assert fake_screen.starts == 1 and b.started and not b.paused
        assert len(fake_screen.front_cbs) == 1  # the front-app watcher subscribed now
        b.resume("step s2")  # idempotent
        assert fake_screen.starts == 1 and len(fake_screen.front_cbs) == 1

        b.pause("no lesson step")  # a pause / resume cycle still restarts it, one watcher only
        assert fake_screen.stops == 1 and b.paused and fake_screen.front_cbs == []
        b.resume("step s3")
        assert fake_screen.starts == 2 and len(fake_screen.front_cbs) == 1

    asyncio.run(go())


def test_eager_env_keeps_the_old_boot_start(fake_screen, monkeypatch):
    monkeypatch.setenv("ORCH_SCREEN_EAGER", "1")

    async def go():
        b = ScreenBridge()
        assert b.start(_on_obs) is True
        b.watch_frontmost(_on_front)
        assert fake_screen.starts == 1 and not b.paused and b.started
        assert len(fake_screen.front_cbs) == 1

    asyncio.run(go())


def test_no_screen_recording_error_while_no_step_runs(fake_screen):
    fake_screen.status = "no_permission"
    sent: list[tuple[str, dict]] = []

    async def emit(t: str, p: dict | None = None) -> None:
        sent.append((t, p or {}))

    class Clock:
        t = 1000.0

        def __call__(self) -> float:
            return self.t

    async def go():
        b = ScreenBridge()
        assert b.start(_on_obs)
        clock = Clock()
        s = LessonSession(emit, Modules(demo=False, force_stubs="all"), clock=clock, screen=b)
        for _ in range(4):  # well past SCREEN_DOWN_S, no lesson loaded
            await s._check_screen_health()
            clock.t += 20
        assert not [p for t, p in sent if t == "error"]
        assert s._screen_down_since is None
        b.paused = False  # even when the bridge isn't paused: no step runs, so no error
        b.started = True
        for _ in range(3):
            await s._check_screen_health()
            clock.t += 20
        assert not [p for t, p in sent if t == "error"]
        assert fake_screen.starts == 0

    asyncio.run(go())


# ---------------------------------------------------------------------------------------------- event taps
quartz = pytest.importorskip("Quartz")


def _tap_masks(monkeypatch, preflight):
    from server.screen import events

    # None stands for an old pyobjc without the call (pyobjc's lazy module can't really lose an attribute)
    monkeypatch.setattr(events.Quartz, "CGPreflightListenEventAccess", preflight, raising=False)
    requested = []
    monkeypatch.setattr(events.Quartz, "CGRequestListenEventAccess",
                        lambda: requested.append("request") or False, raising=False)
    masks: list[int] = []

    def fake_tap(self, mask):  # never a real tap in tests
        masks.append(mask)
        return None

    monkeypatch.setattr(events.EventTriggers, "_make_tap", fake_tap)
    t = events.EventTriggers(lambda *_: None)
    ready = threading.Event()
    t._tap_thread(ready)
    t.stop()
    key_mask = events._mask(events.Quartz.kCGEventKeyDown)
    return t, masks, key_mask, requested, ready


def test_no_keyboard_tap_without_input_monitoring(monkeypatch):
    t, masks, key_mask, requested, ready = _tap_masks(monkeypatch, lambda: False)
    assert key_mask not in masks and len(masks) == 1  # the mouse tap is still asked for
    assert t.key_tap is False and ready.is_set()
    assert requested == []  # never CGRequestListenEventAccess (it prompts)


def test_keyboard_tap_with_input_monitoring_or_an_old_pyobjc(monkeypatch):
    _, masks, key_mask, requested, _ = _tap_masks(monkeypatch, lambda: True)
    assert key_mask in masks and requested == []
    _, masks, key_mask, _, _ = _tap_masks(monkeypatch, None)  # no preflight call: as before
    assert key_mask in masks
