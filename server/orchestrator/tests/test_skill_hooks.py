"""Skill tree hooks in the lesson session: a hint / show me makes the step's pass assisted, an unassisted pass on two
days masters the step's catalog skills, a skip misses a due review, and a proof of the learner's own file is kept.
Offline: stub modules, no model, no network."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from server.orchestrator import skill_hooks, stubs
from server.orchestrator.modules import Modules
from server.orchestrator.session import LessonSession
from server.skilltree import ledger, proofs

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


def test_note_assist_is_per_step_and_resets_with_the_lesson():
    s = SimpleNamespace(graph={"lesson": {"id": "A"}}, step={"id": "s1"})
    skill_hooks.note_assist(s, "explain")  # explaining the idea is not doing it for them
    assert skill_hooks._assisted(s) == set()
    skill_hooks.note_assist(s, "show_me")
    assert skill_hooks._assisted(s) == {"s1"}
    s.graph = {"lesson": {"id": "B"}}
    assert skill_hooks._assisted(s) == set()


def test_record_keeps_a_proof_from_the_learners_file_inside_the_lesson_folder(state):
    work = state / "work"
    (work / "app.py").write_text("import os\n\ndef add(a, b):\n    return a + b\n")
    (work / ".env").write_text("KEY=1")
    step = {"id": "s1", "file": "app.py", "code": "def add(a, b):\n    return a + b"}
    up = skill_hooks.record(step, ["py.functions"], assisted=False, skipped=False, lesson_id="L", workdir=str(work), now=t(1))
    (row,) = up["skills"]
    assert row["id"] == "py.functions" and row["state"] == "practicing" and row["proofIds"]
    assert proofs.get(row["proofIds"][0])["text"] == "def add(a, b):\n    return a + b"
    assert skill_hooks._read_file(str(work), "../outside.py") == (None, None)
    assert skill_hooks._read_file(str(work), ".env")[0] is None
    # an assisted pass keeps no proof (it is not the learner's own work) and never counts toward mastery
    up = skill_hooks.record(step, ["py.functions"], assisted=True, skipped=False, lesson_id="L", workdir=str(work), now=t(2))
    assert len(proofs.for_skill("py.functions")) == 1 and up["skills"][0]["unassistedDays"] == 1


def test_skip_misses_only_a_due_review(state):
    ledger.record_pass(["bl.edit"], now=t(1), tz=UTC)
    ledger.record_pass(["bl.edit"], now=t(2), tz=UTC)
    step = {"id": "s"}
    assert skill_hooks.record(step, ["bl.edit"], assisted=False, skipped=True, lesson_id=None, workdir=None, now=t(3)) is None
    up = skill_hooks.record(step, ["bl.edit"], assisted=False, skipped=True, lesson_id=None, workdir=None, now=t(9))
    assert up["events"][0]["kind"] == "review_missed"
    assert skill_hooks.record({"id": "r", "kind": "read"}, ["bl.edit"], assisted=False, skipped=False,
                              lesson_id=None, workdir=None, now=t(9)) is None


def test_session_pass_after_a_hint_is_assisted_and_a_clean_pass_counts(state, monkeypatch):
    clock = {"now": t(1)}
    real = ledger.record_pass
    monkeypatch.setattr(ledger, "record_pass", lambda ids, **k: real(ids, **{**k, "now": clock["now"], "tz": UTC}))
    (state / "work" / "app.py").write_text("def add(a, b):\n    return a + b\n")

    async def lesson(hint: bool) -> LessonSession:
        s, _ = _session()
        await s.load_graph(_python_graph())
        await s.drain()
        s.workdir = str(state / "work")
        if hint:
            await s._action("hint")
            await s.drain()
        await s._pass_step()
        await s.drain()
        return s

    s = asyncio.run(lesson(hint=True))
    assert s.skill_update and s.skill_update["skills"][0]["id"] == "py.functions"
    row = ledger.skill_row("py.functions", now=t(1), tz=UTC)
    assert row["passes"] == 1 and row["unassistedDays"] == 0
    asyncio.run(lesson(hint=False))
    clock["now"] = t(2)
    s = asyncio.run(lesson(hint=False))
    assert s.skill_update["events"][0]["kind"] == "mastered"
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

    sent = asyncio.run(go())
    assert any(type_ == "step.passed" for type_, _ in sent)
