"""Desktop test 10 (Nov 15): the engine had no idea a notebook cell ran (R1), only the checks knew the video's
Untitled.ipynb is the learner's mnist.ipynb (R2), a VS Code notebook lesson's checks read every window (R3), and a
ScreenCaptureKit TCC refusal was retried at once (R5). On the cached t10 lesson (test_video_replay's rig: real session +
real checks, no Claude / Gemini, no network) and the learner's own notebook (fixtures/t10_mnist.ipynb, read only copy).

    env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u BRIGHTDATA_API_KEY python -m pytest server/orchestrator/tests/test_t10_nbrun.py -q
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from server.orchestrator import notebook_runs
from server.orchestrator.tests.test_video_replay import NB, Replay, run
from server.orchestrator.tests.test_video_replay import _offline  # noqa: F401 - autouse: no keys, no network

FIXTURE = Path(__file__).parent / "fixtures" / "t10_mnist.ipynb"


@pytest.fixture
def rp(tmp_path, monkeypatch) -> Replay:
    return Replay(tmp_path, monkeypatch)


def _nb() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _write(rp: Replay, nb: dict) -> Path:
    p = rp.folder / NB
    p.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    return p


def _unrun(cell: dict) -> dict:
    c = copy.deepcopy(cell)
    c["execution_count"], c["outputs"] = None, []
    return c


def _nb_runs(rp: Replay) -> list:
    return [r for r in rp.s.runs.values() if r.run_id.startswith(notebook_runs.PREFIX)]


async def _at_step(rp: Replay, idx: int, nb: dict) -> None:
    """Lesson running, the notebook as `nb` on disk, step `idx` just started (its snapshot taken)."""
    await rp.to("s2")
    _write(rp, nb)
    await rp.s.start_step(idx)
    await rp.settle()


async def _saved(rp: Replay, nb: dict) -> None:
    """VS Code autosaves the notebook; the watcher reports the change."""
    p = _write(rp, nb)
    await rp.s.on_file_change([str(p)])
    await rp.settle()


# ------------------------------------------------------------------ R1: a cell the learner ran is a run of the step
def test_a_cell_whose_execution_count_changed_is_a_run_and_grades_the_metric(rp):
    full = _nb()
    pre = {**full, "cells": [*full["cells"][:3], _unrun(full["cells"][3])]}  # s5's cell typed, not run yet
    post = {**full, "cells": full["cells"][:4]}  # ran: [19], the 5 epochs' accuracy lines under it

    async def go():
        await _at_step(rp, 4, pre)
        assert rp.s.step["id"] == "s5" and not _nb_runs(rp)
        await _saved(rp, post)

    run(go())
    runs = _nb_runs(rp)
    assert len(runs) == 1, [r.run_id for r in rp.s.runs.values()]
    r = runs[0]
    assert r.exit_code == 0 and "[19]" in r.command
    out = "\n".join(r.output_tail)
    assert "accuracy: 0.9858" in out and "\x1b" not in out  # ANSI stripped
    assert "Number of images" not in out  # only the cell that ran, never the earlier cells' outputs
    rows = rp.rows("s5")
    assert rows["s5c3"]["status"] == "pass", rows["s5c3"]  # metric_threshold read the run's output
    assert rows["s5-ran"]["status"] == "pass", rows["s5-ran"]
    assert rp.passed("s5"), rows  # the code is in the notebook (its precision checks) and the cell ran


def test_an_unchanged_execution_count_is_never_a_run(rp):
    full = _nb()
    ran = {**full, "cells": full["cells"][:4]}

    async def go():
        await _at_step(rp, 4, ran)  # s5's cell already ran before the step began
        edited = copy.deepcopy(ran)
        edited["cells"][3]["source"] = [*edited["cells"][3]["source"], "\n# a comment"]  # edited + saved, not run
        await _saved(rp, edited)

    run(go())
    assert not _nb_runs(rp)
    rows = rp.rows("s5")
    assert rows["s5-ran"]["status"] == "pending" and "Shift+Enter" in rows["s5-ran"]["detail"], rows["s5-ran"]
    assert not rp.passed("s5")


def test_an_error_cell_is_a_failed_run_and_the_coach_explains_it_at_once(rp, monkeypatch):
    full = _nb()
    typo = copy.deepcopy(full["cells"][0])
    typo["execution_count"] = 3
    typo["outputs"] = [{"output_type": "error", "ename": "NameError", "evalue": "name 'tf' is not defined",
                        "traceback": ["\x1b[0;31m---------------------------------------------------------------\x1b[0m",
                                      "\x1b[0;31mNameError\x1b[0m    Traceback (most recent call last)",
                                      "Cell \x1b[0;32mIn[3], line 7\x1b[0m",
                                      "\x1b[0;31mNameError\x1b[0m: name 'tf' is not defined"]}]
    spoken: list[tuple[str, str]] = []
    real = type(rp.s)._consider_speaking

    def record(self, reason, step, failed, ctx):
        spoken.append((reason, step["id"], ctx.exit_code))
        return real(self, reason, step, failed, ctx)

    monkeypatch.setattr(type(rp.s), "_consider_speaking", record)

    async def go():
        await _at_step(rp, 1, {**full, "cells": [_unrun(full["cells"][0])]})
        assert rp.s.step["id"] == "s2"
        await _saved(rp, {**full, "cells": [typo]})

    run(go())
    runs = _nb_runs(rp)
    assert len(runs) == 1 and runs[0].exit_code == 1
    out = "\n".join(runs[0].output_tail)
    assert "NameError: name 'tf' is not defined" in out and "\x1b" not in out
    assert rp.rows("s2")["s2-ran"]["status"] == "fail"
    assert ("breakpoint", "s2", 1) in spoken, spoken  # the run_end breakpoint: explained now, not on the idle gate
    assert not rp.passed("s2")


def test_the_replayed_lesson_still_passes_each_notebook_step_on_its_run(rp):
    """test 9's replay, step by step: every notebook step passes on the cell run it saved (a run row, green)."""
    async def go():
        await rp.to("s4")

    run(go())
    for sid in ("s2", "s3"):
        assert rp.passed(sid) and rp.rows(sid)[f"{sid}-ran"]["status"] == "pass", (sid, rp.rows(sid))


def test_a_colab_lesson_has_no_notebook_run_row(rp):
    async def go():
        await rp.to("s2")

    run(go())
    rp.s.graph["lesson"]["goal"] = "Train it in Google Colab"
    assert not notebook_runs.watching(rp.s)
    assert notebook_runs.need_run(rp.s, rp.s.step, [], {"passed": True}) is None


# ------------------------------------------------------------------ R2: the video's notebook is the learner's
def test_resolve_file_finds_the_learners_notebook_for_the_videos_untitled(tmp_path):
    from server.orchestrator.workspace import resolve_file

    (tmp_path / "mnist.ipynb").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    assert resolve_file(tmp_path, "Untitled.ipynb") == tmp_path / "mnist.ipynb"
    assert resolve_file(tmp_path, "missing.py") is None
    assert resolve_file(tmp_path / "nowhere", "Untitled.ipynb") is None


def test_the_coach_excerpt_reads_the_learners_notebook_cells(rp):
    async def go():
        await rp.to("s2")
        _write(rp, _nb())

    run(go())
    text, file = rp.s._code_excerpt(rp.s.step)
    assert file and file.endswith(".ipynb") and "import tensorflow as tf" in text and "# %% [cell" in text


# ------------------------------------------------------------------ R3: a VS Code notebook lesson reads VS Code only
def test_a_vscode_notebook_lessons_checks_stay_on_vscode(rp):
    run(rp.start())
    s2 = next(s for s in rp.s.graph["steps"] if s["id"] == "s2")
    assert {c.get("app") for c in s2["checks"]} == {"Code"}


def test_a_colab_lessons_checks_read_any_window():
    from server.orchestrator.session import is_colab_lesson, unscope_editor_apps

    g = {"lesson": {"title": "MNIST in Google Colab"}, "steps": [
        {"id": "s1", "title": "t", "checks": [{"id": "c", "type": "screen_contains", "app": "Code", "pattern": "x"}]}]}
    assert is_colab_lesson(g)
    unscope_editor_apps(g)
    assert "app" not in g["steps"][0]["checks"][0]


# ------------------------------------------------------------------ R5: a TCC refusal backs off 5 min at once
def test_a_tcc_refusal_is_not_retried_and_backs_off_300s():
    sck = pytest.importorskip("server.screen.sck")
    from server.screen.reader import ScreenReader

    err = ('Error Domain=com.apple.ScreenCaptureKit.SCStreamErrorDomain Code=-3801 "The user declined TCCs for '
           'application, window, display capture"')
    cap = object.__new__(sck.SCKCapturer)
    calls = []

    def once():
        calls.append(1)
        raise sck.SCKDeclined(f"SCShareableContent failed: {err}")

    cap._capture_once = once
    with pytest.raises(sck.SCKDeclined):
        cap.capture()
    assert len(calls) == 1  # no "retrying once with fresh content" (it froze capture for 1.5 s)
    assert sck._declined(err) and not sck._declined("connection interrupted")

    reader = object.__new__(ScreenReader)
    reader.use_sck, reader._sck_retry_at, reader._sck_streak, reader._sck = True, 0.0, 0, cap
    import time

    assert reader._sck_capture() is None
    assert reader._sck_retry_at - time.time() > 290
