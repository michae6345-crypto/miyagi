from __future__ import annotations

import pytest

from server.plans import catalog, proposal
from shared.contracts.events import PlanProposal


def test_a_shipped_playlist_proposes_its_catalog_plan_with_skills():
    pl = dict(catalog.playlists("intro-python")[0])
    got = proposal.from_playlist(pl, have=set())
    PlanProposal.model_validate(got)
    py = catalog.get("intro-python")
    assert got["source"] == "playlist" and got["tool"] == py["tool"] and got["fromPlans"] == ["intro-python"]
    assert [le["videoId"] for le in got["lessons"]] == [v["id"] for v in pl["videos"]]
    assert got["project"]["title"] == py["project"]["title"]
    grown = {g for le in got["lessons"] for g in le.get("grows") or []}
    assert grown and grown <= {s["id"] for s in py["skills"]} and {s["id"] for s in got["skills"]} == grown
    assert got["have"] == {"done": 0, "of": len(got["skills"])}
    one = next(iter(grown))
    assert proposal.from_playlist(pl, have={one})["have"]["done"] == 1


def test_an_unknown_playlist_proposes_plain_video_lessons():
    pl = {"playlistId": "PLxxxxxxxxxxxxxx", "title": "Zzz qqq", "channel": "", "videos": [
        {"id": "aaaaaaaaaa1", "title": "Part one", "seconds": 61}, {"id": "aaaaaaaaaa2", "title": "Part two", "seconds": None}]}
    got = proposal.from_playlist(pl)
    PlanProposal.model_validate(got)
    assert "tool" not in got and "skills" not in got and got["minutes"] == 2
    assert got["lessons"][0] == {"title": "Part one", "videoId": "aaaaaaaaaa1", "seconds": 61, "minutes": 2}


@pytest.mark.asyncio
async def test_a_goal_proposal_is_built_from_catalog_lessons_needs_first():
    got = await proposal.from_goal("I want to learn pandas", allow_model=False)
    PlanProposal.model_validate(got)
    assert got["source"] == "goal" and got["fromPlans"] == ["intro-python", "pandas"]
    assert got["lessons"][0]["from"] == {"planId": "intro-python", "index": 0}
    assert got["lessons"][-1]["from"]["planId"] == "pandas" and got["note"]
    assert got["minutes"] == sum(le["minutes"] for le in got["lessons"])
    done = await proposal.from_goal("I want to learn pandas", done={"intro-python"}, allow_model=False)
    assert done["fromPlans"] == ["pandas"]  # a finished plan is not proposed again
    py_skills = {g for le in catalog.get("pandas")["lessons"][:1] for g in le["grows"]}
    fewer = await proposal.from_goal("learn pandas", done={"intro-python"}, have=py_skills, allow_model=False)
    assert len(fewer["lessons"]) < len(done["lessons"])  # a lesson whose skills are had is left out


@pytest.mark.asyncio
async def test_a_goal_nothing_matches_proposes_nothing_without_the_model():
    assert await proposal.from_goal("qqq zzz xxyy", allow_model=False) is None


def test_accepted_lessons_keep_skips_and_drop_unbuildable_rows():
    p = PlanProposal.model_validate({"title": "T", "source": "playlist", "lessons": [
        {"title": "A", "videoId": "aaaaaaaaaa1", "skip": True}, {"title": "B", "videoId": "bad id"},
        {"title": "C", "goal": "Teach C", "grows": ["x.y"], "from": {"planId": "intro-c", "index": 2}}]})
    lessons, skipped = proposal.accepted_lessons(p)
    assert [le["title"] for le in lessons] == ["A", "C"] and skipped == {0}
    assert lessons[1] == {"title": "C", "goal": "Teach C", "grows": ["x.y"], "from": {"planId": "intro-c", "index": 2}}
