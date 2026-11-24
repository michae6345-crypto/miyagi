"""Code that is the same program written another way, and imports that no longer resolve.

A lesson's code pattern is written against the video's form. Equivalent forms failed it:

* Python: ``from operations import add as plus`` + ``plus(2, 3)``; ``import operations`` + ``operations.add(2, 3)``;
  ``from m import a, b`` for ``from m import a``;
* JS / TS: ``import { formatDate, formatPrice } from '../utils'`` for ``import { formatPrice } ...``; a default import
  under another local name (``import SiteHeader from './Header.jsx'`` + ``<SiteHeader/>``); ``import * as u`` +
  ``u.f()``; ``<Fragment>`` / ``<React.Fragment>`` for ``<>``.

``equivalent_view`` writes the code once more in the canonical form (aliases resolved, one name per import line,
module-qualified calls unqualified, fragments as ``<>``), so a check reads either.

And a file can look finished while what it imports is gone (``from operations import add`` after ``add`` was renamed
by hand; ``import Header from './Header.jsx'`` when Header.jsx has no default export): ``broken_imports`` resolves a
lesson file's imports of the lesson's own modules and says which don't exist.

Pure: reads files in the lesson folder, never runs them.
"""
from __future__ import annotations

import ast
import os
import re
import time
from pathlib import Path

_PY = (".py", ".pyw")
_JS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte")
CODE_EXT = _PY + _JS
_SKIP_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__", "dist", "build", ".next", ".ipynb_checkpoints",
              ".miyagi-previous", "tutorial"}
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 300


def kind_of(filename: str | None) -> str | None:
    low = str(filename or "").strip().lower()
    if low.endswith(_PY):
        return "py"
    if low.endswith(_JS):
        return "js"
    return None


# ---------------------------------------------------------------- equivalent forms

_PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+(?:\(([^()]*)\)|([^()\n#]+))", re.M)


def _from_names(m: re.Match[str]) -> list[tuple[str, str]]:
    """The (name, local name) pairs of a ``from m import ...`` match, a parenthesised list over lines included."""
    return _names(re.sub(r"#[^\n]*", "", m.group(2) if m.group(2) is not None else m.group(3)))
_PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w.]+)(?:[ \t]+as[ \t]+(\w+))?[ \t]*$", re.M)
_JS_IMPORT = re.compile(r"^[ \t]*import\s+(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\}|\*\s*as\s+(\w+))?\s*from\s*"
                        r"(['\"`])([^'\"`\n]+)\4", re.M)
_FRAGMENT_OPEN = re.compile(r"<\s*(?:React\s*\.\s*)?Fragment\s*>")
_FRAGMENT_CLOSE = re.compile(r"<\s*/\s*(?:React\s*\.\s*)?Fragment\s*>")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def _rename(text: str, old: str, new: str) -> str:
    """``old`` -> ``new`` as a whole identifier, never an attribute (``x.old``) or part of a longer name."""
    return re.sub(rf"(?<![\w.$]){re.escape(old)}(?![\w$])", new, text)


def _names(spec: str) -> list[tuple[str, str]]:
    """``"a, b as c"`` -> ``[("a", "a"), ("b", "c")]`` (imported name, local name)."""
    out = []
    for part in spec.split(","):
        ws = part.replace("type ", "").split()
        if not ws:
            continue
        if len(ws) >= 3 and ws[1] == "as":
            out.append((ws[0], ws[2]))
        elif _IDENT.fullmatch(ws[0]):
            out.append((ws[0], ws[0]))
    return out


def _py_view(text: str) -> str:
    extra: list[str] = []
    body = text
    for m in _PY_FROM.finditer(text):
        mod = m.group(1)
        for name, local in _from_names(m):
            if name == "*":
                continue
            extra.append(f"from {mod} import {name}")
            if local != name:
                body = _rename(body, local, name)
    for m in _PY_IMPORT.finditer(text):
        mod, local = m.group(1), m.group(2) or m.group(1)
        for f in sorted(set(re.findall(rf"(?<![\w.]){re.escape(local)}\.(\w+)", text))):
            extra.append(f"from {mod} import {f}")
        body = re.sub(rf"(?<![\w.]){re.escape(local)}\.(?=\w)", "", body)
    return body + ("\n" + "\n".join(extra) if extra else "")


def _stem(path: str) -> str:
    p = Path(path)
    stem = p.name.split(".")[0]
    return p.parent.name if stem == "index" and p.parent.name else stem


def _js_view(text: str) -> str:
    extra: list[str] = []
    body = text
    for m in _JS_IMPORT.finditer(text):
        default, named, star, q, path = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        if default and default != "type":
            canon = _stem(path)
            if path.startswith(".") and _IDENT.fullmatch(canon) and canon != default:
                extra.append(f"import {canon} from {q}{path}{q}")
                body = _rename(body, default, canon)
        if named:
            for name, local in _names(named):
                extra.append(f"import {{ {name} }} from {q}{path}{q}")
                if local != name:
                    body = _rename(body, local, name)
        if star:
            for f in sorted(set(re.findall(rf"(?<![\w.$]){re.escape(star)}\.(\w+)", text))):
                extra.append(f"import {{ {f} }} from {q}{path}{q}")
            body = re.sub(rf"(?<![\w.$]){re.escape(star)}\.(?=\w)", "", body)
    body = _FRAGMENT_CLOSE.sub("</>", _FRAGMENT_OPEN.sub("<>", body))
    return body + ("\n" + "\n".join(extra) if extra else "")


def equivalent_view(text: str, filename: str | None) -> str | None:
    """``text`` written in the canonical form (see the module doc), or None when that is ``text`` itself or the
    language is not Python / JS / TS. Line structure is kept; the canonical import lines are appended."""
    kind = kind_of(filename)
    if kind is None or not text:
        return None
    view = _py_view(text) if kind == "py" else _js_view(text)
    return view if view != text else None


# ---------------------------------------------------------------- the lesson's files

_WALKS: dict[tuple[str, tuple[str, ...]], tuple[float, list[Path]]] = {}
WALK_TTL_S = 2.0  # checks run on every frame and save: one folder walk serves them for a moment


def lesson_files(workdir: str | os.PathLike, exts: tuple[str, ...] = CODE_EXT) -> list[Path]:
    """The lesson folder's code files (never .venv / node_modules / build output), at most MAX_FILES."""
    key, now = (os.fspath(workdir), exts), time.monotonic()
    hit = _WALKS.get(key)
    if hit and now - hit[0] < WALK_TTL_S:
        return [p for p in hit[1] if p.exists()]
    if len(_WALKS) > 64:
        _WALKS.clear()
    files = _walk(workdir, exts)
    _WALKS[key] = (now, files)
    return files


def _walk(workdir: str | os.PathLike, exts: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for root, dirs, files in os.walk(workdir):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
        for f in sorted(files):
            if f.lower().endswith(exts):
                out.append(Path(root) / f)
                if len(out) >= MAX_FILES:
                    return out
    return out


def find_file(workdir: str | os.PathLike, rel: str) -> Path | None:
    """The lesson file ``rel`` names: ``workdir/rel``, else the one file whose path ends with ``/rel`` (a lesson's
    ``src/App.jsx`` is ``my-react-app/src/App.jsx`` in the folder; the shortest path wins)."""
    rel = str(rel or "").strip().replace("\\", "/").lstrip("./")
    if not rel or os.path.isabs(rel) or ".." in rel.split("/"):
        return None
    root = Path(workdir)
    direct = root / rel
    if direct.is_file():
        return direct
    hits = [p for p in lesson_files(root, (Path(rel).suffix.lower(),) if Path(rel).suffix else CODE_EXT)
            if p.as_posix().endswith("/" + rel)]
    return min(hits, key=lambda p: len(p.as_posix())) if hits else None


def read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# ---------------------------------------------------------------- imports that don't resolve

def _py_defines(text: str) -> set[str] | None:
    """Top-level names a Python module defines (None: can't tell, e.g. a module-level __getattr__ or `import *`)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        names = set(re.findall(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)|^(\w+)\s*[:=]", text, re.M))
        return {n for tup in names for n in tup if n}
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name == "*":
                    return None
                out.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            return None  # conditional definitions: can't tell statically
    if "__getattr__" in out:
        return None
    return out


def _py_module(importer: Path, root: Path, mod: str) -> Path | None:
    dots = len(mod) - len(mod.lstrip("."))
    parts = [p for p in mod.lstrip(".").split(".") if p]
    bases = [importer.parent] if dots else [importer.parent, root]
    if dots > 1:
        bases = [importer.parents[dots - 2]] if len(importer.parents) >= dots - 1 else []
    for base in bases:
        p = base.joinpath(*parts) if parts else base
        for cand in (p.with_suffix(".py") if parts else None, p / "__init__.py"):
            if cand is not None and cand.is_file():
                return cand
    return None


def _py_broken(path: Path, root: Path, text: str) -> list[str]:
    out = []
    for m in _PY_FROM.finditer(text):
        mod = _py_module(path, root, m.group(1))
        if mod is None or mod == path:
            continue
        src = read(mod)
        defined = _py_defines(src) if src is not None else None
        if defined is None:
            continue
        for name, _ in _from_names(m):
            if name == "*" or name in defined:
                continue
            if (mod.parent / name).is_dir() or (mod.parent / f"{name}.py").is_file():
                continue  # a submodule of a package
            out.append(f"{path.name} imports {name} from {mod.name}, which doesn't define it")
    return out


_JS_RESOLVE = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")


def _js_module(importer: Path, spec: str) -> Path | None:
    if not spec.startswith("."):
        return None
    base = (importer.parent / spec).resolve()
    for ext in _JS_RESOLVE:
        cand = Path(str(base) + ext)
        if cand.is_file():
            return cand
    for ext in _JS_RESOLVE[1:]:
        cand = base / f"index{ext}"
        if cand.is_file():
            return cand
    return None


def _js_exports(text: str) -> tuple[bool, set[str]] | None:
    """(has a default export, named exports) of a JS / TS module; None when it re-exports another module (`export *`)."""
    if re.search(r"^\s*export\s*\*", text, re.M):
        return None
    default = bool(re.search(r"^\s*export\s+default\b|\bexport\s*\{[^}]*\bas\s+default\b|module\.exports\s*=",
                             text, re.M))
    named = set(re.findall(r"^\s*export\s+(?:declare\s+)?(?:async\s+)?(?:function\*?|class|const|let|var|type|"
                           r"interface|enum|abstract\s+class)\s+([A-Za-z_$][\w$]*)", text, re.M))
    for block in re.findall(r"\bexport\s*(?:type\s*)?\{([^}]*)\}", text):
        for name, local in _names(block):
            named.add(local)
    if re.search(r"\bmodule\.exports\b|\bexports\.\w+\s*=", text):
        return None  # CommonJS: default interop, can't tell named exports statically
    return default, named


def _js_broken(path: Path, text: str) -> list[str]:
    out = []
    for m in _JS_IMPORT.finditer(text):
        default, named, spec = m.group(1), m.group(2), m.group(5)
        mod = _js_module(path, spec)
        if mod is None or mod == path or not mod.suffix.lower() in _JS:
            continue
        src = read(mod)
        exp = _js_exports(src) if src is not None else None
        if exp is None:
            continue
        has_default, names = exp
        if default and default != "type" and not has_default:
            out.append(f"{path.name} imports a default export from {mod.name}, which has none")
        for name, _ in _names(named or ""):
            if name not in names and name != "default":
                out.append(f"{path.name} imports {name} from {mod.name}, which doesn't export it")
    return out


def broken_imports(workdir: str | os.PathLike, files: list[str]) -> list[str]:
    """Why some import in the lesson ``files`` (names as the step gives them) doesn't resolve to a module of the
    lesson's own: a name the module no longer defines or exports. Modules outside the lesson folder (the standard
    library, npm packages) are never judged."""
    root = Path(workdir)
    out: list[str] = []
    seen: set[Path] = set()
    for rel in files:
        path = find_file(root, rel)
        if path is None or path in seen:
            continue
        seen.add(path)
        text = read(path)
        if text is None:
            continue
        kind = kind_of(path.name)
        if kind == "py":
            out += _py_broken(path, root, text)
        elif kind == "js":
            out += _js_broken(path, text)
    return out


_LABEL_FILE = re.compile(r"(?<![\w/.-])([\w./-]+\.(?:py|jsx?|tsx?|mjs|cjs|vue|svelte))\b")


def file_in_label(label: str) -> str | None:
    """The code file a check's label names ("main.py calls add(2, 3)" -> main.py), else None."""
    m = _LABEL_FILE.search(label or "")
    return m.group(1) if m else None
