"""miyagi cloud routing and the Opus guard (server.config), offline: no client makes a call here.

Cloud mode sends the install token to the proxy; a Settings key (bring-your-own-key) goes straight to the provider;
Opus never runs by default, never through the cloud, and the refusal fallback never names it.
"""

from __future__ import annotations

import pytest

from server import config

CLOUD = "https://cloud.example.test"
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
    assert config.key_source("anthropic") == "cloud" and config.cloud_status() == "ok"
    assert not config.gemini_text_ok()


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


class _Err(Exception):
    def __init__(self, status, body):
        super().__init__(str(body))
        self.status_code, self.body = status, body


def test_cloud_errors():
    assert config.cloud_error(_Err(503, {"type": "miyagi_paused"})) == "miyagi_paused"
    assert config.cloud_error(_Err(429, {"type": "error", "error": {"type": "miyagi_quota"}})) == "miyagi_quota"
    assert config.cloud_error(_Err(401, {"type": "error"})) is None  # a direct key: a bad key, not the cloud
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    assert config.cloud_error(_Err(401, {"type": "error"})) == "miyagi_auth"
