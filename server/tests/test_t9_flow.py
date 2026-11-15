"""Desktop test 9 ("Watch a video", Nov 15 2026): the video lesson's start flow. Offline: fake setup check, fake
installer, a recording runner instead of VS Code. Run: python -m pytest server/tests/test_t9_flow.py -q"""

from __future__ import annotations

import asyncio

import pytest

from server.orchestrator import stubs
from server.orchestrator.tests.test_session import Rig, run

PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY",
             "TIGER_DATABASE_URL")


@pytest.fixture(autouse=True)
def _isolated_and_free(tmp_path_factory, monkeypatch):
    """As server/orchestrator/tests/conftest.py: no ~/miyagi/state, no paid keys, no watch-page fetches."""
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path_factory.mktemp("miyagi-state")))
    for k in PAID_KEYS:
        monkeypatch.setenv(k, "")
    monkeypatch.delenv("DEMO", raising=False)
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(wsmod, "find_resources", lambda graph: [])


def _item(tool: str, label: str, kind: str, ok: bool, method: str = "pip") -> dict:
    return {"tool": tool, "label": label, "kind": kind, "why": f"{label} for this lesson", "needed": True,
            "installed": ok, "ok": ok, "version": "1.0" if ok else None,
            "install": {"method": "none" if kind == "editor" else method,
                        "command": None if kind == "editor" else f"pip install {tool}", "url": None}}


def notebook_lesson(colab: bool = False) -> dict:
    """Test 9's shape: a Jupyter notebook lesson built from a video (step 1 starts Jupyter)."""
    g = stubs.load_fixture_lesson()
    g["lesson"]["title"] = "Build Your First Neural Network with TensorFlow"
    g["steps"][0]["title"] = "Open the notebook in Colab" if colab else "Create venv and start Jupyter"
    return g


def _rig(tmp_path, monkeypatch, items_fn):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod
    from server.orchestrator.workspace import Workspace
    from server.workspace import setup_card

    monkeypatch.setattr(wsmod, "requirements", lambda graph, folder: items_fn())
    monkeypatch.setattr(wsmod, "setup_card", setup_card)
    calls: list[list[str]] = []
    rig = Rig(tmp_path)
    rig.s.workspace = Workspace(enabled=True, runner=lambda argv: calls.append(argv) or True)
    return rig, calls


# ---------------------------------------------------------------- V8: VS Code opens by itself


def test_v8_notebook_video_lesson_opens_vscode_alongside_the_setup_card(tmp_path, monkeypatch):
    """t9 V8: the Jupyter video lesson waited on "Open VS Code" (06:14:17) while the curated lesson opens VS Code by
    itself. Now the setup card goes out without Open (and without "Open the lesson folder…?") and VS Code opens."""
    state = {"jupyter": False}
    rig, calls = _rig(tmp_path, monkeypatch, lambda: [
        _item("vscode", "Visual Studio Code", "editor", True), _item("jupyter", "Jupyter", "python_package", state["jupyter"])])

    async def go():
        await rig.s.load_graph(notebook_lesson())
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    assert rig.s.notebook_lesson
    setup = [c for c in rig.of("card") if c["kind"] == "setup"]
    assert setup and "open_editor" not in setup[0]["actions"] and "install" in setup[0]["actions"]
    assert "Open the lesson folder" not in setup[0]["body"]
    assert rig.s.editor_open and [c for c in calls if str(tmp_path.resolve()) in c], calls


def test_v8_nothing_missing_opens_vscode_without_a_card(tmp_path, monkeypatch):
    rig, calls = _rig(tmp_path, monkeypatch, lambda: [_item("vscode", "Visual Studio Code", "editor", True),
                                                      _item("jupyter", "Jupyter", "python_package", True)])

    async def go():
        await rig.s.load_graph(notebook_lesson())
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    assert rig.s.editor_open and calls
    assert not [c for c in rig.of("card") if c["kind"] == "setup"]


def test_v8_colab_lesson_never_opens_vscode(tmp_path, monkeypatch):
    rig, calls = _rig(tmp_path, monkeypatch, lambda: [_item("vscode", "Visual Studio Code", "editor", True),
                                                      _item("jupyter", "Jupyter", "python_package", False)])

    async def go():
        await rig.s.load_graph(notebook_lesson(colab=True))
        await asyncio.sleep(0.05)
        await rig.settle()

    run(go())
    assert not rig.s.editor_open and not calls
    setup = [c for c in rig.of("card") if c["kind"] == "setup"]
    assert setup and "open_editor" in setup[0]["actions"]  # unchanged: the learner decides
