"""The step checks hear when the lesson and the step began (RunContext.step_started_at / lesson_started_at), so an
export already in the folder is never the file a step saved under a name of its own. Offline: stub modules."""
from __future__ import annotations

import asyncio
import time

import pytest

from server.orchestrator.tests.test_session import Rig


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    return Rig(tmp_path)


def test_a_lesson_from_step_one_passes_both_start_times(rig):
    before = time.time()

    async def go():
        await rig.start_lesson()
        assert rig.s.idx == 0
        first = rig.s.context()
        assert first.lesson_started_at is not None and first.lesson_started_at >= before - 1
        assert first.step_started_at is not None and first.step_started_at >= first.lesson_started_at - 1
        await rig.s.start_step(1)
        await rig.settle()
        second = rig.s.context()
        assert second.lesson_started_at == first.lesson_started_at
        assert second.step_started_at is not None and second.step_started_at >= first.step_started_at
        await rig.s.start_step(0)  # back to a step already seen: its files may be from the first visit
        await rig.settle()
        again = rig.s.context()
        assert again.step_started_at is None and again.lesson_started_at == first.lesson_started_at

    asyncio.run(go())


def test_the_start_times_reach_the_checks_context(rig):
    from server import checks
    from server.orchestrator.context import RunContext

    rig.s.m.real["checks"] = checks
    made = rig.s.m.make_context(RunContext(workdir=str(rig.workdir), step_started_at=5.0, lesson_started_at=2.0))
    assert isinstance(made, checks.RunContext)
    assert (made.step_started_at, made.lesson_started_at) == (5.0, 2.0)


def test_a_lesson_restored_at_a_later_step_passes_no_start_time(rig):
    async def go():
        await rig.start_lesson()
        rig.s.lesson_wall_t0 = 0.0  # what start_step leaves when this session began at a later step (a restore)
        await rig.s.start_step(2)
        await rig.settle()
        ctx = rig.s.context()
        assert ctx.step_started_at is None and ctx.lesson_started_at is None

    asyncio.run(go())
