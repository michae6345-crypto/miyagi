"""On-disk progress of the active lesson: ~/miyagi/state/current.json (+ graph-<lessonId>.json).

current.json holds the progress (small, rewritten often) and names its graph file; graph-<lessonId>.json
is the step graph the builder produced, so a restarted engine can resume without rebuilding.
Each file is written atomically (temp file + os.replace), and the pair is committed as a unit: the
graph file is written first, then current.json (the commit point) is replaced to point at it; older
graph files are removed only after that. clear() removes current.json first. So a reader never sees
progress without its graph. A missing, unreadable or corrupt file reads as "none".
history.json lists the lessons finished on this Mac (what each covered): a later lesson's prerequisites read
"passed" from it (prerequisite_status). recent.json lists the last RECENT_MAX unfinished lessons a newer one replaced
(the launcher's "Continue: Build a tiny weather CLI · 2/7", E11). Override the folder with MIYAGI_STATE_DIR (tests do).
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
        prev = load()
        if prev is not None and prev.get("lessonId") != out.get("lessonId"):
            try:  # another lesson replaces this save: keep it on the recent list
                remember(prev)
            except OSError as e:
                log.warning("could not update the recent lessons: %s", e)
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


# ---------------------------------------------------------------- recent unfinished lessons (E11)
RECENT_MAX = 5
RECENT_FIELDS = ("lessonId", "title", "mode", "sourceUrl", "stepIndex", "stepCount", "stepTitle", "workdir",
                 "lastActiveAt")


def _recent_path() -> Path:
    return state_dir() / "recent.json"  # not a graph-*.json file: clear() never removes it


def recent() -> list[dict]:
    """Unfinished lessons a newer lesson replaced, newest first: {lessonId, title, mode, sourceUrl, stepIndex,
    stepCount, stepTitle, workdir, lastActiveAt}. Their step graphs aren't kept: a rebuild (E2's cache) brings one
    back."""
    data = _read(_recent_path())
    return [e for e in data if isinstance(e, dict) and e.get("lessonId")] if isinstance(data, list) else []


def remember(state: dict) -> None:
    """Put an unfinished lesson's save on the recent list (newest first, one entry per lesson)."""
    entry = {k: state.get(k) for k in RECENT_FIELDS if state.get(k) is not None}
    if not entry.get("lessonId"):
        return
    rest = [e for e in recent() if e.get("lessonId") != entry["lessonId"]]
    _write_atomic(_recent_path(), ([entry] + rest)[:RECENT_MAX])


# ---------------------------------------------------------------- finished lessons (prerequisite evidence)
HISTORY_MAX = 50
_STOP = {"a", "an", "the", "and", "or", "of", "in", "on", "to", "for", "with", "your", "how", "what", "basic", "intro",
         "introduction", "using", "use", "simple", "first", "write", "build", "make", "create", "add"}


def _history() -> Path:
    return state_dir() / "history.json"  # not a graph-*.json file: clear() never removes it


def completed() -> list[dict]:
    """Lessons finished on this Mac, oldest first: {lessonId, title, covered: [phrases], finishedAt}."""
    data = _read(_history())
    return [e for e in data if isinstance(e, dict) and e.get("lessonId")] if isinstance(data, list) else []


def record_completed(graph: dict, skipped: set[str] | frozenset[str] = frozenset()) -> dict | None:
    """The lesson's last step passed: remember what it covered (title, goal, concept titles, the steps the learner
    passed; skipped steps don't count) so a later lesson can mark its prerequisites passed."""
    les = graph.get("lesson") or {}
    passed = [st for st in graph.get("steps") or [] if isinstance(st, dict) and st.get("id") not in skipped]
    if not les.get("id") or not passed:
        return None
    covered = [les.get("title"), les.get("goal")] + [p.get("title") for p in les.get("primer") or [] if isinstance(p, dict)]
    covered += [st.get(k) for st in passed for k in ("title", "what")]
    entry = {"lessonId": les["id"], "title": les.get("title") or "a lesson",
             "covered": [c.strip() for c in covered if isinstance(c, str) and c.strip()], "finishedAt": time.time()}
    _write_atomic(_history(), ([e for e in completed() if e["lessonId"] != entry["lessonId"]] + [entry])[-HISTORY_MAX:])
    return entry


def _stems(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if w.endswith("ies") and len(w) > 4:
            w = w[:-3] + "y"
        elif w.endswith("sses"):
            w = w[:-2]
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        if len(w) >= 2 and w not in _STOP:
            out.add(w)
    return out


def _lesson_name(title: str) -> str:
    t = re.sub(r"^(build|make|create|write|code)\s+(a|an|the|your)?\s*", "", (title or "").strip(), flags=re.I)
    return t[:1].upper() + t[1:] if t else "an earlier lesson"


def prerequisite_status(prereqs: list[dict], lesson_id: str | None = None) -> list[dict]:
    """Each prerequisite with status "passed" + evidence ("Passed in Python Calculator") when a finished lesson (not
    this one) covered every word of its title, else "unknown". New dicts; the input is not changed."""
    done = [(e, _stems(" ".join(e.get("covered") or []))) for e in reversed(completed()) if e.get("lessonId") != lesson_id]
    out = []
    for p in prereqs:
        if not isinstance(p, dict):
            continue
        q = {k: v for k, v in p.items() if k != "evidence"}
        q["status"] = "unknown"
        need = _stems(p.get("title") or "")
        hit = next((e for e, have in done if need and need <= have), None)  # newest first
        if hit is not None:
            q["status"], q["evidence"] = "passed", f"Passed in {_lesson_name(hit.get('title') or '')}"
        out.append(q)
    return out
