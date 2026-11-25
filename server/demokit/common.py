"""Where the installed app keeps the neural-net lesson, and whether miyagi is running.

Standard library only, so the reset runs with any python3. folder_name() and lesson_key() copy
server.workspace.paths.folder_name and server.context.store.lesson_key (a test keeps them in step).
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = Path("/Applications/miyagi.app")
ENGINE_PORT = 8787

# The curated lesson (server/orchestrator/curated.py): its graph and its clean nn.py, as the engine ships them.
LESSON_JSON = Path("demo") / "cache" / "lessons" / "text-nn-from-scratch.json"
STARTER = Path("demo") / "nn-start.py"
LESSON_ID = "lesson-nn-from-scratch"
LESSON_TITLE = "A neural net from scratch"
FILE = "nn.py"

# pgrep -f patterns. The app's main process only (its helpers live under Contents/Frameworks), and any engine.
APP_PROC = r"miyagi\.app/Contents/MacOS/miyagi"
ENGINE_PROC = r"-m server\.orchestrator\.main"
PGREP = ("pgrep", "-f", "--")  # `--`: ENGINE_PROC starts with a dash, which pgrep would read as an option (exit 2)


def slugify(text: str, max_len: int = 48) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    if len(t) > max_len:
        t = t[:max_len].rsplit("-", 1)[0] or t[:max_len]
    return t or "lesson"


def folder_name(lesson_id: str, title: str) -> str:
    """`<slug-of-title>-<6 hex of sha1(lesson id)>`, as server.workspace.paths.folder_name names it."""
    return f"{slugify(title or 'lesson')}-{hashlib.sha1((lesson_id or title).encode()).hexdigest()[:6]}"


def lesson_key(lesson_id: str | None) -> str:
    """The file stem of a lesson's context notes, as server.context.store.lesson_key makes it."""
    raw = str(lesson_id or "lesson")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", raw)[:80].strip("._") or "lesson"
    if stem != raw:
        stem += "-" + hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()[:8]
    return stem


def graph_name(lesson_id: str) -> str:
    """graph-<lessonId>.json, as server.sessions.store._graph_name names it."""
    return "graph-" + (re.sub(r"[^A-Za-z0-9._-]", "_", lesson_id)[:120] or "lesson") + ".json"


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@dataclass(frozen=True)
class Layout:
    """Every path the kit reads or moves. Tests build one on a temp HOME and a temp app."""

    home: Path
    app: Path = APP
    repo: Path = REPO_ROOT
    port: int = ENGINE_PORT
    _cache: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def miyagi(self) -> Path:
        return self.home / "miyagi"

    @property
    def lessons(self) -> Path:
        return self.miyagi / "lessons"

    @property
    def state(self) -> Path:
        return self.miyagi / "state"

    @property
    def attempts(self) -> Path:
        return self.lessons / ".miyagi-state" / "attempts"  # curated.prepare_folder keeps old nn.py files here

    @property
    def backups(self) -> Path:
        return self.state / ".demo-backups"

    @property
    def app_support(self) -> Path:
        return self.home / "Library" / "Application Support" / "miyagi"

    def engine_sources(self) -> list[Path]:
        """Where the engine's own files are, first match wins: the installed app's bundle, the installer's copy,
        this checkout."""
        return [self.app / "Contents" / "Resources" / "engine" / "src", self.miyagi / "engine" / "src", self.repo]

    def find(self, rel: Path) -> Path | None:
        return next((s / rel for s in self.engine_sources() if (s / rel).is_file()), None)

    def lesson(self) -> tuple[str, str]:
        """(lesson id, title) of the curated neural-net lesson."""
        if "lesson" not in self._cache:
            g = read_json(self.find(LESSON_JSON) or Path("/nonexistent")) or {}
            meta = g.get("lesson") if isinstance(g.get("lesson"), dict) else {}
            self._cache["lesson"] = (str(meta.get("id") or LESSON_ID), str(meta.get("title") or LESSON_TITLE))
        return self._cache["lesson"]

    def starter(self) -> str:
        """The clean nn.py the engine puts in place on a fresh start."""
        p = self.find(STARTER)
        try:
            return p.read_text(encoding="utf-8") if p else "import numpy as np\n"
        except OSError:
            return "import numpy as np\n"

    def folder(self) -> Path:
        lid, title = self.lesson()
        return self.lessons / folder_name(lid, title)


# ----------------------------------------------------------------------------------------------- is miyagi running

def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    """Something accepts a TCP connection (no request is sent)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pgrep(pattern: str) -> bool:
    try:
        return subprocess.run([*PGREP, pattern], capture_output=True, timeout=5, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def running(port: int = ENGINE_PORT, *, port_probe=port_open, proc_probe=pgrep) -> list[str]:
    """What of miyagi is running: [] when nothing is."""
    out = []
    if proc_probe(APP_PROC):
        out.append("the miyagi app")
    if port_probe(port):
        out.append(f"an engine on :{port}")
    elif proc_probe(ENGINE_PROC):
        out.append("an engine")
    return out


def saved_lesson_id(state: Path) -> str | None:
    """The lesson id in <state>/current.json (the place the app offers to continue), or None."""
    cur = read_json(state / "current.json")
    return str(cur["lessonId"]) if isinstance(cur, dict) and cur.get("lessonId") else None


def tilde(p: Path | str, home: Path) -> str:
    s = str(p)
    h = str(home)
    return "~" + s[len(h):] if s == h or s.startswith(h + "/") else s
