"""Latency: a stalled socket must not stall every emitter; repeated app reads share one disk read; locate on the loop
never captures."""

import asyncio
import time

from server.orchestrator import hub as hub_mod
from server.orchestrator.hub import Hub
from server.orchestrator.main import Engine
from server.orchestrator.screen_bridge import ScreenBridge


class _Ws:
    def __init__(self, delay=0.0, fail=False):
        self.delay, self.fail, self.sent = delay, fail, []

    async def send_json(self, msg):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(msg)


def test_stalled_client_is_dropped_and_others_are_not_held(monkeypatch):
    monkeypatch.setattr(hub_mod, "SEND_TIMEOUT_S", 0.2)

    async def go():
        h = Hub()
        slow, good, bad = _Ws(delay=30), _Ws(), _Ws(fail=True)
        for w in (slow, good, bad):
            h.clients.add(w)
        t = time.monotonic()
        await h.emit("status", {"state": "idle", "detail": ""})
        return h, slow, good, time.monotonic() - t

    h, slow, good, dt = asyncio.run(go())
    assert dt < 1.0  # was: sequential, unbounded (the slow client held every emitter 30 s)
    assert len(good.sent) == 1 and h.clients == {good}


def test_app_reads_are_coalesced(monkeypatch):
    calls = []

    async def go():
        e = Engine.__new__(Engine)
        e._reads, e._reads_inflight, e._reads_gen = {}, {}, 0

        async def make():
            calls.append(1)
            await asyncio.sleep(0.05)
            return {"n": len(calls)}

        a = await asyncio.gather(*(e._coalesced("k", make) for _ in range(4)))
        b = await e._coalesced("k", make)
        e.forget_reads()
        c = await e._coalesced("k", make)
        return a, b, c

    a, b, c = asyncio.run(go())
    assert all(x == {"n": 1} for x in a) and b == {"n": 1} and c == {"n": 2}


def test_locate_on_the_loop_never_captures():
    class R:
        status = "ok"
        captured = False

        def latest(self):
            return None

        def locate_match(self, *a):
            R.captured = True

        def locate_match_cached(self, *a):
            return None

    async def go():
        b = ScreenBridge(enabled=False)
        b.reader = R()
        return b.locate("x")

    assert asyncio.run(go()) is None and not R.captured


def test_stalled_client_socket_is_closed_not_just_forgotten(monkeypatch):
    monkeypatch.setattr(hub_mod, "SEND_TIMEOUT_S", 0.1)

    class W(_Ws):
        closed = None

        async def close(self, code=1000):
            self.closed = code

    async def go():
        h = Hub()
        slow, good = W(delay=30), W()
        h.clients.update((slow, good))
        await h.emit("status", {"state": "idle", "detail": ""})
        await asyncio.gather(*list(h._close_tasks))
        return h, slow, good

    h, slow, good = asyncio.run(go())
    assert slow.closed == 1011 and good.closed is None and h.clients == {good} and not h._close_tasks


def test_cancelled_leader_does_not_cancel_waiters():
    async def go():
        e = Engine.__new__(Engine)
        e._reads, e._reads_inflight, e._reads_gen = {}, {}, 0
        n = []

        async def make():
            n.append(1)
            await asyncio.sleep(0.2 if len(n) == 1 else 0.01)
            return len(n)

        leader = asyncio.create_task(e._coalesced("k", make))
        await asyncio.sleep(0.02)
        waiter = asyncio.create_task(e._coalesced("k", make))
        await asyncio.sleep(0.02)
        leader.cancel()
        return await waiter, len(n)

    res, calls = asyncio.run(go())
    assert res == 2 and calls == 2  # the waiter retried as the new leader instead of raising CancelledError


def test_read_in_flight_during_forget_is_not_cached():
    async def go():
        e = Engine.__new__(Engine)
        e._reads, e._reads_inflight, e._reads_gen = {}, {}, 0

        async def make():
            await asyncio.sleep(0.05)
            return "stale"

        t = asyncio.create_task(e._coalesced("k", make))
        await asyncio.sleep(0.01)
        e.forget_reads()
        await t
        return e._reads

    assert asyncio.run(go()) == {}


def test_startup_does_not_wait_for_screen_boot(monkeypatch):
    import threading

    release = threading.Event()

    class SlowScreen:
        enabled = True
        down_reason = None

        def start(self, cb, loop=None):
            release.wait(3)
            return True

        def stop(self):
            pass

        def watch_frontmost(self, cb):
            pass

    async def go():
        e = Engine.__new__(Engine)
        e._reads, e._reads_inflight, e._reads_gen = {}, {}, 0
        e._screen_boot = e._ticker = e._avoider = e._autostart = e._cloud_off = None
        e.status = None
        e.screen = SlowScreen()
        up = []
        e._screen_up = lambda ok: up.append(ok)
        e.watch_cloud = lambda: None
        e.save_progress = lambda: None

        class Sess:
            workdir = "."
            on_screen = staticmethod(lambda *a: None)

        class Watcher:
            def set_root(self, r): pass
            def start(self): pass
            async def stop(self): pass

        class Mods:
            demo = False
            def describe(self): return ""

        e.session, e.watcher, e.modules = Sess(), Watcher(), Mods()
        t = time.monotonic()
        await e.start()
        dt = time.monotonic() - t
        assert e._screen_boot is not None and not e._screen_boot.done() and up == []
        stopper = asyncio.create_task(e.stop())
        await asyncio.sleep(0.1)
        assert not stopper.done()  # stop() awaits the screen boot
        release.set()
        await stopper
        return dt, up

    dt, up = asyncio.run(go())
    assert dt < 1.0 and up == [True]  # start() returned while the 3 s screen boot was still running
