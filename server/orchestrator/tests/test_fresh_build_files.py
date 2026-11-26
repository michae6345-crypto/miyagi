"""A FRESH build of a lesson whose folder is reused starts with a clean set of learner files (Michael, Nov 15 7:19: test
9's mnist.ipynb passed s1-s3 by itself on a new build); the last run's files move to .miyagi-previous/<time>/, nothing
deleted. A build that continues a saved place (an engine restart's save, never ended) keeps them."""

from __future__ import annotations

import json

import pytest

from server.orchestrator import stubs
from server.orchestrator.tests.test_session import Rig, run
from server.workspace import core


def _old_run(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "mnist.ipynb").write_text('{"cells": [{"source": "model.fit(x, y)"}]}', encoding="utf-8")
    (folder / "train.py").write_text("model.fit(x, y)\n", encoding="utf-8")
    (folder / "starter.py").write_text("# TODO\n", encoding="utf-8")  # prepare()'s starter: stays
    (folder / "README.md").write_text("# lesson\n", encoding="utf-8")
    (folder / ".venv" / "bin").mkdir(parents=True)
    (folder / ".vscode").mkdir()
    (folder / "tutorial").mkdir()
    (folder / "tutorial" / "mnist.ipynb").write_text("{}", encoding="utf-8")  # the video's download: stays
    sf = core._state_file(folder)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"scaffolded": True, "files": ["starter.py"], "readme": "README.md"}), encoding="utf-8")


def test_set_aside_moves_only_the_learners_files(tmp_path):
    folder = tmp_path / "lessons" / "nn-tf-1ac5c7"
    _old_run(folder)
    dest = core.set_aside_previous(folder)
    assert dest is not None and dest.parent == folder / core.PREVIOUS_DIR
    assert sorted(p.name for p in dest.iterdir()) == ["mnist.ipynb", "train.py"]
    assert not (folder / "mnist.ipynb").exists() and not (folder / "train.py").exists()
    for kept in ("starter.py", "README.md", ".venv", ".vscode", "tutorial/mnist.ipynb"):
        assert (folder / kept).exists(), kept
    assert core.set_aside_previous(folder) is None  # nothing left to move: no empty folder


@pytest.fixture
def built(tmp_path, monkeypatch):
    from server.orchestrator import workspace as wsmod

    monkeypatch.delenv("TUT_WORKDIR", raising=False)
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    from server.workspace import paths

    lesson = stubs.load_fixture_lesson()
    folder = (paths.lessons_root() / paths.folder_name(lesson)).resolve()
    _old_run(folder)
    monkeypatch.setattr(wsmod, "prepare", lambda graph, goal: str(folder))  # "reusing lesson folder"

    def go():
        rig = Rig(tmp_path / "unused")

        async def build(url, goal, workdir, **kw):
            return json.loads(json.dumps(lesson))

        rig.s.m.build_lesson = build

        async def main():
            await rig.s.learn_url("https://www.youtube.com/watch?v=VPlFpvLOgtQ", skip_preflight=True)
            await rig.settle()

        run(main())
        return rig

    return folder, lesson, go


def test_fresh_build_starts_without_the_last_runs_notebook(built):
    folder, lesson, go = built
    rig = go()
    assert rig.of("lesson.ready") and rig.s.workdir == str(folder)
    assert not (folder / "mnist.ipynb").exists()
    prev = list((folder / core.PREVIOUS_DIR).iterdir())
    assert len(prev) == 1 and (prev[0] / "mnist.ipynb").is_file()  # moved, not deleted
    assert rig.s.idx == 0 and not rig.of("step.passed")  # nothing passed on the old files


def test_build_that_continues_a_save_keeps_the_files(built):
    from server.sessions import store

    folder, lesson, go = built
    store.save({"lessonId": lesson["lesson"]["id"], "stepIndex": 2})  # an engine restart's save, never ended
    go()
    assert (folder / "mnist.ipynb").is_file() and not (folder / core.PREVIOUS_DIR).exists()


def test_never_a_folder_the_lesson_was_redirected_to(tmp_path, monkeypatch):
    from server.orchestrator import workspace as wsmod

    monkeypatch.delenv("TUT_WORKDIR", raising=False)
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    mine = tmp_path / "my-project"  # the learner's own folder (adopt_folder)
    mine.mkdir()
    (mine / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert wsmod.set_aside_previous(str(mine), stubs.load_fixture_lesson()) is None and (mine / "app.py").is_file()


def test_build_after_the_learner_ended_it_is_fresh(built):
    from server.sessions import store

    folder, lesson, go = built
    store.save({"lessonId": lesson["lesson"]["id"], "stepIndex": 2, "stopped": True})  # End: only Continue restores
    go()
    assert not (folder / "mnist.ipynb").exists() and (folder / core.PREVIOUS_DIR).is_dir()
