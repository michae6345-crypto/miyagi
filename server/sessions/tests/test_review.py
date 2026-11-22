"""Spaced review scheduler. Offline and deterministic: an injected clock and a fixed time zone, no model, no network.
Run from the repo root:  python -m pytest server/sessions/tests/test_review.py -q"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from server.orchestrator import stubs
from server.orchestrator.main import contract_progress
from server.sessions import progress, review, store
from server.sessions.tests.test_sessions import Engine, run

UTC = timezone.utc
DAY = 86400.0
T0 = datetime(2026, 11, 2, 15, 30, tzinfo=UTC).timestamp()  # a Monday, mid-afternoon


def at(days: float, hour: int = 9) -> float:
    """Epoch seconds `days` after T0's day at `hour`:00 UTC."""
    d = datetime(2026, 11, 2, hour, 0, tzinfo=UTC) + timedelta(days=days)
    return d.timestamp()


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(d))
    work = tmp_path / "default-workdir"  # the fixture lesson's own workdir is the hero's demo/pinn-lab: a lesson-mode
    work.mkdir(exist_ok=True)  # session creates each step's file there (pinn_convection.py): the hero cache would miss
    monkeypatch.setenv("TUT_WORKDIR", str(work))
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY", "TIGER_DATABASE_URL"):
        monkeypatch.setenv(k, "")
    return d


def smap(track, *nodes):
    return {"track": track, "headline": "", "nodes": [{"id": i, "label": label, "state": st} for i, label, st in nodes],
            "edges": [], "cross": [], "next": []}


def entry(lesson_id, finished_at, track, *nodes):
    return {"lessonId": lesson_id, "title": lesson_id, "covered": [], "finishedAt": finished_at, "skillMap": smap(track, *nodes)}


HISTORY = [
    entry("l1", at(0), "Python", ("fn", "Functions", "mastered"), ("loop", "Loops", "learning"), ("cls", "Classes", "next")),
]


def sched(history, st, now, tz=UTC):
    return review.items(history, st, now, tz)


def only(rows, label):
    return next(r for r in rows if r["label"] == label)


# ---------------------------------------------------------------------------------------------- the intervals
def test_intervals_are_one_three_seven_fourteen_thirty():
    assert review.INTERVALS == (1, 3, 7, 14, 30)


def test_a_new_mastered_skill_is_due_one_day_after_the_lesson_finished():
    rows = sched(HISTORY, {}, at(0, 18))
    assert [r["label"] for r in rows] == ["Functions"]  # learning / next skills are never scheduled
    r = rows[0]
    assert r["dueAt"] == at(1, 0) and r["interval"] == 1 and r["checks"] == 1
    assert r["when"] == "Tomorrow" and "lastResult" not in r
    assert review.public(rows, at(0, 18))["due"] == 0


def test_due_from_the_start_of_its_day_not_the_hour_it_finished():
    assert review.public(sched(HISTORY, {}, at(1, 0) - 1), at(1, 0) - 1)["due"] == 0
    now = at(1, 0)
    out = review.public(sched(HISTORY, {}, now), now)
    assert out["due"] == 1 and out["items"][0]["when"] == "Today"


def test_a_pass_walks_up_the_boxes_and_the_last_box_repeats():
    k = review.skill_key("Python", "Functions")
    t = at(1, 10)
    waits = []
    for _ in range(7):
        st = {k: review.record_result(k, True, now=t)}
        row = only(sched(HISTORY, st, t), "Functions")
        waits.append(row["interval"])
        assert row["lastResult"] == "passed" and row["lastAt"] == t
        assert row["dueAt"] == datetime.combine((datetime.fromtimestamp(t, UTC) + timedelta(days=row["interval"])).date(),
                                                datetime.min.time(), tzinfo=UTC).timestamp()
        t = row["dueAt"] + 3600
    assert waits == [3, 7, 14, 30, 30, 30, 30]  # box 0's own 1 day was the first wait, before any review
    assert review.load_state()[k]["reps"] == 7


def test_a_failed_check_resets_to_one_day():
    k = review.skill_key("Python", "Functions")
    for t in (at(1), at(4), at(11)):
        review.record_result(k, True, now=t)
    assert only(sched(HISTORY, review.load_state(), at(11)), "Functions")["interval"] == 14
    review.record_result(k, False, now=at(20, 14))
    row = only(sched(HISTORY, review.load_state(), at(20, 15)), "Functions")
    assert row["interval"] == 1 and row["lastResult"] == "missed"
    assert row["dueAt"] == at(21, 0) and row["when"] == "Tomorrow"
    assert review.load_state()[k]["reps"] == 3  # a miss earns no rep


def test_due_first_oldest_first_then_upcoming_by_date():
    h = [entry("a", at(0), "Python", ("fn", "Functions", "mastered")),
         entry("b", at(-5), "Shell", ("cd", "Navigation", "mastered")),
         entry("c", at(2), "Git", ("co", "Commits", "mastered"))]
    now = at(3, 12)
    rows = sched(h, {}, now)
    assert [r["label"] for r in rows] == ["Navigation", "Functions", "Commits"]
    assert [r["when"] for r in rows] == ["Today", "Today", "Today"]
    assert review.public(rows, now)["due"] == 3
    rows = sched(h, {}, at(2, 12))
    assert [r["label"] for r in rows] == ["Navigation", "Functions", "Commits"]
    assert review.public(rows, at(2, 12))["due"] == 2  # Commits is due tomorrow (the lesson finished today)


def test_a_skill_mastered_in_two_lessons_is_one_review_from_the_first_time():
    h = [entry("a", at(0), "Python", ("fn", "Functions", "mastered")),
         entry("b", at(5), "python", ("fn2", "functions", "mastered"))]
    rows = sched(h, {}, at(6))
    assert len(rows) == 1 and rows[0]["dueAt"] == at(1, 0)
    assert review.mastered_skills(h)[review.skill_key("Python", "Functions")]["lessonId"] == "b"  # replay the newest


def test_nothing_mastered_or_no_finish_time_means_no_schedule():
    assert sched([], {}, T0) == []
    assert sched([entry("a", None, "Python", ("fn", "Functions", "mastered"))], {}, T0) == []
    assert sched([entry("a", at(0), "Python", ("fn", "Functions", "learning"))], {}, T0) == []
    assert review.payload(now=T0, tz=UTC) is None
    assert sched([{"lessonId": "x", "finishedAt": at(0)}, "junk", None], {}, T0) == []


def test_when_words_use_the_learners_calendar_days():
    now = datetime(2026, 11, 2, 23, 50, tzinfo=UTC).timestamp()  # Monday late night
    assert review.when_word(now - 3 * DAY, now, UTC) == "Today"  # overdue reads as today
    assert review.when_word(now + 600, now, UTC) == "Tomorrow"  # 00:00 Tuesday is ten minutes away: the next day
    assert review.when_word(at(3, 0), now, UTC) == "Thursday"
    assert review.when_word(at(6, 0), now, UTC) == "Sunday"
    assert review.when_word(at(7, 0), now, UTC) == "Nov 9"
    assert review.when_word(at(45, 0), now, UTC) == "Dec 17"
    west = timezone(timedelta(hours=-8))  # the same instants are a different calendar day in Los Angeles
    assert review.when_word(now + 600, now, west) == "Today"


def test_due_follows_the_time_zone():
    west = timezone(timedelta(hours=-8))
    finished = datetime(2026, 11, 2, 3, 0, tzinfo=UTC).timestamp()  # Sunday Nov 1, 19:00 in Los Angeles
    h = [entry("a", finished, "Python", ("fn", "Functions", "mastered"))]
    assert sched(h, {}, finished, west)[0]["dueAt"] == datetime(2026, 11, 2, 0, 0, tzinfo=west).timestamp()
    assert sched(h, {}, finished, UTC)[0]["dueAt"] == datetime(2026, 11, 3, 0, 0, tzinfo=UTC).timestamp()


def test_a_dst_change_does_not_move_a_calendar_day():
    from zoneinfo import ZoneInfo

    ny = ZoneInfo("America/New_York")
    finished = datetime(2026, 11, 1, 12, 0, tzinfo=ny).timestamp()  # clocks go back at 2:00 that morning
    h = [entry("a", finished, "Python", ("fn", "Functions", "mastered"))]
    k = review.skill_key("Python", "Functions")
    st = {k: {"box": 1, "lastResult": "passed", "lastAt": finished, "reps": 1}}
    assert sched(h, st, finished, ny)[0]["dueAt"] == datetime(2026, 11, 4, 0, 0, tzinfo=ny).timestamp()


# ---------------------------------------------------------------------------------------------- disk
def test_review_state_roundtrips_and_bad_files_read_as_empty(state):
    k = review.skill_key("Python", "Functions")
    review.record_result(k, True, now=at(1))
    on_disk = json.loads((state / "review.json").read_text())
    assert on_disk["skills"][k]["box"] == 1
    (state / "review.json").write_text("not json")
    assert review.load_state() == {}
    (state / "review.json").write_text(json.dumps({"skills": {"a::b": {"box": 99}, "c::d": "x", "e::f": {"box": 2, "lastAt": at(1)}}}))
    assert list(review.load_state()) == ["e::f"]
    (state / "review.json").write_text(json.dumps([1, 2]))
    assert review.load_state() == {}


def test_payload_reads_history_and_review_json_from_the_state_folder(state):
    store._write_atomic(state / "history.json", HISTORY)
    out = review.payload(now=at(1, 8), tz=UTC)
    assert out["due"] == 1 and out["items"][0]["label"] == "Functions"
    review.record_result(review.skill_key("Python", "Functions"), True, now=at(1, 8))
    out = review.payload(now=at(1, 9), tz=UTC)
    assert out["due"] == 0 and out["items"][0]["interval"] == 3 and out["items"][0]["lastResult"] == "passed"
    assert out["items"][0]["when"] == "Friday"


def test_record_result_safely_never_raises(monkeypatch):
    monkeypatch.setattr(review.store, "_write_atomic", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    review.record_result_safely(review.skill_key("a", "b"), True)  # logged, not raised
    review.record_result_safely(None, True)


# ---------------------------------------------------------------------------------------------- the progress message
def test_progress_carries_the_review_additively(state, monkeypatch):
    store._write_atomic(state / "history.json", HISTORY)
    monkeypatch.setattr(review.time, "time", lambda: at(2, 8))
    p = progress.progress()
    assert p["review"]["due"] == 1 and p["review"]["items"][0]["label"] == "Functions"
    assert {"skills", "completed", "inProgress"} <= set(p)  # nothing that was there is gone
    wire = contract_progress(p)
    assert wire["review"] == p["review"] and "skills" in wire and "completed" in wire


def test_progress_without_a_mastered_skill_has_no_review_key(state):
    store._write_atomic(state / "history.json", [entry("a", at(0), "Python", ("fn", "Functions", "learning"))])
    assert "review" not in progress.progress()
    assert "review" not in contract_progress({"skills": [], "completed": []})


def test_the_item_shape_matches_what_the_app_reads(state):
    """dashboard/types.ts readReview + progress/types.ts readReview: label, skillId, track, dueAt (epoch s or ms), interval,
    lastResult, lastAt, when, checks."""
    store._write_atomic(state / "history.json", HISTORY)
    item = review.payload(now=at(1, 8), tz=UTC)["items"][0]
    assert set(item) == {"skillId", "label", "track", "dueAt", "when", "interval", "checks"}
    assert isinstance(item["dueAt"], float) and item["dueAt"] < 1e11  # epoch seconds: toMs() multiplies
    assert not any(str(v).startswith("/") for v in item.values())  # no filesystem paths


# ---------------------------------------------------------------------------------------------- Start review
def test_steps_behind_a_skill_and_the_review_graph():
    g = stubs.load_fixture_lesson()
    assert review.steps_behind(g, "Build the MLP") == ["s2"]
    assert review.steps_behind(g, "build the mlp") == ["s2"]
    assert review.steps_behind(g, "No such skill") == []
    k = review.skill_key("PyTorch", "Build the MLP")
    rg = review.review_graph(g, "Build the MLP", k, skill_id="build-the-mlp")
    assert [s["id"] for s in rg["steps"]] == ["s2"]
    assert rg["lesson"]["id"] != g["lesson"]["id"] and rg["lesson"]["id"].startswith("review-")
    assert rg["lesson"]["title"] == "Review: Build the MLP"
    assert review.review_of(rg) == {"key": k, "label": "Build the MLP", "skillId": "build-the-mlp"}
    assert len(g["steps"]) == 6 and "review" not in g["lesson"]  # the finished lesson is untouched
    assert review.review_of(g) is None
    assert review.review_graph(g, "No such skill", k) is None


def test_find_picks_by_id_label_or_the_first_due(state):
    store._write_atomic(state / "history.json", HISTORY + [entry("l2", at(3), "Git", ("co", "Commits", "mastered"))])
    now = at(2, 8)
    assert review.find({"skillId": "fn"}, now, UTC)["label"] == "Functions"
    assert review.find({"label": "commits"}, now, UTC)["label"] == "Commits"
    assert review.find({}, now, UTC)["label"] == "Functions"  # no selector: the first one due
    assert review.find({"label": "Nope"}, now, UTC) is None
    assert review.find({}, at(0, 8), UTC) is None  # nothing is due yet


# ---------------------------------------------------------------------------------------------- the lesson hook
def _review_engine(state):
    g = stubs.load_fixture_lesson()
    ids = [s["id"] for s in g["steps"]]
    done = entry(g["lesson"]["id"], at(0), "PyTorch", *[(f"n{i}", s["title"], "mastered") for i, s in enumerate(g["steps"])])
    store._write_atomic(state / "history.json", [done])
    k = review.skill_key("PyTorch", g["steps"][0]["title"])
    rg = review.review_graph(g, g["steps"][0]["title"], k)
    assert [s["id"] for s in rg["steps"]] == [ids[0]]
    return rg, k, done


def test_passing_a_review_step_records_the_pass_and_adds_no_finished_lesson(state):
    rg, k, done = _review_engine(state)
    e = Engine()

    async def go():
        await e.s.load_graph(rg)
        await e.settle()
        await e.s._pass_step()
        await e.settle()

    run(go())
    assert review.load_state()[k]["box"] == 1 and review.load_state()[k]["lastResult"] == "passed"
    assert [c["lessonId"] for c in store.completed()] == [done["lessonId"]]  # no "Review: ..." in Finished lessons


def test_a_skipped_review_step_resets_the_skill(state):
    rg, k, _ = _review_engine(state)
    review.record_result(k, True, now=at(1))
    review.record_result(k, True, now=at(4))
    assert review.load_state()[k]["box"] == 2
    e = Engine()

    async def go():
        await e.s.load_graph(rg)
        await e.settle()
        await e.s.action("skip_step", None)
        await e.settle()

    run(go())
    assert review.load_state()[k]["box"] == 0 and review.load_state()[k]["lastResult"] == "missed"
    assert len(store.completed()) == 1


def test_an_ordinary_lesson_is_unchanged_by_the_hook(state):
    e = Engine()

    async def go():
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        await e.s._pass_step()
        await e.settle()

    run(go())
    assert not (state / "review.json").exists()


# ---------------------------------------------------------------------------------------------- the socket: review.start
from server.orchestrator.tests.test_launch_contract import _engine, _until, quiet_env  # noqa: E402,F401


def _seed_finished_lesson(tmp_path, days_ago: float = 3):
    """A finished, cached lesson whose skills are mastered, finished `days_ago` days ago (so every review is due)."""
    g = stubs.load_fixture_lesson()
    lib = tmp_path / "library"
    lib.mkdir(exist_ok=True)
    (lib / "lesson-1.json").write_text(json.dumps(g))
    import time as _t

    fin = _t.time() - days_ago * DAY
    nodes = [(f"n{i}", s["title"], "mastered") for i, s in enumerate(g["steps"])]
    store._write_atomic(store.state_dir() / "history.json", [entry(g["lesson"]["id"], fin, "PyTorch", *nodes)])
    return g


def test_review_start_replays_the_skills_own_step(quiet_env, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    g = _seed_finished_lesson(tmp_path)
    main, eng, ws_rec, calls = _engine(monkeypatch)
    title = g["steps"][1]["title"]
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "engine.hello" and "review.start" in hello["payload"]["capabilities"]
            ws.send_json({"type": "progress.get", "payload": {}})
            prog = _until(ws, "progress")[-1]["payload"]
            assert prog["review"]["due"] == len(g["steps"]) and prog["review"]["items"][0]["when"] == "Today"
            ws.send_json({"type": "review.start", "payload": {"label": title}})
            got = _until(ws, "step.started")
            ready = next(m for m in got if m["type"] == "lesson.ready")["payload"]
            assert [s["id"] for s in ready["steps"]] == ["s2"] and "Review" in ready["lesson"]["title"]
    assert calls == []  # no model call anywhere
    assert eng.session.graph["lesson"]["review"]["label"] == title  # marked: its pass / skip goes to the schedule
    assert review.load_state() == {}  # starting records nothing; only a pass or a skipped step does


def test_review_start_with_nothing_to_review_says_so(quiet_env, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    main, eng, _, calls = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            ws.receive_json()
            ws.send_json({"type": "review.start", "payload": {"label": "Nope"}})
            err = _until(ws, "error")[-1]["payload"]
            assert "review" in err["message"].lower()
            ws.send_json({"type": "review.start", "payload": {"label": 5, "skillId": ["x"]}})  # junk reads as absent
            assert _until(ws, "error")[-1]["type"] == "error"
    assert eng.session.graph is None and calls == []

