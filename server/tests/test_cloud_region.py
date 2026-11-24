"""451 region_unavailable (the cloud's region block, cloud/app.py D9), offline: the cloud is faked, no call leaves.

With the block on, /v1/install and every route that spends money (/v1/anthropic, /v1/gemini, the shared lesson cache's
build claim) answer 451 {"error": "region_unavailable", "message": ...} with x-should-retry: false. The engine:
  - reads it as its own case (config.cloud_error -> "miyagi_region"), never as a verdict on the install token: no
    cloud.token_invalid (so the app never re-mints), config.status.cloud unchanged
  - stops calling the cloud for the rest of the run (config.region_blocked): coach calls, scene looks, fast ask warm-ups,
    lesson builds and the shared lesson cache answer at once, with no request
  - tells the app once per run: cloud.notice {reason: "region_unavailable", status: 451}
"""

from __future__ import annotations

import asyncio

import anthropic
import httpx
import pytest

from server import config
from server.lesson import cloud_cache
from shared.contracts.events import engine_message

CLOUD = "https://cloud.example.test/v1"
TOKEN = "mi_" + "r" * 43
VID = "AXXnSzmpyoI"
VID2 = "dQw4w9WgXcQ"
BODY = {"error": "region_unavailable", "message": "miyagi isn't available in your region yet."}


def _resp(status: int = 451, body: dict | None = None, path: str = "/anthropic/v1/messages") -> httpx.Response:
    req = httpx.Request("POST", CLOUD + path, headers={"x-api-key": TOKEN})
    return httpx.Response(status, json=BODY if body is None else body, request=req,
                          headers={"x-should-retry": "false"})


def _sdk_451() -> anthropic.APIStatusError:
    """What the Anthropic SDK raises for the proxy's 451 (no retry: 451 is not retryable and x-should-retry is false)."""
    r = _resp()
    return anthropic.APIStatusError("region_unavailable", response=r, body=BODY)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in (*config.KEY_ENV.values(), config.CLOUD_URL_ENV):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv(cloud_cache.ENV_OFF, raising=False)
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    config._unknown.clear()
    monkeypatch.setattr(config, "_region_url", None)
    cloud_cache.reset()
    yield
    cloud_cache.reset()
    config.set_app_keys({})
    config._unknown.clear()


@pytest.fixture
def heard():
    got: list[dict] = []
    off = config.on_cloud_verdict(got.append)
    yield got
    off()


class _Cloud:
    """The shared lesson cache's routes: every call answers `reply` and is counted."""

    def __init__(self, reply: httpx.Response):
        self.reply, self.calls = reply, []

    def client(self, timeout):
        cloud = self

        class _C:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, params=None, headers=None):
                cloud.calls.append("GET")
                return cloud.reply

            async def post(self, url, params=None, headers=None):
                cloud.calls.append("POST")
                return cloud.reply

            async def put(self, url, content=None, headers=None):
                cloud.calls.append("PUT")
                return cloud.reply

        return _C()


# ------------------------------------------------------------------ install 451 / AI-call 451: config


def test_an_install_or_ai_call_451_is_its_own_case_never_a_token_verdict(heard):
    install_451 = anthropic.APIStatusError("region_unavailable", response=_resp(path="/install"), body=BODY)
    assert config.cloud_error(install_451) == "miyagi_region"
    assert config.cloud_error(_sdk_451()) == "miyagi_region"
    assert config.CLOUD_ERRORS["miyagi_region"] == "miyagi isn't available in your region yet."
    # not a token verdict: no re-mint, config.status.cloud stays "ok"
    assert not config.token_invalid_pending() and config.cloud_status() == "ok" and config.cloud_verdict() is None
    assert config.region_blocked() and config.region_blocked("gemini") and config.region_blocked(None)
    # one event for the run, however many calls were turned away
    assert heard == [{"state": None, "reason": "region_unavailable", "token_invalid": False, "ttl": None, "region": True}]


def test_the_block_follows_the_cloud_url_not_the_token(heard):
    config.cloud_error(_sdk_451())
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": "mi_" + "s" * 43})  # a new token does not help
    assert config.region_blocked()
    config.set_app_keys({"anthropic": "sk-ant-direct", "miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert not config.region_blocked("anthropic")  # a Settings key goes direct: not through the cloud
    config.set_app_keys({"miyagiToken": TOKEN})  # the app turned the cloud off: nothing to block
    assert not config.region_blocked()


def test_a_direct_key_451_without_the_body_is_not_the_cloud():
    config.set_app_keys({"anthropic": "sk-ant-direct"})
    assert config.cloud_error(anthropic.APIStatusError("x", response=_resp(body={"type": "error"}), body={})) is None
    assert not config.region_blocked()


# ------------------------------------------------------------------ no more calls after a 451


def test_after_a_451_no_ai_call_is_made(monkeypatch):
    from server.coach import fast_ask, llm, scene
    from server.lesson import claude as lesson_claude

    def no_client(*a, **k):
        raise AssertionError("a call was made after the region block")

    monkeypatch.setattr(llm, "get_client", no_client)
    monkeypatch.setattr(fast_ask, "get_client", no_client)
    monkeypatch.setattr(lesson_claude, "client", no_client)
    monkeypatch.setattr(llm, "offline_mode", lambda: False)
    config.cloud_error(_sdk_451())

    async def go():
        with pytest.raises(llm.CoachLLMError) as e:
            await llm.structured_call(purpose="coach test", model="claude-haiku-5-5", system=[], user_text="hi",
                                      schema={"type": "object"})
        assert e.value.kind == "cloud" and "miyagi_region" in str(e.value)
        with pytest.raises(llm.CoachLLMError) as e:
            await scene.look(None, {"title": "t", "instructions": "i"})
        assert e.value.kind == "cloud"
        assert (await fast_ask.warm(source="test"))["skipped"] == "region"
        with pytest.raises(RuntimeError, match="miyagi_region"):
            await lesson_claude._call("claude-haiku-5-5", "system", "user", effort="low", schema=None)

    asyncio.run(go())


def test_a_cache_451_denies_the_claim_and_stops_the_cache(monkeypatch):
    cloud = _Cloud(_resp(path="/lessons/x/build"))
    monkeypatch.setattr(cloud_cache, "_client", cloud.client)
    heard: list[dict] = []
    off = cloud_cache.on_notice(heard.append)

    async def go():
        assert await cloud_cache.claim(VID) == "denied"
        assert await cloud_cache.claim(VID2) == "error"  # blocked: no request
        assert await cloud_cache.lookup(VID2, source_url="u", goal="g", workdir="/tmp", key="k") is None

    asyncio.run(go())
    off()
    assert cloud.calls == ["POST"]
    assert heard == [{"reason": "region_unavailable", "status": 451}]
    assert config.region_blocked()  # AI calls stop too


# ------------------------------------------------------------------ the engine: one cloud.notice per run


class _WS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, msg):
        self.sent.append(msg)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import main
    from server.orchestrator.hub import Hub

    for name in main.KEY_ENV:
        monkeypatch.setitem(main._ENV_AT_START, name, "")
    e = main.Engine()
    e.hub = Hub(strict=True)  # every frame is checked against shared/contracts/events.py
    ws = _WS()
    e.hub.clients.add(ws)
    yield e, ws
    for off in (e._cloud_off, e._notice_off):
        if off:
            off()


def test_one_region_notice_per_run_and_nothing_else(engine, monkeypatch):
    e, ws = engine
    cloud = _Cloud(_resp(path="/lessons/x/build"))
    monkeypatch.setattr(cloud_cache, "_client", cloud.client)

    async def go():
        e.watch_cloud()
        for _ in range(3):
            config.cloud_error(_sdk_451())  # AI calls turned away
        await asyncio.to_thread(config.cloud_error, _sdk_451())  # from a worker thread too
        assert await cloud_cache.claim(VID) == "error"  # blocked already: the cache asks nothing
        cloud_cache.reset()
        config._region_url = None  # as if a fresh 451 came from the cache first, later in the run
        assert await cloud_cache.claim(VID2) == "denied"
        config.cloud_error(_sdk_451())
        await asyncio.sleep(0.05)

    asyncio.run(go())
    assert cloud.calls == ["POST"]
    assert [m["type"] for m in ws.sent] == ["cloud.notice"]  # no error, no config.status, no cloud.token_invalid
    msg = ws.sent[0]
    assert msg["payload"] == {"reason": "region_unavailable", "status": 451}
    assert engine_message("cloud.notice", msg["payload"]) == msg
    assert TOKEN not in repr(ws.sent)
