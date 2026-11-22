"""The AutoCAD lesson end to end in the session (Nov 22): the setup card offers I have it / Get it / FreeCAD and never
Install; the video is never held; each press does what it says; AutoCAD coming to the front flips its row. Offline:
fake Claude, fake Spotlight, a recorded `open` (nothing is opened), a strict contract-validating hub."""
import asyncio
import json
from pathlib import Path

import pytest

from server.orchestrator.tests.test_session import Rig, run
from server.orchestrator.workspace import Workspace
from server.workspace import apps as A
from server.workspace import setup as S
from server.workspace.tests.test_setup import FakeMac, reqs_reply, tool
from server.workspace.tests.test_workspace import FakeClient

FIX = Path(__file__).resolve().parents[2] / "workspace" / "tests" / "fixtures" / "autocad_toy_car.json"
VENDOR = "https://www.autodesk.com/products/autocad/free-trial"


def graph() -> dict:
    return json.loads(FIX.read_text(encoding="utf-8"))


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.setattr("server.workspace.editor.editor_id", lambda: "vscode")
    monkeypatch.setattr(A, "APP_ROOTS", [tmp_path / "Applications"])
    mac = FakeMac(apps={"com.microsoft.VSCode": "/Applications/Visual Studio Code.app"})
    monkeypatch.setattr(S.shutil, "which", mac.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: mac.apps.get(bundle))
    monkeypatch.setattr(S, "brew_path", lambda: "/opt/homebrew/bin/brew")
    state = {"autocad": None}  # where AutoCAD is, once "installed"

    def detect(t, run, extra=None):
        if t == "autocad" and state["autocad"]:
            return {"installed": True, "where": state["autocad"], "version": "25.0"}
        return {"installed": False, "where": "", "version": ""}

    monkeypatch.setattr(A, "detect", detect)
    fc = FakeClient(reqs_reply(editor=False, why="the tutorial is a no-code CAD workflow done entirely in AutoCAD.",
                               tools=[tool("autocad", "app", why="Used to draw the car profile.", brew="autocad", brew_cask=True)]))
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(wsmod, "requirements", lambda g, folder: S.requirements(g, workdir=folder, client=fc, run=mac.run))
    r = Rig(tmp_path)
    r.opened: list[list[str]] = []
    r.s.workspace = Workspace(enabled=True, runner=lambda argv: r.opened.append(argv) or True)
    r.state = state
    return r


async def _start(rig) -> dict:
    await rig.s.load_graph(graph())
    await rig.settle()
    await asyncio.sleep(0.05)
    await rig.settle()
    return [c for c in rig.of("card") if c.get("kind") == "setup"][-1]


def test_card_is_a_quiet_companion_with_have_it_get_it_and_freecad(rig):
    card = run(_start(rig))
    assert card["title"] == "This lesson uses AutoCAD"
    assert card["actions"] == ["have_it", "get_it", "alternative", "skip_setup"] and "install" not in card["actions"]
    assert card["setup"]["holdVideo"] is False and card["setup"]["editorNeeded"] is False
    row = card["setup"]["items"][1]
    assert row["install"]["method"] == "download" and row["install"]["url"] == VENDOR
    assert not [a for a in rig.opened if a[:1] == ["open"]]  # nothing opened by itself
    assert "editor" not in json.dumps(rig.s.graph["steps"][0]).lower()  # the lesson talks about AutoCAD


def test_i_have_it_not_found_trusts_the_learner_and_remembers(rig):
    async def go():
        await _start(rig)
        await rig.s.action("have_it", "autocad")
        await rig.settle()

    run(go())
    note = rig.of("card")[-1]
    assert note["title"] == "Got it. I'll use AutoCAD when it opens." and note["actions"] == [] and note["dismissAfterMs"] == 4000
    assert rig.s._setup_card is None and A.recall()["autocad"]["haveIt"] is True
    assert "the learner says they have it" in rig.s._explain_context()["setup"]


def test_i_have_it_found_flips_the_row(rig):
    async def go():
        await _start(rig)
        rig.state["autocad"] = "/Applications/Autodesk/AutoCAD 2025/AutoCAD 2025.app"
        await rig.s.action("have_it")  # no tool id: the first app row waiting
        await rig.settle()

    run(go())
    assert rig.of("card")[-1]["title"] == "AutoCAD found"
    item = next(it for it in rig.s.reqs if it["tool"] == "autocad")
    assert item["installed"] and item["ok"] and item["version"] == "25.0"
    assert "AutoCAD 25.0 is installed" in rig.s._explain_context()["setup"]


def test_get_it_opens_only_the_vendor_page_then_autocad_in_front_flips_the_row(rig):
    async def go():
        await _start(rig)
        await rig.s.action("get_it", "autocad")
        await rig.settle()
        body = rig.of("card")[-1]["body"]
        rig.state["autocad"] = "/Applications/Autodesk/AutoCAD 2025/AutoCAD 2025.app"
        await rig.s.on_front_switch("AutoCAD 2025")
        await rig.settle()
        return body

    body = run(go())
    assert rig.opened == [["open", VENDOR]]
    assert body == "Opened Autodesk's page. I'll notice when AutoCAD opens."
    assert rig.of("card")[-1]["title"] == "AutoCAD found" and rig.s._setup_card is None


def test_freecad_alternative_becomes_an_installable_row(rig):
    async def go():
        await _start(rig)
        await rig.s.action("alternative", "autocad")
        await rig.settle()

    run(go())
    card = rig.of("card")[-1]
    rows = {r["tool"]: r for r in card["setup"]["items"]}
    assert rows["autocad"]["using"] == "FreeCAD" and rows["autocad"]["actions"] == []
    assert rows["freecad"]["setupKind"] == "free_app" and rows["freecad"]["install"]["method"] == "brew_cask"
    assert rows["freecad"]["install"]["command"] == "brew install --cask freecad"
    assert card["actions"][0] == "install" and "have_it" not in card["actions"]
    assert rig.opened == []  # nothing installed or opened until the learner presses Install
    assert A.recall()["autocad"]["choice"] == "alternative:freecad"


def test_a_link_off_the_allowlist_is_shown_never_opened(rig):
    from server.orchestrator import setup_apps

    async def go():
        await _start(rig)
        return await setup_apps.open_url(rig.s, "https://autodesk-free.example/crack", "AutoCAD")

    assert run(go()) is False and rig.opened == []
    shown = rig.of("card")[-1]
    assert shown["title"] == "Check this link first" and "autodesk-free.example" in shown["output"]
    # Claude's own link for AutoCAD (a .dmg on another site) is never what Get it opens: the catalog's vendor page is
    assert all(VENDOR == r["install"]["url"] for r in rig.of("card")[0]["setup"]["items"] if r["tool"] == "autocad")
