"""cloud.notice: the shared lesson cache's refused build claim reaches the app, offline (the cloud is faked, no call leaves).

lesson/cloud_cache.py claim() hears a 401 signin_required or a 429 cap and calls its on_notice listeners; the engine
(Engine.watch_cloud) sends each one to the app as `cloud.notice {reason, status, resets_at?}`, validated against
shared/contracts/events.py. Only those three fields: never the install token or a user id. The lesson builds here either
way, so the notice is the only thing sent: no `error`, no config.status, no cloud.token_invalid.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from server import config
from server.lesson import cloud_cache
from shared.contracts.events import engine_message

CLOUD = "https://cloud.example.test/v1"
TOKEN = "mi_" + "c" * 43
VID = "AXXnSzmpyoI"
VID2 = "dQw4w9WgXcQ"


class _WS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, msg):
        self.sent.append(msg)


class _Claims:
    """The claim route only: each POST answers the next reply (the last one repeats)."""

    def __init__(self, *replies: httpx.Response):
        self.replies = list(replies)
        self.posts = 0

    def client(self, timeout):
        claims = self

        class _C:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, params=None, headers=None):
                claims.posts += 1
                return claims.replies.pop(0) if len(claims.replies) > 1 else claims.replies[0]

        return _C()


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv(cloud_cache.ENV_OFF, raising=False)
    monkeypatch.setattr(config, "cloud_url", lambda: CLOUD)
    monkeypatch.setattr(config, "cloud_token", lambda: TOKEN)
    verdicts: list = []
    monkeypatch.setattr(config, "cloud_error", lambda *a, **k: verdicts.append(a))  # a notice is never a token verdict
    from server.orchestrator import main
    from server.orchestrator.hub import Hub

    cloud_cache.reset()
    e = main.Engine()
    e.hub = Hub(strict=True)  # every frame is checked against shared/contracts/events.py
    ws = _WS()
    e.hub.clients.add(ws)
    yield e, ws, verdicts
    for off in (e._cloud_off, e._notice_off):
        if off:
            off()
    cloud_cache.reset()


def _signin() -> httpx.Response:
    return httpx.Response(401, json={"error": "signin_required", "message": "Sign in to build new lessons."})


def _cap() -> httpx.Response:
    return httpx.Response(429, json={"type": "error", "error": {
        "type": "miyagi_quota", "limit": "lesson_builds", "resets_at": "2026-12-01T00:00:00Z", "user_id": "u-123"}})


def test_signin_required_and_a_cap_are_sent_as_cloud_notice(engine, monkeypatch):
    e, ws, verdicts = engine
    claims = _Claims(_signin(), _cap())
    monkeypatch.setattr(cloud_cache, "_client", claims.client)

    async def go():
        e.watch_cloud()
        e.watch_cloud()  # a second call never registers a second listener
        assert await cloud_cache.claim(VID) == "denied"
        # a worker thread's claim (a to_thread / sync path) lands on the loop too
        assert await asyncio.to_thread(asyncio.run, cloud_cache.claim(VID2)) == "denied"
        await asyncio.sleep(0.05)

    asyncio.run(go())
    assert claims.posts == 2
    notices = [m for m in ws.sent if m["type"] == "cloud.notice"]
    assert [m["payload"] for m in notices] == [
        {"reason": "signin_required", "status": 401},
        {"reason": "lesson_builds", "status": 429, "resets_at": "2026-12-01T00:00:00Z"},
    ]
    for m in notices:
        assert engine_message("cloud.notice", m["payload"]) == m  # in shared/contracts/events.py
    # nothing else: no error frame (no double fire with the app's error {notice} fallback), no token heal, no status
    assert [m["type"] for m in ws.sent] == ["cloud.notice", "cloud.notice"]
    assert verdicts == []
    assert TOKEN not in repr(ws.sent) and "u-123" not in repr(ws.sent) and "user_id" not in repr(ws.sent)


def test_one_notice_per_refused_claim_and_none_after_stop(engine, monkeypatch):
    e, ws, _ = engine
    monkeypatch.setattr(cloud_cache, "_client", _Claims(_signin()).client)

    async def go():
        e.watch_cloud()
        await cloud_cache.claim(VID)
        await cloud_cache.claim(VID)  # the same video again: the cloud is not asked twice, no second notice
        await asyncio.sleep(0.01)
        await e.stop()
        await cloud_cache.claim(VID2)  # after stop: the listener is gone
        await asyncio.sleep(0.01)

    asyncio.run(go())
    assert [m["type"] for m in ws.sent if m["type"] in ("cloud.notice", "error")] == ["cloud.notice"]
    assert e._notice_off is None


def test_a_bad_notice_is_dropped_not_sent(engine):
    e, ws, _ = engine

    async def go():
        e.watch_cloud()
        e._on_cloud_notice({"status": 401})  # no reason
        e._on_cloud_notice({"reason": "x", "status": "nope"})
        e._on_cloud_notice({"reason": "anon_daily_cap", "status": 429, "resets_at": 5, "token": TOKEN})
        await asyncio.sleep(0.01)

    asyncio.run(go())
    assert [m["payload"] for m in ws.sent] == [{"reason": "anon_daily_cap", "status": 429}]
