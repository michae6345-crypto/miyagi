"""A lesson folder's VS Code settings look calm on a projector (core.CALM_VIEW), with a larger font only under
MIYAGI_DEMO=1, and never hide the ▷ Run button or the terminal."""

from __future__ import annotations

import json

import pytest

from server.workspace import core


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(core, "VSCODE_A11Y", "auto")  # no companion probe
    monkeypatch.delenv("MIYAGI_DEMO", raising=False)


def _settings(folder) -> dict:
    return json.loads((folder / ".vscode" / "settings.json").read_text(encoding="utf-8"))


def test_a_lesson_folder_gets_the_calm_view(tmp_path):
    core._write_vscode_settings(tmp_path)
    got = _settings(tmp_path)
    assert got["workbench.startupEditor"] == "none"
    assert got["editor.minimap.enabled"] is False
    assert got["breadcrumbs.enabled"] is False
    assert got["explorer.openEditors.visible"] == 0
    assert got["workbench.tips.enabled"] is False
    assert got["extensions.ignoreRecommendations"] is True
    for k, v in core.CALM_VIEW.items():
        assert got[k] == v


def test_no_bigger_font_without_miyagi_demo(tmp_path):
    core._write_vscode_settings(tmp_path)
    got = _settings(tmp_path)
    assert "editor.fontSize" not in got and "terminal.integrated.fontSize" not in got


def test_miyagi_demo_makes_the_font_a_bit_bigger(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_DEMO", "1")
    core._write_vscode_settings(tmp_path)
    got = _settings(tmp_path)
    assert got["editor.fontSize"] == 16 and got["terminal.integrated.fontSize"] == 15


def test_a_value_already_in_the_file_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_DEMO", "1")
    p = tmp_path / ".vscode" / "settings.json"
    p.parent.mkdir()
    p.write_text(json.dumps({"breadcrumbs.enabled": True, "editor.fontSize": 20, "workbench.startupEditor": "readme"}))
    core._write_vscode_settings(tmp_path)
    got = _settings(tmp_path)
    assert got["breadcrumbs.enabled"] is True and got["editor.fontSize"] == 20
    assert got["workbench.startupEditor"] == "readme"
    assert got["editor.minimap.enabled"] is False and got["terminal.integrated.fontSize"] == 15


def test_the_run_button_and_the_terminal_stay(tmp_path, monkeypatch):
    """The lesson points at VS Code's real ▷ Run button (editor title actions) and its terminal."""
    monkeypatch.setenv("MIYAGI_DEMO", "1")
    (tmp_path / "nn.py").write_text("import numpy as np\n")
    core._write_vscode_settings(tmp_path)
    got = _settings(tmp_path)
    hidden = {"workbench.editor.editorActionsLocation", "workbench.editor.showTabs", "workbench.statusBar.visible",
              "terminal.integrated.tabs.enabled", "window.menuBarVisibility"}
    assert not hidden & set(got)
    assert got["terminal.integrated.hideOnStartup"] == "whenEmpty"  # a run's own terminal still shows
    assert got["terminal.integrated.env.osx"]["PATH"].startswith("${workspaceFolder}/.venv/bin")
    assert not hidden & set(core.CALM_VIEW) and not any(k.startswith("terminal.") for k in core.CALM_VIEW)


def test_ensure_calm_view_merges_only_the_calm_keys(tmp_path):
    p = tmp_path / ".vscode" / "settings.json"
    p.parent.mkdir()
    p.write_text(json.dumps({"python.defaultInterpreterPath": "x", "breadcrumbs.enabled": True}))
    assert core.ensure_calm_view(tmp_path, demo=True) is True
    got = _settings(tmp_path)
    assert got["python.defaultInterpreterPath"] == "x" and got["breadcrumbs.enabled"] is True
    assert got["workbench.startupEditor"] == "none" and got["editor.fontSize"] == 16
    assert "window.title" not in got  # the other lesson keys are the engine's job
    assert core.ensure_calm_view(tmp_path, demo=True) is False  # nothing left to add


def test_ensure_calm_view_follows_miyagi_demo_by_default(tmp_path, monkeypatch):
    core.ensure_calm_view(tmp_path)
    assert "editor.fontSize" not in _settings(tmp_path)
    monkeypatch.setenv("MIYAGI_DEMO", "1")
    core.ensure_calm_view(tmp_path)
    assert _settings(tmp_path)["editor.fontSize"] == 16


def test_ensure_calm_view_leaves_a_file_with_comments_alone(tmp_path):
    p = tmp_path / ".vscode" / "settings.json"
    p.parent.mkdir()
    p.write_text('{\n  // mine\n  "editor.fontSize": 12\n}\n')
    assert core.ensure_calm_view(tmp_path, demo=True) is False
    assert "// mine" in p.read_text()
