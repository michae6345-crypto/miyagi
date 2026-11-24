"""Activity + bon: the store (server/sessions/activity.py). Pure: a tmp state dir, fixed clocks, no network."""

from __future__ import annotations

import json
import time

import pytest

from server.sessions import activity as act
from server.sessions import store

NOON = time.mktime((2026, 11, 24, 12, 0, 0, 0, 0, -1))  # local noon: day_of() is the learner's own calendar day
DAY = 86400.0


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))


def _row(step="s1", lesson="lesson-a"):
    return {"stepId": step, "lessonId": lesson, "title": f"Step {step}", "lessonTitle": "Lesson A",
            "skills": [{"id": "loops", "label": "Loops"}]}


# ------------------------------------------------------------------------------------------------ bon
@pytest.mark.parametrize("steps,level,name", [(0, 1, "Seed"), (2, 1, "Seed"), (3, 2, "Sprout"), (8, 3, "Shoot"),
                                              (15, 4, "Sapling"), (25, 5, "Budding"), (40, 6, "In bloom"),
                                              (59, 6, "In bloom"), (60, 7, "Young tree"), (90, 8, "Bonsai"),
                                              (500, 8, "Bonsai")])
def test_bon_levels_match_the_apps_growth_ts(steps, level, name):
    b = act.bon(steps)
    assert (b["level"], b["name"], b["steps"]) == (level, name, steps)


def test_bon_next_and_fraction():
    assert act.bon(5) == {"steps": 5, "level": 2, "name": "Sprout",
                          "next": {"level": 3, "name": "Shoot", "at": 8, "left": 3}, "fraction": 0.4}
    top = act.bon(90)
    assert "next" not in top and top["fraction"] == 1.0
    assert act.bon(-4)["steps"] == 0


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
    assert len(snap["recent"]) == 20
    assert snap["recent"][0]["stepId"] == "s24" and snap["recent"][-1]["stepId"] == "s5"
    assert snap["recent"][0]["skills"] == [{"id": "loops", "label": "Loops"}]
    assert "key" not in snap["recent"][0] and snap["recent"][0]["at"].endswith("Z")


def test_a_repeat_pass_is_listed_again_but_not_twice_in_a_row():
    a = act.Activity()
    a.pass_step("l:s1", _row(), NOON)
    a.pass_step("l:s1", _row(), NOON + 1)
    assert len(a.recent) == 1
    a.pass_step("l:s2", _row("s2"), NOON + 2)
    a.pass_step("l:s1", _row(), NOON + 3)  # replayed later (a review): it is a pass the learner made
    assert [r["stepId"] for r in a.recent] == ["s1", "s2", "s1"] and a.count == 2


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
    assert [m["id"] for m in snap["milestones"]] == ["steps:10", "level:3", "level:2", "first_step"]  # newest first


def test_finished_lessons_count_once():
    a = act.Activity()
    got = a.finish_lesson("lesson-a", "Lesson A", NOON)
    assert [m["id"] for m in got] == ["lesson:lesson-a", "first_lesson"]
    assert a.finish_lesson("lesson-a", "Lesson A", NOON + 5) == []
    assert a.finish_lesson("", None, NOON) == []
    assert a.snapshot(NOON)["totals"]["lessonsCompleted"] == 1


# ------------------------------------------------------------------------------------------------ minutes
def test_minutes_per_day_totals_and_active_days():
    a = act.Activity()
    a.add_seconds(59, NOON)
    assert a.snapshot(NOON)["today"] == 0 and a.active_days == 0
    a.add_seconds(2, NOON)
    assert a.snapshot(NOON)["today"] == 1 and a.active_days == 1
    a.add_seconds(600, NOON + DAY)
    snap = a.snapshot(NOON + DAY)
    assert snap["today"] == 10 and snap["totals"]["minutes"] == 11 and snap["totals"]["activeDays"] == 2
    assert len(snap["days"]) == act.DAYS_SHOWN
    assert snap["days"][-1] == {"date": "2026-11-25", "minutes": 10}
    assert snap["days"][-2] == {"date": "2026-11-24", "minutes": 1}
    assert snap["days"][0]["minutes"] == 0


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
    assert len(a.days) == act.DAYS_KEPT
    assert a.snapshot(NOON)["totals"]["minutes"] == 2 * (act.DAYS_KEPT + 10)
    assert a.active_days == act.DAYS_KEPT + 10


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
                                  '{"days": {"bad": 5, "2026-11-24": -1, "2026-11-23": 90}}'])
def test_a_broken_file_reads_as_empty_or_what_is_valid(junk):
    path = store.state_dir() / act.FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(junk)
    a = act.Activity.load()
    assert a.count == 0 and a.recent == []
    assert set(a.days) <= {"2026-11-23"}
    a.snapshot(NOON)  # never raises


def test_count_is_never_below_the_keys_kept():
    a = act.Activity({"count": 1, "keys": ["a:s1", "a:s2", "a:s3"]})
    assert a.count == 3 and a.has("a:s2")
