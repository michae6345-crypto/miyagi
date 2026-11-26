"""The learner's Jupyter notebook as the checks read it: the exact cell sources they typed and what the cells printed
(desktop test 9: OCR missed `mnist.load_data()` clipped at the editor's edge and wrapped, and passed an "Image shape line
printed" check on the print() SOURCE line). Pure: reads one .ipynb file, never runs anything.

    find_notebook(workdir, names)   the step's notebook in the lesson folder, else the newest .ipynb there (the learner
                                    names it: test 9's mnist.ipynb for the video's Untitled.ipynb)
    read_notebook(path)             Notebook(path, sources, outputs, errors, executed, cells) or None
    Notebook.only(indices)          the same notebook seen through some of its code cells (t10: a step's checks read
                                    only the outputs of the cell(s) holding the step's own code)

On disk a notebook is as of its last save: the lesson folder's .vscode/settings.json turns on files.autoSave for a
notebook lesson (server.workspace.core.ensure_notebook_autosave), so a run cell's outputs reach the file within ~1 s.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_BACKSPACES = re.compile(r"\x08+")


def clean_output(text: str) -> str:
    """A cell's printed text as the learner reads it (t10: Keras's progress lines in mnist.ipynb are full of ANSI codes,
    `\\x1b[1m1875/1875\\x1b[0m ... accuracy: 0.9858`): colour codes go; a progress bar redrawn with backspaces or \\r
    becomes one line per redraw, so each "accuracy: 0.93" is its own line."""
    return _BACKSPACES.sub("\n", _ANSI.sub("", text)).replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class Cell:
    """One code cell: its source, what it printed (ANSI-free), its error outputs, the image types it displayed
    (a matplotlib figure: image/png) and whether it ran."""
    source: str = ""
    outputs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    executed: bool = False
    count: int | None = None  # its execution count ([4]): the kernel's run order


# t10: never tutorial/ (the video's downloaded, finished notebook) or .miyagi-previous/ (an earlier run's set aside)
_SKIP_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__", ".ipynb_checkpoints", "tutorial",
              ".miyagi-previous"}
MAX_BYTES = 20 * 1024 * 1024  # a notebook with huge embedded images: still read, but not a runaway file


@dataclass
class Notebook:
    path: Path
    sources: list[str] = field(default_factory=list)  # each code / markdown cell's source, as typed
    outputs: list[str] = field(default_factory=list)  # each code cell's printed / returned text (stream, text/plain)
    errors: list[str] = field(default_factory=list)  # each error output: "NameError: name 'x' is not defined" + traceback
    executed: bool = False  # some code cell ran (an execution_count or an output)
    cells: list[Cell] = field(default_factory=list)  # the code cells, in order
    # t11: the kernel VS Code saved in the notebook's metadata: kernelspec.display_name (".venv (3.12.16)") and
    # language_info.version ("3.12.16": written only once VS Code connected a kernel; Miyagi's template has none)
    kernel: str = ""
    kernel_version: str = ""

    def only(self, indices: list[int] | tuple[int, ...]) -> "Notebook":
        """This notebook as a step's checks see it (t10): every cell's source (the code may be anywhere), but the
        outputs, errors and run state of the code cells at `indices` only."""
        picked = [self.cells[i] for i in indices if 0 <= i < len(self.cells)]
        return Notebook(path=self.path, sources=list(self.sources),
                        outputs=[o for c in picked for o in c.outputs], errors=[e for c in picked for e in c.errors],
                        executed=any(c.executed for c in picked), cells=picked)

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
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    spec, info = meta.get("kernelspec"), meta.get("language_info")
    nb.kernel = str(spec.get("display_name") or "") if isinstance(spec, dict) else ""
    nb.kernel_version = str(info.get("version") or "") if isinstance(info, dict) else ""
    for cell in data["cells"]:
        if not isinstance(cell, dict):
            continue
        nb.sources.append(_text(cell.get("source")))
        if cell.get("cell_type") != "code":
            continue
        n = cell.get("execution_count")
        c = Cell(source=nb.sources[-1], executed=n is not None,
                 count=n if isinstance(n, int) and not isinstance(n, bool) else None)
        for out in cell.get("outputs") or []:
            if not isinstance(out, dict):
                continue
            c.executed = True
            kind = out.get("output_type")
            if kind == "stream":
                c.outputs.append(clean_output(_text(out.get("text"))))
            elif kind in ("execute_result", "display_data"):
                data_ = out.get("data") or {}
                c.images += [k for k in data_ if isinstance(k, str) and k.startswith("image/")]
                plain = data_.get("text/plain")
                if plain is not None:
                    c.outputs.append(clean_output(_text(plain)))
            elif kind == "error":
                head = f"{out.get('ename') or 'Error'}: {out.get('evalue') or ''}".strip()
                tb = _ANSI.sub("", "\n".join(str(x) for x in out.get("traceback") or []))
                c.errors.append("\n".join(x for x in (head, tb) if x))
        nb.cells.append(c)
        nb.executed = nb.executed or c.executed
        nb.outputs += c.outputs
        nb.errors += c.errors
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
    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    for n in names:
        n = str(n or "").strip()
        if n.endswith(".ipynb"):
            p = Path(n) if os.path.isabs(n) else root / n
            if p.is_file():
                return _instead_of_template(p, root, mtime)
    found = _candidates(root)
    if not found:
        return None
    return max(found, key=mtime)


def _untouched(nb: Notebook | None) -> bool:
    """Miyagi's empty template as made (server.lesson.notebook_steps.empty_notebook): no code typed, nothing ran."""
    return nb is not None and not nb.executed and not any(c.source.strip() for c in nb.cells)


def _instead_of_template(named: Path, root: Path, mtime) -> Path:
    """t11: the learner made their own notebook (test 11: Untitled.ipynb) and left the lesson's named one (mnist.ipynb)
    as Miyagi's untouched template: every check read the empty template. Then the newest other .ipynb in the lesson
    folder that is newer than the template and has code in a cell is the one to read."""
    if not _untouched(read_notebook(named)):
        return named
    t = mtime(named)
    for p in sorted((p for p in _candidates(root) if p != named and mtime(p) > t), key=mtime, reverse=True):
        nb = read_notebook(p)
        if nb is not None and any(c.source.strip() for c in nb.cells):
            return p
    return named
