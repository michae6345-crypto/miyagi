"""Skill tree over the real WebSocket endpoint (TestClient), offline: engine.hello lists proof.get; progress.get carries
the catalog tree (tracks, round 3 fields) and validates against the contract; proof.get answers by id and by skill;
data.delete removes proofs only for no `what`, "proofs" or "all"; a passed step's step.passed carries the v4 fields.
Stub modules: any build fails the test; no model, no network."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from server.orchestrator.tests.test_launch_contract import _engine, _until, quiet_env  # noqa: F401 - the fixture
from server.skilltree import ledger, proofs
from shared.contracts import events as contract

DAY = 86_400


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _wait(cond, n: int = 200) -> None:
    for _ in range(n):
        if cond():
            return
        time.sleep(0.02)


def test_hello_lists_proof_get(quiet_env, monkeypatch, state):
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "engine.hello" and "proof.get" in hello["payload"]["capabilities"]


def test_progress_carries_the_catalog_tree(quiet_env, monkeypatch, state):
    now = time.time()
    ledger.record_pass(["bl.navigate"], now=now - 11 * DAY, lesson_id="L1", step_id="s1", step_title="Orbit")
    ledger.record_pass(["bl.navigate"], now=now - 10 * DAY, lesson_id="L2", step_id="s1")
    ledger.record_pass(["cad.pad"], now=now - DAY)
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        ws.send_json({"type": "progress.get", "payload": {}})
        got = _until(ws, "progress")[-1]["payload"]
    contract.validate_engine_payload("progress", got)
    g = got["graph"]
    assert [t["id"] for t in g["tracks"]] == ["blender", "cad"]
    nav = next(s for s in g["skills"] if s["id"] == "bl.navigate")
    assert nav["state"] == "mastered" and nav["schedule"]["round"] == 0 and nav["steps"][0]["title"] == "Orbit"
    assert g["masteryDays"] == 2 and g["reviewDays"] == [3, 7, 21, 60] and "bl.navigate" in g["keepFresh"]


def test_proof_get_by_id_and_skill(quiet_env, monkeypatch, state):
    pid = proofs.save({"kind": "code", "text": "Pad001.Length = 5", "lang": "python"}, skill_ids=["cad.pad"],
                      lesson={"id": "L", "title": "Bracket"}, step={"id": "s2", "title": "Pad it"})
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        ws.send_json({"type": "proof.get", "payload": {"id": pid, "reqId": "r1"}})
        one = _until(ws, "proof")[-1]["payload"]
        ws.send_json({"type": "proof.get", "payload": {"skillId": "cad.pad"}})
        many = _until(ws, "proof")[-1]["payload"]
        ws.send_json({"type": "proof.get", "payload": {"id": "pf-gone-0000"}})
        none = _until(ws, "proof")[-1]["payload"]
        ws.send_json({"type": "proof.get", "payload": {"id": 5}})  # malformed: one error, the engine carries on
        assert _until(ws, "error")[-1]["payload"]["message"]
    for p in (one, many, none):
        contract.ProofEvent.model_validate(p)
    assert one["reqId"] == "r1" and one["items"][0]["text"] == "Pad001.Length = 5" and one["items"][0]["key"] == "L:s2"
    assert many["skillId"] == "cad.pad" and [i["id"] for i in many["items"]] == [pid] and none["items"] == []


def test_data_delete_removes_proofs_for_no_what_proofs_or_all(quiet_env, monkeypatch, state):
    proofs.save({"kind": "code", "text": "x = 1"}, skill_ids=["py.variables"])
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        ws.send_json({"type": "data.delete", "payload": {"what": ["notes"]}})
        ws.send_json({"type": "proof.get", "payload": {"skillId": "py.variables"}})  # instant reads run in order here
        _wait(lambda: False, n=10)
        assert len(proofs.for_skill("py.variables")) == 1
        ws.send_json({"type": "data.delete", "payload": {"what": ["proofs"]}})
        _wait(lambda: not proofs.for_skill("py.variables"))
        assert proofs.for_skill("py.variables") == []
        proofs.save({"kind": "code", "text": "y = 2"}, skill_ids=["py.variables"])
        ws.send_json({"type": "data.delete", "payload": {}})
        _wait(lambda: not proofs.for_skill("py.variables"))
    assert proofs.for_skill("py.variables") == []


def test_data_delete_all_or_progress_forgets_the_skill_record(quiet_env, monkeypatch, state):
    """skilltree.json holds every pass with its lesson and step titles: "all" / "progress" / Delete my data erase it;
    "proofs" and "notes" keep it."""
    def seed():
        ledger.record_pass(["py.variables"], now=time.time(), lesson_id="L", step_id="s1", lesson_title="Vars",
                           step_title="Make x")

    seed()
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        for what in (["notes"], ["proofs"]):
            ws.send_json({"type": "data.delete", "payload": {"what": what}})
        _wait(lambda: False, n=10)
        assert "py.variables" in ledger.load()
        for payload in ({"what": ["all"]}, {"what": ["progress"]}, {}):
            seed()
            ws.send_json({"type": "data.delete", "payload": payload})
            _wait(lambda: not ledger.load())
            assert ledger.load() == {} and not ledger.path().exists()


def test_review_start_for_a_catalog_skill_loads_its_review_lesson(quiet_env, monkeypatch, state, tmp_path):
    main, eng, _, _ = _engine(monkeypatch)
    src = {"lesson": {"id": "L9", "title": "A FreeCAD bracket", "workdir": "/elsewhere"},
           "steps": [{"id": "s1", "title": "Sketch a rectangle"}, {"id": "s2", "title": "Pad the sketch 5 mm"}]}
    monkeypatch.setattr(main.library_mod, "index_by_lesson_id", lambda: {"L9": "lib9"})
    monkeypatch.setattr(main.library_mod, "load_graph", lambda lid: src if lid == "lib9" else None)
    monkeypatch.setattr(main, "_library_folder", lambda g: str(tmp_path / "bracket"))
    assert eng._review_graph("cad.pad", "") is None  # not mastered: REVIEW_GONE
    ledger.record_pass(["cad.pad"], now=time.time() - 9 * DAY, lesson_id="L9", step_id="s2")
    ledger.record_pass(["cad.pad"], now=time.time() - 8 * DAY, lesson_id="L9", step_id="s2")
    g = eng._review_graph("cad.pad", "")
    assert g["lesson"]["_folder"] == str(tmp_path / "bracket") and "workdir" not in g["lesson"]
    assert [s["id"] for s in g["steps"]] == ["s2"] and g["lesson"]["review"]["key"] == "skilltree::cad.pad"


def test_a_passed_catalog_step_sends_skill_ids_and_progress_shows_it(quiet_env, monkeypatch, state):
    from server.orchestrator import stubs

    main, eng, _, _ = _engine(monkeypatch)
    g = stubs.load_fixture_lesson()
    g["lesson"].update({"id": "les-bl", "title": "Mug cup", "goal": "Teach Blender inset and extrude by hollowing a "
                                                                     "cylinder into the cup of a mug.", "libraries": {}})
    for st in g["steps"]:
        st.pop("skillIds", None)

    async def go() -> tuple[list[dict], dict]:
        await eng.session.load_graph(g)
        await eng.session.drain()
        await eng.session._pass_step()
        await eng.session.drain()
        eng.forget_reads()
        return [m for m in eng.hub.history if m["type"] == "step.passed"], await eng.progress_payload()

    (msg,), prog = asyncio.run(go())
    assert msg["payload"]["skillIds"] == ["bl.extrude"] and msg["payload"]["key"] == "les-bl:s1"
    assert msg["payload"]["assisted"] is False
    ext = next(s for s in prog["graph"]["skills"] if s["id"] == "bl.extrude")
    assert ext["state"] == "practicing" and ext["steps"][0]["passed"] is True
    assert any(st["passed"] is False for st in ext["steps"])  # the lesson's other steps, not passed yet
