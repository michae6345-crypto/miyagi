"""Open in Blender (Nov 24): a Blender lesson's setup card opens donut.blend in the learner's Blender, the miyagi
bridge loaded. Offline and launch-free: a strict contract-validating hub, a fake Workspace runner (nothing opens),
a fake headless runner for the new scene, fake bridge answers, and subprocess.Popen patched to raise."""
from __future__ import annotations

import asyncio
import subprocess
import types
from pathlib import Path

import pytest

from server.orchestrator import open_in_app as O
from server.orchestrator import setup_apps
from server.orchestrator import workspace as wsmod
from server.orchestrator.tests.test_session import Rig, run
from server.orchestrator.workspace import Workspace
from server.workspace import blender
from server.workspace import blender_ext as bx

EXE = "/Applications/Blender.app/Contents/MacOS/Blender"
BLEND_BYTES = b"BLENDER-v405" + b"\0" * 64


def blender_row(ok: bool = True) -> dict:
    return {"tool": "blender", "label": "Blender", "kind": "app", "needed": True, "why": "Used to model the donut.",
            "min_version": "", "installed": ok, "ok": ok, "version": "5.3.0" if ok else "", "binary": "",
            "where": "/Applications/Blender.app" if ok else "",
            "install": {"method": "brew_cask", "command": "brew install --cask blender", "url": ""}}


def autocad_row() -> dict:
    return {"tool": "autocad", "label": "AutoCAD", "kind": "app", "needed": True, "why": "Used to draw the car.",
            "min_version": "", "installed": True, "ok": True, "version": "25.0", "binary": "",
            "where": "/Applications/Autodesk/AutoCAD 2025/AutoCAD 2025.app",
            "install": {"method": "download", "command": "", "url": "https://www.autodesk.com/products/autocad/free-trial"}}


def graph(*, tool: str = "blender", mode: str | None = None, steps: list[dict] | None = None) -> dict:
    label = {"blender": "Blender", "autocad": "AutoCAD"}.get(tool, tool)
    lesson = {"id": f"lesson-{tool}-donut", "title": f"{label} donut for beginners", "goal": "make a donut",
              "libraries": {}, "app": {"tool": tool, "label": label}}
    if mode:
        lesson["mode"] = mode
    if steps is None:
        steps = [
            {"id": "s1", "index": 1, "title": "Look around", "instructions": "Orbit the view with the middle mouse.",
             "checks": [], "targets": [], "explanations": [], "hints": [], "common_mistakes": []},
            {"id": "s2", "index": 2, "title": "Save the scene", "file": "donut.blend",
             "instructions": "Save the file as donut.blend in the lesson folder.",
             "checks": [{"id": "c1", "type": "file_contains", "label": "saved", "file": "donut.scene.json",
                         "pattern": "Cube"}],
             "targets": [], "explanations": [], "hints": [], "common_mistakes": []},
        ]
    return {"lesson": lesson, "sources": [], "steps": steps}


class Fakes:
    """What the act() tests control: bridge answers, the 'Blender without the bridge' seam, the create runner and
    the workspace launcher."""

    def __init__(self) -> None:
        self.instances: list[dict] = []
        self.unbridged = False
        self.create_calls: list[list[str]] = []
        self.create_code = 0
        self.create_data: bytes | None = BLEND_BYTES
        self.launched: list[list[str]] = []
        self.launch_ok = True

    def create(self, argv: list[str], timeout: float) -> int:
        self.create_calls.append(list(argv))
        if self.create_data is not None:
            Path(argv[-1]).write_bytes(self.create_data)
        return self.create_code

    def run(self, argv: list[str]) -> bool:
        self.launched.append(list(argv))
        return self.launch_ok


@pytest.fixture(autouse=True)
def no_launch(monkeypatch):
    """Nothing in this file may start a process: Popen raises, and the headless runner is always a fake."""
    def popen(*a, **k):
        raise AssertionError("subprocess.Popen called in an open_in_app test")

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(blender, "run_blender", lambda argv, timeout: (_ for _ in ()).throw(
        AssertionError("the real headless runner was called")))


@pytest.fixture
def fakes(monkeypatch):
    f = Fakes()
    monkeypatch.setattr(blender, "run_blender", f.create)
    monkeypatch.setattr(blender, "find_blender", lambda: EXE)
    monkeypatch.setattr(bx, "instances", lambda timeout=bx.TIMEOUT_S: list(f.instances))
    monkeypatch.setattr(O, "running_without_bridge", lambda found: f.unbridged)
    monkeypatch.setattr(O, "WATCH_POLL_S", 0.01)
    return f


@pytest.fixture
def rig(tmp_path, monkeypatch, fakes):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.setattr("server.workspace.editor.editor_id", lambda: "vscode")
    rows = {"items": [blender_row()]}
    monkeypatch.setattr(wsmod, "requirements", lambda g, folder: [dict(r) for r in rows["items"]])
    monkeypatch.setattr(wsmod, "find_resources", lambda g: [])
    r = Rig(tmp_path)
    r.rows = rows
    r.fakes = fakes
    r.s.workspace = Workspace(enabled=True, runner=fakes.run)
    return r


async def _load(rig, g: dict) -> list[dict]:
    await rig.s.load_graph(g)
    for _ in range(3):
        await rig.settle()
        await asyncio.sleep(0.02)
    return [c for c in rig.of("card") if c.get("kind") == "setup"]


def _words(text: str) -> int:
    return len((text or "").split())


def _blend(rig) -> Path:
    return Path(rig.s.workdir).resolve() / "donut.blend"


# ------------------------------------------------------------------ the offer (acceptance 2)
@pytest.mark.parametrize("mode", [None, "lesson"], ids=["video", "lesson-mode"])
def test_blender_lesson_offers_open_in_blender(rig, mode):
    cards = run(_load(rig, graph(mode=mode)))
    offers = [c for c in cards if "open_in_app" in (c.get("actions") or [])]
    assert len(offers) == 1, cards
    card = offers[0]
    assert card["actions"] == ["open_in_app"]
    assert card["setup"]["actionLabels"] == {"open_in_app": "Open in Blender"}
    assert card["setup"]["holdVideo"] is False
    assert card["title"] == "Blender is ready" and card["body"] == "Open donut.blend in Blender?"
    assert _words(card["title"]) <= 12 and _words(card["body"]) <= 12
    assert [it["tool"] for it in card["setup"]["items"]] == ["blender"]
    assert card["setup"]["editorNeeded"] is False
    # an offer only: Blender never opens by itself (lesson mode opens VS Code, through the same fake runner)
    assert not [a for a in rig.fakes.launched if a[:1] == [EXE]] and rig.fakes.create_calls == []


def test_offer_from_a_scene_check_when_no_step_names_a_blend(rig):
    g = graph(steps=[{"id": "s1", "index": 1, "title": "Add a torus", "instructions": "Add a torus.",
                      "checks": [{"id": "c1", "type": "file_contains", "label": "torus", "file": "ring.scene.json",
                                  "pattern": "Torus"}],
                      "targets": [], "explanations": [], "hints": [], "common_mistakes": []}])
    card = run(_load(rig, g))[-1]
    assert card["actions"] == ["open_in_app"] and card["body"] == "Open ring.blend in Blender?"


@pytest.mark.parametrize("mode", [None, "lesson"], ids=["video", "lesson-mode"])
def test_autocad_lesson_keeps_the_old_note(rig, mode):
    rig.rows["items"] = [autocad_row()]
    cards = run(_load(rig, graph(tool="autocad", mode=mode)))
    assert not [c for c in cards if "open_in_app" in (c.get("actions") or [])]
    if mode is None:
        assert cards[-1]["title"] == "AutoCAD is ready" and cards[-1]["actions"] == []


def test_blender_lesson_without_a_known_stem_keeps_the_old_note(rig):
    g = graph(steps=[{"id": "s1", "index": 1, "title": "Look around", "instructions": "Orbit the view.",
                      "checks": [], "targets": [], "explanations": [], "hints": [], "common_mistakes": []}])
    cards = run(_load(rig, g))
    assert not [c for c in cards if "open_in_app" in (c.get("actions") or [])]
    assert cards[-1]["title"] == "Blender is ready" and cards[-1]["actions"] == []
    assert "dismissAfterMs" in cards[-1]


def test_code_lesson_gets_no_open_in_app():
    class S:
        graph = types.MappingProxyType({"lesson": {"title": "numpy"}, "steps": [{"id": "s1", "file": "nn.py"}]})
        workdir = "/tmp"
        workspace = Workspace(enabled=True, runner=lambda argv: True)

    assert O.blend_path(S()) is None and O.open_card(S(), [blender_row()]) is None


def test_no_blender_found_means_no_offer(rig, monkeypatch):
    rig.rows["items"] = [{**blender_row(ok=False), "haveIt": True}]  # not missing, but not found on this Mac
    monkeypatch.setattr(blender, "find_blender", lambda: None)
    cards = run(_load(rig, graph()))
    assert not [c for c in cards if "open_in_app" in (c.get("actions") or [])]


def test_workspace_off_means_no_offer(rig):
    rig.s.workspace = Workspace(enabled=False, runner=rig.fakes.run)
    run(rig.s.load_graph(graph()))
    assert O.open_card(rig.s, [blender_row()]) is None


def test_flag_off_returns_the_old_note(rig, monkeypatch):
    monkeypatch.setattr(O, "APP_RENDERS_OPEN_IN_APP", False)
    cards = run(_load(rig, graph()))
    assert cards[-1]["title"] == "Blender is ready" and cards[-1]["actions"] == []
    assert O.offer_card(rig.s, [blender_row()]) == setup_apps.note_card("Blender is ready")
    assert O.open_card(rig.s, [blender_row()]) is None


def test_long_names_keep_the_body_short(rig):
    g = graph()
    g["steps"][1]["file"] = "a b c d e f g h i j k l m.blend"
    run(rig.s.load_graph(g))
    card = O.open_card(rig.s, [blender_row()])
    assert card["body"] == "Open the lesson's scene in Blender?" and _words(card["body"]) <= 12


def test_refresh_after_blender_found_offers_open(rig):
    """setup_apps.refresh with nothing left waiting (Blender just found / installed): the offer, not the note."""
    async def go():
        await rig.s.load_graph(graph())
        await rig.settle()
        rig.s.reqs = [blender_row()]
        rig.s._setup_card = {"kind": "setup", "title": "Set up first", "body": "", "actions": ["install"],
                             "setup": {"items": [{"tool": "blender"}]}}
        await setup_apps.refresh(rig.s, "Blender found")

    run(go())
    card = rig.of("card")[-1]
    assert card["actions"] == ["open_in_app"] and rig.s._setup_card is None


def test_refresh_for_autocad_keeps_the_note(rig):
    async def go():
        await rig.s.load_graph(graph(tool="autocad"))
        await rig.settle()
        rig.s.reqs = [autocad_row()]
        rig.s._setup_card = {"kind": "setup", "title": "x", "body": "", "actions": ["have_it"],
                             "setup": {"items": [{"tool": "autocad"}]}}
        await setup_apps.refresh(rig.s, "AutoCAD found")

    run(go())
    card = rig.of("card")[-1]
    assert card["title"] == "AutoCAD found" and card["actions"] == [] and card["dismissAfterMs"] == setup_apps.NOTE_MS


def test_install_settled_offers_open(rig, monkeypatch):
    """Blender installed from the setup card, nothing left: Open in Blender instead of "Blender installed"."""
    rig.rows["items"] = [blender_row(ok=False)]
    monkeypatch.setattr(wsmod, "install", lambda item, wd, on_line: {"ok": True, "version": "5.3.0"})

    async def go():
        await _load(rig, graph())
        rig.rows["items"] = [blender_row()]
        await rig.s.action("install", "blender")
        for _ in range(3):
            await rig.settle()
            await asyncio.sleep(0.02)

    run(go())
    card = [c for c in rig.of("card") if c.get("kind") == "setup"][-1]
    assert card["actions"] == ["open_in_app"]


# ------------------------------------------------------------------ path safety (acceptance 6)
@pytest.mark.parametrize("raw", ["../x.blend", "/abs/x.blend", "a/b.blend", "a\\b.blend", "~/x.blend", ".blend",
                                 ".hidden.blend", "x$.blend", "..blend", "x.blend\n/etc"])
def test_unsafe_step_files_never_resolve(rig, raw):
    g = graph()
    g["steps"][1]["file"] = raw
    g["steps"][1]["checks"] = []
    run(rig.s.load_graph(g))
    assert O.safe_name(raw, ".blend") is None
    assert O.blend_path(rig.s) is None


@pytest.mark.parametrize("raw", ["../ring.scene.json", "/abs/ring.scene.json", "a/ring.scene.json"])
def test_unsafe_scene_checks_never_resolve(rig, raw):
    g = graph()
    g["steps"][1].pop("file")
    g["steps"][1]["checks"][0]["file"] = raw
    run(rig.s.load_graph(g))
    assert O.blend_path(rig.s) is None


def test_unsafe_file_is_skipped_for_a_safe_one_inside_the_folder(rig):
    g = graph()
    g["steps"][0]["file"] = "../../outside.blend"
    run(rig.s.load_graph(g))
    p = O.blend_path(rig.s)
    assert p == _blend(rig) and p.is_relative_to(Path(rig.s.workdir).resolve())


def test_symlink_out_of_the_lesson_folder_is_refused(rig, tmp_path_factory):
    run(rig.s.load_graph(graph()))
    outside = tmp_path_factory.mktemp("outside") / "elsewhere.blend"
    outside.write_bytes(BLEND_BYTES)
    Path(rig.s.workdir).mkdir(parents=True, exist_ok=True)
    (Path(rig.s.workdir) / "donut.blend").symlink_to(outside)
    assert O.blend_path(rig.s) is None


def test_safe_names():
    assert O.safe_name("donut.blend", ".blend") == "donut.blend"
    assert O.safe_name(" My Donut_v2.blend ", ".blend") == "My Donut_v2.blend"
    assert O.safe_name("donut.scene.json", ".scene.json") == "donut.scene.json"
    assert O.safe_name("donut.obj", ".blend") is None and O.safe_name(None, ".blend") is None


# ------------------------------------------------------------------ the button (acceptance 3, 4, 5, 7)
async def _press(rig, *texts):
    for t in texts:
        await rig.s.action("open_in_app", t)
    await rig.settle()


def _loaded(rig, g=None):
    run(_load(rig, g or graph()))
    return _blend(rig)


def test_press_creates_the_scene_then_launches_with_the_bridge(rig):
    path = _loaded(rig)
    assert not path.exists()
    run(_press(rig, None))
    f = rig.fakes
    assert len(f.create_calls) == 1
    argv = f.create_calls[0]
    for flag in ("--background", "--factory-startup", "--disable-autoexec"):
        assert flag in argv
    tmp = Path(argv[-1])
    assert tmp.parent == path.parent and tmp != path and not tmp.exists()  # the temp was os.replaced, none left
    assert path.read_bytes() == BLEND_BYTES
    assert f.launched == [[EXE, str(path), "--python", str(bx.BRIDGE_START)]]
    assert bx.BRIDGE_START == Path(__file__).resolve().parents[3] / "blender-addon" / "start_bridge.py"
    note = rig.of("card")[-1]
    assert note["title"] == "Opening donut.blend in Blender" and note["actions"] == [] and _words(note["title"]) <= 12


def test_zero_byte_scene_is_created_the_same_way(rig):
    path = _loaded(rig)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    run(_press(rig, None))
    assert len(rig.fakes.create_calls) == 1 and path.read_bytes() == BLEND_BYTES
    assert len(rig.fakes.launched) == 1


def test_saved_scene_is_never_rewritten(rig):
    path = _loaded(rig)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"BLENDER learner's own")
    run(_press(rig, "blender"))
    assert rig.fakes.create_calls == [] and path.read_bytes() == b"BLENDER learner's own"
    assert rig.fakes.launched == [[EXE, str(path), "--python", str(bx.BRIDGE_START)]]


def test_already_open_in_blender_means_no_create_no_launch(rig):
    path = _loaded(rig)
    rig.fakes.instances = [{"app": "blender", "port": 8801, "pid": 4242, "file": str(path)}]
    run(_press(rig, None))
    assert rig.fakes.create_calls == [] and rig.fakes.launched == [] and not path.exists()
    note = rig.of("card")[-1]
    assert note["title"] == "Already open in Blender" and note["dismissAfterMs"] and _words(note["title"]) <= 12


def test_blender_without_the_bridge_says_quit_first(rig):
    _loaded(rig)
    rig.fakes.unbridged = True
    run(_press(rig, None))
    assert rig.fakes.launched == [] and rig.fakes.create_calls == []
    assert rig.of("card")[-1]["title"] == "Quit Blender, then press Open in Blender again."


def test_running_without_bridge_seam(monkeypatch):
    real = O.running_without_bridge
    monkeypatch.setattr(O, "_running_pids", list)
    assert real([]) is False
    monkeypatch.setattr(O, "_running_pids", lambda: [10])
    assert real([]) is True
    assert real([{"pid": 10}]) is False  # that Blender has the bridge
    assert real([{"pid": 11}]) is True
    assert real([{"port": 8801}]) is False  # an older bridge without a pid: counted, not guessed


def test_two_presses_within_the_grace_launch_once(rig):
    _loaded(rig)
    run(_press(rig, None, None))
    assert len(rig.fakes.launched) == 1
    assert rig.of("card")[-1]["title"] == "Blender is opening. Give it a moment."
    rig.clock.t += O.LAUNCH_GRACE_S + 1  # after the grace (Blender never answered): a press launches again
    run(_press(rig, None))
    assert len(rig.fakes.launched) == 2


def test_concurrent_presses_launch_once(rig):
    _loaded(rig)

    async def go():
        await asyncio.gather(O.act(rig.s, None), O.act(rig.s, None), O.act(rig.s, "blender"))
        await rig.settle()

    run(go())
    assert len(rig.fakes.launched) == 1 and len(rig.fakes.create_calls) == 1


@pytest.mark.parametrize("case", ["rc1", "no-output"])
def test_create_failure_means_no_launch_and_one_short_card(rig, case):
    path = _loaded(rig)
    if case == "rc1":
        rig.fakes.create_code = 1
    else:
        rig.fakes.create_data = None
    mark = rig.mark()
    run(_press(rig, None))
    assert len(rig.fakes.create_calls) == 1 and rig.fakes.launched == [] and not path.exists()
    cards = [e["payload"] for e in rig.since(mark) if e["type"] == "card"]
    assert len(cards) == 1 and cards[0]["title"] == "Couldn't make the scene file. Try again."
    assert _words(cards[0]["title"]) <= 12
    assert not [p for p in path.parent.glob(".donut.*")]


def test_launch_failure_is_one_short_card(rig):
    _loaded(rig)
    rig.fakes.launch_ok = False
    mark = rig.mark()
    run(_press(rig, None))
    cards = [e["payload"] for e in rig.since(mark) if e["type"] == "card"]
    assert [c["title"] for c in cards] == ["Couldn't start Blender. Try again."]
    assert O._state(rig.s)["launched"] == {}  # a failed launch holds no grace: the next press tries again


def test_no_blender_found_on_press(rig, monkeypatch):
    _loaded(rig)
    monkeypatch.setattr(blender, "find_blender", lambda: None)
    run(_press(rig, None))
    assert rig.fakes.launched == [] and rig.of("card")[-1]["title"] == "Blender isn't on this Mac yet."


def test_other_app_or_no_scene_never_launches(rig):
    _loaded(rig)
    run(_press(rig, "autocad"))
    assert rig.of("card")[-1]["title"] == "Only Blender opens from here for now."
    run(rig.s.load_graph(graph(tool="autocad")))
    run(_press(rig, None))
    assert rig.of("card")[-1]["title"] == "This lesson has no Blender scene to open."
    assert rig.fakes.launched == [] and rig.fakes.create_calls == []


def test_missing_bridge_start_launches_without_the_python_pair(rig, monkeypatch, tmp_path, caplog):
    path = _loaded(rig)
    monkeypatch.setattr(bx, "BRIDGE_START", tmp_path / "gone" / "start_bridge.py")
    with caplog.at_level("WARNING", logger="orchestrator.open_in_app"):
        run(_press(rig, None))
    assert rig.fakes.launched == [[EXE, str(path)]]
    assert any("start_bridge.py" in r.getMessage() and "missing" in r.getMessage() for r in caplog.records)


def test_act_never_raises(rig, monkeypatch):
    _loaded(rig)

    def boom(*a, **k):
        raise RuntimeError("bridge exploded")

    monkeypatch.setattr(bx, "instances", boom)
    monkeypatch.setattr(O, "running_without_bridge", boom)
    run(_press(rig, None))
    assert rig.fakes.launched == [] and rig.of("card")[-1]["title"] == "Couldn't start Blender. Try again."


# ------------------------------------------------------------------ after the launch (acceptance 8)
def _coach_calls(monkeypatch):
    calls = []

    async def on_step(s, gen, step):
        calls.append((gen, step["id"]))

    from server.orchestrator import onscreen_coach

    monkeypatch.setattr(onscreen_coach, "on_step", on_step)
    monkeypatch.setattr(onscreen_coach, "is_app_lesson", lambda s: True)
    return calls


def test_bridge_answer_spawns_the_coach_once_for_the_current_step(rig, monkeypatch):
    path = _loaded(rig)
    calls = _coach_calls(monkeypatch)  # after the load: the step start's own on_step is not ours

    async def go():
        await rig.s.action("open_in_app")
        await rig.settle()
        gen, step = rig.s.step_gen, rig.s.step
        await asyncio.sleep(0.05)  # no bridge yet: nothing
        assert calls == []
        rig.fakes.instances = [{"app": "blender", "port": 8801, "pid": 1, "file": str(path)}]
        assert await O._state(rig.s)["watch"] is True
        await rig.settle()
        return gen, step["id"]

    expected = run(go())
    assert calls == [expected]


def test_no_coach_when_the_step_changed(rig, monkeypatch):
    path = _loaded(rig)
    calls = _coach_calls(monkeypatch)

    async def go():
        await rig.s.action("open_in_app")
        await rig.settle()
        rig.s.step_gen += 1  # the learner moved on before Blender answered
        rig.fakes.instances = [{"app": "blender", "port": 8801, "pid": 1, "file": str(path)}]
        assert await O._state(rig.s)["watch"] is False
        await rig.settle()

    run(go())
    assert calls == []


def test_no_coach_for_another_file(rig, monkeypatch):
    _loaded(rig)
    calls = _coach_calls(monkeypatch)
    monkeypatch.setattr(O, "WATCH_S", 0.05)

    async def go():
        await rig.s.action("open_in_app")
        rig.fakes.instances = [{"app": "blender", "port": 8801, "pid": 1, "file": "/elsewhere/other.blend"}]
        assert await O._state(rig.s)["watch"] is False

    run(go())
    assert calls == []
