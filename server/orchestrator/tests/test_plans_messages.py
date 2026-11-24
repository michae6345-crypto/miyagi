"""ui-v4 plans over the engine's real WebSocket (FastAPI TestClient): the contract's plans commands and replies, offline.

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
from shared.contracts.events import ENGINE_EVENTS, PlaylistInfo, PlanProposalEvent, Plans

PLID = "PLtestTESTtest0123456789"
PL_URL = f"https://www.youtube.com/playlist?list={PLID}"


@pytest.fixture
def plans_env(quiet_env, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    catalog.reload()
    calls: list[str] = []
    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({"/playlist": (200, fixture("playlist_page.html"))},
                                                                 calls))
    playlist._inflight.clear()
    from server.coach import llm

    async def offline(**_k):  # never the real model (.env / the cloud install token): tests that want it override this
        raise llm.CoachLLMError("offline test", "offline")

    monkeypatch.setattr(llm, "structured_call", offline)
    yield calls
    catalog.reload()


def _ask(ws, type_: str, payload: dict, want: str) -> dict:
    ws.send_json({"type": type_, "payload": payload})
    got = _until(ws, want)
    return got[-1]["payload"]


def _plans(ws, type_: str, payload: dict) -> dict:
    out = _ask(ws, type_, payload, "plans")
    Plans.model_validate(out)
    return out


def test_hello_lists_the_plans_commands(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, _eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "engine.hello"
        caps = hello["payload"]["capabilities"]
        assert {"plans.list", "plan.start", "plan.remove", "playlist.get", "plan.propose"} <= set(caps)
        assert "plan.lesson.start" not in caps
    assert "plans" in ENGINE_EVENTS and "playlist" in ENGINE_EVENTS


def test_plans_round_trips(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, _eng, _, calls = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        assert _plans(ws, "plans.list", {"reqId": "r-0"}) == {"items": [], "reqId": "r-0"}

        out = _plans(ws, "plan.start", {"catalogId": "intro-python", "reqId": "r-1"})
        assert out["reqId"] == "r-1" and [p["id"] for p in out["items"]] == ["intro-python"]
        p = out["items"][0]
        assert p["source"] == "preset" and p["catalogId"] == "intro-python" and p["nextIndex"] == 0
        assert p["lessons"][0]["state"] == "next" and isinstance(p["startedAt"], str)
        again = _plans(ws, "plan.start", {"catalogId": "intro-python", "reqId": "r-2"})
        assert len(again["items"]) == 1 and again["items"][0]["startedAt"] == p["startedAt"]

        ws.send_json({"type": "playlist.get", "payload": {"url": PL_URL, "reqId": "r-pl"}})
        first = _until(ws, "playlist")[-1]["payload"]
        second = _until(ws, "playlist")[-1]["payload"]
        for x in (first, second):
            PlaylistInfo.model_validate(x)
            assert x["reqId"] == "r-pl" and x["url"] == PL_URL and x["playlistId"] == PLID and x["videoCount"] == 3
        assert first["proposing"] is True and "proposal" not in first
        assert second["proposing"] is False and second["proposal"]["source"] == "playlist"
        prop = second["proposal"]
        prop["lessons"][0]["skip"] = True
        out = _plans(ws, "plan.start", {"playlistId": PLID, "url": PL_URL, "proposal": prop, "reqId": "r-3"})
        pl = next(x for x in out["items"] if x["id"] == "pl-" + PLID)
        assert pl["source"] == "playlist" and pl["playlistId"] == PLID and pl["total"] == 2
        assert [le["state"] for le in pl["lessons"]] == ["skipped", "next", "todo"]
        assert len(plans_env) == 1  # one fetch: the page; the proposal and the start needed no other

        ws.send_json({"type": "plan.propose", "payload": {"goal": "I want to learn pandas", "reqId": "r-g"}})
        first = _until(ws, "plan.proposal")[-1]["payload"]
        second = _until(ws, "plan.proposal")[-1]["payload"]
        for x in (first, second):
            PlanProposalEvent.model_validate(x)
            assert x["reqId"] == "r-g" and x["goal"] == "I want to learn pandas"
        assert first["proposing"] is True and second["proposing"] is False
        assert second["proposal"]["fromPlans"] == ["intro-python", "pandas"]
        out = _plans(ws, "plan.start", {"goal": "I want to learn pandas", "proposal": second["proposal"], "reqId": "r-4"})
        goal = next(x for x in out["items"] if x["source"] == "goal")
        assert goal["id"].startswith("goal-") and goal["lessons"][0]["goal"]

        out = _plans(ws, "plan.remove", {"id": "intro-python"})
        assert "intro-python" not in [x["id"] for x in out["items"]] and len(out["items"]) == 2
    assert calls == []  # no lesson was built


def test_plans_errors_are_said_not_dropped(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, _eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        err = _ask(ws, "plan.start", {"catalogId": "no-such-plan", "reqId": "r-x"}, "error")
        assert "catalog" in err["message"] and err["reqId"] == "r-x"
        assert _ask(ws, "plan.start", {}, "error")["message"]
        assert _ask(ws, "plan.start", {"url": "https://example.com/x"}, "error")["message"]
        assert _plans(ws, "plan.remove", {"id": "../../etc"})["items"] == []  # a bad id never reaches the disk
        got = _ask(ws, "playlist.get", {"url": "https://example.com/list", "reqId": "r-u"}, "playlist")
        assert got["error"] == "unsupported" and got["reqId"] == "r-u" and got["proposing"] is False and not got["videos"]
        ws.send_json({"type": "plan.propose", "payload": {"goal": "qqq zzz xxyy"}})
        _until(ws, "plan.proposal")
        none = _until(ws, "plan.proposal")[-1]["payload"]
        assert none["error"] == "not_found" and none["proposing"] is False
        assert _ask(ws, "plan.propose", {"goal": ""}, "error")["message"]  # the contract's min_length


def test_plan_propose_falls_back_to_the_mocked_model(plans_env, monkeypatch):
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
        ws.send_json({"type": "plan.propose", "payload": {"goal": "how does my car engine work"}})
        _until(ws, "plan.proposal")
        m = _until(ws, "plan.proposal")[-1]["payload"]
        assert m["proposal"]["fromPlans"][-1] == "intro-arduino"
        ws.send_json({"type": "plan.propose", "payload": {"goal": "learn swift"}})
        _until(ws, "plan.proposal")
        assert _until(ws, "plan.proposal")[-1]["payload"]["proposal"]["source"] == "goal"
    assert len(asked) == 1


def test_a_plan_lesson_starts_through_learn_and_is_linked(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, eng, _, _ = _engine(monkeypatch)
    started: list[tuple] = []

    async def learn(query, mode=None):
        started.append(("learn", query, mode))
        await eng._emit("lesson.ready", {"lesson": {"id": "les-plan-1", "title": "t"}, "steps": []})

    async def learn_url(url, transcript_only=False):
        started.append(("learn_url", url))

    monkeypatch.setattr(eng.session, "learn", learn)
    monkeypatch.setattr(eng.session, "learn_url", learn_url)
    goal1 = catalog.get("intro-blender")["lessons"][1]["goal"]
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        _plans(ws, "plan.start", {"catalogId": "intro-blender"})
        pushed = _plans(ws, "learn", {"query": goal1, "mode": "lesson", "plan": {"id": "intro-blender", "index": 1}})
        les = pushed["items"][0]["lessons"][1]
        assert les["state"] == "in_progress" and pushed["items"][0]["nextIndex"] == 1 and les["openedAt"]
        _until(ws, "lesson.ready")
        assert started == [("learn", goal1, "lesson")]

        ws.send_json({"type": "playlist.get", "payload": {"url": PLID}})
        _until(ws, "playlist")
        _until(ws, "playlist")
        _plans(ws, "plan.start", {"playlistId": PLID})  # no proposal: the playlist's own videos (cached)
        url = "https://www.youtube.com/watch?v=aaaaaaaaaa3"
        pushed = _plans(ws, "learn_url", {"url": url, "plan": {"id": "pl-" + PLID, "index": 2}})
        pl = next(x for x in pushed["items"] if x["id"] == "pl-" + PLID)
        assert pl["lessons"][2]["state"] == "in_progress"
        _plans(ws, "plans.list", {})
        assert started[-1] == ("learn_url", url)
    saved = json.loads((state_dir() / "plans.json").read_text())
    assert saved["plans"]["intro-blender"]["started"]["1"]["lessonId"] == "les-plan-1"
    assert eng.session.app_v2 is True


def test_a_plan_lesson_started_over_a_running_lesson_is_still_linked(plans_env, monkeypatch):
    """The session ends the lesson already loaded (lesson.ended for the OLD lesson) before the plan lesson loads: that end
    must not drop the plan link, and only the plan lesson's own end clears it."""
    from fastapi.testclient import TestClient

    main, eng, _, _ = _engine(monkeypatch)

    async def learn(query, mode=None):
        await eng._emit("lesson.ended", {"lessonId": "old", "reason": "new lesson"})
        await eng._emit("lesson.ready", {"lesson": {"id": "les-plan-1", "title": "t"}, "steps": []})

    monkeypatch.setattr(eng.session, "learn", learn)
    goal1 = catalog.get("intro-blender")["lessons"][1]["goal"]
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        _plans(ws, "plan.start", {"catalogId": "intro-blender"})
        _plans(ws, "learn", {"query": goal1, "mode": "lesson", "plan": {"id": "intro-blender", "index": 1}})
        _until(ws, "lesson.ready")
        _plans(ws, "plans.list", {})  # a round trip: the link (after lesson.ready went out) has run
    assert eng._plan_ref == ("intro-blender", 1, "les-plan-1")
    saved = json.loads((state_dir() / "plans.json").read_text())
    assert saved["plans"]["intro-blender"]["started"]["1"]["lessonId"] == "les-plan-1"


def test_plan_ref_clears_only_on_the_linked_lessons_end(plans_env, monkeypatch):
    import asyncio

    _main, eng, _, _ = _engine(monkeypatch)
    pushes: list[int] = []

    async def push() -> None:
        pushes.append(1)

    monkeypatch.setattr(eng, "push_plans", push)
    eng._plan_ref = ("p", 0, None)
    asyncio.run(eng._plan_lesson_event("lesson.ended", {"lessonId": "old"}))
    assert eng._plan_ref == ("p", 0, None) and pushes == []
    eng._plan_ref = ("p", 0, "mine")
    asyncio.run(eng._plan_lesson_event("lesson.ended", {"lessonId": "other"}))
    assert eng._plan_ref == ("p", 0, "mine") and pushes == []
    asyncio.run(eng._plan_lesson_event("lesson.ended", {"lessonId": "mine"}))
    assert eng._plan_ref is None and pushes == [1]


def test_parse_command_uses_the_contract_for_plans():
    from server.orchestrator.main import parse_command

    assert parse_command({"type": "plan.start", "payload": {"catalogId": "intro-c"}}).payload.catalogId == "intro-c"
    assert parse_command({"type": "learn", "payload": {"query": "q", "plan": {"id": "intro-c", "index": 2}}}).payload.plan.index == 2
    for bad in ({"type": "plan.remove", "payload": {"id": 3}}, {"type": "plan.propose", "payload": {"goal": ""}},
                {"type": "learn", "payload": {"query": "q", "plan": {"id": "a", "index": -1}}},
                {"type": "plan.get", "payload": {"id": "intro-c"}}, {"type": "plan.lesson.start", "payload": {"id": "a"}}):
        with pytest.raises(ValueError):
            parse_command(bad)


def test_unreachable_youtube_is_one_clear_error(plans_env, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({"/playlist": (0, httpx.ConnectError("down")),
                                                                  "/feeds/videos.xml": (0, httpx.ConnectError("down"))}, []))
    main, _eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        got = _ask(ws, "playlist.get", {"url": PLID, "reqId": "r-o"}, "playlist")
        assert got["error"] == "offline" and got["reqId"] == "r-o"
