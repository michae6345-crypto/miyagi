"""Lesson tests never reach a paid API or the network: no .env, no keys, and real clients raise."""

import pytest

_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY")
# Per test only (the autouse fixture below), so other modules' tests keep their own environment.
# server.lesson loads .env lazily, at call time, so the fixture's LESSON_NO_DOTENV is always in effect.


class _Blocked:
    def __init__(self, *a, **k):
        raise AssertionError("tests must not create a real API client (stub it)")


def block_network(monkeypatch, *, http: bool = True) -> None:
    import anthropic
    from google import genai

    from server.lesson import claude, gemini

    import os

    for k in [k for k in os.environ if k.startswith("LESSON_") or k == "ORCH_PREBUILD"]:
        monkeypatch.delenv(k, raising=False)  # .env may already be in the process (another module loaded it)
    monkeypatch.setenv("LESSON_NO_DOTENV", "1")
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _Blocked)
    monkeypatch.setattr(anthropic, "Anthropic", _Blocked)
    monkeypatch.setattr(genai, "Client", _Blocked)
    monkeypatch.setattr(claude, "_client", None)
    monkeypatch.setattr(gemini, "_clients", {})
    from server.lesson import materials

    async def no_materials(url, **k):  # the tutorial's linked code: materials tests serve fixtures instead
        raise RuntimeError(f"offline test: no materials fetch ({url})")

    monkeypatch.setattr(materials, "_http_get", no_materials)
    monkeypatch.setattr(materials, "_tasks", {})
    if http:
        import httpx
        import requests

        async def no_send(self, request, *a, **k):
            raise AssertionError(f"tests must not reach the network: {request.url}")

        def no_req(self, request, *a, **k):
            raise AssertionError(f"tests must not reach the network: {request.url}")

        monkeypatch.setattr(httpx.AsyncClient, "send", no_send)
        monkeypatch.setattr(requests.Session, "send", no_req)


@pytest.fixture(autouse=True)
def _no_paid_calls(monkeypatch):
    block_network(monkeypatch)
