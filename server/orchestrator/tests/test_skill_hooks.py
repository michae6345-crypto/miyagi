"""Skill tree hooks in the lesson session: Show me / Do it for me / a third hint make the step's pass assisted, an
unassisted pass on two days masters the step's catalog skills, step.passed carries key / assisted / skillIds / proofId,
a skip misses a due review, and a proof of the learner's own file is kept. Offline: stub modules, no model, no network."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from server.orchestrator import skill_hooks, stubs
from server.orchestrator.modules import Modules
from server.orchestrator.session import LessonSession
from server.skilltree import ledger, proofs
from shared.contracts import events as contract

UTC = timezone.utc
EXTRUDE_GOAL = "Teach Blender inset and extrude by hollowing a cylinder into the cup of a mug."


def t(day: int, hour: int = 10) -> float:
    return datetime(2026, 11, day, hour, tzinfo=UTC).timestamp()


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MIYAGI_SYSTEM_STATUS", "0")
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "work"))
    (tmp_path / "work").mkdir()
    return tmp_path


def _python_graph() -> dict:
    g = stubs.load_fixture_lesson()
    g["lesson"] = {**g["lesson"], "id": "les-py", "title": "Functions practice", "goal": "practice functions",
                   "libraries": {}}
    for st in g["steps"]:
        st.pop("skillIds", None)
    g["steps"][0].update({"title": "Write the add function", "file": "app.py", "code": "def add(a, b):\n    return a + b"})
    return g


def _session() -> tuple[LessonSession, list]:
    sent: list = []

    async def emit(type_, payload=None):
        sent.append((type_, payload))

    s = LessonSession(emit, Modules(demo=False, force_stubs="all"), idle_gate_s=5, advance_delay_s=0, metric_eval_s=0,
                      result_stagger_s=0, build_tick_s=0.01, seen_interval_s=0)
    s.workspace = None
    return s, sent


def test_catalog_lesson_tags_from_its_goal():
    s = SimpleNamespace(graph={"lesson": {"goal": EXTRUDE_GOAL}, "steps": [{"id": "s1", "title": "Inset the top"}]},
                        steps=[{"id": "s1", "title": "Inset the top"}])
    assert skill_hooks.tags(s)["s1"] == ["bl.extrude"]


def test_assist_rule_show_me_do_it_for_me_or_the_third_hint():
    s = SimpleNamespace(graph={"lesson": {"id": "A"}}, step={"id": "s1"})
    skill_hooks.note_assist(s, "explain")  # explaining the idea is not doing it for them
    skill_hooks.note_assist(s, "hint")
    skill_hooks.note_assist(s, "hint")
    assert not skill_hooks.assisted(s, "s1")
    skill_hooks.note_assist(s, "hint")
    assert skill_hooks.assisted(s, "s1")
    s.step = {"id": "s2"}
    skill_hooks.note_assist(s, "show_me")
    s.step = {"id": "s3"}
    skill_hooks.note_assist(s, "apply_fix")
    assert skill_hooks.assisted(s, "s2") and skill_hooks.assisted(s, "s3")
    s.graph = {"lesson": {"id": "B"}}  # a new lesson starts clean
    assert not skill_hooks.assisted(s, "s1")


def test_show_me_counts_only_once_something_is_shown(state):
    async def press(shown: bool) -> bool:
        s, _sent = _session()
        await s.load_graph(_python_graph())
        await s.drain()
        s.screen_down_reason = lambda include_ax=False: None
        s._lesson_window_hidden = lambda: False
        s._can_see = lambda: False
        s.m.has_pointing = lambda: False

        async def where(step):
            return shown

        s._show_where = where
        await s._action("show_me")
        await s.drain()
        return skill_hooks.assisted(s, s.step["id"])

    assert asyncio.run(press(False)) is False  # "Nothing to point at": the pass stays unassisted
    assert asyncio.run(press(True)) is True  # the box went up: assisted


def test_record_keeps_a_proof_from_the_learners_file_inside_the_lesson_folder(state):
    work = state / "work"
    (work / "app.py").write_text("import os\n\ndef add(a, b):\n    return a + b\n")
    (work / ".env").write_text("KEY=1")
    step = {"id": "s1", "title": "Add", "file": "app.py", "code": "def add(a, b):\n    return a + b"}
    got = skill_hooks.record(step, ["py.functions"], assisted=False, skipped=False, lesson={"id": "L", "title": "Fns"},
                             workdir=str(work), now=t(1))
    rec = proofs.get(got["proofId"])
    assert rec["text"] == "def add(a, b):\n    return a + b" and rec["file"] == "app.py" and rec["line"] == 3
    assert rec["key"] == "L:s1" and rec["lessonTitle"] == "Fns"
    assert ledger.skill_row("py.functions", now=t(1))["state"] == "practicing"
    assert skill_hooks._read_file(str(work), "../outside.py") == (None, None)
    assert skill_hooks._read_file(str(work), ".env")[0] is None
    # an assisted pass keeps no proof (it is not only the learner's own work) and never counts toward mastery
    got = skill_hooks.record(step, ["py.functions"], assisted=True, skipped=False, lesson={"id": "L"}, workdir=str(work), now=t(2))
    assert "proofId" not in got and len(proofs.for_skill("py.functions")) == 1
    assert ledger.skill_row("py.functions", now=t(2))["unassistedDays"] == 1


def test_skip_misses_only_a_due_review(state):
    ledger.record_pass(["bl.edit"], now=t(1), tz=UTC)
    ledger.record_pass(["bl.edit"], now=t(2), tz=UTC)
    step = {"id": "s"}
    assert skill_hooks.record(step, ["bl.edit"], assisted=False, skipped=True, lesson=None, workdir=None, now=t(3)) == {"events": []}
    got = skill_hooks.record(step, ["bl.edit"], assisted=False, skipped=True, lesson=None, workdir=None, now=t(9))
    assert got["events"][0]["kind"] == "review_missed"
    assert skill_hooks.record({"id": "r", "kind": "read"}, ["bl.edit"], assisted=False, skipped=False,
                              lesson=None, workdir=None, now=t(9)) == {"events": []}


def test_session_step_passed_carries_the_v4_fields_and_masters_on_day_two(state, monkeypatch):
    clock = {"now": t(1)}
    real = ledger.record_pass
    monkeypatch.setattr(ledger, "record_pass", lambda ids, **k: real(ids, **{**k, "now": clock["now"], "tz": UTC}))
    (state / "work" / "app.py").write_text("def add(a, b):\n    return a + b\n")

    async def lesson(hints: int) -> tuple[LessonSession, dict]:
        s, sent = _session()
        await s.load_graph(_python_graph())
        await s.drain()
        s.workdir = str(state / "work")
        for _ in range(hints):
            await s._action("hint")
            await s.drain()
        await s._pass_step()
        await s.drain()
        (passed,) = [p for type_, p in sent if type_ == "step.passed"]
        contract.validate_engine_payload("step.passed", passed)
        return s, passed

    _, passed = asyncio.run(lesson(hints=3))
    assert passed["key"] == "les-py:s1" and passed["assisted"] is True and passed["skillIds"] == ["py.functions"]
    assert "proofId" not in passed
    assert ledger.skill_row("py.functions", now=t(1), tz=UTC)["unassistedDays"] == 0
    _, passed = asyncio.run(lesson(hints=1))  # one hint is a nudge, not the answer
    assert passed["assisted"] is False and proofs.get(passed["proofId"])["kind"] == "code"
    clock["now"] = t(2)
    s, passed = asyncio.run(lesson(hints=0))
    assert s.skill_events[0]["kind"] == "mastered"
    assert ledger.skill_row("py.functions", now=t(2), tz=UTC)["state"] == "mastered"


def test_session_hook_never_breaks_the_pass(state, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(skill_hooks, "record", boom)

    async def go() -> list:
        s, sent = _session()
        await s.load_graph(_python_graph())
        await s.drain()
        await s._pass_step()
        await s.drain()
        return sent

    (passed,) = [p for type_, p in asyncio.run(go()) if type_ == "step.passed"]
    assert passed["stepId"] == "s1" and passed["key"] == "les-py:s1" and passed["skillIds"] == ["py.functions"]


def test_run_it_for_me_on_a_run_step_makes_the_pass_assisted(state, monkeypatch):
    """The engine ran the step's command: Run it for me (run_command), Do it for me on a run step and the Yes on "Run
    this command?" all reach _run_for_me. The pass is assisted: no proof of the engine's output, no mastery."""
    clock = {"now": t(1)}
    real = ledger.record_pass
    monkeypatch.setattr(ledger, "record_pass", lambda ids, **k: real(ids, **{**k, "now": clock["now"], "tz": UTC}))
    (state / "work" / "app.py").write_text("def add(a, b):\n    return a + b\n")

    async def lesson(direct: bool) -> dict:
        s, sent = _session()
        g = _python_graph()
        g["steps"][0]["run_command"] = "python app.py"
        await s.load_graph(g)
        await s.drain()
        s.workdir = str(state / "work")
        if direct:  # the apply_fix / confirm re-entry paths call _run_for_me without a run_command action
            await s._run_for_me(s.step)
        else:
            await s._action("run_command")
        await s.drain()
        await s._pass_step()
        await s.drain()
        (passed,) = [p for type_, p in sent if type_ == "step.passed"]
        contract.validate_engine_payload("step.passed", passed)
        return passed

    passed = asyncio.run(lesson(direct=False))
    assert passed["assisted"] is True and "proofId" not in passed
    clock["now"] = t(2)
    passed = asyncio.run(lesson(direct=True))
    assert passed["assisted"] is True and "proofId" not in passed
    row = ledger.skill_row("py.functions", now=t(2), tz=UTC)
    assert row["state"] != "mastered" and row["unassistedDays"] == 0
    assert proofs.for_skill("py.functions") == []


def test_a_review_pass_is_recorded_under_the_replayed_lessons_key(state):
    from server.skilltree import graph

    work = state / "work"
    (work / "app.py").write_text("def add(a, b):\n    return a + b\n")
    step = {"id": "s1", "title": "Add", "file": "app.py", "code": "def add(a, b):\n    return a + b"}
    skill_hooks.record(step, ["py.functions"], assisted=False, skipped=False, lesson={"id": "L", "title": "Fns"},
                       workdir=str(work), now=t(1))
    review = {"id": "review-py-functions-L", "title": "Review: Functions",
              "review": {"key": "skilltree::py.functions", "skillId": "py.functions", "lessonId": "L", "lessonTitle": "Fns"}}
    got = skill_hooks.record(step, ["py.functions"], assisted=False, skipped=False, lesson=review, workdir=str(work),
                             now=t(2))
    row = ledger.load()["py.functions"]
    assert [p["lessonId"] for p in row["passes"]] == ["L", "L"] and row["passes"][1]["lessonTitle"] == "Fns"
    assert proofs.get(got["proofId"])["key"] == "L:s1"
    steps = graph._steps("py.functions", row, None, UTC)
    assert [s["key"] for s in steps] == ["L:s1"]


def test_tags_cache_is_keyed_on_the_lesson_and_step_ids_not_the_graph_address():
    s = SimpleNamespace(graph={"lesson": {"id": "A", "goal": EXTRUDE_GOAL}, "steps": [{"id": "s1", "title": "Inset"}]},
                        steps=[{"id": "s1", "title": "Inset the top"}])
    assert skill_hooks.tags(s)["s1"] == ["bl.extrude"]
    # a later lesson with the same step count: a stale (id(graph), len) key would hand back lesson A's tags
    s.graph = {"lesson": {"id": "B", "goal": "practice functions"}, "steps": [{"id": "t1", "title": "Write add"}]}
    s.steps = [{"id": "t1", "title": "Write the add function"}]
    got = skill_hooks.tags(s)
    assert "s1" not in got and got.get("t1") != ["bl.extrude"]
