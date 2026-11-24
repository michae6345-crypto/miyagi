"""Skill tree engine: catalog tracks (Blender, CAD), deterministic step tagging, mastery on 2 unassisted days, the
3 / 7 / 21 / 60 review schedule, proofs (capped, redacted, deletable) and the payloads. Offline: no model, no network."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from server.skilltree import catalog, graph, ledger, proofs, service, tagging
from shared.contracts import events as contract

UTC = timezone.utc
DAY = 86_400


def t(day: int, hour: int = 10) -> float:
    return datetime(2026, 11, day, hour, tzinfo=UTC).timestamp()


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


# ------------------------------------------------------------------------------------------------ catalog
def test_catalog_has_more_than_five_tracks_with_blender_and_cad():
    ids = [tr.id for tr in catalog.tracks()]
    assert len(ids) > 5
    for want in ("blender", "cad", "fusion", "onshape", "python"):
        assert want in ids
    blender = catalog.get().tracks_by_id["blender"]
    assert [p.id for p in blender.plans] == ["intro-blender", "blender-animation", "blender-materials"]
    assert blender.label == "Blender" and catalog.get().tracks_by_id["cad"].label == "CAD"
    assert {"bl.extrude", "bla.keyframes", "blm.uv"} <= {s.id for s in blender.skills}
    cad = catalog.get().tracks_by_id["cad"]
    assert {"cad.sketch", "cad.pad", "cadp.slicer"} <= {s.id for s in cad.skills}


def test_catalog_skill_needs_resolve_and_lessons_grow_every_skill():
    cat = catalog.get()
    for sk in cat.skills_by_id.values():
        for n in sk.needs:
            assert cat.skills_by_id.get(n), (sk.id, n)
        assert sk.lessons, f"{sk.id} is grown by no lesson"


def test_match_lesson_by_goal_and_title():
    plan, lesson = catalog.match_lesson({"title": "x", "goal": "Teach G, R and S in Blender with axis keys and typed "
                                                               "numbers by placing a cube, a cone and a sphere at set spots."})
    assert plan.id == "intro-blender" and lesson["grows"] == ["bl.transform"]
    assert catalog.match_lesson({"title": "Move, rotate and scale"})[1]["grows"] == ["bl.transform"]
    assert catalog.match_lesson({"title": "Weather CLI", "goal": "build a weather app"}) is None


def test_broken_catalog_reads_as_empty(tmp_path, monkeypatch):
    bad = tmp_path / "c.json"
    bad.write_text("{nope")
    monkeypatch.setenv("MIYAGI_SKILL_CATALOG", str(bad))
    assert catalog.tracks() == [] and catalog.skill("bl.edit") is None
    assert tagging.tag_step({"id": "s1", "title": "Extrude the top face"}, {"title": "Blender"}) == []


# ------------------------------------------------------------------------------------------------ tagging
def test_tag_explicit_step_ids_win():
    step = {"id": "s1", "skillIds": ["bl.render", "nope.x"], "title": "Extrude"}
    assert tagging.tag_step(step, {"grows": ["bl.extrude"]}) == ["bl.render"]


def test_tag_one_grown_skill_goes_to_every_step():
    lesson = {"title": "Move, rotate and scale"}
    assert tagging.tag_step({"id": "s1", "title": "Open Blender"}, lesson) == ["bl.transform"]


def test_tag_two_grown_skills_split_by_the_step_words():
    lesson = {"grows": ["cad.sketch", "cad.constrain"]}
    assert tagging.tag_step({"id": "a", "title": "Draw a rectangle in the sketcher"}, lesson) == ["cad.sketch"]
    assert tagging.tag_step({"id": "b", "title": "Add a dimension constraint"}, lesson) == ["cad.constrain"]
    assert tagging.tag_step({"id": "c", "title": "Look around"}, lesson) == ["cad.sketch", "cad.constrain"]


def test_tag_fallback_blender_and_cad_without_catalog_match():
    les = {"title": "Make a chair in Blender", "goal": "model a chair"}
    assert tagging.tag_step({"id": "s", "title": "Extrude the seat down", "instructions": "Press E"}, les)[0] == "bl.extrude"
    assert "bl.loops" in tagging.tag_step({"id": "s", "title": "Add a loop cut and bevel the edges"}, les)
    cad = {"title": "A FreeCAD bracket"}
    assert tagging.tag_step({"id": "s", "title": "Pad the sketch 5 mm"}, cad)[0] == "cad.pad"
    assert tagging.tag_step({"id": "s", "title": "Fillet the outside edges"}, cad)[0] == "cad.fillet"


def test_tag_fallback_python_from_file_suffix_and_nothing_for_unknown():
    step = {"id": "s", "title": "Write the function", "file": "app.py", "code": "def add(a, b):\n    return a + b\n"}
    assert tagging.tag_step(step, {"title": "Weather CLI"}) == ["py.functions"]
    assert tagging.tag_step({"id": "s", "title": "Breathe"}, {"title": "Meditation"}) == []


def test_tag_graph_is_deterministic():
    g = {"lesson": {"title": "Extrude and inset"}, "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}]}
    one, two = tagging.tag_graph(g), tagging.tag_graph(json.loads(json.dumps(g)))
    assert one == two and set(one) == {"s1", "s2"}


# ------------------------------------------------------------------------------------------------ mastery
def test_mastery_needs_unassisted_passes_on_two_different_days(state):
    assert ledger.record_pass(["bl.edit"], now=t(1), tz=UTC) == []
    assert ledger.record_pass(["bl.edit"], now=t(1, 15), tz=UTC) == []  # same day: still 1 day
    assert ledger.skill_row("bl.edit", now=t(1, 16), tz=UTC)["state"] == "practicing"
    assert ledger.record_pass(["bl.edit"], now=t(2), tz=UTC, assisted=True) == []  # a hint: not toward mastery
    row = ledger.skill_row("bl.edit", now=t(2), tz=UTC)
    assert row["unassistedDays"] == 1 and row["passes"] == 3 and "masteredAt" not in row
    ev = ledger.record_pass(["bl.edit"], now=t(3), tz=UTC)
    assert ev == [{"kind": "mastered", "skillId": "bl.edit", "at": t(3), "nextDueAt": t(6, 0)}]
    row = ledger.skill_row("bl.edit", now=t(3), tz=UTC)
    assert row["state"] == "mastered" and row["review"]["interval"] == 3 and row["review"]["due"] is False


def test_unknown_skill_ids_are_ignored(state):
    assert ledger.record_pass(["nope.x"], now=t(1)) == []
    assert not (state / "skilltree.json").exists()


def test_ready_and_locked_follow_needs(state):
    rows = ledger.load()
    assert ledger.state_of("bl.navigate", rows) == "ready"
    assert ledger.state_of("bl.transform", rows) == "locked"
    ledger.record_pass(["bl.navigate"], now=t(1), tz=UTC)
    ledger.record_pass(["bl.navigate"], now=t(2), tz=UTC)
    assert ledger.state_of("bl.transform", ledger.load()) == "ready"


def _master(sid: str) -> None:
    ledger.record_pass([sid], now=t(1), tz=UTC)
    ledger.record_pass([sid], now=t(2), tz=UTC)


def test_review_schedule_3_7_21_60_then_60(state):
    _master("cad.pad")
    due = ledger.skill_row("cad.pad", now=t(2), tz=UTC)["review"]["dueAt"]
    assert due == t(5, 0)
    assert ledger.record_pass(["cad.pad"], now=t(4), tz=UTC) == []  # before due: practice, no review
    now, intervals = t(5, 9), []
    for _ in range(5):
        (ev,) = ledger.record_pass(["cad.pad"], now=now, tz=UTC)
        assert ev["kind"] == "reviewed"
        intervals.append(ev["interval"])
        now = ev["nextDueAt"] + 3600
    assert intervals == [7, 21, 60, 60, 60]


def test_assisted_or_missed_review_resets_to_three_days_but_keeps_mastery(state):
    _master("py.loops")
    (ev,) = ledger.record_pass(["py.loops"], now=t(5, 9), tz=UTC)
    assert ev["interval"] == 7
    (ev,) = ledger.record_pass(["py.loops"], now=t(12, 9), tz=UTC, assisted=True)
    assert ev["kind"] == "review_missed" and ev["interval"] == 3 and ev["nextDueAt"] == t(15, 0)
    row = ledger.skill_row("py.loops", now=t(12, 10), tz=UTC)
    assert row["state"] == "mastered" and row["review"]["lastResult"] == "missed"
    ev = ledger.record_review("py.loops", False, now=t(20), tz=UTC)
    assert ev["kind"] == "review_missed"
    assert ledger.record_review("py.dicts", True, now=t(20)) is None  # never mastered: nothing to review


def test_due_lists_oldest_first_with_overdue_days(state):
    _master("bl.navigate")
    ledger.record_pass(["cad.pad"], now=t(3), tz=UTC)
    ledger.record_pass(["cad.pad"], now=t(4), tz=UTC)
    rows = ledger.due(now=t(10), tz=UTC)
    assert [r["skillId"] for r in rows] == ["bl.navigate", "cad.pad"]
    assert rows[0]["overdueDays"] == 5 and rows[0]["track"] == "blender"
    assert ledger.due(now=t(4, 12), tz=UTC) == []


def test_forget_one_and_all(state):
    _master("bl.edit")
    ledger.record_pass(["bl.render"], now=t(1))
    assert ledger.forget("bl.edit") == 1 and ledger.forget("bl.edit") == 0
    assert set(ledger.load()) == {"bl.render"}
    assert ledger.forget() == 1 and ledger.load() == {}


def test_corrupt_ledger_reads_empty(state):
    state.mkdir(parents=True)
    (state / "skilltree.json").write_text('{"skills": {"bl.edit": {"passes": [{"at": "x"}], "review": {"stage": 9}}}}')
    assert ledger.load()["bl.edit"] == {"passes": [], "masteredAt": None, "review": None}


def test_passes_are_capped(state):
    for i in range(ledger.MAX_PASSES + 10):
        ledger.record_pass(["py.run"], now=t(1) + i)
    assert len(ledger.load()["py.run"]["passes"]) == ledger.MAX_PASSES


# ------------------------------------------------------------------------------------------------ proofs
def test_proof_code_is_the_learners_lines_redacted_and_capped(state):
    step = {"id": "s1", "file": "app.py", "code": "def add(a, b):\n    return a + b"}
    text = 'KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"\n\ndef add(a, b):\n    return a+b  # mine\n    return a + b\n'
    body = proofs.build(step, file_text=text, file_ref="app.py")
    assert body["kind"] == "code" and body["file"] == "app.py" and body["lang"] == "python" and body["line"] == 3
    assert body["text"].startswith("def add(a, b):") and "sk-ant" not in body["text"] and "truncated" not in body
    long = "def add(a, b):\n" + "\n".join(f"    x{i} = {i}" for i in range(200)) + "\n    return a + b\n"
    body = proofs.build({**step, "code": long}, file_text=long, file_ref="app.py")
    assert body["truncated"] and len(body["text"].splitlines()) <= proofs.MAX_LINES and len(body["text"]) <= proofs.TEXT_MAX


def test_proof_command_cell_and_secret_files(state):
    run = {"command": "python3 app.py", "output": ["ok"] * 100 + ["token=ghp_" + "a" * 36]}
    body = proofs.build({"id": "r", "kind": "run", "run_command": "python3 app.py"}, run=run)
    assert body["kind"] == "command" and body["text"] == "python3 app.py" and body["lang"] == "shell"
    assert body["truncated"] and "ghp_" not in body["output"] and len(body["output"]) <= proofs.OUTPUT_MAX
    cell = proofs.build({"id": "c", "file": "a.ipynb"}, cell={"source": "x = 1\nx", "output": "1"})
    assert cell["kind"] == "cell" and cell["output"] == "1" and cell["file"] == "a.ipynb"
    assert proofs.build({"id": "s", "code": "A=1"}, file_text="A=1", file_ref=".env") is None
    assert proofs.build({"id": "s", "code": "print(1)"}, file_text="nothing here") is None


def test_proof_save_wire_validates_against_the_contract(state):
    step = {"id": "s3", "title": "Hollow the cup", "checks": [{"id": "c1", "label": "The cup is hollow"}]}
    pid = proofs.save({"kind": "code", "text": "bpy.ops.mesh.inset()", "lang": "python"}, skill_ids=["bl.extrude"],
                      lesson={"id": "lesson-abc12345", "title": "Mug cup"}, step=step, now=t(1))
    rec = proofs.get(pid)
    assert pid.startswith("pf-") and rec["key"] == "lesson-abc12345:s3" and rec["check"] == {"label": "The cup is hollow"}
    wire = proofs.wire(rec, UTC)
    assert wire["at"] == "2026-11-01T10:00:00+00:00"
    contract.Proof.model_validate(wire)
    ev = service.proof_payload(None, "bl.extrude", "r1")
    contract.ProofEvent.model_validate(ev)
    assert ev["reqId"] == "r1" and [i["id"] for i in ev["items"]] == [pid]
    assert service.proof_payload("pf-nope-0000", None)["items"] == []


def test_proof_cap_and_delete(state, monkeypatch):
    monkeypatch.setattr(proofs, "MAX_PROOFS", 3)
    ids = [proofs.save({"kind": "code", "text": f"x = {i}"}, skill_ids=["py.variables"], now=t(1) + i) for i in range(5)]
    left = [p["id"] for p in proofs.for_skill("py.variables", limit=10)]
    assert left == ids[:1:-1]  # the newest 3, newest first
    assert proofs.get(ids[4])["text"] == "x = 4" and proofs.get("../etc") is None
    ledger.record_pass(["py.variables"], now=t(2), proof_id=ids[4])
    assert proofs.delete(ids[4]) and not proofs.delete(ids[4])
    assert "proofId" not in ledger.load()["py.variables"]["passes"][0]
    assert proofs.delete_for_skill("py.variables") == 2
    proofs.save({"kind": "cell", "text": "1"}, skill_ids=["np.arrays"])
    assert proofs.wipe() == 1 and proofs.for_skill("np.arrays") == []


def test_data_delete_kinds_that_remove_proofs():
    assert service.deletes_proofs(None) and service.deletes_proofs(["proofs"]) and service.deletes_proofs(["all"])
    assert not service.deletes_proofs(["notes"]) and not service.deletes_proofs([])


# ------------------------------------------------------------------------------------------------ progress.graph
def test_graph_merge_adds_touched_tracks_round3_fields_and_validates(state):
    pid = proofs.save({"kind": "code", "text": "x"}, skill_ids=["bl.navigate"], lesson={"id": "L1"}, step={"id": "s1"}, now=t(1))
    ledger.record_pass(["bl.navigate"], now=t(1), tz=UTC, lesson_id="L1", step_id="s1", proof_id=pid,
                       lesson_title="Viewport", step_title="Orbit")
    ledger.record_pass(["bl.navigate"], now=t(2), tz=UTC, lesson_id="L2", step_id="s1", assisted=True)
    ledger.record_pass(["bl.navigate"], now=t(3), tz=UTC, lesson_id="L2", step_id="s2")
    current = {"lesson": {"id": "L3", "title": "Move, rotate and scale"}, "steps": [{"id": "s1", "title": "Grab"}],
               "tags": {"s1": ["bl.transform"]}}
    base = {"skills": [], "completed": [], "graph": {"skills": [{"id": "python.x", "label": "x", "track": "Python"}], "edges": []}}
    out = graph.merge(base, current=current, now=t(10), tz=UTC)
    g = out["graph"]
    contract.SkillGraphInfo.model_validate(g)
    contract.validate_engine_payload("progress", out)
    ids = [s["id"] for s in g["skills"]]
    assert ids[0] == "python.x" and "bl.navigate" in ids and "bl.render" in ids and "cad.pad" not in ids
    nav = next(s for s in g["skills"] if s["id"] == "bl.navigate")
    assert nav["state"] == "mastered" and nav["catalogId"] == "bl.navigate"
    assert nav["mastery"] == {"need": 2, "days": ["2026-11-01", "2026-11-03"], "assisted": 1}
    assert nav["schedule"] == {"dueAt": "2026-11-06T00:00:00+00:00", "round": 0, "interval": 3}
    assert nav["review"] == {"dueAt": "2026-11-06T00:00:00+00:00"} and nav["proofIds"] == [pid]
    assert [st["key"] for st in nav["steps"]] == ["L1:s1", "L2:s1", "L2:s2"] and nav["evidence"] == {"done": 3, "total": 3}
    assert nav["steps"][0]["lessonTitle"] == "Viewport" and nav["steps"][1]["assisted"] is True
    tr = next(s for s in g["skills"] if s["id"] == "bl.transform")
    assert tr["state"] == "ready" and tr["steps"] == [{"lessonId": "L3", "stepId": "s1", "title": "Grab", "passed": False,
                                                       "lessonTitle": "Move, rotate and scale"}]
    assert {"from": "bl.navigate", "to": "bl.transform", "kind": "requires"} in g["edges"]
    (track,) = g["tracks"]
    assert track["id"] == "blender" and track["mastered"] == 1 and track["next"] == "bl.transform"
    assert track["planIds"] == ["intro-blender", "blender-animation", "blender-materials"]
    assert g["masteryDays"] == 2 and g["reviewDays"] == [3, 7, 21, 60] and g["keepFresh"] == ["bl.navigate"]


def test_graph_merge_events_and_nothing_touched(state):
    assert graph.merge({}, now=t(5)) == {} and graph.merge(None, now=t(5)) == {}
    ledger.record_pass(["cad.pad"], now=t(1), tz=UTC)
    ledger.record_pass(["cad.pad"], now=t(2), tz=UTC)
    g = graph.merge({}, now=t(2, 12), tz=UTC)["graph"]
    assert [e["kind"] for e in g["events"]] == ["mastered"] and g["events"][0]["skillId"] == "cad.pad"
    g = graph.merge({"graph": {"ackedUntil": t(2, 11)}}, now=t(2, 12), tz=UTC)["graph"]
    assert "events" not in g
    assert [tr["id"] for tr in g["tracks"]] == ["cad"]


# ------------------------------------------------------------------------------------------------ review.start
def test_catalog_review_graph_replays_the_steps_behind_the_skill(state):
    from server.skilltree import review

    src = {"lesson": {"id": "L9", "title": "A FreeCAD bracket", "_folder": "/tmp/x"},
           "steps": [{"id": "s1", "title": "Sketch a rectangle"}, {"id": "s2", "title": "Pad the sketch 5 mm"}]}
    assert review.review_graph("cad.pad", lambda lid: src) is None  # not mastered yet
    ledger.record_pass(["cad.pad"], now=t(1), lesson_id="L9", step_id="s2")
    ledger.record_pass(["cad.pad"], now=t(2), lesson_id="L9", step_id="s2")
    asked: list[str] = []
    g = review.review_graph("cad.pad", lambda lid: asked.append(lid) or (src if lid == "L9" else None))
    assert asked == ["L9"] and [s["id"] for s in g["steps"]] == ["s2"] and g["steps"][0]["skillIds"] == ["cad.pad"]
    assert g["lesson"]["review"] == {"key": "skilltree::cad.pad", "label": "Pad", "skillId": "cad.pad"}
    assert g["lesson"]["id"] == "review-cad-pad-L9" and g["lesson"]["_folder"] == "/tmp/x"
    assert "skillIds" not in src["steps"][1]  # the cached lesson is never changed
    assert tagging.tag_graph(g) == {"s2": ["cad.pad"]}
    (ev,) = ledger.record_pass(tagging.tag_graph(g)["s2"], now=t(6), tz=UTC, lesson_id=g["lesson"]["id"], step_id="s2")
    assert ev["kind"] == "reviewed" and ev["interval"] == 7


def test_sessions_review_never_schedules_a_catalog_key(state):
    from server.sessions import review as old_review

    old_review.record_result_safely("skilltree::cad.pad", True)
    assert old_review.load_state() == {}
