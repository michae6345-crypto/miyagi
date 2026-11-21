"""What a lesson needs on this Mac, what is missing, and (only after the learner says yes) installing it.

    reqs = requirements(graph)                 # Claude reads the step graph -> tools; checked locally, read-only
    editor_needed(reqs)                        # False for a Blender / Figma / browser-only lesson
    res = install(item, on_line=print)         # ONLY after the learner confirms; Homebrew or pip in the lesson venv

Items: {tool, label, kind, why, needed, installed, ok, version, min_version, install: {method, command, url}}
  kind: editor | app | runtime | cli | python_package | web_app (nothing to install; install.method "open" + url)
  installed: present on this Mac; ok: installed and new enough (min_version)
  install.method: brew | brew_cask | pip | download | open | none. `command` is for display only: install() rebuilds
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
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jsonschema import Draft202012Validator

from . import editor as _editor
from . import paths
from .scaffold import _extract_json, _reply_text, make_client, record_cost

log = logging.getLogger("server.workspace")

DEFAULT_MODEL = "claude-haiku-5-5"
KINDS = ["editor", "app", "runtime", "cli", "python_package", "web_app"]
_PKG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._+\-/]{0,80}$")  # brew formula/cask, pip requirement name
_PIP_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._\-]{0,80})(\[[A-Za-z0-9_,\-]+\])?")
_PIP_FLOOR = re.compile(r">=\s*([0-9][0-9.]*)")
_VER = re.compile(r"(\d+(?:\.\d+){0,3})")

# Known tools: how to find them and how to install them. Claude's ids are mapped onto these;
# anything else is checked generically (`which <bin>` / `import <module>`).
CATALOG: dict[str, dict] = {
    "cursor": {"label": "Cursor", "kind": "editor", "bundle": "com.todesktop.230313mzl4w4u92", "app": "Cursor",
               "bin": "cursor", "cask": "cursor", "url": "https://cursor.com/downloads"},
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
    # Web apps: nothing to install; the card links to them ("Open in browser").
    "openai-platform": {"label": "OpenAI Platform", "kind": "web_app", "url": "https://platform.openai.com"},
    "chatgpt": {"label": "ChatGPT", "kind": "web_app", "url": "https://chatgpt.com"},
    "botpress": {"label": "Botpress", "kind": "web_app", "url": "https://app.botpress.cloud"},
    "zapier": {"label": "Zapier", "kind": "web_app", "url": "https://zapier.com/app/home"},
    "google-sheets": {"label": "Google Sheets", "kind": "web_app", "url": "https://sheets.google.com"},
    "jupyter": {"label": "Jupyter", "kind": "python_package", "module": "jupyter", "pip": "jupyter", "url": "https://jupyter.org/install"},
}
ALIASES = {
    "visual-studio-code": "vscode", "visual studio code": "vscode", "code": "vscode", "vs code": "vscode",
    "python3": "python", "cpython": "python", "nodejs": "node", "node.js": "node", "cargo": "rust", "rustc": "rust",
    "openai": "openai-platform", "openai agent builder": "openai-platform", "agent builder": "openai-platform",
    "openai platform": "openai-platform", "botpress studio": "botpress", "zapier agents": "zapier",
    "sheets": "google-sheets", "google sheets": "google-sheets",
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
                    "url": {"type": "string", "description": "web_app: the app's https URL; otherwise the official download page"},
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
Go only by the video's steps above (what the learner typed when searching is not part of the lesson).
- editor: needed=true only if the steps have the learner write code or text files (a code editor such as
  VS Code). needed=false for no-code lessons (Botpress, Zapier, OpenAI's web tools, Figma, Blender, Unity,
  spreadsheets, a DAW), for conceptual videos, and for terminal-only lessons; say so in "why".
- web apps the steps use in the browser (OpenAI Platform, ChatGPT, Botpress, Zapier, Google Sheets, ...):
  kind "web_app" with their https URL; nothing to install.
- tools: runtimes (python, node, rust, go, java), CLIs (git, docker, ffmpeg, ...), desktop apps (blender,
  figma, docker), and the Python packages the steps import (torch, pandas, numpy, ...). Use lesson.libraries
  for versions. Do not list the editor here, npm packages the project's package.json installs, or
  the macOS terminal. Each tool appears once. At most 15.
- min_version only when the tutorial clearly needs it (e.g. python 3.10 for match statements).
- brew: the real Homebrew formula/cask name (brew_cask=true for GUI apps), "" if you are not sure.
"""


# --------------------------------------------------------------------------- local checks (read-only)

Runner = Callable[[list[str]], tuple[int, str]]


TIMEOUT = 124  # _run's exit code for "timed out" (the output so far is returned)
PY_CHECK_TIMEOUT = float(os.environ.get("MIYAGI_PY_CHECK_TIMEOUT", "45"))  # cold torch/matplotlib imports: 5-20 s


def _run(argv: list[str], timeout: float = 8.0) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as e:
        partial = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return TIMEOUT, partial
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# One interpreter imports every package in turn (no parallel cold imports), printing a line per package as
# it goes, so a timeout still keeps the packages already checked. A module that exists but fails to
# import for another reason is installed-but-broken, not missing (reinstalling wouldn't help).
_PY_PROBE = """
import importlib, importlib.metadata as md, json, sys
for i, (cands, dist) in enumerate(json.loads(sys.argv[1])):
    r = {"i": i, "ok": False}
    for m in cands:
        try:
            mod = importlib.import_module(m)
        except ModuleNotFoundError:
            continue
        except Exception as e:
            r = {"i": i, "ok": True, "mod": m, "ver": "", "broken": type(e).__name__ + ": " + str(e)[:120]}
            break
        r = {"i": i, "ok": True, "mod": m, "ver": str(getattr(mod, "__version__", "") or "")}
        break
    if r["ok"] and not r.get("ver") and dist:
        try:
            r["ver"] = md.version(dist)
        except Exception:
            pass
    print(json.dumps(r), flush=True)
"""
# pip name -> import names, for the common mismatches (the import name Claude gives is tried first).
IMPORT_ALIASES = {
    "pydoe": ["pyDOE", "pydoe"], "pydoe2": ["pyDOE2", "pydoe2"], "scikit-learn": ["sklearn"], "pillow": ["PIL"],
    "opencv-python": ["cv2"], "opencv-python-headless": ["cv2"], "beautifulsoup4": ["bs4"], "pyyaml": ["yaml"],
    "python-dotenv": ["dotenv"], "scikit-image": ["skimage"], "pytorch": ["torch"], "tensorflow-cpu": ["tensorflow"],
}
_MOD = re.compile(r"[A-Za-z_][\w.]*")
# import name -> pip name (lesson.libraries sometimes holds the import name)
PIP_FOR_IMPORT = {"sklearn": "scikit-learn", "cv2": "opencv-python", "pil": "pillow", "bs4": "beautifulsoup4",
                  "yaml": "pyyaml", "skimage": "scikit-image", "dotenv": "python-dotenv"}


def import_candidates(item: dict) -> list[str]:
    """Import names to try: Claude's import_name, its lowercase, known aliases of the pip name, the pip name
    as a module (dashes -> underscores) and its lowercase. pyDOE's current release installs `pydoe`."""
    cat = CATALOG.get(item.get("tool", ""), {})
    pip = re.split(r"[\[<>=!~ ;]", (item.get("pip_name") or cat.get("pip") or item.get("tool") or "").strip())[0]
    base = [item.get("import_name") or "", cat.get("module") or ""]
    base += IMPORT_ALIASES.get(pip.lower(), []) + IMPORT_ALIASES.get((item.get("tool") or "").lower(), [])
    base += [pip.replace("-", "_"), (item.get("tool") or "").replace("-", "_")]
    out: list[str] = []
    for m in base:
        for v in (m, m.lower()):
            if v and _MOD.fullmatch(v) and v not in out:
                out.append(v)
    return out[:8]


def check_python_packages(items: list[dict], py: str | None, *, run: Runner = _run, timeout: float | None = None) -> None:
    """Fill installed / version / ok on python_package items with ONE interpreter run. A package the probe
    didn't reach before the timeout is unknown (installed=None, ok=None, unknown=True), never "missing"."""
    if not items:
        return
    if not py:
        for it in items:
            it.update(installed=False, version="", where="", ok=False)
        return
    payload = [[import_candidates(it), re.split(r"[\[<>=!~ ;]", it.get("pip_name") or it.get("tool") or "")[0]] for it in items]
    # The engine's own Python (no lesson .venv yet): -I -S, the stdlib only, which is what a new .venv starts with.
    # Otherwise the engine's bundled Pillow / PyObjC counted as the lesson's and Install never made the .venv.
    argv = [py, *(["-I", "-S"] if is_bundled(py) else []), "-c", _PY_PROBE, json.dumps(payload)]
    code, out = run(argv, timeout=timeout or PY_CHECK_TIMEOUT) if run is _run else run(argv)
    seen: dict[int, dict] = {}
    for line in (out or "").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and isinstance(r.get("i"), int):
            seen[r["i"]] = r
    for i, it in enumerate(items):
        r = seen.get(i)
        if r is None:  # probe timed out / crashed before this one: we don't know
            it.update(installed=None, version="", where=py, ok=None, unknown=True,
                      detail="timed out checking (cold import); try again" if code == TIMEOUT else "couldn't check")
            continue
        version = _version(r.get("ver") or "")
        it.update(installed=bool(r["ok"]), version=version, where=py, import_name=r.get("mod") or it.get("import_name", ""),
                  ok=bool(r["ok"]) and meets(version, it.get("min_version", "")))
        it.pop("unknown", None)
        if r.get("broken"):
            it["detail"] = "installed but fails to import: " + r["broken"]


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


# The lesson .venv's Python: 3.12 first (every common ML wheel exists for it), then the nearest versions. The newest
# isn't the best pick: on a brand-new 3.14 the wheels for TensorFlow and friends often don't exist yet.
PYTHON_PREFERENCE = (12, 13, 11, 10, 14, 9)


def _xcode_stub(path: str | None) -> bool:
    """Apple's /usr/bin/python3 on a Mac without the Command Line Tools: running it pops the "install the developer
    tools" dialog instead of starting Python. A read-only setup check must never trigger that."""
    if sys.platform != "darwin" or not path:
        return False
    try:
        if Path(path).resolve() != Path("/usr/bin/python3"):
            return False
        r = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True, timeout=5)
        return r.returncode != 0
    except (OSError, subprocess.SubprocessError):
        return False


def bundled_python() -> str | None:
    """The Python inside miyagi.app (MIYAGI_BUNDLED_PYTHON, set by the app's localEngine.ts when it starts the engine
    with it), else the interpreter this engine runs on. A fresh Mac has no other Python 3 (no Homebrew, and
    /usr/bin/python3 is the Command Line Tools stub), and an app launched from Finder gets PATH=/usr/bin:/bin, so this
    is what a lesson .venv is built from there. The bundle keeps venv + ensurepip (pip comes from its wheel, offline)."""
    for p in (os.environ.get("MIYAGI_BUNDLED_PYTHON", "").strip(), getattr(sys, "_base_executable", "") or sys.executable):
        if p and Path(p).is_file() and os.access(p, os.X_OK) and sys.version_info >= (3, 9):
            return p
    return None


def is_bundled(py: str | None) -> bool:
    """Is `py` exactly what bundled_python() picked (best_python's fallback, not a python3.x found on PATH)? Its
    site-packages hold the ENGINE's libraries (Pillow, PyObjC, anthropic...), which a lesson .venv made from it doesn't
    have: a package check against it must not count them. Same string only: on a dev Mac PATH's python3.12 and the
    engine's base interpreter resolve to one file, and that case keeps today's check."""
    return bool(py) and py == bundled_python()


def best_python() -> str | None:
    """The python3.x to build a lesson .venv with: python3.12 / 3.13 / 3.11 / 3.10 on PATH, else the Python inside
    miyagi.app (bundled_python: a fresh Mac's only Python 3), then 3.14 / 3.9 and plain python3. Never Apple's Xcode
    stub (no Command Line Tools)."""
    later = []
    for minor in PYTHON_PREFERENCE:
        if minor in (14, 9):  # a newer / older one than the bundled 3.12: the bundle first (TensorFlow-class wheels)
            later.append(minor)
            continue
        if (p := shutil.which(f"python3.{minor}")) and not _xcode_stub(p):
            return p
    if p := bundled_python():
        return p
    for minor in later:
        if (p := shutil.which(f"python3.{minor}")) and not _xcode_stub(p):
            return p
    p = shutil.which("python3")
    return None if _xcode_stub(p) else p


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
    if kind == "web_app":  # nothing to install or check locally
        item.update(installed=True, version="", where=cat.get("url") or _https(item.get("url", "")), ok=True)
        return item
    if kind == "python_package":
        check_python_packages([item], check_python(workdir), run=run)
        return item
    else:
        if cat.get("bundle") or kind in ("app", "editor"):
            app = find_app(cat.get("bundle", ""), cat.get("app", item.get("label", "")), run)
            if app:
                installed, where, version = True, app, _app_version(app, run)
        binary = item.get("binary") or cat.get("bin") or ""
        b = None
        if binary == "python3":  # our own pick, an absolute path (the bundled one may sit under a folder with spaces)
            b = best_python()
        elif binary and re.fullmatch(r"[\w.+\-/]+", binary):
            b = shutil.which(binary)
        if b and not installed:
            code, out = run([b, "--version"])
            if code == 0 or binary != "python3":  # our python pick must run: one that can't print its version isn't there
                installed, where = True, b
                version = _version(out) if code == 0 else ""
    item.update(installed=installed, version=version, where=where, ok=installed and meets(version, item.get("min_version", "")))
    return item


# --------------------------------------------------------------------------- install recipes

def recipe(item: dict, brew: str | None) -> dict:
    """{method, package, command, url}: Homebrew when it exists, pip for Python packages, else the download page."""
    cat = CATALOG.get(item["tool"], {})
    url = cat.get("url") or _https(item.get("url", ""))
    if item["kind"] == "web_app":
        return {"method": "open", "package": "", "command": "", "url": url}
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


def check_python(workdir: Path | str | None) -> str | None:
    """The Python whose packages the setup check reads: the lesson folder's .venv when it has one, else best_python()
    (the one Install builds that .venv from). The setup card and the preflight card both check through requirements(),
    so they agree (desktop test 10)."""
    return venv_python(workdir) or best_python()


# --------------------------------------------------------------------------- requirements()

def _lesson_json(graph: dict) -> str:
    keep = ("index", "title", "instructions", "targets", "checks", "precision_checks")
    slim = {
        "lesson": {k: v for k, v in (graph.get("lesson") or {}).items() if k in ("title", "libraries")},
        "sources": [{k: s.get(k) for k in ("kind", "title", "url")} for s in graph.get("sources") or []],
        "steps": [{k: s[k] for k in keep if k in s} for s in graph.get("steps") or []],
    }
    return json.dumps(slim, indent=1)[:50_000]


def cache_key(graph: dict) -> str:
    """Keyed by the VIDEO when there is one: the prompt never sees the learner's goal, so the tool list
    depends only on the video. S8's preflight (lesson id "preflight-<videoId>", one step per chapter)
    therefore warms the cache that the real lesson's setup card reads. Else the lesson id / first URL."""
    for src in graph.get("sources") or []:
        if vid := (src.get("videoId") or paths.video_id(src.get("url", ""))):
            return f"video-{vid}"
    meta = paths.lesson_meta(graph)
    if (m := re.fullmatch(r"preflight-([\w-]{6,})", meta.get("id") or "")) and m.group(1) != "url":
        return f"video-{m.group(1)}"
    basis = meta.get("id") or paths.primary_url(graph) or json.dumps(graph, sort_keys=True)[:4000]
    return "lesson-" + hashlib.sha1(basis.encode()).hexdigest()[:12]


def _cache_file(graph: dict) -> Path:
    key = re.sub(r"[^A-Za-z0-9_-]", "_", cache_key(graph))
    return paths.lessons_root() / ".miyagi-state" / "requirements" / f"{key}.json"


def _ask_claude(graph: dict, client) -> dict:
    model = os.environ.get("WORKSPACE_REQ_MODEL", DEFAULT_MODEL)
    msgs = [{"role": "user", "content": PROMPT.format(lesson_json=_lesson_json(graph))}]
    kw = dict(model=model, max_tokens=4000, system=SYSTEM, messages=msgs)  # noqa: C408
    try:
        msg = client.messages.create(**kw, output_config={"format": {"type": "json_schema", "schema": REQ_SCHEMA}})
        record_cost(msg, model, "workspace requirements")
    except Exception as e:
        if "schema" not in str(e).lower() and "output_config" not in str(e).lower():
            raise
        msgs = [{"role": "user", "content": msgs[0]["content"] + "\n\nReply with ONE JSON object matching:\n" + json.dumps(REQ_SCHEMA)}]
        msg = client.messages.create(**{**kw, "messages": msgs})
        record_cost(msg, model, "workspace requirements")
    obj = _extract_json(_reply_text(msg))
    errs = [e.message for e in Draft202012Validator(REQ_SCHEMA).iter_errors(obj)]
    if errs:
        raise ValueError("requirements JSON invalid: " + "; ".join(errs[:5]))
    return obj


def _lower_first(t: str) -> str:
    first = t.split(" ", 1)[0]
    common = {"All", "The", "This", "These", "Everything", "Every", "Each", "Work", "Steps", "It", "You", "No", "Only", "Nothing"}
    return t[:1].lower() + t[1:] if first in common else t  # keep proper nouns: "Blender is ..."


def _https(url: str) -> str:
    url = (url or "").strip()
    return url if re.fullmatch(r"https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/[^\s\"'<>]*)?", url) else ""


def _canonical(tool: str) -> str:
    t = re.sub(r"[\s_-]+", " ", (tool or "").strip().lower())  # "openai-agent-builder" == "OpenAI Agent Builder"
    return ALIASES.get(t, t.replace(" ", "-"))


_JUPYTER_FAMILY = {"jupyter", "notebook", "jupyterlab", "ipykernel", "jupyter-notebook", "jupyter-lab"}
IPYKERNEL = {"tool": "ipykernel", "kind": "python_package", "why": "Runs the notebook's cells in VS Code.", "needed": True,
             "min_version": "", "binary": "", "import_name": "ipykernel", "pip_name": "ipykernel", "brew": "",
             "brew_cask": False, "url": "https://pypi.org/project/ipykernel/"}


def _lib_names(graph: dict) -> list[str]:
    libs = (graph.get("lesson") or {}).get("libraries")
    names = list(libs) if isinstance(libs, (dict, list)) else []
    return [str(n).strip() for n in names if isinstance(n, str) and n.strip()]


def notebook_lesson(graph: dict) -> bool:
    """A lesson whose code runs in a notebook (an .ipynb step file, or Jupyter in its libraries / steps): VS Code runs
    the cells with the lesson .venv's ipykernel, so the setup card must install it."""
    if {n.lower() for n in _lib_names(graph)} & _JUPYTER_FAMILY:
        return True
    for st in graph.get("steps") or []:
        if not isinstance(st, dict):
            continue
        if str(st.get("file") or "").lower().endswith(".ipynb"):
            return True
        for x in (st.get("targets") or []) + (st.get("checks") or []) + (st.get("precision_checks") or []):
            if isinstance(x, dict) and str(x.get("file") or "").lower().endswith(".ipynb"):
                return True
        if re.search(r"\bjupyter\b|\.ipynb\b", f"{st.get('title', '')} {st.get('instructions', '')}", re.IGNORECASE):
            return True
    return False


def _colab_lesson(graph: dict) -> bool:
    """A notebook lesson done in Google Colab (a browser): the orchestrator's is_colab_lesson, same fields."""
    les = graph.get("lesson") or {}
    blob = " ".join([str(les.get(k) or "") for k in ("title", "goal")]
                    + [str(s.get("url") or "") for s in graph.get("sources") or [] if isinstance(s, dict)]
                    + [f"{st.get('title', '')} {st.get('instructions', '')}" for st in graph.get("steps") or []
                       if isinstance(st, dict)]).lower()
    return "colab" in blob


def _python_lesson(graph: dict) -> bool:
    if notebook_lesson(graph) or {n.lower() for n in _lib_names(graph)} & {"python", "python3"}:
        return True
    for st in graph.get("steps") or []:
        if not isinstance(st, dict):
            continue
        files = [st.get("file")] + [x.get("file") for x in (st.get("targets") or []) + (st.get("checks") or [])
                                    if isinstance(x, dict)]
        if any(str(f or "").lower().endswith(".py") for f in files):
            return True
        if re.search(r"\b(python3?|pip3?)\s", str(st.get("run_command") or "")):
            return True
    return False


def local_requirements(graph: dict) -> dict:
    """What a lesson needs without asking Claude (offline, no key, the API down): the editor when it has code, Python,
    and lesson.libraries as Python packages (a Python lesson only: a React lesson's libraries are npm's). Notebook
    lessons get ipykernel in place of the jupyter family. Same shape as Claude's answer; never cached, so the next
    online check asks Claude as usual."""
    py = _python_lesson(graph)
    nb = notebook_lesson(graph)
    tool = {"needed": True, "min_version": "", "binary": "", "import_name": "", "pip_name": "", "brew": "",
            "brew_cask": False, "url": ""}
    tools: list[dict] = []
    if py:
        tools.append({**tool, "tool": "python", "kind": "runtime", "why": "Runs the lesson's code.", "binary": "python3"})
        for name in _lib_names(graph):
            low = name.lower()
            if low in ("python", "python3") or (nb and low in _JUPYTER_FAMILY):
                continue
            canon = _canonical(low)
            if canon in CATALOG and CATALOG[canon].get("kind") != "python_package":
                continue  # git, node, docker, VS Code...: not a pip package
            pip = PIP_FOR_IMPORT.get(low, name)  # sklearn -> scikit-learn, cv2 -> opencv-python, PIL -> pillow
            if not pip_requirement(pip):
                continue
            tools.append({**tool, "tool": pip.lower(), "kind": "python_package", "why": "The lesson imports it.",
                          "pip_name": pip, "import_name": name if pip.lower() != low else
                          (IMPORT_ALIASES.get(low) or [""])[0]})
    return {"editor": {"needed": py or nb, "why": "You write and run the code in VS Code." if py or nb
                       else "this lesson doesn't edit code files."}, "tools": tools[:16]}


def _items(raw: dict, graph: dict | None = None) -> list[dict]:
    ed = raw.get("editor") or {}
    items = [{
        "tool": (eid := _editor.editor_id()), "label": CATALOG[eid]["label"], "kind": "editor", "needed": bool(ed.get("needed")),
        "why": (ed.get("why") or "") if ed.get("needed") else "No editor needed: " + _lower_first(ed.get("why") or "this lesson doesn't edit code files."),
        "min_version": "",
    }]
    seen = {"vscode", "cursor"}  # the editor is item 0 only (VS Code; MIYAGI_EDITOR overrides)
    for t in (raw.get("tools") or [])[:20]:
        tool = _canonical(t.get("tool", ""))
        if not tool or tool in seen or not re.fullmatch(r"[a-z0-9][a-z0-9._+@\-]{0,40}", tool):
            continue
        seen.add(tool)
        cat = CATALOG.get(tool, {})
        kind = cat.get("kind") or (t.get("kind") if t.get("kind") in KINDS else "cli")
        if kind == "web_app" and not (cat.get("url") or _https(t.get("url", ""))):
            continue  # a web app we can't link to is no use on the card
        if kind == "editor":
            continue
        items.append({
            "tool": tool, "label": cat.get("label") or t.get("tool") or tool, "kind": kind,
            "why": t.get("why", ""), "needed": bool(t.get("needed", True)), "min_version": t.get("min_version", ""),
            "binary": t.get("binary", ""), "import_name": t.get("import_name", ""), "pip_name": t.get("pip_name", ""),
            "brew": t.get("brew", ""), "brew_cask": bool(t.get("brew_cask")), "url": t.get("url", ""),
        })
    colab = graph is not None and _colab_lesson(graph)
    if graph is not None and ed.get("needed") and not colab and notebook_lesson(graph) and not seen & _JUPYTER_FAMILY:
        # VS Code runs a notebook's cells with the lesson .venv's ipykernel; Claude's list often leaves it out
        items.append({**IPYKERNEL, "label": "Jupyter kernel (ipykernel)"})
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
            log.warning("requirements: no Anthropic key: the lesson's own list (lesson.libraries)")
            raw = local_requirements(lesson)
        else:
            try:
                raw = _ask_claude(lesson, client)
            except Exception as e:  # noqa: BLE001 - offline / API down: the lesson's own list, not an empty card
                log.warning("requirements: Claude failed (%s): the lesson's own list (lesson.libraries)", str(e)[:300])
                raw = local_requirements(lesson)
            else:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(raw, indent=1))
        if not raw.get("tools") and not (raw.get("editor") or {}).get("needed"):
            return []  # nothing known: no card (as before)
    items = _items(raw, lesson)
    brew = brew_path()
    pys = [it for it in items if it["kind"] == "python_package"]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(check, it, workdir=workdir, run=run) for it in items if it["kind"] != "python_package"]
        if pys:  # one interpreter, packages imported one after another (cold imports in parallel time out)
            futs.append(ex.submit(check_python_packages, pys, check_python(workdir), run=run))
        for f in futs:
            f.result()
    for it in items:
        it["install"] = {k: v for k, v in recipe(it, brew).items() if k != "package"}
    return items


def editor_needed(items: list[dict]) -> bool:
    return any(it["kind"] == "editor" and it["needed"] for it in items)


def missing(items: list[dict]) -> list[dict]:
    """Needed items that aren't installed or are too old (items we couldn't check are not "missing")."""
    return [it for it in items if it["needed"] and not it.get("ok") and not it.get("unknown")]


def unknown(items: list[dict]) -> list[dict]:
    """Items whose check didn't finish (e.g. a cold torch import past the timeout)."""
    return [it for it in items if it.get("unknown")]


# --------------------------------------------------------------------------- install()

# The engine's own Python setup (the app strips most of these; a launcher or a shell may not): never handed to the
# lesson's .venv, its pip, or brew.
_ENGINE_PY_ENV = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__",
                  "CONDA_PREFIX", "PYTHONNOUSERSITE")
OFFLINE = "No internet connection. Connect to Wi-Fi, then press Install again."
NO_PYTHON = "no python3 on this Mac"
NOT_INSTALLED_APP = "Drag miyagi into your Applications folder and open it from there, then press Install again."
_NET_ERR = re.compile(r"NewConnectionError|Name or service not known|nodename nor servname|Temporary failure in name "
                      r"resolution|Network is unreachable|Failed to establish a new connection|ConnectTimeout|"
                      r"Read timed out|Could not resolve host|No matching distribution found", re.IGNORECASE)


_PROXY_ENV = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")
_PIP_CONF = ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_CONFIG_FILE")
_BREW_MIRROR = ("HOMEBREW_BOTTLE_DOMAIN", "HOMEBREW_API_DOMAIN", "HOMEBREW_ARTIFACT_DOMAIN")


def _pip_conf_files() -> list[Path]:
    home = Path.home()
    return [home / ".config" / "pip" / "pip.conf", home / ".pip" / "pip.conf",
            home / "Library" / "Application Support" / "pip" / "pip.conf", Path("/Library/Application Support/pip/pip.conf"),
            Path("/etc/pip.conf")]


def _host_of(r: dict) -> str | None:
    """The host an install downloads from, when it's certain: pypi.org for pip, ghcr.io for Homebrew's bottles. None
    (no pre-check: the install itself decides, and a failure is read for network errors) behind a proxy, with a custom
    pip index (env or pip.conf) or a Homebrew mirror, where a direct probe of the default host would say "offline" on
    a Mac that is online."""
    if any(os.environ.get(k) for k in _PROXY_ENV):
        return None
    if r.get("method") == "pip":
        if any(os.environ.get(k) for k in _PIP_CONF) or any(p.is_file() for p in _pip_conf_files()):
            return None
        return "pypi.org"
    if any(os.environ.get(k) for k in _BREW_MIRROR):
        return None
    return "ghcr.io"


def online(host: str | None = "pypi.org", timeout: float = 4.0) -> bool:
    """Can this Mac reach `host` on 443 right now? A few seconds at most, so an Install with the Wi-Fi off says so at
    once instead of pip retrying for minutes (and a calm "connect to Wi-Fi" instead of a pip traceback). None: no
    certain host to probe, so True (the install decides)."""
    import socket

    if not host:
        return True
    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_venv(workdir: Path | str, *, emit: Callable[[str], None] | None = None, env: dict | None = None,
                timeout: float = 600.0, popen=subprocess.Popen) -> tuple[str | None, str]:
    """<workdir>/.venv's python, made with best_python() when there's none yet (the Python inside miyagi.app on a Mac
    with no other Python 3; no network: venv + ensurepip's bundled pip). A .venv whose python is a dangling link
    (miyagi.app moved, or the Python it was made from was removed) is moved aside to the lessons root's
    .miyagi-state/old-venvs/ (never emptied: `venv --clear` on a symlinked .venv empties its target) and made again.
    One build per folder at a time (_venv_lock): the setup card's Install and the open's ensure_lesson_venv may both
    ask at once, and a half-built .venv (python there, pip not yet) must never be used or moved aside.
    -> (python, "") or (None, why)."""
    with _venv_lock(workdir):
        return _ensure_venv(workdir, emit or (lambda _line: None), env, timeout, popen)


_venv_locks: dict[str, threading.Lock] = {}
_venv_locks_guard = threading.Lock()


def _venv_lock(workdir: Path | str) -> threading.Lock:
    key = str(Path(workdir).expanduser().resolve())
    with _venv_locks_guard:
        return _venv_locks.setdefault(key, threading.Lock())


def _aside_dir(venv: Path) -> Path:
    """Where a broken .venv goes: <lessons root>/.miyagi-state/old-venvs/ (outside the lesson folder, so the file
    watcher and VS Code's interpreter list never see it), else beside it."""
    try:
        d = paths.lessons_root().expanduser() / ".miyagi-state" / "old-venvs"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{venv.parent.name}-{time.strftime('%Y%m%d-%H%M%S')}"
    except OSError:
        return venv.with_name(f".venv.old-{time.strftime('%Y%m%d-%H%M%S')}")


def _ensure_venv(workdir, emit, env, timeout, popen) -> tuple[str | None, str]:
    if py := venv_python(workdir):
        return py, ""
    base = best_python()
    if base is None:
        return None, NO_PYTHON
    if is_bundled(base) and ("/AppTranslocation/" in base or base.startswith("/Volumes/")):
        # miyagi runs from the disk image (or macOS moved it aside): a .venv linked to this path breaks next launch
        return None, NOT_INSTALLED_APP
    venv = Path(workdir) / ".venv"
    if venv.exists() or venv.is_symlink():  # a broken .venv (dangling python link): set aside, never emptied
        aside = _aside_dir(venv)
        try:
            try:
                venv.rename(aside)
            except OSError:  # another volume: beside it instead
                aside = venv.with_name(f".venv.old-{time.strftime('%Y%m%d-%H%M%S')}")
                venv.rename(aside)
            emit(f"(the old .venv no longer runs: moved to {aside})")
        except OSError as e:
            return None, f"could not move the broken .venv aside: {e}"
    env = dict(env if env is not None else os.environ)
    for k in _ENGINE_PY_ENV:
        env.pop(k, None)
    argv = [base, "-m", "venv", str(venv)]
    emit(f"$ {Path(base).name} -m venv .venv")
    code, txt = _stream(argv, emit, env, timeout, popen)
    if code != 0:
        return None, f"could not create .venv: {txt[-300:]}"
    py = venv_python(workdir)
    return (py, "") if py else (None, "could not create .venv: no python in it")


def install(item: dict, *, workdir: Path | str | None = None, on_line: Callable[[str], None] | None = None,
            timeout: float = 1800.0, popen=subprocess.Popen, net: Callable[[str], bool] | None = None) -> dict:
    """Install one requirements() item. Call ONLY after the learner confirmed it.

    brew / brew cask (HOMEBREW_NO_AUTO_UPDATE), or pip into `<workdir>/.venv` (created with the newest
    python3 if missing). Streams output lines to on_line. Without Homebrew, returns the download URL and
    installs nothing (never installs Homebrew itself). Returns {ok, tool, method, error?, url?, version?}.
    """
    emit = on_line or (lambda _line: None)
    brew = brew_path()
    r = recipe(item, brew)
    out = {"tool": item["tool"], "method": r["method"], "ok": False}
    if r["method"] == "open":
        out.update(error="a web app: nothing to install, open it in the browser", url=r["url"])
        return out
    if r["method"] in ("download", "none"):
        out.update(error="Homebrew isn't installed; download it from the official page" if r["url"] else "no installer known",
                   url=r["url"])
        return out
    env = {**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ENV_HINTS": "1", "NONINTERACTIVE": "1"}
    for k in _ENGINE_PY_ENV:  # the engine's own Python setup never reaches the lesson's .venv / pip
        env.pop(k, None)
    reachable = net or (online if popen is subprocess.Popen else (lambda _host: True))  # tests inject popen: no network
    if not reachable(_host_of(r)):
        out.update(error=OFFLINE, offline=True)
        return out
    if r["method"] == "pip":
        if not workdir:
            out["error"] = "pip installs go into the lesson's .venv: no lesson folder given"
            return out
        py, err = ensure_venv(workdir, emit=emit, env=env, timeout=timeout, popen=popen)
        if py is None:
            out.update(error=err, **({"url": CATALOG["python"]["url"]} if err == NO_PYTHON else {}))
            return out
        argv = [py, "-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off",
                "--retries", "2", "--timeout", "30", r["package"]]
    elif r["method"] == "brew_cask":
        argv = [brew, "install", "--cask", r["package"]]
    else:
        argv = [brew, "install", r["package"]]
    emit("$ " + r["command"])
    code, txt = _stream(argv, emit, env, timeout, popen)
    if code != 0:
        if _NET_ERR.search(txt) and not reachable(_host_of(r)):  # the Wi-Fi dropped during the download
            out.update(error=OFFLINE, offline=True)
            return out
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

def setup_card(items: list[dict], *, step_id: str | None = None, resources: list[dict] | None = None) -> dict:
    """The proposed `card {kind: "setup"}` payload for the app (see README: contract proposal)."""
    miss = missing(items)
    need_ed = editor_needed(items)
    ed = next((it for it in items if it["kind"] == "editor"), None)
    web = [it for it in items if it["kind"] == "web_app"]
    if miss:
        body = "Missing: " + ", ".join(it["label"] for it in miss) + ". Install now?"
    elif web and not need_ed:
        body = "Nothing to install."
    elif unknown(items):
        body = "Nothing missing so far."
    else:
        body = "You have everything this lesson needs."
    if unk := unknown(items):
        body += " Still checking " + ", ".join(it["label"] for it in unk) + " (first import is slow)."
    if web:
        body += " In your browser: " + ", ".join(it["label"] for it in web) + "."
    if not need_ed and ed:
        body += " " + ed["why"]
    elif need_ed and ed and ed.get("installed"):
        body += f" Open the lesson folder in {ed['label']}?"
    if resources:  # find_resources(): the video links its own code/notebooks/data
        body += f" The video links its materials ({', '.join(r['name'] for r in resources[:3])}{'…' if len(resources) > 3 else ''}): download them?"
    actions = ((["open_editor"] if need_ed and ed and ed.get("installed") else []) + (["open_in_browser"] if web else [])
               + (["download"] if resources else []) + (["install"] if miss else []) + ["skip_setup"])
    card = {
        "kind": "setup", "title": "Set up first" if miss else "Ready to go", "body": body,
        "actions": actions,
        "setup": {
            "editorNeeded": need_ed,
            "editor": ed["tool"] if ed else None,          # "cursor" | "vscode"
            "editorLabel": ed["label"] if ed else None,    # "Visual Studio Code": the open_editor button reads "Open Visual Studio Code"
            "resources": [{"name": r["name"], "url": r["url"], "kind": r["kind"]} for r in resources or []],
            "actionLabels": {"open_editor": f"Open {ed['label']}" if ed else "Open editor", "open_in_browser": "Open in browser",
                             "download": "Download tutorial files",
                             "install": "Install", "skip_setup": "Skip"},
            "items": [{
                "tool": it["tool"], "label": it["label"], "kind": it["kind"], "why": it["why"], "needed": it["needed"],
                "installed": it.get("installed", False), "ok": it.get("ok", False), "unknown": bool(it.get("unknown")), "version": it.get("version") or None,
                "minVersion": it.get("min_version") or None,
                "install": {"method": it["install"]["method"], "command": it["install"]["command"] or None, "url": it["install"]["url"] or None},
            } for it in items],
        },
    }
    if step_id:
        card["stepId"] = step_id
    return card


# --------------------------------------------------------------------------- VS Code not found

def editor_item(*, run: Runner = _run) -> dict:
    """The setup row for the lesson's editor (VS Code), checked on this Mac, with its install recipe: Homebrew's cask
    when there's Homebrew, else its download page."""
    eid = _editor.editor_id()
    it = {"tool": eid, "label": CATALOG[eid]["label"], "kind": "editor", "needed": True, "min_version": "",
          "why": "miyagi opens your lesson in it."}
    check(it, run=run)
    it["install"] = {k: v for k, v in recipe(it, brew_path()).items() if k != "package"}
    return it


def editor_missing_card(*, run: Runner = _run) -> tuple[dict, dict] | None:
    """(card, item) when the lesson needs VS Code and this Mac has none, else None. The card is a plain setup card
    whose only missing row is the editor, so the v2 app draws it as its VS Code sheet ("VS Code not found", Get VS
    Code). Read-only (Spotlight lookup, a few seconds at most): run it in a thread."""
    if _editor.preferred_editor() is not None:
        return None
    it = editor_item(run=run)
    if it.get("installed"):  # found by Spotlight somewhere preferred_editor didn't look: not "not found"
        return None
    card = setup_card([it])
    card.update(title="VS Code not found", body="miyagi needs VS Code to teach this. Install it, and the lesson opens in it.",
                actions=[a for a in card["actions"] if a in ("install", "skip_setup")])
    return card, it
