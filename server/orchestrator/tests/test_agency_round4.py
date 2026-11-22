"""eng-agency fix round 4: a lesson's VS Code checks graded on its files never stall the event loop (offline: no
model, no network; the only process is the regex worker's own Python)."""
from __future__ import annotations

import asyncio
import threading
import time
import uuid

from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig, run
from server.safety import regex_worker

N_SLOW = 12


def _slow_lesson(nonce: str) -> dict:
    """The reviewer's probe: one step of N_SLOW distinct screen_contains checks that each run past the worker's
    deadline on calc.py, about the Code app, whose file is in the lesson folder."""
    checks = [{"id": f"s1c{i}", "type": "screen_contains", "app": "Code", "label": f"row {i}", "file": "calc.py",
               "pattern": f"(?:pz{nonce}{i})?" + "a?" * 24 + "a" * 24 + "!"} for i in range(N_SLOW)]
    return {"lesson": {"id": f"lesson-slow-{nonce}", "title": "Slow", "goal": "slow", "mode": "lesson",
                       "complete": True, "builtBy": "claude"},
            "steps": [{"id": "s1", "index": 1, "title": "Write it", "instructions": "Type it.", "file": "calc.py",
                       "code": "a\n", "checks": checks, "precision_checks": []}]}


def _rig(tmp_path, monkeypatch, graph) -> tuple[Rig, FakeScreen]:
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.setenv("TUT_SPOOL_DIR", str(tmp_path / "spool"))
    monkeypatch.delenv("DEMO", raising=False)
    from server.orchestrator.workspace import Workspace

    screen = FakeScreen()
    rig = Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,coach,finder,diagrams"), screen=screen)
    rig.s.workspace = Workspace(enabled=False, runner=lambda argv: True)
    rig.s.check_wait_s = 0

    async def build(goal, workdir, on_update=None, **kw):
        return graph

    async def no_judge(step, screen=None, files=None, **kw):
        return None

    rig.s.m.build_text_lesson = build
    rig.s.m.judge_step = no_judge
    return rig, screen


def test_slow_vscode_checks_graded_on_the_file_never_stall_the_event_loop(tmp_path, monkeypatch):
    """The frame shows no VS Code text, so _settle_checks grades every Code check on calc.py: those searches wait
    on the regex worker in a thread, under the lesson's budget. The loop's longest stall stays about
    LESSON_TIMEOUTS x DEADLINE_S (an on-loop sink's share of the budget), never one deadline per check."""
    rig, screen = _rig(tmp_path, monkeypatch, _slow_lesson(uuid.uuid4().hex[:8]))
    (tmp_path / "calc.py").write_text("a" * 40 + "\n")  # every pattern backtracks for seconds on it
    screen.text = {"Terminal": ["$ ls", "calc.py"]}  # a frame without VS Code text
    timeouts: list[bool] = []
    real_strike = regex_worker.strike

    def strike(pattern):
        timeouts.append(threading.current_thread() is threading.main_thread())
        return real_strike(pattern)

    monkeypatch.setattr(regex_worker, "strike", strike)
    gaps: list[float] = []

    async def go():
        stop = asyncio.Event()

        async def ticker():
            last = time.monotonic()
            while not stop.is_set():
                await asyncio.sleep(0.01)
                now = time.monotonic()
                gaps.append(now - last)
                last = now

        tick = asyncio.create_task(ticker())
        await rig.s.learn("slow", mode="lesson")
        await rig.settle()
        for _ in range(3):  # more frames: the lesson's budget is spent, nothing waits on the worker again
            await rig.s.evaluate("screen")
            await rig.settle()
        stop.set()
        await tick

    t0 = time.monotonic()
    run(go())
    took = time.monotonic() - t0
    assert timeouts, "the probe never reached the regex worker's deadline"
    bound = regex_worker.LESSON_TIMEOUTS * regex_worker.DEADLINE_S + 0.75  # + a worker restart
    assert max(gaps) < bound, (max(gaps), timeouts)
    # the budget stops the lesson's slow patterns: a few deadlines in all, never one per check per frame
    assert len(timeouts) <= regex_worker.LESSON_TIMEOUTS
    assert took < 4 * regex_worker.LESSON_TIMEOUTS * (regex_worker.DEADLINE_S + 0.75) + 5.0


def test_settle_searches_run_off_the_loop_with_the_lessons_budget(tmp_path, monkeypatch):
    rig, screen = _rig(tmp_path, monkeypatch, _slow_lesson(uuid.uuid4().hex[:8]))
    (tmp_path / "calc.py").write_text("a\n")
    screen.text = {"Terminal": ["$ ls"]}
    from server.checks import evaluator

    seen = []
    real = evaluator.screen_check_on_file

    def on_file(check, path, window_open=True):
        seen.append((threading.current_thread() is threading.main_thread(), regex_worker._CURRENT.get()))
        return real(check, path, window_open=window_open)

    monkeypatch.setattr(rig.s.m.real["checks"], "screen_check_on_file", on_file)

    async def go():
        await rig.s.learn("slow", mode="lesson")
        await rig.settle()
        seen.clear()
        await rig.s.evaluate("screen")
        await rig.settle()

    run(go())
    assert seen and all(not main and b is not None and b.key == rig.s._regex_key() for main, b in seen)


def test_a_search_on_the_loop_counts_against_the_running_lesson(tmp_path, monkeypatch):
    """Outside any budget() (a metric read off a run, code_gate, the notebook coach ...) the running lesson's Budget
    applies (regex_worker.set_fallback); a new lesson gets a fresh one."""
    rig, _ = _rig(tmp_path, monkeypatch, _slow_lesson(uuid.uuid4().hex[:8]))
    assert regex_worker._CURRENT.get() is None
    first = regex_worker._active()
    assert first is not None and first.key == rig.s._regex_key()
    rig.s.lesson_epoch += 1
    second = regex_worker._active()
    assert second is not first and second.key == rig.s._regex_key()
    with regex_worker.budget(("explicit", 1)) as b:  # an explicit budget() wins
        assert regex_worker._active() is b
    regex_worker.set_fallback(None)
    assert regex_worker._active() is None


def test_the_fallback_never_keeps_a_session_alive():
    import gc

    class S:
        def key(self):
            return ("s", 1)

    s = S()
    regex_worker.set_fallback(s.key)
    assert regex_worker._active().key == ("s", 1)
    del s
    gc.collect()
    assert regex_worker._active() is None


def test_a_build_lints_under_its_own_regex_budget(tmp_path, monkeypatch):
    """The model's patterns a build lints never count against (or are stopped by) the lesson running meanwhile."""
    from server.lesson import builder

    seen = []

    async def impl(source_url, goal, workdir, **kw):
        seen.append(regex_worker._active())
        return {"lesson": {"id": "x"}, "steps": []}

    monkeypatch.setattr(builder, "_build_lesson_impl", impl)
    monkeypatch.setattr(builder, "_untrusted", lambda g, w: g)

    class Lesson:
        def key(self):
            return ("lesson", "running")

    lesson = Lesson()
    regex_worker.set_fallback(lesson.key)
    asyncio.run(builder.build_lesson("https://example.com/post", "goal", str(tmp_path)))
    assert seen and seen[0] is not None and seen[0].key[0] == "build"
    assert regex_worker._active().key == ("lesson", "running")
