"""ask.warm and the circle ask's plumbing (fast circle to ask, Nov 22): the push-to-talk hold is answered beside the
queue and only schedules server/coach/fast_ask.warm(); hello lists it so the app sends it; an action ask carries
its capture and release time down to circle_ask.answer. Offline: the warm-up and the answer are replaced."""

from __future__ import annotations

import asyncio

from shared.contracts import events

from server.coach import fast_ask
from server.orchestrator import circle_ask
from server.orchestrator.tests.test_launch_contract import _engine, quiet_env  # noqa: F401 - quiet_env: a fixture

REGION = {"x": 100.0, "y": 200.0, "w": 300.0, "h": 80.0, "displayId": 1, "scale": 2.0}
CAPTURE = {"path": "/tmp/miyagi-capture/cap-1-00000000-0000-0000-0000-000000000000.jpg", "w": 600, "h": 160,
           "rect": {"x": 96.0, "y": 196.0, "w": 308.0, "h": 88.0}, "displayId": 1}


def test_ask_warm_is_instant_and_schedules_the_warmup(quiet_env, monkeypatch):  # noqa: F811
    main, eng, _ws, _calls = _engine(monkeypatch)
    seen: list = []
    monkeypatch.setattr(fast_ask, "warm_soon", lambda source=None, *, ptt_id=None: seen.append((source, ptt_id)))
    assert "ask.warm" in main.INSTANT  # never queued behind a build or an answer

    async def go():
        await eng.dispatch({"type": "ask.warm", "payload": {"pttId": "ptt-7"}})  # what v2-integration's ptt.ts sends
        await eng.dispatch({"type": "ask.warm", "payload": {"source": "keydown"}})
        await eng.dispatch({"type": "ask.warm"})

    asyncio.run(go())
    assert seen == [("keydown", "ptt-7"), ("keydown", None), ("keydown", None)]


def test_hello_lists_ask_warm(quiet_env, monkeypatch):  # noqa: F811
    """The app sends ask.warm only when engine.hello.capabilities lists it (ptt.ts, engine.ts send())."""
    _main, eng, _ws, _calls = _engine(monkeypatch)
    caps = eng.hello()["capabilities"]
    assert "ask.warm" in caps and "ask.region" not in caps


def test_one_ask_warm_contract():
    """v2-integration's AskWarm {pttId?} is the one definition; source is an extra optional field on it."""
    m = events.APP_COMMANDS["ask.warm"].model_validate({"pttId": "p1", "source": "keydown"})
    assert m.pttId == "p1" and m.source == "keydown"
    assert events.APP_COMMANDS["ask.warm"].model_validate({}).pttId is None
    assert "ask.region" not in events.APP_COMMANDS


def test_action_ask_carries_capture_and_release_time(quiet_env, monkeypatch):  # noqa: F811
    main, eng, _ws, _calls = _engine(monkeypatch)
    got: list = []

    async def fake_answer(session, step, text, region, ask_id=None, *, app_capture=None, release_t=None):
        got.append({"region": region, "ask_id": ask_id, "capture": app_capture, "release_t": release_t})

    monkeypatch.setattr(circle_ask, "answer", fake_answer)
    raw = {"type": "action", "payload": {"kind": "ask", "text": "what is this", "region": REGION, "source": "circle",
                                         "askId": "k1", "capture": CAPTURE}, main.RX_KEY: 12.5}

    asyncio.run(eng.dispatch(raw))
    assert len(got) == 1 and got[0]["ask_id"] == "k1" and got[0]["release_t"] == 12.5
    assert got[0]["capture"].path == CAPTURE["path"] and got[0]["capture"].w == 600  # the AskCapture model
    assert "cap-1-" not in repr(main._redact(raw))  # the crop's path is never logged
