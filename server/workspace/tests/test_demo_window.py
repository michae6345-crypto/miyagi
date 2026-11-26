"""Nov 24 (the 1517 demo): one VS Code window for the lesson, sized calmly. Fakes only: no real editor, window list,
companion or Accessibility call."""

from __future__ import annotations

import json

import pytest

from server.workspace import editor as E
from server.workspace import vscode_ext

CODE = ("com.microsoft.VSCode", "Code")
VSC = {"id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "cli": "/usr/local/bin/code",
       "bundle": "com.microsoft.VSCode", "process": "Code"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.delenv("MIYAGI_ARRANGE", raising=False)
    E.reset_open_state()
    monkeypatch.setattr(E, "preferred_editor", lambda installed=None: VSC)
    monkeypatch.setattr(E, "editor_pid", lambda ed: 222)  # VS Code is running
    monkeypatch.setattr(E, "frontmost_app", lambda skip=None: None)
    monkeypatch.setattr(vscode_ext, "windows", lambda timeout=None: [])
    monkeypatch.setattr(E, "_titles_readable", lambda: False)
    from server.workspace import active

    monkeypatch.setattr(active, "vscode_windows", lambda titles=None: [])
    yield
    E.reset_open_state()


def _folder(tmp_path):
    f = tmp_path / "lessons" / "a-neural-net-from-scratch-da5236"
    f.mkdir(parents=True)
    (f / "nn.py").write_text("import numpy as np\n", encoding="utf-8")
    return f


# --------------------------------------------------------------------------------------- is the window still up?

def test_the_companion_decides_when_it_answers(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    monkeypatch.setattr(vscode_ext, "windows", lambda timeout=None: [{"port": 8791, "folders": [str(folder)]}])
    assert E._lesson_window_alive(folder) is True
    monkeypatch.setattr(vscode_ext, "windows", lambda timeout=None: [{"port": 8791, "folders": [str(tmp_path / "x")]}])
    assert E._lesson_window_alive(folder) is False  # companions answered, none has the lesson folder


def test_no_titles_and_no_companion_is_unknown_not_closed(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    assert E._lesson_window_alive(folder) is True  # titles unreadable (no Screen Recording): keep at-most-once
    monkeypatch.setattr(E, "_titles_readable", lambda: True)
    assert E._lesson_window_alive(folder) is False  # titles readable and none: VS Code runs with no window
    monkeypatch.setattr(E, "editor_pid", lambda ed: None)
    assert E._lesson_window_alive(folder) is False  # VS Code quit


def test_a_second_open_never_reopens_or_adds_a_window(tmp_path):
    folder = _folder(tmp_path)
    calls: list[list[str]] = []

    def run(argv):
        calls.append(list(argv))
        return True

    quiet = {"trusted": lambda: False, "previous": None, "arrange_windows": False}
    first = E.open_lesson_editor(folder, "nn.py", lesson_id="L", runner=run, focus=lambda: CODE,
                                 windows=lambda: [], **quiet)
    assert first["opened"] and not first.get("already")
    # Start pressed: explicit, the real-call path that checks the window (no titles, no companion: unknown)
    again = E.open_lesson_editor(folder, "nn.py", lesson_id="L", runner=run, explicit=True, focus=lambda: CODE, **quiet)
    assert again["already"]  # a bring-forward, never a second first open ("closed since it opened")
    code = [c for c in calls if c[0] == VSC["cli"]]
    want = [VSC["cli"], str(folder.resolve()), "-g", str((folder / "nn.py").resolve())]
    assert code == [want, want] and not any("-n" in c for c in calls)


# --------------------------------------------------------------------------------------- the calm layout

class FakeAX:
    def __init__(self):
        self.log: list = []

    def folder_window(self, pid, folder):
        return "lesson"

    def focused_window(self, pid):
        return "lesson"

    def is_fullscreen(self, w):
        return False

    def set_frame(self, w, x, y, wd, h):
        self.log.append(("frame", w, x, y, wd, h))
        return True

    def other_lesson_windows(self, pid, folder):
        return [("old-lesson-abc123", "old")]

    def minimize(self, w):
        self.log.append(("minimize", w))
        return True

    def raise_window(self, w):
        self.log.append(("raise", w))


def test_lesson_window_fills_the_screen_beside_the_drawer(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    monkeypatch.setattr(E, "NATIVE_FULLSCREEN", False)
    monkeypatch.setattr(E, "panel_rect", lambda: None)
    from server.workspace import layout as L

    monkeypatch.setattr(E, "lesson_screen", lambda: L.Screen(frame=L.Rect(0, 0, 1728, 1117), visible=L.Rect(0, 0, 1728, 1117)))
    ax, rep = FakeAX(), {}
    E.make_fullscreen(VSC, rep, folder=str(folder), ax=ax, sleep=lambda s: None)
    top = L.MENU_BAND + E.PILL_CLEARANCE  # no notch, menu bar hidden: still below its 24 pt band and the island row
    h = 1117 - E.BAR_CLEARANCE - top
    right = 1728 - E.drawer_reserve()
    frame = [e for e in ax.log if e[0] == "frame"]
    assert frame == [("frame", "lesson", 0, top, round(right), h)]
    assert frame[0][2] + frame[0][4] < 1728  # it ends before the drawer
    assert ("minimize", "old") in ax.log and ax.log[-1] == ("raise", "lesson")
    assert rep["fullscreen"] == "done (maximized)" and rep["put_away"] == ["old-lesson-abc123"]


def test_without_accessibility_nothing_tries_to_size_the_window(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    monkeypatch.setattr(E, "make_fullscreen", lambda *a, **k: pytest.fail("no AX call without Accessibility"))
    monkeypatch.setattr(E, "arrange", lambda *a, **k: pytest.fail("no AX call without Accessibility"))
    monkeypatch.setattr(E, "AX", lambda: pytest.fail("no AX call without Accessibility"))
    calls: list = []
    rep = E.open_editor_report(folder, "nn.py", runner=lambda argv: calls.append(argv) or True, editor=VSC,
                               trusted=lambda: False, previous=None, fullscreen=True)
    assert rep["opened"] and rep["fullscreen"].startswith("skipped: Accessibility not granted")
    assert "-n" not in calls[0]


# --------------------------------------------------------------------------------------- one tab

def test_curated_folder_shows_one_tab_and_the_learners_settings_win(tmp_path):
    from server.orchestrator import curated

    graph = {"lesson": {"id": "lesson-nn-from-scratch", "title": "A neural net from scratch"}}
    fresh = tmp_path / "lessons" / "fresh"
    fresh.mkdir(parents=True)
    curated._folder_extras(fresh, graph)
    got = json.loads((fresh / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert got["workbench.editor.showTabs"] == "single"
    assert got["python.defaultInterpreterPath"].endswith("python")

    mine = tmp_path / "lessons" / "mine"
    (mine / ".vscode").mkdir(parents=True)
    (mine / ".vscode" / "settings.json").write_text(json.dumps({"workbench.editor.showTabs": "multiple"}),
                                                    encoding="utf-8")
    curated._folder_extras(mine, graph)
    got = json.loads((mine / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert got["workbench.editor.showTabs"] == "multiple"  # the learner's value stays
