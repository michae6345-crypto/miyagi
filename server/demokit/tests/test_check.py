"""The pre-demo check with fake probes, a temp HOME and a temp app (no network, no real ~/miyagi, no real engine)."""

from __future__ import annotations

import json
import plistlib
from pathlib import Path

import pytest

from server.demokit import check
from server.demokit.common import FILE, Layout

LID = "lesson-nn-from-scratch"
STARTER = "import numpy as np\n"
HEALTH_OK = {"ok": True, "items": [{"id": "accessibility", "state": "ok"}, {"id": "screen", "state": "ok"},
                                   {"id": "engine", "state": "ok"}]}


class FakeProbes(check.Probes):
    def __init__(self, lay, **kw):
        super().__init__(lay)
        self.app_up = kw.get("app_up", True)
        self.port_up = kw.get("port_up", self.app_up)
        self.health = kw.get("health", HEALTH_OK)
        self.cloud = kw.get("cloud", (200, '{"ok":true}'))
        self.ed = kw.get("ed", {"id": "vscode", "app_path": "/Applications/Visual Studio Code.app", "cli": "/x/code"})
        self.comp = kw.get("comp", (True, "0.0.6"))
        self.code_up = kw.get("code_up", False)
        self.windows = kw.get("windows")
        self.caff = kw.get("caff", True)
        self.batt = kw.get("batt", False)
        self.urls: list[str] = []

    def app_running(self):
        return self.app_up

    def port_open(self, port):
        return self.port_up

    def http_get(self, url, timeout):
        self.urls.append(url)
        if url == check.CLOUD_HEALTHZ:
            return self.cloud
        if url.startswith("http://127.0.0.1:") and self.port_up and self.health is not None:
            return 200, json.dumps(self.health)
        return None

    def vscode(self):
        if isinstance(self.ed, Exception):
            raise self.ed
        return self.ed

    def companion(self):
        return self.comp

    def vscode_running(self):
        return self.code_up

    def vscode_windows(self):
        return self.windows

    def caffeinated(self):
        return self.caff

    def on_battery(self):
        return self.batt


@pytest.fixture()
def lay(tmp_path) -> Layout:
    app = tmp_path / "Applications" / "miyagi.app"
    src = app / "Contents" / "Resources" / "engine" / "src"
    (src / "demo" / "cache" / "lessons").mkdir(parents=True)
    (src / "demo" / "nn-start.py").write_text(STARTER)
    (src / "demo" / "cache" / "lessons" / "text-nn-from-scratch.json").write_text(
        json.dumps({"lesson": {"id": LID, "title": "A neural net from scratch"}}))
    with (app / "Contents" / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleShortVersionString": "0.1.0"}, f)
    home = tmp_path / "home"
    sup = home / "Library" / "Application Support" / "miyagi"
    sup.mkdir(parents=True)
    (sup / "auth.bin").write_bytes(b"secret-token-bytes")
    lay = Layout(home=home, app=app, repo=tmp_path / "no-repo", port=8787)
    folder = lay.folder()
    (folder / ".venv" / "lib" / "python3.12" / "site-packages" / "numpy").mkdir(parents=True)
    (folder / FILE).write_text(STARTER)
    return lay


def _run(lay, probes, *args):
    lines: list[str] = []
    code = check.main(list(args), lay=lay, probes=probes, out=lines.append)
    return code, lines


def _status(lines, text) -> str:
    hit = [ln for ln in lines if text in ln]
    assert hit, (text, lines)
    return hit[0].split()[0]


def test_all_ok_exits_zero(lay):
    code, lines = _run(lay, FakeProbes(lay))
    assert code == 0, "\n".join(lines)
    assert lines[0] == "miyagi pre-demo check" and lines[-1] == "All set."
    for text in ("miyagi.app 0.1.0", "engine answers on :8787", "miyagi-cloud answers", "signed in",
                 "VS Code and its code CLI", "companion 0.0.6", "Accessibility is on", "Screen Recording is on",
                 "neural-net lesson starts clean", "VS Code is closed", "caffeinate keeps"):
        assert _status(lines, text) == "ok", text
    assert _status(lines, "Do Not Disturb") == "note"


def test_never_prints_the_auth_file(lay):
    _, lines = _run(lay, FakeProbes(lay))
    assert "secret-token-bytes" not in "\n".join(lines)


def test_an_earlier_take_and_a_saved_place_say_run_the_reset(lay):
    (lay.folder() / FILE).write_text(STARTER + "W1 = 1\n")
    lay.state.mkdir(parents=True)
    (lay.state / "current.json").write_text(json.dumps({"lessonId": LID, "stepIndex": 2}))
    (lay.state / "recent.json").write_text(json.dumps([{"lessonId": LID}]))
    code, lines = _run(lay, FakeProbes(lay))
    assert code == 1 and lines[-1] == "1 to fix."
    row = next(ln for ln in lines if "neural-net lesson" in ln)
    assert row.split()[0] == "fix" and "earlier take" in row and "Continue" in row
    assert lines[lines.index(row) + 1].strip() == "-> " + check.RESET


def test_a_saved_place_of_another_lesson_is_fine(lay):
    lay.state.mkdir(parents=True)
    (lay.state / "current.json").write_text(json.dumps({"lessonId": "lesson-other", "stepIndex": 2}))
    assert _run(lay, FakeProbes(lay))[0] == 0


def test_no_numpy_yet_is_a_note_not_a_fix(lay):
    import shutil

    shutil.rmtree(lay.folder() / ".venv")
    code, lines = _run(lay, FakeProbes(lay))
    assert code == 0 and _status(lines, "NumPy isn't in the lesson's .venv") == "note"


def test_app_closed_skips_the_engine_and_asks_for_permissions_by_hand(lay):
    p = FakeProbes(lay, app_up=False)
    code, lines = _run(lay, p)
    assert code == 0
    assert _status(lines, "miyagi isn't open yet") == "skip"
    assert _status(lines, "Check by hand") == "note"
    assert not any(u.startswith("http://127.0.0.1") for u in p.urls)  # the engine is never asked


def test_a_dev_engine_holding_the_port_while_the_app_is_closed_is_a_fix(lay):
    code, lines = _run(lay, FakeProbes(lay, app_up=False, port_up=True))
    assert code == 1 and _status(lines, "something already holds :8787") == "fix"


def test_engine_down_while_the_app_runs(lay):
    code, lines = _run(lay, FakeProbes(lay, port_up=False))
    assert code == 1 and _status(lines, "the engine doesn't answer") == "fix"
    assert _status(lines, "Check by hand") == "note"


def test_permission_off_gives_the_settings_path(lay):
    health = {"ok": True, "items": [{"id": "accessibility", "state": "missing"}, {"id": "screen", "state": "unknown"}]}
    code, lines = _run(lay, FakeProbes(lay, health=health))
    assert code == 1
    i = next(i for i, ln in enumerate(lines) if "Accessibility is off" in ln)
    assert "Privacy & Security > Accessibility" in lines[i + 1]
    assert "Screen & System Audio Recording" in next(ln for ln in lines if "Check by hand" in ln)


def test_cloud_down_and_offline(lay):
    code, lines = _run(lay, FakeProbes(lay, cloud=None))
    assert code == 1 and _status(lines, "miyagi-cloud didn't answer in 5 s") == "fix"
    p = FakeProbes(lay, cloud=None)
    code, lines = _run(lay, p, "--offline")
    assert code == 0 and _status(lines, "miyagi-cloud: --offline") == "skip"
    assert check.CLOUD_HEALTHZ not in p.urls


def test_cloud_error_status(lay):
    code, lines = _run(lay, FakeProbes(lay, cloud=(503, "")))
    assert code == 1 and _status(lines, "miyagi-cloud answered 503") == "fix"


def test_not_signed_in(lay):
    (lay.app_support / "auth.bin").unlink()
    code, lines = _run(lay, FakeProbes(lay))
    assert code == 1 and _status(lines, "not signed in") == "fix"


def test_no_app(lay, tmp_path):
    lay2 = Layout(home=lay.home, app=tmp_path / "nowhere" / "miyagi.app", repo=lay.repo)
    code, lines = _run(lay2, FakeProbes(lay2))
    assert code == 1 and _status(lines, "miyagi.app is not in") == "fix"


def test_vscode_missing_cli_missing_companion_missing(lay):
    code, lines = _run(lay, FakeProbes(lay, ed=None))
    assert code == 1 and "code.visualstudio.com" in "\n".join(lines)
    ed = {"id": "vscode", "app_path": "/Applications/Visual Studio Code.app", "cli": None}
    code, lines = _run(lay, FakeProbes(lay, ed=ed, comp=(False, None)))
    assert _status(lines, "code CLI is missing") == "fix" and _status(lines, "companion is not installed") == "fix"


def test_vscode_lookup_that_cannot_load_is_a_skip(lay):
    code, lines = _run(lay, FakeProbes(lay, ed=ModuleNotFoundError("jsonschema")))
    assert code == 0 and _status(lines, "couldn't load the engine's lookup") == "skip"


def test_open_vscode_windows_are_a_fix(lay):
    code, lines = _run(lay, FakeProbes(lay, code_up=True, windows=2))
    assert code == 1 and _status(lines, "VS Code is open (2 windows)") == "fix"
    code, lines = _run(lay, FakeProbes(lay, code_up=True, windows=None))
    assert _status(lines, "VS Code is open") == "fix"


def test_reminders(lay):
    _, lines = _run(lay, FakeProbes(lay, caff=False, batt=True))
    assert _status(lines, "caffeinate -d") == "note" and _status(lines, "On battery") == "note"


def test_the_real_vscode_probe_uses_the_editor_lookup(lay, monkeypatch):
    from server.workspace import editor

    monkeypatch.setattr(editor, "installed_editors", lambda: [{"id": "vscode", "app_path": "/A", "cli": "/c"}])
    assert check.Probes(lay).vscode() == {"id": "vscode", "app_path": "/A", "cli": "/c"}


def test_scripts_exist_and_are_executable():
    root = Path(check.__file__).resolve().parents[2]
    for name in ("miyagi-demo-check.sh", "miyagi-demo-reset.sh"):
        p = root / "scripts" / name
        assert p.is_file() and p.stat().st_mode & 0o111, name
