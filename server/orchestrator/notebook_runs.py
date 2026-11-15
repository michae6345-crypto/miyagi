"""A notebook cell the learner ran, as a run of the step (desktop test 10, Nov 15: R1).

In a VS Code notebook lesson the cells run in the notebook's kernel, never through `tut run` or VS Code's terminal, so
the engine never saw a run: `state.runs` stayed empty for the whole lesson, metric checks waited for a run that never
"finished", and a cell's error reached the coach only as a file change (the s2 typo card came ~12.5 s late).

The notebook on disk says what ran (the lesson folder autosaves, server.workspace.core.ensure_notebook_autosave): each
code cell's execution_count. At step start every notebook in the lesson folder is snapshot (cell -> execution_count);
when a notebook's file changes, a cell whose execution_count is new since then was run by the learner. Those cells are
fed to LessonSession.ingest as one run of the step (run_started, its text outputs ANSI-stripped, run_ended: exit 1 when
a cell has an error output), so the existing machinery grades metrics / output checks from the run, the coach explains
a failed run at once, and Check my work / the judge know the run finished. A cell whose execution_count did not change
is never a run (a save, an edit, a re-opened notebook).

    snapshot(s)          step start: every notebook's execution counts (LessonSession._reset_step_state)
    poll(s) -> bool      any new runs -> ingested (LessonSession.evaluate, every trigger but run_end)
    need_run(s, step, results, gate)   a video lesson's notebook step needs that run, as a "Just teach me" run step does

Colab / browser notebook lessons are left alone (the notebook isn't on this disk). Never raises into the lesson.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("orchestrator.notebook_runs")

PREFIX = "nb-"  # run ids of notebook runs
MAX_BYTES = 20 * 1024 * 1024
_SKIP = {".venv", "venv", "node_modules", ".git", "__pycache__", ".ipynb_checkpoints"}
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][A-Za-z0-9]")
_ids = itertools.count(1)
_MISSING = object()


def watching(s: Any) -> bool:
    """A VS Code notebook lesson (the notebook is on this disk), not a Colab / browser one, not a Demo."""
    graph = getattr(s, "graph", None)
    if not getattr(s, "notebook_lesson", False) or not graph or not getattr(s, "workdir", None):
        return False
    try:
        from . import stage
        from .session import is_colab_lesson

        return not is_colab_lesson(graph) and not stage.on(s)
    except Exception:  # noqa: BLE001
        return False


def _files(workdir: str | os.PathLike, depth: int = 2) -> dict[str, tuple[float, int]]:
    """The notebooks in the lesson folder (and one level down; never .venv / checkpoints): path -> (mtime, size)."""
    out: dict[str, tuple[float, int]] = {}
    try:
        entries = list(os.scandir(workdir))
    except OSError:
        return out
    for e in entries:
        try:
            if e.is_file() and e.name.endswith(".ipynb") and not e.name.startswith("."):
                st = e.stat()
                out[e.path] = (st.st_mtime, st.st_size)
            elif depth > 1 and e.is_dir() and not e.name.startswith(".") and e.name not in _SKIP:
                out.update(_files(e.path, depth - 1))
        except OSError:
            continue
    return out


def _text(v: object) -> str:
    return "".join(str(x) for x in v) if isinstance(v, list) else str(v or "")


def _lines(text: str) -> list[str]:
    """Printed text as the learner sees it: no ANSI colours, a progress bar's \\r rewrites kept as their last state."""
    out = []
    for ln in _ANSI.sub("", text).split("\n"):
        parts = [p for p in ln.split("\r") if p.strip()]
        if parts:
            out.append(parts[-1].rstrip())
    return out


def _cells(path: str) -> list[dict] | None:
    """The notebook's code cells: {key, has_id, count, lines, error, source}. None: unreadable / not a notebook."""
    try:
        p = Path(path)
        if p.stat().st_size > MAX_BYTES:
            return None
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("cells"), list):
        return None
    out = []
    for i, cell in enumerate(data["cells"]):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        count = cell.get("execution_count")
        cid = cell.get("id")
        lines: list[str] = []
        error = False
        for o in cell.get("outputs") or []:
            if not isinstance(o, dict):
                continue
            kind = o.get("output_type")
            if kind == "stream":
                lines += _lines(_text(o.get("text")))
            elif kind in ("execute_result", "display_data"):
                plain = (o.get("data") or {}).get("text/plain")
                if plain is not None:
                    lines += _lines(_text(plain))
            elif kind == "error":
                error = True
                tb = _lines("\n".join(str(x) for x in o.get("traceback") or []))
                head = f"{o.get('ename') or 'Error'}: {o.get('evalue') or ''}".strip()
                lines += tb if any(head in t for t in tb[-3:]) else tb + [head]
        out.append({"key": str(cid) if cid else f"#{i}", "has_id": bool(cid),
                    "count": count if isinstance(count, int) and not isinstance(count, bool) else None,
                    "lines": lines, "error": error, "source": _text(cell.get("source"))})
    return out


def _counts(cells: list[dict]) -> dict[str, int | None]:
    return {c["key"]: c["count"] for c in cells}


def snapshot(s: Any) -> None:
    """Step start: every notebook's execution counts (the baseline a run is new against). Never raises."""
    s._nb_runs = None
    try:
        if not watching(s):
            return
        files = _files(s.workdir)
        base = {p: _counts(cells) for p in files if (cells := _cells(p)) is not None}
        s._nb_runs = {"gen": getattr(s, "step_gen", 0), "seen": files, "base": base}
    except Exception:  # noqa: BLE001
        log.exception("notebook snapshot failed")


def detect(s: Any) -> list[dict]:
    """New runs since the last look: [{run_id, path, cells, lines, failed, command}], one per notebook that changed.
    Synchronous (no await between the read and the baseline update): two evaluations can't both report a run."""
    if not watching(s) or getattr(s, "step", None) is None or getattr(s, "passed", False):
        return []
    st = getattr(s, "_nb_runs", None)
    if st is None or st.get("gen") != getattr(s, "step_gen", 0):
        snapshot(s)  # a step started without one (a restore): from now on
        return []
    files = _files(s.workdir)
    changed = [p for p, sig in files.items() if st["seen"].get(p) != sig]
    st["seen"] = files
    found = []
    for p in changed:
        cells = _cells(p)
        if cells is None:
            continue
        old = st["base"].get(p, {})  # a notebook made after the step began: every executed cell is new
        old_counts = {v for v in old.values() if v is not None}
        ran = []
        for c in cells:
            prev = old.get(c["key"], _MISSING)
            if c["count"] is None or prev == c["count"]:
                continue  # never run, or not run again (a save / an edit): never a run
            if not c["has_id"] and prev is not _MISSING and c["count"] in old_counts:
                continue  # no cell ids (old nbformat): a cell inserted above moved this one, it didn't run
            ran.append(c)
        st["base"][p] = _counts(cells)
        if not ran:
            continue
        ran.sort(key=lambda c: c["count"])
        name = Path(p).name
        nums = ", ".join(f"[{c['count']}]" for c in ran)
        found.append({"run_id": f"{PREFIX}{next(_ids)}", "path": p, "cells": [c["count"] for c in ran],
                      "lines": [ln for c in ran for ln in c["lines"]], "failed": any(c["error"] for c in ran),
                      "command": f"{name}: run cell {nums}"})
    return found


async def poll(s: Any) -> bool:
    """New notebook runs -> LessonSession.ingest (run_started, output, run_ended: the run_end evaluation follows).
    True when at least one run was fed. Never raises."""
    try:
        found = detect(s)
    except Exception:  # noqa: BLE001
        log.exception("notebook run detection failed")
        return False
    for ev in found:
        rid = ev["run_id"]
        log.info("notebook run %s: %s cell(s) %s ran in %s%s", rid, len(ev["cells"]), ev["cells"],
                 Path(ev["path"]).name, " (error)" if ev["failed"] else "")
        try:
            await s.ingest({"kind": "run_started", "run_id": rid, "command": ev["command"], "cwd": str(s.workdir),
                            "source": "notebook"})
            if ev["lines"]:
                await s.ingest({"kind": "output", "run_id": rid, "lines": ev["lines"]})
            await s.ingest({"kind": "run_ended", "run_id": rid, "exit_code": 1 if ev["failed"] else 0})
        except Exception:  # noqa: BLE001
            log.exception("notebook run %s not ingested", rid)
    return bool(found)


def need_run(s: Any, step: dict, results: list[dict], gate: dict) -> tuple[list[dict], dict] | None:
    """A video lesson's notebook step can't pass on its code alone: it needs a run of a cell since the step began
    (as LessonSession._need_run asks of a "Just teach me" run step). One more row, "Ran the cell": green on the step's
    latest notebook run that finished without an error, red on one that stopped with an error, else pending. None:
    not such a step (a "Just teach me" lesson, a Colab lesson, a step without a notebook, no notebook on disk)."""
    try:
        if getattr(s, "lesson_mode", False) or not watching(s):
            return None
        if not (step.get("code") or "").strip():  # t10-flow's s1 (select the .venv kernel) has no cell to run
            return None
        file = str(s._step_file(step) or "")
        if not file.lower().endswith(".ipynb"):
            return None
        from server.checks.notebook import find_notebook

        nb = find_notebook(s.workdir, [file])
        if nb is None:
            return None  # nothing on disk to see a run in: the screen decides, as before
    except Exception:  # noqa: BLE001
        log.exception("notebook run row failed")
        return None
    base = {"checkId": f"{step['id']}-ran", "label": "Ran the cell", "status": "pending",
            "detail": f"run the cell in {nb.name} (Shift+Enter)"}
    runs = [r for r in s.step_runs if r.run_id.startswith(PREFIX) and not r.running]
    row = base
    if runs:
        row = ({**base, "status": "pass", "detail": f"ran in {nb.name}"} if runs[-1].exit_code == 0
               else {**base, "status": "fail", "detail": "the cell stopped with an error"})
    if row["status"] != "pass" and gate.get("passed"):
        gate = {**gate, "passed": False, "via": None}
    return [*results, row], gate
