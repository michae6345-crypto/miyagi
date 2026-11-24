"""Activity + bon in the engine (orchestrator/activity_feed.py): what counts, the activity.get round trip, the pushes,
idle time left out, Delete my data. A fake WebSocket on the real hub; stub modules (no model call, no network)."""

from __future__ import annotations

import asyncio
import copy
import time
from types import SimpleNamespace

from server.orchestrator import activity_feed as af
from server.orchestrator import stubs
from server.orchestrator.tests.test_launch_contract import _engine, quiet_env  # noqa: F401 - fixture
from server.sessions import activity as act
from server.sessions import review as review_mod

NOON = time.mktime((2026, 11, 24, 12, 0, 0, 0, 0, -1))


class FakeWS:
    """What the hub needs of a WebSocket: send_json. Everything sent is kept."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, msg: dict) -> None:
        self.sent.append(msg)

    def of(self, type_: str) -> list[dict]:
        return [m["payload"] for m in self.sent if m["type"] == type_]


class Clock:
    def __init__(self, wall: float = NOON) -> None:
        self.w, self.m = wall, 1000.0

    def wall(self) -> float:
        return self.w

    def mono(self) -> float:
        return self.m

    def step(self, dt: float) -> None:
        self.w += dt
        self.m += dt


def _rig(monkeypatch, clock: Clock | None = None):
    main, eng, _ws, calls = _engine(monkeypatch)
    clock = clock or Clock()
    eng.activity = af.ActivityFeed(eng.hub.emit, wall=clock.wall, mono=clock.mono)
    fake = FakeWS()
    eng.hub.join(fake)
    return main, eng, fake, clock, calls


async def _start(eng, graph: dict | None = None) -> None:
    await eng.session.load_graph(graph or stubs.load_fixture_lesson())
    await eng.session.drain()


async def _pass(eng) -> str:
    sid = eng.session.step["id"]
    await eng.session._pass_step()
    await eng.session.drain()
    await asyncio.sleep(0)
    return sid


async def _get(eng, fake) -> dict:
    n = len(fake.of("activity"))
    await eng.dispatch({"type": "activity.get", "payload": {}}, ws=fake)
    got = fake.of("activity")
    assert len(got) == n + 1
    return got[-1]


# --------------------------------------------------------------------------------------- round trips
def test_activity_get_answers_the_snapshot_and_hello_lists_it(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        assert "activity.get" in eng.capabilities()
        snap = await _get(eng, fake)
        assert snap["bon"] == {"steps": 0, "level": 1, "name": "Seed",
                               "next": {"level": 2, "name": "Sprout", "at": 3, "left": 3}, "fraction": 0.0}
        assert snap["totals"] == {"minutes": 0, "passedSteps": 0, "lessonsCompleted": 0, "activeDays": 0}
        assert len(snap["days"]) == 84 and snap["recent"] == [] and snap["milestones"] == []

    asyncio.run(go())
    assert calls == []


def test_activity_get_over_the_real_websocket(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, eng, _ws, _calls = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            hello = ws.receive_json()
            assert "activity.get" in hello["payload"]["capabilities"]
            ws.send_json({"type": "activity.get", "payload": {}})
            for _ in range(50):
                msg = ws.receive_json()
                if msg["type"] == "activity":
                    break
            assert msg["type"] == "activity" and msg["payload"]["bon"]["level"] == 1


def test_passing_steps_counts_pushes_and_tags_skills(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        lid = eng.session.graph["lesson"]["id"]
        passed = [await _pass(eng) for _ in range(3)]
        pushes = fake.of("activity")
        assert len(pushes) == 3  # one push per counted pass
        last = pushes[-1]
        assert last["bon"]["steps"] == 3 and last["bon"]["level"] == 2 and last["bon"]["name"] == "Sprout"
        assert [r["stepId"] for r in last["recent"]] == passed[::-1]
        r0 = last["recent"][0]
        assert r0["lessonId"] == lid and r0["title"] and r0["lessonTitle"]
        assert r0["skills"] and all(set(s) == {"id", "label"} for s in r0["skills"])
        assert {m["id"] for m in last["milestones"]} == {"first_step", "level:2"}
        snap = await _get(eng, fake)
        assert snap["totals"]["passedSteps"] == 3
        await eng.activity.flush()
        assert act.Activity.load().count == 3  # saved on this Mac

    asyncio.run(go())
    assert calls == []


def test_skipped_already_and_provisional_steps_never_count(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        s = eng.session
        await eng.activity.observe(s, "step.passed", {"stepId": s.step["id"], "skipped": True})
        await eng.activity.observe(s, "step.passed", {"stepId": s.step["id"], "already": True})
        await eng.activity.observe(s, "step.passed", {"stepId": "no-such-step"})
        await eng.activity.observe(s, "step.passed", {})
        await s._pass_step(skipped=True)  # the real Skip
        await s.drain()
        assert eng.activity.a.count == 0 and fake.of("activity") == []
        g = copy.deepcopy(s.graph)
        g["steps"][0]["provisional"] = True
        s.graph = g
        await eng.activity.observe(s, "step.passed", {"stepId": g["steps"][0]["id"]})
        assert eng.activity.a.count == 0

    asyncio.run(go())


def test_the_same_step_passed_again_does_not_count_twice(quiet_env, monkeypatch):
    """A lesson started again (library.start keeps its id) and a review replay (its own lesson id) pass the same steps."""
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        g = stubs.load_fixture_lesson()
        await _start(eng, copy.deepcopy(g))
        first = await _pass(eng)
        assert eng.activity.a.count == 1
        await eng.session.end_lesson("new lesson")
        await _start(eng, copy.deepcopy(g))  # the same lesson again from step 1
        assert eng.session.step["id"] == first
        await _pass(eng)
        assert eng.activity.a.count == 1
        await eng.session.end_lesson("new lesson")
        rg = review_mod.review_graph(copy.deepcopy(g), g["steps"][0]["title"], "k", skill_id="x")
        if rg is None or rg["steps"][0]["id"] != first:  # the fixture's first skill: build a one-step review by hand
            rg = copy.deepcopy(g)
            rg["steps"] = [rg["steps"][0]]
            rg["lesson"]["review"] = {"key": "k", "label": "x", "skillId": "x", "lessonId": g["lesson"]["id"]}
            rg["lesson"]["id"] = "review-x-" + g["lesson"]["id"]
        assert rg["lesson"]["id"] != g["lesson"]["id"]
        await _start(eng, rg)
        await _pass(eng)
        assert eng.activity.a.count == 1  # the review replayed a counted step: not new
        last = fake.of("activity")[-1]
        assert last["bon"]["steps"] == 1 and len(last["recent"]) == 1  # the same step back to back: one row
        eng.session.graph["lesson"]["review"]["lessonId"] = "lesson-other"  # a review of a step not seen yet
        await eng.activity.observe(eng.session, "step.passed", {"stepId": first})
        row = fake.of("activity")[-1]["recent"][0]
        assert row["review"] is True and row["lessonId"] == rg["lesson"]["id"] and eng.activity.a.count == 2

    asyncio.run(go())


def test_the_counter_survives_an_engine_restart(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        await _pass(eng)
        await eng.stop()

    asyncio.run(go())
    main2, eng2, _ws, _c = _engine(monkeypatch)  # a new engine on the same disk (its feed loads activity.json)
    fake2 = FakeWS()
    eng2.hub.join(fake2)

    async def again():
        snap = await _get(eng2, fake2)
        assert snap["bon"]["steps"] == 1 and len(snap["recent"]) == 1

    asyncio.run(again())


def test_a_finished_lesson_is_a_dated_milestone_once(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        s = eng.session
        lid = s.graph["lesson"]["id"]
        card = {"kind": "complete", "title": "Done", "result": {"passed": 6, "skipped": 0, "total": 6, "lessonId": lid,
                                                              "title": "PINN lesson"}}
        await eng._emit("card", card)
        await eng._emit("card", card)  # the reconnect replay sends it again
        lessons = [m for m in fake.of("activity")[-1]["milestones"] if m["kind"] == "lesson"]
        assert len(lessons) == 1 and lessons[0]["label"] == "Finished PINN lesson" and lessons[0]["date"] == "2026-11-24"
        assert len(fake.of("activity")) == 1
        await eng._emit("card", {"kind": "hint", "title": "x"})  # any other card: nothing
        assert len(fake.of("activity")) == 1

    asyncio.run(go())


# --------------------------------------------------------------------------------------- minutes
def test_minutes_count_active_lesson_time_and_leave_idle_out(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        s = eng.session
        feed = eng.activity
        await feed.tick(s)
        for _ in range(30):  # no lesson: nothing counts
            clock.step(2)
            await feed.tick(s)
        assert feed.a.total_s == 0
        await _start(eng)
        assert af.lesson_running(s)
        now = [0.0]
        s.clock = lambda: now[0]
        s.video_playing = False
        s.inputs = SimpleNamespace(seconds_since_key=lambda: None)
        s.last_activity = 0.0
        for _ in range(60):  # active: a save / key / screen change in the last 2 minutes
            clock.step(1)
            now[0] += 1
            await feed.tick(s)
        assert 59 <= feed.a.total_s <= 60
        pushes = [p for p in fake.of("activity")]
        assert pushes and pushes[-1]["today"] == 1  # today's minutes went up: pushed
        now[0] += af.IDLE_S + 1  # idle for over two minutes: nothing more counts
        for _ in range(30):
            clock.step(1)
            await feed.tick(s)
        assert feed.a.total_s <= 60
        s.inputs = SimpleNamespace(seconds_since_key=lambda: 3.0)  # typing again
        for _ in range(10):
            clock.step(1)
            await feed.tick(s)
        assert 69 <= feed.a.total_s <= 70
        s.inputs = SimpleNamespace(seconds_since_key=lambda: 999.0)
        assert not s.lesson_mode  # the fixture is a video lesson
        s.video_playing, s.segment_done = True, False  # watching the lesson video
        for _ in range(10):
            clock.step(1)
            await feed.tick(s)
        assert 79 <= feed.a.total_s <= 80
        clock.step(600)  # the Mac slept: one long gap never counts
        await feed.tick(s)
        assert feed.a.total_s <= 80
        s.awaiting_resume = True  # "Continue?" is up: the lesson is frozen
        for _ in range(10):
            clock.step(1)
            await feed.tick(s)
        assert feed.a.total_s <= 80
        await feed.flush()
        assert act.Activity.load().total_s >= 79

    asyncio.run(go())


def test_minute_pushes_are_at_most_one_a_minute(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        s = eng.session
        s.inputs = SimpleNamespace(seconds_since_key=lambda: 0.5)
        await eng.activity.tick(s)
        for _ in range(300):
            clock.step(1)
            await eng.activity.tick(s)
        assert len(fake.of("activity")) == 5

    asyncio.run(go())


def test_no_app_connected_counts_nothing(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        s = eng.session
        s.inputs = SimpleNamespace(seconds_since_key=lambda: 0.5)
        s.app_left = lambda: True
        await eng.activity.tick(s)
        for _ in range(20):
            clock.step(1)
            await eng.activity.tick(s)
        assert eng.activity.a.total_s == 0

    asyncio.run(go())


# --------------------------------------------------------------------------------------- privacy
def test_delete_my_data_erases_activity_and_pushes_the_empty_snapshot(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        await _pass(eng)
        await eng.activity.flush()
        assert act.Activity.load().count == 1
        await eng.dispatch({"type": "data.delete", "payload": {}}, ws=fake)
        assert fake.of("activity")[-1]["bon"]["steps"] == 0
        assert act.Activity.load().count == 0
        snap = await _get(eng, fake)
        assert snap["recent"] == [] and snap["milestones"] == []

    asyncio.run(go())


def test_a_failing_save_never_costs_the_event(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    def boom(_data):
        raise OSError("disk full")

    monkeypatch.setattr(act.Activity, "write", staticmethod(boom))

    async def go():
        await _start(eng)
        sid = await _pass(eng)
        assert any(p["stepId"] == sid for p in fake.of("step.passed"))
        await eng.activity.flush()
        assert eng.activity._dirty is True  # tried again on the next change

    asyncio.run(go())


def test_step_key_uses_the_reviewed_lesson():
    assert af.step_key({"id": "lesson-a"}, "s1") == "lesson-a:s1"
    assert af.step_key({"id": "review-x-lesson-a", "review": {"lessonId": "lesson-a"}}, "s1") == "lesson-a:s1"
    assert af.step_key({}, "s1") == "" and af.step_key({"id": "a"}, "") == ""
