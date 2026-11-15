"""On-disk progress of the active lesson: ~/miyagi/state/current.json (+ graph-<lessonId>.json).

current.json holds the progress (small, rewritten often) and names its graph file; graph-<lessonId>.json
is the step graph the builder produced, so a restarted engine can resume without rebuilding.
Each file is written atomically (temp file + os.replace), and the pair is committed as a unit: the
graph file is written first, then current.json (the commit point) is replaced to point at it; older
graph files are removed only after that. clear() removes current.json first. So a reader never sees
progress without its graph. A missing, unreadable or corrupt file reads as "none".
Override the folder with MIYAGI_STATE_DIR (tests do).
"""

from __future__ import annotations

import json
import re
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("sessions")

VERSION = 1
STATE_FIELDS = ("lessonId", "sourceUrl", "title", "mode", "stepIndex", "stepCount", "stepId", "stepTitle", "passedSteps",
                "skippedSteps", "checks", "videoT", "workdir", "editorOpen", "startedAt", "lastActiveAt",
                "stopped")  # stopped: kept by the bar's End (sessions/resume.py KEEP_END): restored only by Continue


def state_dir() -> Path:
    return Path(os.environ.get("MIYAGI_STATE_DIR") or Path.home() / "miyagi" / "state")


def _current() -> Path:
    return state_dir() / "current.json"


def _legacy_graph_path() -> Path:
    return state_dir() / "current.graph.json"  # before graph-<lessonId>.json (still read)


def _graph_name(lesson_id: str) -> str:
    return "graph-" + (re.sub(r"[^A-Za-z0-9._-]", "_", lesson_id)[:120] or "lesson") + ".json"


def _graph_files() -> list[Path]:
    d = state_dir()
    return sorted(d.glob("graph-*.json")) + ([_legacy_graph_path()] if _legacy_graph_path().exists() else [])


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
    lid = str(out.get("lessonId") or "lesson")
    name = _graph_name(lid)
    if graph is not None:
        _write_atomic(state_dir() / name, graph)  # 1. the graph, under its own name
    if (state_dir() / name).exists():
        out["graphFile"] = name
    elif _legacy_graph_path().exists():
        out["graphFile"] = _legacy_graph_path().name
    _write_atomic(_current(), out)  # 2. commit: progress + which graph it belongs to
    keep = out.get("graphFile")
    for p in _graph_files():  # 3. only now drop graphs nothing points at
        if p.name != keep:
            try:
                p.unlink()
            except OSError:
                pass
    return out


def load() -> dict | None:
    """The saved progress, or None (no file, corrupt file, or no lesson id in it)."""
    data = _read(_current())
    if not isinstance(data, dict) or not data.get("lessonId") or not isinstance(data.get("stepIndex"), int):
        return None
    return data


def load_graph(state: dict | None = None) -> dict | None:
    """The cached step graph for the saved lesson (None if missing, corrupt or for another lesson)."""
    if state is None:
        state = load()
    candidates: list[Path] = []
    if state is not None:
        if isinstance(state.get("graphFile"), str) and "/" not in state["graphFile"]:
            candidates.append(state_dir() / state["graphFile"])
        if state.get("lessonId"):
            candidates.append(state_dir() / _graph_name(str(state["lessonId"])))
    candidates.append(_legacy_graph_path())
    g = None
    for p in dict.fromkeys(candidates):
        g = _read(p)
        if isinstance(g, dict) and (state is None or (g.get("lesson") or {}).get("id") == state.get("lessonId")):
            break
        g = None
    if not isinstance(g, dict) or not isinstance(g.get("steps"), list) or not g["steps"]:
        return None
    if state is not None and (g.get("lesson") or {}).get("id") != state.get("lessonId"):
        return None
    return g


def clear() -> None:
    for p in [_current(), *_graph_files()]:  # current.json first: no progress is ever left without its graph
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning("could not remove %s: %s", p, e)
