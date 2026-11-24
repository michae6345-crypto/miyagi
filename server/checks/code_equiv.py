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
import builtins
import json
import os
import symtable
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
    # a def with type hints is the same def: ``def add(a: int, b: int) -> int:`` is ``def add(a, b):``
    for m in _PY_DEF.finditer(text):
        plain = ", ".join(_unannotated(p) for p in _top_level_split(m.group(3)) if p.strip())
        line = f"{m.group(1)}def {m.group(2)}({plain}):"
        if line.strip() != m.group(0).strip():
            extra.append(line)
    extra += _py_inlined(body)
    return body + ("\n" + "\n".join(extra) if extra else "")


_PY_TEMP = re.compile(r"^([ \t]*)([A-Za-z_]\w*)[ \t]*=(?!=)[ \t]*(\S[^\n#]*?)[ \t]*(?:#[^\n]*)?$")


def _py_inlined(text: str) -> list[str]:
    """A value kept in a name only to be used once on the next line is the same program with the value in place:
    ``total = add(2, 3)`` then ``print(total)`` is ``print(add(2, 3))``. Only a one-line value, a name read nowhere
    else in the file, and a next line at the same indent."""
    lines = text.split("\n")
    out = []
    for k, ln in enumerate(lines):
        m = _PY_TEMP.match(ln)
        if not m or m.group(3).endswith(("(", "[", "{", ",", "\\")):
            continue
        nxt = next((j for j in range(k + 1, len(lines)) if lines[j].strip()), None)
        if nxt is None:
            continue
        name = m.group(2)
        word = re.compile(rf"(?<![\w.]){re.escape(name)}(?!\w)")
        rest = "\n".join(lines[:k] + lines[k + 1:])
        uses = word.findall(rest)
        indent = lines[nxt][:len(lines[nxt]) - len(lines[nxt].lstrip())]
        if len(uses) != 1 or not word.search(lines[nxt]) or indent != m.group(1) \
                or re.match(rf"[ \t]*{re.escape(name)}\s*=(?!=)", lines[nxt]):
            continue
        out.append(word.sub(lambda _: m.group(3), lines[nxt]))
    return out


_PY_DEF = re.compile(r"^([ \t]*(?:async[ \t]+)?)def[ \t]+(\w+)[ \t]*\(([^()\n]*(?:\([^()\n]*\)[^()\n]*)*)\)"
                     r"[ \t]*(?:->[^:\n]+)?:", re.M)


def _top_level_split(params: str) -> list[str]:
    """Parameters split on the commas outside brackets (``x: dict[str, int], y`` -> two)."""
    out, depth, cur = [], 0, ""
    for ch in params:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [*out, cur]


def _unannotated(param: str) -> str:
    """``b: int = 2`` -> ``b=2``; ``a: int`` -> ``a``."""
    m = re.match(r"\s*(\**\s*[A-Za-z_]\w*)\s*(?::[^=]*)?(=.*)?$", param)
    if not m:
        return param.strip()
    return m.group(1).replace(" ", "") + ("=" + m.group(2)[1:].strip() if m.group(2) else "")


def _stem(path: str) -> str:
    p = Path(path)
    stem = p.name.split(".")[0]
    return p.parent.name if stem == "index" and p.parent.name else stem


def _js_view(text: str, file: Path | None = None, root: Path | None = None) -> str:
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
        bare = _without_script_ext(path)
        if bare is not None:  # '../utils.ts' / './Header.jsx' is the module '../utils' / './Header'
            if default and default != "type":
                extra.append(f"import {default} from {q}{bare}{q}")
            for name, _ in _names(named or ""):
                extra.append(f"import {{ {name} }} from {q}{bare}{q}")
        if star:
            for f in sorted(set(re.findall(rf"(?<![\w.$]){re.escape(star)}\.(\w+)", text))):
                extra.append(f"import {{ {f} }} from {q}{path}{q}")
            body = re.sub(rf"(?<![\w.$]){re.escape(star)}\.(?=\w)", "", body)
    body = _FRAGMENT_CLOSE.sub("</>", _FRAGMENT_OPEN.sub("<>", body))
    extra += _destructured_callbacks(text)
    # a component declared and exported in one line is the same default export as a separate ``export default Food``
    extra += [f"export default {m.group(1)}" for m in _JS_EXPORT_DECL.finditer(text)]
    # a function bound to a name (const f = (a, b) => ..., const f = function (a, b) {...}) is `function f(a, b)`
    for m in _JS_BOUND_FN.finditer(text):
        params = next((g for g in m.groups()[1:] if g is not None), "")
        extra.append(f"function {m.group(1)}({params}) {{")
    if file is not None:  # an import through the project's path alias ('@/utils') is the relative import it stands for
        for m in _JS_IMPORT.finditer(text):
            spec, q = m.group(5), m.group(4)
            if spec.startswith(".") or (rel := _alias_as_relative(file, root, spec)) is None:
                continue
            if m.group(1) and m.group(1) != "type":
                extra.append(f"import {m.group(1)} from {q}{rel}{q}")
            for name, _ in _names(m.group(2) or ""):
                extra.append(f"import {{ {name} }} from {q}{rel}{q}")
    return body + ("\n" + "\n".join(extra) if extra else "")


_JS_EXPORT_DECL = re.compile(r"^[ \t]*export[ \t]+default[ \t]+(?:async[ \t]+)?(?:function\b[ \t]*\*?|class\b)[ \t]*"
                             r"([A-Za-z_$][\w$]*)", re.M)


# a callback over a list that destructures each element: items.map(({ id, price }) => ...)
_DESTRUCTURED_CALLBACK = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\.\s*(?:map|forEach|filter|find|findIndex|some|every|"
                                    r"flatMap)\s*\(\s*\(\s*\{([^{}()]*)\}\s*(?::[^()=]*)?\)\s*=>")


def _singular(name: str) -> str | None:
    low = name.lower()
    if low.endswith("ies") and len(name) > 4:
        return name[:-3] + "y"
    if low.endswith(("ses", "xes", "ches", "shes")):
        return name[:-2]
    if low.endswith("s") and not low.endswith("ss") and len(name) > 2:
        return name[:-1]
    return None


def _destructured_callbacks(text: str) -> list[str]:
    """``items.map(({ id, price }) => <li>{formatPrice(price)}</li>)`` read as the callback that takes the element
    (``item``, the list's name in the singular) and uses ``item.price``: each such callback's body once more, the
    destructured fields written as the element's properties."""
    out = []
    for m in _DESTRUCTURED_CALLBACK.finditer(text):
        elem = _singular(m.group(1))
        fields = [f.split(":")[-1].split("=")[0].strip() for f in m.group(2).split(",")]
        fields = [f for f in fields if _IDENT.fullmatch(f)]
        if not elem or not fields:
            continue
        depth, k = 1, m.end()  # the callback runs to the call's closing parenthesis
        while k < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[k], 0)
            k += 1
        seg = text[m.end():k - 1 if not depth else k]
        for f in fields:
            seg = _rename(seg, f, f"{elem}.{f}")
        out.append(f"{m.group(1)}.map(({elem}) =>{seg})")
    return out


_SCRIPT_EXT = re.compile(r"\.(?:[cm]?[jt]sx?)$")


def _without_script_ext(spec: str) -> str | None:
    """A relative import spec without its script extension (``../utils.ts`` -> ``../utils``), else None."""
    if not spec.startswith(".") or not _SCRIPT_EXT.search(spec):
        return None
    return _SCRIPT_EXT.sub("", spec)


_JS_BOUND_FN = re.compile(r"^[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+([A-Za-z_$][\w$]*)[ \t]*(?::[^=\n]+)?=[ \t]*"
                          r"(?:async[ \t]+)?(?:function[ \t]*\*?[ \t]*[\w$]*[ \t]*\(([^()]*)\)"
                          r"|\(([^()]*)\)[ \t]*(?::[^=\n]+)?=>|([A-Za-z_$][\w$]*)[ \t]*=>)", re.M)


def _tsconfig_paths(start: Path, root: Path) -> tuple[Path, dict] | None:
    """The nearest tsconfig.json / jsconfig.json at or above ``start`` (inside ``root``) that maps import paths:
    (the folder its ``baseUrl`` names, its ``paths``)."""
    from .code_text import strip_comments

    here = start
    while True:
        for name in ("tsconfig.json", "jsconfig.json"):
            cfg = here / name
            src = read(cfg) if cfg.is_file() else None
            if src is None:
                continue
            try:
                data = json.loads(re.sub(r",(\s*[}\]])", r"\1", strip_comments(src, "c")))
            except ValueError:
                continue
            opts = data.get("compilerOptions") if isinstance(data, dict) else None
            if isinstance(opts, dict) and isinstance(opts.get("paths"), dict):
                return here / str(opts.get("baseUrl") or "."), opts["paths"]
        if here == root or root not in here.parents:
            return None
        here = here.parent


def _alias_as_relative(path: Path, root: Path | None, spec: str) -> str | None:
    """``@/utils`` in src/components/Cart.tsx with tsconfig ``"paths": {"@/*": ["src/*"]}`` -> ``../utils``; None when
    no path alias of the project maps it."""
    if root is None:
        return None
    found = _tsconfig_paths(path.parent, root)
    if found is None:
        return None
    base, paths = found
    for key, targets in paths.items():
        if not isinstance(targets, list) or not targets or not isinstance(targets[0], str):
            continue
        k, t = str(key), targets[0]
        if k.endswith("*") and t.endswith("*") and spec.startswith(k[:-1]):
            target = base / (t[:-1] + spec[len(k) - 1:])
        elif k == spec:
            target = base / t
        else:
            continue
        rel = os.path.relpath(target.resolve(), path.parent.resolve()).replace(os.sep, "/")
        return rel if rel.startswith(".") else "./" + rel
    return None


def equivalent_view(text: str, filename: str | None, root: str | os.PathLike | None = None) -> str | None:
    """``text`` written in the canonical form (see the module doc), or None when that is ``text`` itself or the
    language is not Python / JS / TS. Line structure is kept; the canonical import lines are appended. With the lesson
    folder (``root``), an import through a tsconfig path alias also reads as the relative import it means."""
    kind = kind_of(filename)
    if kind is None or not text:
        return None
    if kind == "py":
        view = _py_view(text)
    else:
        path = find_file(root, str(filename)) if root and os.path.isabs(os.fspath(root)) else None
        view = _js_view(text, path, Path(root) if path is not None else None)
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


def _py_case_mismatch(importer: Path, root: Path, mod: str) -> Path | None:
    """The lesson file a module name only matches with its letters' case aside (``from operations import add`` with
    Operations.py beside it): macOS's file system finds it, Python's import doesn't (ModuleNotFoundError). None when
    the name matches exactly, or nothing in the lesson matches at all (a library)."""
    parts = [p for p in mod.lstrip(".").split(".") if p]
    if not parts:
        return None
    for base in ([importer.parent] if mod.startswith(".") else [importer.parent, root]):
        cur = base
        for i, part in enumerate(parts):
            want = {f"{part}.py", part} if i == len(parts) - 1 else {part}
            try:
                names = os.listdir(cur)
            except OSError:
                break
            exact = [n for n in names if n in want]
            if exact:
                if i == len(parts) - 1:
                    return None
                cur = cur / exact[0]
                continue
            folded = [n for n in names if n.casefold() in {w.casefold() for w in want}
                      and (n.endswith(".py") or (cur / n).is_dir())]
            if folded:
                return cur / folded[0]
            break
    return None


def _py_broken(path: Path, root: Path, text: str) -> list[str]:
    out = []
    for mod_name in [*(m.group(1) for m in _PY_FROM.finditer(text)), *(m.group(1) for m in _PY_IMPORT.finditer(text))]:
        if (wrong := _py_case_mismatch(path, root, mod_name)) is not None:
            out.append(f"{path.name} imports {mod_name}, but the file is {wrong.name}: Python's import is "
                       f"case-sensitive (ModuleNotFoundError); rename {wrong.name} so its case matches the import")
            return out
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
    out += _py_shadowed(path, root, text)
    out += _py_not_imported(path, root, text)
    return out


def _py_shadowed(path: Path, root: Path, text: str) -> list[str]:
    """A name the file imports from one of the lesson's own modules and then binds again itself further down (the old
    ``def add(a, b)`` left below ``from operations import add``): every use after that is the file's own copy, not the
    module's."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    out = []
    for k, stmt in enumerate(tree.body):
        if not isinstance(stmt, ast.ImportFrom) or not stmt.module and not stmt.level:
            continue
        mod = _py_module(path, root, "." * (stmt.level or 0) + (stmt.module or ""))
        if mod is None or mod == path:
            continue
        for alias in stmt.names:
            local = alias.asname or alias.name
            for later in tree.body[k + 1:]:
                bound = [later.name] if isinstance(later, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else \
                    [t.id for t in later.targets if isinstance(t, ast.Name)] if isinstance(later, ast.Assign) else []
                if local in bound:
                    what = "def" if isinstance(later, (ast.FunctionDef, ast.AsyncFunctionDef)) else \
                        "class" if isinstance(later, ast.ClassDef) else "assignment"
                    out.append(f"{path.name}'s own {what} of {local} (line {later.lineno}) replaces the {local} it "
                               f"imports from {mod.name}: delete it so the import is used")
                    break
    return out


_MODULE_NAMES = frozenset({"__name__", "__file__", "__doc__", "__spec__", "__loader__", "__package__", "__builtins__",
                           "__path__", "__cached__", "__annotations__", "__dict__", "__debug__"})


def _py_free_names(text: str) -> set[str] | None:
    """The global names a Python module uses but never binds (no def / class / assignment / import of its own, not a
    builtin): each is a NameError when that line runs. None: can't tell (doesn't parse, ``import *``, ``globals()``)."""
    if re.search(r"^\s*from\s+\S+\s+import\s+\*|\bglobals\s*\(|\bexec\s*\(|\b__getattr__\b", text, re.M):
        return None
    try:
        top = symtable.symtable(text, "<lesson>", "exec")
    except (SyntaxError, ValueError, RecursionError):
        return None
    bound = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
    used: set[str] = set()
    stack = [top]
    while stack:
        t = stack.pop()
        for s in t.get_symbols():
            if t is not top and s.is_declared_global() and (s.is_assigned() or s.is_imported()):
                bound.add(s.get_name())  # def setup(): global total; total = 0
            if s.is_referenced() and (s.is_global() or t is top) and not (s.is_assigned() or s.is_imported()
                                                                        or s.is_parameter() or s.is_namespace()):
                used.add(s.get_name())
        stack.extend(t.get_children())
    return used - bound - set(dir(builtins)) - _MODULE_NAMES


def _py_not_imported(path: Path, root: Path, text: str) -> list[str]:
    """A name the file uses but never imports or defines, that another of the lesson's own modules defines (a wrapper
    ``add_numbers`` added to operations.py, still called from main.py that imports only ``add``)."""
    free = _py_free_names(text)
    if not free:
        return []
    out = []
    for other in lesson_files(root, _PY):
        if other == path or not free:
            continue
        src = read(other)
        defined = _py_defines(src) if src is not None else None
        for name in sorted(free & (defined or set())):
            out.append(f"{path.name} uses {name}, which it never imports (it is defined in {other.name})")
            free.discard(name)
    return out


_JS_RESOLVE = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
# TypeScript's ESM imports name the file the .ts compiles to (NodeNext, bundler resolution): "./util.js" is util.ts
_TS_FOR_JS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}


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
    for ext in _TS_FOR_JS.get(base.suffix, ()):
        cand = base.with_suffix(ext)
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


_CJS_OBJECT = re.compile(r"\bmodule\.exports\s*=\s*\{([^{}]*)\}\s*;?\s*$", re.M)
_CJS_ANY = re.compile(r"\bmodule\.exports\s*=")
_CJS_PROP = re.compile(r"\b(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=")
_JS_REQUIRE = re.compile(r"\b(?:const|let|var)\s*\{([^{}]*)\}\s*=\s*require\(\s*(['\"`])([^'\"`\n]+)\2\s*\)")


def _cjs_exports(text: str) -> set[str] | None:
    """The names a CommonJS module exports (``module.exports = { a, b: c }``, ``exports.x = ...``); None when it can't
    tell (``module.exports = someFunction``, a spread, a computed key)."""
    names = set(_CJS_PROP.findall(text))
    objs = _CJS_OBJECT.findall(text)
    if len(_CJS_ANY.findall(text)) != len(objs):
        return None
    for body in objs:
        for part in body.split(","):
            part = part.strip()
            if not part:
                continue
            key = part.split(":", 1)[0].strip()
            if part.startswith("...") or not re.fullmatch(r"[A-Za-z_$][\w$]*", key):
                return None
            names.add(key)
    return names if names or objs else None


_JS_COMPONENT = re.compile(r"^[ \t]*(?:export[ \t]+(?:default[ \t]+)?)?(?:(?:const|let|var)[ \t]+([A-Z][\w$]*)[ \t]*"
                           r"(?::[^=\n]+)?=[ \t]*(?:async[ \t]+)?(?:\([^()]*\)|[A-Za-z_$][\w$]*)[ \t]*(?::[^=\n]+)?=>"
                           r"|function[ \t]+([A-Z][\w$]*)[ \t]*\([^()]*\)[ \t]*(?::[^{\n]+)?)\s*\{", re.M)
_JSX_START = re.compile(r"<[A-Za-z>]")


def _block_at(text: str, start: int) -> str | None:
    """The text inside the braces that open at ``start`` (braces in a string aside), or None when they don't close."""
    depth, i, quote = 0, start, ""
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = ""
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return None


def silent_components(text: str) -> list[str]:
    """React components (a capitalised function) whose body is a block that holds JSX but never returns it
    (``const Header = () => { <header>...</header> }``): the JSX is a statement, the component returns undefined and
    renders nothing."""
    out = []
    for m in _JS_COMPONENT.finditer(text):
        body = _block_at(text, m.end() - 1)
        if body is None or re.search(r"\breturn\b", body):
            continue
        if _JSX_START.match(body.lstrip()):
            out.append(m.group(1) or m.group(2))
    return out


def _js_top_level(text: str, name: str) -> int | None:
    """The 1-based line where ``text`` declares ``name`` at the top level (``function name``, ``const name =``,
    ``class name``, exported or not), else None."""
    m = re.search(rf"^(?:export[ \t]+(?:default[ \t]+)?)?(?:async[ \t]+)?(?:function[ \t]*\*?[ \t]*|(?:const|let|var|"
                  rf"class)[ \t]+){re.escape(name)}(?![\w$])", text, re.M)
    return text.count("\n", 0, m.start()) + 1 if m else None


def _js_shadowed(path: Path, text: str) -> list[str]:
    """A name the file imports and also declares itself at the top level (an old ``function formatPrice`` left below
    ``import { formatPrice } from '../utils'``): TypeScript's TS2440 "Import declaration conflicts with local
    declaration", a SyntaxError ("has already been declared") in JavaScript."""
    out = []
    for m in _JS_IMPORT.finditer(text):
        locals_ = [local for _, local in _names(m.group(2) or "")]
        if m.group(1) and m.group(1) != "type":
            locals_.append(m.group(1))
        for local in locals_:
            if (line := _js_top_level(text, local)) is not None:
                out.append(f"{path.name} declares its own {local} (line {line}) beside the {local} it imports from "
                           f"'{m.group(5)}': delete it so the import is used")
    return out


def defines_top_level(path: Path, text: str, name: str) -> int | None:
    """The 1-based line where a lesson code file binds ``name`` at its top level (a Python def / class / assignment,
    a JavaScript function / const / let / var / class), else None."""
    if kind_of(path.name) == "py":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            return None
        for stmt in tree.body:
            bound = [stmt.name] if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else \
                [t.id for t in stmt.targets if isinstance(t, ast.Name)] if isinstance(stmt, ast.Assign) else \
                [stmt.target.id] if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) else []
            if name in bound:
                return stmt.lineno
        return None
    return _js_top_level(text, name)


def uses_name(path: Path, text: str, name: str) -> bool:
    """Does a lesson code file import ``name`` (``from m import name``, ``import { name } from``)?"""
    if kind_of(path.name) == "py":
        return any(name in [n for n, _ in _from_names(m)] for m in _PY_FROM.finditer(text))
    return any(name in [n for n, _ in _names(m.group(2) or "")] for m in _JS_IMPORT.finditer(text))


def _skip_braces(s: str, i: int) -> int:
    """The index just past the ``}`` that closes the ``{`` at ``s[i]`` (strings and template literals skipped)."""
    depth, quote = 0, ""
    while i < len(s):
        ch = s[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "'\"`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _tag_end(s: str, i: int) -> int:
    """The index of the ``>`` that ends the tag opened at ``s[i]`` (quoted attribute values and ``{...}`` skipped)."""
    quote = ""
    while i < len(s):
        ch = s[i]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "{":
            i = _skip_braces(s, i)
            continue
        elif ch == ">":
            return i
        i += 1
    return i


_RETURN_JSX = re.compile(r"\breturn\s*\(\s*(?=<)")


def adjacent_jsx(text: str) -> list[int]:
    """The 1-based lines of each ``return ( ... )`` whose JSX has two elements side by side at the top (``<>...</>``
    then ``<Footer/>``): "Adjacent JSX elements must be wrapped in an enclosing tag", the file doesn't compile."""
    out = []
    for m in _RETURN_JSX.finditer(text):
        i, depth, roots = m.end(), 0, 0
        while i < len(text):
            ch = text[i]
            if ch == "{":
                i = _skip_braces(text, i)
                continue
            if ch == ")" and depth == 0:
                break
            if ch == "<" and i + 1 < len(text) and (text[i + 1].isalpha() or text[i + 1] in ">/"):
                end = _tag_end(text, i)
                if text[i + 1] == "/":
                    depth -= 1
                else:
                    if depth == 0:
                        roots += 1
                    if text[end - 1] != "/":
                        depth += 1
                i = end + 1
                if depth < 0:
                    break
                continue
            if depth == 0 and not ch.isspace():
                break  # not plain JSX (an expression around it): leave it alone
            i += 1
        if roots > 1:
            out.append(text.count("\n", 0, m.start()) + 1)
    return out


def _js_broken(path: Path, text: str) -> list[str]:
    out = _js_shadowed(path, text)
    if path.suffix.lower() in (".jsx", ".tsx", ".js"):
        for line in adjacent_jsx(text):
            out.append(f"{path.name} returns two JSX elements side by side (line {line}): wrap them in one "
                       f"<>...</> fragment")
    if path.suffix.lower() in (".jsx", ".tsx", ".js"):
        for name in silent_components(text):
            out.append(f"{name} in {path.name} never returns its JSX (its body is in {{ }} with no return), so it "
                       f"renders nothing: return the JSX, or wrap it in ( ) instead of {{ }}")
    for m in _JS_REQUIRE.finditer(text):  # const { scale } = require('./recipe-utils')
        spec = m.group(3)
        if not spec.startswith("."):
            continue
        mod = _js_module(path, spec)
        if mod is None:
            out.append(f"{path.name} requires '{spec}', which doesn't exist")
            continue
        src = read(mod) if mod != path and mod.suffix.lower() in _JS else None
        names = _cjs_exports(src) if src is not None else None
        if names is None:
            continue
        for part in m.group(1).split(","):
            name = part.split(":", 1)[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", name) and name not in names:
                out.append(f"{path.name} requires {name} from {mod.name}, which doesn't export it")
    for m in _JS_IMPORT.finditer(text):
        default, named, spec = m.group(1), m.group(2), m.group(5)
        mod = _js_module(path, spec)
        if mod is None and spec.startswith("."):
            out.append(f"{path.name} imports '{spec}', which doesn't exist (no such file next to it)")
            continue
        if mod is None or mod == path or not mod.suffix.lower() in _JS:
            continue
        src = read(mod)
        exp = _js_exports(src) if src is not None else None
        if exp is None:
            continue
        has_default, names = exp
        if mod.suffix.lower() in (".jsx", ".tsx", ".js"):
            for name in silent_components(src or ""):
                out.append(f"{path.name} renders {name} from {mod.name}, which never returns its JSX (its body is in "
                           f"{{ }} with no return): return the JSX, or wrap it in ( ) instead of {{ }}")
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
