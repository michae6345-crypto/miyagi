"""Stopping a lesson that is still on its way (a tester, Nov 25: "midway I want to just remove the plan ... it still doesn't
do that"): End / Stop building and plan.remove must stop a start that is queued, running, or building, and nothing may
come back after the stop. Offline: fake session methods and the engine's real WebSocket, never a model."""

from __future__ import annotations

import asyncio
import json

import pytest

from server.lesson import builder
from server.orchestrator.tests.test_launch_contract import _engine, _queued_fence, _until, quiet_env  # noqa: F401
from server.orchestrator.tests.test_plans_messages import _plans, plans_env  # noqa: F401
from server.plans import catalog
from server.sessions.store import state_dir


# ---------------------------------------------------------------------------------------------- the queue, as a unit


def _start(type_: str = "learn", plan: str | None = None) -> dict:
    p: dict = {"query": "q"}
    if plan:
        p["plan"] = {"id": plan, "index": 0}
    return {"type": type_, "payload": p}


def test_stop_starts_drops_queued_starts_and_keeps_the_rest_in_order():
    from server.orchestrator.main import _stop_starts

    async def go() -> tuple[int, list[dict]]:
        q: asyncio.Queue = asyncio.Queue()
        for raw in (_start(), {"type": "action", "payload": {"kind": "hint"}}, _start("library.start"),
                    {"type": "video.state", "payload": {}}, _start("learn_url")):
            q.put_nowait(raw)
        n = _stop_starts(q, {})
        assert not n.running
        return n.queued, [q.get_nowait() for _ in range(q.qsize())]

    n, left = asyncio.run(go())
    assert n == 3
    assert [r["type"] for r in left] == ["action", "video.state"]


def test_stop_starts_cancels_the_running_start_only():
    from server.orchestrator.main import _stop_starts

    async def go() -> tuple[int, bool, int, bool]:
        q: asyncio.Queue = asyncio.Queue()
        job = asyncio.ensure_future(asyncio.sleep(30))
        n = _stop_starts(q, {"cmd": _start(), "job": job}).total
        await asyncio.sleep(0)
        other = asyncio.ensure_future(asyncio.sleep(30))
        m = _stop_starts(q, {"cmd": {"type": "action", "payload": {"kind": "ask"}}, "job": other}).total
        await asyncio.sleep(0)
        alive = not other.done()
        other.cancel()
        return n, job.cancelled(), m, alive

    n, cancelled, m, alive = asyncio.run(go())
    assert (n, cancelled) == (1, True)
    assert (m, alive) == (0, True)  # an ask the worker runs is not a lesson start: never cancelled by a stop


def test_stop_starts_for_a_plan_only_touches_that_plans_lessons():
    from server.orchestrator.main import _stop_starts

    async def go() -> tuple[int, list[dict], bool]:
        q: asyncio.Queue = asyncio.Queue()
        for raw in (_start(plan="a"), _start(plan="b"), _start()):
            q.put_nowait(raw)
        job = asyncio.ensure_future(asyncio.sleep(30))
        n = _stop_starts(q, {"cmd": _start(plan="b"), "job": job}, plan_id="a")
        await asyncio.sleep(0)
        alive = not job.done()
        job.cancel()
        assert not n.running  # only a queued start of plan a: nothing ran, so plan_removed ends nothing for it
        return n.queued, [q.get_nowait() for _ in range(q.qsize())], alive

    n, left, alive = asyncio.run(go())
    assert n == 1 and alive
    assert [(r["payload"].get("plan") or {}).get("id") for r in left] == ["b", None]


# ------------------------------------------------------------------------------------- plan.remove on the engine side


def _ref_engine(monkeypatch):
    _main, eng, _, _ = _engine(monkeypatch)
    ended: list[str] = []

    async def end_lesson(reason: str = "end_lesson") -> None:
        ended.append(reason)

    monkeypatch.setattr(eng.session, "end_lesson", end_lesson)
    return eng, ended


def test_removing_a_plan_whose_lesson_is_building_stops_the_build(quiet_env, monkeypatch):  # noqa: F811
    eng, ended = _ref_engine(monkeypatch)
    monkeypatch.setattr(eng.session, "building", lambda: True)
    eng._plan_ref = ("p", 3, None)
    asyncio.run(eng.plan_removed("p"))
    assert ended == ["stopped"] and eng._plan_ref is None


def test_removing_a_plan_whose_progressive_lesson_loaded_keeps_it(quiet_env, monkeypatch):  # noqa: F811
    """Step 1 is live (graph loaded) while the rest builds, even before the link: removal never ends that lesson."""
    eng, ended = _ref_engine(monkeypatch)
    monkeypatch.setattr(eng.session, "building", lambda: True)
    eng.session.graph = {"lesson": {"id": "les-1"}, "steps": []}
    eng._plan_ref = ("p", 3, None)
    asyncio.run(eng.plan_removed("p"))
    assert ended == [] and eng._plan_ref is None


def test_removing_a_plan_whose_lesson_runs_keeps_the_lesson_and_unlinks_it(quiet_env, monkeypatch):  # noqa: F811
    eng, ended = _ref_engine(monkeypatch)
    monkeypatch.setattr(eng.session, "building", lambda: True)  # the rest of a progressive build, after lesson.ready
    eng._plan_ref = ("p", 3, "les-1")
    asyncio.run(eng.plan_removed("p"))
    assert ended == [] and eng._plan_ref is None


def test_removing_another_plan_touches_nothing(quiet_env, monkeypatch):  # noqa: F811
    eng, ended = _ref_engine(monkeypatch)
    monkeypatch.setattr(eng.session, "building", lambda: True)
    eng._plan_ref = ("p", 3, None)
    asyncio.run(eng.plan_removed("other"))
    assert ended == [] and eng._plan_ref == ("p", 3, None)
    asyncio.run(eng.plan_removed("other", cancelled_start=True))  # its start was cancelled: that start is stopped
    assert ended == ["stopped"] and eng._plan_ref == ("p", 3, None)


def test_a_stopped_plan_build_is_never_linked_to_a_later_lesson(quiet_env, monkeypatch):  # noqa: F811
    _main, eng, _, _ = _engine(monkeypatch)

    async def push() -> None:
        return None

    monkeypatch.setattr(eng, "push_plans", push)
    eng._plan_ref = ("p", 0, None)
    asyncio.run(eng._plan_lesson_event("lesson.ended", {"reason": "new lesson"}))
    assert eng._plan_ref == ("p", 0, None)  # the old lesson ending as the plan lesson starts: still the plan's
    asyncio.run(eng._plan_lesson_event("lesson.ended", {"reason": "stopped"}))
    assert eng._plan_ref is None


# ---------------------------------------------------------------------------------------- over the real WebSocket


def test_end_drops_a_learn_still_waiting_in_the_queue(quiet_env, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    main, eng, _, _ = _engine(monkeypatch)
    started: list[str] = []

    async def slow_action(kind, text=None, **_k):  # holds the queue, as a slow press does
        await asyncio.sleep(0.3)

    async def learn(query, mode=None):
        started.append(query)

    monkeypatch.setattr(eng.session, "action", slow_action)
    monkeypatch.setattr(eng.session, "learn", learn)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        ws.send_json({"type": "action", "payload": {"kind": "hint"}})
        ws.send_json({"type": "learn", "payload": {"query": "coffee", "mode": "lesson"}})
        ws.send_json({"type": "end_lesson", "payload": {}})
        _until(ws, "lesson.ended")
        _queued_fence(ws)  # runs after the action, and after the learn had it stayed queued
    assert started == []


def test_the_end_lesson_card_action_drops_a_queued_learn(quiet_env, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    main, eng, _, _ = _engine(monkeypatch)
    started: list[str] = []
    acted: list[str] = []

    async def action(kind, text=None, **_k):
        acted.append(kind)
        if kind == "hint":
            await asyncio.sleep(0.3)  # holds the queue

    async def learn(query, mode=None):
        started.append(query)

    monkeypatch.setattr(eng.session, "action", action)
    monkeypatch.setattr(eng.session, "learn", learn)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        ws.send_json({"type": "action", "payload": {"kind": "hint"}})
        ws.send_json({"type": "learn", "payload": {"query": "coffee", "mode": "lesson"}})
        ws.send_json({"type": "action", "payload": {"kind": "end_lesson"}})
        _queued_fence(ws)
    assert started == [] and acted == ["hint", "end_lesson"]


def test_end_cancels_a_learn_the_worker_is_running(quiet_env, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    main, eng, _, _ = _engine(monkeypatch)
    seen: list[str] = []

    async def learn(query, mode=None):
        seen.append("start")
        await eng._emit("status", {"state": "thinking"})
        try:
            await asyncio.sleep(2)  # e.g. ending the old lesson, before the build task exists (short: a regression fails, never hangs)
            seen.append("built")
        except asyncio.CancelledError:
            seen.append("cancelled")
            raise

    monkeypatch.setattr(eng.session, "learn", learn)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        ws.send_json({"type": "learn", "payload": {"query": "coffee", "mode": "lesson"}})
        _until(ws, "status")
        ws.send_json({"type": "end_lesson", "payload": {}})
        ended = _until(ws, "lesson.ended")[-1]["payload"]
        _queued_fence(ws)
    assert seen == ["start", "cancelled"]
    assert ended["reason"] == "stopped"


def test_removing_a_plan_mid_build_stops_its_lesson_and_it_stays_removed(plans_env, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    main, eng, _, _ = _engine(monkeypatch)
    seen: list[str] = []

    async def learn(query, mode=None):
        seen.append("start")
        await eng._emit("lesson.building", {"message": "Planning the lesson", "progress": 0.1})
        try:
            await asyncio.sleep(2)
            seen.append("built")
        except asyncio.CancelledError:
            seen.append("cancelled")
            raise

    monkeypatch.setattr(eng.session, "learn", learn)
    goal = catalog.get("intro-blender")["lessons"][0]["goal"]
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        assert ws.receive_json()["type"] == "engine.hello"
        _plans(ws, "plan.start", {"catalogId": "intro-blender"})
        ws.send_json({"type": "learn", "payload": {"query": goal, "mode": "lesson", "plan": {"id": "intro-blender", "index": 0}}})
        _until(ws, "lesson.building")
        ws.send_json({"type": "plan.remove", "payload": {"id": "intro-blender", "reqId": "r-rm"}})
        got = _queued_fence(ws)  # behind the learn had it not been cancelled
        ended = [m["payload"] for m in got if m["type"] == "lesson.ended"]
        assert [e["reason"] for e in ended] == ["stopped"]
        assert not [m for m in got if m["type"] == "lesson.building"]  # nothing of the build after the stop
        out = _plans(ws, "plans.list", {})
        assert [p["id"] for p in out["items"]] == []
    assert seen == ["start", "cancelled"]
    assert eng._plan_ref is None
    saved = json.loads((state_dir() / "plans.json").read_text())
    assert "intro-blender" not in saved["plans"]


# ----------------------------------------------------------------------------------- side calls end with the build


def test_a_side_call_is_cancelled_when_its_build_is():
    async def go() -> tuple[bool, bool]:
        side: list[asyncio.Future] = []

        async def build() -> None:
            side.append(builder.end_with_build(asyncio.ensure_future(asyncio.sleep(30))))
            await asyncio.sleep(30)

        t = asyncio.ensure_future(build())
        await asyncio.sleep(0.01)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        await asyncio.sleep(0)
        return side[0].cancelled(), t.cancelled()

    assert asyncio.run(go()) == (True, True)


def test_a_side_call_that_finished_is_left_alone():
    async def go() -> str:
        async def build() -> asyncio.Future:
            f = builder.end_with_build(asyncio.ensure_future(asyncio.sleep(0, result="done")))
            await f
            return f

        f = await asyncio.ensure_future(build())
        await asyncio.sleep(0)
        return f.result()

    assert asyncio.run(go()) == "done"
