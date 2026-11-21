"""Island / comms hardening: every "thinking" resolves, a (re)connect resyncs, replies carry their lesson / step, a stalled
client can't block the others. Offline: fake sockets and TestClient only."""

from __future__ import annotations

import asyncio
import types

from server.orchestrator import hub as hub_mod
from server.orchestrator import session as session_mod
from server.orchestrator import stubs
from server.orchestrator.hub import Hub
from server.orchestrator.tests.test_session import Rig


def run(coro):
    return asyncio.run(coro)


class FakeWS:
    def __init__(self, delay: float = 0.0, fail: bool = False):
        self.sent: list[dict] = []
        self.delay, self.fail = delay, fail
        self.closed: int | None = None

    async def close(self, code: int = 1000):
        self.closed = code

    async def send_json(self, msg):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(msg)


def test_hub_drops_a_stalled_client_without_blocking_the_rest(monkeypatch):
    monkeypatch.setattr(hub_mod, "SEND_TIMEOUT_S", 0.05)

    async def go():
        h = Hub()
        slow, ok, dead = FakeWS(delay=5), FakeWS(), FakeWS(fail=True)
        for w in (slow, ok, dead):
            h.join(w)
        await h.emit("status", {"state": "idle"})
        assert [m["type"] for m in ok.sent] == ["status"]
        assert h.clients == {ok}
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert slow.closed == 1011 and dead.closed == 1011  # dropped sockets are closed, so the app reconnects
        assert ok.closed is None

    run(go())


def test_hub_holds_events_emitted_during_the_snapshot_and_sends_them_after():
    async def go():
        h = Hub()
        w = FakeWS()
        h.begin(w)
        await h.send_to(w, "status", {"state": "idle"})  # the snapshot
        await h.emit("status", {"state": "thinking"})  # a live event in the gap
        await h.finish(w)
        await h.emit("status", {"state": "watching"})
        assert [m["payload"]["state"] for m in w.sent] == ["idle", "thinking", "watching"]

    run(go())


def test_thinking_watchdog_ends_an_unresolved_spinner(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    r = Rig(tmp_path)
    r.s.THINKING_MAX_S = 0.05

    async def go():
        await r.s._status("thinking", detail="Writing a hint")
        assert r.s.status == "thinking"
        await asyncio.sleep(0.2)
        assert r.s.status != "thinking"
        assert r.of("status")[-1]["state"] in ("idle", "watching")
        assert any("too long" in e["message"] for e in r.of("error"))

    run(go())


def test_a_thinking_that_resolves_never_fires_the_watchdog(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    r = Rig(tmp_path)
    r.s.THINKING_MAX_S = 0.05

    async def go():
        await r.s._status("thinking")
        await r.s._status("watching")
        await asyncio.sleep(0.15)
        assert r.of("error") == []

    run(go())


def test_cancelled_action_leaves_no_thinking(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    r = Rig(tmp_path)

    async def go():
        await r.s.load_graph(stubs.load_fixture_lesson())
        started = asyncio.Event()

        async def slow(kind, text=None):
            await r.s._status("thinking", detail="Writing a hint")
            started.set()
            await asyncio.sleep(30)

        r.s._action = slow
        t = asyncio.create_task(r.s.action("hint"))
        await started.wait()
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
        assert r.s.status != "thinking"
        assert r.of("status")[-1]["state"] != "thinking"

    run(go())


def test_status_of_an_ended_lesson_is_not_recorded_as_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    r = Rig(tmp_path)

    async def go():
        token = session_mod._EPOCH.set(r.s.lesson_epoch - 1)
        try:
            await r.s._status("thinking", detail="Writing a hint")
        finally:
            session_mod._EPOCH.reset(token)
        assert r.s.status != "thinking"  # not recorded: a later real status is still sent, not deduped away
        assert not any(p.get("state") == "thinking" for p in r.of("status"))

    run(go())


def test_engine_emit_tags_status_and_error_with_epoch_and_gen(monkeypatch):
    from server.orchestrator import main

    async def go():
        await main.engine.session._status("thinking")
        await main.engine._emit("error", {"message": "x"})
        s = main.engine.session
        for m in list(main.engine.hub.history)[-2:]:
            assert m["payload"]["epoch"] == s.lesson_epoch and m["payload"]["gen"] == s.step_gen
        await s._status("idle")

    run(go())


def test_an_answer_card_for_an_older_step_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    r = Rig(tmp_path)

    async def go():
        token = session_mod._GEN.set(r.s.step_gen - 1)
        try:
            await r.s.emit("card", {"kind": "answer", "title": "Old", "body": "for the previous step"})
        finally:
            session_mod._GEN.reset(token)
        assert r.of("card") == []
        await r.s.emit("card", {"kind": "answer", "title": "New", "body": "current"})
        assert [c["title"] for c in r.of("card")] == ["New"]

    run(go())


def test_every_connect_gets_hello_first_and_a_tagged_status_snapshot(monkeypatch):
    from fastapi.testclient import TestClient

    from server.orchestrator import main

    main.engine.recorder.enabled = False
    with TestClient(main.app) as client:
        for _ in range(2):  # a reconnect resyncs again
            with client.websocket_connect("/", headers={"host": "127.0.0.1:8787"}) as ws:
                first = ws.receive_json()
                assert first["type"] == "engine.hello"
                msgs = []
                for _ in range(40):
                    m = ws.receive_json()
                    msgs.append(m)
                    if m["type"] == "status":
                        break
                st = [m for m in msgs if m["type"] == "status"]
                assert st and "epoch" in st[-1]["payload"] and "gen" in st[-1]["payload"]


def test_disconnect_mid_work_cancels_cleanly(monkeypatch):
    import time

    from fastapi.testclient import TestClient

    from server.orchestrator import main

    main.engine.recorder.enabled = False
    sess = main.engine.session
    started = {"n": 0}

    async def slow(kind, text=None):
        started["n"] += 1
        await sess._status("thinking", detail="Writing a hint")
        await asyncio.sleep(60)

    monkeypatch.setattr(sess, "_action", slow)
    with TestClient(main.app) as client:
        with client.websocket_connect("/", headers={"host": "127.0.0.1:8787"}) as ws:
            assert ws.receive_json()["type"] == "engine.hello"
            ws.send_json({"type": "action", "payload": {"kind": "hint"}})
            for _ in range(60):  # until the island says thinking: the command is running
                m = ws.receive_json()
                if m["type"] == "status" and m["payload"]["state"] == "thinking":
                    break
            else:
                raise AssertionError("the action never set thinking")
            assert sess.status == "thinking" and started["n"] == 1
        # the app left mid-work: the command is cancelled and thinking resolves
        for _ in range(100):
            if sess.status != "thinking" and not main.engine.hub.clients:
                break
            time.sleep(0.05)
        assert not main.engine.hub.clients
        assert sess.status != "thinking"
        with client.websocket_connect("/", headers={"host": "127.0.0.1:8787"}) as ws:  # the next client is resynced
            assert ws.receive_json()["type"] == "engine.hello"
            st = None
            for _ in range(40):
                m = ws.receive_json()
                if m["type"] == "status":
                    st = m["payload"]
                    break
            assert st is not None and st["state"] != "thinking"
