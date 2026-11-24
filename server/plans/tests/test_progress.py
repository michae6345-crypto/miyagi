from __future__ import annotations

import json
import time

import pytest

from server.plans import catalog, progress
from server.sessions import store

PL = {"playlistId": "PLtestTESTtest0123456789", "title": "Rust from zero", "channel": "Ex", "url": "u",
      "videos": [{"id": "ccccccccccc", "title": "Rust 1", "seconds": 600}, {"id": "ddddddddddd", "title": "Rust 2",
                                                                          "seconds": None}]}


def _finish(lesson_id: str, title: str = "A lesson", goal: str = "") -> None:
    """What sessions.store.record_completed writes when a lesson's last step passes."""
    store.record_completed({"lesson": {"id": lesson_id, "title": title, "goal": goal},
                            "steps": [{"id": "s1", "title": "one"}]}, skill_map={"skills": []})


def _running(lesson_id: str, started_at: float, **extra) -> None:
    store.save({"lessonId": lesson_id, "title": "x", "startedAt": started_at, "stepIndex": 2, "stepCount": 5,
                "passedSteps": ["a", "b"], **extra}, {"lesson": {"id": lesson_id}, "steps": []})


def test_start_catalog_plan_and_next_lesson(plans_state):
    v = progress.start_catalog("intro-python", goal="automate my spreadsheets")
    py = catalog.get("intro-python")
    assert v["key"] == "intro-python" and v["kind"] == "catalog" and v["active"] and v["goal"].startswith("automate")
    assert v["done"] == 0 and v["total"] == len(py["lessons"]) and v["next"] == {"index": 0, "title": py["lessons"][0]["title"]}
    assert v["minutesLeft"] == catalog.total_minutes(py)
    assert all(r["state"] == "todo" for r in v["lessons"])
    spec = progress.lesson_spec("intro-python")
    assert spec == {"key": "intro-python", "index": 0, "title": py["lessons"][0]["title"], "query": py["lessons"][0]["goal"]}
    assert json.loads((plans_state / "plans.json").read_text())["active"] == "intro-python"
    with pytest.raises(KeyError):
        progress.start_catalog("no-such-plan")


def test_lesson_done_through_the_linked_lesson_id():
    progress.start_catalog("intro-c")
    v = progress.lesson_starting("intro-c", 0)
    assert v["lessons"][0]["state"] == "current" and v["next"]["index"] == 0
    assert progress.link_lesson("intro-c", 0, "les-1")
    _running("les-1", time.time())
    v = progress.view("intro-c")
    assert v["done"] == 0 and v["next"]["steps"] == {"passed": 2, "total": 5}  # the running lesson's own count
    _finish("les-1")
    v = progress.view("intro-c")
    assert v["done"] == 1 and v["lessons"][0]["state"] == "done" and v["next"]["index"] == 1
    assert progress.lesson_spec("intro-c")["index"] == 1


def test_reconcile_links_the_lesson_that_started_after_the_plan_lesson():
    progress.start_catalog("intro-go")
    progress.lesson_starting("intro-go", 2)
    _running("les-go", time.time() + 1)
    progress.view("intro-go")  # links it
    _finish("les-go")
    v = progress.view("intro-go")
    assert [r["state"] for r in v["lessons"][:3]] == ["todo", "todo", "done"] and v["next"]["index"] == 0


def test_reconcile_does_not_link_an_older_or_much_later_lesson():
    progress.start_catalog("intro-go")
    progress.lesson_starting("intro-go", 0)
    _running("les-old", time.time() - 3600)
    _finish("les-old")
    assert progress.view("intro-go")["done"] == 0
    _running("les-late", time.time() + progress.LINK_WINDOW_S + 60)
    _finish("les-late")
    assert progress.view("intro-go")["done"] == 0


def test_reconcile_by_the_goal_a_finished_lesson_covered():
    progress.start_catalog("intro-rust")
    goal = catalog.get("intro-rust")["lessons"][1]["goal"]
    progress.lesson_starting("intro-rust", 1)
    _finish("les-r", title="Something else", goal=goal)
    v = progress.view("intro-rust")
    assert v["lessons"][1]["state"] == "done"


def test_playlist_plan_links_by_video_and_keeps_done_when_re_added():
    v = progress.start_playlist(PL)
    assert v["key"] == "yt-" + PL["playlistId"] and v["kind"] == "playlist" and v["total"] == 2
    assert v["lessons"][0]["videoId"] == "ccccccccccc" and v["lessons"][0]["minutes"] == 10
    spec = progress.lesson_spec(v["key"], 1)
    assert spec["url"] == "https://www.youtube.com/watch?v=ddddddddddd"
    progress.lesson_starting(v["key"], 1)
    _running("les-v", time.time(), sourceUrl="https://www.youtube.com/watch?v=ddddddddddd")
    _finish("les-v")
    assert progress.view(v["key"])["lessons"][1]["state"] == "done"
    # the playlist gained a video at the top: the done mark follows its video
    pl2 = dict(PL, videos=[{"id": "eeeeeeeeeee", "title": "Intro", "seconds": 30}] + PL["videos"])
    v2 = progress.start_playlist(pl2)
    assert [r["state"] for r in v2["lessons"]] == ["todo", "todo", "done"] and v2["total"] == 3


def test_mark_done_remove_and_resume():
    assert progress.resume() is None
    progress.start_catalog("intro-sql")
    progress.start_catalog("intro-r")
    assert progress.resume()["key"] == "intro-r"
    n = len(catalog.get("intro-r")["lessons"])
    for i in range(n):
        v = progress.mark_done("intro-r", i)
    assert v["complete"] and v["next"] is None and progress.lesson_spec("intro-r") is None
    assert progress.resume()["key"] == "intro-sql"  # the active plan is complete: the next unfinished one
    assert progress.done_plan_ids() == {"intro-r"}
    assert progress.mark_done("intro-r", 0, False)["complete"] is False
    assert progress.mark_done("intro-r", 99) is None and progress.mark_done("nope", 0) is None
    assert progress.remove("intro-sql") and not progress.remove("intro-sql")
    assert [v["key"] for v in progress.all_views()] == ["intro-r"]


def test_corrupt_or_foreign_state_reads_as_empty(plans_state):
    plans_state.mkdir(parents=True, exist_ok=True)
    (plans_state / "plans.json").write_text("{nope")
    assert progress.all_views() == [] and progress.view("intro-c") is None
    (plans_state / "plans.json").write_text(json.dumps({"plans": {"../etc": {"kind": "catalog"}, "intro-c": "x"},
                                                        "active": "../etc"}))
    assert progress.all_views() == []
    progress.start_catalog("intro-c")
    assert [v["key"] for v in progress.all_views()] == ["intro-c"]


def test_a_catalog_plan_that_left_the_catalog_has_no_lessons(monkeypatch, tmp_path):
    progress.start_catalog("intro-c")
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"plans": [catalog.get("intro-go")]}))
    monkeypatch.setenv("MIYAGI_PLANS_CATALOG", str(f))
    catalog.reload()
    v = progress.view("intro-c")
    assert v["total"] == 0 and v["next"] is None and not v["complete"]
    assert progress.lesson_spec("intro-c") is None
