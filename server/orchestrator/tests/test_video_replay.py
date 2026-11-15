"""Offline replay of desktop test 9 (Nov 15, 06:12-06:19): the "Watch a video" path on the cached Gemini lesson
demo/cache/lessons/5c0ea8a49f419487.json ("Code your first Neural Network with TensorFlow", Kie Codes, VPlFpvLOgtQ;
s1 venv + Jupyter, s2 imports + MNIST, s3 shapes + plot, s4 model, s5 train, s6 predict, s7 evaluate).

The engine's real session code runs the lesson (learn_url -> _build -> load_graph -> start_step -> evaluate ->
_pass_step, the real server.checks evaluator), with:
  * the lesson builder returning the cached lesson (no Gemini), the coach / finder / diagrams stubbed (no Claude);
  * a temp lesson folder (TUT_WORKDIR) holding the learner's mnist.ipynb (sources, and outputs once a cell ran);
  * a scripted screen reader (FakeScreen): the OCR lines test 9's frames showed per step, the clipped / wrapped
    `load_data()` line included; it starts with nothing read (the reader resumes after the step starts, V1);
  * no socket may leave this machine (a guard fails the test on any non-loopback connect).

Each test-9 finding still open is an xfail(strict=True) naming its V-number (scratchpad T9-BRIEF.md): the fix that
lands flips it to XPASS, which fails the suite until the mark is removed. Run (well under a minute, no screen):
    env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u BRIGHTDATA_API_KEY python -m pytest server/orchestrator/tests/test_video_replay.py -q
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import socket
from collections import deque
from pathlib import Path

import pytest

from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig

REPO = Path(__file__).resolve().parents[3]
CACHED = REPO / "demo" / "cache" / "lessons" / "5c0ea8a49f419487.json"
URL = "https://www.youtube.com/watch?v=VPlFpvLOgtQ"
GOAL = "build a neural network"
NB = "mnist.ipynb"  # the learner's notebook (test 9); the video's is Untitled.ipynb


def _graph() -> dict:
    return json.loads(CACHED.read_text(encoding="utf-8"))


STEPS = {s["id"]: s for s in _graph()["steps"]}

# ------------------------------------------------------------------ what the screen showed in test 9
S1_TERMINAL = [  # VS Code's terminal after the step-1 command ran (06:15:25-:32)
    "(.venv) learner@mac nn-tensorflow % source .venv/bin/activate && jupyter notebook",
    "Requirement already satisfied: jupyter in ./.venv/lib/python3.12/site-packages (1.1.1)",
    "[I 2026-11-15 06:15:30.112 ServerApp] Jupyter Server 2.21.1 is running at:",
    "[I 2026-11-15 06:15:30.112 ServerApp] http://localhost:8888/tree?token=4f2a9c",
]
S2_LOAD = "(train_images, train_labels), (test_images, test_labels) = tf.keras.datasets.mnist.load_data()"
S2_CODE = STEPS["s2"]["code"].splitlines()
S2_CLIPPED = [ln if ln != S2_LOAD else S2_LOAD[:-12] for ln in S2_CODE]  # 06:15:54: ran off the narrow editor
S2_WRAPPED = []  # 06:17:34: word wrap on: "…datasets.mnist." / "load_data()"
for _ln in S2_CODE:
    S2_WRAPPED += [S2_LOAD[:-11], S2_LOAD[-11:]] if _ln == S2_LOAD else [_ln]
S3_CODE = STEPS["s3"]["code"].splitlines()
S3_OUT = ["Number of images in the training dataset: 60000", "Number of images in the testing dataset: 10000",
          "Shape of the images in the training dataset: (28, 28)"]


def _cell(code: str, outputs: list[str] | None) -> dict:
    cell = {"cell_type": "code", "metadata": {}, "source": code.splitlines(keepends=True),
            "execution_count": None, "outputs": []}
    if outputs is not None:
        cell["execution_count"] = 1
        cell["outputs"] = [{"output_type": "stream", "name": "stdout", "text": [ln + "\n" for ln in outputs]}]
    return cell


def _notebook(cells: list[dict]) -> str:
    return json.dumps({"cells": cells, "metadata": {"kernelspec": {"name": "python3", "display_name": ".venv"}},
                       "nbformat": 4, "nbformat_minor": 5}, indent=1)


# ------------------------------------------------------------------ the rig
@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Zero paid calls: no keys in the environment, and no socket may reach past this machine."""
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    real = socket.socket.connect

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            raise AssertionError(f"the replay tried to reach {address!r} (no network in this test)")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


class Replay:
    """Rig (test_session.py) on the real checks + the cached video lesson, a scripted screen and notebook."""

    def __init__(self, tmp_path: Path, monkeypatch):
        folder = tmp_path / "nn-tensorflow"
        folder.mkdir()
        monkeypatch.setenv("TUT_WORKDIR", str(folder))
        monkeypatch.delenv("DEMO", raising=False)
        monkeypatch.delenv("MIYAGI_STAGE", raising=False)
        self.screen = FakeScreen()
        self.rig = Rig(folder, modules=Modules(demo=False, force_stubs="lesson,coach,finder,diagrams"),
                       screen=self.screen, with_inputs=True)
        self.rig.hub.history = deque(maxlen=None)  # the whole lesson (the hub keeps 500 by default)
        self.s = self.rig.s
        from server.orchestrator.workspace import Workspace

        self.s.workspace = Workspace(enabled=False, runner=lambda argv: True)
        self.s.check_wait_s = 0
        self.built: list[str] = []
        self.cells: list[dict] = []

        async def build_lesson(source_url, goal, workdir, on_progress=None, on_update=None, video_meta=None):
            self.built.append(source_url)
            return _graph()  # Gemini watched it once (06:13, 56.8 s); this is that build, from the cache

        async def no_judge(step, screen=None, files=None, **kw):
            return None

        self.s.m.build_lesson = build_lesson
        self.s.m.judge_step = no_judge

    # -- the app / learner
    @property
    def folder(self) -> Path:
        return self.rig.workdir

    async def settle(self) -> None:
        for _ in range(3):
            await self.rig.settle()
            await asyncio.sleep(0)

    async def start(self) -> None:
        """Build lesson on the picked video (preflight already shown): the real build path, from the cache."""
        await self.s.learn_url(URL, skip_preflight=True)
        await self.settle()

    async def work(self, secs: float = 3.0) -> None:
        """The learner types in VS Code (the editor or its terminal), then stops: past the typing guard."""
        self.rig.clock.t += 1
        self.rig.inputs.key()
        self.rig.clock.t += secs

    async def frame(self, **apps: list[str]) -> None:
        """The screen reader's next frame: exactly these apps' OCR lines (the reader only fires on a change)."""
        self.screen.text = {k: list(v) for k, v in apps.items()}
        await self.s.on_screen(None)
        await self.settle()

    def save_notebook(self) -> None:
        (self.folder / NB).write_text(_notebook(self.cells), encoding="utf-8")

    async def video_at(self, t: float) -> None:
        await self.s.video_state(t, True)
        await self.settle()

    # -- what the app was told
    def of(self, type_: str) -> list[dict]:
        return self.rig.of(type_)

    def started(self, sid: str) -> dict:
        return next(p for p in self.of("step.started") if p["stepId"] == sid)

    def rows(self, sid: str) -> dict[str, dict]:
        """The drawer's checklist for step `sid`: the last check.updated per check."""
        out: dict[str, dict] = {}
        for p in self.of("check.updated"):
            if p["stepId"] == sid:
                out[p["checkId"]] = p
        return out

    def passed(self, sid: str) -> bool:
        return any(p["stepId"] == sid and not p.get("skipped") for p in self.of("step.passed"))

    # -- correct work, step by step (as the learner did it in test 9, minus the bugs)
    async def do_s1(self) -> None:
        await self.work()
        await self.frame(Terminal=S1_TERMINAL)

    async def do_s2(self, lines: list[str] | None = None) -> None:
        self.cells = [_cell(STEPS["s2"]["code"], [])]
        self.save_notebook()
        await self.work()
        await self.frame(Code=[NB] + (lines or S2_CODE))

    async def do_s3(self, run: bool = True) -> None:
        self.cells = [_cell(STEPS["s2"]["code"], []), _cell(STEPS["s3"]["code"], S3_OUT if run else None)]
        self.save_notebook()
        await self.work()
        await self.frame(Code=[NB] + S3_CODE + (S3_OUT if run else []))

    async def to(self, sid: str) -> None:
        """Start the lesson and do every step before `sid` right."""
        await self.start()
        order = ["s1", "s2", "s3"]
        for prev in order[:order.index(sid)]:
            await getattr(self, f"do_{prev}")()
            assert self.passed(prev), (prev, self.rows(prev))
        assert self.s.step["id"] == sid


@pytest.fixture
def rp(tmp_path, monkeypatch) -> Replay:
    return Replay(tmp_path, monkeypatch)


def run(coro):
    return asyncio.run(coro)


def _xfail(v: str, why: str):
    return pytest.mark.xfail(strict=True, reason=f"{v} (test 9): {why}")


# ------------------------------------------------------------------ the lesson loads
def test_the_cached_lesson_loads_on_the_real_build_path(rp):
    run(rp.start())
    assert rp.built == [URL]  # the builder was asked once, for the picked video (no Gemini: the cache answered)
    ready = rp.of("lesson.ready")[0]
    assert ready["lesson"]["id"] == "lesson-5c0ea8a4" and ready["lesson"]["builtBy"] == "gemini"
    assert [s["id"] for s in ready["steps"]] == ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]
    assert ready["steps"][1]["video"] == {"videoId": "VPlFpvLOgtQ", "start": 73.0, "end": 126.0}
    assert rp.s.notebook_lesson and rp.s.workdir == str(rp.folder.resolve())
    assert rp.s.step["id"] == "s1" and rp.started("s1")["index"] == 1


# ------------------------------------------------------------------ s1: venv + Jupyter
def test_s1_tells_the_learner_one_concrete_thing(rp):
    run(rp.start())
    text = rp.started("s1")["instructions"]
    assert text and "Run Run" not in text


@_xfail("V6", "step 1 sends the learner to make a second venv (`python3 -m venv venv`) next to the lesson's .venv")
def test_s1_uses_the_lessons_venv_not_a_second_one(rp):
    run(rp.start())
    p = rp.started("s1")
    told = " ".join([p["instructions"], p.get("details") or "", p.get("code") or ""])
    assert not re.search(r"-m\s+venv\s+venv\b", told) and "venv/bin/activate" not in told.replace(".venv/", "")
    assert ".venv" in told


@_xfail("V1", "the start-of-step evaluation ran before the reader resumed: 'No terminal errors' passed with "
              "'screen reading is off, so nothing to flag'")
def test_s1_no_screen_check_passes_before_the_screen_is_read(rp):
    run(rp.start())
    rows = rp.rows("s1")
    assert rows and all(r["status"] != "pass" for r in rows.values()), rows
    assert not any("screen reading is off" in (r.get("detail") or "") for r in rows.values())


def test_s1_passes_once_the_terminal_shows_jupyter_running(rp):
    async def go():
        await rp.start()
        await rp.do_s1()

    run(go())
    rows = rp.rows("s1")
    assert {k: r["status"] for k, r in rows.items()} == {"s1c1": "pass", "s1c2": "pass", "s1c3": "pass"}
    assert rows["s1c1"]["detail"].startswith("seen")
    assert rp.of("step.passed")[0] == {"stepId": "s1", "nextStepId": "s2"}
    assert rp.started("s2")


def test_s1_does_not_pass_on_an_empty_terminal(rp):
    async def go():
        await rp.start()
        await rp.work()
        await rp.frame(Terminal=["(.venv) learner@mac nn-tensorflow % "])

    run(go())
    assert not rp.passed("s1") and rp.s.step["id"] == "s1"


# ------------------------------------------------------------------ s2: imports + MNIST
@_xfail("V5", "'Run Run the cell (Shift+Enter) in the VS Code terminal': run_command is a sentence, and Shift+Enter "
              "is a notebook action, not the terminal")
def test_s2_instruction_is_plain_and_points_at_the_notebook(rp):
    run(rp.to("s2"))
    text = rp.started("s2")["instructions"]
    assert "Run Run" not in text and "terminal" not in text.lower()


def test_s2_passes_on_the_code_and_no_errors(rp):
    async def go():
        await rp.to("s2")
        await rp.do_s2()

    run(go())
    assert rp.passed("s2"), rp.rows("s2")
    assert rp.started("s3")


@_xfail("V2", "`mnist.load_data()` wrapped to '…datasets.mnist.' / 'load_data()' never matched")
def test_s2_passes_when_load_data_wraps_onto_the_next_line(rp):
    async def go():
        await rp.to("s2")
        await rp.do_s2(S2_WRAPPED)

    run(go())
    assert rp.rows("s2")["s2c2"]["status"] == "pass"
    assert rp.passed("s2")


@_xfail("V2", "`load_data()` ran off the narrow editor's right edge; the notebook on disk had it")
def test_s2_passes_when_load_data_is_clipped_but_in_the_notebook(rp):
    async def go():
        await rp.to("s2")
        await rp.do_s2(S2_CLIPPED)

    run(go())
    assert rp.rows("s2")["s2c2"]["status"] == "pass"
    assert rp.passed("s2")


# ------------------------------------------------------------------ s3: shapes + plot
def test_s3_video_plays_its_clip_then_waits_for_the_checks(rp):
    """step.started -> seek to the clip + play; the player reaches the checkpoint -> pause (the app shows "Waiting for
    your checks"); the learner runs the cell -> step.passed (the next step resumes the video)."""
    async def go():
        await rp.to("s3")
        m = rp.rig.mark()
        await rp.video_at(151.0)  # the clip's end (2:31)
        assert not rp.passed("s3")
        await rp.do_s3()
        return [(e["type"], e["payload"]) for e in rp.rig.since(m)]

    after = run(go())
    seq = [(e["type"], e["payload"]) for e in rp.rig.events
           if e["type"].startswith("video.") or e["type"] in ("step.started", "step.passed")]
    i = next(k for k, (t, p) in enumerate(seq) if t == "step.started" and p["stepId"] == "s3")
    tail = [t if t != "video.seek" else (t, p["t"], p["play"]) for t, p in seq[i:]]
    assert tail[:4] == ["step.started", ("video.seek", 126.0, True), "video.play", "video.pause"], tail
    assert tail[4] == "step.passed" and seq[i + 4][1]["stepId"] == "s3"
    types_ = [t for t, _ in after]
    assert types_.index("video.pause") < types_.index("step.passed")


@_xfail("V3", "'Image shape line printed' passed on the SOURCE line print('Shape of the images…'), not its output")
def test_s3_output_checks_do_not_pass_on_the_source_alone(rp):
    async def go():
        await rp.to("s3")
        await rp.do_s3(run=False)

    run(go())
    rows = rp.rows("s3")
    assert rows["s3c1"]["status"] == "pass"  # the code is typed: that row may pass
    assert rows["s3c4"]["status"] != "pass", rows["s3c4"]
    assert not rp.passed("s3")


def test_s3_passes_once_the_cell_ran(rp):
    async def go():
        await rp.to("s3")
        await rp.do_s3()

    run(go())
    assert {k: r["status"] for k, r in rp.rows("s3").items()} == \
        {"s3c1": "pass", "s3c2": "pass", "s3c3": "pass", "s3c4": "pass"}
    assert rp.passed("s3") and rp.started("s4")


# ------------------------------------------------------------------ End
def test_end_closes_cleanly_with_nothing_left_running(rp, caplog):
    caplog.set_level(logging.ERROR)

    async def go():
        await rp.to("s3")
        await rp.s.end_lesson("stopped")  # the bar's End (main.py: app command end_lesson)
        await rp.settle()
        await asyncio.sleep(0.05)
        me = asyncio.current_task()
        return [t for t in asyncio.all_tasks() if t is not me and not t.done()]

    left = run(go())
    assert not left, left
    ended = rp.of("lesson.ended")[-1]
    assert ended == {"lessonId": "lesson-5c0ea8a4", "reason": "stopped"}
    assert rp.rig.types()[-3:] == ["video.pause", "lesson.ended", "status"]
    assert not [r for r in caplog.records if "destroyed but it is pending" in r.getMessage()]
