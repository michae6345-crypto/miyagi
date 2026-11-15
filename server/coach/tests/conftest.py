"""Hermetic environment for every coach test: no .env, no keys, no model overrides, no modes.

The shared .env (COACH_MODEL_DIAGNOSE, real Bright Data keys…) may already be in os.environ when pytest
starts (another module ran load_dotenv at import). Every coach test starts from a clean slate, and a
test that needs a value sets it itself with monkeypatch.
"""

from __future__ import annotations

import os

import pytest

from server.coach import llm

PREFIXES = ("COACH_", "ANTHROPIC_", "BRIGHTDATA_", "ELEVENLABS_", "GEMINI_")
NAMES = ("DEMO", "ORCH_STUBS", "TUT_ENV")


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith(PREFIXES) or k in NAMES:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_load_env", lambda: None)  # never read the shared .env
    monkeypatch.setattr(llm, "_local_keys", {})  # no app-provided keys (BYOK)
    try:  # integration/live: llm.get_key delegates to server.config
        import server.config as cfg

        if hasattr(cfg, "_app_keys"):
            monkeypatch.setattr(cfg, "_app_keys", {})
    except ImportError:
        pass
    yield
