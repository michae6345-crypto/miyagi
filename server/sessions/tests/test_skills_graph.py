"""The Skills page's graph (Progress.graph): states, edges, capstones, goal, next, also ready, keep fresh, events, week, the
goal / ack commands, step.skillIds, LibraryItem.teaches, and a round trip through the pydantic contract.
Offline and deterministic: an injected clock and a fixed time zone, no model, no network.
Run from the repo root:  python -m pytest server/sessions/tests/test_skills_graph.py -q"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server.lesson import library, skillmap
from server.orchestrator.main import contract_library_detail, contract_progress
from server.orchestrator.tests.test_launch_contract import _engine, _until, quiet_env  # noqa: F401 - the fixture
from server.sessions import progress, review, skills_graph as sg, store
from shared.contracts import events as contract

UTC = timezone.utc
DAY = 86400.0
T0 = datetime(2026, 11, 18, 15, 30, tzinfo=UTC).timestamp()  # a Wednesday, mid-afternoon


def at(days: float, hour: int = 9) -> float:
    return (datetime(2026, 11, 18, hour, 0, tzinfo=UTC) + timedelta(days=days)).timestamp()


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(d))
    monkeypatch.setenv("MIYAGI_LIBRARY_DIR", str(tmp_path / "library"))
    return d


def smap(track, nodes, edges=(), cross=(), nxt=()):
    return {"track": track, "headline": "", "nodes": [{"id": i, "label": label, "state": st} for i, label, st in nodes],
            "edges": [{"from": a, "to": b} for a, b in edges], "cross": list(cross),
            "next": [{"title": t, "goal": g} for t, g in nxt]}


def entry(lesson_id, finished_at, m, minutes=None):
    e = {"lessonId": lesson_id, "title": lesson_id.title(), "covered": [], "finishedAt": finished_at, "skillMap": m}
    if minutes is not None:
        e["result"] = {"passed": 3, "skipped": 0, "total": 3, "minutes": minutes}
    return e


def by_id(g):
    return {s["id"]: s for s in g["skills"]}


def numpy_entry(finished=None):
    return entry("numpy", finished or at(-3), smap(
        "NumPy", [("arrays", "Arrays", "mastered"), ("index", "Indexing", "mastered"), ("broad", "Broadcasting", "learning"),
                  ("vect", "Vectorized math", "next")],
        edges=[("arrays", "index"), ("index", "broad"), ("broad", "vect")], nxt=[("Vectorized math", "vectorize loops")]))


def test_nothing_known_is_no_graph():
    assert sg.build_graph([], now=T0) is None
    assert sg.graph(now=T0) is None


def test_states_come_from_the_maps_and_prerequisites():
    g = sg.build_graph([numpy_entry()], now=T0)
    s = by_id(g)
    assert s["numpy.arrays"]["state"] == "mastered" and s["numpy.indexing"]["state"] == "mastered"
    assert s["numpy.broadcasting"]["state"] == "practicing"  # a skipped step
    assert s["numpy.vectorized-math"]["state"] == "locked"  # its prerequisite is practicing, not mastered
    assert s["numpy.arrays"]["masteredAt"] == at(-3) and "masteredAt" not in s["numpy.broadcasting"]
    assert s["numpy.arrays"]["lessons"][0]["lessonId"] == "numpy"
    assert all(x["kind"] in ("skill", "capstone") for x in g["skills"])


def test_next_skill_with_every_prerequisite_mastered_is_ready_and_the_best_state_wins_across_lessons():
    first = entry("a", at(-5), smap("Git", [("c", "Commits", "mastered"), ("b", "Branches", "next")], edges=[("c", "b")]))
    later = entry("b", at(-1), smap("Git", [("c", "Commits", "next"), ("b", "Branches", "next")], edges=[("c", "b")]))
    s = by_id(sg.build_graph([first, later], now=T0))
    assert s["git.commits"]["state"] == "mastered" and s["git.commits"]["masteredAt"] == at(-5)
    assert s["git.branches"]["state"] == "ready"


def test_edges_requires_helps_and_no_loops():
    git = entry("git", at(-2), smap("Git", [("c", "Commits", "mastered"), ("b", "Branches", "next")], edges=[("c", "b")],
                                    cross=[{"track": "NumPy", "label": "Arrays", "to": "b", "note": "shared idea"},
                                           {"track": "Nowhere", "label": "Ghost", "to": "b"}]))
    loop = entry("loop", at(-1), smap("Git", [("b", "Branches", "next"), ("c", "Commits", "mastered")], edges=[("b", "c")]))
    g = sg.build_graph([git, numpy_entry(), loop], now=T0)
    edges = {(e["from"], e["to"], e.get("kind")) for e in g["edges"]}
    both = [("git.commits", "git.branches", "requires") in edges, ("git.branches", "git.commits", "requires") in edges]
    assert sum(both) == 1  # whichever lesson came first stands; the other direction would close a loop
    assert ("numpy.arrays", "git.branches", "helps") in edges  # cross link from a skill that exists
    assert not any("ghost" in e["from"] for e in g["edges"])  # a cross source nobody learned is not invented
    helps = [e for e in g["edges"] if e["kind"] == "helps"]
    assert helps and all(0 < e["weight"] <= 1 for e in helps)


def test_one_capstone_per_track_requires_the_track_and_completes_when_all_are_mastered():
    done = entry("g", at(-2), smap("Git", [("c", "Commits", "mastered"), ("b", "Branches", "mastered")], edges=[("c", "b")]))
    g = sg.build_graph([done, numpy_entry()], now=T0)
    caps = {c["id"]: c for c in g["capstones"]}
    assert set(caps) == {"git.capstone", "numpy.capstone"}
    assert caps["git.capstone"]["requires"] == ["git.commits", "git.branches"]
    assert caps["git.capstone"]["completedAt"] == at(-2) and "completedAt" not in caps["numpy.capstone"]
    s = by_id(g)
    assert s["git.capstone"]["kind"] == "capstone" and s["git.capstone"]["state"] == "mastered"
    assert s["numpy.capstone"]["state"] == "practicing"
    assert {"from": "numpy.vectorized-math", "to": "numpy.capstone", "kind": "requires"} in g["edges"]
    assert [p["capstoneId"] for p in g["portfolio"]] == ["git.capstone"]
    assert g["portfolio"][0]["skillIds"] == ["git.commits", "git.branches"]


def test_goal_defaults_to_the_furthest_along_unfinished_track_and_a_stored_goal_wins():
    done = entry("g", at(-2), smap("Git", [("c", "Commits", "mastered")]))
    far = entry("n", at(-1), smap("Pandas", [("a", "Frames", "mastered"), ("b", "Groups", "mastered"), ("c", "Joins", "next")],
                                  edges=[("a", "b"), ("b", "c")]))
    low = entry("m", at(-1), smap("Math", [("a", "Vectors", "mastered"), ("b", "Matrices", "next"), ("c", "Eigen", "next")],
                                  edges=[("a", "b"), ("b", "c")]))
    g = sg.build_graph([done, low, far], now=T0)
    assert g["goal"] == "pandas.capstone"  # git is finished; pandas is 2 of 3, math 1 of 3
    g2 = sg.build_graph([done, low, far], prefs={"goal": "math.capstone"}, now=T0)
    assert g2["goal"] == "math.capstone"
    g3 = sg.build_graph([done, low, far], prefs={"goal": "gone.capstone"}, now=T0)
    assert g3["goal"] == "pandas.capstone"  # a stale pick is ignored
    only_done = sg.build_graph([done], now=T0)
    assert only_done["goal"] is None and "next" not in only_done


def test_next_is_on_the_goal_path_practicing_first_and_carries_its_lesson_step():
    g = sg.build_graph([numpy_entry()], index={"numpy": "lib-numpy"}, now=T0)
    nxt = g["next"]
    assert nxt["skillId"] == "numpy.broadcasting"  # practicing before the locked next one
    assert nxt["lessonId"] == "numpy" and nxt["libraryId"] == "lib-numpy"
    assert nxt["why"] and len(nxt["why"].split()) <= 12
    ready = sg.build_graph([entry("g", at(-2), smap("Git", [("c", "Commits", "mastered"), ("b", "Branches", "next")],
                                                    edges=[("c", "b")], nxt=[("Branches", "learn git branches")]))], now=T0)
    assert ready["next"]["skillId"] == "git.branches" and ready["next"]["goal"] == "learn git branches"
    assert "lessonId" not in ready["next"]


def test_a_lesson_in_progress_gives_evidence_and_the_step_to_continue():
    graph = {"lesson": {"id": "np2", "title": "NumPy basics", "track": "numpy"},
             "steps": [{"id": f"s{i}", "title": t, "kind": k, "what": t} for i, (t, k) in enumerate(
                 [("Make arrays", "code"), ("Run it", "run"), ("Index arrays", "code"), ("Broadcast", "code")], 1)]}
    current = {"lessonId": "np2", "title": "NumPy basics", "stepIndex": 2, "stepCount": 4, "passedSteps": ["s1", "s2"],
               "skippedSteps": [], "lastActiveAt": at(-0.5)}
    g = sg.build_graph([], current, graph, index={"np2": "lib-np2"}, now=T0)
    s = by_id(g)
    assert s["numpy.make-arrays"]["state"] == "mastered" and s["numpy.make-arrays"]["masteredAt"] == at(-0.5)
    assert s["numpy.index-arrays"]["state"] == "ready"
    assert g["next"]["skillId"] == "numpy.index-arrays" and g["next"]["lessonId"] == "np2"
    assert g["next"]["stepIndex"] == 2 and g["next"]["stepCount"] == 4
    # one skill with two steps, one passed: practicing with evidence
    graph2 = {"lesson": {"id": "np3", "track": "numpy"}, "steps": [
        {"id": "a", "title": "Slicing", "keyIdea": "Slicing", "kind": "code"}, {"id": "b", "title": "More slicing", "keyIdea": "Slicing", "kind": "code"}]}
    cur2 = {"lessonId": "np3", "title": "Slicing", "stepIndex": 1, "stepCount": 2, "passedSteps": ["a"], "skippedSteps": [],
            "lastActiveAt": at(-0.1)}
    sk = by_id(sg.build_graph([], cur2, graph2, now=T0))["numpy.slicing"]
    assert sk["state"] == "practicing" and sk["evidence"] == {"done": 1, "total": 2} and sk["lessons"][0]["stepIds"] == ["a", "b"]


def test_also_ready_and_keep_fresh_are_capped_at_three():
    nodes = [(f"n{i}", f"Skill {i}", "next") for i in range(6)]
    solo = entry("x", at(-4), smap("Many", nodes))  # no edges: all six are ready
    g = sg.build_graph([solo], now=T0)
    assert len(g["alsoReady"]) == 3 and g["next"]["skillId"] not in g["alsoReady"]
    assert all(by_id(g)[i]["state"] == "ready" for i in g["alsoReady"])
    mastered = entry("y", at(-30), smap("Old", [(f"m{i}", f"Old {i}", "mastered") for i in range(5)]))
    rows = review.items([mastered], {}, T0)
    g2 = sg.build_graph([mastered], review_rows=rows, now=T0)
    assert len(g2["keepFresh"]) == 3
    due = [by_id(g2)[i]["review"]["dueAt"] for i in g2["keepFresh"]]
    assert due == sorted(due) and all(d <= T0 + DAY for d in due)
    assert all("review" in s for s in g2["skills"] if s["state"] == "mastered" and s["kind"] == "skill")
    fresh = entry("z", T0 - 60, smap("New", [("a", "Fresh", "mastered")]))
    state_ = {review.skill_key("New", "Fresh"): {"box": 3, "lastResult": "passed", "lastAt": T0 - 60, "reps": 3}}
    far = sg.build_graph([fresh], review_rows=review.items([fresh], state_, T0), now=T0)
    assert far["keepFresh"] == [] and "review" in by_id(far)["new.fresh"]  # next review is two weeks away: scheduled, not due


def test_events_since_the_ack_each_with_a_stable_id():
    hist = [entry("g", at(-2), smap("Git", [("c", "Commits", "mastered"), ("b", "Branches", "next")], edges=[("c", "b")])),
            entry("n", at(-10), smap("Old", [("a", "Old skill", "mastered")]))]
    g = sg.build_graph(hist, prefs={"ackedUntil": at(-5)}, now=T0)
    ids = [e["id"] for e in g["events"]]
    assert ids == ["mastered:git.commits", "unlocked:git.branches"]
    assert g["events"][1] == {"id": "unlocked:git.branches", "kind": "unlocked", "skillId": "git.branches", "at": at(-2), "from": "git.commits"}
    assert g["ackedUntil"] == at(-5)
    again = sg.build_graph(hist, prefs={"ackedUntil": at(-5)}, now=T0 + 5)
    assert [e["id"] for e in again["events"]] == ids  # stable across reads
    assert sg.build_graph(hist, prefs={"ackedUntil": at(-1)}, now=T0)["events"] == []
    # never acked: only the last day plays, the old history never replays
    fresh = sg.build_graph(hist, now=T0)
    assert fresh["events"] == [] and fresh["ackedUntil"] == T0 - sg.UNSEEN_WINDOW_S
    assert [e["skillId"] for e in sg.build_graph(hist, now=at(-2) + 3600)["events"]] == ["git.commits", "git.branches"]
    done = entry("d", at(-1), smap("Fin", [("a", "Only", "mastered")]))
    kinds = {e["kind"] for e in sg.build_graph([done], prefs={"ackedUntil": at(-3)}, now=T0)["events"]}
    assert kinds == {"mastered", "capstone_done"}


def test_week_counts_the_learners_own_monday_first_week():
    hist = [entry("a", at(-1), smap("Git", [("c", "Commits", "mastered")]), minutes=12),  # Tuesday
            entry("b", at(-3), smap("Old", [("o", "Old", "mastered")]), minutes=30)]  # last Sunday: not this week
    g = sg.build_graph(hist, activity=[at(0, 7)], now=T0, tz=UTC)
    w = g["week"]
    assert w["days"] == [False, True, True, False, False, False, False]
    assert w["minutes"] == 12 and w["mastered"] == 1
    assert "goalAway" not in w  # every track is finished: there is no goal to be away from
    none = sg.build_graph([entry("c", at(-1), smap("Git", [("c", "Commits", "mastered")]))], now=T0, tz=UTC)
    assert "minutes" not in none["week"]  # nothing records minutes: absent, never zero


def test_payload_round_trips_through_the_contract():
    g = sg.build_graph([numpy_entry(), entry("g", at(-2), smap("Git", [("c", "Commits", "mastered"), ("b", "Branches", "next")],
                                                              edges=[("c", "b")], cross=[{"track": "NumPy", "label": "Arrays", "to": "b"}]))],
                       index={"numpy": "lib-numpy"}, review_rows=review.items([numpy_entry()], {}, T0), now=T0, tz=UTC)
    payload = contract_progress({"skills": [], "completed": [], "inProgress": [], "graph": g})
    ev = contract.ProgressEvent.model_validate(payload)
    assert ev.graph is not None and ev.graph.goal == g["goal"]
    assert [s.id for s in ev.graph.skills] == [s["id"] for s in g["skills"]]
    assert ev.graph.next is not None and ev.graph.next.skillId == g["next"]["skillId"]
    back = json.loads(ev.graph.model_dump_json(by_alias=True, exclude_none=True))
    assert {(e["from"], e["to"]) for e in back["edges"]} == {(e["from"], e["to"]) for e in g["edges"]}
    assert len(ev.graph.alsoReady or []) <= 3 and len(ev.graph.keepFresh or []) <= 3


def test_choices_persist_and_the_ack_never_moves_back(state):
    assert sg.load_prefs() == {}
    sg.set_goal("pandas.capstone")
    sg.ack(at(-2))
    sg.ack(at(-4))  # an older ack arriving late changes nothing
    assert sg.load_prefs() == {"goal": "pandas.capstone", "ackedUntil": at(-2)}
    sg.ack("2026-11-19T00:00:00Z")  # a Moment may be ISO text
    assert sg.load_prefs()["ackedUntil"] == datetime(2026, 11, 19, tzinfo=UTC).timestamp()
    sg.ack("not a time")
    sg.ack(None)
    assert sg.load_prefs()["goal"] == "pandas.capstone"
    (state / "skills.json").write_text("{not json")
    assert sg.load_prefs() == {}  # unreadable reads as empty


def test_progress_carries_the_graph_from_the_saved_state(state):
    store._write_atomic(state / "history.json", [numpy_entry(finished=T0 - DAY)])
    p = progress.progress()
    assert p is not None and p["graph"]["skills"] and p["graph"]["goal"] == "numpy.capstone"
    sg.set_goal("numpy.capstone")
    assert progress.progress()["graph"]["goal"] == "numpy.capstone"


def test_node_steps_and_skill_tags_follow_the_same_ids_as_the_graph():
    g = {"lesson": {"id": "L", "title": "Lists in Python", "track": "python"},
         "steps": [{"id": "s1", "title": "Make a list", "kind": "code"}, {"id": "s2", "title": "Run it", "kind": "run"},
                   {"id": "s3", "title": "Loop over it", "kind": "code"}],
         }
    ns = skillmap.node_steps(g)
    assert ns["track"] == "Python"
    assert [(t["label"], t["steps"]) for t in ns["taught"]] == [("Make a list", ["s1", "s2"]), ("Loop over it", ["s3"])]
    tags, by_step = library.skill_tags(g)
    assert tags["teaches"] == ["python.make-a-list", "python.loop-over-it"] and "unlocks" not in tags
    assert by_step == {"s1": ["python.make-a-list"], "s2": ["python.make-a-list"], "s3": ["python.loop-over-it"]}
    g["lesson"]["nextTopics"] = ["Dictionaries"]
    assert library.skill_tags(g)[0]["unlocks"] == ["python.dictionaries"]
    # the id a finished lesson's map gives the same skill is the one the tags name
    done = sg.build_graph([entry("L", at(-1), skillmap.skill_map(g, {"passed": ["s1", "s2", "s3"], "skipped": []}))], now=T0)
    assert {"python.make-a-list", "python.loop-over-it", "python.dictionaries"} <= {s["id"] for s in done["skills"]}
    assert library.skill_tags({}) == ({}, {}) and skillmap.node_steps({})["taught"] == []
    row = library.summary(g, "lib1")
    assert row["teaches"] == ["python.make-a-list", "python.loop-over-it"]
    detail = contract_library_detail({"item": {**library.detail(g, "lib1"), "id": "lib1"}})
    assert detail["steps"][0]["skillIds"] == ["python.make-a-list"] and detail["steps"][2]["skillIds"] == ["python.loop-over-it"]
    contract.LibraryItemEvent.model_validate({"item": detail["item"], "steps": detail["steps"]})


# ------------------------------------------------------------------------------------------------ the commands
def test_hello_lists_set_goal_and_skills_ack_and_both_commands_work(quiet_env, monkeypatch, state):
    store._write_atomic(state / "history.json", [numpy_entry(finished=T0 - DAY)])
    main, eng, _, _ = _engine(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "engine.hello"
            caps = hello["payload"]["capabilities"]
            assert "set_goal" in caps and "skills.ack" in caps and "progress.get" in caps
            ws.send_json({"type": "set_goal", "payload": {"capstoneId": "numpy.capstone"}})
            got = _until(ws, "progress")[-1]["payload"]
            assert got["graph"]["goal"] == "numpy.capstone"
            assert sg.load_prefs()["goal"] == "numpy.capstone"
            ws.send_json({"type": "skills.ack", "payload": {"until": at(-1)}})
            for _ in range(200):  # reads run beside each other: wait for the ack to land before asking again
                if sg.load_prefs().get("ackedUntil") == at(-1):
                    break
                time.sleep(0.02)
            ws.send_json({"type": "progress.get", "payload": {}})
            after = _until(ws, "progress")[-1]["payload"]
            assert after["graph"]["ackedUntil"] == at(-1) and after["graph"]["goal"] == "numpy.capstone"
            ws.send_json({"type": "set_goal", "payload": {"capstoneId": 5}})  # malformed: one error, the engine carries on
            err = _until(ws, "error")[-1]
            assert err["payload"]["message"]
            ws.send_json({"type": "progress.get", "payload": {}})
            assert _until(ws, "progress")[-1]["payload"]["graph"]["goal"] == "numpy.capstone"
    assert sg.load_prefs() == {"goal": "numpy.capstone", "ackedUntil": at(-1)}


def test_lesson_ready_steps_and_outline_carry_skill_ids(quiet_env, monkeypatch):
    import asyncio

    from server.orchestrator import stubs

    _, eng, _, _ = _engine(monkeypatch)

    async def go() -> dict:
        await eng.session.load_graph(stubs.load_fixture_lesson())
        await eng.session.drain()
        return eng.session._lesson_ready_payload()

    payload = asyncio.run(go())
    steps = payload["steps"]
    assert steps and all(isinstance(st.get("skillIds"), list) and st["skillIds"] for st in steps)
    assert all("." in i for st in steps for i in st["skillIds"])
    outline = payload["lesson"]["outline"]["steps"]
    assert [r.get("skillIds") for r in outline] == [st.get("skillIds") for st in steps]
    contract.OutlineStep.model_validate(outline[0])
