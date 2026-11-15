"""Resume-or-new. Run from the repo root:  python -m pytest server/sessions -q"""

from __future__ import annotations

import asyncio
import json

import pytest

from server import sessions
from server.orchestrator import stubs
from server.orchestrator.hub import Hub
from server.orchestrator.modules import Modules
from server.orchestrator.session import LessonSession
from server.sessions import Resumer, resume_offer, store
from shared.contracts.events import engine_message, parse_app_message


class WallClock:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(d))
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "work"))
    (tmp_path / "work").mkdir()
    monkeypatch.delenv("DEMO", raising=False)
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY",
              "TIGER_DATABASE_URL"):  # cost freeze: an accidental live call fails at once, for free
        monkeypatch.setenv(k, "")
    return d


def state_dir_of():
    return sessions.state_dir()


class Engine:
    """A fresh engine process: strict hub + session + resumer (a restart = a new Engine on the same disk)."""

    def __init__(self) -> None:
        self.hub = Hub(strict=True)
        self.clock = WallClock()
        self.s = LessonSession(self.hub.emit, Modules(demo=False, force_stubs="all"), idle_gate_s=5,
                               advance_delay_s=0, metric_eval_s=0, result_stagger_s=0, build_tick_s=0.01,
                               seen_interval_s=0)
        self.r = Resumer(self.s, clock=self.clock)

    async def settle(self) -> None:
        await asyncio.sleep(0)
        await self.s.drain()

    def since(self, mark: int) -> list[dict]:
        return list(self.hub.history)[mark:]

    def mark(self) -> int:
        return len(self.hub.history)


def test_save_load_clear_roundtrip_is_atomic(state_dir):
    assert sessions.load() is None
    graph = {"lesson": {"id": "L1", "title": "T"}, "steps": [{"id": "s1", "title": "a"}]}
    sessions.save({"lessonId": "L1", "title": "T", "stepIndex": 0, "stepCount": 1, "videoT": 12.5}, graph)
    st = sessions.load()
    assert st["lessonId"] == "L1" and st["videoT"] == 12.5 and st["lastActiveAt"] and st["version"] == 1
    assert sessions.load_graph(st) == graph
    assert sorted(p.name for p in state_dir.iterdir()) == ["current.json", "graph-L1.json"]  # no temp files left
    assert st["graphFile"] == "graph-L1.json"
    sessions.clear()
    assert sessions.load() is None and sessions.load_graph() is None
    sessions.clear()  # clearing nothing is fine


def test_corrupt_or_foreign_files_read_as_none(state_dir):
    state_dir.mkdir(parents=True)
    (state_dir / "current.json").write_text("{not json")
    assert sessions.load() is None
    (state_dir / "current.json").write_text(json.dumps({"lessonId": "L1"}))  # no step index
    assert sessions.load() is None
    sessions.save({"lessonId": "L1", "stepIndex": 0, "stepCount": 2}, {"lesson": {"id": "OTHER"}, "steps": [{"id": "x"}]})
    assert sessions.load_graph(sessions.load()) is None  # cached graph belongs to another lesson
    (state_dir / "current.graph.json").write_text("garbage")
    assert sessions.load_graph() is None


def test_resume_offer_card_matches_the_contract():
    card = resume_offer({"lessonId": "L", "title": "PINNs for convection", "stepIndex": 2, "stepCount": 7,
                         "lastActiveAt": 1000.0}, now=1000.0 + 12 * 60 + 5)
    assert card["kind"] == "resume" and card["actions"] == ["resume", "end_lesson"]
    assert card["body"] == "PINNs for convection · step 3 of 7 · 12 min ago"
    engine_message("card", card)
    assert parse_app_message({"type": "action", "payload": {"kind": "end_lesson"}}).payload.kind == "end_lesson"
    assert parse_app_message({"type": "action", "payload": {"kind": "resume"}}).payload.kind == "resume"
    assert sessions.ago(30) == "just now" and sessions.ago(7200) == "2 h ago" and sessions.ago(86400 * 3) == "3 days ago"


def test_progress_saved_on_step_and_video_and_in_memory_card_uses_it():
    e = Engine()

    async def go():
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        await e.s.goto_step(1)
        await e.settle()
        n = len(e.s.steps)
        seg = e.s._segment(e.s.step)
        await e.s.video_state(seg["start"] + 7, True)
        st = sessions.load()
        assert st["stepIndex"] == 1 and st["videoT"] == seg["start"] + 7 and st["passedSteps"] == [e.s.steps[0]["id"]] and st["mode"] == "video"

        e.clock.t += 600  # the app was away 10 min; E4's engine asks to resume (lesson frozen in memory)
        msgs = e.s.snapshot(ask_resume=True)
        assert [t for t, _ in msgs] == ["video.pause", "card"] and e.s.awaiting_resume
        before = (state_dir_of() / "current.json").read_text()
        assert e.r.save_now() is None  # frozen: nothing may overwrite the save (disconnect, stop, player)
        await e.s.video_state(seg["start"] + 30, True)
        assert (state_dir_of() / "current.json").read_text() == before
        assert msgs[1][1]["body"].endswith("step 2 of %d · 10 min ago" % n)
        for t, p in msgs:
            engine_message(t, p)
        m = e.mark()
        await e.s.action("resume")  # in memory: the session's own resume
        await e.settle()
        assert not e.s.awaiting_resume and e.s.idx == 1
        assert e.since(m)[-1] == {"type": "status", "payload": {"state": "watching"}}

    run(go())


def test_resume_after_engine_restart_restores_step_and_video():
    first = Engine()

    async def before():
        await first.s.load_graph(stubs.load_fixture_lesson())
        await first.settle()
        await first.s.goto_step(2)
        await first.settle()
        seg = first.s._segment(first.s.step)
        await first.s.video_state(seg["start"] + 20, False)
        return seg

    seg = run(before())

    second = Engine()  # engine restarted: nothing in memory
    second.clock.t = first.clock.t + 3600

    async def after():
        msgs = second.s.snapshot()  # what main.py's ws_endpoint sends a new connection
        assert [t for t, _ in msgs] == ["spotlight", "video.pause", "status", "card"]
        assert msgs[2][1] == {"state": "idle"} and "step 3 of" in msgs[3][1]["body"]
        assert msgs[3][1]["body"].endswith("1 h ago")
        for t, p in msgs:
            engine_message(t, p)
        m = second.mark()
        await second.s.action("resume")  # the card's button
        await second.settle()
        evs = second.since(m)
        types = [e["type"] for e in evs]
        assert types[0] == "lesson.ready"
        started = [e["payload"] for e in evs if e["type"] == "step.started"]
        assert len(started) == 1 and started[0]["index"] == 2  # no detour through step 0
        assert started[0]["video"] == seg  # the video lesson gets its segment back
        seeks = [e["payload"] for e in evs if e["type"] == "video.seek"]
        assert seeks[-1] == {"t": seg["start"] + 20, "play": True}
        assert second.s.idx == 2 and second.s.phase == "active"
        assert ("status", {"state": "watching"}) in [(e["type"], e["payload"]) for e in evs]

    run(after())


def test_end_lesson_clears_the_save_and_new_learn_too():
    e = Engine()

    async def go():
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        assert sessions.load() is not None
        await e.s.end_lesson("end_lesson")
        assert sessions.load() is None and sessions.load_graph() is None
        assert e.s.snapshot() == [("status", {"state": "idle"})]

        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        assert sessions.load() is not None
        await e.s.learn("something else")  # a new lesson ends the old one
        await e.settle()
        assert sessions.load() is None

    run(go())


def test_passing_moves_the_save_forward_and_finishing_clears_it():
    e = Engine()

    async def go():
        await e.s.load_graph(stubs.load_fixture_lesson())
        await e.settle()
        n = len(e.s.steps)
        await e.s._pass_step()  # quit right after a pass -> resume on the next step
        assert sessions.load()["stepIndex"] == 1
        await e.settle()
        await e.s.goto_step(n - 1)
        await e.settle()
        await e.s._pass_step()
        assert sessions.load() is None  # lesson complete

    run(go())


def test_resume_with_nothing_saved_is_a_clear_error():
    e = Engine()

    async def go():
        m = e.mark()
        assert not await e.r.resume()
        assert [x["type"] for x in e.since(m)] == ["error", "status"]
        assert e.s.snapshot() == [("status", {"state": "idle"})]

    run(go())


def _text_lesson_7() -> dict:
    g = stubs.text_lesson(stubs.load_fixture_lesson(), goal="teach me PINNs")
    extra = json.loads(json.dumps(g["steps"][-1]))
    extra["id"], extra["index"], extra["title"] = "s7-extra", len(g["steps"]), "One more practice step"
    g["steps"].append(extra)
    assert len(g["steps"]) == 7 and g["lesson"]["mode"] == "lesson"
    return g


def _no_builds(e: Engine) -> list[str]:
    calls: list[str] = []
    for name in ("build_lesson", "build_text_lesson", "extend_lesson"):
        async def boom(*_a, _n=name, **_k):
            calls.append(_n)
            raise AssertionError(f"{_n} called on resume")
        setattr(e.s.m, name, boom)
    return calls


def test_text_lesson_survives_restart_step_3_of_7_with_zero_build_calls():
    full = _text_lesson_7()
    first_part = json.loads(json.dumps(full))
    first_part["steps"] = first_part["steps"][:4]
    first_part["lesson"]["complete"] = False  # "Just teach me" arrives in parts
    e1 = Engine()

    async def before():
        await e1.s.load_graph(first_part)
        await e1.settle()
        assert len(sessions.load_graph()["steps"]) == 4  # saved as soon as lesson.ready went out
        await e1.s._extend_lesson(full, True)  # the rest of the lesson arrives
        assert len(sessions.load_graph()["steps"]) == 7  # lesson.updated rewrites the saved graph
        await e1.s._pass_step()  # step 1 passed
        await e1.settle()
        await e1.s._pass_step(skipped=True)  # step 2 skipped
        await e1.settle()
        assert e1.s.idx == 2
        st = sessions.load()
        assert (st["stepIndex"], st["stepCount"], st["mode"]) == (2, 7, "lesson")
        assert st["passedSteps"] == [full["steps"][0]["id"]] and st["skippedSteps"] == [full["steps"][1]["id"]]

    run(before())

    e2 = Engine()  # engine restart: nothing in memory, a builder that must not be called
    calls = _no_builds(e2)

    async def after():
        msgs = e2.s.snapshot()
        card = msgs[-1][1]
        assert card["kind"] == "resume" and card["actions"] == ["resume", "end_lesson"]
        assert card["body"].startswith(full["lesson"]["title"] + " · step 3 of 7")
        m = e2.mark()
        await e2.s.action("resume")
        await e2.settle()
        evs = e2.since(m)
        types = [x["type"] for x in evs]
        assert types[0] == "lesson.ready" and len(evs[0]["payload"]["steps"]) == 7
        started = [x["payload"] for x in evs if x["type"] == "step.started"]
        assert [p["stepId"] for p in started] == [full["steps"][2]["id"]]
        assert not any(t.startswith("video.") for t in types)  # a text lesson has no player
        assert calls == [] and e2.s.idx == 2 and e2.s.lesson_mode
        assert e2.s.skipped_steps == [full["steps"][1]["id"]]  # the session knows what was skipped again
        st = sessions.load()  # the restored session keeps saving, lists intact
        assert st["stepIndex"] == 2 and st["skippedSteps"] == [full["steps"][1]["id"]]

    run(after())


def test_end_lesson_on_the_resume_card_clears_and_goes_idle():
    e1 = Engine()
    run(e1.s.load_graph(_text_lesson_7()))
    e2 = Engine()

    async def go():
        assert e2.s.snapshot()[-1][0] == "card"
        await e2.s.action("end_lesson")
        assert sessions.load() is None and e2.s.snapshot() == [("status", {"state": "idle"})]

    run(go())


def _save_text_lesson_at_step_2():
    """Michael's case: a "Just teach me" lesson, learner on s2 (index 1) when the engine restarts."""
    lesson = _text_lesson_7()
    e1 = Engine()

    async def go():
        await e1.s.load_graph(lesson)
        await e1.settle()
        await e1.s._pass_step()
        await e1.settle()
        assert e1.s.idx == 1

    run(go())
    st = sessions.load()
    assert (st["stepIndex"], st["stepId"]) == (1, lesson["steps"][1]["id"])
    return lesson, st


def test_restart_connect_state_then_resume_starts_the_saved_step(tmp_path, monkeypatch, state_dir):
    """save at s2 -> engine restart -> app connects (and leaves, and comes back) -> /state still s2 ->
    resume starts s2. Real main.app; stub modules and no workspace (no VS Code, no API calls)."""
    from fastapi.testclient import TestClient

    from server.orchestrator import main

    lesson, saved = _save_text_lesson_at_step_2()
    files = {p.name: p.read_bytes() for p in state_dir.iterdir()}
    eng = main.Engine()  # the restarted engine process
    eng.recorder.enabled = False
    eng.session.workspace = None
    eng.session.m = eng.modules = Modules(demo=False, force_stubs="all")
    calls = []
    for name in ("build_lesson", "build_text_lesson", "extend_lesson"):
        async def boom(*_a, _n=name, **_k):
            calls.append(_n)
            raise AssertionError(_n)
        setattr(eng.session.m, name, boom)
    monkeypatch.setattr(main, "engine", eng)
    s2 = lesson["steps"][1]["id"]
    with TestClient(main.app) as client:
        for _ in range(2):  # connect, leave, connect again: nothing is answered yet
            with client.websocket_connect("/") as ws:
                msgs = [ws.receive_json() for _ in range(4)]
                assert [m["type"] for m in msgs] == ["spotlight", "video.pause", "status", "card"]
                assert " · step 2 of 7" in msgs[3]["payload"]["body"]
        st = client.get("/state").json()
        assert st["phase"] == "awaiting_resume" and st["saved"]["stepId"] == s2 and st["saved"]["stepIndex"] == 1
        assert {p.name: p.read_bytes() for p in state_dir.iterdir()} == files  # not one byte rewritten
        with client.websocket_connect("/") as ws:
            [ws.receive_json() for _ in range(4)]
            ws.send_json({"type": "action", "payload": {"kind": "resume"}})
            got = []
            while not any(m["type"] == "step.started" for m in got):
                got.append(ws.receive_json())
            assert [m["payload"]["stepId"] for m in got if m["type"] == "step.started"] == [s2]
        st = client.get("/state").json()
        assert st["stepId"] == s2 and st["phase"] == "active"
    assert calls == []
    assert sessions.load()["stepId"] == s2


def test_same_lesson_loaded_again_after_restart_continues_at_the_saved_step():
    lesson, _ = _save_text_lesson_at_step_2()
    e2 = Engine()
    fresh = json.loads(json.dumps(lesson))  # e.g. a "Just teach me" rebuild that hit the lesson cache

    async def go():
        assert e2.s.snapshot()[-1][0] == "card"
        await e2.s.load_graph(fresh)
        await e2.settle()
        assert e2.s.idx == 1 and sessions.load()["stepIndex"] == 1

    run(go())


def test_another_lesson_replaces_the_pending_save():
    _save_text_lesson_at_step_2()
    e2 = Engine()

    other = stubs.load_fixture_lesson()
    other["lesson"]["id"] = "another-lesson"

    async def go():
        await e2.s.load_graph(other)
        await e2.settle()
        st = sessions.load()
        assert st["lessonId"] == "another-lesson" and st["stepIndex"] == 0
        assert sessions.load_graph(st)["lesson"]["id"] == "another-lesson"

    run(go())


def test_graph_and_progress_commit_together(state_dir):
    g1 = {"lesson": {"id": "L1"}, "steps": [{"id": "a", "title": "a"}]}
    g2 = {"lesson": {"id": "L2"}, "steps": [{"id": "b", "title": "b"}]}
    sessions.save({"lessonId": "L1", "stepIndex": 0, "stepCount": 1}, g1)
    store._write_atomic(state_dir / store._graph_name("L2"), g2)  # crash after the graph, before current.json
    assert sessions.load()["lessonId"] == "L1" and sessions.load_graph(sessions.load()) == g1
    sessions.save({"lessonId": "L2", "stepIndex": 0, "stepCount": 1}, g2)
    assert sorted(p.name for p in state_dir.iterdir()) == ["current.json", "graph-L2.json"]
    sessions.clear()
    assert list(state_dir.iterdir()) == []


def test_legacy_graph_file_still_resumes(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    g = {"lesson": {"id": "L1"}, "steps": [{"id": "a", "title": "a"}]}
    (state_dir / "current.graph.json").write_text(json.dumps(g))
    (state_dir / "current.json").write_text(json.dumps({"lessonId": "L1", "stepIndex": 0, "stepCount": 1}))
    assert sessions.load_graph(sessions.load()) == g
