"""t8 offline: the judged lesson on a venue network that drops packets (Tiger's port blocked, Claude unreachable).
Run from the repo root:  python -m pytest server/orchestrator/tests/test_t8_offline.py -q

Measured on a private engine under a sandbox + tarpit proxy (scratch run, 06:35): a typed question in the curated
lesson waited 82 s for Claude (45 s timeout, twice) and Check my work, Show me and a new learn queued behind it."""

from __future__ import annotations

import asyncio
import time

import pytest

from server.checks import tiger
from server.orchestrator import curated, stage
from server.orchestrator.tests.test_session import Rig


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.delenv("MIYAGI_STAGE", raising=False)
    for name in ("GRADE_S", "ROW_S", "RUN_S", "STUCK_S"):
        monkeypatch.setattr(stage, name, 0.0)
    r = Rig(tmp_path)
    r.s.CURATED_ASK_S = 0.3
    return r


async def settle(rig: Rig) -> None:
    for _ in range(4):
        await rig.settle()
        await asyncio.sleep(0)


def hang_explain(rig: Rig) -> list:
    calls: list = []

    async def explain(step, question, ctx):  # Claude behind a dropped port: never answers
        calls.append(question)
        await asyncio.sleep(3600)

    rig.s.m.explain = explain
    return calls


@pytest.mark.parametrize("mode", ["demo", "lesson"])
def test_a_typed_question_answers_from_the_lesson_when_claude_hangs(rig, mode):
    async def go():
        await rig.s.learn("build a neural network", mode=mode)
        await settle(rig)
        assert curated.active(rig.s) and stage.on(rig.s) == (mode == "demo")
        calls = hang_explain(rig)
        m = rig.mark()
        t0 = time.monotonic()
        await asyncio.wait_for(rig.s.action("ask", "why does the loss not move?"), 5)
        took = time.monotonic() - t0
        await settle(rig)
        assert calls == ["why does the loss not move?"]
        assert took < 2.0, f"the question held the action queue for {took:.1f}s"
        cards = [e["payload"] for e in rig.since(m) if e["type"] == "card"]
        assert cards, "no answer at all"
        card = cards[-1]
        assert card["kind"] == "answer" and card["stepId"] == "nn1"
        assert "reach Claude" not in card["title"] and "retry" not in (card.get("actions") or [])
        assert card["body"]  # the step's own Explain card
        assert not rig.of("error")
    asyncio.run(go())


def test_the_next_press_is_not_stuck_behind_a_hanging_question(rig):
    async def go():
        await rig.s.learn("build a neural network", mode="demo")
        await settle(rig)
        hang_explain(rig)
        t0 = time.monotonic()
        ask = asyncio.create_task(rig.s.action("ask", "what is tanh?"))
        await asyncio.sleep(0)
        await asyncio.wait_for(ask, 5)
        rig.clock.t += 5
        await rig.s.action("check_step")  # Check my work right after: the Demo passes the typing step
        await settle(rig)
        assert time.monotonic() - t0 < 3.0
        assert [p["stepId"] for p in rig.of("step.passed")] == ["nn1"]
    asyncio.run(go())


def test_a_slow_answer_outside_the_curated_lesson_is_not_cut(rig):
    async def go():
        assert not curated.active(rig.s)

        async def explain(step, question, ctx):
            await asyncio.sleep(0.5)  # > CURATED_ASK_S: only the curated / Demo lesson has an offline answer
            return {"kind": "answer", "title": "Slow but real", "body": "x"}

        rig.s.m.explain = explain
        card = await rig.s._explain_in_time({"id": "s1"}, "q", {})
        assert card["title"] == "Slow but real"
    asyncio.run(go())


def test_tiger_writes_never_wait_on_a_blocked_port(tmp_path):
    """Venue Wi-Fi blocks Tiger's port: connect hangs until its timeout. Every record_* returns at once, the rows go
    to the spool, and the engine never waits for the connect."""
    started = []

    def slow_connect(dsn):
        started.append(time.monotonic())
        time.sleep(1.0)  # psycopg's connect_timeout on a dropped SYN
        raise OSError("connection timeout expired")

    w = tiger.TigerWriter(dsn="postgres://u:p@203.0.113.9:37145/tsdb", connect=slow_connect, spool_dir=tmp_path,
                          flush_every=0.05)
    t0 = time.monotonic()
    for i in range(200):
        w.record_event("check_pass", "lesson-nn-from-scratch", "nn1", payload={"i": i})
        w.record_metric("stage-nn4-0", "loss", i, 0.49)
    w.record_run({"id": "stage-nn4-0", "lesson_id": "lesson-nn-from-scratch", "source": "demo"})
    assert time.monotonic() - t0 < 0.5
    w.flush(timeout=5)
    assert started, "the writer never tried Tiger"
    assert not w.online and w.rows_spooled == 401 and w.dropped == 0
    assert sum(len(f.read_text().splitlines()) for f in tmp_path.glob("*.jsonl")) == 401
