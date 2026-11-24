"""Time to the first lesson step (lane eng-build-speed): the real builder on a virtual clock, every model call faked at
the latencies of the recorded Nov 22 build (speed_harness.py). Step 1 reaches the learner as soon as it is built,
the finished lesson is identical to the old serial build's, and the step-1 fast path falls back to the old path
whenever it can't finish. Offline: no key, no network, no paid call."""

from __future__ import annotations

import asyncio
import copy

import pytest

from server.lesson import builder, claude
from server.lesson.tests import speed_harness as h
from server.lesson.tests.test_app_lesson import autocad


@pytest.fixture(scope="module")
def runs():
    out = {}
    for name, p in (("clean", h.PROFILE_10MIN), ("s1_retry", h.PROFILE_10MIN_S1_RETRY)):
        out[name] = {"before": h.build_once(p, fast=False), "after": h.build_once(p, fast=True)}
    return out


def test_first_step_under_20s_on_a_10_minute_video(runs):
    print("\n" + h.report())  # pytest -s: the critical-path timeline, before vs after
    clean, retry = runs["clean"], runs["s1_retry"]
    assert h.first_step_s(clean["before"]) >= 35 and h.first_step_s(retry["before"]) >= 38  # the old serial build
    assert h.first_step_s(clean["after"]) <= 15.5  # segment 8.8 + step 1's detail 3.6 + its adapt 2.6
    assert h.first_step_s(retry["after"]) <= 20.5  # + step 1's lint retry (Sonnet, 5 s)
    for r in (clean, retry):  # the full lesson is no slower
        assert r["after"]["done_s"] <= r["before"]["done_s"] + 0.5


def test_the_finished_lesson_is_identical(runs):
    for r in runs.values():
        before, after = r["before"]["graph"], r["after"]["graph"]
        assert h.comparable(before) == h.comparable(after)
        assert [s["id"] for s in after["steps"]] == [f"s{i}" for i in range(1, 7)] and after["lesson"]["complete"] is True
        assert after["build"]["firstStep"]["same"] is True and "firstStep" not in before["build"]


def test_step_1_streams_first_then_the_rest_is_appended(runs):
    for r in runs.values():
        ups = [u for u in r["after"]["updates"] if not u["provisional"]]
        first = ups[0]
        assert first["steps"] == ["s1"] and first["complete"] is False
        g = first["graph"]
        assert g["lesson"]["id"] == r["after"]["graph"]["lesson"]["id"] and g["sources"][0]["videoId"] == h.VID
        assert g["steps"][0] == r["after"]["graph"]["steps"][0]  # the step the learner got is the lesson's step 1
        assert g["steps"][0]["checks"] and g["build"]["adapted"] is True
        # the old build streamed nothing real before the end (the quick-start placeholder, then the whole lesson)
        assert all(u["complete"] for u in r["before"]["updates"] if not u["provisional"])


def test_step_1_goes_before_the_rest_of_the_fan_out(runs):
    ev = runs["clean"]["after"]["events"]
    s1_adapt = next(e for e in ev if e["kind"] == "adapt" and e["steps"] == [1])
    s1_detail = next(e for e in ev if e["kind"] == "detail" and e["steps"] == [1])
    assert s1_adapt["start"] == s1_detail["end"]  # its lane was kept: no wait behind steps 5 and 6
    starts = {e["steps"][0]: e["start"] for e in ev if e["kind"] == "detail"}
    assert {starts[i] for i in (1, 2, 3, 4)} == {s1_detail["start"]}  # 4 lanes: steps 1-4 start together
    assert starts[5] > s1_adapt["start"] and starts[6] > s1_adapt["start"]  # 5 and 6 wait, step 1's adapt does not


def test_captions_load_while_the_lesson_caches_are_asked(runs):
    after, before = runs["clean"]["after"]["events"], runs["clean"]["before"]["events"]
    cap = next(e for e in after if e["kind"] == "captions")
    claim = next(e for e in after if e["kind"] == "shared_claim")
    assert cap["start"] < claim["end"]  # in parallel now
    assert next(e for e in before if e["kind"] == "captions")["start"] >= next(e for e in before if e["kind"] == "shared_claim")["end"]


def test_a_cache_hit_never_waits_for_captions(tmp_path):
    h.build_once(h.PROFILE_10MIN, fast=True, root=tmp_path)
    fakes = h.Fakes(h.PROFILE_10MIN)
    run = h.build_once(h.PROFILE_10MIN, fast=True, root=tmp_path, fakes=fakes)
    assert run["done_s"] < 0.1 and not [e for e in run["events"] if e["kind"] in ("captions", "segment", "adapt")]


def test_a_cached_draft_still_sends_step_1_first(tmp_path):
    """readapt (a cached video draft): only the adapt pass runs, and step 1 still goes out before the rest."""
    h.build_once(h.PROFILE_10MIN, fast=True, root=tmp_path)
    slow = h.build_once(h.PROFILE_10MIN, fast=False, root=tmp_path, readapt=True)
    fast = h.build_once(h.PROFILE_10MIN, fast=True, root=tmp_path, readapt=True)
    real = [u for u in fast["updates"] if not u["provisional"]]
    assert real and real[0]["steps"] == ["s1"] and real[0]["t"] < fast["done_s"]
    assert h.first_step_s(fast) < h.first_step_s(slow)
    assert h.comparable(fast["graph"]) == h.comparable(slow["graph"])
    assert not [e for e in fast["events"] if e["kind"] in ("segment", "detail")]


def test_a_failed_early_step_1_falls_back_to_the_full_build(monkeypatch):
    """Step 1's own adapt call fails: nothing real is streamed early, and the full build adapts step 1 as before."""
    fakes = h.Fakes(h.PROFILE_10MIN)
    real_call = fakes.call_once
    failed = []

    async def flaky(mid, system, prompt, *, effort, schema):
        if '"index": 1' in h._text(prompt) and '"index": 2' not in h._text(prompt):  # step 1 alone: down, escalation too
            failed.append(1)
            raise RuntimeError("Claude call failed (500): overloaded")
        return await real_call(mid, system, prompt, effort=effort, schema=schema)

    fakes.call_once = flaky
    run = h.build_once(h.PROFILE_10MIN, fast=True, fakes=fakes)
    before = h.build_once(h.PROFILE_10MIN, fast=False)
    assert failed and h.comparable(run["graph"]) == h.comparable(before["graph"])
    assert all(u["complete"] for u in run["updates"] if not u["provisional"])  # the whole lesson, at the end
    assert "firstStep" not in run["graph"]["build"]


def test_kill_switch_is_the_old_serial_build(runs):
    ev = runs["clean"]["before"]["events"]
    seg = next(e for e in ev if e["kind"] == "segment")
    assert seg["start"] >= next(e for e in ev if e["kind"] == "captions")["end"]
    adapts = [e for e in ev if e["kind"] == "adapt"]
    assert sorted(map(tuple, (e["steps"] for e in adapts))) == [(1, 2, 3), (4, 5, 6)]  # batches of 3, as before


# --------------------------------------------------------------------------- claude._Lanes
def test_lanes_priority_goes_first_and_the_reserve_keeps_a_lane():
    async def go():
        lanes = claude._Lanes(2)
        order: list[str] = []
        gate = asyncio.Event()

        async def call(name: str, prio: bool = False):
            await lanes.acquire(prio)
            try:
                order.append(name)
                await gate.wait()
            finally:
                lanes.release(prio)

        held = [asyncio.ensure_future(call(f"a{i}")) for i in range(2)]
        await asyncio.sleep(0)
        queued = [asyncio.ensure_future(call(f"q{i}")) for i in range(2)]
        await asyncio.sleep(0)
        urgent = asyncio.ensure_future(call("p", prio=True))
        await asyncio.sleep(0)
        assert order == ["a0", "a1"] and lanes.busy == 2
        gate.set()
        await asyncio.gather(*held, *queued, urgent)
        assert order[2] == "p"  # jumped the two that queued before it
        assert lanes.busy == 0 and lanes.prio_busy == 0

        with lanes.reserve():  # one lane kept: non-priority callers get limit - 1
            gate2 = asyncio.Event()

            async def hold():
                await lanes.acquire()
                try:
                    await gate2.wait()
                finally:
                    lanes.release()

            t1 = asyncio.ensure_future(hold())
            t2 = asyncio.ensure_future(hold())
            await asyncio.sleep(0)
            assert lanes.busy == 1  # the second waits: the other lane is step 1's
            await lanes.acquire(True)  # ...and step 1 gets it at once
            assert lanes.busy == 2
            lanes.release(True)
            gate2.set()
            await asyncio.gather(t1, t2)
        assert lanes.busy == 0 and lanes.reserved == 0

    asyncio.run(go())


def test_lanes_give_the_lane_back_when_a_waiter_is_cancelled():
    async def go():
        lanes = claude._Lanes(1)
        await lanes.acquire()
        w = asyncio.ensure_future(lanes.acquire())
        await asyncio.sleep(0)
        w.cancel()
        await asyncio.gather(w, return_exceptions=True)
        lanes.release()
        assert lanes.busy == 0 and not lanes._waiters
        await asyncio.wait_for(lanes.acquire(), 1)  # nothing leaked
        lanes.release()

    asyncio.run(go())


# --------------------------------------------------------------------------- lesson-wide decisions for step 1 alone
def test_step_1_alone_is_not_made_an_app_step_when_a_later_step_writes_code():
    g = autocad()
    g["steps"] = g["steps"][:1]
    later = [{"index": 2, "title": "Script it", "run_command": "python3 make_car.py", "file": "make_car.py"}]
    assert "app" not in builder.normalize_checks(copy.deepcopy(g), set(), later)["lesson"]
    assert builder.normalize_checks(copy.deepcopy(g), set(), [{"index": 2, "title": "Extrude"}])["lesson"]["app"]["tool"] == "autocad"


def test_the_rest_is_adapted_while_step_1_is_still_being_fixed():
    """Fast details, step 1 needs a lint retry: the full build adapts steps 2-6 while step 1's lock is still on its
    way, never re-adapts step 1, and the finished lesson is still the old build's."""
    p = {**h.PROFILE_10MIN, "detail_s": [1.0] * 6, "lint_fail": {1}}
    before, after = h.build_once(p, fast=False), h.build_once(p, fast=True)
    ev = after["events"]
    s1_retry = next(e for e in ev if e["kind"] == "adapt_retry" and e["steps"] == [1])
    rest = next(e for e in ev if e["kind"] == "adapt" and 2 in e["steps"])
    assert rest["start"] < s1_retry["end"]  # in parallel
    assert sum(1 in e["steps"] for e in ev if e["kind"].startswith("adapt")) == 2  # round 1 + its retry, once each
    assert h.comparable(after["graph"]) == h.comparable(before["graph"])
    assert h.first_step_s(after) < h.first_step_s(before)


def test_a_failed_build_after_step_1_keeps_step_1():
    """The rest of the build fails (a later step's detail call is down): step 1 already went out, then the error is
    raised (the session keeps the steps it has, as for a long video's failed part)."""
    fakes = h.Fakes(h.PROFILE_10MIN)
    real_call = fakes.call_once

    async def down(mid, system, prompt, *, effort, schema):
        if "Fill in step 6" in h._text(prompt):
            await asyncio.sleep(9)
            raise RuntimeError("Claude call failed (500): overloaded")
        return await real_call(mid, system, prompt, effort=effort, schema=schema)

    fakes.call_once = down
    with pytest.raises(RuntimeError):
        h.build_once(h.PROFILE_10MIN, fast=True, fakes=fakes)
    real = [u for u in fakes.updates if not u["provisional"]]
    assert len(real) == 1 and real[0]["steps"] == ["s1"] and real[0]["complete"] is False


# --------------------------------------------------------------------------- review round 1
def test_the_workspace_sees_the_steps_still_being_built(runs):
    """Blocker 1: the starter files are made from the first graph the session gets. It carries the other steps as known
    so far (build.upcomingSteps; no event to the app carries `build`), so the scaffold's leak check and its list of
    files the learner creates cover steps 2..N."""
    from server.workspace import paths, scaffold

    first = next(u for u in runs["clean"]["after"]["updates"] if not u["provisional"])["graph"]
    up = first["build"]["upcomingSteps"]
    assert [u["index"] for u in up] == [2, 3, 4, 5, 6] and all(u["title"] for u in up)
    assert any(u.get("checks") for u in up)  # the details already in carry their draft checks
    steps = paths.lesson_steps(first)
    assert len(steps) == 6 and steps[0] == first["steps"][0]
    g = copy.deepcopy(first)
    g["build"]["upcomingSteps"] = [{"index": 2, "title": "Make data.csv", "checks": [
        {"id": "x", "type": "file_exists", "file": "data.csv"},
        {"id": "y", "type": "file_contains", "file": "todo.py", "pattern": "def part_2"}]}]
    assert "data.csv" in scaffold.learner_creates(g)
    assert scaffold.leaks("todo.py", "def part_2():\n    pass\n", g)  # a starter file holding step 2's code leaks
    assert "Make data.csv" in scaffold._lesson_for_prompt(g)
    done = copy.deepcopy(g)
    done["lesson"]["complete"] = True  # a finished lesson has every step itself: no side field read
    assert paths.lesson_steps(done) == done["steps"]


def _virtual_build(fakes, root, until_cancel_s=None, **kw):
    """build_lesson on the virtual clock; with until_cancel_s, cancel it then and report how long the cancel took."""
    from server.lesson import builder as b

    (root / "work").mkdir(exist_ok=True)
    with h.patched(fakes, fast=True, root=root):
        async def go():
            def on_update(graph, complete):
                fakes.updates.append({"t": round(h.now(), 3), "complete": complete,
                                      "provisional": bool((graph.get("lesson") or {}).get("provisional")),
                                      "steps": [s["id"] for s in graph.get("steps") or []], "graph": copy.deepcopy(graph)})

            task = asyncio.ensure_future(b.build_lesson(h.URL, h.GOAL, str(root / "work"), on_update=on_update,
                                                        video_meta={"title": h.TITLE, "length_s": 600}, **kw))
            if until_cancel_s is None:
                return await task
            await asyncio.sleep(until_cancel_s)
            t0 = h.now()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            took = h.now() - t0
            await asyncio.sleep(120)  # anything still running would have sent step 1 by now
            return took, claude._sem().busy

        return h.run_virtual(go())


def test_a_cancelled_build_stops_at_once_and_never_sends_step_1(tmp_path):
    """Blocker 2: cancelled while the rest is being adapted and step 1 is still in its (slow) lint retry: the cancel
    does not wait for step 1, and step 1 is never sent afterwards."""
    p = {**h.PROFILE_10MIN, "lint_fail": {1}, "escalate_s": (40.0, 2.45)}
    fakes = h.Fakes(p)
    took, busy = _virtual_build(fakes, tmp_path, until_cancel_s=25.0)
    assert took < 0.01 and busy == 0
    assert not [u for u in fakes.updates if not u["provisional"]]
    assert max(e["end"] for e in fakes.events if e["kind"] == "detail") < 25  # cancelled in the adapt pass
    assert not [e for e in fakes.events if e["kind"] == "adapt" and 2 in e["steps"]]  # ...which never finished


def test_a_build_that_fails_before_step_1_is_sent_fails_the_normal_way(tmp_path):
    """Should-fix 4: a later step's detail call is down at once, while step 1 is still being built: step 1 is not sent
    (no one-step "complete" lesson); the build raises as before."""
    fakes = h.Fakes(h.PROFILE_10MIN)
    real_call = fakes.call_once

    async def down(mid, system, prompt, *, effort, schema):
        if "Fill in step 6" in h._text(prompt):
            raise RuntimeError("Claude call failed (500): overloaded")
        return await real_call(mid, system, prompt, effort=effort, schema=schema)

    fakes.call_once = down
    with pytest.raises(RuntimeError):
        _virtual_build(fakes, tmp_path)
    assert not [u for u in fakes.updates if not u["provisional"]]


def test_explanations_the_full_build_puts_in_step_1_move_to_step_2():
    """Should-fix 3: step 2's call reads 15 s before its start; an explanation there belongs to step 1 in the full
    build, but step 1 went out without it (step 2's detail wasn't in yet). It goes to step 2, never dropped."""
    p = {**h.PROFILE_10MIN, "detail_extra": {2: {"explanations": [{"topic": "idea 2", "t": "2:05"},
                                                                    {"topic": "lead-in", "t": "1:35"}]}}}
    before, after = h.build_once(p, fast=False), h.build_once(p, fast=True)

    def topics(g):
        return sorted(e["topic"] for s in g["steps"] for e in s.get("explanations") or [])

    assert "lead-in" in [e["topic"] for e in before["graph"]["steps"][0]["explanations"]]
    assert topics(after["graph"]) == topics(before["graph"])  # nothing dropped
    s2 = after["graph"]["steps"][1]
    assert "lead-in" in [e["topic"] for e in s2["explanations"]]
    assert s2["video"]["start"] <= s2["explanations"][0]["t"] < s2["video"]["end"]  # its jump stays in its own clip
    keys = [(e["t"], e["topic"]) for s in after["graph"]["steps"] for e in s["explanations"]]
    assert len(keys) == len(set(keys))  # nothing twice
    assert after["graph"]["build"]["firstStep"]["same"] is False


def test_the_full_build_keeps_step_1s_notebook_choice():
    """Should-fix 5: step 1 went out as a non-notebook lesson (step 4's Jupyter mention wasn't in yet): the full build
    does not turn the lesson into a notebook lesson the session doesn't know about."""
    p = {**h.PROFILE_10MIN, "detail_extra": {4: {"code": "# run this cell in jupyter\nx = 4"}}}
    before, after = h.build_once(p, fast=False), h.build_once(p, fast=True)
    assert before["graph"]["lesson"].get("notebook")  # the old build would have made it one
    first = next(u for u in after["updates"] if not u["provisional"])["graph"]
    assert not first["lesson"].get("notebook") and not after["graph"]["lesson"].get("notebook")


def test_an_app_titled_video_decides_app_or_code_on_every_step():
    """Should-fix 5: for a video whose title names an app, step 1 waits for every step's detail before the app-or-code
    choice, and the full build keeps that choice even when a later adapt result names a code file."""
    p = {**h.PROFILE_10MIN, "title": "AutoCAD toy car for 3D printing", "work_file": "car.dwg",
         "detail_extra": {i: {"code": ""} for i in range(1, 7)},
         "adapt_extra": {5: {"precision_checks": [{"type": "file_contains", "label": "macro", "file": "macro.py",
                                                    "pattern": "def part_5"}]}}}
    after = h.build_once(p, fast=True)
    first = next(u for u in after["updates"] if not u["provisional"])
    details_done = max(e["end"] for e in after["events"] if e["kind"] == "detail")
    assert first["t"] > details_done
    assert first["graph"]["lesson"]["app"]["tool"] == "autocad"
    assert after["graph"]["lesson"].get("app") == first["graph"]["lesson"]["app"]


def test_a_failed_early_step_1_gets_the_old_batches(monkeypatch):
    """Nit: step 1's early adapt failed before the full build's round 1: round 1 is exactly the old one."""
    fakes = h.Fakes(h.PROFILE_10MIN)
    real_call = fakes.call_once

    async def flaky(mid, system, prompt, *, effort, schema):
        if '"index": 1' in h._text(prompt) and '"index": 2' not in h._text(prompt):
            raise RuntimeError("Claude call failed (500): overloaded")
        return await real_call(mid, system, prompt, effort=effort, schema=schema)

    fakes.call_once = flaky
    run = h.build_once(h.PROFILE_10MIN, fast=True, fakes=fakes)
    rounds = sorted(tuple(e["steps"]) for e in run["events"] if e["kind"] == "adapt")
    assert rounds == [(1, 2, 3), (4, 5, 6)]


def test_a_second_watch_attempt_is_ignored():
    """Nit: a second watch_transcript in the same build (an unusable step list asked again): its details never feed
    the first attempt's step 1."""
    from server.lesson import first_step
    from server.lesson.workdir import scan

    async def go():
        fs = first_step.FirstStep(url=h.URL, vid=h.VID, goal=h.GOAL, workdir="/nonexistent/_x", info=scan("/nonexistent/_x"),
                                  key="k" * 16, on_update=None)
        seg = {"title": "t", "steps": [{"start": "0:05", "end": "1:40", "title": "a", "instructions": "a"},
                                        {"start": "1:45", "end": "3:20", "title": "b", "instructions": "b"}]}
        assert fs.segment(seg) == {1}
        assert fs.segment(seg) == set() and fs.stale
        fs.detail(1, {**seg["steps"][0], "checks": []})
        assert fs.task is None and await fs.lock() is None
        fs.close()

    asyncio.run(go())


# --------------------------------------------------------------------------- review round 2
def test_an_app_titled_video_keeps_all_4_lanes_for_the_details():
    """Should-fix C: while step 1 waits for every detail (app-titled video), no lane is held back for it: step 5's
    detail starts as soon as step 1's frees a lane (lanes are process-wide: a prebuild would lose one too)."""
    p = {**h.PROFILE_10MIN, "title": "AutoCAD toy car for 3D printing", "work_file": "car.dwg",
         "detail_extra": {i: {"code": ""} for i in range(1, 7)}}
    ev = h.build_once(p, fast=True)["events"]
    d = {e["steps"][0]: e for e in ev if e["kind"] == "detail"}
    assert d[5]["start"] == min(x["end"] for x in d.values())


def test_upcoming_follows_a_second_step_list():
    """Nit: after a second watch attempt, the workspace's view of the other steps is the second step list."""
    from server.lesson import first_step
    from server.lesson.workdir import scan

    async def go():
        fs = first_step.FirstStep(url=h.URL, vid=h.VID, goal=h.GOAL, workdir="/nonexistent/_x", info=scan("/nonexistent/_x"),
                                  key="k" * 16, on_update=None)
        one = {"title": "t", "steps": [{"start": "0:05", "end": "1:40", "title": "a", "instructions": "a"},
                                       {"start": "1:45", "end": "3:20", "title": "b", "instructions": "b"}]}
        two = {"title": "t", "steps": [{"start": "0:05", "end": "1:40", "title": "a2", "instructions": "a"},
                                       {"start": "1:45", "end": "3:20", "title": "b2", "instructions": "b"},
                                       {"start": "3:25", "end": "5:00", "title": "c2", "instructions": "c"}]}
        fs.segment(one)
        fs.segment(two)
        fs.detail(2, {**two["steps"][1], "checks": [{"type": "file_exists", "file": "data.csv"}]})
        up = fs.upcoming()
        assert [u["title"] for u in up] == ["b2", "c2"] and up[0]["checks"][0]["file"] == "data.csv"
        fs.close()

    asyncio.run(go())
