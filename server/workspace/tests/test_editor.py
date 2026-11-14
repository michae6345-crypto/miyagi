"""Editor choice (Cursor > VS Code, MIYAGI_EDITOR), open + frontmost, and the Accessibility arrangement (fakes)."""

from __future__ import annotations

import pytest

from server.workspace import editor as E
from server.workspace import setup as S
from server.workspace.tests.test_setup import FakeMac, reqs_reply
from server.workspace.tests.test_workspace import FakeClient, load

CURSOR = {"id": "cursor", "label": "Cursor", "app": "Cursor", "app_path": "/Applications/Cursor.app", "cli": "/opt/homebrew/bin/cursor"}
VSCODE = {"id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "app_path": "/Applications/Visual Studio Code.app",
          "cli": "/usr/local/bin/code"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.delenv("MIYAGI_EDITOR", raising=False)
    monkeypatch.delenv("MIYAGI_ARRANGE", raising=False)


@pytest.mark.parametrize("installed,env,want", [
    ([CURSOR, VSCODE], None, "cursor"),          # Cursor preferred when installed
    ([VSCODE], None, "vscode"),
    ([CURSOR, VSCODE], "code", "vscode"),        # MIYAGI_EDITOR overrides
    ([CURSOR, VSCODE], "vscode", "vscode"),
    ([VSCODE], "cursor", "vscode"),              # override not installed -> fall back
    ([], None, None),
])
def test_preferred_editor(monkeypatch, installed, env, want):
    if env:
        monkeypatch.setenv("MIYAGI_EDITOR", env)
    got = E.preferred_editor(installed)
    assert (got or {}).get("id") == want


def test_editor_id_and_label_follow_the_preference(monkeypatch):
    monkeypatch.setattr(E, "installed_editors", lambda: [CURSOR, VSCODE])
    assert E.editor_id() == "cursor" and E.editor_label() == "Cursor"
    assert E.goto_argv("/l/main.py", 7) == ["/opt/homebrew/bin/cursor", "-r", "-g", "/l/main.py:7"]
    monkeypatch.setattr(E, "installed_editors", list)
    monkeypatch.setenv("MIYAGI_EDITOR", "cursor")
    assert E.editor_id() == "cursor"  # not installed yet: the setup card offers to install Cursor


def opener(tmp_path, ok=lambda a: True):
    (tmp_path / "main.py").write_text("")
    calls = []
    return calls, (lambda a: calls.append(a) or ok(a))


def test_open_with_cursor_cli_then_frontmost_without_accessibility(tmp_path):
    calls, run = opener(tmp_path)
    rep = E.open_editor_report(tmp_path, "main.py", runner=run, editor=CURSOR, trusted=lambda: False, previous=None)
    assert calls[0] == ["/opt/homebrew/bin/cursor", "-n", str(tmp_path.resolve()), "-g", str((tmp_path / "main.py").resolve())]
    assert calls[1] == ["open", "-a", "Cursor"]
    assert rep["opened"] and rep["frontmost"] and rep["label"] == "Cursor"
    assert rep["arrange"] == "skipped: Accessibility not granted" and "unfullscreened" not in rep


def test_cli_failure_falls_back_to_open_a(tmp_path):
    calls, run = opener(tmp_path, ok=lambda a: a[0] == "open")
    assert E.open_editor(tmp_path, "main.py", runner=run, editor=CURSOR, trusted=lambda: False, previous=None)
    assert calls[1][:3] == ["open", "-a", "Cursor"] and calls[1][-1].endswith("main.py")


def test_no_editor_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "installed_editors", list)
    rep = E.open_editor_report(tmp_path, runner=lambda a: True, previous=None)
    assert rep["opened"] is False and "no supported editor" in rep["error"]


def test_arrange_off_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_ARRANGE", "0")
    _, run = opener(tmp_path)
    rep = E.open_editor_report(tmp_path, runner=run, editor=CURSOR, trusted=lambda: True, previous=None)
    assert rep["arrange"].startswith("off")


class FakeAX:
    def __init__(self, fullscreen_prev=True, fullscreen_editor=False):
        self.wins = {"prev": {"fs": fullscreen_prev}, "ed": {"fs": fullscreen_editor}}
        self.log = []

    def focused_window(self, pid):
        return "prev" if pid == 111 else "ed"

    def is_fullscreen(self, w):
        return self.wins[w]["fs"]

    def exit_fullscreen(self, w):
        self.log.append(("exit_fs", w))
        self.wins[w]["fs"] = False
        return True

    def set_frame(self, w, x, y, wd, h):
        self.log.append(("frame", w, x, y, wd, h))
        return True


def test_arrange_unfullscreens_previous_and_docks_editor_left(monkeypatch):
    monkeypatch.setattr(E, "find_pid", lambda name: 222)
    monkeypatch.setattr(E, "left_frame", lambda fraction=0.6: (0, 38, round(1728 * fraction), 1079))
    ax, rep = FakeAX(fullscreen_prev=True, fullscreen_editor=True), {}
    E.arrange(CURSOR, {"pid": 111, "name": "Safari"}, rep, ax=ax, sleep=lambda s: None)
    assert ax.log == [("exit_fs", "prev"), ("exit_fs", "ed"), ("frame", "ed", 0, 38, 1037, 1079)]
    assert rep == {"unfullscreened": "Safari", "arranged": True, "frame": [0, 38, 1037, 1079], "arrange": "done"}


def test_arrange_leaves_windowed_apps_alone(monkeypatch):
    monkeypatch.setattr(E, "find_pid", lambda name: 222)
    monkeypatch.setattr(E, "left_frame", lambda fraction=0.6: (0, 0, 600, 800))
    ax, rep = FakeAX(fullscreen_prev=False), {}
    E.arrange(CURSOR, {"pid": 111, "name": "Terminal"}, rep, ax=ax, sleep=lambda s: None)
    assert ("exit_fs", "prev") not in ax.log and "unfullscreened" not in rep and rep["arranged"]


def test_arrange_gives_up_without_an_editor_window(monkeypatch):
    monkeypatch.setattr(E, "find_pid", lambda name: None)
    rep = {}
    E.arrange(CURSOR, None, rep, ax=FakeAX(), wait_s=0.01, sleep=lambda s: None)
    assert rep["arrange"].startswith("skipped: no Cursor window")


def test_open_with_accessibility_runs_arrange(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(E, "arrange", lambda ed, prev, rep: seen.update(ed=ed["id"], prev=prev) or rep.update(arrange="done"))
    _, run = opener(tmp_path)
    rep = E.open_editor_report(tmp_path, runner=run, editor=CURSOR, trusted=lambda: True, previous={"pid": 1, "name": "Keynote"}, wait=True)
    assert seen == {"ed": "cursor", "prev": {"pid": 1, "name": "Keynote"}} and rep["arrange"] == "done" and rep["ax_trusted"]


def test_setup_card_names_cursor(monkeypatch):
    monkeypatch.setattr(E, "editor_id", lambda: "cursor")
    m = FakeMac(apps={"com.todesktop.230313mzl4w4u92": "/Applications/Cursor.app"})
    monkeypatch.setattr(S.shutil, "which", m.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: m.apps.get(bundle))
    items = S.requirements(load("pandas_pokemon.json"), client=FakeClient(reqs_reply()), run=m.run)
    assert items[0]["tool"] == "cursor" and items[0]["label"] == "Cursor" and items[0]["installed"]
    card = S.setup_card(items)
    assert card["setup"]["editorLabel"] == "Cursor" and card["setup"]["actionLabels"]["open_editor"] == "Open Cursor"
    assert "Open the lesson folder in Cursor?" in card["body"] and card["actions"][0] == "open_editor"


def test_cursor_missing_offers_the_cask(monkeypatch):
    monkeypatch.setattr(E, "editor_id", lambda: "cursor")
    m = FakeMac()
    monkeypatch.setattr(S.shutil, "which", m.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: None)
    monkeypatch.setattr(S, "brew_path", lambda: "/opt/homebrew/bin/brew")
    items = S.requirements(load("pandas_pokemon.json"), client=FakeClient(reqs_reply()), run=m.run)
    assert items[0]["install"]["command"] == "brew install --cask cursor"


def test_ax_trusted_is_a_bool():
    assert isinstance(E.ax_trusted(), bool)
