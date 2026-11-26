"""Desktop test 12 (Nov 15, 08:54-09:00, the "Watch a video" Kie Codes MNIST notebook lesson):
- a step passed while its clip still played: the app's player jumped to the next step's video.start (2:51 -> 4:12,
  4:36 -> 7:18) although the engine logged "video plays on ... no jump": step.started now says where the clip is;
- the step's box + code popup went up on the plt.subplots line the learner had already typed (the cell was running);
- VS Code stayed narrowed after End lesson: the frame from before the lesson comes back;
- preflight copy: no fit hedge under a good match; the length in whole minutes (8:40 is "8 min", not "9 min").
Offline: no API calls, no real windows (a fake AX)."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from server.orchestrator import nb_coach, stubs
from server.orchestrator.session import LessonSession as Session
from server.orchestrator.tests.test_session import Rig
from server.orchestrator.workspace import Workspace
from server.preflight import core as pf
from server.workspace import editor

ROOT = Path(__file__).resolve().parents[2]
LESSON = ROOT / "demo" / "cache" / "lessons" / "5c0ea8a49f419487.json"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    return Rig(tmp_path)


# ------------------------------------------------------------------ 1. no jump ahead on a pass mid-clip
def _video_after(rig: Rig, mark: int, step_id: str) -> tuple[dict, list[str]]:
    ev = rig.since(mark)
    i = next(k for k, e in enumerate(ev) if e["type"] == "step.started" and e["payload"]["stepId"] == step_id)
    return ev[i]["payload"], [e["type"] for e in ev[i:]]


def test_pass_mid_clip_tells_the_player_to_play_on(rig):
    """s1's clip (0-40 s) is at 0:20 when s1 passes: s2 (40-120 s) starts where the video is. The app's player seeks to
    step.started's video.start unless it's already past it (player/store.ts), so that start is the clip's position,
    and the engine sends no video.seek: nothing between 0:20 and 0:40 is skipped."""
    async def go():
        await rig.start_lesson()
        await rig.s.video_state(20.0, True)
        rig.clock.t += 2.0  # 0:22 now
        m = rig.mark()
        await rig.save("# hi\n")
        return m

    m = run(go())
    started, after = _video_after(rig, m, "s2")
    assert started["video"]["end"] == 120 and started["video"]["start"] <= 22.0, started["video"]
    assert started["video"]["start"] >= 20.0  # no replay of what already played either
    assert "video.seek" not in after
    assert rig.s._segment(rig.s.step)["start"] == 40.0  # the step's own segment (Show me, the gate) is unchanged


def test_paused_at_the_gate_still_starts_the_next_clip(rig):
    async def go():
        await rig.start_lesson()
        await rig.end_segment()  # held at 0:40 ("Waiting for your checks")
        m = rig.mark()
        await rig.save("# hi\n")
        return m

    m = run(go())
    started, after = _video_after(rig, m, "s2")
    assert started["video"]["start"] == 40.0 and "video.seek" in after


def test_skip_mid_clip_moves_on_to_the_next_clip(rig):
    async def go():
        await rig.start_lesson()
        await rig.s.video_state(20.0, True)
        m = rig.mark()
        await rig.s.action("skip_step")
        await rig.settle()
        return m

    m = run(go())
    started, after = _video_after(rig, m, "s2")
    assert started["video"]["start"] == 40.0 and "video.seek" in after


def test_back_after_a_play_on_still_opens_the_previous_clip(rig):
    """14f55e7: Back opens the previous step and its clip from its start (a seek backward); play-on never touches it."""
    async def go():
        await rig.start_lesson()
        await rig.s.video_state(20.0, True)
        await rig.save("# hi\n")  # s2 starts, the clip plays on
        await rig.s.video_state(45.0, True)
        m = rig.mark()
        await rig.s.action("back")
        await rig.settle()
        return m

    m = run(go())
    started, _after = _video_after(rig, m, "s1")
    assert started["video"]["start"] == 0.0 and rig.s.step["id"] == "s1"
    assert all(e["payload"]["t"] <= 45.0 for e in rig.since(m) if e["type"] == "video.seek")


def _graph() -> dict:
    return copy.deepcopy(json.loads(LESSON.read_text(encoding="utf-8")))


def _bare(tmp_path: Path, graph: dict | None = None) -> Session:
    s = Session.__new__(Session)  # no engine, no screen: the helpers only
    s.graph = graph or _graph()
    s.workdir = str(tmp_path)
    s.has_python = True
    s.lesson_epoch = 1
    return s


def test_t12_timings_play_on(tmp_path):
    s = _bare(tmp_path)
    s.idx, s.phase, s.segment_done, s.video_t = 3, "active", False, None  # s4 (151-251 s) passes at 2:53
    s.clock = lambda: 1000.0
    s._play_at = (173.0, 1000.0)
    assert s._clip_runs_into(4) == 173.0  # s5 is 251-437 s: play on from 2:53, never jump to 4:11
    s._play_at = (252.0, 1000.0)  # already inside s5's clip: play on there too (no seek back)
    assert s._clip_runs_into(4) == 252.0
    s.skipped_steps = ["s4"]  # Skip: the next clip, as the app's step.passed skipped says
    assert s._clip_runs_into(4) is None


# ------------------------------------------------------------------ 2. no box / code popup on typed notebook code
def _nb(path: Path, sources: list[str]) -> None:
    cells = [{"cell_type": "code", "metadata": {}, "source": src.splitlines(keepends=True), "execution_count": None,
              "outputs": []} for src in sources]
    path.write_text(json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")


def test_code_typed_reads_the_notebook_and_the_code_checks(tmp_path):
    g = _graph()
    g["lesson"]["notebook"] = "mnist.ipynb"
    s = _bare(tmp_path, g)
    s.notebook_lesson, s.last_results = True, []
    s3 = next(x for x in g["steps"] if x["id"] == "s3")
    s1 = next(x for x in g["steps"] if x["id"] == "s1")
    _nb(tmp_path / "mnist.ipynb", [""])
    assert not nb_coach.code_typed(s, s3)
    _nb(tmp_path / "mnist.ipynb", ["import tensorflow as tf", s3["code"]])
    assert nb_coach.code_typed(s, s3)
    assert not nb_coach.code_typed(s, s1)  # a shell step's box is on the terminal
    s.notebook_lesson = False
    assert not nb_coach.code_typed(s, s3)  # not a notebook lesson: as before
    s.notebook_lesson = True
    _nb(tmp_path / "mnist.ipynb", [""])  # the file isn't saved yet, but its code check passed (t12: s3c1)
    s.last_results = [{"checkId": "s3c1", "status": "pass", "label": "subplots call typed"},
                      {"checkId": "s3c2", "status": "fail", "label": "Training count printed"},
                      {"checkId": "s3-ran", "status": "pending", "label": "Ran the cell"}]
    assert nb_coach.code_typed(s, s3)


def test_no_step_box_on_typed_notebook_code(rig, tmp_path):
    g = _graph()
    g["lesson"]["notebook"] = "mnist.ipynb"
    s = rig.s
    s.graph, s.workdir, s.notebook_lesson, s.last_results = g, str(tmp_path), True, []
    s3 = next(x for x in g["steps"] if x["id"] == "s3")
    _nb(tmp_path / "mnist.ipynb", [s3["code"]])

    async def go():
        m = rig.mark()
        placed = await s._spotlight_target(s3)
        return placed, rig.since(m)

    placed, ev = run(go())
    assert placed is False and not [e for e in ev if e["type"] == "spotlight" and "rect" in e["payload"]]
    assert s.spot_track is None  # nothing left to follow onto that line later either


# ------------------------------------------------------------------ 3. VS Code's frame back after the lesson
class FakeAX:
    def __init__(self, frame):
        self.frames = {"w": tuple(frame)}

    def frame(self, win):
        return self.frames.get(win)

    def set_frame(self, win, x, y, w, h):
        self.frames[win] = (x, y, w, h)
        return True


def test_restore_frames_puts_the_window_back(monkeypatch):
    monkeypatch.setattr(editor, "_arranged", [])
    ax = FakeAX((0, 25, 1728, 1050))  # VS Code before the lesson: the whole screen
    assert editor._set_frame(ax, "w", 0, 60, 1037, 900)  # arrange: the left 60%
    assert editor._set_frame(ax, "w", 0, 60, 1000, 900)  # a run step: room for the drawer (the first frame stays)
    assert editor.restore_frames(ax) == [(0, 25, 1728, 1050)]
    assert ax.frames["w"] == (0, 25, 1728, 1050)
    assert editor.restore_frames(ax) == []  # once


def test_restore_frames_leaves_a_window_the_learner_moved(monkeypatch):
    monkeypatch.setattr(editor, "_arranged", [])
    ax = FakeAX((0, 25, 1728, 1050))
    editor._set_frame(ax, "w", 0, 60, 1037, 900)
    ax.frames["w"] = (200, 80, 1200, 800)  # they resized it during the lesson: theirs now
    assert editor.restore_frames(ax) == [] and ax.frames["w"] == (200, 80, 1200, 800)


def test_end_lesson_restores_the_layout(rig):
    calls = []

    class WS:
        def restore_layout(self):
            calls.append(1)

        def __getattr__(self, name):  # goto_target etc.: nothing
            return lambda *a, **k: None

    async def go():
        await rig.start_lesson()
        rig.s.workspace = WS()
        await rig.s.end_lesson("end_lesson")
        await rig.s.end_lesson("end_lesson")  # nothing running: nothing to restore

    run(go())
    assert calls == [1]


def test_workspace_restore_never_touches_real_windows_in_tests():
    assert Workspace(enabled=True, runner=lambda argv: True).restore_layout() is False


# ------------------------------------------------------------------ 4. preflight copy
def _res(score: float) -> dict:
    return {"videoId": "VPlFpvLOgtQ", "url": "https://www.youtube.com/watch?v=VPlFpvLOgtQ",
            "title": "Code your first Neural Network with TensorFlow", "channel": "Kie Codes", "style": "coding",
            "durationS": 520, "chapters": [{"start": i * 60, "title": f"c{i}"} for i in range(7)],
            "topic": "Codes and trains a handwritten-digit MNIST neural network classifier in TensorFlow",
            "goalMatch": {"score": score, "note": "Builds a real neural network, though only a basic digit classifier "
                                                  "on one dataset"},
            "buildPlan": {"strategy": "whole", "cached": True, "estSecondsToFirstSteps": 0},
            "cachedLesson": {"steps": 7}, "requirements": []}


def test_preflight_fit_note_only_on_a_poor_match():
    good = pf.preflight_card(_res(0.93))
    assert "though only" not in good["body"] and "warning" not in good
    assert good["body"].endswith("Built before: ready instantly (7 steps).")
    poor = pf.preflight_card(_res(0.3))
    assert "though only a basic digit classifier" in poor["body"] and poor["warning"].startswith("Builds a real")
    assert "—" not in good["body"] + poor["body"]


def test_preflight_length_in_whole_minutes():
    card = pf.preflight_card(_res(0.93))
    assert card["preflight"]["durationS"] == 480  # the app's "N min" (Math.round(s / 60)): 8:40 reads "8 min"
    assert round(card["preflight"]["durationS"] / 60) == 8
    assert pf.preflight_card({**_res(0.93), "durationS": 45})["preflight"]["durationS"] == 45
    assert pf.preflight_card({**_res(0.93), "durationS": None})["preflight"]["durationS"] is None
