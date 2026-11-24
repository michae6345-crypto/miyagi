"""Skill tree messages over the real WebSocket endpoint (TestClient), offline: engine.hello lists them; tracks / skill /
mastery / reviews round-trip; proofs and skills can be deleted; bad payloads get one error and the engine carries on;
a passed step sends skills.update. Stub modules: any build fails the test; no model, no network."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from server.orchestrator.tests.test_launch_contract import _engine, _until, quiet_env  # noqa: F401 - the fixture
from server.skilltree import ledger, proofs, service

DAY = 86_400


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _mastered(sid: str, days_ago: float) -> None:
    now = time.time() - days_ago * DAY
    ledger.record_pass([sid], now=now - DAY)
    ledger.record_pass([sid], now=now)


def test_hello_lists_the_skills_commands(quiet_env, monkeypatch, state):
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "engine.hello"
        assert set(service.COMMANDS) <= set(hello["payload"]["capabilities"])


def test_tracks_skill_mastery_reviews_round_trip(quiet_env, monkeypatch, state):
    _mastered("bl.navigate", days_ago=10)  # its 3-day review is due
    pid = proofs.save({"kind": "snippet", "text": "Pad001.Length = 5"}, skill_ids=["cad.pad"])
    ledger.record_pass(["cad.pad"], proof_id=pid)
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        ws.send_json({"type": "skills.tracks.get", "payload": {}})
        tracks = _until(ws, "skills.tracks")[-1]["payload"]
        ids = [t["id"] for t in tracks["tracks"]]
        assert "blender" in ids and "cad" in ids and len(ids) > 5 and tracks["due"] == 1
        ws.send_json({"type": "skills.tracks.get", "payload": {"track": "cad"}})
        (cad,) = _until(ws, "skills.tracks")[-1]["payload"]["tracks"]
        pad = next(s for s in cad["skills"] if s["id"] == "cad.pad")
        assert pad["state"] == "practicing" and pad["proofIds"] == [pid]
        ws.send_json({"type": "skill.get", "payload": {"id": "cad.pad"}})
        sk = _until(ws, "skill")[-1]["payload"]["skill"]
        assert sk["proofs"][0]["text"] == "Pad001.Length = 5" and sk["lessons"]
        ws.send_json({"type": "skills.mastery.get", "payload": {}})
        m = _until(ws, "skills.mastery")[-1]["payload"]
        assert [r["id"] for r in m["mastered"]] == ["bl.navigate"] and [r["id"] for r in m["practicing"]] == ["cad.pad"]
        ws.send_json({"type": "skills.reviews.get", "payload": {}})
        r = _until(ws, "skills.reviews")[-1]["payload"]
        assert r["due"] == 1 and r["items"][0]["skillId"] == "bl.navigate" and r["items"][0]["interval"] == 3


def test_deletes_and_bad_payloads(quiet_env, monkeypatch, state):
    p1 = proofs.save({"kind": "output", "text": "$ python3 a.py\nok"}, skill_ids=["py.run"])
    p2 = proofs.save({"kind": "snippet", "text": "x = 1"}, skill_ids=["py.variables"])
    ledger.record_pass(["py.run"], proof_id=p1)
    ledger.record_pass(["py.variables"], proof_id=p2)
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        ws.send_json({"type": "skill.proof.delete", "payload": {"id": p1}})
        assert _until(ws, "skills.proofs")[-1]["payload"] == {"deleted": 1}
        ws.send_json({"type": "skill.proof.delete", "payload": {"skillId": "py.variables"}})
        sk = _until(ws, "skill")[-1]["payload"]["skill"]
        assert sk["proofs"] == [] and sk["state"] == "practicing"  # the pass stays, its proof went
        for bad in ({"type": "skill.get", "payload": {"id": "../x"}},
                    {"type": "skill.get", "payload": {"id": "zz.nothing"}},
                    {"type": "skill.proof.delete", "payload": {}},
                    {"type": "skills.reviews.get", "payload": {"days": 1000}}):
            ws.send_json(bad)
            assert _until(ws, "error")[-1]["payload"]["message"]
        ws.send_json({"type": "skill.forget", "payload": {"id": "py.run"}})
        m = _until(ws, "skills.mastery")[-1]["payload"]
        assert [r["id"] for r in m["practicing"]] == ["py.variables"]
        ws.send_json({"type": "skill.forget", "payload": {}})
        assert _until(ws, "skills.mastery")[-1]["payload"]["practicing"] == []
    assert ledger.load() == {} and proofs.for_skill("py.variables") == []


def test_data_delete_wipes_the_proofs(quiet_env, monkeypatch, state):
    proofs.save({"kind": "snippet", "text": "x = 1"}, skill_ids=["py.variables"])
    main, *_ = _engine(monkeypatch)
    with TestClient(main.app) as client, client.websocket_connect("/") as ws:
        ws.receive_json()
        ws.send_json({"type": "data.delete", "payload": {}})
        for _ in range(200):
            if not proofs.for_skill("py.variables"):
                break
            time.sleep(0.02)
    assert proofs.for_skill("py.variables") == []


def test_a_passed_step_sends_skills_update(quiet_env, monkeypatch, state):
    from server.orchestrator import stubs

    main, eng, _, _ = _engine(monkeypatch)
    g = stubs.load_fixture_lesson()
    g["lesson"].update({"id": "les-bl", "title": "Mug cup", "goal": "Teach Blender inset and extrude by hollowing a "
                                                                     "cylinder into the cup of a mug.", "libraries": {}})
    for st in g["steps"]:
        st.pop("skillIds", None)

    async def go() -> list[dict]:
        await eng.session.load_graph(g)
        await eng.session.drain()
        await eng.session._pass_step()
        await eng.session.drain()
        return [m for m in eng.hub.history if m["type"] == "skills.update"]

    (msg,) = asyncio.run(go())
    assert [s["id"] for s in msg["payload"]["skills"]] == ["bl.extrude"]
    assert msg["payload"]["skills"][0]["state"] == "practicing" and msg["payload"]["events"] == []
