"""Live bug (ChatGPT-in-Python, 14:24, short video): the quick-start placeholder (no checks) ended, passed
with pending=true, showed "Building the next part…", and the real lesson never replaced it ("The lesson
build was interrupted"). Drives the REAL server.lesson.build_lesson (models faked, no network) through the
real Session."""

import asyncio
import json

import pytest

from server.lesson import builder, claude, gemini, transcript
from server.lesson.tests.test_builder import DRAFT, _good_adapt
from server.orchestrator.tests.test_session import Rig

URL = "https://www.youtube.com/watch?v=pGOyw_M1mNk"


@pytest.fixture(autouse=True)
def _no_paid_calls(monkeypatch):
    from server.lesson.tests.conftest import block_network
    block_network(monkeypatch, http=False)  # E4's tests use in-process HTTP; real API clients still raise
VM = {"title": "ChatGPT in Python for Beginners", "duration_s": 864,
      "chapters": [{"start": 0, "title": "Step By Step"}, {"start": 38, "title": "Get an API key"},
                   {"start": 300, "title": "Write the chat loop"}, {"start": 700, "title": "Wrap up"}]}


@pytest.fixture
def lesson_fakes(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "w"))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.setenv("LESSON_ENGINE", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-placeholder")  # Gemini is opt-in (D1): engine AND a key; faked below
    monkeypatch.setenv("LESSON_GEMINI_USAGE_FILE", str(tmp_path / "usage.json"))
    monkeypatch.setattr(builder, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(builder, "RAW_DIR", tmp_path / "cache" / "raw")
    monkeypatch.setattr(builder, "QUICK_START_S", 0.05)
    calls = {"gemini": 0}

    async def slow_gemini(url, goal, **kw):
        calls["gemini"] += 1
        await asyncio.sleep(0.6)  # the placeholder is up and its clip ends meanwhile
        return json.loads(json.dumps(DRAFT))

    async def adapt(goal, steps, summary, feedback=None):
        return _good_adapt()

    async def meta(vid):
        return {"video_id": vid, "title": VM["title"], "description": "", "length_s": 864, "chapters": []}

    async def no_goal(goal, meta):
        return {"score": None, "note": "test"}

    from server.lesson import links, progressive
    monkeypatch.setattr(gemini, "watch_video", slow_gemini)
    monkeypatch.setattr(claude, "adapt_checks", adapt)
    monkeypatch.setattr(transcript, "fetch_metadata", meta)
    monkeypatch.setattr(progressive, "goal_match", no_goal)

    async def ok(client, url):
        return True

    monkeypatch.setattr(links, "_resolves", ok)
    return calls


def test_placeholder_end_then_real_lesson_replaces_it_without_interruption(tmp_path, lesson_fakes):
    rig = Rig(tmp_path / "w")
    (tmp_path / "w").mkdir(exist_ok=True)
    rig.s.m.build_lesson = lambda url, goal, workdir, **kw: builder.build_lesson(url, goal, workdir, refresh=True, **kw)

    async def go():
        build = asyncio.ensure_future(rig.s.learn_url(URL))
        for _ in range(100):  # wait for the placeholder
            await asyncio.sleep(0.02)
            if rig.s.graph and rig.s.graph["lesson"].get("provisional") and rig.s.step:
                break
        assert rig.s.graph["lesson"]["provisional"] and rig.s.step["provisional"]
        await rig.s.video_state(rig.s.step["video"]["end"] + 1, True)  # the placeholder's clip ends
        await asyncio.sleep(0.05)
        await build  # returns once the placeholder is live (perf.until_loaded); the build runs on
        await rig.built()

    asyncio.run(go())
    errors = [e["message"] for e in rig.of("error")]
    assert not errors, errors
    assert not any("next part" in (c.get("title") or "") for c in rig.of("card")), rig.of("card")
    assert not any(p.get("stepId") == "s1" and p.get("pending") for p in rig.of("step.passed"))  # placeholder never pends
    readies = rig.of("lesson.ready")
    assert readies[0]["lesson"]["provisional"] is True and readies[-1]["lesson"]["provisional"] is False
    assert rig.s.step and rig.s.step["id"] == "s1" and not rig.s.step.get("provisional")  # the REAL s1 runs
    assert rig.of("step.started")[-1]["stepId"] == "s1"


def test_no_extend_while_building_or_for_a_placeholder_or_a_lesson_without_parts(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    (tmp_path).mkdir(exist_ok=True)
    rig = Rig(tmp_path)
    started = []

    async def extend_lesson(graph, on_update=None):
        started.append(graph["lesson"].get("id"))
        done = json.loads(json.dumps(graph))
        done["lesson"]["complete"] = True  # the last part: no further extends
        return done

    rig.s.m.extend_lesson = extend_lesson
    rig.s.m.lesson_needs_more = lambda g, cur: True
    from server.orchestrator import stubs
    base = stubs.load_fixture_lesson()

    def g(**lesson):
        x = json.loads(json.dumps(base))
        x["lesson"].update(lesson)
        return x

    async def go():
        await rig.s.load_graph(g(complete=False))  # no parts: a short video's provisional/partial graph
        rig.s._maybe_extend()
        await rig.s.load_graph(g(complete=False, provisional=True, parts={"total": 3, "list": [{"status": "pending"}]}))
        rig.s._maybe_extend()
        await rig.s.load_graph(g(complete=False, parts={"total": 3, "list": [{"status": "pending"}]}))
        rig.s._build_task = asyncio.ensure_future(asyncio.sleep(1))  # the main build is still running
        assert rig.s._more_in_flight() is True
        rig.s._maybe_extend()
        rig.s._build_task.cancel()
        rig.s._build_task = None
        rig.s._maybe_extend()  # a real lazily built long video, nothing building: now it extends
        await rig.settle()

    asyncio.run(go())
    assert len(started) == 1
