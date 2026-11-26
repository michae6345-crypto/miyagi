"""Desktop test 10: the preflight card checks a lesson's Python packages where the setup card does after Build (the
lesson folder's own .venv), so the two agree. Test 10 showed "tensorflow ✕ numpy ✕ … · 4 to install" for a cached
lesson whose .venv had all four (preflight checked the build's placeholder folder `_new`, so the system Python), and
then no setup card came.

Temp lesson folders, a fake .venv (an empty file named python) and a fake runner standing in for the interpreter:
no pip, no network, no keys. S2's tool list is a cached file, so there's no Claude call either."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from server.preflight import core, needs_line, preflight, preflight_card
from server.preflight.tests.test_preflight import CODING, KEYS, FakeClaude, transport
from server.workspace import lesson_folder, paths, setup

VID = "kCc8FmEb1nY"
URL = f"https://www.youtube.com/watch?v={VID}"
GOAL = "build a neural network"
PACKAGES = ("jupyter", "tensorflow", "numpy", "matplotlib")
TOOLS = {  # S2's list for the video (the shape Claude returns), as test 10's cache had it
    "editor": {"needed": True, "why": "The steps run code in VS Code."},
    "tools": [{"tool": t, "kind": "python_package", "why": "", "needed": True, "min_version": "", "binary": "",
               "import_name": t, "pip_name": t, "brew": "", "brew_cask": False, "url": f"https://pypi.org/project/{t}/"}
              for t in PACKAGES],
}
GRAPH = {"lesson": {"id": "lesson-t10", "title": "Build Your First Neural Network with TensorFlow"},
         "sources": [{"kind": "video", "videoId": VID, "url": URL}],
         "steps": [{"index": i, "title": f"s{i}"} for i in range(7)]}


class FakePython:
    """Runs the setup check's import probe as if `have[python]` were installed in that Python (nothing elsewhere)."""

    def __init__(self) -> None:
        self.have: dict[str, set[str]] = {}
        self.probed: list[str] = []

    def __call__(self, argv: list[str]) -> tuple[int, str]:
        if len(argv) == 4 and argv[1] == "-c":
            self.probed.append(argv[0])
            have = self.have.get(argv[0], set())
            out = []
            for i, (cands, _dist) in enumerate(json.loads(argv[3])):
                mod = next((c for c in cands if c in have), None)
                out.append(json.dumps({"i": i, "ok": True, "mod": mod, "ver": "9.0.0"} if mod else {"i": i, "ok": False}))
            return 0, "\n".join(out)
        return 1, ""  # mdfind / defaults / --version: nothing found


@pytest.fixture
def lessons(tmp_path, monkeypatch):
    root = tmp_path / "lessons"
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(root))
    for k in ("TUT_WORKDIR", "DEMO", "ORCH_HERO_WORKDIR", "ORCH_HERO_LESSON_IDS", "ORCH_LESSON_URL"):
        monkeypatch.delenv(k, raising=False)
    req = root / ".miyagi-state" / "requirements"
    req.mkdir(parents=True)
    (req / f"video-{VID}.json").write_text(json.dumps(TOOLS), encoding="utf-8")  # S2's cached list: no Claude call
    core.clear_memo()
    yield root
    core.clear_memo()


def make_venv(folder: Path) -> str:
    py = paths.venv_python(folder / ".venv")  # bin/python; Scripts\python.exe on Windows
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    site = folder / ".venv" / ("Lib" if paths._windows() else "lib/python3.12") / "site-packages"
    site.mkdir(parents=True)
    return str(py)


def req_fn(fake: FakePython):
    """S2's requirements() as preflight calls it (the setup card calls the same function with the lesson folder)."""
    def req(graph, *, workdir=None):
        return setup.requirements(graph, workdir=workdir, run=fake, client=None)
    return req


async def _pf(fake: FakePython, hit) -> dict:
    async with httpx.AsyncClient(transport=transport()) as http:
        return await preflight(URL, GOAL, keys=KEYS, http=http, claude_client=FakeClaude(CODING),
                               requirements_fn=req_fn(fake), lesson_cache=lambda u, g: hit() if callable(hit) else hit)


def packages(items: list[dict]) -> dict[str, bool]:
    return {it["tool"]: bool(it.get("ok")) for it in items if it["kind"] == "python_package"}


def test_lesson_folder_is_prepares_folder_found_read_only(lessons, monkeypatch):
    from server.orchestrator import workspace as e4
    from server.workspace import core as ws_core

    own = (lessons / paths.folder_name(GRAPH)).resolve()
    assert lesson_folder(GRAPH) == own and not own.exists()  # found, never created
    assert e4.lesson_folder(GRAPH) == str(own)
    other = lessons.parent / "my-own-folder"
    other.mkdir()
    ws_core._state_file(own).write_text(json.dumps({"redirect": str(other)}), encoding="utf-8")  # "use this folder"
    assert lesson_folder(GRAPH) == other
    monkeypatch.setenv("TUT_WORKDIR", str(other))
    assert Path(e4.lesson_folder(GRAPH)).resolve() == other.resolve()  # a pinned folder is the lesson's folder


def test_cached_lesson_names_the_real_lesson_folder(lessons, tmp_path, monkeypatch):
    from server.lesson import builder
    from server.lesson.workdir import scan

    monkeypatch.setattr(builder, "CACHE_DIR", tmp_path / "cache")
    builder.CACHE_DIR.mkdir()
    workdir = core._build_workdir(URL, GOAL)
    assert Path(workdir).name == "_new"  # the build's placeholder: never where the lesson's .venv lives
    (builder.CACHE_DIR / f"{builder.cache_key(URL, GOAL, workdir, scan(workdir))}.json").write_text(json.dumps(GRAPH), encoding="utf-8")
    hit = core.cached_lesson(URL, GOAL)
    assert hit["workdir"] == workdir and hit["folder"] is None  # not built into its folder yet
    own = lessons / paths.folder_name(GRAPH)
    own.mkdir()
    assert Path(core.cached_lesson(URL, GOAL)["folder"]) == own.resolve()


def test_t10_preflight_checks_the_lesson_venv_like_the_setup_card(lessons):
    """Test 10 CP3: everything is in the lesson's .venv: preflight says so (no "to install", no Install), and the setup
    check after Build (same function, same folder) agrees."""
    own = lessons / paths.folder_name(GRAPH)
    own.mkdir()
    venv_py = make_venv(own)
    fake = FakePython()
    fake.have[venv_py] = set(PACKAGES)
    hit = {"graph": GRAPH, "file": "x.json", "steps": 7, "workdir": str(lessons / "_new"), "folder": str(own)}
    res = asyncio.run(_pf(fake, hit))
    assert packages(res["requirements"]) == dict.fromkeys(PACKAGES, True)
    assert fake.probed == [venv_py]  # the lesson's .venv, not the system Python
    card = preflight_card(res)
    assert "install" not in card["actions"] and "to install" not in card["body"] and "✗" not in card["body"]
    assert not [it for it in card["items"] if it["needed"] and not it["ok"] and it["kind"] == "python_package"]
    after_build = setup.requirements(GRAPH, workdir=str(own), run=fake, client=None)  # what the setup card reads
    assert packages(after_build) == packages(res["requirements"])
    assert not [it for it in setup.missing(after_build) if it["kind"] == "python_package"]  # so no setup card


def test_no_lesson_venv_yet_says_what_the_setup_card_will_do(lessons):
    """No .venv yet: the packages are what the setup card will install into the lesson's .venv (no "✗"), and both
    cards count the same rows to install."""
    fake = FakePython()
    hit = {"graph": GRAPH, "file": "x.json", "steps": 7, "workdir": str(lessons / "_new"), "folder": None}
    res = asyncio.run(_pf(fake, hit))
    assert packages(res["requirements"]) == dict.fromkeys(PACKAGES, False)
    card = preflight_card(res)
    assert needs_line(res["requirements"]).endswith("Jupyter, tensorflow, numpy, matplotlib (to install in the lesson's .venv)")
    assert "✗" not in needs_line(res["requirements"]) and "Needs" not in card["body"] and "install" in card["actions"]
    after_build = setup.requirements(GRAPH, workdir=str(lessons / paths.folder_name(GRAPH)), run=fake, client=None)
    app_count = {it["tool"] for it in card["items"] if it["needed"] and not it["ok"] and it["kind"] == "python_package"}
    assert app_count == {it["tool"] for it in setup.missing(after_build) if it["kind"] == "python_package"}


def test_memoised_preflight_rechecks_when_the_lesson_venv_changed(lessons):
    """Prefetched before the build (no .venv), built + installed, picked again inside the 10 min memo: the card
    reads the new .venv, not the old "to install"."""
    own = lessons / paths.folder_name(GRAPH)
    own.mkdir()
    fake = FakePython()
    hit = {"graph": GRAPH, "file": "x.json", "steps": 7, "workdir": str(lessons / "_new"), "folder": str(own)}
    first = asyncio.run(_pf(fake, hit))
    assert packages(first["requirements"]) == dict.fromkeys(PACKAGES, False) and first["lessonVenv"] is None
    fake.have[make_venv(own)] = set(PACKAGES)  # the build made the .venv; Install filled it
    again = asyncio.run(_pf(fake, hit))
    assert "cached" not in again and packages(again["requirements"]) == dict.fromkeys(PACKAGES, True)
    third = asyncio.run(_pf(fake, hit))  # nothing changed since: the memo answers
    assert third.get("cached") and packages(third["requirements"]) == dict.fromkeys(PACKAGES, True)
