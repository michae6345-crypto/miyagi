"""config.status (orchestrator key_status) always fits the ConfigStatus contract, in every key mode, offline.

key_source() answers 'cloud' when calls go through the miyagi cloud; KeyState has to carry it, or the app's validator
drops the whole config.status event and Settings shows stale rows.
"""

from __future__ import annotations

from typing import get_args

import pytest

from server import config
from server.orchestrator.main import key_status
from shared.contracts.events import ConfigStatus, KeyState, engine_message

CLOUD = "https://cloud.example.test/v1"  # server/tests/conftest.py allows this reserved host
TOKEN = "mi_" + "a" * 43


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in (*config.KEY_ENV.values(), config.CLOUD_URL_ENV):
        monkeypatch.delenv(var, raising=False)
    config.set_app_keys({})
    config._unknown.clear()
    yield
    config.set_app_keys({})
    config._unknown.clear()


def _valid(status: dict) -> None:
    ConfigStatus.model_validate(status)
    assert engine_message("config.status", status)["payload"] == status


def test_cloud_mode_status_validates():
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    status = key_status()
    assert status["anthropic"] == "cloud" and status["gemini"] == "cloud" and status["cloud"] == "ok"
    _valid(status)


def test_no_keys_status_validates():
    status = key_status()
    assert status["anthropic"] == "missing" and status["cloud"] == "off"
    _valid(status)


def test_byok_and_env_status_validates(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-gemini")
    config.set_app_keys({"anthropic": "sk-ant-direct"})
    status = key_status()
    assert status["anthropic"] == "ok" and status["gemini"] == "env"
    _valid(status)


def test_every_key_source_value_is_a_key_state():
    assert {"ok", "cloud", "env", "missing", "invalid"} <= set(get_args(KeyState))
