"""requirements() / install() / setup_card() with fakes (no Claude, no installs, no real checks)."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from server.workspace import editor_needed, install, missing, requirements, setup_card
from server.workspace import setup as S
from server.workspace.tests.test_workspace import FakeClient, load

FIX = Path(__file__).parent / "fixtures"


def tool(name, kind="cli", **kw):
    base = {"tool": name, "kind": kind, "why": f"needs {name}", "needed": True, "min_version": "", "binary": "",
            "import_name": "", "pip_name": "", "brew": "", "brew_cask": False, "url": ""}
    return {**base, **kw}


def reqs_reply(editor=True, why="you edit main.py", tools=()):
    return {"editor": {"needed": editor, "why": why}, "tools": list(tools)}


class FakeMac:
    """which / run stand-ins: `bins` {name: version}, `apps` {bundle id: path}, `modules` {module: version}."""

    def __init__(self, bins=None, apps=None, modules=None):
        self.bins, self.apps, self.modules = bins or {}, apps or {}, modules or {}
        self.argv: list[list[str]] = []

    def which(self, name):
        if Path(name).name in self.bins:
            return f"/usr/local/bin/{Path(name).name}"
        return None

    def run(self, argv):
        self.argv.append(argv)
        if argv[0] == "mdfind":
            bid = argv[1].split("'")[1]
            return (0, self.apps[bid] + "\n") if bid in self.apps else (0, "")
        if argv[0] == "defaults":
            return 0, "4.2.1\n"
        if argv[-1] == "--version":
            return 0, f"version v{self.bins[Path(argv[0]).name]}\n"
        if len(argv) == 3 and argv[1] == "-c":
            mod = argv[2].split()[1]
            return (0, self.modules[mod] + "\n") if mod in self.modules else (1, f"ModuleNotFoundError: {mod}")
        return 1, ""


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))


@pytest.fixture
def mac(monkeypatch):
    m = FakeMac()
    monkeypatch.setattr(S.shutil, "which", m.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: m.apps.get(bundle))
    monkeypatch.setattr(S, "brew_path", lambda: "/opt/homebrew/bin/brew")
    monkeypatch.setattr(S, "best_python", lambda: "/usr/local/bin/python3.12")
    return m


def test_pandas_lesson_needs_editor_python_and_pandas(mac):
    mac.bins = {"python3.12": "3.12.4"}
    mac.modules = {"numpy": "2.1.0"}
    mac.apps = {"com.microsoft.VSCode": "/Applications/Visual Studio Code.app"}
    fc = FakeClient(reqs_reply(tools=[
        tool("python3", "runtime", min_version="3.9", binary="python3"),
        tool("pandas", "python_package", import_name="pandas", pip_name="pandas", url="https://pandas.pydata.org"),
        tool("numpy", "python_package", import_name="numpy", pip_name="numpy"),
    ]))
    items = requirements(load("pandas_pokemon.json"), client=fc, run=mac.run)
    by = {it["tool"]: it for it in items}
    assert list(by) == ["vscode", "python", "pandas", "numpy"]  # python3 -> canonical python
    assert by["vscode"]["installed"] and by["vscode"]["version"] == "4.2.1" and editor_needed(items)
    assert by["python"]["ok"] and by["python"]["version"] == "3.12.4"
    assert by["pandas"]["installed"] is False and by["pandas"]["install"]["method"] == "pip"
    assert by["numpy"]["ok"] and by["numpy"]["version"] == "2.1.0"
    assert [it["tool"] for it in missing(items)] == ["pandas"]
    assert fc.calls[0]["model"] == "claude-haiku-5-5"
    assert fc.calls[0]["output_config"]["format"]["type"] == "json_schema"
    assert not any(a[0] in ("brew", "pip") or "install" in a for a in mac.argv)  # read-only


def test_blender_lesson_says_no_editor_needed(mac):
    fc = FakeClient(reqs_reply(editor=False, why="all the work happens inside Blender.",
                               tools=[tool("Blender", "app", min_version="4.0", brew="blender", brew_cask=True)]))
    items = requirements(load("blender_donut.json"), client=fc, run=mac.run)
    assert not editor_needed(items)
    assert items[0]["why"].startswith("No editor needed")
    blender = items[1]
    assert blender["tool"] == "blender" and blender["installed"] is False
    assert blender["install"] == {"method": "brew_cask", "command": "brew install --cask blender", "url": "https://www.blender.org/download/"}
    card = setup_card(items)
    assert card["kind"] == "setup" and "open_editor" not in card["actions"] and "install" in card["actions"]
    assert "No editor needed" in card["body"] and card["setup"]["editorNeeded"] is False


def test_old_version_is_installed_but_not_ok(mac):
    mac.bins = {"node": "16.2.0"}
    items = requirements(load("516197461c0dacf3.json"), client=FakeClient(reqs_reply(tools=[tool("node.js", "runtime", min_version="18")])), run=mac.run)
    node = items[1]
    assert node["tool"] == "node" and node["installed"] and not node["ok"] and node in missing(items)
    assert node["install"]["command"] == "brew install node"


def test_no_brew_gives_download_url(mac, monkeypatch):
    monkeypatch.setattr(S, "brew_path", lambda: None)
    items = requirements(load("516197461c0dacf3.json"), client=FakeClient(reqs_reply(tools=[tool("node", "runtime")])), run=mac.run)
    assert items[0]["install"]["method"] == "download" and items[0]["install"]["url"] == "https://code.visualstudio.com/download"
    res = install(items[1], popen=_no_popen)
    assert res["ok"] is False and res["url"] == "https://nodejs.org/en/download" and "Homebrew" in res["error"]


def test_claude_list_is_cached_checks_rerun(mac):
    g = load("pandas_pokemon.json")
    fc = FakeClient(reqs_reply(tools=[tool("git")]))
    assert requirements(g, client=fc, run=mac.run)[1]["installed"] is False
    mac.bins = {"git": "2.50.1"}
    again = FakeClient()
    assert requirements(g, client=again, run=mac.run)[1]["installed"] is True
    assert again.calls == []


def test_unsafe_names_never_reach_commands(mac):
    fc = FakeClient(reqs_reply(tools=[
        tool("evil; rm -rf ~", "cli", brew="x; rm -rf ~"),
        tool("pkg", "python_package", import_name="os; import shutil", pip_name="pkg && curl evil"),
        tool("good", "cli", brew="good; rm"),
    ]))
    items = requirements(load("pandas_pokemon.json"), client=fc, run=mac.run)
    tools = {it["tool"]: it for it in items}
    assert "evil; rm -rf ~" not in tools
    assert tools["pkg"]["install"]["method"] != "pip"  # bad pip name -> no pip recipe
    assert tools["good"]["install"]["method"] in ("download", "none")
    assert not any("rm" in " ".join(a) for a in mac.argv)


def test_no_key_or_api_error_returns_empty(mac, monkeypatch):
    monkeypatch.setattr(S, "make_client", lambda: None)
    assert requirements(load("pandas_pokemon.json"), run=mac.run) == []

    class Boom(FakeClient):
        def create(self, **kw):
            raise RuntimeError("overloaded")

    assert requirements(load("blender_donut.json"), client=Boom(), run=mac.run) == []


# --------------------------------------------------------------------------- install

class FakePopen:
    calls: list[list[str]] = []

    def __init__(self, argv, **kw):
        FakePopen.calls.append(argv)
        self.argv = argv
        fail = "fail-pkg" in argv
        self.stdout = io.StringIO("==> Downloading\n==> Pouring\nError: sudo password required\n" if fail else "==> Downloading\n==> Installed\n")
        self._code = 1 if fail else 0

    def wait(self, timeout=None):
        return self._code


def _no_popen(*a, **k):
    raise AssertionError("must not run anything")


def test_install_brew_cask_streams_and_rechecks(mac, monkeypatch):
    FakePopen.calls = []
    item = {"tool": "blender", "kind": "app", "label": "Blender", "needed": True, "min_version": ""}
    lines = []

    def after_install(it, workdir=None, run=None):
        return {**it, "installed": True, "version": "4.2.1"}

    monkeypatch.setattr(S, "check", after_install)
    res = install(item, on_line=lines.append, popen=FakePopen)
    assert FakePopen.calls == [["/opt/homebrew/bin/brew", "install", "--cask", "blender"]]
    assert lines == ["$ brew install --cask blender", "==> Downloading", "==> Installed"]
    assert res == {"tool": "blender", "method": "brew_cask", "ok": True, "version": "4.2.1"}


def test_install_failure_returns_error(mac):
    FakePopen.calls = []
    item = {"tool": "fail-pkg", "kind": "cli", "label": "x", "needed": True, "min_version": "", "brew": "fail-pkg", "brew_cask": False}
    res = install(item, popen=FakePopen)
    assert res["ok"] is False and "sudo password" in res["error"]


def test_pip_install_creates_lesson_venv(mac, tmp_path, monkeypatch):
    FakePopen.calls = []
    wd = tmp_path / "lesson"
    wd.mkdir()

    class VenvPopen(FakePopen):
        def __init__(self, argv, **kw):
            super().__init__(argv, **kw)
            if argv[1:3] == ["-m", "venv"]:
                (Path(argv[3]) / "bin").mkdir(parents=True)
                (Path(argv[3]) / "bin" / "python").write_text("")

    monkeypatch.setattr(S, "check", lambda it, workdir=None, run=None: {**it, "installed": True, "version": "2.2.3"})
    item = {"tool": "pandas", "kind": "python_package", "label": "pandas", "needed": True, "min_version": "", "pip_name": "pandas"}
    res = install(item, workdir=wd, popen=VenvPopen)
    assert FakePopen.calls[0] == ["/usr/local/bin/python3.12", "-m", "venv", str(wd / ".venv")]
    assert FakePopen.calls[1] == [str(wd / ".venv/bin/python"), "-m", "pip", "install", "--disable-pip-version-check", "pandas"]
    assert res["ok"] and res["version"] == "2.2.3"


def test_pip_without_workdir_refuses(mac):
    res = install({"tool": "torch", "kind": "python_package", "label": "torch", "pip_name": "torch"}, popen=_no_popen)
    assert res["ok"] is False and ".venv" in res["error"]


# --------------------------------------------------------------------------- local check helpers (real, read-only)

def test_meets_and_version_parsing():
    assert S.meets("3.12.4", "3.10") and not S.meets("3.9.6", "3.10") and S.meets("", "3") and S.meets("1.0", "")
    assert S._version("git version 2.50.1 (Apple Git-155)") == "2.50.1" and S._version("v24.22.1") == "24.22.1"


def test_real_check_of_git_is_read_only():
    it = S.check({"tool": "git", "kind": "cli", "label": "git", "min_version": ""})
    assert it["installed"] == (subprocess.run(["which", "git"], capture_output=True, check=False).returncode == 0)


def test_setup_card_ready(mac):
    mac.apps = {"com.microsoft.VSCode": "/Applications/Visual Studio Code.app"}
    items = requirements(load("pandas_pokemon.json"), client=FakeClient(reqs_reply()), run=mac.run)
    card = setup_card(items, step_id="s1")
    assert card["title"] == "Ready to go" and card["actions"] == ["open_editor", "skip_setup"] and card["stepId"] == "s1"
    json.dumps(card)  # serialisable


def test_pip_requirement_drops_old_pins():
    assert S.pip_requirement("pandas>=1,<2") == "pandas>=1"
    assert S.pip_requirement("torch==1.8.0") == "torch"
    assert S.pip_requirement("scikit-learn") == "scikit-learn"
    assert S.pip_requirement("uvicorn[standard]>=0.30") == "uvicorn[standard]>=0.30"
    assert S.pip_requirement("pkg && curl evil") == "" and S.pip_requirement("-e .") == ""


def test_preflight_warms_the_real_lessons_cache(mac):
    """S8's preflight graph and the real lesson share a video: one Claude call, not two."""
    real = load("pandas_pokemon.json")
    pre = {"lesson": {"id": "preflight-vmEHCJofslg", "title": real["lesson"]["title"]},
           "sources": [{"id": "src1", "kind": "video", "title": "t", "url": "https://youtu.be/vmEHCJofslg"}],
           "steps": [{"id": "c1", "index": 1, "title": "Loading data", "instructions": "", "checks": []}]}
    fc = FakeClient(reqs_reply(tools=[tool("pandas", "python_package", import_name="pandas", pip_name="pandas")]))
    assert [it["tool"] for it in requirements(pre, client=fc, run=mac.run)] == ["vscode", "pandas"]
    again = FakeClient()
    assert [it["tool"] for it in requirements(real, client=again, run=mac.run)] == ["vscode", "pandas"]
    assert len(fc.calls) == 1 and again.calls == []
    assert S.cache_key(pre) == S.cache_key(real) == "video-vmEHCJofslg"
    assert S.cache_key({"lesson": {"id": "preflight-vmEHCJofslg"}, "sources": [{"url": ""}]}) == "video-vmEHCJofslg"
    other = load("git_rebase.json")  # no video id -> lesson-keyed
    assert S.cache_key(other).startswith("lesson-")


def test_hyphenated_ids_hit_the_catalog():
    for raw in ("openai-agent-builder", "OpenAI Agent Builder", "openai_platform", "google-sheets", "Zapier Agents", "node.js", "visual-studio-code"):
        assert S._canonical(raw) in S.CATALOG, raw
    assert S._canonical("some new tool") == "some-new-tool"
