"""miyagi cloud routing and the Opus guard (server.config), offline: no client makes a call here.

Cloud mode sends the install token to the proxy; a Settings key (bring-your-own-key) goes straight to the provider;
Opus never runs by default, never through the cloud, and the refusal fallback never names it.
"""

from __future__ import annotations

import os

import pytest

from server import config

HOST = "https://cloud.example.test"
CLOUD = HOST + "/v1"  # miyagiCloud / MIYAGI_CLOUD_URL is the proxy's API root, https://<host>/v1
TOKEN = "mi_" + "a" * 43


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in (*config.KEY_ENV.values(), config.CLOUD_URL_ENV, "MIYAGI_ALLOW_OPUS", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    config.set_app_keys({})
    yield
    config.set_app_keys({})


def test_cloud_mode_routes_the_token_to_the_proxy():
    config.set_app_keys({"miyagiCloud": CLOUD + "/", "miyagiToken": TOKEN})
    assert config.mode("anthropic") == "cloud" and config.mode("gemini") == "cloud"
    kw = config.anthropic_kwargs("coach")
    assert kw["api_key"] == TOKEN
    assert kw["base_url"] == CLOUD + "/anthropic"
    assert kw["default_headers"] == {"x-miyagi-role": "coach"}
    g = config.gemini_kwargs("lesson")
    assert g["api_key"] == TOKEN and g["http_options"].base_url == CLOUD + "/gemini"
    assert g["http_options"].api_version == "v1beta"  # the proxy serves /v1/gemini/v1beta/models/{m} only
    assert config.key_source("anthropic") == "cloud" and config.cloud_status() == "ok"
    assert not config.gemini_text_ok()


def test_cloud_paths_match_the_proxy_routes():
    """claude/eng-proxy cloud/app.py serves /v1/anthropic/v1/messages and /v1/gemini/v1beta/models/{m}."""
    import anthropic
    from google import genai

    config.set_app_keys({"miyagiCloud": HOST + "/v1", "miyagiToken": TOKEN})
    kw = config.anthropic_kwargs("lesson")
    assert kw["base_url"] == "https://cloud.example.test/v1/anthropic"
    assert str(anthropic.Anthropic(**kw)._prepare_url("/v1/messages")) == HOST + "/v1/anthropic/v1/messages"
    g = config.gemini_kwargs("lesson")
    assert g["http_options"].base_url == "https://cloud.example.test/v1/gemini"
    req = genai.Client(**g)._api_client._build_request("post", "models/gemini-3.8-flash:generateContent", {})
    assert req.url == HOST + "/v1/gemini/v1beta/models/gemini-3.8-flash:generateContent"


def test_byok_key_goes_direct_even_with_the_cloud_on():
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN, "anthropic": "sk-ant-direct"})
    assert config.mode("anthropic") == "byok"
    kw = config.anthropic_kwargs("coach")
    assert kw == {"api_key": "sk-ant-direct", "base_url": config.ANTHROPIC_DIRECT_URL}
    assert config.key_source("anthropic") == "ok"
    assert config.mode("gemini") == "cloud"  # the other provider still uses the proxy


def test_env_key_without_cloud(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert config.mode("anthropic") == "env"
    assert config.anthropic_kwargs()["base_url"] == config.ANTHROPIC_DIRECT_URL
    assert config.cloud_status() == "off"


def test_cloud_url_without_token_is_not_cloud(monkeypatch):
    monkeypatch.setenv(config.CLOUD_URL_ENV, CLOUD)
    assert config.cloud_status() == "missing" and config.mode("anthropic") == "missing"
    assert config.anthropic_kwargs() == {}


def test_plain_http_cloud_url_is_refused():
    config.set_app_keys({"miyagiCloud": "http://cloud.example.test", "miyagiToken": TOKEN})
    assert config.cloud_url() is None and config.mode("anthropic") == "missing"


def test_opus_guard(monkeypatch):
    assert config.guard_model("claude-opus-5-5") == config.SONNET
    assert config.guard_model("claude-fable-5-2") == config.SONNET
    assert config.guard_model("claude-haiku-5-5") == "claude-haiku-5-5"
    monkeypatch.setenv("MIYAGI_ALLOW_OPUS", "1")
    assert config.guard_model("claude-opus-5-5") == "claude-opus-5-5"
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert config.guard_model("claude-opus-5-5") == config.SONNET  # the cloud never takes Opus


def test_fallback_never_reaches_opus():
    fb = config.fallback_kwargs("claude-sonnet-5-5")
    assert fb["fallbacks"] == "default" and fb["betas"] == [config.FALLBACK_BETA]  # Sonnet 5.5 -> Sonnet 5 only
    assert config.fallback_kwargs("claude-haiku-5-5") == {}
    assert config.fallback_kwargs("claude-opus-5-5") == {}  # not opted in


def test_safe_env_strips_keys():
    env = config.safe_env({"ANTHROPIC_API_KEY": "x", "MIYAGI_CLOUD_TOKEN": "t", "MIYAGI_CLOUD_URL": CLOUD,
                           "GOOGLE_API_KEY": "g", "TIGER_DATABASE_URL": "postgres://u", "PATH": "/usr/bin",
                           "MIYAGI_LESSONS_DIR": "/tmp/l"}, PYTHONUNBUFFERED="1")
    assert env == {"PATH": "/usr/bin", "MIYAGI_LESSONS_DIR": "/tmp/l", "PYTHONUNBUFFERED": "1"}


def test_apply_keys_never_exports_the_install_token(monkeypatch):
    """Learner subprocesses inherit os.environ: the token and the proxy URL must not be in it."""
    from server.orchestrator import main

    monkeypatch.setitem(main._ENV_AT_START, "anthropic", "")
    monkeypatch.setitem(main._ENV_AT_START, "gemini", "")
    status = main.apply_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert status["anthropic"] == "cloud" and status["cloud"] == "ok"
    assert TOKEN not in os.environ.values()
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "MIYAGI_CLOUD_TOKEN", "ANTHROPIC_BASE_URL"):
        assert var not in os.environ
    assert config.anthropic_kwargs("coach")["api_key"] == TOKEN  # the engine itself still routes it


class _Err(Exception):
    def __init__(self, status, body):
        super().__init__(str(body))
        self.status_code, self.body = status, body


def _proxy(status, kind, message="m"):
    """cloud/app.py error(): Anthropic's {type, error: {type, message}} plus Google's code/status."""
    return _Err(status, {"type": "error", "error": {"type": kind, "status": kind.upper(), "code": status,
                                                    "message": message}})


def test_cloud_errors():
    assert config.cloud_error(_Err(503, {"type": "miyagi_paused"})) == "miyagi_paused"
    assert config.cloud_error(_Err(429, {"type": "error", "error": {"type": "miyagi_quota"}})) == "miyagi_quota"
    assert config.cloud_error(_Err(401, {"type": "error"})) is None  # a direct key: a bad key, not the cloud
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert config.cloud_error(_Err(401, {"type": "error"})) == "miyagi_auth"


def test_cloud_errors_from_the_real_proxy_shapes():
    # the kill switch (cloud/app.py PROXY_ENABLED off): 503 proxy_disabled, cloud mode or not
    assert config.cloud_error(_proxy(503, "proxy_disabled")) == "miyagi_paused"
    # a disabled install / the quota stop mean nothing for a direct key
    assert config.cloud_error(_proxy(403, "permission_error")) is None
    assert config.cloud_error(_proxy(429, "rate_limit_error")) is None
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert config.cloud_error(_proxy(503, "proxy_disabled")) == "miyagi_paused"
    assert config.cloud_error(_proxy(401, "authentication_error")) == "miyagi_auth"  # unknown token
    assert config.cloud_error(_proxy(403, "permission_error")) == "miyagi_auth"  # install disabled
    assert config.cloud_error(_proxy(429, "rate_limit_error", "Daily limit reached for this install.")) == "miyagi_quota"
    # Anthropic's own 429, forwarded unchanged by the proxy: an ordinary rate limit (retried)
    assert config.cloud_error(_Err(429, {"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}})) is None
    assert config.cloud_error(_proxy(503, "upstream_not_configured")) is None
    # a Settings key for Claude: its 403 is Anthropic's, not the cloud's; Gemini still goes through the cloud
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN, "anthropic": "sk-ant-direct"})
    assert config.cloud_error(_proxy(403, "permission_error")) is None
    assert config.cloud_error(_proxy(403, "permission_error"), provider="gemini") == "miyagi_auth"


def test_cloud_errors_from_google_genai():
    from google.genai import errors

    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert config.cloud_error(errors.ServerError(503, _proxy(503, "proxy_disabled").body), "gemini") == "miyagi_paused"
    assert config.cloud_error(errors.ClientError(429, _proxy(429, "rate_limit_error").body), "gemini") == "miyagi_quota"
    google_429 = {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    assert config.cloud_error(errors.ClientError(429, google_429), "gemini") is None
