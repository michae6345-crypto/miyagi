"""Fresh Mac with no VS Code: the "VS Code not found" setup card (the v2 app's VS Code sheet), never an open that does
nothing and a lesson left with no editor; once VS Code is there, the lesson opens in it."""
import asyncio

from server.orchestrator.tests.test_session import Rig, run
from server.orchestrator.workspace import Workspace

CARD = {"kind": "setup", "title": "VS Code not found", "body": "miyagi needs VS Code to teach this.",
        "actions": ["install", "skip_setup"],
        "setup": {"editorNeeded": True, "editor": "vscode", "editorLabel": "Visual Studio Code", "resources": [],
                  "actionLabels": {}, "items": [{"tool": "vscode", "label": "Visual Studio Code", "kind": "editor",
                                                 "why": "", "needed": True, "installed": False, "ok": False,
                                                 "unknown": False, "version": None, "minVersion": None,
                                                 "install": {"method": "download", "command": None,
                                                             "url": "https://code.visualstudio.com/download"}}]}}
ITEM = {"tool": "vscode", "label": "Visual Studio Code", "kind": "editor", "needed": True, "installed": False,
        "ok": False, "install": {"method": "download", "command": "", "url": "https://code.visualstudio.com/download"}}


def _rig(tmp_path, monkeypatch, missing: list[bool]):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: None)  # no S2 setup check (no key)
    calls: list[list[str]] = []
    ws = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)
    ws.editor_check = lambda: (dict(CARD), dict(ITEM)) if missing[0] else None
    (tmp_path / "pinn_convection.py").write_text("import torch\n", encoding="utf-8")
    rig = Rig(tmp_path)
    rig.s.workspace = ws
    return rig, calls


def test_no_vscode_sends_the_not_found_card_and_opens_nothing(tmp_path, monkeypatch):
    missing = [True]
    rig, calls = _rig(tmp_path, monkeypatch, missing)

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()
        await rig.s.action("open_editor")  # the learner presses Open: the card again, still nothing opened
        await rig.settle()

    run(go())
    cards = [c for c in rig.of("card") if c.get("title") == "VS Code not found"]
    assert len(cards) == 2 and cards[0]["setup"]["items"][0]["install"]["method"] == "download"
    assert not [c for c in calls if str(tmp_path.resolve()) in c], calls  # no `code <folder>`, no `open -a`
    assert not rig.s.editor_open and rig.s._no_editor
    assert any(it.get("tool") == "vscode" for it in rig.s.reqs or [])  # Install finds the editor row


def test_vscode_found_later_opens_the_lesson(tmp_path, monkeypatch):
    missing = [True]
    rig, calls = _rig(tmp_path, monkeypatch, missing)

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()
        missing[0] = False  # installed (Homebrew from the card, or the learner's own download)
        await rig.s._editor_found_check()
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    assert [c for c in rig.of("card") if c.get("title") == "VS Code found"]
    assert [c for c in calls if str(tmp_path.resolve()) in c] and rig.s.editor_open and not rig.s._no_editor


def test_vscode_installed_opens_as_before(tmp_path, monkeypatch):
    rig, calls = _rig(tmp_path, monkeypatch, [False])

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    assert not [c for c in rig.of("card") if c.get("title") == "VS Code not found"]
    assert [c for c in calls if str(tmp_path.resolve()) in c] and rig.s.editor_open


def test_open_resends_the_setup_card_that_already_lists_vscode(tmp_path, monkeypatch):
    rig, _calls = _rig(tmp_path, monkeypatch, [True])
    listed = {"kind": "setup", "title": "Set up first", "body": "Missing: VS Code, numpy.", "actions": ["install", "skip_setup"],
              "setup": {**CARD["setup"], "items": CARD["setup"]["items"] + [{**CARD["setup"]["items"][0], "tool": "numpy",
                                                                              "label": "numpy", "kind": "python_package"}]}}

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.settle()
        rig.s._setup_card = listed
        await rig.s.action("open_editor")
        await rig.settle()

    run(go())
    assert rig.of("card")[-1]["title"] == "Set up first"  # rows kept: the packages aren't dropped for the sheet
