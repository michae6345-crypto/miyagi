from __future__ import annotations

import json
import time

import pytest

from server.plans import catalog, progress
from server.plans.playlist import lessons_from
from server.sessions import store
from shared.contracts.events import PlanState

PLID = "PLtestTESTtest0123456789"
PL = {"playlistId": PLID, "title": "Rust from zero", "channel": "Ex", "url": "u",
      "videos": [{"id": "ccccccccccc", "title": "Rust 1", "seconds": 600}, {"id": "ddddddddddd", "title": "Rust 2",
                                                                          "seconds": None}]}


def _finish(lesson_id: str, title: str = "A lesson", goal: str = "") -> None:
    """What sessions.store.record_completed writes when a lesson's last step passes."""
    store.record_completed({"lesson": {"id": lesson_id, "title": title, "goal": goal},
                            "steps": [{"id": "s1", "title": "one"}]}, skill_map={"skills": []})


def _running(lesson_id: str, started_at: float, **extra) -> None:
    store.save({"lessonId": lesson_id, "title": "x", "startedAt": started_at, "stepIndex": 2, "stepCount": 5,
                "passedSteps": ["a", "b"], **extra}, {"lesson": {"id": lesson_id}, "steps": []})


def _playlist(pl: dict = PL) -> dict:
    return progress.start_playlist(pl["playlistId"], lessons_from(pl), title=pl["title"], channel=pl["channel"])


def _states(v: dict) -> list[str]:
    return [r["state"] for r in v["lessons"]]


def test_start_catalog_plan_is_a_contract_plan_state(plans_state):
    v = progress.start_catalog("intro-python")
    PlanState.model_validate(v)
    py = catalog.get("intro-python")
    assert v["id"] == v["catalogId"] == "intro-python" and v["source"] == "preset" and v["track"] == py["track"]
    assert v["done"] == 0 and v["total"] == len(py["lessons"]) and v["nextIndex"] == 0
    assert v["minutesLeft"] == catalog.total_minutes(py) and v["tool"] == py["tool"]
    assert _states(v) == ["next"] + ["todo"] * (len(py["lessons"]) - 1)
    le = v["lessons"][0]
    assert le["goal"] == py["lessons"][0]["goal"] and le["skillIds"] == py["lessons"][0]["grows"]
    assert le["stepCount"] == py["lessons"][0]["steps"] and le["check"] == py["lessons"][0]["check"]
    assert v["project"]["state"] == "locked" and v["project"]["title"] == py["project"]["title"]
    assert isinstance(v["startedAt"], str) and "T" in v["startedAt"] and isinstance(v["updatedAt"], str)
    assert "finishedAt" not in v
    assert set(json.loads((plans_state / "plans.json").read_text())["plans"]) == {"intro-python"}
    assert progress.start_catalog("intro-python")["startedAt"] == v["startedAt"]  # the same plan, not a new one
    with pytest.raises(KeyError):
        progress.start_catalog("no-such-plan")


def test_lesson_done_through_the_linked_lesson_id():
    progress.start_catalog("intro-c")
    v = progress.lesson_starting("intro-c", 0)
    assert v["lessons"][0]["state"] == "in_progress" and v["nextIndex"] == 0 and v["lessons"][0]["openedAt"]
    assert progress.link_lesson("intro-c", 0, "les-1")
    _running("les-1", time.time())
    v = progress.view("intro-c")
    assert v["done"] == 0 and v["lessons"][0]["steps"] == {"done": 2, "total": 5}  # the running lesson's own count
    assert v["lessons"][0]["lessonId"] == "les-1"
    _finish("les-1")
    v = progress.view("intro-c")
    PlanState.model_validate(v)
    assert v["done"] == 1 and v["lessons"][0]["state"] == "done" and v["lessons"][0]["doneAt"]
    assert v["nextIndex"] == 1 and v["lessons"][1]["state"] == "next"


def test_unmarking_a_finished_lesson_sticks():
    """Regression: mark_done(False) on a lesson whose engine lesson is in history.json was re-marked by reconcile."""
    progress.start_catalog("intro-c")
    progress.lesson_starting("intro-c", 0)
    progress.link_lesson("intro-c", 0, "les-1")
    _finish("les-1")
    assert progress.view("intro-c")["done"] == 1
    v = progress.mark_done("intro-c", 0, False)
    assert v["done"] == 0 and v["lessons"][0]["state"] != "done"
    assert progress.view("intro-c")["done"] == 0  # the next sync keeps it un-marked
    assert progress.all_views()[0]["done"] == 0
    assert progress.mark_done("intro-c", 0, True)["done"] == 1  # marking it again still works
    progress.mark_done("intro-c", 0, False)
    progress.lesson_starting("intro-c", 0)  # opened again: a fresh run that can finish it
    progress.link_lesson("intro-c", 0, "les-2")
    _finish("les-2")
    assert progress.view("intro-c")["lessons"][0]["state"] == "done"


def test_reconcile_links_the_lesson_that_started_after_the_plan_lesson():
    progress.start_catalog("intro-go")
    progress.lesson_starting("intro-go", 2)
    _running("les-go", time.time() + 1)
    progress.view("intro-go")  # links it
    _finish("les-go")
    v = progress.view("intro-go")
    assert _states(v)[:3] == ["next", "todo", "done"] and v["nextIndex"] == 0


def test_reconcile_does_not_link_an_older_or_much_later_lesson():
    progress.start_catalog("intro-go")
    progress.lesson_starting("intro-go", 0)
    _running("les-old", time.time() - 3600)
    _finish("les-old")
    assert progress.view("intro-go")["done"] == 0
    _running("les-late", time.time() + progress.LINK_WINDOW_S + 60)
    _finish("les-late")
    assert progress.view("intro-go")["done"] == 0


def test_a_video_lesson_stamped_far_from_the_ask_is_not_linked():
    """A wall-clock jump: the running lesson names the video but started far outside the link window."""
    _playlist()
    key = progress.playlist_key(PLID)
    progress.lesson_starting(key, 1)
    _running("les-far", time.time() + progress.LINK_WINDOW_S + 600, sourceUrl="https://www.youtube.com/watch?v=ddddddddddd")
    _finish("les-far")
    assert progress.view(key)["done"] == 0


def test_reconcile_by_the_goal_a_finished_lesson_covered():
    progress.start_catalog("intro-rust")
    goal = catalog.get("intro-rust")["lessons"][1]["goal"]
    progress.lesson_starting("intro-rust", 1)
    _finish("les-r", title="Something else", goal=goal)
    v = progress.view("intro-rust")
    assert v["lessons"][1]["state"] == "done"


def test_playlist_plan_links_by_video_and_keeps_done_when_re_added():
    v = _playlist()
    PlanState.model_validate(v)
    assert v["id"] == "pl-" + PLID and v["source"] == "playlist" and v["playlistId"] == PLID and v["total"] == 2
    assert v["lessons"][0]["videoId"] == "ccccccccccc" and v["lessons"][0]["minutes"] == 10
    progress.lesson_starting(v["id"], 1)
    _running("les-v", time.time(), sourceUrl="https://www.youtube.com/watch?v=ddddddddddd")
    _finish("les-v")
    assert progress.view(v["id"])["lessons"][1]["state"] == "done"
    # the playlist gained a video at the top: the done mark follows its video
    pl2 = dict(PL, videos=[{"id": "eeeeeeeeeee", "title": "Intro", "seconds": 30}] + PL["videos"])
    v2 = _playlist(pl2)
    assert _states(v2) == ["next", "todo", "done"] and v2["total"] == 3


def test_skipped_lessons_and_a_finished_plan():
    v = progress.start_playlist(PLID, lessons_from(PL), title="Rust", skipped={0})
    assert _states(v) == ["skipped", "next"] and v["total"] == 1 and v["nextIndex"] == 1
    v = progress.mark_done(v["id"], 1)
    PlanState.model_validate(v)
    assert v["finishedAt"] and "nextIndex" not in v and v["done"] == v["total"] == 1
    v = progress.mark_done(v["id"], 1, False)
    assert "finishedAt" not in v and v["nextIndex"] == 1


def test_goal_plan_from_accepted_lessons():
    lessons = [{"title": "Sketch", "goal": "Teach a sketch", "minutes": 10, "grows": ["cad.sketch"],
                "from": {"planId": "intro-cad", "index": 0}}, {"title": "Print", "goal": "Teach printing", "minutes": 5}]
    v = progress.start_goal("I want to 3D print a stand", lessons, title="3D print a stand",
                            tool={"id": "freecad", "label": "FreeCAD"})
    PlanState.model_validate(v)
    assert v["id"].startswith("goal-") and len(v["id"]) == 13 and v["source"] == "goal"
    assert v["goal"] == "I want to 3D print a stand" and v["lessons"][0]["skillIds"] == ["cad.sketch"]
    assert v["minutesLeft"] == 15 and v["tool"]["id"] == "freecad"
    again = progress.start_goal("i want to 3d print a stand!", [], title="x")
    assert again["id"] == v["id"] and again["total"] == 2  # the same goal answers with the plan already there


def test_mark_done_remove_and_order():
    assert progress.all_views() == []
    progress.start_catalog("intro-sql")
    progress.start_catalog("intro-r")
    assert [v["id"] for v in progress.all_views()] == ["intro-r", "intro-sql"]
    n = len(catalog.get("intro-r")["lessons"])
    for i in range(n):
        v = progress.mark_done("intro-r", i)
    assert v["finishedAt"] and "nextIndex" not in v and v["project"]["state"] == "ready"
    assert progress.done_plan_ids() == {"intro-r"}
    assert progress.skills_done() >= set(catalog.get("intro-r")["lessons"][0]["grows"])
    assert "finishedAt" not in progress.mark_done("intro-r", 0, False)
    assert progress.mark_done("intro-r", 99) is None and progress.mark_done("nope", 0) is None
    assert progress.remove("intro-sql") and not progress.remove("intro-sql")
    assert [v["id"] for v in progress.all_views()] == ["intro-r"]


def test_v1_records_are_read_as_v2(plans_state):
    plans_state.mkdir(parents=True, exist_ok=True)
    now = time.time()
    (plans_state / "plans.json").write_text(json.dumps({"version": 1, "active": "intro-c", "plans": {
        "intro-c": {"key": "intro-c", "kind": "catalog", "planId": "intro-c", "done": [0], "started": {}, "current": None,
                    "startedAt": now, "lastActiveAt": now},
        "yt-" + PLID: {"key": "yt-" + PLID, "kind": "playlist", "playlistId": PLID, "title": "Rust",
                       "lessons": lessons_from(PL), "done": [], "started": {}, "startedAt": now, "lastActiveAt": now - 1}}}))
    views = progress.all_views()
    assert [v["id"] for v in views] == ["intro-c", "pl-" + PLID]
    assert views[0]["source"] == "preset" and views[0]["done"] == 1 and views[1]["source"] == "playlist"
    for v in views:
        PlanState.model_validate(v)


def test_corrupt_or_foreign_state_reads_as_empty(plans_state):
    plans_state.mkdir(parents=True, exist_ok=True)
    (plans_state / "plans.json").write_text("{nope")
    assert progress.all_views() == [] and progress.view("intro-c") is None
    (plans_state / "plans.json").write_text(json.dumps({"plans": {"../etc": {"source": "preset"}, "intro-c": "x"}}))
    assert progress.all_views() == []
    progress.start_catalog("intro-c")
    assert [v["id"] for v in progress.all_views()] == ["intro-c"]


def test_a_catalog_plan_that_left_the_catalog_has_no_lessons(monkeypatch, tmp_path):
    progress.start_catalog("intro-c")
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"plans": [catalog.get("intro-go")]}))
    monkeypatch.setenv("MIYAGI_PLANS_CATALOG", str(f))
    catalog.reload()
    v = progress.view("intro-c")
    assert v["total"] == 0 and "nextIndex" not in v and "finishedAt" not in v
    assert progress.lesson_starting("intro-c", 0) is None


def test_iso_times():
    assert progress.iso(None) is None and progress.iso(0) is None and progress.iso(True) is None
    assert progress.iso(1_700_000_000).startswith("2023-11-1")
