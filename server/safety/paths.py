"""Lesson-folder path rules (OWASP LLM06, excessive agency).

Every file name that reaches the engine from a model, a lesson graph, a cached / stored lesson or a coach diff is
untrusted. Before the engine reads or writes such a file it goes through safe_lesson_path():

  * relative only: no absolute path, no `~`, no `..` component, no NUL, no backslash, no Windows drive;
  * after resolve() (symlinks followed) the file is inside workdir.resolve();
  * writes (write=True) also never touch .git/, .vscode/, .venv/, node_modules/ or a dotfile, except the harmless
    project dotfiles in DOTFILE_ALLOW (.gitignore, .editorconfig, .nvmrc, .python-version).
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

WRITE_DENY_DIRS = frozenset({".git", ".vscode", ".venv", "venv", "node_modules", ".idea", ".github", ".devcontainer"})
DOTFILE_ALLOW = frozenset({".gitignore", ".editorconfig", ".nvmrc", ".python-version"})
_DRIVE = re.compile(r"^[A-Za-z]:")


def rel_problem(rel: str | os.PathLike | None, *, write: bool = False) -> str | None:
    """Why `rel` (a path relative to the lesson folder) is refused on its text alone, else None. No disk access."""
    if rel is None:
        return "no path"
    try:
        s = os.fspath(rel)
    except TypeError:
        return "no path"
    if not isinstance(s, str) or not s.strip():
        return "no path"
    if "\x00" in s:
        return "NUL in the path"
    if "\\" in s or _DRIVE.match(s):
        return "not a POSIX relative path"
    if s.startswith(("/", "~")):
        return "absolute or home path"
    parts = [p for p in PurePosixPath(s).parts if p not in ("", ".")]
    if not parts:
        return "no path"
    if ".." in parts:
        return "goes up out of the lesson folder"
    if write:
        return _write_problem(parts)
    return None


def _write_problem(parts: list[str] | tuple[str, ...]) -> str | None:
    for i, part in enumerate(parts):
        if part in WRITE_DENY_DIRS:
            return f"{part}/ is never written"
        if part.startswith("."):
            last = i == len(parts) - 1
            if not (last and part in DOTFILE_ALLOW):
                return f"{part} is a dotfile"
    return None


def safe_lesson_path(workdir: str | os.PathLike | None, rel: str | os.PathLike | None, *,
                     write: bool = False) -> Path | None:
    """workdir/rel when it is safe to read (write=False) or write (write=True), else None.

    The returned path is the resolved one (symlinks followed), so a caller that opens it opens what was checked."""
    if not workdir or rel_problem(rel, write=write) is not None:
        return None
    try:
        root = Path(os.fspath(workdir)).expanduser().resolve()
        target = (root / os.fspath(rel)).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if target == root:
        return None
    try:
        inside = target.relative_to(root)
    except ValueError:
        return None
    if write and _write_problem(inside.parts) is not None:  # a symlink inside the folder onto .git/ or a dotfile
        return None
    return target


def why_unsafe(workdir: str | os.PathLike | None, rel: str | os.PathLike | None, *, write: bool = False) -> str | None:
    """The reason safe_lesson_path() refuses `rel` (None when it accepts it): for logs."""
    if not workdir:
        return "no lesson folder"
    if (why := rel_problem(rel, write=write)) is not None:
        return why
    if safe_lesson_path(workdir, rel, write=write) is None:
        return "outside the lesson folder" if not write else "outside the lesson folder or a protected file"
    return None


def lesson_rel(workdir: str | os.PathLike | None, path: str | os.PathLike) -> str | None:
    """`path` (absolute or relative) as a path relative to the lesson folder, or None when it is not inside it.
    An absolute path is accepted only when it lies inside the folder (VS Code and the coach name files that way)."""
    try:
        s = os.fspath(path)
    except TypeError:
        return None
    if not isinstance(s, str) or not s or "\x00" in s or not workdir:
        return None
    if not s.startswith("/"):
        return s
    p = Path(s)
    for root in (Path(os.fspath(workdir)).expanduser(), _resolved(workdir)):
        for cand in (p, _resolved(p)):
            try:
                rel = cand.relative_to(root).as_posix()
            except ValueError:
                continue
            return rel if rel not in ("", ".") else None
    return None


def lesson_file(workdir: str | os.PathLike | None, path: str | os.PathLike | None, *,
                write: bool = False) -> tuple[Path | None, str]:
    """(workdir / rel, rel) for a lesson file named relatively or by an absolute path inside the folder, when
    safe_lesson_path() accepts it (write rules with write=True); (None, "") otherwise. The path keeps the folder's
    own spelling (not resolved), so callers compare and show it as before."""
    if not workdir or path is None:
        return None, ""
    try:
        s = os.fspath(path)
    except TypeError:
        return None, ""
    rel: str | None
    try:
        rel = Path(s).relative_to(Path(os.fspath(workdir))).as_posix() if s.startswith("/") else s
    except ValueError:
        rel = lesson_rel(workdir, s)
    if not rel or safe_lesson_path(workdir, rel, write=write) is None:
        return None, ""
    return Path(os.fspath(workdir)) / rel, rel


def relative_to_lesson(workdir: str | os.PathLike | None, path: str | os.PathLike) -> str:
    """`path` as the learner should read it on a card: relative to the lesson folder (`src/app.py`, never only
    `app.py` and never an absolute path). Falls back to the file name when it isn't inside the folder."""
    rel = lesson_rel(workdir, os.fspath(path) if os.fspath(path).startswith("/") else
                     str(Path(os.fspath(workdir or ".")) / os.fspath(path)))
    return rel if rel and not rel.startswith("/") else Path(os.fspath(path)).name


def _resolved(p: str | os.PathLike) -> Path:
    try:
        return Path(os.fspath(p)).expanduser().resolve()
    except (OSError, RuntimeError):
        return Path(os.fspath(p))
