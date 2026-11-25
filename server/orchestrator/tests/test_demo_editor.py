"""Nov 24 (the 1517 demo): starting the neural-net lesson must show one clean editor with a starter that does not
already pass step 1. The demo went through library.start, which never put the clean nn.py back; a save at step 1
from an engine restart also kept the old file; and every Start ran the `code` CLI again.

Offline: stub modules, a recording workspace, fake companion; never the real editor, `open` or Electron."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from server.checks import evaluator as ev
from server.orchestrator import curated
from server.orchestrator import workspace as wsmod
from server.orchestrator.tests.test_launch_contract import FakeReader, RecWorkspace

LID = "text-nn-from-scratch"
LESSON_ID = "lesson-nn-from-scratch"


def _nn1() -> dict:
    return json.loads(curated.LESSON_FILE.read_text(encoding="utf-8"))["steps"][0]


def _solved_step1() -> str:
    """The demo folder's nn.py: the starter with step 1's code (X / y, W1 to W3, forward with tanh) in place."""
    return curated._starter().replace("# The network\n", "# The network\n" + _nn1()["code"] + "\n", 1)


# ------------------------------------------------------------------------------------------ the starter itself

def test_the_clean_starter_does_not_pass_step_one(tmp_path):
    nn1 = _nn1()
    starter = curated._starter()
    assert "# The network" in starter  # the real demo/nn-start.py, not the fallback
    (tmp_path / "nn.py").write_text(starter, encoding="utf-8")
    ctx = ev.RunContext(workdir=str(tmp_path))
    files = {r["checkId"]: r["status"] for r in ev.evaluate_step(nn1, ctx, which="precision")}
    assert files == {"nn1p1": "fail", "nn1p2": "fail", "nn1p3": "fail", "nn1p4": "fail"}
    seen = ev.RunContext(workdir=str(tmp_path), screen={"Code": starter.splitlines()})
    screen = {r["checkId"]: r["status"] for r in ev.evaluate_step(nn1, seen, which="checks")}
    assert set(screen) == {"nn1c1", "nn1c2", "nn1c3", "nn1c4"} and "pass" not in screen.values()

    # control: the demo's solved nn.py passes all of them, so the checks above fail for the right reason
    solved = _solved_step1()
    (tmp_path / "nn.py").write_text(solved, encoding="utf-8")
    files = {r["checkId"]: r["status"] for r in ev.evaluate_step(nn1, ctx, which="precision")}
    assert set(files.values()) == {"pass"}
    seen = ev.RunContext(workdir=str(tmp_path), screen={"Code": solved.splitlines()})
    assert {r["status"] for r in ev.evaluate_step(nn1, seen, which="checks")} == {"pass"}


# ------------------------------------------------------------------------------------------ library.start

@pytest.fixture
def lib_env(tmp_path, monkeypatch):
    """An engine with the curated lesson in its library, lessons under tmp, no pinned TUT_WORKDIR."""
    import server.screen as screen_pkg

    reader = FakeReader()
    monkeypatch.setattr(screen_pkg, "get_reader", lambda: reader)
    monkeypatch.setenv("TUT_SCREEN_FIXTURE", "fake.png")
    for k in ("ORCH_AUTO_RESUME", "ORCH_SCREEN_EAGER", "ORCH_AUTOSTART", "ORCH_SCREEN", "DEMO", "TUT_WORKDIR",
              "MIYAGI_CURATED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MIYAGI_SYSTEM_STATUS", "0")
    lib = tmp_path / "library"
    lib.mkdir()
    shutil.copy(curated.LESSON_FILE, lib / f"{LID}.json")
    monkeypatch.setenv("MIYAGI_LIBRARY_DIR", str(lib))
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: None)  # no setup check (no model call)
    from server.workspace import paths, vscode_ext

    monkeypatch.setattr(vscode_ext, "windows", lambda timeout=None: [])  # never this Mac's VS Code companion

    graph = json.loads(curated.LESSON_FILE.read_text(encoding="utf-8"))
    folder = (paths.lessons_root() / paths.folder_name(graph)).resolve()
    return tmp_path / "lessons", folder


def _old_demo_folder(folder: Path) -> None:
    """The demo Mac's folder: solved step-1 code in nn.py, and an older state file that lists nn.py as a starter."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "nn.py").write_text(_solved_step1(), encoding="utf-8")
    (folder / "README.md").write_text("# A neural net from scratch\n", encoding="utf-8")
    from server.workspace import core

    sf = core._state_file(folder)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"scaffolded": True, "curated": curated.KEY, "lesson_id": LESSON_ID, "open_file": "nn.py",
                              "files": ["nn.py"], "readme": "README.md"}), encoding="utf-8")


def _engine():
    from server.orchestrator import main
    from server.orchestrator.modules import Modules

    eng = main.Engine()
    eng.recorder.enabled = False
    ws = RecWorkspace()
    eng.workspace = eng.session.workspace = ws
    eng.session.m = eng.modules = Modules(demo=False, force_stubs="all")
    eng.session.ready_hold_s = 0
    return eng, ws


def _start(eng) -> None:
    async def go():
        await eng.library_start(LID)
        await asyncio.sleep(0.05)
        await eng.session.drain()
    asyncio.run(go())


def _step1_not_passed(s) -> None:
    assert s.idx == 0 and s.step is not None and s.step["id"] == "nn1"
    assert not s.passed
    assert all(v != "pass" for v in (getattr(s, "results", None) or {}).values() if isinstance(v, str))


def test_library_start_puts_the_clean_starter_back(lib_env):
    root, folder = lib_env
    _old_demo_folder(folder)
    eng, _ = _engine()
    _start(eng)
    s = eng.session
    assert Path(s.workdir).resolve() == folder
    assert (folder / "nn.py").read_text(encoding="utf-8") == curated._starter()
    kept = list((root / ".miyagi-state" / "attempts" / folder.name).glob("nn-*.py"))
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == _solved_step1()
    _step1_not_passed(s)
    assert s.graph["lesson"]["builtBy"] == curated.BUILT_BY
    from server.workspace import core

    assert core.read_state(folder)["files"] == []  # set_aside_previous may move a stale nn.py from now on
    settings = json.loads((folder / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert settings["workbench.editor.showTabs"] == "single"


def test_a_step_one_save_from_a_restart_is_a_fresh_start(lib_env):
    from server.orchestrator.session import LessonSession
    from server.sessions import store

    _, folder = lib_env
    _old_demo_folder(folder)
    # the demo's first take: Start, then the engine restarted 6 s later (stepIndex 0, never stopped)
    store.save({"lessonId": LESSON_ID, "stepIndex": 0, "workdir": str(folder), "startedAt": 1.0})
    graph = json.loads(curated.LESSON_FILE.read_text(encoding="utf-8"))
    assert LessonSession._continues_save(graph) is False
    eng, _ = _engine()
    _start(eng)
    assert (folder / "nn.py").read_text(encoding="utf-8") == curated._starter()
    _step1_not_passed(eng.session)
    saved = store.load()
    assert saved is None or saved.get("startedAt") != 1.0  # never the restart's save restored


def test_a_later_save_continues_with_the_learners_own_code(lib_env):
    from server.orchestrator.session import LessonSession
    from server.sessions import store

    _, folder = lib_env
    _old_demo_folder(folder)
    mine = _solved_step1() + "\n# my own note: qqqq\n"
    (folder / "nn.py").write_text(mine, encoding="utf-8")
    store.save({"lessonId": LESSON_ID, "stepIndex": 1, "workdir": str(folder)})
    graph = json.loads(curated.LESSON_FILE.read_text(encoding="utf-8"))
    assert LessonSession._continues_save(graph) is True
    eng, _ = _engine()
    _start(eng)
    assert (folder / "nn.py").read_text(encoding="utf-8") == mine  # byte for byte
    assert eng.session.idx == 1 and Path(eng.session.workdir).resolve() == folder
    assert not (folder.parent / ".miyagi-state" / "attempts").exists()


def test_continue_keeps_the_learners_code(lib_env):
    from server.sessions import store

    _, folder = lib_env
    _old_demo_folder(folder)
    mine = _solved_step1() + "\n# mine\n"
    (folder / "nn.py").write_text(mine, encoding="utf-8")
    graph = json.loads(curated.LESSON_FILE.read_text(encoding="utf-8"))
    graph["lesson"]["workdir"] = str(folder)
    store.save({"lessonId": LESSON_ID, "stepIndex": 2, "workdir": str(folder), "stopped": True}, graph=graph)
    eng, _ = _engine()

    async def go():
        assert await eng.session.resume()  # the library's Continue row
        await asyncio.sleep(0.05)
        await eng.session.drain()
    asyncio.run(go())
    assert (folder / "nn.py").read_text(encoding="utf-8") == mine
    assert eng.session.idx == 2


# ------------------------------------------------------------------------------------------ Start: one window

def _started_session(tmp_path, show):
    from server.orchestrator.modules import Modules
    from server.orchestrator.session import LessonSession

    async def emit(t, p=None):
        pass

    s = LessonSession(emit, Modules(demo=False, force_stubs="all"), idle_gate_s=5, advance_delay_s=0,
                      metric_eval_s=0, result_stagger_s=0, build_tick_s=0.01, seen_interval_s=0)
    s.ready_hold_s = 0
    s.has_clients = lambda: True
    s.learner_asked = False  # "Before you start" holds VS Code until Start
    calls: list[list[str]] = []
    ws = wsmod.Workspace(enabled=True, runner=lambda argv: calls.append(list(argv)) or True)
    ws.editor_check = lambda: None
    ws.show = show
    s.workspace = ws
    return s, calls


@pytest.fixture
def nn_lesson(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path / "work"))
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: None)
    from server.workspace import editor as E
    from server.workspace import vscode_ext

    monkeypatch.setattr(vscode_ext, "windows", lambda timeout=None: [])  # never this Mac's VS Code companion
    E.reset_open_state()
    monkeypatch.setattr(E, "preferred_editor", lambda installed=None: {
        "id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "cli": "/usr/local/bin/code",
        "bundle": "com.microsoft.VSCode", "process": "Code"})
    monkeypatch.setattr(E, "frontmost_app", lambda skip=None: None)
    monkeypatch.setattr(E, "_lesson_window_alive", lambda folder: pytest.fail("no real window list in a test"))
    work = tmp_path / "work"
    work.mkdir()
    (work / "nn.py").write_text(curated._starter(), encoding="utf-8")
    g = curated.lesson_for("build a neural network", force=True)
    g["lesson"]["workdir"] = str(work)
    yield g, work
    E.reset_open_state()


def _press_start(s, g):
    async def go():
        await s.load_graph(g)
        await s.drain()
        assert s.awaiting_start
        await s.action("start")
        await asyncio.sleep(0.05)
        await s.drain()
    asyncio.run(go())


def test_start_shows_the_file_in_the_open_window_without_the_cli(tmp_path, nn_lesson):
    g, work = nn_lesson
    shown: list = []
    s, calls = _started_session(tmp_path, lambda folder, file, line: shown.append((folder, file, line)) or True)
    _press_start(s, g)
    assert shown and Path(shown[-1][1]).name == "nn.py"
    assert not [c for c in calls if c and c[0].endswith("code")]  # no `code` CLI at all
    assert s.editor_open


def test_start_with_no_window_runs_one_code_open(tmp_path, nn_lesson):
    g, work = nn_lesson
    s, calls = _started_session(tmp_path, lambda folder, file, line: False)
    _press_start(s, g)
    opens = [c for c in calls if c and c[0].endswith("code")]
    assert opens == [["/usr/local/bin/code", str(work.resolve()), "-g", str((work / "nn.py").resolve())]]


# ------------------------------------------------------------------------------------------ never README.md

def test_open_without_a_file_never_opens_the_readme(tmp_path, monkeypatch):
    from server.workspace import core, vscode_ext
    from server.workspace import editor as E

    monkeypatch.setattr(vscode_ext, "windows", lambda timeout=None: [])
    E.reset_open_state()
    monkeypatch.setattr(E, "preferred_editor", lambda installed=None: {
        "id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "cli": "/usr/local/bin/code",
        "bundle": "com.microsoft.VSCode", "process": "Code"})
    monkeypatch.setattr(E, "frontmost_app", lambda skip=None: None)
    folder = tmp_path / "lessons" / "a-lesson-abc123"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("# hi\n", encoding="utf-8")
    sf = core._state_file(folder)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"scaffolded": True, "readme": "README.md", "files": []}), encoding="utf-8")
    calls: list[list[str]] = []
    ws = wsmod.Workspace(enabled=True, runner=lambda argv: calls.append(list(argv)) or True)
    try:
        ws.open(str(folder), full=True, file=None)
    finally:
        E.reset_open_state()
    opens = [c for c in calls if c and c[0].endswith("code")]
    assert opens == [["/usr/local/bin/code", str(folder.resolve())]]
    assert not any("README.md" in a for c in calls for a in c)
    assert core.open_file_for(folder) == "README.md"  # S2's own API keeps its README fallback
