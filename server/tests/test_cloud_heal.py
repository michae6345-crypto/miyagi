"""Install token self-heal (server.config verdicts + the orchestrator's cloud.token_invalid), offline: no client makes a call.

A 401 from the miyagi cloud means the proxy does not know the install token: the app hears `cloud.token_invalid` once per
token and mints a new one. A 403 (an operator disabled the install) is never healed: config.status.cloud says
"unauthorized". Paused / over quota show in config.status.cloud and lapse on their own. A new token clears the verdict.
"""

from __future__ import annotations

import asyncio

import anthropic
import httpx
import pytest

from server import config
from shared.contracts.events import ConfigStatus, engine_message

CLOUD = "https://cloud.example.test/v1"
TOKEN = "mi_" + "a" * 43
TOKEN2 = "mi_" + "b" * 43


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in (*config.KEY_ENV.values(), config.CLOUD_URL_ENV):
        monkeypatch.delenv(var, raising=False)
    config.set_app_keys({})
    config._unknown.clear()
    yield
    config.set_app_keys({})
    config._unknown.clear()


@pytest.fixture
def heard():
    got: list[dict] = []
    off = config.on_cloud_verdict(got.append)
    yield got
    off()


class _Err(Exception):
    def __init__(self, status, body):
        super().__init__(str(body))
        self.status_code, self.body = status, body


def _proxy(status, kind, message="m"):
    """cloud/app.py error(): Anthropic's {type, error: {type, message}} plus Google's code/status."""
    return _Err(status, {"type": "error", "error": {"type": kind, "status": kind.upper(), "code": status,
                                                    "message": message}})


def _sdk_401(token: str) -> anthropic.AuthenticationError:
    """What the Anthropic SDK raises for the proxy's 401, with the request (and the key it carried) attached."""
    req = httpx.Request("POST", CLOUD + "/anthropic/v1/messages", headers={"x-api-key": token})
    body = {"type": "error", "error": {"type": "authentication_error", "status": "AUTHENTICATION_ERROR", "code": 401,
                                       "message": "Unknown install token. Get a new one at /v1/install."}}
    resp = httpx.Response(401, json=body, request=req)
    return anthropic.AuthenticationError("Unknown install token", response=resp, body=body)


def test_unknown_token_is_reported_once_per_token(heard):
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert config.cloud_status() == "ok"
    for _ in range(3):  # several failing calls: one verdict, one token_invalid
        assert config.cloud_error(_proxy(401, "authentication_error")) == "miyagi_auth"
    assert config.cloud_status() == "unauthorized"
    assert config.token_invalid_pending()
    assert heard == [{"state": "unauthorized", "reason": "unknown_token", "token_invalid": True, "ttl": None}]
    assert TOKEN not in repr(heard) and TOKEN not in repr(config._verdict)  # only a short hash is kept

    # the app mints a new token: the verdict is gone, config.status.cloud is ok again
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN2})
    assert config.cloud_status() == "ok" and not config.token_invalid_pending()
    # ...and if the proxy forgets that one too, it is a new token: reported again (the app's backoff stops a loop)
    config.cloud_error(_proxy(401, "authentication_error"))
    assert [e["token_invalid"] for e in heard] == [True, True]


def test_the_same_token_sent_again_keeps_its_verdict(heard):
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    config.cloud_error(_proxy(401, "authentication_error"))
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})  # a reconnect re-sends config.keys
    assert config.cloud_status() == "unauthorized" and config.token_invalid_pending()
    config.cloud_error(_proxy(401, "authentication_error"))
    assert len(heard) == 1


def test_unknown_outlives_a_later_paused_verdict(heard):
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    config.cloud_error(_proxy(401, "authentication_error"))
    config.cloud_error(_proxy(503, "proxy_disabled"))  # the kill switch answers before the token check
    assert config.cloud_status() == "unauthorized" and config.token_invalid_pending()
    config.cloud_error(_proxy(401, "authentication_error"))
    assert [e["token_invalid"] for e in heard].count(True) == 1


def test_disabled_install_is_unauthorized_without_token_invalid(heard):
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert config.cloud_error(_proxy(403, "permission_error", "This install has been disabled.")) == "miyagi_auth"
    config.cloud_error(_proxy(403, "permission_error"))
    assert config.cloud_status() == "unauthorized" and not config.token_invalid_pending()
    assert heard == [{"state": "unauthorized", "reason": "disabled", "token_invalid": False, "ttl": None}]


def test_paused_and_quota_lapse(heard, monkeypatch):
    real = config.time.monotonic
    skew = [0.0]
    monkeypatch.setattr(config.time, "monotonic", lambda: real() + skew[0])
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert config.cloud_error(_proxy(503, "proxy_disabled")) == "miyagi_paused"
    assert config.cloud_status() == "paused"
    assert heard[-1]["reason"] == "paused" and heard[-1]["ttl"] == config.PAUSED_TTL_S
    config.cloud_error(_proxy(503, "proxy_disabled"))
    assert len(heard) == 1  # still paused: no new event
    skew[0] = config.PAUSED_TTL_S + 1
    assert config.cloud_status() == "ok"  # lapsed: the next refused call says so again
    config.cloud_error(_proxy(429, "rate_limit_error", "Daily limit reached for this install."))
    assert config.cloud_status() == "quota" and heard[-1]["reason"] == "quota" and heard[-1]["ttl"] >= 60
    assert not any(e["token_invalid"] for e in heard)


def test_no_verdict_for_a_direct_key_or_a_stale_token(heard):
    config.set_app_keys({"anthropic": "sk-ant-direct"})
    assert config.cloud_error(_proxy(401, "authentication_error")) is None
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN, "anthropic": "sk-ant-direct"})
    config.cloud_error(_proxy(401, "authentication_error"))  # Claude goes direct: Anthropic's 401, not the cloud's
    assert heard == [] and config.cloud_status() == "ok"
    # a call made with the old token ends after the app sent a new one: not the new token's verdict
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN2})
    assert config.cloud_error(_sdk_401(TOKEN)) == "miyagi_auth"
    assert heard == [] and config.cloud_status() == "ok"
    assert config.cloud_error(_sdk_401(TOKEN2)) == "miyagi_auth"  # the real SDK error with the current token
    assert heard[-1]["token_invalid"] and config.cloud_status() == "unauthorized"


def test_a_failing_listener_never_breaks_the_caller():
    def boom(_):
        raise RuntimeError("listener")

    off = config.on_cloud_verdict(boom)
    try:
        config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
        assert config.cloud_error(_proxy(401, "authentication_error")) == "miyagi_auth"
    finally:
        off()


# ------------------------------------------------------------------ the orchestrator tells the app


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
    # not strict: config.status in cloud mode carries anthropic/gemini "cloud", which KeyState in events.py does not
    # list yet (true before this change too); cloud.token_invalid is checked against the contract below
    e.hub = Hub(strict=False)
    ws = _WS()
    e.hub.clients.add(ws)
    yield e, ws
    if e._cloud_off:
        e._cloud_off()


def _types(ws):
    return [m["type"] for m in ws.sent]


def test_engine_sends_token_invalid_once_and_a_fresh_status(engine):
    e, ws = engine

    async def go():
        e.watch_cloud()
        await e.dispatch({"type": "config.keys", "payload": {"miyagiCloud": CLOUD, "miyagiToken": TOKEN}})
        assert ws.sent[-1]["payload"]["cloud"] == "ok"
        for _ in range(3):
            config.cloud_error(_proxy(401, "authentication_error"))
        # a worker thread's call (a sync client in asyncio.to_thread) lands on the loop too
        await asyncio.to_thread(config.cloud_error, _proxy(401, "authentication_error"))
        await asyncio.sleep(0.05)
        assert _types(ws).count("cloud.token_invalid") == 1
        tin = next(m for m in ws.sent if m["type"] == "cloud.token_invalid")
        assert tin["payload"] == {"reason": "unknown_token"} and TOKEN not in repr(ws.sent)
        assert engine_message("cloud.token_invalid", tin["payload"]) == tin  # in shared/contracts/events.py
        ConfigStatus.model_validate(ws.sent[-1]["payload"])  # anthropic / gemini "cloud" (a KeyState), cloud a CloudState
        assert ws.sent[-1] == {"type": "config.status", "payload": {**ws.sent[-1]["payload"], "cloud": "unauthorized"}}
        # the app heals: config.keys with a new token -> cloud ok, nothing more about the old one
        await e.dispatch({"type": "config.keys", "payload": {"miyagiCloud": CLOUD, "miyagiToken": TOKEN2}})
        assert ws.sent[-1]["type"] == "config.status" and ws.sent[-1]["payload"]["cloud"] == "ok"
        assert _types(ws).count("cloud.token_invalid") == 1

    asyncio.run(go())


def test_engine_repeats_token_invalid_when_the_dead_token_comes_back(engine):
    e, ws = engine

    async def go():
        e.watch_cloud()
        await e.dispatch({"type": "config.keys", "payload": {"miyagiCloud": CLOUD, "miyagiToken": TOKEN}})
        config.cloud_error(_proxy(401, "authentication_error"))
        await asyncio.sleep(0.01)
        await e.dispatch({"type": "config.keys", "payload": {"miyagiCloud": CLOUD, "miyagiToken": TOKEN}})
        assert _types(ws)[-2:] == ["config.status", "cloud.token_invalid"]

    asyncio.run(go())


def test_engine_disabled_install_gets_no_token_invalid(engine):
    e, ws = engine

    async def go():
        e.watch_cloud()
        await e.dispatch({"type": "config.keys", "payload": {"miyagiCloud": CLOUD, "miyagiToken": TOKEN}})
        config.cloud_error(_proxy(403, "permission_error", "This install has been disabled."))
        config.cloud_error(_proxy(403, "permission_error"))
        await asyncio.sleep(0.01)
        assert "cloud.token_invalid" not in _types(ws)
        assert [m["payload"]["cloud"] for m in ws.sent if m["type"] == "config.status"] == ["ok", "unauthorized"]

    asyncio.run(go())
