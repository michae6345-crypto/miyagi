"""Context memory in a real LessonSession (the AutoCAD lesson of Nov 22): what the learner did reaches the coach's
next prompt as untrusted data. Offline: the setup_apps rig (fake Claude, fake Spotlight, a recorded `open`)."""

from __future__ import annotations

import pytest

from server.context import store
from server.orchestrator.tests.test_session import run
from server.orchestrator.tests.test_setup_apps import _start, rig  # noqa: F401 - the rig fixture


@pytest.fixture
def memory_on(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_CONTEXT_MEMORY", "1")
    monkeypatch.setenv("MIYAGI_CONTEXT_DIR", str(tmp_path / "context"))
    store._index.clear()
    yield
    store._index.clear()


def test_what_the_learner_did_reaches_the_explain_context(rig, memory_on):  # noqa: F811
    async def go():
        await _start(rig)
        await rig.s.action("have_it", "autocad")
        await rig.settle()

    run(go())
    mem = rig.s._explain_context()["memory"]
    assert "learner said they already have autocad" in mem
    assert "setup asked: This lesson uses AutoCAD" in mem
    assert "lesson:" in mem
    assert rig.s._memory_kw(rig.s.step, "judge") == {"memory": rig.s._memory_kw(rig.s.step, "judge")["memory"]}
    assert "setup asked" in rig.s._memory_kw(rig.s.step, "judge")["memory"]


def test_end_then_a_fresh_start_of_the_same_lesson_starts_with_no_old_notes(rig, memory_on):  # noqa: F811
    async def go():
        await _start(rig)
        await rig.s.action("have_it", "autocad")
        await rig.settle()
        await rig.s.end_lesson("stopped")  # End: the saved place stays resumable
        await rig.settle()
        await _start(rig)  # the same lesson (same id) loaded again at step 1: a fresh run, not a Resumer restore

    run(go())
    mem = rig.s._explain_context().get("memory", "")
    assert "said they already have autocad" not in mem
    assert "lesson:" in mem  # this run's own notes are there


def test_a_resumer_restore_keeps_the_notes(rig, memory_on):  # noqa: F811
    async def go():
        await _start(rig)
        await rig.s.action("have_it", "autocad")
        await rig.settle()
        rig.s.restoring = True  # sessions.Resumer._load_at: an engine restart's save of this lesson, or Continue
        try:
            await _start(rig)
        finally:
            rig.s.restoring = False

    run(go())
    assert "said they already have autocad" in rig.s._explain_context()["memory"]


def test_memory_off_leaves_the_context_unchanged(rig):  # noqa: F811
    run(_start(rig))
    assert "memory" not in rig.s._explain_context()
    assert rig.s._memory_kw(rig.s.step, "diagnose") == {}
