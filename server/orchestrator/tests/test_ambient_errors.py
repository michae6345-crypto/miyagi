"""Ambient help, explain this error, over the engine's real WebSocket (FastAPI TestClient): ambient.set, error.seen,
error.explain -> error.explanation, error.dismiss, the hourly cap, quiet during a lesson, and the screen reader running
for it outside a lesson. Recorded OCR frames (server/ambient_errors/tests/fixtures), a fake screen reader, a fake model
client: never a real model, screen or window."""

from __future__ import annotations

import time

import pytest

from server import ambient_cap
from server.ambient_errors.tests.helpers import empty_frame, frame
from server.ambient_errors.watcher import ErrorWatcher
from server.orchestrator.tests.test_launch_contract import _engine, quiet_env  # noqa: F401 - a fixture
from shared.contracts.events import ENGINE_EVENTS, ErrorExplanation


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def amb(quiet_env, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("ORCH_STRICT", "1")  # every event must match the contract
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    from server.coach import llm

    calls: list[dict] = []

    async def model(**kw):
        calls.append(kw)
        return llm.CallResult(data={"title": "config is undefined here", "why": "server.js reads config.port on "
                                    "line 12 before config is set.", "fix": "Set config before line 12.", "diff": "",
                                    "command": ""}, model="claude-haiku-5-5")

    monkeypatch.setattr(llm, "structured_call", model)
    ambient_cap.reset_shared(ambient_cap.HourlyCap(limit=20, path=False))
    main, eng, _ws, _calls = _engine(monkeypatch)
    clock = Clock()
    eng.ambient.watcher = ErrorWatcher(clock=clock, now_iso=lambda: "2026-11-24T10:42:05-08:00")
    yield main, eng, clock, calls, quiet_env
    ambient_cap.reset_shared(None)


def _next(ws, type_: str, limit: int = 60) -> dict:
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == type_:
            return m["payload"]
    raise AssertionError(f"no {type_}")


def _spot(client, eng, clock, ws, name: str) -> dict:
    """A recorded frame on screen for 1.2 s -> its error.seen."""
    client.portal.call(eng.on_screen, frame(name))
    clock.t += 1.2
    client.portal.call(eng.ambient.tick)
    p = _next(ws, "error.seen")
    ENGINE_EVENTS["error.seen"].validate_python(p)
    return p


def _set(ws, **payload) -> None:
    ws.send_json({"type": "ambient.set", "payload": payload})


def _settle(client, eng, cond, s: float = 2.0) -> None:
    end = time.monotonic() + s
    while time.monotonic() < end and not cond():
        client.portal.call(lambda: __import__("asyncio").sleep(0.02))


def test_hello_lists_the_three_commands(amb):
    from fastapi.testclient import TestClient

    main, *_ = amb
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        hello = ws.receive_json()
        caps = set(hello["payload"]["capabilities"])
        assert {"ambient.set", "error.explain", "error.dismiss"} <= caps
        assert not {"setup.scan", "setup.fix", "help.ask", "help.nav"} & caps  # other lanes list their own


def test_spot_explain_dismiss(amb):
    from fastapi.testclient import TestClient

    main, eng, clock, calls, reader = amb
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        client.portal.call(eng.on_screen, frame("python_traceback"))  # off by default: nothing is watched
        clock.t += 5
        client.portal.call(eng.ambient.tick)
        assert eng.ambient.watcher.held == {}

        _set(ws, errors=True, mutedApps=["1Password"])
        _settle(client, eng, lambda: eng.ambient.errors_on())
        _settle(client, eng, lambda: reader.starts > 0)
        assert reader.starts > 0  # outside a lesson, the reader runs for "Spot errors"
        seen = _spot(client, eng, clock, ws, "python_traceback")
        assert seen["kind"] == "python_traceback" and seen["file"] == "~/code/weather-app/app.py"

        ws.send_json({"type": "error.explain", "payload": {"id": seen["id"], "reqId": "x1"}})
        assert _next(ws, "error.explanation") == {"id": seen["id"], "reqId": "x1", "pending": True}
        ans = _next(ws, "error.explanation")
        ErrorExplanation.model_validate(ans)
        assert ans["title"] == "pandas isn't installed here" and ans["install"]["tool"] == "pandas"
        assert calls == []  # known on this Mac: no model call
        assert eng.ambient.lesson_running() is False

        ws.send_json({"type": "error.dismiss", "payload": {"id": seen["id"]}})
        ws.send_json({"type": "error.explain", "payload": {"id": seen["id"], "reqId": "x2"}})
        assert _next(ws, "error.explanation") == {"id": seen["id"], "reqId": "x2", "error": "gone"}


def test_model_explain_once_then_from_memory_and_the_cap(amb):
    from fastapi.testclient import TestClient

    main, eng, clock, calls, _reader = amb
    ambient_cap.reset_shared(ambient_cap.HourlyCap(limit=1, path=False))
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        _set(ws, errors=True)
        _settle(client, eng, lambda: eng.ambient.errors_on())
        node = _spot(client, eng, clock, ws, "node_stack")
        for req in ("a", "b"):
            ws.send_json({"type": "error.explain", "payload": {"id": node["id"], "reqId": req}})
        got = [_next(ws, "error.explanation") for _ in range(3)]
        answers = [g for g in got if not g.get("pending")]
        assert answers and all(a["why"].startswith("server.js reads config.port") for a in answers)
        assert len(calls) == 1 and calls[0]["model"] == "claude-haiku-5-5"
        assert "<untrusted" in calls[0]["user_text"] and "/Users/sam" not in calls[0]["user_text"]

        clock.t += 6
        client.portal.call(eng.on_screen, empty_frame(app="Code", title="x"))  # Terminal hidden: node stays held
        git = _spot(client, eng, clock, ws, "git_error")
        ws.send_json({"type": "error.explain", "payload": {"id": git["id"]}})
        assert _next(ws, "error.explanation") == {"id": git["id"], "pending": True}
        capped = _next(ws, "error.explanation")
        assert capped["error"] == "cap" and 1 <= capped["retryInS"] <= 3600 and len(calls) == 1


def test_gone_clears_and_a_lesson_keeps_it_quiet(amb):
    from fastapi.testclient import TestClient

    main, eng, clock, _calls, _reader = amb
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        _set(ws, errors=True)
        _settle(client, eng, lambda: eng.ambient.errors_on())
        seen = _spot(client, eng, clock, ws, "tsc_error")
        client.portal.call(eng.on_screen, empty_frame(app="Code", title="index.ts — web", text="sam@mac web %"))
        clock.t += 3.5
        client.portal.call(eng.ambient.tick)
        assert _next(ws, "error.seen") == {"id": seen["id"], "clear": True}

        # a lesson runs: no error.seen, and what was shown is cleared
        clock.t += 1  # one peek every 5 s
        again = _spot(client, eng, clock, ws, "pip_failure")
        eng.session.phase = "active"
        client.portal.call(eng.ambient.tick)
        assert _next(ws, "error.seen") == {"id": again["id"], "clear": True}
        assert eng.ambient.wants_screen() is False
        client.portal.call(eng.ambient.on_obs, frame("git_error"))
        clock.t += 10
        client.portal.call(eng.ambient.tick)
        assert eng.ambient.watcher.held == {}
        eng.session.phase = "idle"

        _set(ws, errors=False)
        _settle(client, eng, lambda: not eng.ambient.errors_on())
        client.portal.call(eng.on_screen, frame("git_error"))
        clock.t += 10
        client.portal.call(eng.ambient.tick)
        assert eng.ambient.watcher.held == {}
    assert eng.ambient.conns == {}  # the connection closed: its settings went with it


def test_no_error_seen_while_a_lesson_search_runs(amb, monkeypatch):
    """The video search before a build ('searching') is a lesson phase: no peek, no screen reading for errors."""
    from fastapi.testclient import TestClient

    from server.orchestrator.ambient import LESSON_PHASES

    assert "searching" in LESSON_PHASES
    main, eng, clock, _calls, _reader = amb
    sent: list[tuple[str, dict]] = []
    real_send_to = eng.ambient.hub.send_to

    async def send_to(ws, type_, payload):
        sent.append((type_, payload))
        return await real_send_to(ws, type_, payload)

    monkeypatch.setattr(eng.ambient.hub, "send_to", send_to)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        _set(ws, errors=True)
        _settle(client, eng, lambda: eng.ambient.errors_on())

        eng.session.phase = "searching"
        assert eng.ambient.lesson_running() is True and eng.ambient.wants_screen() is False
        client.portal.call(eng.on_screen, frame("tsc_error"))
        client.portal.call(eng.ambient.on_obs, frame("tsc_error"))
        for _ in range(4):
            clock.t += 1.5
            client.portal.call(eng.ambient.tick)
        assert eng.ambient.watcher.held == {}
        assert [t for t, _p in sent if t == "error.seen"] == []

        # the search ends with no lesson: spotting resumes, and the first peek is the error on screen now
        eng.session.phase = "idle"
        seen = _spot(client, eng, clock, ws, "git_error")
        assert not seen.get("clear") and [p for t, p in sent if t == "error.seen"][0]["id"] == seen["id"]
