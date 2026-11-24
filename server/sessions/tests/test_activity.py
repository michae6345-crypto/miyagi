"""Activity + bon: the store (server/sessions/activity.py). Pure: a tmp state dir, fixed clocks, no network. Every
payload is checked against the ui-v4 contract (shared/contracts/events.py Activity / BonState)."""

from __future__ import annotations

import json
import time

import pytest

from server.sessions import activity as act
from server.sessions import store
from shared.contracts.events import validate_engine_payload

NOON = time.mktime((2026, 11, 24, 12, 0, 0, 0, 0, -1))  # local noon: day_of() is the learner's own calendar day
DAY = 86400.0


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))


def _row(step="s1", lesson="lesson-a"):
    return {"stepId": step, "lessonId": lesson, "stepTitle": f"Step {step}", "lessonTitle": "Lesson A",
            "skillIds": ["py.loops"], "skills": ["Loops"]}


# ------------------------------------------------------------------------------------------------ bon
@pytest.mark.parametrize("steps,level,name", [(0, 1, "Seed"), (2, 1, "Seed"), (3, 2, "Sprout"), (8, 3, "Shoot"),
                                              (15, 4, "Sapling"), (25, 5, "Budding"), (40, 6, "In bloom"),
                                              (59, 6, "In bloom"), (60, 7, "Young tree"), (90, 8, "Bonsai"),
                                              (500, 8, "Bonsai")])
def test_bon_levels_match_the_apps_growth_ts(steps, level, name):
    b = act.bon(steps)
    assert (b["level"], b["name"], b["steps"]) == (level, name, steps)
    validate_engine_payload("bon", b)


def test_bon_next_and_fraction():
    assert act.bon(5) == {"steps": 5, "level": 2, "name": "Sprout",
                          "next": {"level": 3, "name": "Shoot", "at": 8, "left": 3}, "fraction": 0.4}
    top = act.bon(90)
    assert "next" not in top and top["fraction"] == 1.0
    assert act.bon(-4)["steps"] == 0
    grew = act.bon(8, grew=True, last_key="l:s8")
    assert grew["grew"] is True and grew["lastKey"] == "l:s8"
    validate_engine_payload("bon", grew)


# ------------------------------------------------------------------------------------------------ the counter
def test_a_step_counts_once_ever():
    a = act.Activity()
    assert a.pass_step("lesson-a:s1", _row(), NOON)[0] is True
    assert a.pass_step("lesson-a:s1", _row(), NOON + 5)[0] is False  # the same step again: no new count
    assert a.pass_step("lesson-b:s1", _row(lesson="lesson-b"), NOON + 9)[0] is True  # s1 of another lesson is new
    assert a.count == 2
    assert a.pass_step("", _row(), NOON) == (False, [])


def test_recent_keeps_the_last_20_newest_first_with_skill_tags():
    a = act.Activity()
    for i in range(25):
        a.pass_step(f"l:s{i}", _row(step=f"s{i}"), NOON + i)
    snap = a.snapshot(NOON + 30)
    validate_engine_payload("activity", snap)
    assert len(snap["recent"]) == 20
    assert snap["recent"][0]["stepId"] == "s24" and snap["recent"][-1]["stepId"] == "s5"
    r0 = snap["recent"][0]
    assert r0["skillIds"] == ["py.loops"] and r0["skills"] == ["Loops"] and r0["key"] == "l:s24"
    assert r0["stepTitle"] == "Step s24" and r0["lessonTitle"] == "Lesson A" and r0["lessonId"] == "lesson-a"
    assert not r0["at"].endswith("Z") and r0["at"][-6] in "+-"  # the learner's UTC offset


def test_only_counted_passes_are_recent():
    a = act.Activity()
    a.pass_step("l:s1", _row(), NOON)
    a.pass_step("l:s1", _row(), NOON + 1)
    a.pass_step("l:s2", _row("s2"), NOON + 2)
    a.pass_step("l:s1", _row(), NOON + 3)  # replayed later (a review): not counted, not listed again
    assert [r["stepId"] for r in a.recent] == ["s1", "s2"] and a.count == 2


def test_bon_import_keeps_the_larger_count_and_the_seen_keys():
    a = act.Activity()
    a.pass_step("l:s1", _row(), NOON)
    assert a.import_count(24, ["l:s1", "l:s2", 5, "", "x" * 300]) is True
    assert a.count == 24 and a.has("l:s2") and not a.has("x" * 300)
    assert a.pass_step("l:s2", _row("s2"), NOON)[0] is False  # the app counted it already
    assert a.import_count(3, []) is False and a.count == 24  # never lowers the count
    assert a.import_count("many", None) is False
    b = act.Activity()
    b.import_count(0, [f"k:{i}" for i in range(1000)])
    assert b.count == act.IMPORT_SEEN_MAX


def test_milestones_first_step_levels_and_step_marks():
    a = act.Activity()
    got = []
    for i in range(10):
        got += a.pass_step(f"l:s{i}", _row(step=f"s{i}"), NOON + i)[1]
    ids = [m["id"] for m in got]
    assert ids == ["first_step", "level:2", "level:3", "steps:10"]
    lv = next(m for m in got if m["id"] == "level:2")
    assert lv["label"] == "bon grew to Sprout" and lv["date"] == "2026-11-24" and lv["value"] == 2
    snap = a.snapshot(NOON + 60)
    validate_engine_payload("activity", snap)
    # the wire carries only the contract's MilestoneKind values (level marks stay on disk), newest first
    assert [m["id"] for m in snap["milestones"]] == ["steps:10", "first_step"]
    m0 = snap["milestones"][0]
    assert m0 == {"id": "steps:10", "kind": "steps", "title": "10 steps passed", "at": m0["at"], "count": 10}


def test_finished_lessons_count_once():
    a = act.Activity()
    got = a.finish_lesson("lesson-a", "Lesson A", NOON)
    assert [m["id"] for m in got] == ["lesson:lesson-a", "first_lesson"]
    assert a.finish_lesson("lesson-a", "Lesson A", NOON + 5) == []
    assert a.finish_lesson("", None, NOON) == []
    snap = a.snapshot(NOON)
    assert snap["totals"]["lessonsFinished"] == 1 and [m["kind"] for m in snap["milestones"]] == ["first_lesson"]


# ------------------------------------------------------------------------------------------------ minutes
def test_minutes_and_steps_per_day_week_and_totals():
    a = act.Activity()
    a.add_seconds(59, NOON)
    assert a.snapshot(NOON)["days"][-1]["minutes"] == 0 and a.active_days == 0
    a.add_seconds(2, NOON)
    assert a.snapshot(NOON)["days"][-1]["minutes"] == 1 and a.active_days == 1
    a.add_seconds(600, NOON + DAY)
    a.pass_step("l:s1", _row(), NOON + DAY)
    snap = a.snapshot(NOON + DAY)
    validate_engine_payload("activity", snap)
    assert snap["minutesTracked"] is True and snap["totals"]["minutes"] == 11 and a.active_days == 2
    assert snap["totals"]["stepsPassed"] == 1
    assert snap["week"] == {"minutes": 11, "stepsPassed": 1, "skillsMastered": 0}
    assert len(snap["days"]) == act.DAYS_SHOWN == 84
    assert snap["days"][-1] == {"date": "2026-11-25", "minutes": 10, "steps": 1}
    assert snap["days"][-2] == {"date": "2026-11-24", "minutes": 1, "steps": 0}
    assert snap["days"][0]["minutes"] == 0 and snap["asOf"].startswith("2026-11-25T12:00:00")


def test_bad_durations_never_count():
    a = act.Activity()
    for dt in (0, -5, 3600, 1e9, float("nan"), True, "5"):
        a.add_seconds(dt, NOON)  # type: ignore[arg-type]
    assert a.total_s == 0 and a.days == {}


def test_hour_milestones():
    a = act.Activity()
    got = a.add_seconds(3599, NOON) + a.add_seconds(2, NOON)
    assert [m["id"] for m in got] == ["hours:1"] and got[0]["label"] == "1 hour of lessons"


def test_old_days_are_pruned_but_totals_stay():
    a = act.Activity()
    for i in range(act.DAYS_KEPT + 10):
        a.add_seconds(120, NOON + i * DAY)
        a.pass_step(f"l:s{i}", _row(), NOON + i * DAY)
    assert len(a.days) == act.DAYS_KEPT and len(a.day_steps) == act.DAYS_KEPT
    assert a.snapshot(NOON)["totals"]["minutes"] == 2 * (act.DAYS_KEPT + 10)
    assert a.active_days == act.DAYS_KEPT + 10 and a.count == act.DAYS_KEPT + 10


# ------------------------------------------------------------------------------------------------ time zones
def test_snapshot_under_a_non_utc_zone(monkeypatch):
    """Days, asOf and recent times follow the learner's zone: 23:30 in Los Angeles is still the 24th there."""
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        late = time.mktime((2026, 11, 24, 23, 30, 0, 0, 0, -1))  # 07:30 UTC on the 25th
        a = act.Activity()
        a.pass_step("l:s1", _row(), late)
        a.add_seconds(120, late)
        snap = a.snapshot(late)
        validate_engine_payload("activity", snap)
        assert snap["days"][-1] == {"date": "2026-11-24", "minutes": 2, "steps": 1}
        assert snap["asOf"] == "2026-11-24T23:30:00-08:00" and snap["tz"] == "America/Los_Angeles"
        assert snap["recent"][0]["at"] == "2026-11-24T23:30:00-08:00"
        assert a.recent[0]["at"] == "2026-11-25T07:30:00Z"  # stored in UTC
    finally:
        monkeypatch.undo()  # TZ back as it was, then the C library rereads it
        time.tzset()


def test_local_iso_reads_stored_times():
    assert act.local_iso("not a time") is None and act.local_iso(None) is None and act.local_iso(True) is None
    assert act.local_iso(NOON).startswith("2026-11-24T12:00:00")


# ------------------------------------------------------------------------------------------------ disk
def test_round_trip_through_activity_json():
    a = act.Activity()
    a.add_seconds(300, NOON)
    a.pass_step("l:s1", _row(), NOON)
    a.finish_lesson("l", "L", NOON)
    a.save()
    path = store.state_dir() / act.FILE
    assert json.loads(path.read_text())["count"] == 1
    b = act.Activity.load()
    assert b.snapshot(NOON) == a.snapshot(NOON)
    assert b.pass_step("l:s1", _row(), NOON)[0] is False  # the dedupe set survives a restart
    assert b.finish_lesson("l", "L", NOON) == []  # and so do the milestones
    act.Activity.erase()
    assert not path.exists() and act.Activity.load().count == 0
    act.Activity.erase()  # erasing twice is fine


@pytest.mark.parametrize("junk", ["not json", "[]", '{"days": 5, "keys": "x", "count": "many", "recent": 3}',
                                  '{"days": {"bad": 5, "2026-11-24": -1, "2026-11-23": 90}}',
                                  '{"recent": [{"key": 5}, {"key": "l:s1", "at": "never"}], "daySteps": [1]}'])
def test_a_broken_file_reads_as_empty_or_what_is_valid(junk):
    path = store.state_dir() / act.FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(junk)
    a = act.Activity.load()
    assert a.count == 0
    assert set(a.days) <= {"2026-11-23"}
    snap = a.snapshot(NOON)  # never raises
    assert snap["recent"] == []
    validate_engine_payload("activity", snap)


def test_count_is_never_below_the_keys_kept():
    a = act.Activity({"count": 1, "keys": ["a:s1", "a:s2", "a:s3"]})
    assert a.count == 3 and a.has("a:s2")


# ------------------------------------------------------------------------------------------------ test isolation
def test_no_state_dir_under_pytest_never_touches_the_disk(monkeypatch, tmp_path):
    """A test that builds main.Engine() outside orchestrator/tests has no MIYAGI_STATE_DIR: the learner's real
    ~/miyagi/state/activity.json is never read or written."""
    monkeypatch.delenv("MIYAGI_STATE_DIR")
    monkeypatch.setattr(store, "state_dir", lambda: tmp_path)  # where it would have gone
    (tmp_path / act.FILE).write_text(json.dumps({"count": 7}))
    assert act.disk_ok() is False
    assert act.Activity.load().count == 0
    act.Activity({"count": 3}).save()
    act.Activity.erase()
    assert json.loads((tmp_path / act.FILE).read_text()) == {"count": 7}
