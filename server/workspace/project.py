"""Set up this project (ambient help, AMBIENT-HELP.md section 2): what the open project asks for, read from its own files.

    rep = scan(path)                  # setup.report payload: read-only, no model call, never runs a project script
    quick = scan(path, quick=True)    # the first answer (scanning: true, no checks), within ~100 ms
    res = fix(tool, root, on_line=cb) # ONLY after the learner pressed Install on that row: the existing install path

What it reads (the project's own files, nothing else): requirements*.txt, pyproject.toml, Pipfile, environment.yml,
.python-version, package.json, .nvmrc, .node-version, Dockerfile, docker-compose.yml, Makefile (which CLIs its recipes
call). What it checks on this Mac: the project's Python (its .venv / venv when it has one, else the Python a new .venv
would be made from), whether each package imports in it (setup.check_python_packages: one interpreter run), node's
version, node_modules against package.json, and the CLIs those files call (`which`).

Rows are the contract's SetupItem (setup._row) plus `from` ("requirements.txt:4", ".nvmrc"), kind node_package (every
package.json dependency as one row) and install method npm. `next` on the report is one plain sentence saying what to
do first (additive: the app may show it under the card's title).

fix() goes through setup.install (brew, allowlisted casks, pip with the safety.packages verdict) with the project's
own interpreter, or `npm install` in the project folder. The argv is rebuilt from the row's validated name: never a
string from the app or the project's files.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

from . import setup as _setup

log = logging.getLogger("server.workspace.project")

Runner = Callable[..., tuple[int, str]]

MANIFESTS = ("requirements.txt", "pyproject.toml", "Pipfile", "environment.yml", "environment.yaml", ".python-version",
             "package.json", ".nvmrc", ".node-version", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
             "compose.yaml", "Makefile")
EXTRA_REQUIREMENTS = re.compile(r"^requirements[-_.]?[\w-]*\.txt$")  # requirements-dev.txt: read, rows marked optional
MAX_FILE_BYTES = 256 * 1024  # a manifest bigger than this is not a hand-written project file: too_big
MAX_PACKAGES = 300           # python packages checked in one probe
MAX_ROWS = 20                # rows sent: every missing one first (up to this many), then ready ones; `more` counts the rest
UP_LEVELS = 4                # from the file the editor has open up to the folder holding the manifests
VENV_DIRS = (".venv", "venv", "env", ".env-venv")
NODE_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")  # an app started from Finder gets PATH=/usr/bin:/bin

# CLIs a Makefile / pyproject / lock file calls -> (label, brew formula or "", fallback command shown)
CLI_HINTS: dict[str, tuple[str, str, str]] = {
    "uv": ("uv", "uv", ""), "poetry": ("Poetry", "poetry", ""), "pipenv": ("Pipenv", "pipenv", ""),
    "yarn": ("Yarn", "yarn", ""), "pnpm": ("pnpm", "pnpm", ""), "make": ("make", "", "xcode-select --install"),
    "cargo": ("Rust (cargo)", "", ""), "go": ("Go", "", ""), "docker": ("Docker", "", ""), "git": ("git", "", ""),
}
_MAKE_CMD = re.compile(r"^\t\s*[@-]?\s*(?:\$\(\w+\)\s*)?([A-Za-z][\w.-]*)")
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)(\[[A-Za-z0-9_,\-\s]+\])?\s*(.*)$")
_PY_FLOOR = re.compile(r"(?:>=|~=|==|\^|~)\s*v?(\d+(?:\.\d+)?)")
_NODE_FLOOR = re.compile(r"v?(\d+(?:\.\d+){0,2})")

# The Python import name of common packages whose distribution name differs (the rest: name, dashes -> underscores).
CONDA_SKIP = {"python", "pip", "setuptools", "wheel", "conda", "libgcc", "ca-certificates", "openssl"}


class ScanError(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind  # SetupScanError: no_project | unreadable | too_big


# --------------------------------------------------------------------------- where the project is

def home_short(p: str | Path | None) -> str:
    if not p:
        return ""
    s, home = str(p), str(Path.home())
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


def _has_manifest(d: Path) -> bool:
    try:
        return any((d / m).is_file() for m in MANIFESTS) or any(EXTRA_REQUIREMENTS.match(p.name) for p in d.iterdir()
                                                                if p.is_file())
    except OSError:
        return False


def _unsafe_root(d: Path) -> bool:
    """Never a project: /, the home folder itself, or a folder above it (setup.fix would npm install there)."""
    home = Path.home().resolve()
    r = d.resolve()
    return r == Path("/") or r == home or r in home.parents


def find_root(path: str | Path) -> Path:
    """The project folder for `path` (a folder, or a file in it): the nearest folder at or above it that holds a
    manifest, up to UP_LEVELS up, never above the home folder; else the folder itself. Raises ScanError."""
    p = Path(str(path)).expanduser()
    if not p.exists():
        raise ScanError("unreadable")
    d = p if p.is_dir() else p.parent
    if not os.access(d, os.R_OK):
        raise ScanError("unreadable")
    cur = d.resolve()
    for _ in range(UP_LEVELS + 1):
        if _unsafe_root(cur):
            break
        if _has_manifest(cur):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    if _unsafe_root(d):
        raise ScanError("no_project")
    return d.resolve()


EDITOR_BUNDLES = {"com.microsoft.VSCode", "com.microsoft.VSCodeInsiders", "com.vscodium", "com.visualstudio.code.oss"}
TERMINAL_BUNDLES = {"com.apple.Terminal", "com.googlecode.iterm2", "dev.warp.Warp-Stable", "com.mitchellh.ghostty"}


def _frontmost() -> tuple[str, str, int] | None:
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return None
    a = NSWorkspace.sharedWorkspace().frontmostApplication()
    if a is None:
        return None
    return str(a.bundleIdentifier() or ""), str(a.localizedName() or ""), int(a.processIdentifier())


def _pids_of(bundles: set[str]) -> list[int]:
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return []
    return [int(a.processIdentifier()) for a in NSWorkspace.sharedWorkspace().runningApplications()
            if str(a.bundleIdentifier() or "") in bundles]


SHELLS = {"zsh", "bash", "fish", "sh", "-zsh", "-bash", "-fish", "-sh", "nu", "tcsh"}


def terminal_cwd(pid: int, run: Runner | None = None) -> str | None:
    """The working folder of the newest shell under a terminal app's process (Terminal: login -> -zsh). `ps` + `lsof`,
    read-only. None when there's no shell or it can't be read."""
    run = run or _setup._run
    code, out = run(["ps", "-A", "-o", "pid=,ppid=,comm="])
    if code != 0:
        return None
    kids: dict[int, list[tuple[int, str]]] = {}
    for ln in out.splitlines():
        parts = ln.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            kids.setdefault(int(parts[1]), []).append((int(parts[0]), Path(parts[2].strip()).name))
    shells, todo, seen = [], [pid], set()
    while todo:
        cur = todo.pop()
        if cur in seen or len(seen) > 400:
            continue
        seen.add(cur)
        for child, name in kids.get(cur, []):
            if name in SHELLS:
                shells.append(child)
            todo.append(child)
    for sh in sorted(shells, reverse=True):  # the newest shell first (the front tab, most of the time)
        code, out = run(["lsof", "-a", "-d", "cwd", "-p", str(sh), "-Fn"])
        if code == 0:
            for ln in out.splitlines():
                if ln.startswith("n/"):
                    return ln[1:]
    return None


def open_folder(*, front: Callable[[], tuple[str, str, int] | None] | None = None,
                editor: Callable[[], dict | None] | None = None,
                terminal: Callable[[int], str | None] | None = None,
                terminals: Callable[[], list[int]] | None = None) -> str | None:
    """The folder of the frontmost editor or terminal: VS Code's workspace (active_editor: AXDocument, else its window
    title) or the terminal's shell folder. Miyagi's own window is usually in front when the learner asks, so with
    another app in front it falls back to VS Code's front window, then the newest terminal shell. None: no project."""
    from . import active

    front = front or _frontmost
    editor = editor or (lambda: active.active_editor())
    terminal = terminal or terminal_cwd
    terminals = terminals or (lambda: _pids_of(TERMINAL_BUNDLES))
    f = front()
    if f and f[0] in TERMINAL_BUNDLES and (cwd := terminal(f[2])):
        return cwd
    ed = editor()
    if ed and (ed.get("folder") or ed.get("path")):
        return ed.get("folder") or str(Path(ed["path"]).parent)
    for pid in terminals():
        if cwd := terminal(pid):
            return cwd
    return None


# --------------------------------------------------------------------------- reading the project's files

def _read(root: Path, name: str) -> str | None:
    p = root / name
    try:
        if not p.is_file():
            return None
        if p.stat().st_size > MAX_FILE_BYTES:
            raise ScanError("too_big")
        return p.read_text(encoding="utf-8", errors="replace")
    except ScanError:
        raise
    except OSError:
        raise ScanError("unreadable") from None


def _line_of(text: str, name: str) -> int | None:
    rx = re.compile(r"(^|[\s\"'\[,{])" + re.escape(name) + r"($|[\s\"'\]=<>~!;\[:,@])", re.IGNORECASE)
    for i, ln in enumerate(text.splitlines(), 1):
        if rx.search(ln):
            return i
    return None


def _pkg(name: str, spec: str, frm: str, *, optional: bool = False, why: str = "") -> dict:
    floor = _PY_FLOOR.search(spec or "")
    minimum = floor.group(1) if floor and ">=" in spec else ""
    return {"tool": name.lower(), "label": name, "kind": "python_package",
            "pip_name": name + (f">={minimum}" if minimum else ""), "min_version": minimum, "from": frm,
            "why": why or f"{frm.split(':')[0]} lists it", "needed": not optional, "_spec": spec}


def parse_requirements(text: str, fname: str = "requirements.txt", *, optional: bool = False) -> list[dict]:
    out = []
    for i, raw in enumerate(text.splitlines(), 1):
        ln = raw.split(" #")[0].strip()
        if not ln or ln.startswith(("#", "-", "git+", "http:", "https:", "file:", ".", "/")):
            continue  # options (-r, -e, --index-url), URLs and local paths: never followed
        ln = ln.split(";")[0].strip()  # environment markers
        if "@" in ln and "://" in ln:
            continue  # name @ https://...
        m = _REQ_NAME.match(ln)
        if m:
            out.append(_pkg(m.group(1), m.group(3) or "", f"{fname}:{i}", optional=optional))
    return out


def _dep_name(spec: str) -> tuple[str, str] | None:
    m = _REQ_NAME.match(spec.split(";")[0])
    return (m.group(1), m.group(3) or "") if m else None


def parse_pyproject(text: str) -> tuple[list[dict], str, set[str]]:
    """-> (package rows, the Python floor, CLIs the file says it is built with: poetry / uv / pipenv)."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise ScanError("unreadable") from None
    rows, floor, clis = [], "", set()
    proj = data.get("project") or {}
    for spec in proj.get("dependencies") or []:
        if isinstance(spec, str) and (nm := _dep_name(spec)):
            rows.append(_pkg(nm[0], nm[1], f"pyproject.toml:{_line_of(text, nm[0]) or 1}"))
    if isinstance(proj.get("requires-python"), str) and (m := _PY_FLOOR.search(proj["requires-python"])):
        floor = m.group(1)
    tool = data.get("tool") or {}
    poetry = tool.get("poetry") or {}
    if poetry:
        clis.add("poetry")
        for name, spec in (poetry.get("dependencies") or {}).items():
            spec_s = spec if isinstance(spec, str) else (spec.get("version", "") if isinstance(spec, dict) else "")
            if name.lower() == "python":
                if m := _PY_FLOOR.search(spec_s or ""):
                    floor = floor or m.group(1)
                continue
            rows.append(_pkg(name, ">=" + m.group(1) if (m := _PY_FLOOR.search(spec_s or "")) else "",
                             f"pyproject.toml:{_line_of(text, name) or 1}"))
    if "uv" in tool:
        clis.add("uv")
    return rows, floor, clis


def parse_pipfile(text: str) -> tuple[list[dict], str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise ScanError("unreadable") from None
    rows = []
    for name, spec in (data.get("packages") or {}).items():
        spec_s = spec if isinstance(spec, str) and spec != "*" else ""
        rows.append(_pkg(name, spec_s, f"Pipfile:{_line_of(text, name) or 1}"))
    floor = str((data.get("requires") or {}).get("python_version") or "")
    return rows, floor


def parse_environment_yml(text: str, fname: str = "environment.yml") -> tuple[list[dict], str]:
    import yaml

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        raise ScanError("unreadable") from None
    rows, floor = [], ""
    for dep in (data.get("dependencies") or []) if isinstance(data, dict) else []:
        if isinstance(dep, dict):
            for spec in dep.get("pip") or []:
                if isinstance(spec, str) and (nm := _dep_name(spec)):
                    rows.append(_pkg(nm[0], nm[1], f"{fname}:{_line_of(text, nm[0]) or 1}"))
            continue
        if not isinstance(dep, str):
            continue
        name = re.split(r"[=<>! ]", dep.split("::")[-1], maxsplit=1)[0].strip()
        if name.lower() == "python":
            if m := re.search(r"(\d+\.\d+)", dep):
                floor = m.group(1)
            continue
        if name and name.lower() not in CONDA_SKIP and re.fullmatch(r"[A-Za-z0-9][\w.\-]*", name):
            rows.append(_pkg(name, "", f"{fname}:{_line_of(text, name) or 1}"))
    return rows, floor


def parse_version_file(text: str) -> str:
    """.python-version / .nvmrc / .node-version: "3.12.4", "v20.11.1", "20" -> major.minor ("20" stays "20").
    "lts/*", "system", "node" -> "" (no floor)."""
    t = (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""
    m = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.\d+)?", t)
    if not m:
        return ""
    return m.group(1) + (f".{m.group(2)}" if m.group(2) else "")


def parse_package_json(text: str) -> tuple[dict, str]:
    """-> ({name: spec} of dependencies + devDependencies, the node floor from engines.node)."""
    try:
        data = json.loads(text)
    except ValueError:
        raise ScanError("unreadable") from None
    if not isinstance(data, dict):
        return {}, ""
    deps: dict = {}
    for key in ("dependencies", "devDependencies"):
        if isinstance(data.get(key), dict):
            deps.update({k: v for k, v in data[key].items() if isinstance(k, str)})
    floor = ""
    eng = (data.get("engines") or {}).get("node") if isinstance(data.get("engines"), dict) else None
    if isinstance(eng, str) and (m := _NODE_FLOOR.search(eng)):
        floor = m.group(1)
    return deps, floor


def makefile_clis(text: str) -> list[str]:
    """The CLIs (of CLI_HINTS) a Makefile's recipes call, in order. Never runs make."""
    found: list[str] = ["make"]
    for ln in text.splitlines():
        m = _MAKE_CMD.match(ln)
        if m and m.group(1) in CLI_HINTS and m.group(1) not in found:
            found.append(m.group(1))
    return found


def read_project(root: Path) -> dict:
    """Every manifest in `root`, parsed (no subprocess, no checks): {files, packages, python_floor, python_from,
    node_floor, node_from, node_deps, clis: [(cli, from)], docker_from}. Raises ScanError (too_big / unreadable)."""
    out: dict = {"files": [], "packages": [], "python_floor": "", "python_from": "", "node_floor": "", "node_from": "",
                 "node_deps": None, "clis": [], "docker_from": ""}
    names = []
    try:
        names = sorted(p.name for p in root.iterdir() if p.is_file())
    except OSError:
        raise ScanError("unreadable") from None

    def py_floor(v: str, frm: str) -> None:
        if v and not out["python_floor"]:
            out["python_floor"], out["python_from"] = v, frm

    def cli(name: str, frm: str) -> None:
        if name not in [c for c, _ in out["clis"]]:
            out["clis"].append((name, frm))

    reqs = [n for n in names if n == "requirements.txt"] + [n for n in names if n != "requirements.txt"
                                                             and EXTRA_REQUIREMENTS.match(n)]
    for n in reqs:
        out["files"].append(n)
        out["packages"] += parse_requirements(_read(root, n) or "", n, optional=n != "requirements.txt")
    if (t := _read(root, "pyproject.toml")) is not None:
        out["files"].append("pyproject.toml")
        rows, floor, clis = parse_pyproject(t)
        out["packages"] += rows
        py_floor(floor, "pyproject.toml")
        for c in sorted(clis):
            cli(c, "pyproject.toml")
    if (t := _read(root, "Pipfile")) is not None:
        out["files"].append("Pipfile")
        rows, floor = parse_pipfile(t)
        out["packages"] += rows
        py_floor(floor, "Pipfile")
        cli("pipenv", "Pipfile")
    for n in ("environment.yml", "environment.yaml"):
        if (t := _read(root, n)) is not None:
            out["files"].append(n)
            rows, floor = parse_environment_yml(t, n)
            out["packages"] += rows
            py_floor(floor, n)
            break
    if (t := _read(root, ".python-version")) is not None:
        out["files"].append(".python-version")
        if v := parse_version_file(t):  # the pinned version wins over a range's floor
            out["python_floor"], out["python_from"] = v, ".python-version"
    if (t := _read(root, "package.json")) is not None:
        out["files"].append("package.json")
        deps, floor = parse_package_json(t)
        out["node_deps"] = deps
        if floor:
            out["node_floor"], out["node_from"] = floor, "package.json"
    for n in (".nvmrc", ".node-version"):
        if (t := _read(root, n)) is not None:
            out["files"].append(n)
            if v := parse_version_file(t):
                out["node_floor"], out["node_from"] = v, n
    if "yarn.lock" in names:
        cli("yarn", "yarn.lock")
    if "pnpm-lock.yaml" in names:
        cli("pnpm", "pnpm-lock.yaml")
    if "uv.lock" in names:
        cli("uv", "uv.lock")
    for n in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml"):
        if n in names:
            _read(root, n)  # size check only
            out["files"].append(n)
            out["docker_from"] = out["docker_from"] or n
    if (t := _read(root, "Makefile")) is not None:
        out["files"].append("Makefile")
        for c in makefile_clis(t):
            cli(c, "Makefile")
    # one row per package: requirements.txt's line wins over pyproject's; a needed listing over an optional one
    seen: dict[str, dict] = {}
    for r in out["packages"]:
        key = re.sub(r"[-_.]+", "-", r["tool"])
        if key not in seen or (r["needed"] and not seen[key]["needed"]):
            seen[key] = r
    out["packages"] = list(seen.values())
    if len(out["packages"]) > MAX_PACKAGES:
        raise ScanError("too_big")
    return out


# --------------------------------------------------------------------------- checks on this Mac

def project_python(root: Path) -> tuple[str | None, str | None]:
    """(the project's own venv python, its folder) when it has one, else (None, None)."""
    from . import paths

    for d in VENV_DIRS:
        venv = root / d
        py = paths.venv_python(venv)
        if (venv / "pyvenv.cfg").is_file() and py.exists():
            return str(py), str(venv)
    return None, None


def node_binary() -> str | None:
    if found := shutil.which("node"):
        return found
    for d in NODE_DIRS:
        if (p := Path(d) / "node").exists():
            return str(p)
    return None


def npm_binary() -> str | None:
    if found := shutil.which("npm"):
        return found
    for d in NODE_DIRS:
        if (p := Path(d) / "npm").exists():
            return str(p)
    return None


CLT_SHIMS = {"make", "git"}  # /usr/bin stubs that pop the "install the developer tools" dialog when run without them


def _clt_missing(run: Runner) -> bool:
    """No Command Line Tools: /usr/bin/make and /usr/bin/git are stubs (running one opens Apple's install dialog)."""
    import sys

    if sys.platform != "darwin":
        return False
    code, _out = run(["xcode-select", "-p"])
    return code != 0


def _py_minor_tool(floor: str) -> dict:
    """The python row's tool / binary / brew formula for a floor: the catalog's python (3.12) unless it asks newer."""
    m = re.match(r"(\d+)\.(\d+)", floor or "")
    if m and (int(m.group(1)), int(m.group(2))) > (3, 12):
        v = f"{m.group(1)}.{m.group(2)}"
        return {"tool": f"python@{v}", "binary": f"python{v}", "brew": f"python@{v}", "label": f"Python {v}"}
    return {"tool": "python", "binary": "python3", "brew": "", "label": f"Python {floor}" if floor else "Python 3"}


def node_modules_state(root: Path, deps: dict) -> tuple[int, int]:
    """(installed, total) of package.json's dependencies in root/node_modules (a package.json per package)."""
    nm = root / "node_modules"
    have = sum(1 for name in deps if (nm / name / "package.json").is_file()) if nm.is_dir() else 0
    return have, len(deps)


def _install_dict(item: dict, brew: str | None) -> dict:
    r = _setup.recipe(item, brew)
    return {"method": r["method"], "command": r.get("command") or "", "url": r.get("url") or "",
            **({"confirm": r["confirm"]} if r.get("confirm") else {}), **({"refused": r["refused"]} if r.get("refused") else {})}


def build_items(root: Path, info: dict, *, run: Runner | None = None, brew: str | None | object = ...,
                python: str | None | object = ..., node: str | None | object = ...) -> tuple[list[dict], dict]:
    """Every row for `info` (read_project), checked on this Mac. -> (items, env). Read-only."""
    run = run or _setup._run
    brew = _setup.brew_path() if brew is ... else brew
    venv_py, venv_dir = project_python(root)
    py = (venv_py or _setup.best_python()) if python is ... else python
    env: dict = {}
    items: list[dict] = []
    py_version = ""
    if py and (info["packages"] or info["python_floor"]):
        code, out = run([py, "--version"])
        py_version = _setup._version(out) if code == 0 else ""
        where = home_short(venv_dir) if venv_dir and py == venv_py else Path(py).name
        env["python"] = f"{where} (Python {py_version})" if py_version else where
        if not (venv_dir and py == venv_py):
            env["python"] += ", no project .venv yet"

    if info["python_floor"]:
        t = _py_minor_tool(info["python_floor"])
        row = {**t, "kind": "runtime", "needed": True, "min_version": info["python_floor"], "from": info["python_from"],
               "pip_name": "", "import_name": "", "brew_cask": False, "url": ""}
        row["installed"], row["version"], row["where"] = bool(py_version), py_version, py or ""
        row["ok"] = bool(py_version) and _setup.meets(py_version, info["python_floor"])
        # no project .venv yet: the newer Python may be here beside the one a new .venv would use (python3.13)
        if not row["ok"] and not (venv_py and py == venv_py) and t["binary"] != "python3" \
                and (other := shutil.which(t["binary"])) and (v := _setup._version(run([other, "--version"])[1])) \
                and _setup.meets(v, info["python_floor"]):
            row.update(installed=True, version=v, where=other, ok=True)
        have = f"; {'the .venv uses' if venv_py and py == venv_py else 'this Mac has'} {py_version}" if py_version else ""
        row["why"] = f"{info['python_from']} asks for Python {info['python_floor']}{have if not row['ok'] else ''}"
        row["install"] = _install_dict(row, brew)
        items.append(row)

    pkgs = [dict(p) for p in info["packages"]]
    if pkgs:
        _setup.check_python_packages(pkgs, py, run=run)
        for p in pkgs:
            p["install"] = _install_dict(p, brew)
            if p.get("detail") and "fails to import" in p["detail"]:
                p["why"] = f"{p['why']}; it is installed but fails to import"
        items += pkgs

    deps = info["node_deps"]
    if deps is not None or info["node_floor"]:
        nb = node_binary() if node is ... else node
        nv = ""
        if nb:
            code, out = run([nb, "--version"])
            nv = _setup._version(out) if code == 0 else ""
        if nv:
            env["node"] = f"node {nv}"
        floor = info["node_floor"]
        row = {"tool": "node", "label": f"Node.js {floor}" if floor else "Node.js", "kind": "runtime", "needed": True,
               "min_version": floor, "from": info["node_from"] or "package.json", "binary": "node", "pip_name": "",
               "import_name": "", "brew": "", "brew_cask": False, "url": "", "installed": bool(nv), "version": nv,
               "where": nb or ""}
        row["ok"] = bool(nv) and _setup.meets(nv, floor)
        if not nv:
            row["why"] = f"{row['from']} needs Node.js to run this project"
        elif not row["ok"]:
            row["why"] = f"{row['from']} asks for Node {floor}; this Mac has {nv}"
        else:
            row["why"] = f"{row['from']} runs on Node.js"
        row["install"] = _install_dict(row, brew)
        items.append(row)
        if deps:
            have, total = node_modules_state(root, deps)
            lockers = [c for c, _ in info["clis"] if c in ("yarn", "pnpm")]
            nm = {"tool": "node_modules", "label": f"Node packages ({total})", "kind": "node_package", "needed": True,
                  "min_version": "", "from": "package.json", "installed": have == total, "ok": have == total,
                  "version": "", "where": home_short(root / "node_modules")}
            if have == total:
                nm["why"] = "package.json lists them; all installed"
            elif have == 0:
                nm["why"] = "package.json lists them; none installed yet"
            else:
                nm["why"] = f"package.json lists them; {total - have} not installed yet"
            if lockers:  # the project uses another package manager: shown, the learner runs it (no npm lock churn)
                nm["install"] = {"method": "none", "command": f"{lockers[0]} install", "url": ""}
            else:
                nm["install"] = {"method": "npm", "command": "npm install", "url": ""}
            items.append(nm)

    if info["docker_from"]:
        row = {"tool": "docker", "label": "Docker Desktop", "kind": "app", "needed": True, "min_version": "",
               "from": info["docker_from"], "why": f"{info['docker_from']} builds and runs this project in a container",
               "binary": "docker", "pip_name": "", "import_name": "", "brew": "", "brew_cask": False, "url": ""}
        _setup.check(row, run=run)
        row["install"] = _install_dict(row, brew)
        items.append(row)

    for name, frm in info["clis"]:
        if name == "docker" and info["docker_from"]:
            continue
        label, formula, fallback = CLI_HINTS[name]
        cat = {"cargo": "rust", "go": "go", "docker": "docker", "git": "git"}.get(name)
        row = {"tool": cat or name, "label": label, "kind": "cli", "needed": True, "min_version": "", "from": frm,
               "why": f"{frm} runs it", "binary": name, "pip_name": "", "import_name": "", "brew": formula,
               "brew_cask": False, "url": ""}
        if cat:
            row["kind"] = _setup.CATALOG[cat]["kind"]
        if name in CLT_SHIMS and _clt_missing(run):  # /usr/bin/make without the developer tools: never run the stub
            row.update(installed=False, version="", where="", ok=False)
            fallback = "xcode-select --install"
        else:
            _setup.check(row, run=run)
        if fallback and not row["installed"]:
            row["install"] = {"method": "none", "command": fallback, "url": ""}
        else:
            row["install"] = _install_dict(row, brew)
        items.append(row)
    return items, env


# --------------------------------------------------------------------------- the report

def _contract_row(it: dict) -> dict:
    inst = it["install"]
    row = _setup._row({**it, "install": {"method": inst["method"], "command": inst.get("command") or "",
                                         "url": inst.get("url") or ""}})
    if it.get("from"):
        row["from"] = it["from"]
    if not it.get("ok") and not it.get("unknown") and inst["method"] == "npm":
        row["actions"] = ["install"]
    if inst.get("refused"):
        row["actions"] = [a for a in row["actions"] if a != "install"]
    return row


def _order(items: list[dict]) -> list[dict]:
    """Missing first (needed before optional), then the ones we couldn't check, then the ready ones."""
    def rank(it: dict) -> int:
        if it.get("unknown"):
            return 2
        if not it.get("ok"):
            return 0 if it.get("needed") else 1
        return 3
    return sorted(items, key=rank)


def next_step(items: list[dict], info: dict, venv: bool) -> str:
    """One plain sentence: what to do first. Calm, no dashes."""
    miss = [it for it in items if not it.get("ok") and not it.get("unknown") and it.get("needed")]
    if not info["files"]:
        return "No project files here yet, like requirements.txt or package.json."
    if not items:
        return "This project doesn't ask for anything to install."
    if not miss:
        unk = [it for it in items if it.get("unknown")]
        return "Some checks took too long. Check again in a moment." if unk else "Everything this project asks for is here."
    first = miss[0]
    rest = len(miss) - 1
    tail = f" Then {rest} more." if rest else ""
    pkgs = [it for it in miss if it["kind"] == "python_package"]
    if first["kind"] == "runtime" and first["tool"].startswith("python") and first.get("installed"):
        return f"Install {first['label']}, then make the project's .venv again with it.{tail}"
    if first["kind"] == "python_package" and len(pkgs) == len(miss):
        where = "into the project's .venv" if venv else "into a new .venv in this folder"
        more = len(pkgs) - 1
        also = f" and {more} more Python package{'s' if more > 1 else ''}" if more else ""
        return f"Install {first['label']}{also} {where}."
    if first["kind"] == "node_package":
        return f"Run {first['install'].get('command') or 'npm install'} in the project folder.{tail}"
    if first["install"]["method"] == "none" and first["install"].get("command"):
        return f"{first['label']} is missing. Run {first['install']['command']} in Terminal.{tail}"
    return f"Install {first['label']} first.{tail}"


def scan(path: str | Path | None = None, *, req_id: str | None = None, quick: bool = False, run: Runner | None = None,
         folder: Callable[[], str | None] | None = None, **checks) -> dict:
    """setup.report for the project at `path` (None: the folder open in the frontmost editor / terminal). Never raises:
    a problem is the report's `error`. quick: the manifests only, `scanning: true` and no items (no subprocess)."""
    base: dict = {**({"reqId": req_id} if req_id else {}), "files": [], "items": [], "ready": 0, "total": 0}
    try:
        target = path or (folder or open_folder)()
        if not target:
            return {**base, "error": "no_project"}
        root = find_root(target)
        base.update(root=home_short(root), name=root.name, _path=str(root))  # _path: the caller's, never sent
        info = read_project(root)
        base["files"] = info["files"]
        if quick:
            return {**base, "scanning": True}
        items, env = build_items(root, info, run=run, **checks)
    except ScanError as e:
        return {**base, "error": e.kind}
    except Exception:  # noqa: BLE001 - a report always goes out
        log.exception("setup.scan failed")
        return {**base, "error": "unreadable"}
    ordered = _order(items)
    miss = [it for it in ordered if not it.get("ok")]
    shown = miss[:MAX_ROWS]
    shown += [it for it in ordered if it.get("ok")][:MAX_ROWS - len(shown)]
    venv = project_python(root)[0] is not None
    out = {**base, "items": [_contract_row(it) for it in shown], "ready": sum(1 for it in items if it.get("ok")),
           "total": len(items), "next": next_step(ordered, info, venv)}
    if len(items) > len(shown):
        out["more"] = len(items) - len(shown)
    if env:
        out["env"] = env
    return out


# --------------------------------------------------------------------------- setup.fix

def find_item(root: Path, tool: str, *, run: Runner | None = None, **checks) -> dict | None:
    """The full (internal) row for `tool` in the project at root, freshly checked; None when the project doesn't ask
    for it. Rows only ever come from the project's own files, so the app can't make the engine install anything else."""
    info = read_project(root)
    items, _env = build_items(root, info, run=run, **checks)
    return next((it for it in items if it["tool"] == tool), None)


def npm_install(root: Path, *, on_line: Callable[[str], None] | None = None, timeout: float = 1800.0,
                popen=subprocess.Popen, npm: str | None | object = ...) -> dict:
    """`npm install` in the project folder (the learner pressed Install on its Node packages row)."""
    emit = on_line or (lambda _line: None)
    out = {"tool": "node_modules", "method": "npm", "ok": False}
    npm = npm_binary() if npm is ... else npm
    if not npm:
        out.update(error="Node.js isn't installed. Install it first, then press Install again.",
                   url=_setup.CATALOG["node"]["url"])
        return out
    if not (root / "package.json").is_file() or _unsafe_root(root):
        out["error"] = "no package.json in this folder"
        return out
    env = _setup._child_env(NPM_CONFIG_FUND="false", NPM_CONFIG_AUDIT="false", NPM_CONFIG_UPDATE_NOTIFIER="false")
    env["PATH"] = os.pathsep.join([str(Path(npm).parent), env.get("PATH", "")])  # npm's own node first
    emit("$ npm install")
    argv = [npm, "install", "--no-audit", "--no-fund", "--prefix", str(root)]
    code, txt = _setup._stream(argv, emit, env, timeout, popen)
    if code != 0:
        out["error"] = _setup._last_error(txt) or f"exit {code}"
        return out
    deps, _floor = parse_package_json((root / "package.json").read_text(encoding="utf-8", errors="replace"))
    have, total = node_modules_state(root, deps)
    out["ok"] = have == total
    if not out["ok"]:
        out["error"] = f"{total - have} package(s) still missing after npm install"
    return out


def fix(tool: str, root: str | Path, *, on_line: Callable[[str], None] | None = None, confirmed: str | None = None,
        install: Callable[..., dict] | None = None, npm: Callable[..., dict] | None = None, run: Runner | None = None,
        **checks) -> dict:
    """Install one row of the project's report (setup.fix). -> setup.install's result {ok, tool, method, error?, url?,
    version?, needs_confirm?, package?}. `confirmed`: the package name the learner confirmed with a second press (an
    off-list pip package, setup.install's own confirm)."""
    try:
        r = find_root(root)
    except ScanError as e:
        return {"tool": tool, "ok": False, "error": "That project folder isn't there any more." if e.kind == "unreadable"
                else "No project folder to install into."}
    if _unsafe_root(r):
        return {"tool": tool, "ok": False, "error": "No project folder to install into."}
    item = find_item(r, tool, run=run, **checks)
    if item is None:
        return {"tool": tool, "ok": False, "error": "This project doesn't ask for that any more."}
    if item.get("ok"):
        return {"tool": tool, "ok": True, "method": item["install"]["method"], "version": item.get("version") or ""}
    method = item["install"]["method"]
    if method == "npm":
        return (npm or npm_install)(r, on_line=on_line)
    if method == "none":
        cmd = item["install"].get("command")
        return {"tool": tool, "ok": False, "method": "none",
                "error": f"Run {cmd} in Terminal." if cmd else "No installer known: get it from its official site."}
    if confirmed:
        item["confirmed"] = confirmed
    venv_py, _venv = project_python(r)
    return (install or _setup.install)(item, workdir=r, on_line=on_line, python=venv_py)
