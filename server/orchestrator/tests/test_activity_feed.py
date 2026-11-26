"""Activity + bon in the engine (orchestrator/activity_feed.py): what counts, the ui-v4 round trips (activity.get, bon.get,
bon.import), the step.passed fields, the pushes, idle time left out, day boundaries and clock jumps, Delete my data.
A fake WebSocket on the real hub (every payload is validated against the contract); stub modules (no model call, no
network)."""

from __future__ import annotations

import asyncio
import copy
import time
from types import SimpleNamespace

import pytest

from server.orchestrator import activity_feed as af
from server.orchestrator import stubs
from server.orchestrator.tests.test_launch_contract import _engine, quiet_env  # noqa: F401 - fixture
from server.sessions import activity as act
from server.sessions import review as review_mod
from server.sessions import store
from shared.contracts.events import validate_engine_payload

NOON = time.mktime((2026, 11, 24, 12, 0, 0, 0, 0, -1))


@pytest.fixture(autouse=True)
def _no_push_gap(monkeypatch):
    """Most tests look at every push; test_activity_pushes_are_at_most_one_every_10_s puts the contract's gap back."""
    monkeypatch.setattr(af, "PUSH_EVERY_S", 0.0)


class FakeWS:
    """What the hub needs of a WebSocket: send_json. Everything sent is kept, and checked against the contract."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, msg: dict) -> None:
        if msg["type"] in ("activity", "bon", "step.passed"):
            validate_engine_payload(msg["type"], msg["payload"])
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


def _rig(monkeypatch, clock: Clock | None = None, **kw):
    main, eng, _ws, calls = _engine(monkeypatch)
    clock = clock or Clock()
    eng.activity = af.ActivityFeed(eng.hub.emit, wall=clock.wall, mono=clock.mono, **kw)
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


async def _ask(eng, fake, type_: str = "activity.get", payload: dict | None = None, answer: str = "activity") -> dict:
    n = len(fake.of(answer))
    await eng.dispatch({"type": type_, "payload": payload or {}}, ws=fake)
    got = fake.of(answer)
    assert len(got) == n + 1
    return got[-1]


def _running(eng, clock: Clock) -> None:
    """The lesson is running and the learner is typing."""
    s = eng.session
    s.video_playing = False
    s.inputs = SimpleNamespace(seconds_since_key=lambda: 0.5)


# --------------------------------------------------------------------------------------- round trips
def test_activity_get_and_bon_get_answer_and_hello_lists_them(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        caps = eng.capabilities()
        assert {"activity.get", "bon.get", "bon.import"} <= set(caps)
        snap = await _ask(eng, fake)
        assert snap["totals"] == {"lessonsFinished": 0, "stepsPassed": 0, "minutes": 0}
        assert snap["week"] == {"minutes": 0, "stepsPassed": 0, "skillsMastered": 0} and snap["minutesTracked"] is True
        assert len(snap["days"]) == 84 and snap["recent"] == [] and snap["milestones"] == []
        b = await _ask(eng, fake, "bon.get", answer="bon")
        assert b == {"steps": 0, "level": 1, "name": "Seed",
                     "next": {"level": 2, "name": "Sprout", "at": 3, "left": 3}, "fraction": 0.0}

    asyncio.run(go())
    assert calls == []


def test_activity_get_over_the_real_websocket(quiet_env, monkeypatch):
    from fastapi.testclient import TestClient

    main, eng, _ws, _calls = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            hello = ws.receive_json()
            assert {"activity.get", "bon.get", "bon.import"} <= set(hello["payload"]["capabilities"])
            ws.send_json({"type": "activity.get", "payload": {}})
            ws.send_json({"type": "bon.get", "payload": {}})
            got: dict[str, dict] = {}
            for _ in range(50):
                msg = ws.receive_json()
                if msg["type"] in ("activity", "bon"):
                    got[msg["type"]] = msg["payload"]
                if len(got) == 2:
                    break
            assert len(got["activity"]["days"]) == 84 and got["bon"]["level"] == 1


def test_passing_steps_counts_tags_step_passed_and_pushes_bon_then_activity(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        await _ask(eng, fake)
        lid = eng.session.graph["lesson"]["id"]
        passed = [await _pass(eng) for _ in range(3)]
        sp = fake.of("step.passed")
        assert [p["key"] for p in sp] == [f"{lid}:{x}" for x in passed] and all(p["counted"] is True for p in sp)
        ready = {st["id"]: st.get("skillIds") for st in fake.of("lesson.ready")[-1]["steps"]} if fake.of("lesson.ready") \
            else {}
        from server.orchestrator import skill_hooks

        tree = skill_hooks.tags(eng.session)  # a catalog lesson tags with catalog ids (UI-V4.md "Skill tags")
        for p in sp:  # the skill tree's catalog ids when it has them, else lesson.ready's StepSummary.skillIds
            if tree.get(p["stepId"]):
                assert p["skillIds"] == tree[p["stepId"]]
            elif ready.get(p["stepId"]):
                assert p["skillIds"] == ready[p["stepId"]]
        bons = fake.of("bon")
        assert [b["steps"] for b in bons] == [1, 2, 3] and [b.get("grew") for b in bons] == [False, False, True]
        assert bons[-1]["name"] == "Sprout" and bons[-1]["lastKey"] == sp[-1]["key"]
        last = fake.of("activity")[-1]
        assert [r["stepId"] for r in last["recent"]] == passed[::-1]
        r0 = last["recent"][0]
        assert r0["lessonId"] == lid and r0["stepTitle"] and r0["lessonTitle"] and r0["key"] == sp[-1]["key"]
        if r0.get("skillIds"):
            assert len(r0["skills"]) == len(r0["skillIds"])
        assert [m["kind"] for m in last["milestones"]] == ["first_step"]
        assert last["totals"]["stepsPassed"] == 3 and last["days"][-1]["steps"] == 3
        await eng.activity.flush()
        assert act.Activity.load().count == 3  # saved on this Mac

    asyncio.run(go())
    assert calls == []


def test_no_activity_push_until_an_app_asks(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        await _pass(eng)
        assert fake.of("activity") == [] and len(fake.of("bon")) == 1  # bon is pushed to every window
        await _ask(eng, fake)
        await _pass(eng)
        assert len(fake.of("activity")) == 2

    asyncio.run(go())


def test_skipped_already_and_provisional_steps_never_count(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        await _ask(eng, fake)
        s = eng.session
        sid = s.step["id"]
        for extra in ({"skipped": True}, {"already": True}):
            out = eng.activity.annotate(s, "step.passed", {"stepId": sid, **extra})
            assert out["counted"] is False and out["key"].endswith(f":{sid}")
            await eng.activity.observe(s, "step.passed", out)
        await eng.activity.observe(s, "step.passed", {"stepId": "no-such-step"})
        await eng.activity.observe(s, "step.passed", {})
        await s._pass_step(skipped=True)  # the real Skip
        await s.drain()
        assert fake.of("step.passed")[-1]["counted"] is False
        assert eng.activity.a.count == 0 and len(fake.of("activity")) == 1 and fake.of("bon") == []
        g = copy.deepcopy(s.graph)
        g["steps"][0]["provisional"] = True
        s.graph = g
        assert eng.activity.annotate(s, "step.passed", {"stepId": g["steps"][0]["id"]}) == {"stepId": g["steps"][0]["id"]}
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
        assert eng.activity.a.count == 1 and fake.of("step.passed")[-1]["counted"] is False
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
        assert fake.of("step.passed")[-1]["key"] == f"{g['lesson']['id']}:{first}"
        assert len(fake.of("bon")) == 1
        eng.session.graph["lesson"]["review"]["lessonId"] = "lesson-other"  # a review of a step not seen yet
        await eng.activity.observe(eng.session, "step.passed", {"stepId": first})
        await _ask(eng, fake)
        row = fake.of("activity")[-1]["recent"][0]
        assert row["lessonId"] == "lesson-other" and row["key"] == f"lesson-other:{first}" and eng.activity.a.count == 2

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
        snap = await _ask(eng2, fake2)
        assert snap["totals"]["stepsPassed"] == 1 and len(snap["recent"]) == 1
        assert (await _ask(eng2, fake2, "bon.get", answer="bon"))["steps"] == 1

    asyncio.run(again())


def test_bon_import_keeps_the_larger_count(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        lid = eng.session.graph["lesson"]["id"]
        sid = eng.session.step["id"]
        b = await _ask(eng, fake, "bon.import", {"steps": 24, "seen": [f"{lid}:{sid}"]}, answer="bon")
        assert b["steps"] == 24 and b["name"] == "Sapling"
        await _pass(eng)  # the app had counted this step already
        assert fake.of("step.passed")[-1]["counted"] is False and eng.activity.a.count == 24
        b = await _ask(eng, fake, "bon.import", {"steps": 3}, answer="bon")
        assert b["steps"] == 24  # never lowered
        await eng.activity.flush()
        assert act.Activity.load().count == 24

    asyncio.run(go())


def test_a_finished_lesson_is_a_dated_milestone_once(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        await _ask(eng, fake)
        s = eng.session
        lid = s.graph["lesson"]["id"]
        card = {"kind": "complete", "title": "Done", "result": {"passed": 6, "skipped": 0, "total": 6, "lessonId": lid,
                                                              "title": "PINN lesson"}}
        await eng._emit("card", card)
        await eng._emit("card", card)  # the reconnect replay sends it again
        last = fake.of("activity")[-1]
        assert [m["kind"] for m in last["milestones"]] == ["first_lesson"] and last["totals"]["lessonsFinished"] == 1
        assert len(fake.of("activity")) == 2
        await eng._emit("card", {"kind": "hint", "title": "x"})  # any other card: nothing
        assert len(fake.of("activity")) == 2

    asyncio.run(go())


# --------------------------------------------------------------------------------------- pushes
def test_activity_pushes_are_at_most_one_every_10_s(quiet_env, monkeypatch):
    monkeypatch.setattr(af, "PUSH_EVERY_S", 10.0)
    waits: list[float] = []
    gate = asyncio.Event

    async def go():
        released = gate()

        async def sleep(dt: float) -> None:
            waits.append(dt)
            await released.wait()

        main, eng, fake, clock, calls = _rig(monkeypatch, sleep=sleep)
        await _start(eng)
        await _ask(eng, fake)
        n = len(fake.of("activity"))
        await _pass(eng)
        assert len(fake.of("activity")) == n  # 0 s after the answer: waits for the next slot
        await _pass(eng)
        assert len(fake.of("activity")) == n and len(waits) == 1 and waits[0] == pytest.approx(10.0)  # one owed push
        released.set()
        for _ in range(5):
            await asyncio.sleep(0)
        assert len(fake.of("activity")) == n + 1 and fake.of("activity")[-1]["totals"]["stepsPassed"] == 2  # newest
        clock.step(11)
        await _pass(eng)
        assert len(fake.of("activity")) == n + 2  # the gap passed: at once
        assert len(fake.of("bon")) == 3  # bon is never held back
        await eng.activity.flush()

    asyncio.run(go())


# --------------------------------------------------------------------------------------- minutes
def test_minutes_count_active_lesson_time_and_leave_idle_out(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        s = eng.session
        feed = eng.activity
        await _ask(eng, fake)
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
        assert fake.of("activity")[-1]["days"][-1]["minutes"] == 1  # today's minutes went up: pushed
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
        await _ask(eng, fake)
        _running(eng, clock)
        await eng.activity.tick(eng.session)
        n = len(fake.of("activity"))
        for _ in range(300):
            clock.step(1)
            await eng.activity.tick(eng.session)
        assert len(fake.of("activity")) - n == 5

    asyncio.run(go())


def test_minutes_cross_local_midnight_into_the_new_day(quiet_env, monkeypatch):
    late = time.mktime((2026, 11, 24, 23, 58, 0, 0, 0, -1))
    main, eng, fake, clock, calls = _rig(monkeypatch, Clock(late))

    async def go():
        await _start(eng)
        await _ask(eng, fake)
        _running(eng, clock)
        feed = eng.activity
        await feed.tick(eng.session)
        for _ in range(119):  # 23:58:00 -> 23:59:59
            clock.step(1)
            await feed.tick(eng.session)
        assert fake.of("activity")[-1]["days"][-1] == {"date": "2026-11-24", "minutes": 1, "steps": 0}
        n = len(fake.of("activity"))
        clock.step(1)
        await feed.tick(eng.session)  # 00:00:00: today is a new day with no minutes yet
        assert len(fake.of("activity")) == n + 1
        snap = fake.of("activity")[-1]
        assert snap["days"][-1] == {"date": "2026-11-25", "minutes": 0, "steps": 0}
        assert snap["days"][-2] == {"date": "2026-11-24", "minutes": 1, "steps": 0}
        for _ in range(60):
            clock.step(1)
            await feed.tick(eng.session)
        assert fake.of("activity")[-1]["days"][-1]["minutes"] == 1
        assert feed.a.days["2026-11-24"] == pytest.approx(119) and feed.a.days["2026-11-25"] == pytest.approx(61)

    asyncio.run(go())


@pytest.mark.parametrize("jump", [-2 * 86400.0, 3 * 86400.0])
def test_a_wall_clock_jump_counts_only_the_monotonic_second(quiet_env, monkeypatch, jump):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        _running(eng, clock)
        feed = eng.activity
        await feed.tick(eng.session)
        clock.step(1)
        await feed.tick(eng.session)
        assert feed.a.total_s == pytest.approx(1)
        clock.w += jump  # the Mac's clock was set back / forward; one real second passes
        clock.step(1)
        await feed.tick(eng.session)
        assert feed.a.total_s == pytest.approx(2)
        new_day = act.day_of(clock.w)
        assert feed.a.days[new_day] == pytest.approx(1) and feed.a.days[act.day_of(NOON)] == pytest.approx(1)
        assert feed.snapshot()["days"][-1]["date"] == new_day

    asyncio.run(go())


def test_no_app_connected_counts_nothing(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        s = eng.session
        _running(eng, clock)
        s.app_left = lambda: True
        await eng.activity.tick(s)
        for _ in range(20):
            clock.step(1)
            await eng.activity.tick(s)
        assert eng.activity.a.total_s == 0

    asyncio.run(go())


# --------------------------------------------------------------------------------------- privacy
def test_delete_my_data_erases_activity_and_pushes_the_empty_state(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        await _start(eng)
        await _ask(eng, fake)
        await _pass(eng)
        await eng.activity.flush()
        assert act.Activity.load().count == 1
        await eng.dispatch({"type": "data.delete", "payload": {"what": ["notes"]}}, ws=fake)  # notes only: kept
        assert act.Activity.load().count == 1 and eng.activity.a.count == 1
        await eng.dispatch({"type": "data.delete", "payload": {}}, ws=fake)
        assert fake.of("activity")[-1]["totals"]["stepsPassed"] == 0 and fake.of("bon")[-1]["steps"] == 0
        assert act.Activity.load().count == 0 and not (store.state_dir() / act.FILE).exists()
        snap = await _ask(eng, fake)
        assert snap["recent"] == [] and snap["milestones"] == []
        await _start(eng)
        await _pass(eng)
        await eng.dispatch({"type": "data.delete", "payload": {"what": ["progress"]}}, ws=fake)
        assert eng.activity.a.count == 0

    asyncio.run(go())


def test_a_save_scheduled_before_delete_my_data_never_writes_the_old_data_back(quiet_env, monkeypatch):
    """The blocker: a save queued by a pass (or the 60 s tick) snapshotted the old data and waited on the lock that
    erase() held; it then wrote the counter, minutes and milestones back after the file was deleted."""
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        feed = eng.activity
        feed.a.pass_step("lesson-a:s1", {"stepId": "s1", "lessonId": "lesson-a"}, NOON)
        feed.a.add_seconds(120, NOON)
        feed._dirty = True
        feed._save_soon()  # queued, not run yet
        await feed.erase()
        await feed.flush()
        assert not (store.state_dir() / act.FILE).exists()
        assert act.Activity.load().count == 0 and act.Activity.load().total_s == 0
        feed.a.pass_step("lesson-a:s2", {"stepId": "s2", "lessonId": "lesson-a"}, NOON)  # a new pass after the erase
        feed._dirty = True
        feed._save_soon()
        await feed.flush()
        assert act.Activity.load().count == 1 and not act.Activity.load().has("lesson-a:s1")

    asyncio.run(go())


def test_a_save_already_writing_finishes_before_the_erase(quiet_env, monkeypatch):
    main, eng, fake, clock, calls = _rig(monkeypatch)

    async def go():
        feed = eng.activity
        feed.a.pass_step("lesson-a:s1", {"stepId": "s1", "lessonId": "lesson-a"}, NOON)
        feed._dirty = True
        task = asyncio.get_running_loop().create_task(feed._save_now())
        await asyncio.sleep(0)  # the save holds the lock and is writing in its thread
        await feed.erase()
        await task
        assert not (store.state_dir() / act.FILE).exists()

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
