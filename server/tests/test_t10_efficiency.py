"""t10 speed review: the step-start diagram prefetch serves the Diagram press (1 Sonnet call, not 2, and instant),
however the screen changed meanwhile. Counted with a stubbed client (no network, no key)."""
from __future__ import annotations

import asyncio
import itertools
import json
from types import SimpleNamespace

from server import diagrams
from server.orchestrator.tests.conftest import _isolated_and_free  # noqa: F401 (autouse: no paid keys, temp state)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- 1. diagram prefetch -> press

NET = {"kind": "network", "caption": "784 inputs, 10 outputs.", "graph": None,
       "network": {"layers": [784, 128, 10], "activation": "relu", "derivatives": [], "highlight": []}}


class CountingClient:
    def __init__(self, raw):
        self.raw, self.calls = raw, []
        self.messages = self.beta = self

    async def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", model="fake", usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                               content=[SimpleNamespace(type="text", text=json.dumps(self.raw))])


def test_diagram_prefetch_then_press_is_one_call(tmp_path, monkeypatch):
    import importlib

    build_mod = importlib.import_module("server.diagrams.build")
    from server.orchestrator.modules import Modules
    from server.orchestrator.tests.test_session import Rig, _to_step

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.setenv("ORCH_DIAGRAM_PREFETCH", "0")  # the prefetch is driven by hand below (no 2 s sleep)
    fake = CountingClient(NET)
    monkeypatch.setattr(build_mod, "_get_client", lambda: fake)
    diagrams.clear_cache()
    rig = Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,checks,coach,finder"))
    captions = itertools.count()
    real_sleep = asyncio.sleep

    async def go():
        await _to_step(rig, 1)
        assert rig.s.m.has_diagrams()
        # the video's captions change the screen text on every frame (t10: the cache key hashed it)
        monkeypatch.setattr(rig.s, "_screen_lines", lambda: {"Miyagi": [f"caption {next(captions)}"]})
        monkeypatch.setattr(asyncio, "sleep", lambda s, *a, **k: real_sleep(0))
        await rig.s._prefetch_diagram(rig.s.step_gen, rig.s.step)
        monkeypatch.setattr(asyncio, "sleep", real_sleep)
        assert len(fake.calls) == 1
        await rig.s.action("diagram")
        await rig.settle()

    try:
        run(go())
    finally:
        diagrams.clear_cache()
    assert len(fake.calls) == 1  # the press was served by the prefetch
    shown = rig.of("diagram")
    assert shown and shown[-1]["stepId"] == rig.s.step["id"] and shown[-1]["kind"] == "network"
