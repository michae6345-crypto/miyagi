"""Incremental workspace scan: an outline per file, reused until the file really changes.

    from server.context.scan import FileScanner
    sc = FileScanner("lesson-abc")
    changed = sc.scan("/Users/me/miyagi/lessons/nn")              # whole folder: only new / changed files come back
    changed = sc.scan(folder, paths=["/Users/me/.../nn.py"])       # just these (a save)
    sc.outline("nn.py")                                             # the cached FileOutline, or None

A file is re-read only when its (mtime, size) moved, and re-outlined only when its content hash changed (a touch or a
save with no edit costs a stat and a hash). The cache is <context>/<lesson>.files.json (0600), next to the notes.

Never read: .venv, node_modules, .git and the other IGNORE_DIRS; hidden folders; secret files (.env, keys:
server.redact.is_secret_file); binaries and media (by extension, or a NUL byte in the first 4 KB); symlinks out of the
folder. Each file is read up to MAX_FILE_BYTES; at most MAX_FILES files and MAX_TOTAL_BYTES per scan.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from server.context.extract import file_outline
from server.context.store import (
    FILES_SUFFIX,
    _ensure_dir,
    _lock,
    enabled,
    lesson_key,
    root,
)

log = logging.getLogger("server.context.scan")

IGNORE_DIRS = frozenset({".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__",
                         ".ipynb_checkpoints", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "build",
                         ".next", ".nuxt", ".cache", "site-packages", "wandb", "runs", "outputs", ".miyagi-state",
                         "tutorial"})
TEXT_EXT = frozenset({".py", ".pyw", ".ipynb", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".toml", ".cfg",
                      ".ini", ".yaml", ".yml", ".md", ".txt", ".sh", ".html", ".css", ".sql", ".r", ".R", ".go", ".rs",
                      ".java", ".c", ".h", ".cpp", ".rb", ".csv"})
MAX_FILE_BYTES = 200_000
MAX_FILES = 300
MAX_TOTAL_BYTES = 3_000_000
MAX_DEPTH = 6


@dataclass
class FileOutline:
    path: str  # relative to the folder
    mtime: float
    size: int
    hash: str
    summary: str
    facts: dict = field(default_factory=dict)
    truncated: bool = False


def _skippable(name: str) -> bool:
    from server.redact import is_secret_file

    return is_secret_file(name)


def _is_text(p: Path, head: bytes) -> bool:
    return p.suffix in TEXT_EXT and b"\x00" not in head[:4096]


class FileScanner:
    def __init__(self, lesson_id: str | None) -> None:
        self.lesson_id = str(lesson_id or "")
        self.cache_path = root() / f"{lesson_key(lesson_id)}{FILES_SUFFIX}"
        self._cache: dict[str, FileOutline] | None = None
        self.stats: dict[str, int] = {"read": 0, "reused": 0, "skipped": 0}

    # ------------------------------------------------------------ cache
    def _load(self) -> dict[str, FileOutline]:
        if self._cache is None:
            self._cache = {}
            try:
                raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                raw = {}
            for k, v in (raw.get("files") or {}).items() if isinstance(raw, dict) else []:
                try:
                    self._cache[k] = FileOutline(**v)
                except TypeError:
                    continue
        return self._cache

    def _save(self) -> None:
        if self._cache is None:
            return
        try:
            d = _ensure_dir()
            fd, tmp = tempfile.mkstemp(prefix=f".{self.cache_path.name}.", dir=d)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"v": 1, "files": {k: asdict(v) for k, v in self._cache.items()}}, f, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.cache_path)
        except OSError as e:
            log.warning("scan cache not saved: %s", type(e).__name__)

    def outline(self, rel: str) -> FileOutline | None:
        return self._load().get(rel)

    # ------------------------------------------------------------ walk
    def _candidates(self, folder: Path) -> Iterable[Path]:
        base_depth = len(folder.parts)
        n = 0
        for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
            depth = len(Path(dirpath).parts) - base_depth
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")
                                 and depth < MAX_DEPTH)
            for name in sorted(filenames):
                if name.startswith(".") or _skippable(name):
                    self.stats["skipped"] += 1
                    continue
                if Path(name).suffix not in TEXT_EXT:
                    self.stats["skipped"] += 1
                    continue
                yield Path(dirpath) / name
                n += 1
                if n >= MAX_FILES:
                    self.stats["capped"] = 1
                    return

    def _inside(self, folder: Path, p: Path) -> str | None:
        try:
            if p.is_symlink():
                return None
            rel = p.resolve().relative_to(folder.resolve())
        except (OSError, ValueError):
            return None
        if any(part in IGNORE_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            return None
        return rel.as_posix()

    def scan(self, folder: str | Path, paths: Iterable[str] | None = None) -> list[FileOutline]:
        """→ the outlines that are new or changed since the last scan (unchanged files are reused, not re-read).
        Files that vanished leave the cache."""
        if not enabled() or not folder:
            return []
        folder = Path(folder)
        if not folder.is_dir():
            return []
        with _lock(self.cache_path):
            cache = self._load()
            whole = paths is None
            todo = list(self._candidates(folder)) if whole else [Path(p) for p in paths or []]
            seen: set[str] = set()
            changed: list[FileOutline] = []
            total = 0
            complete = True
            for p in todo:
                rel = self._inside(folder, p)
                if rel is None or _skippable(p.name) or p.suffix not in TEXT_EXT:
                    continue
                try:
                    st = p.stat()
                except OSError:
                    cache.pop(rel, None)  # removed since the event
                    continue
                seen.add(rel)
                old = cache.get(rel)
                if old is not None and old.mtime == st.st_mtime and old.size == st.st_size:
                    self.stats["reused"] += 1
                    continue
                if total >= MAX_TOTAL_BYTES:
                    complete = False  # the rest waits for the next scan
                    break
                try:
                    with open(p, "rb") as f:
                        data = f.read(MAX_FILE_BYTES + 1)
                except OSError:
                    continue
                if not _is_text(p, data):
                    self.stats["skipped"] += 1
                    continue
                truncated = len(data) > MAX_FILE_BYTES
                data = data[:MAX_FILE_BYTES]
                total += len(data)
                h = hashlib.sha256(data).hexdigest()[:16]
                if old is not None and old.hash == h:  # touched, not edited: keep the outline
                    old.mtime, old.size = st.st_mtime, st.st_size
                    self.stats["reused"] += 1
                    continue
                text = data.decode("utf-8", errors="replace")
                if truncated and p.suffix == ".ipynb":
                    summary, facts = f"{rel}: large notebook ({st.st_size // 1024} KB), not outlined", {}
                else:
                    summary, facts = file_outline(rel, text)
                self.stats["read"] += 1
                out = FileOutline(rel, st.st_mtime, st.st_size, h, summary, facts, truncated)
                cache[rel] = out
                changed.append(out)
            if whole and complete and not self.stats.get("capped"):
                for rel in [k for k in cache if k not in seen]:
                    cache.pop(rel, None)
            self._save()
        return changed
