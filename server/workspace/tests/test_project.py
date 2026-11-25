"""setup.scan / setup.fix for the open project (server/workspace/project.py): fixture projects, a fake Mac (no real
checks, no installs, no network), the contract's SetupReport shape."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

from server.workspace import project as P
from server.workspace import setup as S
from shared.contracts.events import validate_engine_payload

FIX = Path(__file__).parent / "fixtures" / "projects"


class FakeMac:
    """which / run stand-ins: `bins` {name: version}, `apps` {bundle id: path}, `modules` {module: version}."""

    def __init__(self, bins=None, apps=None, modules=None, clt=True):
        self.bins, self.apps, self.modules, self.clt = bins or {}, apps or {}, modules or {}, clt
        self.argv: list[list[str]] = []

    def which(self, name):
        return f"/usr/local/bin/{Path(name).name}" if Path(name).name in self.bins else None

    def run(self, argv, timeout=None):
        self.argv.append(list(argv))
        if argv[0] == "xcode-select":
            return (0, "/Library/Developer/CommandLineTools\n") if self.clt else (2, "")
        if argv[0] == "mdfind":
            return 0, ""
        if argv[-1] == "--version":
            name = Path(argv[0]).name
            v = self.bins.get(name) or self.bins.get("python" if name == "python" else name)
            return (0, f"version v{v}\n") if v else (127, "not found")
        if len(argv) == 4 and argv[1] == "-c":  # the batched import probe
            lines = []
            for i, (cands, _dist) in enumerate(json.loads(argv[3])):
                hit = next((m for m in cands if m in self.modules), None)
                lines.append(json.dumps({"i": i, "ok": True, "mod": hit, "ver": self.modules[hit]} if hit else {"i": i, "ok": False}))
            return 0, "\n".join(lines)
        return 1, ""


@pytest.fixture
def mac(monkeypatch):
    m = FakeMac()
    monkeypatch.setattr(S.shutil, "which", m.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: m.apps.get(bundle))
    monkeypatch.setattr(S, "brew_path", lambda: "/opt/homebrew/bin/brew")
    monkeypatch.setattr(S, "best_python", lambda: "/usr/local/bin/python3.12")
    return m


def weather(tmp_path: Path, venv: bool = True) -> Path:
    root = tmp_path / "weather-app"
    shutil.copytree(FIX / "weather-app", root)
    if venv:
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".venv" / "pyvenv.cfg").write_text("home = /usr/local/bin\n")
        (root / ".venv" / "bin" / "python").write_text("")
    return root


def full(root: Path, mac: FakeMac, **kw) -> dict:
    kw.setdefault("node", "/usr/local/bin/node")
    rep = P.scan(str(root), req_id="scan-1", run=mac.run, **kw)
    validate_engine_payload("setup.report", {k: v for k, v in rep.items() if not k.startswith("_")})
    return rep


# --------------------------------------------------------------------------- reading the files

def test_requirements_lines_names_floors_and_skips():
    rows = P.parse_requirements((FIX / "weather-app" / "requirements.txt").read_text())
    assert [(r["tool"], r["from"], r["min_version"]) for r in rows] == [
        ("requests", "requirements.txt:1", "2.31"), ("pandas", "requirements.txt:3", ""),
        ("matplotlib", "requirements.txt:4", "")]  # an exact pin is not a floor; -e / git+ / --index-url never followed
    assert rows[0]["pip_name"] == "requests>=2.31"


def test_pyproject_poetry_pipfile_environment_and_version_files():
    rows, floor, clis = P.parse_pyproject(
        '[project]\nname = "x"\nrequires-python = ">=3.11"\ndependencies = [\n  "numpy>=1.26",\n  "rich",\n]\n'
        '[tool.uv]\ndev-dependencies = []\n')
    assert [(r["tool"], r["from"], r["min_version"]) for r in rows] == [("numpy", "pyproject.toml:5", "1.26"),
                                                                       ("rich", "pyproject.toml:6", "")]
    assert floor == "3.11" and clis == {"uv"}
    rows, floor, clis = P.parse_pyproject('[tool.poetry.dependencies]\npython = "^3.10"\nflask = "^3.0"\n')
    assert [(r["tool"], r["min_version"]) for r in rows] == [("flask", "3.0")] and floor == "3.10" and clis == {"poetry"}
    rows, floor = P.parse_pipfile('[packages]\ndjango = "*"\n\n[requires]\npython_version = "3.11"\n')
    assert [r["tool"] for r in rows] == ["django"] and floor == "3.11"
    rows, floor = P.parse_environment_yml("name: lab\ndependencies:\n  - python=3.11\n  - numpy\n  - conda-forge::scipy>=1.11\n"
                                          "  - pip\n  - pip:\n    - torch\n")
    assert [r["tool"] for r in rows] == ["numpy", "scipy", "torch"] and floor == "3.11"
    assert P.parse_version_file("v20.11.1\n") == "20.11" and P.parse_version_file("20") == "20"
    assert P.parse_version_file("lts/*") == "" and P.parse_version_file("3.12.4") == "3.12"
    deps, floor = P.parse_package_json('{"dependencies": {"a": "1"}, "devDependencies": {"b": "2"}, "engines": {"node": ">=18.17"}}')
    assert deps == {"a": "1", "b": "2"} and floor == "18.17"
    assert P.makefile_clis("all:\n\tpoetry install\n\t@docker build .\n\techo hi\n") == ["make", "poetry", "docker"]


def test_find_root_walks_up_from_a_file_to_the_manifests(tmp_path):
    root = weather(tmp_path, venv=False)
    assert P.find_root(root / "src" / "app.py") == root.resolve()
    assert P.find_root(root / "src") == root.resolve()
    lone = tmp_path / "notes"
    lone.mkdir()
    assert P.find_root(lone) == lone.resolve()  # no manifest anywhere: the folder itself (an empty report)


# --------------------------------------------------------------------------- the report

def test_weather_app_report_missing_first_with_from_env_and_next(tmp_path, mac):
    root = weather(tmp_path)
    mac.bins = {"python": "3.12.4", "node": "18.19.0", "make": "3.81"}
    mac.modules = {"requests": "2.32.3"}
    rep = full(root, mac)
    assert rep["reqId"] == "scan-1" and rep["name"] == "weather-app" and rep["_path"] == str(root.resolve())
    assert rep["files"] == ["requirements.txt", ".python-version", "package.json", ".nvmrc", "Dockerfile", "Makefile"]
    by = {it["tool"]: it for it in rep["items"]}
    order = [it["tool"] for it in rep["items"]]
    assert order[:6] == ["pandas", "matplotlib", "node", "node_modules", "docker", "uv"]  # missing first
    assert set(order[6:]) == {"python", "requests", "make"}
    assert rep["ready"] == 3 and rep["total"] == 9 and "more" not in rep
    assert by["pandas"]["from"] == "requirements.txt:3" and by["pandas"]["install"]["method"] == "pip"
    assert by["pandas"]["actions"][0] == "install" and by["pandas"]["kind"] == "python_package"
    assert by["requests"]["ok"] and by["requests"]["version"] == "2.32.3" and by["requests"]["actions"] == []
    assert by["node"]["label"] == "Node.js 20.11" and by["node"]["from"] == ".nvmrc"
    assert by["node"]["why"] == ".nvmrc asks for Node 20.11; this Mac has 18.19.0" and by["node"]["minVersion"] == "20.11"
    assert by["node"]["install"]["method"] == "brew" and by["node"]["install"]["command"] == "brew install node"
    nm = by["node_modules"]
    assert nm["kind"] == "node_package" and nm["label"] == "Node packages (3)" and nm["from"] == "package.json"
    assert nm["install"] == {"method": "npm", "command": "npm install", "url": None} and nm["actions"] == ["install"]
    assert nm["why"] == "package.json lists them; none installed yet"
    assert by["docker"]["from"] == "Dockerfile" and by["docker"]["install"]["method"] == "brew_cask"
    assert by["uv"]["from"] == "Makefile" and by["uv"]["install"]["command"] == "brew install uv"
    assert by["python"]["ok"] and by["python"]["from"] == ".python-version"
    assert rep["env"]["python"].endswith("weather-app/.venv (Python 3.12.4)") and rep["env"]["node"] == "node 18.19.0"
    assert rep["next"] == "Install pandas first. Then 5 more."
    # read-only: version checks and the import probe, never an installer, never a project script
    assert not any(a[0].endswith(("brew", "npm", "pip")) or "install" in a for a in mac.argv)
    assert not any(a[0] == "make" or a[-1] == "dev" for a in mac.argv)


def test_quick_answer_reads_files_only(tmp_path, mac):
    root = weather(tmp_path)
    rep = P.scan(str(root), quick=True, run=mac.run)
    assert rep["scanning"] is True and rep["items"] == [] and "package.json" in rep["files"]
    assert mac.argv == []  # no subprocess at all


def test_ready_project_and_next_steps(tmp_path, mac):
    root = tmp_path / "tidy"
    root.mkdir()
    (root / "requirements.txt").write_text("requests\n")
    mac.modules = {"requests": "2.32.3"}
    rep = full(root, mac, python="/usr/local/bin/python3.12")
    assert rep["ready"] == rep["total"] == 1 and rep["next"] == "Everything this project asks for is here."
    assert rep["env"]["python"] == "python3.12, no project .venv yet"
    (root / "requirements.txt").write_text("requests\nnumpy\nscipy\n")
    rep = full(root, mac, python="/usr/local/bin/python3.12")
    assert rep["next"] == "Install numpy and 1 more Python package into a new .venv in this folder."
    empty = tmp_path / "empty"
    empty.mkdir()
    rep = full(empty, mac)
    assert rep["files"] == [] and rep["items"] == [] and rep["next"].startswith("No project files here yet")


def test_python_too_old_for_the_project_asks_for_a_newer_one(tmp_path, mac):
    root = weather(tmp_path)
    (root / ".python-version").write_text("3.13\n")
    mac.bins = {"python": "3.12.4", "node": "20.11.1", "make": "3.81"}
    mac.modules = {"requests": "2.32.3", "pandas": "2.2.0", "matplotlib": "3.8.0"}
    rep = full(root, mac)
    py = rep["items"][0]
    assert py["tool"] == "python@3.13" and py["label"] == "Python 3.13" and not py["ok"]
    assert py["why"] == ".python-version asks for Python 3.13; the .venv uses 3.12.4"
    assert py["install"]["command"] == "brew install python@3.13"
    assert rep["next"].startswith("Install Python 3.13, then make the project's .venv again with it.")


def test_yarn_project_shows_its_own_command_and_partial_node_modules(tmp_path, mac):
    root = weather(tmp_path)
    (root / "yarn.lock").write_text("")
    (root / "node_modules" / "react").mkdir(parents=True)
    (root / "node_modules" / "react" / "package.json").write_text("{}")
    mac.bins = {"node": "20.11.1"}
    rep = full(root, mac)
    by = {it["tool"]: it for it in rep["items"]}
    assert by["node_modules"]["install"]["method"] == "none" and by["node_modules"]["install"]["command"] == "yarn install"
    assert by["node_modules"]["why"] == "package.json lists them; 2 not installed yet"
    assert by["yarn"]["from"] == "yarn.lock" and not by["yarn"]["ok"]


def test_make_without_developer_tools_is_never_run(tmp_path, mac):
    root = tmp_path / "c-proj"
    root.mkdir()
    (root / "Makefile").write_text("all:\n\tcc main.c\n")
    mac.clt = False
    mac.bins = {"make": "3.81"}  # /usr/bin/make is there, but it's Apple's stub
    rep = full(root, mac)
    make = rep["items"][0]
    assert make["tool"] == "make" and not make["installed"] and make["install"]["command"] == "xcode-select --install"
    assert rep["next"] == "make is missing. Run xcode-select --install in Terminal."
    assert not any(a[0].endswith("make") for a in mac.argv)


def test_long_requirements_sends_missing_rows_and_counts_the_rest(tmp_path, mac):
    root = tmp_path / "big"
    root.mkdir()
    (root / "requirements.txt").write_text("".join(f"pkg{i}\n" for i in range(30)) + "requests\n")
    mac.modules = {"requests": "2.32.3"}
    rep = full(root, mac, python="/usr/local/bin/python3.12")
    assert len(rep["items"]) == P.MAX_ROWS and rep["more"] == 31 - P.MAX_ROWS and rep["total"] == 31
    assert all(not it["ok"] for it in rep["items"])


def test_scan_errors(tmp_path, mac, monkeypatch):
    assert P.scan(None, folder=lambda: None)["error"] == "no_project"
    assert P.scan(str(tmp_path / "gone"))["error"] == "unreadable"
    big = tmp_path / "huge"
    big.mkdir()
    (big / "requirements.txt").write_text("x" * (P.MAX_FILE_BYTES + 1))
    assert P.scan(str(big), run=mac.run)["error"] == "too_big"
    monkeypatch.setattr(P.Path, "home", lambda: tmp_path)
    assert P.scan(str(tmp_path), run=mac.run)["error"] == "no_project"  # the home folder itself is never a project
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "package.json").write_text("{nope")
    assert P.scan(str(bad), run=mac.run)["error"] == "unreadable"


def test_no_path_uses_the_open_folder(tmp_path, mac):
    root = weather(tmp_path)
    rep = P.scan(None, folder=lambda: str(root / "src" / "app.py"), quick=True)
    assert rep["name"] == "weather-app" and rep["scanning"]


# --------------------------------------------------------------------------- where the project is

def test_open_folder_prefers_the_front_terminal_then_vscode_then_any_terminal():
    calls = []

    def term(pid):
        calls.append(pid)
        return {11: "/Users/x/code/api", 22: "/Users/x/code/site"}.get(pid)

    assert P.open_folder(front=lambda: ("com.apple.Terminal", "Terminal", 11), editor=lambda: {"folder": "/v"},
                         terminal=term, terminals=list) == "/Users/x/code/api"
    assert P.open_folder(front=lambda: ("com.github.Electron", "miyagi", 5), editor=lambda: {"folder": "/v/app"},
                         terminal=term, terminals=lambda: [22]) == "/v/app"
    assert P.open_folder(front=lambda: ("com.github.Electron", "miyagi", 5), editor=lambda: {"folder": None, "path": "/v/a/b.py"},
                         terminal=term, terminals=lambda: [22]) == "/v/a"
    assert P.open_folder(front=lambda: None, editor=lambda: None, terminal=term, terminals=lambda: [22]) == "/Users/x/code/site"
    assert P.open_folder(front=lambda: None, editor=lambda: None, terminal=term, terminals=list) is None


def test_terminal_cwd_reads_the_newest_shell_under_the_app():
    def run(argv, timeout=None):
        if argv[0] == "ps":
            return 0, (" 100 1 /System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal\n"
                       " 200 100 login\n 201 200 -zsh\n 300 100 login\n 301 300 -zsh\n 400 1 -zsh\n")
        if argv[0] == "lsof":
            return 0, f"p{argv[-2]}\nfcwd\nn/Users/x/code/shell{argv[-2]}\n"
        return 1, ""

    assert P.terminal_cwd(100, run=run) == "/Users/x/code/shell301"


# --------------------------------------------------------------------------- setup.fix

def test_fix_pip_row_installs_into_the_project_venv(tmp_path, mac):
    root = weather(tmp_path)
    mac.bins = {"python": "3.12.4"}
    got = {}

    def fake_install(item, *, workdir=None, on_line=None, python=None):
        got.update(item=item, workdir=workdir, python=python)
        on_line("Successfully installed pandas-2.2.3")
        return {"ok": True, "tool": item["tool"], "method": "pip", "version": "2.2.3"}

    lines = []
    res = P.fix("pandas", str(root), on_line=lines.append, install=fake_install, run=mac.run, node=None)
    assert res["ok"] and got["workdir"] == root.resolve() and got["python"] == str(root.resolve() / ".venv" / "bin" / "python")
    assert got["item"]["from"] == "requirements.txt:3" and lines == ["Successfully installed pandas-2.2.3"]
    res = P.fix("pandas", str(root), on_line=lines.append, install=fake_install, run=mac.run, node=None, confirmed="pandas")
    assert got["item"]["confirmed"] == "pandas"


def test_fix_only_installs_what_the_project_asks_for(tmp_path, mac):
    root = weather(tmp_path)

    def never(*_a, **_k):
        raise AssertionError("installed something the project never asked for")

    res = P.fix("left-pad-evil", str(root), install=never, npm=never, run=mac.run, node=None)
    assert res == {"tool": "left-pad-evil", "ok": False, "error": "This project doesn't ask for that any more."}
    mac.modules = {"requests": "2.32.3"}
    assert P.fix("requests", str(root), install=never, run=mac.run, node=None)["ok"]  # already there: nothing runs
    assert P.fix("x", str(tmp_path / "gone"), install=never)["error"] == "That project folder isn't there any more."


def test_fix_npm_row_and_a_none_row(tmp_path, mac):
    root = weather(tmp_path)
    mac.bins = {"node": "20.11.1"}
    seen = []
    res = P.fix("node_modules", str(root), npm=lambda r, on_line=None: seen.append(r) or {"ok": True, "tool": "node_modules"},
                run=mac.run)
    assert res["ok"] and seen == [root.resolve()]
    (root / "yarn.lock").write_text("")
    res = P.fix("node_modules", str(root), run=mac.run)
    assert not res["ok"] and res["error"] == "Run yarn install in Terminal."


class FakePopen:
    def __init__(self, argv, **kw):
        self.argv, self.kw = argv, kw
        FakePopen.last = self
        root = Path(argv[argv.index("--prefix") + 1])
        for name in ("react", "react-dom", "vite"):
            (root / "node_modules" / name).mkdir(parents=True, exist_ok=True)
            (root / "node_modules" / name / "package.json").write_text("{}")
        self.stdout = io.StringIO("added 3 packages in 2s\n")

    def wait(self, timeout=None):
        return 0


def test_npm_install_runs_in_the_project_with_a_clean_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-never-passed-on-xxxxxxxxxxxx")
    root = weather(tmp_path, venv=False)
    lines = []
    res = P.npm_install(root, on_line=lines.append, popen=FakePopen, npm="/opt/homebrew/bin/npm")
    assert res["ok"] and lines == ["$ npm install", "added 3 packages in 2s"]
    argv, env = FakePopen.last.argv, FakePopen.last.kw["env"]
    assert argv[:2] == ["/opt/homebrew/bin/npm", "install"] and argv[-1] == str(root)
    assert "ANTHROPIC_API_KEY" not in env and env["PATH"].startswith("/opt/homebrew/bin")
    assert P.npm_install(root, npm=None)["error"].startswith("Node.js isn't installed")


def test_install_pips_into_a_given_interpreter(tmp_path, monkeypatch):
    """setup.install(python=...): a project's own venv/ (not .venv) gets the package; no .venv is made."""
    class Pop:
        def __init__(self, argv, **kw):
            Pop.argv = argv
            self.stdout = io.StringIO("ok\n")

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(S, "check_python_packages", lambda items, py, **k: [it.update(installed=True, version="2.2.3")
                                                                            for it in items])
    item = {"tool": "pandas", "kind": "python_package", "pip_name": "pandas", "label": "pandas", "needed": True,
            "min_version": ""}
    res = S.install(item, workdir=tmp_path, popen=Pop, python="/p/venv/bin/python", net=lambda _h: True)
    assert res["ok"] and Pop.argv[:4] == ["/p/venv/bin/python", "-m", "pip", "install"] and Pop.argv[-1] == "pandas"
    assert not (tmp_path / ".venv").exists()


def test_a_newer_python_beside_the_default_one_counts_without_a_venv(tmp_path, mac):
    root = tmp_path / "new-py"
    root.mkdir()
    (root / ".python-version").write_text("3.13\n")
    mac.bins = {"python3.12": "3.12.4"}
    rep = full(root, mac)
    assert not rep["items"][0]["ok"] and rep["items"][0]["install"]["command"] == "brew install python@3.13"
    mac.bins["python3.13"] = "3.13.1"  # installed with the row's Install
    rep = full(root, mac)
    assert rep["items"][0]["ok"] and rep["items"][0]["version"] == "3.13.1" and rep["ready"] == 1
