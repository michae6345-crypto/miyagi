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
BAR = "━━━━━━━━━━━━━━━━━━━━"
S5_OUT = [ln for e, acc, loss in [(1, 0.8763, 0.4312), (2, 0.9634, 0.1221), (3, 0.9752, 0.0815), (4, 0.9821, 0.0587),
                                  (5, 0.9862, 0.0441)]
          for ln in (f"Epoch {e}/5", f"1875/1875 {BAR} 3s 1ms/step - accuracy: {acc:.4f} - loss: {loss:.4f}")]
S6_OUT = [f"1/1 {BAR} 0s 45ms/step", "Class Probability"]  # the progress line, then the bar chart's title (OCR)
S7_OUT = [f"313/313 {BAR} 0s 1ms/step - accuracy: 0.9771 - loss: 0.0790",
          "Accuracy of the neural network on the 10000 test images: 97.71%"]
OUT = {"s2": [], "s3": S3_OUT, "s4": [], "s5": S5_OUT, "s6": S6_OUT, "s7": S7_OUT}
ORDER = ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]


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

    async def do_cell(self, sid: str, run: bool = True, lines: list[str] | None = None) -> None:
        """The step's cell typed into mnist.ipynb (and run: its output under it), saved; VS Code shows that cell."""
        self.cells = [c for c in self.cells if c["metadata"].get("step") != sid]
        cell = _cell(STEPS[sid]["code"], OUT[sid] if run else None)
        cell["metadata"]["step"] = sid
        self.cells.append(cell)
        self.save_notebook()
        await self.work()
        await self.frame(Code=[NB] + (lines or STEPS[sid]["code"].splitlines()) + (OUT[sid] if run else []))

    async def do(self, sid: str) -> None:
        await (self.do_s1() if sid == "s1" else self.do_cell(sid))

    async def do_s2(self, lines: list[str] | None = None) -> None:
        await self.do_cell("s2", lines=lines)

    async def do_s3(self, run: bool = True) -> None:
        await self.do_cell("s3", run=run)

    async def to(self, sid: str) -> None:
        """Start the lesson and do every step before `sid` right."""
        await self.start()
        for prev in ORDER[:ORDER.index(sid)]:
            await self.do(prev)
            assert self.passed(prev), (prev, self.rows(prev))
            await self.past_bounce(prev)
        assert self.s.step["id"] == sid

    async def past_bounce(self, sid: str) -> None:
        """Replay finding (s5 -> s6): the s6 run step finds the video's Untitled.ipynb 'still empty' and starts s5
        again; the learner answers its "Looks done?" with Confirm. A no-op once that bounce is fixed."""
        if self.s.step is not None and self.s.step["id"] == sid:
            await self.s.action("confirm")
            await self.settle()


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


def test_s1_uses_the_lessons_venv_not_a_second_one(rp):
    """V6 (fixed, venv_steps.py): step 1 sent the learner to make a second venv next to the lesson's .venv."""
    run(rp.start())
    p = rp.started("s1")
    told = " ".join([p["instructions"], p.get("details") or "", p.get("code") or ""])
    assert not re.search(r"-m\s+venv\s+venv\b", told) and "venv/bin/activate" not in told.replace(".venv/", "")
    assert ".venv" in told


def test_s1_no_screen_check_passes_before_the_screen_is_read(rp):
    """V1 (fixed, claude/t9-checks): 'No terminal errors' passed 'screen reading is off, so nothing to flag' before
    the reader resumed."""
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
    assert {"s1c2", "s1c3"} <= set(rows) and all(r["status"] == "pass" for r in rows.values()), rows
    assert rows["s1c2"]["detail"].startswith("seen")  # (V6 dropped the pip-output row s1c1: the setup card installs)
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


def test_s2_passes_when_load_data_wraps_onto_the_next_line(rp):
    async def go():
        await rp.to("s2")
        await rp.do_s2(S2_WRAPPED)

    run(go())
    assert rp.rows("s2")["s2c2"]["status"] == "pass"
    assert rp.passed("s2")


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


# ------------------------------------------------------------------ s4-s7, and the video around every step
S4_OUTPUT_LABEL = pytest.mark.xfail(strict=True, reason=(
    "REGRESSION 2b236a5 (claude/t9-checks, V3 fix): is_output_check reads s4c4 'Softmax output layer added' as an "
    "output check (label says 'output'), so s4 never passes on its code and the lesson stops at s4"))


@S4_OUTPUT_LABEL
@pytest.mark.parametrize("sid", ["s4", "s5", "s6", "s7"])
def test_later_steps_pass_on_the_cell_and_its_output(rp, sid):
    async def go():
        await rp.to(sid)
        await rp.do(sid)

    run(go())
    assert all(r["status"] == "pass" for r in rp.rows(sid).values()), rp.rows(sid)
    assert rp.passed(sid)


@S4_OUTPUT_LABEL
def test_the_whole_lesson_video_gates_and_resumes_in_order(rp):
    """All seven steps, the player reporting each clip's end before the learner's work: a step that plays its clip
    gets seek(start, play) + play after step.started, pause once the clip ends with checks still open, and nothing
    plays again until the step passes; the last pass plays the video on (the outro)."""
    async def go():
        await rp.start()
        for sid in ORDER:
            await rp.video_at(STEPS[sid]["video"]["end"])
            await rp.do(sid)
            assert rp.passed(sid), (sid, rp.rows(sid))
            await rp.past_bounce(sid)
        await rp.settle()

    run(go())
    ev = [(e["type"], e["payload"]) for e in rp.rig.events
          if e["type"].startswith("video.") or e["type"] in ("step.started", "step.passed")]
    for sid in ORDER:
        i = next(k for k, (t, p) in enumerate(ev) if t == "step.started" and p["stepId"] == sid)
        j = next(k for k, (t, p) in enumerate(ev) if t == "step.passed" and p["stepId"] == sid)
        mid = [t if t != "video.seek" else (t, p["t"], p["play"]) for t, p in ev[i + 1:j]]
        if mid:  # the clip played: seek to its start, play, pause at its end
            assert mid == [("video.seek", STEPS[sid]["video"]["start"], True), "video.play", "video.pause"], (sid, mid)
    assert ev[-1] == ("video.play", {}) and ev[-2][0] == "step.passed" and ev[-2][1]["stepId"] == "s7"
    assert rp.s.phase == "done"


@_xfail("V4 family (replay finding, no owner yet)", "after s5 passes, the s6 run step resolves the video's "
        "Untitled.ipynb, finds it 'still empty' and starts s5 again ('Untitled.ipynb is still empty' card, s5 told to "
        "'create Untitled.ipynb'): session._typing_step_for_empty_run")
def test_s5_to_s6_does_not_bounce_back_over_the_videos_notebook_name(rp):
    async def go():
        await rp.to("s5")
        await rp.do("s5")

    run(go())
    assert rp.s.step["id"] == "s6"
    assert [p["stepId"] for p in rp.of("step.started")].count("s5") == 1
    assert not [c for c in rp.of("card") if "Untitled.ipynb" in f"{c.get('title')} {c.get('body')}"]


def test_no_step_says_run_run_or_sends_a_notebook_cell_to_the_terminal(rp):
    """V5 (fixed): every Run-the-cell step said 'Run Run the cell (Shift+Enter) in the VS Code terminal'."""
    async def go():
        await rp.start()
        for sid in ORDER:
            await rp.do(sid)

    run(go())
    for p in rp.of("step.started"):
        assert "Run Run" not in p["instructions"], p
        assert not ("Shift+Enter" in p["instructions"] and "terminal" in p["instructions"].lower()), p


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
