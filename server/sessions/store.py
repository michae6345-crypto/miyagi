"""On-disk progress of the active lesson: ~/miyagi/state/current.json (+ current.graph.json).

current.json holds the progress (small, rewritten often); current.graph.json is the step graph the
builder produced, written once per lesson so a restarted engine can resume without rebuilding.
Writes are atomic (temp file + os.replace). A missing, unreadable or corrupt file reads as "none".
Override the folder with MIYAGI_STATE_DIR (tests do).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("sessions")

VERSION = 1
STATE_FIELDS = ("lessonId", "sourceUrl", "title", "mode", "stepIndex", "stepCount", "stepId", "stepTitle", "passedSteps",
                "skippedSteps", "checks", "videoT", "workdir", "editorOpen", "startedAt", "lastActiveAt")


def state_dir() -> Path:
    return Path(os.environ.get("MIYAGI_STATE_DIR") or Path.home() / "miyagi" / "state")


def _current() -> Path:
    return state_dir() / "current.json"


def _graph_path() -> Path:
    return state_dir() / "current.graph.json"


def _write_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.warning("ignoring unreadable %s: %s", path, e)
        return None


def save(state: dict, graph: dict | None = None) -> dict:
    """Persist progress (and, when given, the lesson's step graph). Returns what was written."""
    out = {k: state.get(k) for k in STATE_FIELDS if k in state}
    out["version"] = VERSION
    out.setdefault("startedAt", time.time())
    out["lastActiveAt"] = state.get("lastActiveAt") or time.time()
    if graph is not None:
        _write_atomic(_graph_path(), graph)
    _write_atomic(_current(), out)
    return out


def load() -> dict | None:
    """The saved progress, or None (no file, corrupt file, or no lesson id in it)."""
    data = _read(_current())
    if not isinstance(data, dict) or not data.get("lessonId") or not isinstance(data.get("stepIndex"), int):
        return None
    return data


def load_graph(state: dict | None = None) -> dict | None:
    """The cached step graph for the saved lesson (None if missing, corrupt or for another lesson)."""
    g = _read(_graph_path())
    if not isinstance(g, dict) or not isinstance(g.get("steps"), list) or not g["steps"]:
        return None
    if state is not None and (g.get("lesson") or {}).get("id") != state.get("lessonId"):
        return None
    return g


def clear() -> None:
    for p in (_current(), _graph_path()):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning("could not remove %s: %s", p, e)
