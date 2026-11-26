"""Smart setup for any tool a lesson needs (Nov 22, Michael's AutoCAD lesson): packages install, free apps install from
an allowlisted cask, licensed apps are never installed (I have it / Get it / a free alternative), web apps open.
Offline: fake Claude replies, a fake /Applications in a temp folder, a fake Spotlight."""

from __future__ import annotations

import json
import plistlib
from pathlib import Path

import pytest

from server.workspace import apps as A
from server.workspace import missing, requirements, setup_card
from server.workspace import setup as S
from server.workspace.tests.test_setup import FakeMac, reqs_reply, tool
from server.workspace.tests.test_workspace import FakeClient, load
from shared.contracts.events import engine_message

AUTOCAD_WHY = "Used to draw the car profile, cutouts, wheels and tolerances."


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.setattr("server.workspace.editor.editor_id", lambda: "vscode")
    monkeypatch.setattr(A, "APP_ROOTS", [tmp_path / "Applications"])  # never this Mac's real /Applications
    (tmp_path / "Applications").mkdir()


@pytest.fixture
def app_actions(monkeypatch):
    """The app draws I have it / Get it / Try FreeCAD and honours holdVideo (its claim PR landed): both flags on."""
    monkeypatch.setattr(S, "APP_RENDERS_APP_ACTIONS", True)
    monkeypatch.setattr(S, "APP_HONOURS_HOLD_VIDEO", True)


@pytest.fixture
def old_app(monkeypatch):
    """An app older than the setup-calm merge (Nov 22): no I have it / Try FreeCAD buttons, holds under any setup card."""
    monkeypatch.setattr(S, "APP_RENDERS_APP_ACTIONS", False)
    monkeypatch.setattr(S, "APP_HONOURS_HOLD_VIDEO", False)


@pytest.fixture
def mac(monkeypatch):
    m = FakeMac(apps={"com.microsoft.VSCode": "/Applications/Visual Studio Code.app"})
    monkeypatch.setattr(S.shutil, "which", m.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: m.apps.get(bundle))
    monkeypatch.setattr(S, "brew_path", lambda: "/opt/homebrew/bin/brew")
    return m


def make_app(root: Path, rel: str, version: str = "25.0") -> Path:
    app = root / rel
    (app / "Contents").mkdir(parents=True)
    with (app / "Contents" / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleShortVersionString": version}, f)
    return app


def autocad_reply():
    # what Claude answered for Michael's lesson: AutoCAD as an app with a made-up cask
    return reqs_reply(editor=False, why="the tutorial is a no-code CAD workflow done entirely in AutoCAD, not writing code or text files.",
                      tools=[tool("autocad", "app", why=AUTOCAD_WHY, brew="autocad", brew_cask=True,
                                  url="https://evil.example/autocad.dmg")])


# --------------------------------------------------------------------------- names and kinds

@pytest.mark.parametrize("name, tid", [("AutoCAD 2025", "autocad"), ("Autodesk AutoCAD", "autocad"), ("autodesk-fusion-360", "fusion"),
                                       ("Adobe Photoshop CC", "photoshop"), ("MATLAB R2024b", "matlab"), ("Microsoft Excel", "excel"),
                                       ("FreeCAD", "freecad"), ("numpy", None), ("", None)])
def test_canonical_names(name, tid):
    assert A.canonical(name) == tid


def test_bare_ambiguous_names_are_apps_only_when_the_model_says_app():
    # a Java lesson listing the Mozilla Rhino JS engine must not get a "Rhino is paid. Get it" row
    for bare in ("rhino", "word", "logic", "maya"):
        assert A.canonical(bare) is None and A.canonical(bare, "cli") is None, bare
    assert A.canonical("rhino", "app") == "rhino" and A.canonical("maya", "app") == "maya"
    assert A.canonical("Microsoft Word") == "word"  # with the vendor it's always the app
    assert S._canonical("rhino", "library") == "rhino-pkg" and S._canonical("rhino", "app") == "rhino"
    assert A.classify({"tool": S._canonical("rhino", "cli"), "kind": "cli"}) == "package"


@pytest.mark.parametrize("title, tid", [("AutoCAD - Toy Car Creation for 3D Printer", "autocad"), ("Fusion 360 for beginners", "fusion"),
                                        ("Nuclear fusion explained", None), ("Learn Python in 1 hour", None),
                                        ("Blender donut tutorial", "blender"), ("Tinkercad basics", "tinkercad")])
def test_app_in_title(title, tid):
    assert A.app_in_text(title) == tid


def test_classify_every_kind():
    assert A.classify({"tool": "numpy", "kind": "python_package"}) == "package"
    assert A.classify({"tool": "git", "kind": "cli"}) == "package"
    assert A.classify({"tool": "blender", "kind": "app"}) == "free_app"
    assert A.classify({"tool": "freecad", "kind": "app"}) == "free_app"
    assert A.classify({"tool": "autocad", "kind": "app"}) == "licensed_app"
    assert A.classify({"tool": "photoshop", "kind": "cli"}) == "licensed_app"  # whatever kind the model said
    assert A.classify({"tool": "tinkercad", "kind": "web_app"}) == "web_app"


def test_licensed_apps_have_an_allowlisted_vendor_page_and_free_alternatives_resolve():
    from server.safety import browser_url_allowed

    for tid, e in A.LICENSED.items():
        assert e["vendor_url"].startswith("https://") and browser_url_allowed(e["vendor_url"]), tid
        alt = A.alternative(tid)
        assert alt and browser_url_allowed(alt["url"]), tid
    assert A.alternative("autocad") == {"tool": "freecad", "name": "FreeCAD", "url": "https://www.freecad.org/downloads.php",
                                        "installable": True}
    assert not browser_url_allowed("https://autodesk-free-crack.example/autocad")
    assert not browser_url_allowed("https://www.autodesk.com/autocad.dmg")  # a page, never a download


def test_free_app_casks_are_allowlisted_and_model_casks_off_the_list_are_not():
    assert "freecad" in S.ALLOWED_CASKS and "gimp" in S.ALLOWED_CASKS and "cursor" not in S.ALLOWED_CASKS
    r = S.recipe({"tool": "freecad", "kind": "app"}, "/opt/homebrew/bin/brew")
    assert r["method"] == "brew_cask" and r["package"] == "freecad"
    odd = S.recipe({"tool": "some-paint-app", "kind": "app", "brew": "microsoft-excel", "brew_cask": True}, "/opt/homebrew/bin/brew")
    assert odd["method"] in ("download", "none") and odd["package"] == ""


def test_a_licensed_app_is_never_installed_whatever_the_model_says():
    item = {"tool": "autocad", "kind": "app", "label": "AutoCAD", "brew": "autocad", "brew_cask": True,
            "url": "https://evil.example/autocad.dmg"}
    r = S.recipe(item, "/opt/homebrew/bin/brew")
    assert r["method"] == "download" and r["url"] == "https://www.autodesk.com/products/autocad/free-trial" and r["licensed"]

    def boom(*a, **k):  # no process may start
        raise AssertionError("install ran a process")

    res = S.install(item, popen=boom, net=lambda h: True)
    assert res["ok"] is False and res["licensed"] and res["url"].startswith("https://www.autodesk.com/")
    assert "licensed" in res["error"] and "Autodesk" in res["error"]


# --------------------------------------------------------------------------- detection

def test_detects_autocad_one_folder_down_with_its_version(tmp_path):
    root = tmp_path / "Applications"
    make_app(root, "Autodesk/AutoCAD 2024/AutoCAD 2024.app", "24.3")
    make_app(root, "Autodesk/AutoCAD 2025/AutoCAD 2025.app", "25.0.1")
    found = A.detect("autocad", lambda argv: (1, ""))
    assert found["installed"] and found["where"].endswith("AutoCAD 2025.app") and found["version"] == "25.0.1"


def test_detects_by_spotlight_bundle_prefix_when_not_in_applications():
    seen = []

    def run(argv):
        seen.append(argv)
        if argv[0] == "mdfind" and "com.autodesk.AutoCAD*" in argv[1]:
            return 0, "/Volumes/Work/AutoCAD 2025.app\n"
        return 0, "25.1\n" if argv[0] == "defaults" else ""

    found = A.detect("autocad", run)
    assert found == {"installed": True, "where": "/Volumes/Work/AutoCAD 2025.app", "version": "25.1"}
    assert seen[0] == ["mdfind", "kMDItemCFBundleIdentifier == 'com.autodesk.AutoCAD*'"]


def test_windows_only_app_is_never_found_and_says_so():
    assert A.detect("solidworks", lambda argv: (0, "/Applications/x.app"))["noMac"] is True


def test_front_app_matches_its_row():
    row = {"tool": "autocad", "label": "AutoCAD"}
    assert A.matches_front(row, "AutoCAD 2025") and not A.matches_front(row, "Code")
    assert A.matches_front({"tool": "excel", "label": "Microsoft Excel"}, "Microsoft Excel")


# --------------------------------------------------------------------------- the AutoCAD lesson, end to end

def test_autocad_card_with_todays_app_says_only_what_its_buttons_do(mac, old_app):
    """Fix round 2: the app on integration/live draws no I have it / Try FreeCAD button. The card never asks a question
    it can't answer: the row's Get it, FreeCAD's own row with Install, and Skip."""
    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    by = {it["tool"]: it for it in items}
    assert list(by) == ["vscode", "autocad", "freecad"]
    fc = by["freecad"]
    assert fc["altFor"] == "autocad" and fc["needed"] and not fc["installed"] and fc["setupKind"] == "free_app"
    assert fc["install"]["method"] == "brew_cask" and fc["install"]["command"] == "brew install --cask freecad"
    assert fc["why"] == "Free stand-in for AutoCAD."
    assert [it["tool"] for it in missing(items)] == ["autocad"]  # the offer is never "missing"
    assert not any(a[0] == "brew" or "install" in a for a in mac.argv)  # nothing installed by the scan

    card = setup_card(items)
    assert card["title"] == "This lesson uses AutoCAD"
    assert card["body"] == "AutoCAD is paid. Get it, install FreeCAD free, or skip."
    assert len(card["body"].split()) <= 12 and "—" not in card["body"] + card["title"]
    assert "?" not in card["body"]  # no question without a button to answer it
    assert card["actions"] == ["install", "skip_setup"]  # today's app: the rows' own buttons do the work
    assert not {"have_it", "get_it", "alternative"} & set(card["setup"]["actionLabels"])
    rows = {r["tool"]: r for r in card["setup"]["items"]}
    assert rows["autocad"]["install"]["method"] == "download"  # its row's "Get it": the vendor's page
    assert rows["freecad"]["install"]["method"] == "brew_cask" and rows["freecad"]["needed"]  # its row's "Install"
    assert "altFor" not in rows["freecad"]  # engine-only: the contract row is unchanged
    engine_message("card", card)


def test_autocad_card_without_an_installable_alternative(mac, monkeypatch, old_app):
    monkeypatch.setitem(A.LICENSED["autocad"], "alternative", "tinkercad")  # a web alternative gets no row
    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    assert [it["tool"] for it in items] == ["vscode", "autocad"]
    assert setup_card(items)["body"] == "AutoCAD is a paid app. Get it, or skip to watch."


def test_windows_only_app_with_todays_app(mac, old_app):
    fc = FakeClient(reqs_reply(editor=False, why="all in 3ds Max.", tools=[tool("3ds Max", "app")]))
    g = load("autocad_toy_car.json")
    g["lesson"]["title"] = g["sources"][0]["title"] = "3ds Max low poly car"
    items = requirements(g, client=fc, run=mac.run)
    assert setup_card(items)["body"] == "3ds Max is Windows only. Install Blender free, or skip."


def test_autocad_lesson_card_offers_have_it_get_it_and_freecad_never_install(mac, app_actions):
    fc = FakeClient(autocad_reply())
    items = requirements(load("autocad_toy_car.json"), client=fc, run=mac.run)
    by = {it["tool"]: it for it in items}
    assert list(by) == ["vscode", "autocad"] and by["vscode"]["needed"] is False
    ac = by["autocad"]
    assert ac["label"] == "AutoCAD" and ac["kind"] == "app" and ac["setupKind"] == "licensed_app" and not ac["installed"]
    assert ac["install"] == {"method": "download", "command": "", "url": "https://www.autodesk.com/products/autocad/free-trial"}
    assert not any(a[0] == "brew" or "install" in a for a in mac.argv)  # read-only, and no cask for AutoCAD
    assert [it["tool"] for it in missing(items)] == ["autocad"]

    card = setup_card(items)
    assert card["title"] == "This lesson uses AutoCAD"
    assert card["body"] == "Have AutoCAD already? Or try FreeCAD, free. Watch while you decide."
    assert len(card["body"].split()) <= 12 and "—" not in card["body"] + card["title"]
    assert "Install" not in card["body"] and "editor" not in card["body"].lower()
    assert card["actions"] == ["have_it", "get_it", "alternative", "skip_setup"]
    setup = card["setup"]
    assert setup["holdVideo"] is False  # setup is a companion: the video plays
    assert setup["actionLabels"]["have_it"] == "I have it" and setup["actionLabels"]["get_it"] == "Get AutoCAD"
    assert setup["actionLabels"]["alternative"] == "Try FreeCAD"
    row = next(r for r in setup["items"] if r["tool"] == "autocad")
    assert row["setupKind"] == "licensed_app" and row["actions"] == ["have_it", "get_it", "alternative", "skip"]
    assert row["vendorUrl"] == "https://www.autodesk.com/products/autocad/free-trial" and row["vendorName"] == "Autodesk"
    assert row["alternative"] == {"name": "FreeCAD", "url": "https://www.freecad.org/downloads.php", "tool": "freecad"}
    assert row["why"] == AUTOCAD_WHY
    assert engine_message("card", card)["payload"]["setup"]["items"][1]["alternative"]["name"] == "FreeCAD"  # the contract
    json.dumps(card)


def test_autocad_lesson_offline_still_gets_its_app_row(mac, monkeypatch, old_app):
    monkeypatch.setattr(S, "make_client", lambda: None)  # no key / offline: no Claude at all
    items = requirements(load("autocad_toy_car.json"), run=mac.run)
    assert [(it["tool"], it["setupKind"]) for it in items] == [("vscode", "free_app"), ("autocad", "licensed_app"), ("freecad", "free_app")]
    assert items[0]["needed"] is False and items[0]["why"] == "No editor needed: all the work happens in AutoCAD."
    assert setup_card(items)["title"] == "This lesson uses AutoCAD"


def test_claude_forgetting_the_app_still_offers_it(mac, old_app):
    fc = FakeClient(reqs_reply(editor=False, why="no code here.", tools=[]))
    items = requirements(load("autocad_toy_car.json"), client=fc, run=mac.run)
    assert [it["tool"] for it in items] == ["vscode", "autocad", "freecad"]  # + FreeCAD offered (its own row)


def test_autocad_installed_means_ready(mac, tmp_path):
    make_app(tmp_path / "Applications", "Autodesk/AutoCAD 2025/AutoCAD 2025.app", "25.0")
    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    ac = items[1]
    assert ac["installed"] and ac["ok"] and ac["version"] == "25.0" and missing(items) == []
    card = setup_card(items)
    assert card["title"] == "Ready to go" and "have_it" not in card["actions"]
    assert card["setup"]["items"][1]["actions"] == []
    assert A.recall()["autocad"]["installed"] is True  # the scan is remembered for the next lesson


def test_i_have_it_is_remembered_for_the_next_lesson(mac):
    A.remember("autocad", haveIt=True)
    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    assert items[1]["haveIt"] is True and missing(items) == []
    card = setup_card(items)
    assert card["title"] == "Ready to go" and card["setup"]["items"][1]["haveIt"] is True
    assert A.context_line(items) == "Apps on this Mac: AutoCAD: the learner says they have it."


def test_i_have_it_expires_so_a_mistaken_press_undoes_itself(mac, monkeypatch):
    A.remember("autocad", haveIt=True)
    row = A.recall()["autocad"]
    assert row["haveItAt"] > 0 and A.have_it_fresh(row)
    assert not A.have_it_fresh(row, now=row["haveItAt"] + A.HAVE_IT_DAYS * 86400)
    assert not A.have_it_fresh({"haveIt": True})  # kept before haveItAt existed: asked once more
    later = row["haveItAt"] + A.HAVE_IT_DAYS * 86400 + 1
    monkeypatch.setattr(A.time, "time", lambda: later)
    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    assert not items[1].get("haveIt") and [it["tool"] for it in missing(items)] == ["autocad"]  # the card asks again


def test_choosing_the_alternative_is_remembered(mac, old_app):
    A.remember("autocad", choice="alternative:freecad")
    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    assert items[1]["using"] == "FreeCAD"
    # chosen, so FreeCAD's own row is an ordinary needed row: not on this Mac yet, it is what's missing
    fc = items[2]
    assert fc["tool"] == "freecad" and "altFor" not in fc and [it["tool"] for it in missing(items)] == ["freecad"]
    card = setup_card(items)
    assert card["title"] == "Set up first" and card["body"].startswith("Missing: FreeCAD. Install now?")
    assert "uses FreeCAD instead" in A.context_line(items)


def test_choosing_the_alternative_with_it_installed_needs_nothing(mac, tmp_path, old_app):
    make_app(tmp_path / "Applications", "FreeCAD.app", "1.0.0")
    A.remember("autocad", choice="alternative:freecad")
    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    assert items[1]["using"] == "FreeCAD" and items[2]["installed"] and missing(items) == []


def test_choosing_the_alternative_is_remembered_when_the_app_draws_it(mac, app_actions):
    A.remember("autocad", choice="alternative:freecad")
    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    assert items[1]["using"] == "FreeCAD" and missing(items) == []


def test_windows_only_app_card_points_to_the_alternative(mac, app_actions):
    fc = FakeClient(reqs_reply(editor=False, why="all in SOLIDWORKS.", tools=[tool("SolidWorks", "app")]))
    g = load("autocad_toy_car.json")
    g["lesson"]["title"] = g["sources"][0]["title"] = "SOLIDWORKS gear tutorial"
    items = requirements(g, client=fc, run=mac.run)
    card = setup_card(items)
    assert card["body"] == "SOLIDWORKS is Windows only. Try Onshape, free."
    assert card["setup"]["items"][1]["noMac"] is True


def test_mixed_card_installs_packages_and_never_the_licensed_app(mac, app_actions):
    fc = FakeClient(reqs_reply(editor=False, why="CAD plus a slicer.", tools=[
        tool("autocad", "app"), tool("PrusaSlicer", "app", brew="prusaslicer", brew_cask=True)]))
    items = requirements(load("autocad_toy_car.json"), client=fc, run=mac.run)
    by = {it["tool"]: it for it in items}
    assert by["prusaslicer"]["setupKind"] == "free_app" and by["prusaslicer"]["install"]["method"] == "brew_cask"
    card = setup_card(items, hold_for=["prusaslicer"])
    assert card["title"] == "Set up first" and card["body"].startswith("Missing: PrusaSlicer. Install now? Have AutoCAD already?")
    assert card["actions"] == ["install", "have_it", "get_it", "alternative", "skip_setup"]
    assert card["setup"]["holdVideo"] is True  # the step on screen truly needs the slicer, and Install can get it
    rows = {r["tool"]: r for r in card["setup"]["items"]}
    assert rows["prusaslicer"]["actions"] == ["install", "have_it", "skip"]
    assert setup_card(items)["setup"]["holdVideo"] is False


def test_preflight_card_never_offers_install_for_autocad(mac):
    from server.preflight.core import preflight_card

    items = requirements(load("autocad_toy_car.json"), client=FakeClient(autocad_reply()), run=mac.run)
    card = preflight_card({"title": "AutoCAD - Toy Car Creation for 3D Printer", "requirements": items, "style": "no-code",
                           "url": "https://www.youtube.com/watch?v=AcadToyCar1",
                           "buildPlan": {"strategy": "whole", "estSecondsToFirstSteps": 40}})
    assert card["actions"] == ["build", "pick_another"]
    row = next(r for r in card["items"] if r["tool"] == "autocad")
    assert row["setupKind"] == "licensed_app" and row["actions"] == ["have_it", "get_it", "alternative", "skip"]
    assert row["alternative"]["name"] == "FreeCAD"
    assert engine_message("card", card)["payload"]["items"][1]["vendorName"] == "Autodesk"


def test_code_lesson_context_is_unchanged():
    assert A.context_line([{"tool": "numpy", "kind": "python_package", "needed": True}]) == ""
