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
        e._reads, e._reads_inflight = {}, {}

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
