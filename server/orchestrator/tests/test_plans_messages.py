"""ui-v4 plans over the engine's real WebSocket (FastAPI TestClient): every plans command and its reply, offline.

Stub modules, a recording workspace, a fake screen reader (test_launch_contract's rig); YouTube is a recorded page
behind plans.playlist.TRANSPORT; the goal model is a fake; a plan lesson's build is a recorded call, never a model."""

from __future__ import annotations

import json

import httpx
import pytest

from server.orchestrator.tests.test_launch_contract import _engine, _until, quiet_env  # noqa: F401 - a fixture
from server.plans import catalog, playlist
from server.plans.tests.helpers import fixture, youtube_transport
from server.sessions.store import state_dir

PLID = "PLtestTESTtest0123456789"


@pytest.fixture
def plans_env(quiet_env, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    catalog.reload()
    calls: list[str] = []
    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({"/playlist": (200, fixture("playlist_page.html"))},
                                                                 calls))
    playlist._inflight.clear()
    yield calls
    catalog.reload()


def _ask(ws, type_: str, payload: dict, want: str) -> dict:
    ws.send_json({"type": type_, "payload": payload})
    got = _until(ws, want)
    return got[-1]["payload"]


def test_plans_round_trips(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, _eng, _, calls = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        plans = _ask(ws, "plans.list", {}, "plans")
        assert len(plans["plans"]) == 40 and plans["playlists"] == []
        assert all("lessons" not in r and "progress" not in r for r in plans["plans"])

        plan = _ask(ws, "plan.get", {"id": "intro-python"}, "plan")
        assert plan["kind"] == "catalog" and plan["progress"] is None and len(plan["playlists"]) == 2
        assert plan["plan"]["lessons"][0]["index"] == 0 and plan["plan"]["lessons"][0]["goal"].startswith("Teach")

        v = _ask(ws, "plan.start", {"id": "intro-python"}, "plan.progress")
        assert v["key"] == "intro-python" and v["active"] and v["next"]["index"] == 0

        v = _ask(ws, "plan.lesson.done", {"id": "intro-python", "index": 0}, "plan.progress")
        assert v["done"] == 1 and v["next"]["index"] == 1

        prog = _ask(ws, "plans.progress.get", {}, "plans.progress")
        assert [p["key"] for p in prog["plans"]] == ["intro-python"] and prog["resume"]["key"] == "intro-python"
        row = next(r for r in _ask(ws, "plans.list", {}, "plans")["plans"] if r["id"] == "intro-python")
        assert row["progress"] == {"done": 1, "total": 10, "active": True, "complete": False}

        m = _ask(ws, "plan.goal", {"text": "I want to learn pandas"}, "plan.matches")
        assert m["confident"] and m["matches"][0] == {"planId": "pandas", "title": "pandas", "score": m["matches"][0]["score"],
                                                     "line": catalog.get("pandas")["line"], "first": "intro-python"}

        pl = _ask(ws, "plan.playlist", {"url": f"https://www.youtube.com/playlist?list={PLID}"}, "plan.playlist")
        assert pl["id"] == "yt-" + PLID and pl["videoCount"] == 3 and pl["source"] == "page"
        v = _ask(ws, "plan.start", {"id": "yt-" + PLID}, "plan.progress")  # from the cache: no second fetch
        assert v["kind"] == "playlist" and v["total"] == 3 and len(plans_env) == 1
        plan = _ask(ws, "plan.get", {"id": "yt-" + PLID}, "plan")
        assert plan["kind"] == "playlist" and plan["progress"]["title"] == "Python for beginners"

        prog = _ask(ws, "plan.remove", {"id": "intro-python"}, "plans.progress")
        assert [p["key"] for p in prog["plans"]] == ["yt-" + PLID]
    assert calls == []  # no lesson was built


def test_plans_errors_are_said_not_dropped(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, _eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        assert "not on this Mac" in _ask(ws, "plan.get", {"id": "no-such-plan"}, "error")["message"]
        assert "not on this Mac" in _ask(ws, "plan.start", {"id": "no-such-plan"}, "error")["message"]
        assert _ask(ws, "plan.get", {"id": "../../etc"}, "error")["message"]  # a bad id never reaches the disk
        assert _ask(ws, "plan.lesson.done", {"id": "intro-c", "index": "x"}, "error")["message"]
        assert _ask(ws, "plan.goal", {"text": "   "}, "error")["message"]
        assert "playlist" in _ask(ws, "plan.playlist", {"url": "https://example.com/list"}, "error")["message"]
        assert _ask(ws, "plan.start", {"url": "https://example.com/x"}, "error")["message"]
        assert _ask(ws, "plan.lesson.start", {"id": "intro-c"}, "error")["message"]  # not started: no lesson


def test_plan_goal_falls_back_to_the_mocked_model(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    from server.coach import llm

    class R:
        def __init__(self) -> None:
            self.data = {"planIds": ["intro-arduino", "invented"]}

    asked: list[dict] = []

    async def fake(**k):
        asked.append(k)
        return R()

    monkeypatch.setattr(llm, "structured_call", fake)
    main, _eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        m = _ask(ws, "plan.goal", {"text": "how does my car engine work"}, "plan.matches")
        assert m["source"] == "model" and [x["planId"] for x in m["matches"]] == ["intro-arduino"]
        m = _ask(ws, "plan.goal", {"text": "learn swift"}, "plan.matches")
        assert m["source"] == "catalog"
    assert len(asked) == 1


def test_plan_lesson_start_builds_the_next_lesson_and_links_it(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, eng, _, _ = _engine(monkeypatch)
    started: list[tuple] = []

    async def learn(query, mode=None):
        started.append(("learn", query, mode))
        eng.session.graph = {"lesson": {"id": "les-plan-1", "title": "t"}, "steps": []}

    async def learn_url(url, transcript_only=False):
        started.append(("learn_url", url))

    monkeypatch.setattr(eng.session, "learn", learn)
    monkeypatch.setattr(eng.session, "learn_url", learn_url)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        _ask(ws, "plan.start", {"id": "intro-blender"}, "plan.progress")
        _ask(ws, "plan.lesson.done", {"id": "intro-blender", "index": 0}, "plan.progress")
        v = _ask(ws, "plan.lesson.start", {"id": "intro-blender"}, "plan.progress")
        assert v["next"]["index"] == 1 and v["lessons"][1]["state"] == "current"
        _ask(ws, "plans.progress.get", {}, "plans.progress")  # the queued start has run by the time a later read
        goal1 = catalog.get("intro-blender")["lessons"][1]["goal"]
        assert started == [("learn", goal1, "lesson")]

        _ask(ws, "plan.playlist", {"url": PLID}, "plan.playlist")
        _ask(ws, "plan.start", {"id": "yt-" + PLID}, "plan.progress")
        _ask(ws, "plan.lesson.start", {"id": "yt-" + PLID, "index": 2}, "plan.progress")
        _ask(ws, "plans.progress.get", {}, "plans.progress")
        assert started[-1] == ("learn_url", "https://www.youtube.com/watch?v=aaaaaaaaaa4")
    saved = json.loads((state_dir() / "plans.json").read_text())
    assert saved["plans"]["intro-blender"]["started"]["1"]["lessonId"] == "les-plan-1"
    assert eng.session.app_v2 is True


def test_parse_command_checks_plans_payloads():
    from server.orchestrator.main import parse_command

    assert parse_command({"type": "plan.get", "payload": {"id": "intro-c"}}).payload.id == "intro-c"
    assert parse_command({"type": "plan.lesson.start", "payload": {"id": "yt-" + PLID}}).payload.index is None
    for bad in ({"type": "plan.get", "payload": {"id": 3}}, {"type": "plan.lesson.done", "payload": {"id": "a", "index": -1}},
                {"type": "plan.lesson.done", "payload": {"id": "a", "index": True}},
                {"type": "plan.playlist", "payload": {}}, {"type": "plan.start", "payload": {"id": "Bad Id"}}):
        with pytest.raises(ValueError):
            parse_command(bad)


def test_unreachable_youtube_is_one_clear_error(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({"/playlist": (0, httpx.ConnectError("down")),
                                                                  "/feeds/videos.xml": (0, httpx.ConnectError("down"))}, []))
    main, _eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        assert "reach YouTube" in _ask(ws, "plan.playlist", {"url": PLID}, "error")["message"]
