"""What a lesson needs on this Mac, what is missing, and (only after the learner says yes) installing it.

    reqs = requirements(graph)                 # Claude reads the step graph -> tools; checked locally, read-only
    editor_needed(reqs)                        # False for a Blender / Figma / browser-only lesson
    res = install(item, on_line=print)         # ONLY after the learner confirms; Homebrew or pip in the lesson venv

Items: {tool, label, kind, why, needed, installed, ok, version, min_version, install: {method, command, url}}
  kind: editor | app | runtime | cli | python_package
  installed: present on this Mac; ok: installed and new enough (min_version)
  install.method: brew | brew_cask | pip | download | none. `command` is for display only: install() rebuilds
  the argv from method + a validated package name and never runs a string from Claude or the app.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jsonschema import Draft202012Validator

from . import paths
from .scaffold import _extract_json, _reply_text, make_client

log = logging.getLogger("server.workspace")

DEFAULT_MODEL = "claude-haiku-5-5"
KINDS = ["editor", "app", "runtime", "cli", "python_package"]
_PKG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._+\-/]{0,80}$")  # brew formula/cask, pip requirement name
_PIP_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._\-]{0,80})(\[[A-Za-z0-9_,\-]+\])?")
_PIP_FLOOR = re.compile(r">=\s*([0-9][0-9.]*)")
_VER = re.compile(r"(\d+(?:\.\d+){0,3})")

# Known tools: how to find them and how to install them. Claude's ids are mapped onto these;
# anything else is checked generically (`which <bin>` / `import <module>`).
CATALOG: dict[str, dict] = {
    "vscode": {"label": "Visual Studio Code", "kind": "editor", "bundle": "com.microsoft.VSCode", "app": "Visual Studio Code",
               "bin": "code", "cask": "visual-studio-code", "url": "https://code.visualstudio.com/download"},
    "python": {"label": "Python 3", "kind": "runtime", "bin": "python3", "formula": "python@3.12", "url": "https://www.python.org/downloads/macos/"},
    "node": {"label": "Node.js", "kind": "runtime", "bin": "node", "formula": "node", "url": "https://nodejs.org/en/download"},
    "npm": {"label": "npm", "kind": "cli", "bin": "npm", "formula": "node", "url": "https://nodejs.org/en/download"},
    "git": {"label": "git", "kind": "cli", "bin": "git", "formula": "git", "url": "https://git-scm.com/download/mac"},
    "rust": {"label": "Rust (cargo)", "kind": "runtime", "bin": "cargo", "formula": "rust", "url": "https://rustup.rs"},
    "go": {"label": "Go", "kind": "runtime", "bin": "go", "formula": "go", "url": "https://go.dev/dl/"},
    "java": {"label": "Java (JDK)", "kind": "runtime", "bin": "javac", "formula": "openjdk", "url": "https://adoptium.net"},
    "docker": {"label": "Docker Desktop", "kind": "app", "bundle": "com.docker.docker", "app": "Docker", "bin": "docker",
               "cask": "docker-desktop", "url": "https://www.docker.com/products/docker-desktop/"},
    "blender": {"label": "Blender", "kind": "app", "bundle": "org.blenderfoundation.blender", "app": "Blender",
                "cask": "blender", "url": "https://www.blender.org/download/"},
    "figma": {"label": "Figma", "kind": "app", "bundle": "com.figma.Desktop", "app": "Figma", "cask": "figma",
              "url": "https://www.figma.com/downloads/"},
    "unity": {"label": "Unity Hub", "kind": "app", "bundle": "com.unity3d.unityhub", "app": "Unity Hub", "cask": "unity-hub",
              "url": "https://unity.com/download"},
    "jupyter": {"label": "Jupyter", "kind": "python_package", "module": "jupyter", "pip": "jupyter", "url": "https://jupyter.org/install"},
}
ALIASES = {
    "visual-studio-code": "vscode", "visual studio code": "vscode", "code": "vscode", "vs code": "vscode",
    "python3": "python", "cpython": "python", "nodejs": "node", "node.js": "node", "cargo": "rust", "rustc": "rust",
    "golang": "go", "jdk": "java", "openjdk": "java", "docker desktop": "docker", "unity hub": "unity",
}

REQ_SCHEMA = {
    "type": "object",
    "properties": {
        "editor": {
            "type": "object",
            "properties": {
                "needed": {"type": "boolean", "description": "does the learner write code/text files in a code editor?"},
                "why": {"type": "string", "description": "one short sentence"},
            },
            "required": ["needed", "why"],
            "additionalProperties": False,
        },
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "description": "short id: python, node, git, rust, docker, blender, torch, pandas, ..."},
                    "kind": {"type": "string", "enum": KINDS[1:]},
                    "why": {"type": "string", "description": "which step needs it, <= 12 words"},
                    "needed": {"type": "boolean", "description": "false = optional / nice to have"},
                    "min_version": {"type": "string", "description": "e.g. 3.10 or 18, \"\" if any"},
                    "binary": {"type": "string", "description": "cli/runtime: executable to look for on PATH, else \"\""},
                    "import_name": {"type": "string", "description": "python_package: module to import (sklearn), else \"\""},
                    "pip_name": {"type": "string", "description": "python_package: bare pip package name (scikit-learn), else \"\""},
                    "brew": {"type": "string", "description": "Homebrew formula or cask name if one exists, else \"\""},
                    "brew_cask": {"type": "boolean"},
                    "url": {"type": "string", "description": "official download/install page"},
                },
                "required": ["tool", "kind", "why", "needed", "min_version", "binary", "import_name", "pip_name", "brew", "brew_cask", "url"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["editor", "tools"],
    "additionalProperties": False,
}

SYSTEM = """You read a tutorial's step graph and list what software the learner must have on their Mac to
follow it. You only list; nothing is installed without the learner's say-so."""

PROMPT = """Lesson (step graph built from the tutorial, JSON):
{lesson_json}

List what this lesson needs on a Mac.
- editor: needed=true only if the learner writes code or text files (a code editor such as VS Code).
  needed=false when the work happens in another app (Blender, Figma, Unity, Excel, a DAW), in a web
  page/online tool, or only in a terminal; say so in "why".
- tools: runtimes (python, node, rust, go, java), CLIs (git, docker, ffmpeg, ...), desktop apps (blender,
  figma, docker), and the Python packages the steps import (torch, pandas, numpy, ...). Use lesson.libraries
  for versions. Do not list the editor here, npm packages the project's package.json installs, or
  the macOS terminal. Each tool appears once. At most 15.
- min_version only when the tutorial clearly needs it (e.g. python 3.10 for match statements).
- brew: the real Homebrew formula/cask name (brew_cask=true for GUI apps), "" if you are not sure.
"""


# --------------------------------------------------------------------------- local checks (read-only)

Runner = Callable[[list[str]], tuple[int, str]]


def _run(argv: list[str], timeout: float = 8.0) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _version(text: str) -> str:
    m = _VER.search(text or "")
    return m.group(1) if m else ""


def _vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def meets(version: str, minimum: str) -> bool:
    if not minimum or not version:
        return True
    return _vtuple(version) >= _vtuple(minimum)


def brew_path() -> str | None:
    found = shutil.which("brew")
    if found:
        return found
    for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if Path(p).exists():
            return p
    return None


def best_python() -> str | None:
    """The newest python3.x on PATH (Apple's /usr/bin/python3 is often 3.9)."""
    for minor in range(14, 8, -1):
        if p := shutil.which(f"python3.{minor}"):
            return p
    return shutil.which("python3")


def find_app(bundle_id: str, name: str, run: Runner = _run) -> str | None:
    for base in ("/Applications", str(Path.home() / "Applications")):
        p = Path(base) / f"{name}.app"
        if name and p.exists():
            return str(p)
    if bundle_id and sys.platform == "darwin":
        code, out = run(["mdfind", f"kMDItemCFBundleIdentifier == '{bundle_id}'"])
        if code == 0 and (first := next((ln for ln in out.splitlines() if ln.endswith(".app")), None)):
            return first
    return None


def _app_version(app_path: str, run: Runner) -> str:
    code, out = run(["defaults", "read", str(Path(app_path) / "Contents" / "Info"), "CFBundleShortVersionString"])
    return _version(out) if code == 0 else ""


def check(item: dict, *, workdir: Path | str | None = None, run: Runner = _run) -> dict:
    """Fill installed / version / ok on an item. Read-only, a few seconds at most."""
    kind, cat = item["kind"], CATALOG.get(item["tool"], {})
    installed, version, where = False, "", ""
    if kind == "python_package":
        py = venv_python(workdir) or best_python()
        mod = item.get("import_name") or cat.get("module") or item["tool"]
        if py and re.fullmatch(r"[A-Za-z_][\w.]*", mod):
            code, out = run([py, "-c", f"import {mod} as m; print(getattr(m, '__version__', ''))"])
            installed = code == 0
            version = _version(out.strip().splitlines()[-1]) if installed and out.strip() else ""
            where = py
    else:
        if cat.get("bundle") or kind in ("app", "editor"):
            app = find_app(cat.get("bundle", ""), cat.get("app", item.get("label", "")), run)
            if app:
                installed, where, version = True, app, _app_version(app, run)
        binary = item.get("binary") or cat.get("bin") or ""
        if binary == "python3":
            binary = best_python() or ""
        b = shutil.which(binary) if binary and re.fullmatch(r"[\w.+\-/]+", binary) else None
        if b and not installed:
            installed, where = True, b
            code, out = run([b, "--version"])
            version = _version(out) if code == 0 else ""
    item.update(installed=installed, version=version, where=where, ok=installed and meets(version, item.get("min_version", "")))
    return item


# --------------------------------------------------------------------------- install recipes

def recipe(item: dict, brew: str | None) -> dict:
    """{method, package, command, url}: Homebrew when it exists, pip for Python packages, else the download page."""
    cat = CATALOG.get(item["tool"], {})
    url = cat.get("url") or item.get("url") or ""
    if item["kind"] == "python_package":
        pkg = pip_requirement(item.get("pip_name") or cat.get("pip") or item["tool"])
        if pkg:
            return {"method": "pip", "package": pkg, "command": f"pip install {pkg}  (in the lesson's .venv)", "url": url}
    cask = cat.get("cask") or (item.get("brew") if item.get("brew_cask") else "")
    formula = cat.get("formula") or (item.get("brew") if not item.get("brew_cask") else "")
    if brew and cask and _PKG.match(cask):
        return {"method": "brew_cask", "package": cask, "command": f"brew install --cask {cask}", "url": url}
    if brew and formula and _PKG.match(formula):
        return {"method": "brew", "package": formula, "command": f"brew install {formula}", "url": url}
    return {"method": "download" if url else "none", "package": "", "command": "", "url": url}


def pip_requirement(spec: str) -> str:
    """`name[extras]` plus a `>=` floor if given. Upper bounds and exact pins are dropped: a tutorial's
    old pin (pandas<2, torch==1.8) usually has no wheels for a current Python. "" if not a valid name."""
    spec = (spec or "").strip()
    m = _PIP_NAME.match(spec)
    if not m or not re.fullmatch(r"[A-Za-z0-9._\-\[\],<>=!~*+ ]*", spec):
        return ""
    floor = _PIP_FLOOR.search(spec[m.end():])
    return m.group(0) + (f">={floor.group(1)}" if floor else "")


def venv_python(workdir: Path | str | None) -> str | None:
    if not workdir:
        return None
    p = Path(workdir) / ".venv" / "bin" / "python"
    return str(p) if p.exists() else None


# --------------------------------------------------------------------------- requirements()

def _lesson_json(graph: dict) -> str:
    keep = ("index", "title", "instructions", "targets", "checks", "precision_checks")
    slim = {
        "lesson": {k: v for k, v in (graph.get("lesson") or {}).items() if k in ("title", "goal", "libraries")},
        "sources": [{k: s.get(k) for k in ("kind", "title", "url")} for s in graph.get("sources") or []],
        "steps": [{k: s[k] for k in keep if k in s} for s in graph.get("steps") or []],
    }
    return json.dumps(slim, indent=1)[:50_000]


def _cache_file(graph: dict) -> Path:
    meta = paths.lesson_meta(graph)
    key = hashlib.sha1((meta.get("id") or paths.primary_url(graph) or json.dumps(graph, sort_keys=True)[:4000]).encode()).hexdigest()[:12]
    return paths.lessons_root() / ".miyagi-state" / "requirements" / f"{key}.json"


def _ask_claude(graph: dict, client) -> dict:
    model = os.environ.get("WORKSPACE_REQ_MODEL", DEFAULT_MODEL)
    msgs = [{"role": "user", "content": PROMPT.format(lesson_json=_lesson_json(graph))}]
    kw = dict(model=model, max_tokens=4000, system=SYSTEM, messages=msgs)  # noqa: C408
    try:
        msg = client.messages.create(**kw, output_config={"format": {"type": "json_schema", "schema": REQ_SCHEMA}})
    except Exception as e:  # noqa: BLE001 - structured output unsupported -> schema in the prompt
        if "schema" not in str(e).lower() and "output_config" not in str(e).lower():
            raise
        msgs = [{"role": "user", "content": msgs[0]["content"] + "\n\nReply with ONE JSON object matching:\n" + json.dumps(REQ_SCHEMA)}]
        msg = client.messages.create(**{**kw, "messages": msgs})
    obj = _extract_json(_reply_text(msg))
    errs = [e.message for e in Draft202012Validator(REQ_SCHEMA).iter_errors(obj)]
    if errs:
        raise ValueError("requirements JSON invalid: " + "; ".join(errs[:5]))
    return obj


def _lower_first(t: str) -> str:
    return t if t[:2].isupper() else t[:1].lower() + t[1:]


def _canonical(tool: str) -> str:
    t = re.sub(r"\s+", " ", (tool or "").strip().lower())
    return ALIASES.get(t, t.replace(" ", "-"))


def _items(raw: dict) -> list[dict]:
    ed = raw.get("editor") or {}
    items = [{
        "tool": "vscode", "label": CATALOG["vscode"]["label"], "kind": "editor", "needed": bool(ed.get("needed")),
        "why": (ed.get("why") or "") if ed.get("needed") else "No editor needed: " + _lower_first(ed.get("why") or "this lesson doesn't edit code files."),
        "min_version": "",
    }]
    seen = {"vscode"}
    for t in (raw.get("tools") or [])[:15]:
        tool = _canonical(t.get("tool", ""))
        if not tool or tool in seen or not re.fullmatch(r"[a-z0-9][a-z0-9._+@\-]{0,40}", tool):
            continue
        seen.add(tool)
        cat = CATALOG.get(tool, {})
        kind = cat.get("kind") or (t.get("kind") if t.get("kind") in KINDS else "cli")
        if kind == "editor":
            continue
        items.append({
            "tool": tool, "label": cat.get("label") or t.get("tool") or tool, "kind": kind,
            "why": t.get("why", ""), "needed": bool(t.get("needed", True)), "min_version": t.get("min_version", ""),
            "binary": t.get("binary", ""), "import_name": t.get("import_name", ""), "pip_name": t.get("pip_name", ""),
            "brew": t.get("brew", ""), "brew_cask": bool(t.get("brew_cask")), "url": t.get("url", ""),
        })
    return items


def requirements(lesson: dict, *, workdir: Path | str | None = None, client=None, run: Runner = _run,
                 use_cache: bool = True) -> list[dict]:
    """The lesson's tools, each checked on this Mac (read-only). Never installs anything.

    Claude's list is cached per lesson (`<lessons root>/.miyagi-state/requirements/`); the local
    checks run every call. On no key / API failure: [] (nothing to show; the lesson still runs)."""
    cache = _cache_file(lesson)
    raw = None
    if use_cache and cache.exists():
        try:
            raw = json.loads(cache.read_text())
        except ValueError:
            raw = None
    if raw is None:
        client = client if client is not None else make_client()
        if client is None:
            log.warning("requirements: no Anthropic key")
            return []
        try:
            raw = _ask_claude(lesson, client)
        except Exception as e:  # noqa: BLE001
            log.warning("requirements: Claude failed: %s", str(e)[:300])
            return []
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(raw, indent=1))
    items = _items(raw)
    brew = brew_path()
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda it: check(it, workdir=workdir, run=run), items))
    for it in items:
        it["install"] = {k: v for k, v in recipe(it, brew).items() if k != "package"}
    return items


def editor_needed(items: list[dict]) -> bool:
    return any(it["kind"] == "editor" and it["needed"] for it in items)


def missing(items: list[dict]) -> list[dict]:
    """Needed items that aren't installed or are too old."""
    return [it for it in items if it["needed"] and not it.get("ok")]


# --------------------------------------------------------------------------- install()

def install(item: dict, *, workdir: Path | str | None = None, on_line: Callable[[str], None] | None = None,
            timeout: float = 1800.0, popen=subprocess.Popen) -> dict:
    """Install one requirements() item. Call ONLY after the learner confirmed it.

    brew / brew cask (HOMEBREW_NO_AUTO_UPDATE), or pip into `<workdir>/.venv` (created with the newest
    python3 if missing). Streams output lines to on_line. Without Homebrew, returns the download URL and
    installs nothing (never installs Homebrew itself). Returns {ok, tool, method, error?, url?, version?}.
    """
    emit = on_line or (lambda _line: None)
    brew = brew_path()
    r = recipe(item, brew)
    out = {"tool": item["tool"], "method": r["method"], "ok": False}
    if r["method"] in ("download", "none"):
        out.update(error="Homebrew isn't installed; download it from the official page" if r["url"] else "no installer known",
                   url=r["url"])
        return out
    env = {**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ENV_HINTS": "1", "NONINTERACTIVE": "1"}
    if r["method"] == "pip":
        if not workdir:
            out["error"] = "pip installs go into the lesson's .venv: no lesson folder given"
            return out
        py = venv_python(workdir)
        if py is None:
            base = best_python()
            if base is None:
                out.update(error="no python3 on this Mac", url=CATALOG["python"]["url"])
                return out
            emit(f"$ {Path(base).name} -m venv .venv")
            code, txt = _stream([base, "-m", "venv", str(Path(workdir) / ".venv")], emit, env, timeout, popen)
            if code != 0:
                out["error"] = f"could not create .venv: {txt[-300:]}"
                return out
            py = venv_python(workdir)
        argv = [py, "-m", "pip", "install", "--disable-pip-version-check", r["package"]]
    elif r["method"] == "brew_cask":
        argv = [brew, "install", "--cask", r["package"]]
    else:
        argv = [brew, "install", r["package"]]
    emit("$ " + r["command"])
    code, txt = _stream(argv, emit, env, timeout, popen)
    if code != 0:
        out.update(error=_last_error(txt) or f"exit {code}", url=r["url"])
        return out
    after = check(dict(item), workdir=workdir)
    out.update(ok=bool(after["installed"]), version=after.get("version", ""))
    if not after["installed"]:
        out["error"] = "installer finished but the tool still isn't found (open a new terminal / check PATH)"
    return out


def _stream(argv: list[str], emit, env: dict, timeout: float, popen) -> tuple[int, str]:
    tail: list[str] = []
    try:
        p = popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, env=env, bufsize=1)
    except OSError as e:
        return 127, str(e)
    try:
        for line in p.stdout:
            line = line.rstrip()
            if line:
                emit(line)
                tail = (tail + [line])[-40:]
        code = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        return 124, "\n".join(tail + ["timed out"])
    return code, "\n".join(tail)


def _last_error(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    errs = [ln for ln in lines if re.search(r"error|fail|denied|not found|sudo|password", ln, re.IGNORECASE)]
    return (errs[-1] if errs else (lines[-1] if lines else ""))[:300]


# --------------------------------------------------------------------------- card payload (proposal)

def setup_card(items: list[dict], *, step_id: str | None = None) -> dict:
    """The proposed `card {kind: "setup"}` payload for the app (see README: contract proposal)."""
    miss = missing(items)
    need_ed = editor_needed(items)
    ed = next((it for it in items if it["kind"] == "editor"), None)
    if miss:
        body = "Missing: " + ", ".join(it["label"] for it in miss) + ". Install now?"
    else:
        body = "You have everything this lesson needs."
    if not need_ed and ed:
        body += " " + ed["why"]
    actions = (["open_editor"] if need_ed and ed and ed.get("installed") else []) + (["install"] if miss else []) + ["skip_setup"]
    card = {
        "kind": "setup", "title": "Before you start" if miss else "Ready to go", "body": body,
        "actions": actions,
        "setup": {
            "editorNeeded": need_ed,
            "items": [{
                "tool": it["tool"], "label": it["label"], "kind": it["kind"], "why": it["why"], "needed": it["needed"],
                "installed": it.get("installed", False), "ok": it.get("ok", False), "version": it.get("version") or None,
                "minVersion": it.get("min_version") or None,
                "install": {"method": it["install"]["method"], "command": it["install"]["command"] or None, "url": it["install"]["url"] or None},
            } for it in items],
        },
    }
    if step_id:
        card["stepId"] = step_id
    return card
