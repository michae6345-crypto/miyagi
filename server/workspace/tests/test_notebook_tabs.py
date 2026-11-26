"""Nov 26 user test (TensorFlow MNIST notebook lesson): lesson files open as tabs of the lesson's own VS Code window, a
notebook never with `-g`, the folder's interpreter is the lesson .venv, and the layout waits long enough for a cold
VS Code. No real VS Code: every runner is faked."""

from __future__ import annotations

import json

import pytest

from server.workspace import core
from server.workspace import editor as E

VSC = {"id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "cli": "/usr/local/bin/code",
       "bundle": "com.microsoft.VSCode", "process": "Code"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.setattr(E, "installed_editors", lambda: [VSC])
    monkeypatch.setattr(E, "preferred_editor", lambda installed=None: VSC)
    monkeypatch.setattr(E, "frontmost_app", lambda skip=None: None)
    monkeypatch.setattr(E, "_lesson_window_alive", lambda folder: True)
    E.reset_open_state()
    yield
    E.reset_open_state()


def _lesson(tmp_path) -> tuple:
    folder = tmp_path / "lessons" / "build-your-first-nn-5c0ea8"
    folder.mkdir(parents=True)
    nb = folder / "mnist.ipynb"
    nb.write_text("{}", encoding="utf-8")
    py = folder / "train.py"
    py.write_text("x\n", encoding="utf-8")
    return folder.resolve(), nb.resolve(), py.resolve()


def test_file_args_never_put_dash_g_on_a_notebook():
    assert E.file_args("/l/a.py") == ["-g", "/l/a.py"]
    assert E.file_args("/l/mnist.ipynb") == ["/l/mnist.ipynb"] and E.file_args("/l/M.IPYNB") == ["/l/M.IPYNB"]
    assert E.file_args(None) == []


def test_jumps_into_a_lesson_file_name_the_lesson_folder_not_the_last_window(tmp_path):
    folder, nb, py = _lesson(tmp_path)
    assert E.lesson_folder_of(py) == folder and E.lesson_folder_of(nb) == folder
    assert E.lesson_folder_of(tmp_path / "elsewhere.py") is None
    # `code <folder> -g file:line`: the tab opens in the window that has the lesson folder (`-r` took the last active one)
    assert E.goto_argv(py, 7) == [VSC["cli"], str(folder), "-g", f"{py}:7"]
    assert E.goto_argv(nb, 3) == [VSC["cli"], str(folder), str(nb)]  # a notebook: a tab, no line
    other = tmp_path / "proj" / "main.py"
    assert E.goto_argv(other, 2) == [VSC["cli"], "-r", "-g", f"{other}:2"]  # not a lesson file: as before
    assert E.goto_argv(other, 2, folder=tmp_path / "proj") == [VSC["cli"], str(tmp_path / "proj"), "-g", f"{other}:2"]


def test_first_open_shows_the_notebook_as_a_tab_of_the_lesson_window(tmp_path):
    folder, nb, _ = _lesson(tmp_path)
    calls = []
    rep = E.open_lesson_editor(folder, str(nb), lesson_id="L", explicit=True, runner=lambda a: calls.append(a) or True,
                               focus=lambda: None, background=False, arrange_windows=False, trusted=lambda: False,
                               previous=None, windows=lambda: [])
    assert rep["opened"]
    cli = [c for c in calls if c[0] == VSC["cli"]]
    assert cli == [[VSC["cli"], str(folder), str(nb)]]  # no -g, no -n, no -r
    # later: the learner's Open brings the same window forward on the notebook, still a tab
    calls.clear()
    E.open_lesson_editor(folder, str(nb), lesson_id="L", explicit=True, runner=lambda a: calls.append(a) or True)
    assert calls == [[VSC["cli"], str(folder), str(nb)]]


def test_text_files_still_open_with_dash_g(tmp_path):
    folder, _, py = _lesson(tmp_path)
    calls = []
    E.open_lesson_editor(folder, str(py), lesson_id="L2", explicit=True, runner=lambda a: calls.append(a) or True,
                         focus=lambda: None, background=False, arrange_windows=False, trusted=lambda: False,
                         previous=None, windows=lambda: [])
    assert [c for c in calls if c[0] == VSC["cli"]] == [[VSC["cli"], str(folder), "-g", str(py)]]


def test_the_layout_waits_for_a_cold_vs_code():
    import inspect

    assert E.ARRANGE_WAIT_S >= 20
    assert inspect.signature(E.arrange).parameters["wait_s"].default == E.ARRANGE_WAIT_S


def test_notebook_folder_points_vs_code_at_the_lesson_venv(tmp_path):
    folder = tmp_path / "nb"
    folder.mkdir()
    (folder / "mnist.ipynb").write_text("{}", encoding="utf-8")  # a notebook lesson: no .py, no .venv yet
    assert core.is_python_folder(folder)
    assert core.ensure_python_terminal(folder)
    got = json.loads((folder / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert got["python.defaultInterpreterPath"] == "${workspaceFolder}/.venv/bin/python"
    # the learner's own choice wins
    (folder / ".vscode" / "settings.json").write_text(json.dumps({"python.defaultInterpreterPath": "/mine"}), encoding="utf-8")
    core.ensure_python_terminal(folder)
    assert json.loads((folder / ".vscode" / "settings.json").read_text(encoding="utf-8"))["python.defaultInterpreterPath"] == "/mine"


def test_the_lesson_notebook_carries_the_venv_kernelspec():
    from server.lesson.notebook_steps import empty_notebook

    ks = empty_notebook()["metadata"]["kernelspec"]
    assert ks == {"display_name": ".venv", "language": "python", "name": "python3"}
