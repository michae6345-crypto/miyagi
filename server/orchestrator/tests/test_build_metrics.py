"""Build metrics (lane build-metrics): command -> lesson.ready -> step 1, by stage, on fake clocks.

Run from the repo root:  python -m pytest server/orchestrator/tests/test_build_metrics.py -q
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest

from server.orchestrator import build_metrics, stubs
from server.orchestrator import workspace as wsmod
from server.orchestrator.build_metrics import BuildMetrics
from server.orchestrator.hub import Hub
from server.orchestrator.modules import Modules
from server.orchestrator.session import LessonSession

URL = "https://www.youtube.com/watch?v=abcdefghijk"


class Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# ------------------------------------------------------------------------------------------------ the timer alone
def _timer(tmp_path: Path, clock: Clock, **kw) -> BuildMetrics:
    return BuildMetrics(clock=clock, wall=lambda: 1_763_800_000.0, path=lambda: tmp_path / "build-metrics.jsonl", **kw)


def test_stages_add_up_from_the_command_to_step_one(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="orchestrator.build_metrics")
    clock = Clock()
    bm = _timer(tmp_path, clock)
    bm.command("learn_url")
    clock.t += 3.0  # the preflight card + the learner's Build press
    rec = bm.begin("video", source="abcdefghijk")
    clock.t += 1.5
    rec.progress("reading_transcript")
    clock.t += 4.0
    rec.progress("writing_steps", "212 transcript lines")
    clock.t += 22.0
    rec.progress("steps_ready", "claude")
    clock.t += 2.0
    rec.progress("adapting")  # same "checks" mark: the first one counts
    clock.t += 9.0
    rec.progress("done", "37s")
    clock.t += 0.25
    rec.mark("workspace")
    clock.t += 5.0
    rec.mark("hold")
    clock.t += 1.5
    assert bm.ready(steps=7) == 48.25
    clock.t += 0.5
    bm.first_step(0)

    line = bm.last
    assert line["outcome"] == "ok" and line["kind"] == "video" and line["command"] == "learn_url"
    assert line["source"] == "abcdefghijk" and line["engine"] == "claude" and line["steps"] == 7
    assert line["toReadyS"] == 48.25 and line["toFirstStepS"] == 48.75
    assert line["buildToReadyS"] == 45.25 and line["buildToFirstStepS"] == 45.75
    assert line["stages"] == {"preflight": 3.0, "setup": 1.5, "captions": 4.0, "steps": 22.0, "checks": 11.0,
                              "handoff": 0.25, "workspace": 5.0, "hold": 1.5, "start": 0.5}
    assert sum(line["stages"].values()) == pytest.approx(line["toFirstStepS"])
    assert list(line["marks"]) == ["command", "build", "captions", "steps", "checks", "handoff", "workspace", "hold",
                                   "ready", "first_step"]
    assert line["firstStepIndex"] == 0 and "elapsedS" not in line

    logged = [r.getMessage() for r in caplog.records if r.getMessage().startswith("build.metrics ")]
    assert len(logged) == 1 and json.loads(logged[0].split(" ", 1)[1]) == line  # one JSON line in the engine log
    assert build_metrics.read(tmp_path / "build-metrics.jsonl") == [line]
    assert bm.current is None
    bm.first_step(1)  # a later step never adds a second record
    assert len(build_metrics.read(tmp_path / "build-metrics.jsonl")) == 1


def test_a_cache_hit_has_no_model_stages_and_no_command_counts_from_the_build(tmp_path):
    clock = Clock()
    bm = _timer(tmp_path, clock)
    rec = bm.begin("video")
    clock.t += 0.4
    rec.progress("cache_hit", "abc.json")
    rec.progress("done", "abc.json")
    rec.mark("workspace")
    clock.t += 2.0
    rec.mark("hold")
    clock.t += 0.6
    bm.ready()
    bm.first_step(0)
    line = bm.last
    assert line["cacheHit"] is True and "command" not in line and "buildToReadyS" not in line
    assert line["toReadyS"] == 3.0
    assert line["stages"] == {"setup": 0.4, "handoff": 0.0, "workspace": 2.0, "hold": 0.6, "start": 0.0}


def test_failed_and_cancelled_builds_are_recorded_with_how_long_they_ran(tmp_path):
    clock = Clock()
    bm = _timer(tmp_path, clock)
    bm.command("build_lesson")
    clock.t += 1.0
    rec = bm.begin("video")
    rec.progress("reading_transcript")
    clock.t += 6.0
    bm.failed("network")
    failed = bm.last
    assert failed["outcome"] == "failed" and failed["failCode"] == "network"
    assert failed["elapsedS"] == 7.0 and failed["stages"] == {"preflight": 1.0, "setup": 0.0, "captions": 6.0}
    assert "toReadyS" not in failed

    rec2 = bm.begin("text")
    clock.t += 2.0
    rec2.progress("planning")
    clock.t += 3.0
    bm.begin("video")  # a new build replaces it
    replaced = bm.last
    assert replaced["outcome"] == "cancelled" and replaced["reason"] == "replaced" and replaced["elapsedS"] == 5.0
    rec2.progress("writing_steps")  # the replaced build's late callback: its own closed record, a no-op
    assert "steps" not in rec2.marks
    bm.cancel("stopped")
    assert bm.last["reason"] == "stopped" and bm.current is None
    assert [r["outcome"] for r in build_metrics.read(tmp_path / "build-metrics.jsonl")] == ["failed", "cancelled",
                                                                                            "cancelled"]


def test_the_metrics_file_keeps_only_the_last_builds(tmp_path):
    clock = Clock()
    bm = _timer(tmp_path, clock, max_lines=10)
    for i in range(25):
        bm.command(f"cmd{i}")
        bm.begin("video")
        clock.t += 1
        bm.ready()
        bm.first_step(0)
    rows = build_metrics.read(tmp_path / "build-metrics.jsonl")
    assert 10 <= len(rows) <= 11  # trimmed back to 10 once it is 10% over
    assert rows[-1]["command"] == "cmd24" and rows[0]["command"] == f"cmd{25 - len(rows)}"
    assert build_metrics.read(tmp_path / "build-metrics.jsonl", limit=3)[0]["command"] == "cmd22"


def test_the_default_file_is_in_the_state_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    assert build_metrics.metrics_path() == tmp_path / "state" / "build-metrics.jsonl"


# ------------------------------------------------------------------------------------------------ in the session
class Rig:
    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
        self.hub = Hub(strict=True)
        self.clock = Clock()
        self.s = LessonSession(self.hub.emit, Modules(demo=False, force_stubs="all"), clock=self.clock,
                               idle_gate_s=5, advance_delay_s=0, metric_eval_s=0, result_stagger_s=0,
                               build_tick_s=0.01, seen_interval_s=0)
        self.s.ready_hold_s = 0
        self.folder = tmp_path / "lesson"
        self.folder.mkdir()

        def prepare(graph, goal, *a, **kw):  # S2's folder + starter files: 3 s on the fake clock
            self.clock.t += 3.0
            return str(self.folder)

        monkeypatch.setattr(wsmod, "prepare", prepare)
        monkeypatch.setattr(wsmod, "set_aside_previous", lambda *a, **kw: None)

    def of(self, type_: str) -> list[dict]:
        return [e["payload"] for e in self.hub.history if e["type"] == type_]


def test_a_video_build_logs_its_stages_and_appends_the_state_file(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="orchestrator.build_metrics")
    rig = Rig(tmp_path, monkeypatch)
    clock = rig.clock

    async def build(url, goal, workdir, on_progress=None, **kw):
        clock.t += 1.0  # cache lookup + metadata
        on_progress("reading_transcript", "")
        clock.t += 4.0
        on_progress("writing_steps", "212 transcript lines")
        clock.t += 20.0
        on_progress("steps_ready", "claude")
        on_progress("adapting", "")
        clock.t += 10.0
        on_progress("done", "35s")
        return stubs.load_fixture_lesson()

    rig.s.m.build_lesson = build
    rig.s.build_metrics.command("learn_url")  # main.py stamps it on arrival
    clock.t += 2.0
    asyncio.run(rig.s.learn_url(URL))

    assert rig.of("lesson.ready") and rig.of("step.started")
    line = rig.s.build_metrics.last
    assert line["outcome"] == "ok" and line["kind"] == "video" and line["command"] == "learn_url"
    assert line["source"] == "abcdefghijk" and line["engine"] == "claude"
    assert line["stages"] == {"preflight": 2.0, "setup": 1.0, "captions": 4.0, "steps": 20.0, "checks": 10.0,
                              "handoff": 0.0, "workspace": 3.0, "hold": 0.0, "start": 0.0}
    assert line["toReadyS"] == 40.0 and line["toFirstStepS"] == 40.0 and line["buildToReadyS"] == 38.0
    assert line["steps"] == len(rig.s.steps)
    assert build_metrics.read() == [line]  # $MIYAGI_STATE_DIR/build-metrics.jsonl (conftest: a temp folder)
    assert sum(r.getMessage().startswith("build.metrics {") for r in caplog.records) == 1


def test_a_text_lesson_times_its_plan_and_first_step(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    clock = rig.clock

    async def build_text_lesson(goal, workdir, on_update=None, on_progress=None):
        on_progress("planning", "planning the lesson")
        clock.t += 6.0
        on_progress("writing_steps", "5 steps planned")
        clock.t += 12.0
        g = stubs.load_fixture_lesson()
        first = {**g, "steps": g["steps"][:1], "lesson": {**g["lesson"], "complete": False}}
        on_progress("first_steps", "1 step")
        await on_update(first, False)
        clock.t += 30.0  # the rest of the steps: after step 1 started, not in the record
        return g

    rig.s.m.build_text_lesson = build_text_lesson
    rig.s.build_metrics.command("learn")
    clock.t += 0.5
    asyncio.run(rig.s.learn("build a tiny todo app", "lesson"))

    line = rig.s.build_metrics.last
    assert line["kind"] == "text" and line["outcome"] == "ok" and line["command"] == "learn"
    assert line["stages"] == {"preflight": 0.5, "setup": 0.0, "workspace": 3.0, "plan": 6.0, "steps": 12.0,
                              "handoff": 0.0, "hold": 0.0, "start": 0.0}
    assert line["toFirstStepS"] == 21.5 and "source" not in line


def test_a_failed_build_is_recorded_with_its_fail_code(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    clock = rig.clock

    async def build(url, goal, workdir, on_progress=None, **kw):
        on_progress("reading_transcript", "")
        clock.t += 5.0
        raise RuntimeError("Could not retrieve a transcript: 429 Client Error: Too Many Requests (youtube)")

    rig.s.m.build_lesson = build
    asyncio.run(rig.s.learn_url(URL))
    line = rig.s.build_metrics.last
    assert line["outcome"] == "failed" and line["failCode"] == "network"
    assert line["stages"]["captions"] == 5.0 and line["elapsedS"] == 5.0 and "toReadyS" not in line
    assert rig.of("lesson.building")[-1]["failed"] is True


def test_ending_a_build_mid_flight_records_it_as_cancelled(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    clock = rig.clock

    async def build(url, goal, workdir, on_progress=None, **kw):
        on_progress("reading_transcript", "")
        clock.t += 8.0
        await asyncio.Event().wait()  # never finishes

    rig.s.m.build_lesson = build

    async def go():
        learn = asyncio.create_task(rig.s.learn_url(URL))
        for _ in range(20):
            await asyncio.sleep(0.01)
            if rig.s.build_metrics.current is not None and "captions" in rig.s.build_metrics.current.marks:
                break
        await rig.s.end_lesson("stopped")
        await learn

    asyncio.run(go())
    line = rig.s.build_metrics.last
    assert line["outcome"] == "cancelled" and line["elapsedS"] == 8.0 and line["stages"]["captions"] == 8.0
    assert [r["outcome"] for r in build_metrics.read()] == ["cancelled"]
