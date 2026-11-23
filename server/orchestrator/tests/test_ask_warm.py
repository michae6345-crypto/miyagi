"""ask.warm (fast circle to ask, Nov 22): the key-down command is answered beside the queue and only schedules
server/coach/fast_ask.warm(). Offline: the warm-up itself is replaced, nothing leaves the engine."""

from __future__ import annotations

import asyncio

from server.coach import fast_ask
from server.orchestrator.tests.test_launch_contract import _engine, quiet_env  # noqa: F401 - quiet_env: a fixture


def test_ask_warm_is_instant_and_schedules_the_warmup(quiet_env, monkeypatch):  # noqa: F811
    main, eng, _ws, _calls = _engine(monkeypatch)
    seen: list = []
    monkeypatch.setattr(fast_ask, "warm_soon", lambda source=None: seen.append(source))
    assert "ask.warm" in main.INSTANT  # never queued behind a build or an answer

    async def go():
        await eng.dispatch({"type": "ask.warm", "payload": {"source": "keydown"}})
        await eng.dispatch({"type": "ask.warm"})

    asyncio.run(go())
    assert seen == ["keydown", None]
