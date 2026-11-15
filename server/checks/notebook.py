"""The learner's Jupyter notebook as the checks read it: the exact cell sources they typed and what the cells printed
(desktop test 9: OCR missed `mnist.load_data()` clipped at the editor's edge and wrapped, and passed an "Image shape line
printed" check on the print() SOURCE line). Pure: reads one .ipynb file, never runs anything.

    find_notebook(workdir, names)   the step's notebook in the lesson folder, else the newest .ipynb there (the learner
                                    names it: test 9's mnist.ipynb for the video's Untitled.ipynb)
    read_notebook(path)             Notebook(path, sources, outputs, errors, executed) or None

On disk a notebook is as of its last save: the lesson folder's .vscode/settings.json turns on files.autoSave for a
notebook lesson (server.workspace.core.ensure_notebook_autosave), so a run cell's outputs reach the file within ~1 s.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SKIP_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__", ".ipynb_checkpoints"}
MAX_BYTES = 20 * 1024 * 1024  # a notebook with huge embedded images: still read, but not a runaway file


@dataclass
class Notebook:
    path: Path
    sources: list[str] = field(default_factory=list)  # each code / markdown cell's source, as typed
    outputs: list[str] = field(default_factory=list)  # each code cell's printed / returned text (stream, text/plain)
    errors: list[str] = field(default_factory=list)  # each error output: "NameError: name 'x' is not defined" + traceback
    executed: bool = False  # some code cell ran (an execution_count or an output)

    @property
    def source_text(self) -> str:
        return "\n".join(self.sources)

    @property
    def output_text(self) -> str:
        return "\n".join(self.outputs + self.errors)


def _text(v: object) -> str:
    if isinstance(v, list):
        return "".join(str(x) for x in v)
    return str(v or "")


def read_notebook(path: str | os.PathLike | None) -> Notebook | None:
    """The notebook at `path`, or None (missing, unreadable, not notebook JSON)."""
    if not path:
        return None
    p = Path(path)
    try:
        if not p.is_file() or p.stat().st_size > MAX_BYTES:
            return None
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("cells"), list):
        return None
    nb = Notebook(path=p)
    for cell in data["cells"]:
        if not isinstance(cell, dict):
            continue
        nb.sources.append(_text(cell.get("source")))
        if cell.get("cell_type") != "code":
            continue
        if cell.get("execution_count") is not None:
            nb.executed = True
        for out in cell.get("outputs") or []:
            if not isinstance(out, dict):
                continue
            nb.executed = True
            kind = out.get("output_type")
            if kind == "stream":
                nb.outputs.append(_text(out.get("text")))
            elif kind in ("execute_result", "display_data"):
                plain = (out.get("data") or {}).get("text/plain")
                if plain is not None:
                    nb.outputs.append(_text(plain))
            elif kind == "error":
                head = f"{out.get('ename') or 'Error'}: {out.get('evalue') or ''}".strip()
                tb = _ANSI.sub("", "\n".join(str(x) for x in out.get("traceback") or []))
                nb.errors.append("\n".join(x for x in (head, tb) if x))
    return nb


def _candidates(root: Path, depth: int = 2) -> list[Path]:
    out: list[Path] = []
    try:
        entries = list(os.scandir(root))
    except OSError:
        return out
    for e in entries:
        try:
            if e.is_file() and e.name.endswith(".ipynb") and not e.name.startswith("."):
                out.append(Path(e.path))
            elif depth > 1 and e.is_dir() and not e.name.startswith(".") and e.name not in _SKIP_DIRS:
                out.extend(_candidates(Path(e.path), depth - 1))
        except OSError:
            continue
    return out


def find_notebook(workdir: str | os.PathLike | None, names: list[str] | tuple[str, ...] = ()) -> Path | None:
    """The lesson's notebook: a named one (the step's file) in the lesson folder when it exists, else the most recently
    modified .ipynb in the folder (and one level down; never .venv / checkpoints). None: no notebook there."""
    if not workdir:
        return None
    root = Path(workdir)
    if not root.is_dir():
        return None
    for n in names:
        n = str(n or "").strip()
        if n.endswith(".ipynb"):
            p = Path(n) if os.path.isabs(n) else root / n
            if p.is_file():
                return p
    found = _candidates(root)
    if not found:
        return None

    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    return max(found, key=mtime)
