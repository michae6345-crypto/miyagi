"""active_editor / wrong_folder / adopt_folder / new-lesson window reuse. Michael's live case: he typed in
calculator.py of an OLDER lesson folder (i-wanna-build-a-calc-in-python-in-vs-cods-9808de, unsaved) while the current
lesson (python-calculator-e430dc) was open in a second window, so every check said "not seen in Code"."""

from __future__ import annotations

import pytest

from server.workspace import active as A
from server.workspace import core
from server.workspace import editor as E

OLD = "i-wanna-build-a-calc-in-python-in-vs-cods-9808de"
NEW = "python-calculator-e430dc"
VSC = {"id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "cli": "/usr/local/bin/code",
       "bundle": "com.microsoft.VSCode", "process": "Code"}


@pytest.fixture
def lessons(tmp_path, monkeypatch):
    root = tmp_path / "lessons"
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(root))
    old, new = root / OLD, root / NEW
    for d in (old, new):
        d.mkdir(parents=True)
    (old / "calculator.py").write_text("def add(a, b):\n    return a + b  # Michael's work\n")
    (new / "calculator.py").write_text('"""Calculator."""\n# Step 1: add()\n')
    (new / "README.md").write_text("# Python calculator\n_Prepared by miyagi._\n")
    (new / "data").mkdir()
    (new / "data" / "cases.csv").write_text("a,b\n1,2\n")
    E.reset_open_state()
    yield root, old, new
    E.reset_open_state()


def test_parse_title():
    assert A.parse_title(f"● calculator.py — {OLD}") == {"file": "calculator.py", "folder_name": OLD, "dirty": True}
    assert A.parse_title(f"calculator.py — {NEW}") == {"file": "calculator.py", "folder_name": NEW, "dirty": False}
    assert A.parse_title(NEW) == {"file": None, "folder_name": NEW, "dirty": False}
    assert A.parse_title(f"Welcome — {NEW}")["file"] is None and A.parse_title("") is None
    assert A.parse_title("app.js — demo — Visual Studio Code")["folder_name"] == "demo"


def test_active_editor_from_window_titles(lessons):
    root, old, new = lessons
    act = A.active_editor(titles=[f"● calculator.py — {OLD}", f"calculator.py — {NEW}"], ax=lambda: None)
    assert act == {"folder": str(old.resolve()), "folder_name": OLD, "file": "calculator.py",
                   "path": str((old / "calculator.py").resolve()), "dirty": True, "title": f"● calculator.py — {OLD}",
                   "miyagi_lesson": True, "source": "title"}
    other = A.active_editor(titles=["main.go — my-real-project"], ax=lambda: None)
    assert other["folder"] is None and other["folder_name"] == "my-real-project" and not other["miyagi_lesson"]
    assert A.active_editor(titles=[], ax=lambda: None) is None


def test_active_editor_from_accessibility_any_folder(lessons, tmp_path):
    root, old, _ = lessons
    act = A.active_editor(ax=lambda: {"title": f"● calculator.py — {OLD}", "document": old / "calculator.py"})
    assert act["source"] == "ax" and act["folder"] == str(old.resolve()) and act["dirty"] and act["miyagi_lesson"]
    proj = tmp_path / "work" / "proj"
    (proj / "src").mkdir(parents=True)
    act = A.active_editor(ax=lambda: {"title": "calculator.py — proj", "document": proj / "src" / "calculator.py"})
    assert act["folder"] == str(proj) and act["path"].endswith("src/calculator.py") and not act["miyagi_lesson"]


def test_wrong_folder_michaels_case(lessons):
    root, old, new = lessons
    titles = [f"● calculator.py — {OLD}", f"calculator.py — {NEW}"]
    wf = A.wrong_folder(new, ["calculator.py"], titles=titles)
    assert wf["learner_folder"] == str(old.resolve()) and wf["lesson_folder"] == str(new.resolve())
    assert wf["file"] == "calculator.py" and wf["dirty"] and wf["can_adopt"] and wf["learner_is_miyagi_lesson"]
    # default lesson files = what's in the lesson folder
    assert A.wrong_folder(new, titles=titles)["file"] == "calculator.py"
    # in the right folder, or a file the lesson doesn't use: nothing to report
    assert A.wrong_folder(new, titles=[f"calculator.py — {NEW}"]) is None
    assert A.wrong_folder(new, ["calculator.py"], titles=[f"notes.txt — {OLD}"]) is None
    # outside ~/miyagi/lessons by title only: reported, but no path, so "use this folder" isn't offered
    wf = A.wrong_folder(new, ["calculator.py"], titles=["calculator.py — my-real-project"])
    assert wf["learner_folder"] is None and wf["learner_folder_name"] == "my-real-project" and not wf["can_adopt"]


def test_adopt_folder_copies_missing_never_overwrites_or_deletes(lessons):
    root, old, new = lessons
    before = (old / "calculator.py").read_text()
    res = A.adopt_folder(new, old)
    assert res["workdir"] == str(old.resolve())
    assert sorted(res["copied"]) == ["README.md", "data/cases.csv"]
    assert res["skipped"] == ["calculator.py: already there"]
    assert (old / "calculator.py").read_text() == before  # Michael's work untouched
    assert (new / "calculator.py").exists() and (new / "README.md").exists()  # nothing deleted
    # prepare() for this lesson now returns the learner's folder
    assert core.read_state(new)["redirect"] == str(old.resolve())


def test_prepare_follows_the_redirect(lessons, monkeypatch):
    root, old, new = lessons
    graph = {"lesson": {"id": "lesson-calc", "title": "Python calculator"}, "sources": [], "steps": []}
    folder = root / A.paths.folder_name(graph)
    folder.mkdir()
    core.set_redirect(folder, old)
    assert core.prepare(graph, "x", client=None) == old


@pytest.mark.parametrize("bad", ["/", "~", "LESSONS_ROOT", "NEW/sub"])
def test_adopt_refuses_unsafe_targets(lessons, bad):
    root, old, new = lessons
    (new / "sub").mkdir(exist_ok=True)
    target = {"/": "/", "~": "~", "LESSONS_ROOT": str(root), "NEW/sub": str(new / "sub")}[bad]
    with pytest.raises(ValueError):
        A.adopt_folder(new, target)


def test_new_lesson_reuses_an_older_miyagi_window(lessons, monkeypatch):
    root, old, new = lessons
    monkeypatch.setattr(E, "preferred_editor", lambda installed=None: VSC)
    calls = []
    run = lambda a: calls.append(a) or True  # noqa: E731
    wins = lambda: A.vscode_windows([f"● calculator.py — {OLD}"])  # noqa: E731
    rep = E.open_lesson_editor(new, "calculator.py", lesson_id="L", runner=run, focus=lambda: None, windows=wins,
                               trusted=lambda: False, previous=None, arrange_windows=False)
    assert rep["reused_window"] and calls[0][:3] == ["/usr/local/bin/code", "-r", str(new.resolve())]


def test_never_reuse_windows_outside_lessons_or_when_already_open(lessons):
    root, old, new = lessons
    assert not E.reuse_lesson_window(new, windows=lambda: A.vscode_windows(["main.go — my-real-project"]))
    assert not E.reuse_lesson_window(new, windows=lambda: A.vscode_windows([f"a.py — {OLD}", f"calculator.py — {NEW}"]))
    assert not E.reuse_lesson_window(new, windows=lambda: [])
    assert not E.reuse_lesson_window(new, windows=lambda: (_ for _ in ()).throw(RuntimeError("no list")))
    assert E.reuse_lesson_window(new, windows=lambda: A.vscode_windows([f"a.py — {OLD}"]))


def test_frontmost_uses_launch_services(monkeypatch):
    class R:
        def __init__(self, out):
            self.stdout = out

    outs = iter(['ASN:0x0-0x19b19b:\n', '"CFBundleIdentifier"="com.microsoft.VSCode"\n"LSDisplayName"="Code"\n'])
    monkeypatch.setattr(E.subprocess, "run", lambda *a, **k: R(next(outs)))
    assert E._frontmost() == ("com.microsoft.VSCode", "Code")
