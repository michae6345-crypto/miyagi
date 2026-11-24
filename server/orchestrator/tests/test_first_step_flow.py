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


def test_the_side_field_for_the_workspace_never_reaches_the_app(tmp_path, monkeypatch):
    import json

    rig, _graph = _run(tmp_path, monkeypatch, 30.0)
    assert "upcomingSteps" not in json.dumps(rig.events)


def test_a_late_update_from_an_ended_build_never_loads(tmp_path, monkeypatch):
    """Blocker 2 (session side): an update that arrives after the build was ended (End, a new learn) is dropped."""
    import json

    from server.orchestrator import stubs

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "w"))
    (tmp_path / "w").mkdir(exist_ok=True)
    rig = Rig(tmp_path / "w")
    held = {}

    async def build(url, goal, workdir, on_update=None, **kw):
        held["on_update"] = on_update
        await asyncio.sleep(60)  # still building when the learner ends it

    rig.s.m.build_lesson = build

    async def go():
        task = asyncio.ensure_future(rig.s.learn_url("https://www.youtube.com/watch?v=abcdefghijk", skip_preflight=True))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if "on_update" in held:
                break
        await rig.s.end_lesson("end_lesson")
        await asyncio.gather(task, return_exceptions=True)
        mark = rig.mark()
        g = json.loads(json.dumps(stubs.load_fixture_lesson()))
        g["lesson"]["complete"] = False
        await held["on_update"](g, False)  # step 1 of the abandoned build, arriving late
        await rig.settle()
        return rig.since(mark)

    late = asyncio.run(go())
    assert not [e for e in late if e["type"] in ("lesson.ready", "lesson.updated", "step.started")]
    assert rig.s.graph is None


@pytest.mark.parametrize("where", ["prepare", "hold"])
def test_real_step_1_arriving_while_the_placeholder_still_loads(tmp_path, monkeypatch, where):
    """Blocker A: the quick-start placeholder's on_update is still preparing the folder (a Claude call, up to ~25 s) or
    in the "ready" hold when the real step 1 arrives (~15-20 s now). The placeholder lands, then the real lesson
    replaces it; the lesson never stays unloaded."""
    import time

    from server.orchestrator import workspace as wsmod

    real_prepare = wsmod.prepare

    def slow_prepare(graph, goal):
        if where == "prepare":
            time.sleep(0.5)  # in asyncio.to_thread, like the real scaffold call
        return real_prepare(graph, goal)

    monkeypatch.setattr(wsmod, "prepare", slow_prepare)
    if where == "hold":
        monkeypatch.setattr(Rig, "__init__", _with_hold(Rig.__init__, 0.5))
    rig, graph = _run(tmp_path, monkeypatch, 0.05)
    readies = rig.of("lesson.ready")
    assert readies[0]["lesson"]["provisional"] is True and not readies[-1]["lesson"].get("provisional")
    assert rig.s.graph is not None and [s["id"] for s in rig.s.steps] == [f"s{i}" for i in range(1, 7)]
    assert rig.s.graph["lesson"]["complete"] is True and not rig.of("error")
    assert next(s for s in rig.s.steps if s["id"] == "s1")["checks"] == graph["steps"][0]["checks"]


def _with_hold(init, hold_s):
    def patched(self, *a, **k):
        init(self, *a, **k)
        self.s.ready_hold_s = hold_s
    return patched


def test_the_session_keeps_the_builders_app_or_code_choice(tmp_path, monkeypatch):
    """Blocker B: an app-titled video whose code starts in step 2: the builder decided "code lesson" on the whole
    lesson, so the session's load of step 1 alone never turns it into an app lesson."""
    import copy
    import json
    from pathlib import Path

    fx = Path(__file__).resolve().parents[2] / "workspace" / "tests" / "fixtures" / "autocad_toy_car.json"
    g = json.loads(fx.read_text(encoding="utf-8"))
    g["steps"] = g["steps"][:1]
    g["lesson"]["complete"] = False
    g.setdefault("build", {})["firstStep"] = True
    g["lesson"].pop("app", None)
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "w"))
    (tmp_path / "w").mkdir(exist_ok=True)
    rig = Rig(tmp_path / "w")
    checks = copy.deepcopy(g["steps"][0]["checks"])
    asyncio.run(rig.s.load_graph(g))
    assert "app" not in rig.s.graph["lesson"] and rig.s.steps[0]["checks"] == checks
    plain = json.loads(fx.read_text(encoding="utf-8"))  # without the builder's choice: the session still adapts it
    rig2 = Rig(tmp_path / "w")
    asyncio.run(rig2.s.load_graph(plain))
    assert rig2.s.graph["lesson"]["app"]["tool"] == "autocad"
