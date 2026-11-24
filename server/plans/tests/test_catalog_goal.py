from __future__ import annotations

import json

import pytest

from server.plans import catalog, goal


def test_shipped_catalog_loads_every_plan_with_lessons_and_skills():
    plans = catalog.plans()
    assert len(plans) == 40
    ids = [p["id"] for p in plans]
    assert len(set(ids)) == 40 and "intro-python" in ids and "intro-blender" in ids
    for p in plans:
        assert 6 <= len(p["lessons"]) <= 12, p["id"]
        assert all(le["goal"].startswith("Teach") for le in p["lessons"]), p["id"]
        assert all(le["check"] in catalog.CHECKS for le in p["lessons"])
        assert all(catalog.get(n) for n in p["needs"]), p["id"]  # every prerequisite plan exists
        skill_ids = {s["id"] for s in p["skills"]}
        assert all(g in skill_ids for le in p["lessons"] for g in le["grows"]), p["id"]
    assert len(catalog.playlists()) == 50
    assert {pl["planId"] for pl in catalog.playlists()} <= set(ids)


def test_summary_and_detail_shapes():
    py = catalog.get("intro-python")
    row = catalog.summary(py)
    assert row["id"] == "intro-python" and row["lessonCount"] == len(py["lessons"])
    assert row["minutes"] == sum(le["minutes"] for le in py["lessons"]) and row["playlists"] == 2
    assert "lessons" not in row and row["tool"] == {"id": "vscode", "label": "VS Code"}
    det = catalog.detail(py)
    assert [le["index"] for le in det["lessons"]] == list(range(len(py["lessons"])))
    assert len(det["project"]["checks"]) == 3 and det["skills"]
    det["lessons"][0]["grows"].append("x")  # a copy: the cached catalog is untouched
    assert "x" not in catalog.get("intro-python")["lessons"][0]["grows"]


def test_bad_catalog_files_are_dropped_not_fatal(tmp_path, monkeypatch):
    good = catalog.get("intro-c")
    f = tmp_path / "catalog.json"
    f.write_text(json.dumps({"version": 1, "plans": [good, {"id": "Bad Id", "title": "x", "lessons": []},
                                                      {"id": "no-lessons", "title": "No lessons", "lessons": []}, 7]}))
    monkeypatch.setenv("MIYAGI_PLANS_CATALOG", str(f))
    monkeypatch.setenv("MIYAGI_PLANS_PLAYLISTS", str(tmp_path / "missing.json"))
    catalog.reload()
    assert [p["id"] for p in catalog.plans()] == ["intro-c"]
    assert catalog.playlists() == []
    f.write_text("{not json")
    catalog.reload()
    assert catalog.plans() == []


@pytest.mark.parametrize("text, plan_id", [
    ("python", "intro-python"),
    ("learn pandas for my lab data", "pandas"),
    ("3d printing a phone stand", "cad-3d-printing"),
    ("build a website", "intro-html-css"),
    ("I want to make games", "intro-godot"),
    ("make an iPhone app", "intro-swift"),
    ("spreadsheets for my budget", "intro-excel"),
    ("neural networks", "neural-networks"),
    ("AI chatbot with claude", "llm-basics"),
    ("learn git", "intro-git"),
    ("Blender", "intro-blender"),
])
def test_goal_maps_to_catalog_plan_with_no_model(text, plan_id):
    out = goal.match(text)
    assert out["confident"] and out["matches"][0]["planId"] == plan_id, out


def test_goal_names_the_plan_to_finish_first():
    out = goal.match("pytorch")
    assert out["matches"][0]["planId"] == "pytorch" and out["matches"][0]["first"] == "intro-python"
    out = goal.match("pytorch", done={"intro-python", "numpy"})
    assert out["matches"][0]["first"] == "neural-networks"
    assert "first" not in goal.match("pytorch", done={"intro-python", "numpy", "neural-networks"})["matches"][0]


def test_unknown_goal_is_not_confident():
    assert goal.match("something about cooking") == {"goal": "something about cooking", "matches": [],
                                                     "confident": False, "source": "catalog"}
    assert goal.match("")["matches"] == [] and goal.match(None)["goal"] == ""  # type: ignore[arg-type]


class _Res:
    def __init__(self, data):
        self.data = data


@pytest.mark.asyncio
async def test_suggest_skips_the_model_when_confident(monkeypatch):
    from server.coach import llm

    async def boom(**_k):
        raise AssertionError("no model call for a clear goal")

    monkeypatch.setattr(llm, "structured_call", boom)
    out = await goal.suggest("learn rust")
    assert out["source"] == "catalog" and out["matches"][0]["planId"] == "intro-rust"


@pytest.mark.asyncio
async def test_suggest_asks_the_guarded_model_and_keeps_only_real_ids(monkeypatch):
    from server.coach import llm

    seen = {}

    async def fake(**k):
        seen.update(k)
        return _Res({"planIds": ["made-up-plan", "intro-arduino", "intro-arduino", "intro-cad"]})

    monkeypatch.setattr(llm, "structured_call", fake)
    out = await goal.suggest("I want to understand how my car engine works")
    assert out["source"] == "model" and [m["planId"] for m in out["matches"]] == ["intro-arduino", "intro-cad"]
    assert seen["purpose"] == "plan_goal" and "opus" not in seen["model"]
    assert "<untrusted" in seen["user_text"] and "car engine" in seen["user_text"]


@pytest.mark.asyncio
async def test_suggest_keeps_catalog_answer_when_model_fails_or_is_off(monkeypatch):
    from server.coach import llm

    async def down(**_k):
        raise llm.CoachLLMError("offline", "offline")

    monkeypatch.setattr(llm, "structured_call", down)
    out = await goal.suggest("data")
    assert out["source"] == "catalog"

    async def empty(**_k):
        return _Res({"planIds": ["nope"]})

    monkeypatch.setattr(llm, "structured_call", empty)
    assert (await goal.suggest("draw diagrams"))["source"] == "catalog"
    assert (await goal.suggest("draw diagrams", allow_model=False))["matches"] == []


@pytest.mark.asyncio
async def test_suggest_offline_mode_makes_no_call(monkeypatch):
    """The real guarded client in offline mode (ORCH_STUBS=all): it refuses before any network."""
    monkeypatch.setenv("ORCH_STUBS", "all")
    out = await goal.suggest("something about cooking")
    assert out["source"] == "catalog" and out["matches"] == []
