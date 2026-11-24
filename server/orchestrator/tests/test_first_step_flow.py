"""Step 1 first (lane eng-build-speed) through the REAL Session: the real server.lesson.build_lesson on the Claude
transcript path (every model call faked by speed_harness at 1/100 of the recorded latencies, no network) sends step 1
alone, the session starts the lesson on it (with or without the quick-start placeholder before it), and the rest of
the lesson arrives as lesson.updated with the same ids. No contract change: lesson.ready / lesson.updated as for E2's
long videos."""

import asyncio

import pytest

from server.lesson import builder
from server.lesson.tests import speed_harness as h
from server.orchestrator.tests.test_session import Rig


@pytest.fixture(autouse=True)
def _no_paid_calls(monkeypatch):
    from server.lesson.tests.conftest import block_network
    block_network(monkeypatch, http=False)  # real API clients raise; the harness fakes every model call


def _run(tmp_path, monkeypatch, quick_start_s: float):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "w"))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.setattr(builder, "QUICK_START_S", quick_start_s)
    (tmp_path / "w").mkdir(exist_ok=True)
    fakes = h.Fakes(h.scaled(h.PROFILE_10MIN, 0.01))
    rig = Rig(tmp_path / "w")
    rig.s.m.build_lesson = lambda url, goal, workdir, **kw: builder.build_lesson(url, goal, workdir, refresh=True, **kw)
    built: dict = {}
    real_build = builder.build_lesson

    async def keep(*a, **kw):
        built["graph"] = await real_build(*a, **kw)
        return built["graph"]

    monkeypatch.setattr(builder, "build_lesson", keep)
    with h.patched(fakes, fast=True, root=tmp_path / "cache"):
        async def go():
            await rig.s.learn_url(h.URL, skip_preflight=True)
            await rig.built()

        asyncio.run(go())
    return rig, built["graph"]


@pytest.mark.parametrize("quick_start_s", [0.05, 30.0], ids=["after-placeholder", "no-placeholder"])
def test_step_1_starts_the_lesson_and_the_rest_is_appended(tmp_path, monkeypatch, quick_start_s):
    rig, graph = _run(tmp_path, monkeypatch, quick_start_s)
    assert not rig.of("error"), rig.of("error")
    readies = [r for r in rig.of("lesson.ready") if not r["lesson"].get("provisional")]
    assert len(readies[0]["steps"]) == 1 and readies[0]["steps"][0]["id"] == "s1"  # step 1 alone, live
    assert readies[0]["lesson"].get("complete") is False
    if quick_start_s < 1:
        assert rig.of("lesson.ready")[0]["lesson"]["provisional"] is True  # the placeholder came first, then was replaced
    updates = rig.of("lesson.updated")
    assert [s["id"] for u in updates for s in u["steps"]] == ["s2", "s3", "s4", "s5", "s6"] and updates[-1]["complete"] is True
    assert [s["id"] for s in rig.s.steps] == [f"s{i}" for i in range(1, 7)]
    assert rig.s.graph["lesson"]["complete"] is True
    s1 = next(s for s in rig.s.steps if s["id"] == "s1")
    assert s1["checks"] == graph["steps"][0]["checks"] and s1["title"] == graph["steps"][0]["title"]
    assert rig.of("step.started")[0]["stepId"] == "s1"
