"""ask.warm (Nov 22, push to talk speed): offline, with a fake Anthropic transport. Nothing leaves this process.

- the warm-up sends the circle ask's own prefix (model, system with cache_control, output format, thinking, effort),
  1 output token, on a Haiku / Sonnet id (never Opus), through the one keep-alive client;
- the engine keeps a gap (one warm-up per GAP_S, one at a time) and lists ask.warm only with the real coach;
- the command parses (also before the contract lists it), never queues, and never replies.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from server.coach import circle, llm
from server.orchestrator import main
from server.orchestrator.ask_warm import AskWarm
from server.orchestrator.modules import Modules

REGION = {"x": 100.0, "y": 200.0, "w": 300.0, "h": 80.0, "displayId": 1, "scale": 2.0}
OBS = {"blocks": [{"text": "import numpy as np", "rect": {"x": 180, "y": 220, "w": 160, "h": 18}, "app": "Code"}],
       "screen": {"x": 0, "y": 0, "w": 1512, "h": 982}, "scale": 2.0, "app": "Code", "windows": []}


def run(coro):
    return asyncio.run(coro)


class FakeTransport:
    """Stands in for AsyncAnthropic: records every request, answers like a cache write."""

    def __init__(self):
        self.calls: list[dict] = []
        self.retrieved: list[str] = []
        msgs = SimpleNamespace(create=self._create)
        self.messages = msgs
        self.beta = SimpleNamespace(messages=msgs)
        self.models = SimpleNamespace(retrieve=self._retrieve)

    async def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(model=kw["model"], usage=SimpleNamespace(
            input_tokens=3, output_tokens=1, cache_creation_input_tokens=900, cache_read_input_tokens=0))

    async def _retrieve(self, model):
        self.retrieved.append(model)


@pytest.fixture
def transport(monkeypatch):
    t = FakeTransport()
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.delenv("ORCH_STUBS", raising=False)
    monkeypatch.setattr(llm, "get_client", lambda: t)
    monkeypatch.setattr(llm, "has_credentials", lambda: True)
    monkeypatch.setattr(llm, "cloud_mode", lambda: False)
    monkeypatch.setattr(llm, "record_cost", lambda *a, **k: 0.0)
    return t


def test_warm_sends_the_circle_asks_own_prefix(transport, monkeypatch):
    out = run(circle.warm(None))
    assert out["cache"] == [900] and len(transport.calls) == 1
    w = transport.calls[0]
    assert w["model"] in ("claude-haiku-5-5", "claude-sonnet-5-5") and "opus" not in w["model"]
    assert w["max_tokens"] == 1  # max_tokens 0 is rejected with structured outputs
    assert w["thinking"] == {"type": "disabled"} and w["output_config"]["effort"] == "low"
    assert w["output_config"]["format"]["schema"] == circle.SCHEMA
    assert w["system"][0]["text"] == circle.CIRCLE_SYSTEM and all("cache_control" in b for b in w["system"])

    # The real ask, through the same request builder: the same prefix (only the user turn differs).
    async def real(**kw):
        api, kwargs = llm._request(transport, kw["model"], kw["system"], kw["user_content"], kw["schema"], kw["effort"],
                                   kw["max_tokens"], kw["thinking"])
        await api.create(**kwargs)
        return llm.CallResult(data={"title": "numpy", "body": "This imports numpy.", "box_id": -1, "label": ""},
                              model=kw["model"])

    monkeypatch.setattr(llm, "structured_call_retrying", real)
    run(circle.circle_ask(None, "what is this", REGION, obs=OBS, image=None))
    a = transport.calls[1]
    for k in ("model", "system", "thinking", "output_config"):
        assert a[k] == w[k], k
    assert a.get("betas") == w.get("betas") and a.get("fallbacks") == w.get("fallbacks")


def test_warm_reuses_the_keep_alive_client(monkeypatch):
    seen = []

    class Client:
        def __init__(self, **kw):
            seen.append(kw)

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Client)
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_client_kwargs", lambda: {"api_key": "k-test"})
    assert llm.get_client() is llm.get_client() and len(seen) == 1


def test_warm_never_raises_and_skips_offline(transport, monkeypatch):
    monkeypatch.setenv("ORCH_STUBS", "coach")
    assert run(circle.warm(None)) == {"skipped": "offline"} and transport.calls == []
    monkeypatch.delenv("ORCH_STUBS")

    async def boom(requests):
        raise RuntimeError("no")

    monkeypatch.setattr(llm, "warm", boom)
    assert run(circle.warm(None)) == {"error": "RuntimeError"}


def test_modules_warm_only_with_the_real_coach(transport):
    assert Modules(demo=True).has_circle_warm() is False
    assert run(Modules(demo=True).circle_warm(None)) is None
    assert Modules(demo=False, force_stubs="coach").has_circle_warm() is False
    real = Modules(demo=False, force_stubs="lesson,finder,diagrams")
    assert real.has_circle_warm() is True
    assert run(real.circle_warm(None))["cache"] == [900]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _session(calls, available=True, result=None):
    async def circle_warm(step):
        calls.append(step)
        await asyncio.sleep(0)
        return result if result is not None else {"cache": [900], "cache_s": 0.2}

    m = SimpleNamespace(has_circle_warm=lambda: available, circle_warm=circle_warm)
    return SimpleNamespace(m=m, step={"id": "s1"})


def test_gap_one_at_a_time_and_unavailable():
    async def go():
        calls: list = []
        clock = Clock()
        w = AskWarm(_session(calls), gap_s=240, clock=clock)
        assert w.kick("a-1") is True
        assert w.kick("a-2") is False  # one at a time
        await w.task
        clock.t += 30
        assert w.kick("a-3") is False  # within the gap: no second cache write
        clock.t += 211
        assert w.kick("a-4") is True
        await w.task
        assert calls == [{"id": "s1"}, {"id": "s1"}]  # the step the ask would be about
        off = AskWarm(_session(calls, available=False), clock=clock)
        assert off.available() is False and off.kick("b-1") is False

        skipped = AskWarm(_session([], result={"skipped": "no key"}), gap_s=240, clock=clock)
        assert skipped.kick("c-1") is True
        await skipped.task
        assert skipped.kick("c-2") is True  # nothing was written: the next hold may try again
        await skipped.task

    run(go())


def test_engine_parses_lists_and_handles_ask_warm():
    assert "ask.warm" in main.V2_COMMANDS and "ask.warm" in main.V2_INSTANT  # never waits behind a build
    msg = main.parse_command({"type": "ask.warm", "payload": {"pttId": "k3x-12"}})
    assert msg.type == "ask.warm" and getattr(msg.payload, "pttId", None) == "k3x-12"
    bad = main.parse_command({"type": "ask.warm", "payload": {"pttId": "../../etc"}})
    assert getattr(bad.payload, "pttId", "x") is None
    assert main.parse_command({"type": "ask.warm"}).type == "ask.warm"

    kicked, replies = [], []
    fake = SimpleNamespace(session=SimpleNamespace(note_app_v2=lambda t: None), ensure_status=lambda: None,
                           ask_warm=SimpleNamespace(kick=kicked.append, available=lambda: True))

    async def reply(t, p):
        replies.append(t)

    run(main.Engine.handle_v2(fake, "ask.warm", msg.payload, reply))
    assert kicked == ["k3x-12"] and replies == []  # no reply event
    assert "ask.warm" in main.Engine.capabilities(fake)
    fake.ask_warm = SimpleNamespace(available=lambda: False)
    assert "ask.warm" not in main.Engine.capabilities(fake)
    assert "ask.warm" not in main.Engine.capabilities(SimpleNamespace(session=SimpleNamespace()))
