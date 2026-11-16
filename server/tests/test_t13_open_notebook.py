"""Nov 15 10:45 (Michael): a video notebook lesson opened VS Code on README.md, because the auto-open runs before
step 1 starts and the step names no file; the drawer then covered the Explorer. The lesson's notebook opens first."""
from types import SimpleNamespace

from server.orchestrator import lesson_notebook


def _s(tmp_path, notebook_lesson=True, nb="mnist.ipynb"):
    return SimpleNamespace(notebook_lesson=notebook_lesson, workdir=str(tmp_path),
                           graph={"lesson": {"id": "l1", "notebook": nb}})


def test_first_file_is_the_lesson_notebook_and_is_made_if_missing(tmp_path):
    s = _s(tmp_path)
    f = lesson_notebook.first_file(s)
    assert f is not None and f.endswith("mnist.ipynb")
    assert (tmp_path / "mnist.ipynb").is_file()


def test_first_file_keeps_the_learners_notebook(tmp_path):
    (tmp_path / "mnist.ipynb").write_text('{"cells": [{"cell_type": "code", "source": ["x = 1"]}]}')
    f = lesson_notebook.first_file(_s(tmp_path))
    assert f.endswith("mnist.ipynb")
    assert "x = 1" in (tmp_path / "mnist.ipynb").read_text()


def test_first_file_none_outside_notebook_lessons(tmp_path):
    assert lesson_notebook.first_file(_s(tmp_path, notebook_lesson=False)) is None
    assert lesson_notebook.first_file(_s(tmp_path, nb="nn.py")) is None
