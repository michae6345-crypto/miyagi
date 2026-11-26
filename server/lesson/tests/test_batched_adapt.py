"""Batched adapt (lane eng-build-speed-2): the adapt pass's first round starts batch by batch as the step details
land, each batch retries its own lint problems right away, and the full build lints the whole lesson after. The real
builder on a virtual clock with every model call faked (speed_harness.py). Offline: no key, no network, no paid call."""

from __future__ import annotations

import asyncio
import copy

import pytest

from server.lesson import batched, builder, claude
from server.lesson.tests import speed_harness as h
from server.lesson.tests.test_build_speed import _virtual_build


@pytest.fixture(scope="module")
def runs():
    out = {}
    for p in (h.PROFILE_10MIN, h.PROFILE_10MIN_S1_RETRY, h.PROFILE_RECORDED):
        out[p["name"]] = {name: h.build_once(p, **kw) for name, kw in h.MODES}
    return out


def _adapts(run, kind="adapt"):
    return sorted((e for e in run["events"] if e["kind"] == kind), key=lambda e: e["start"])


def test_the_full_lesson_arrives_sooner(runs):
    print("\n" + h.report())  # pytest -s: serial / step 1 first / batched, per profile
    ten, rec = runs[h.PROFILE_10MIN["name"]], runs[h.PROFILE_RECORDED["name"]]
    assert ten["batched"]["done_s"] <= ten["step 1 first"]["done_s"] - 4.0  # 36.0 -> 31.3
    assert rec["batched"]["done_s"] <= rec["step 1 first"]["done_s"] - 2.5  # 41.2 -> 38.2
    for r in runs.values():  # step 1 is never later
        assert h.first_step_s(r["batched"]) == h.first_step_s(r["step 1 first"])
        assert r["batched"]["done_s"] < r["step 1 first"]["done_s"]


def test_same_steps_in_every_mode(runs):
    for r in runs.values():
        ref = h.comparable(r["serial"]["graph"])
        assert h.comparable(r["step 1 first"]["graph"]) == ref and h.comparable(r["batched"]["graph"]) == ref


def test_haiku_calls_unchanged_and_a_batch_starts_when_its_details_are_in(runs):
    r = runs[h.PROFILE_10MIN["name"]]
    before, after = _adapts(r["step 1 first"]), _adapts(r["batched"])
    assert sorted(tuple(e["steps"]) for e in after) == sorted(tuple(e["steps"]) for e in before)  # same batches
    details = {e["steps"][0]: e["end"] for e in r["batched"]["events"] if e["kind"] == "detail"}
    first_rest = next(e for e in after if e["steps"] == [2, 3, 4])
    assert first_rest["start"] == max(details[k] for k in (2, 3, 4)) < max(details.values())
    # a retry only for the steps lint rejected, per batch: steps 3 and 5 sit in two batches -> 2 Sonnet calls (was 1)
    assert sorted(tuple(e["steps"]) for e in _adapts(r["batched"], "adapt_retry")) == [(3,), (5,)]


def test_kill_switch_is_todays_build(runs):
    r = runs[h.PROFILE_10MIN["name"]]["step 1 first"]
    details_done = max(e["end"] for e in r["events"] if e["kind"] == "detail")
    assert all(e["start"] >= details_done for e in _adapts(r) if e["steps"] != [1])
    assert [tuple(e["steps"]) for e in _adapts(r, "adapt_retry")] == [(3, 5)]


def test_explanations_across_a_batch_boundary_are_rehomed_as_before():
    """Step 5's call reads 15 s before its start, inside step 4 (the other batch): the explanation still ends up in
    step 4, exactly as in today's build. The adapt prompt carries no explanations, so a batch's adapt input never
    waits on its neighbour's detail; rehoming runs on the whole draft afterwards."""
    p = {**h.PROFILE_10MIN, "detail_extra": {5: {"explanations": [{"topic": "idea 5", "t": "6:55"},
                                                                    {"topic": "lead-in", "t": "6:35"}]}}}
    old, new = h.build_once(p, fast=True, batched=False), h.build_once(p, fast=True)
    assert h.comparable(new["graph"]) == h.comparable(old["graph"])
    s4 = new["graph"]["steps"][3]
    assert "lead-in" in [e["topic"] for e in s4["explanations"]]


def test_a_cancel_mid_batch_stops_everything(tmp_path):
    fakes = h.Fakes(h.PROFILE_10MIN)
    took, busy = _virtual_build(fakes, tmp_path, until_cancel_s=18.0)  # batch 2-4 running, details 5-6 too
    assert took < 0.01 and busy == 0
    assert not [e for e in fakes.events if e["kind"] == "adapt" and e["steps"] == [2, 3, 4]]  # it never finished
    assert not list((tmp_path / "lessons").glob("*.json"))  # no half lesson cached
    assert [u for u in fakes.updates if not u["provisional"]][-1]["complete"] is False  # only step 1 ever went out


def _failing(profile, when):
    fakes = h.Fakes(profile)
    real_call = fakes.call_once

    async def call(mid, system, prompt, *, effort, schema):
        if when(h._text(prompt)):
            raise RuntimeError("Claude call failed (500): overloaded")
        return await real_call(mid, system, prompt, effort=effort, schema=schema)

    fakes.call_once = call
    return fakes


def test_a_failing_batch_is_left_out_as_today():
    """Round 1 of steps 2-4 fails (escalation too): those steps keep their draft's checks, like a failed batch today."""
    def batch_2_4(t):
        return '"index": 2' in t and '"index": 4' in t and "previous answer had these problems" not in t

    old = h.build_once(h.PROFILE_10MIN, fast=True, batched=False, fakes=_failing(h.PROFILE_10MIN, batch_2_4))
    new = h.build_once(h.PROFILE_10MIN, fast=True, fakes=_failing(h.PROFILE_10MIN, batch_2_4))
    assert h.comparable(new["graph"]) == h.comparable(old["graph"]) and new["graph"]["lesson"]["complete"] is True


def test_a_failing_early_retry_is_left_to_the_full_build():
    """A batch's own retry fails: its round-1 results stand and the full build's lint retries them, as today."""
    fails = []

    def first_retry_of_3(t):
        if "previous answer had these problems" in t and '"index": 3' in t and not fails:
            fails.append(1)
            return True
        return False

    new = h.build_once(h.PROFILE_10MIN, fast=True, fakes=_failing(h.PROFILE_10MIN, first_retry_of_3))
    old = h.build_once(h.PROFILE_10MIN, fast=True, batched=False)
    assert fails and h.comparable(new["graph"]) == h.comparable(old["graph"])
    assert any(3 in e["steps"] for e in _adapts(new, "adapt_retry"))  # the full build retried it


def test_every_adapt_failing_still_fails_the_adapt_pass_as_today():
    def any_adapt(t):
        return '"index"' in t and "Fill in step" not in t

    new = h.build_once(h.PROFILE_10MIN, fast=True, fakes=_failing(h.PROFILE_10MIN, any_adapt))
    old = h.build_once(h.PROFILE_10MIN, fast=True, batched=False, fakes=_failing(h.PROFILE_10MIN, any_adapt))
    assert new["graph"]["build"]["adapted"] is False and h.comparable(new["graph"]) == h.comparable(old["graph"])


# --------------------------------------------------------------------------- unit: what a batch decides early
class _First:
    def __init__(self, state, result=None):
        self._state, self.result = state, result

    def lock_state(self):
        return self._state


def _bat(first=None, title="Todo app in Python"):
    from server.lesson.workdir import scan

    async def make():
        b = batched.BatchedAdapt(goal=h.GOAL, info=scan("/nonexistent/_x"), first=first, vid=h.VID)
        b.seg = {"title": title, "steps": []}
        b.video_info = {"title": title}
        return b

    return asyncio.run(make())


def test_early_retries_only_when_the_app_or_code_choice_is_fixed():
    assert _bat()._app_choice() is None  # no app in the titles: never an app lesson
    assert _bat(title="AutoCAD toy car")._app_choice() is ...  # undecided: round 1 only, the full build retries
    assert _bat(_First("pending"), "AutoCAD toy car")._app_choice() is ...
    pinned = {"tool": "autocad", "label": "AutoCAD"}
    assert _bat(_First("locked", {"app": pinned}), "AutoCAD toy car")._app_choice() == pinned


def test_a_repeat_of_an_unknown_previous_step_is_left_to_the_full_build():
    b = _bat()
    steps = [{"index": i, "start": 10.0 * i, "end": 10.0 * i + 9, "title": f"Step {i}", "instructions": "x",
              "checks": [{"type": "screen_contains", "app": "Code", "pattern": "same"}], "hints": ["h"]} for i in (1, 2, 3)]
    draft = {"title": "t", "libraries": [], "steps": steps}
    same = {"checks": [{"type": "screen_contains", "label": "same typed", "app": "Code", "pattern": "same"}], "targets": []}
    out = {2: {"index": 2, **copy.deepcopy(same)}, 3: {"index": 3, **copy.deepcopy(same)}}
    probs = b._problems(draft, [2, 3], out, None, set())
    assert 3 in probs and any("repeat the previous step" in p for p in probs[3])  # 2 is in the batch: known
    assert not any("repeat the previous step" in p for p in probs.get(2, []))  # 1 is not known yet: left out
    b.adapted[1] = {"index": 1, **copy.deepcopy(same)}
    assert any("repeat the previous step" in p for p in b._problems(draft, [2, 3], out, None, set()).get(2, []))


def test_off_switches():
    assert batched.enabled()
    import os

    os.environ["LESSON_BATCHED_ADAPT"] = "0"
    try:
        assert not batched.enabled()
    finally:
        del os.environ["LESSON_BATCHED_ADAPT"]
    assert builder.ADAPT_BATCH == 3 and claude.CONCURRENCY == 4


# --------------------------------------------------------------------------- review round 1
def test_early_calls_are_quiet(tmp_path):
    """Should-fix 1: the early round-1 and retry calls run while the details are still being written: no "adapting"
    stage before the full build's own adapt pass, the video's model is still the detail calls' model, and build.model
    names the model of the last adapt round, as in today's build."""
    stages = []
    p = {**h.PROFILE_10MIN, "detail_s": [3.6, 5.8, 6.0, 7.7, 6.3, 20.0]}  # step 6's detail is slow: retries run first
    fakes = h.Fakes(p)
    g = _virtual_build(fakes, tmp_path, on_progress=lambda s, m: stages.append((s, round(h.now(), 2))))
    details_done = max(e["end"] for e in fakes.events if e["kind"] == "detail")
    step1_sent = next(t for s, t in stages if s == "first_steps")
    # step 1's own adapt pass says "adapting" (it is the step the learner gets next); the batches never do
    assert not [t for s, t in stages if s == "adapting" and step1_sent < t < details_done]
    assert min(e["start"] for e in fakes.events if e["kind"] == "adapt_retry") < details_done  # (they ran early)
    old = h.build_once(p, fast=True, batched=False)["graph"]
    assert g["build"]["model"] == old["build"]["model"]  # video: the detail model; adapt: the retry model


def test_an_unexpected_error_in_the_early_lint_keeps_round_1(monkeypatch):
    """Should-fix 2: anything but a cancel going wrong after round 1 (here a KeyError in the early lint) leaves the
    batch's round-1 result for the full build, which lints and retries it: the adapt pass never fails because of it."""
    def boom(self, *a, **k):
        raise KeyError("probe")

    monkeypatch.setattr(batched.BatchedAdapt, "_problems", boom)
    new = h.build_once(h.PROFILE_10MIN, fast=True)
    old = h.build_once(h.PROFILE_10MIN, fast=True, batched=False)
    assert new["graph"]["build"]["adapted"] is True and h.comparable(new["graph"]) == h.comparable(old["graph"])


@pytest.mark.parametrize("profile", [
    {**h.PROFILE_10MIN, "lint_fail": {3}, "lint_fail_always": {3}},
    {**h.PROFILE_RECORDED, "lint_fail": set(range(1, 8)), "lint_fail_always": set(range(1, 8))},
], ids=["step 3 never fixed", "no step ever fixed"])
def test_the_retry_cap_is_todays(profile):
    """Should-fix 3: an early retry is the first retry round: a step lint keeps rejecting gets no more Sonnet calls
    than today (a second retry only after the first one helped, and one more round at most)."""
    old = h.calls(h.build_once(profile, fast=True, batched=False)).get("adapt_retry", 0)
    new = h.calls(h.build_once(profile, fast=True)).get("adapt_retry", 0)
    assert new <= old


def test_an_early_batch_the_full_build_sends_differently_is_dropped():
    """Nit: an early call whose steps changed before the full build took them is cancelled at once, not at close()."""
    b = _bat()

    async def go():
        b.plan = [[2, 3]]
        steps = [{"index": 2, "title": "a"}, {"index": 3, "title": "b"}]
        stale = asyncio.ensure_future(asyncio.sleep(60))
        k = batched.key(b.goal, [{"index": 2, "title": "OLD"}, steps[1]], b.summary)
        b.started[k], b.groups[k] = stale, [2, 3]
        assert [[st["index"] for st in grp] for grp in b.layout(steps)] == [[2, 3]]  # sent fresh
        await asyncio.sleep(0)
        assert stale.cancelled()

    asyncio.run(go())


def test_link_checks_are_shared_with_step_1_and_unpinned_starts_are_not_a_problem():
    from server.lesson.workdir import scan

    async def make():
        first = _First("pending")
        first.checked = {"https://example.com": True}
        return first, batched.BatchedAdapt(goal=h.GOAL, info=scan("/nonexistent/_x"), first=first, vid=h.VID)

    first, b = asyncio.run(make())
    assert b.checked is first.checked
    b.seg = {"title": "Todo app in Python", "steps": []}
    steps = [{"index": 1, "start": 50.0, "end": 50.0, "title": "Step 1", "instructions": "x", "hints": ["h"],
              "checks": [{"type": "screen_contains", "app": "Code", "pattern": "one"}]}]
    out = {1: {"index": 1, "checks": [{"type": "screen_contains", "label": "one typed", "app": "Code", "pattern": "one"}]}}
    assert not any("video.start" in p for ps in b._problems({"title": "t", "libraries": [], "steps": steps}, [1], out, None,
                                                            set()).values() for p in ps)
