"""A real run's numbers -> Tiger Data (training_metrics + its runs row), whichever way the engine saw the run end.

`tut run` writes its own runs (cli/tut/sinks.py). The runs the engine itself watches never reached Tiger: VS Code's
▷ Run Python File or `python3 nn.py` typed in its terminal (the companion's command_end, taken by
curated.on_command_end or by the session's _ext_run when the step's run check reads it first) and Run it for me (typed
into VS Code's terminal: _terminal_run_result; or run here as a subprocess). So /stats had no loss curve for the
judged lesson. Each of those runs now goes to Tiger once, when it ends (session.ingest "run_ended", and _ext_run):

    record(session, run)   -> metric rows queued (0: not a run the engine owns, nothing new, or no numbers)

  - run_id: the run's own id. vscode-<id>-<startedAt> is the same on every path that sees one VS Code run;
    run-for-me-<ms>; stage-<step>-<n>-<ms>. Each (run, metric, step) is queued once per session, so a run that two
    paths ingest is one run in Tiger.
  - numbers: the run's `epoch N  loss X` lines (curated.parse_output) as "loss", and the metrics ingested for it (the
    step's metric_pattern readings), which win on the same (name, step).
  - not written: `tut run` (it writes its own run, also when typed in VS Code's terminal), the screen's OCR readings
    ("screen-...": VS Code reports the same run's exact output), replayed `tut run` recordings (/demo/replay).
  - Demo lessons (stage.py) replay recorded output: those runs are written with runs.source = 'demo' and /stats
    labels them "Demo recording", never as the learner's own live run.
  - time: the run's lines all arrive at its end, so each series is spread back from the end over the run's own
    duration, at least 1 s apart: one metrics_1s bucket per printed epoch (a curve on /stats, not one averaged
    point). `step` is the printed epoch.
  - non-blocking: server.checks.tiger's queue and offline spool (the record_event path); never raises.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import time
from typing import Any

log = logging.getLogger("orchestrator.tiger_runs")

SOURCES = (("vscode-", "learner"), ("run-for-me-", "learner"), ("stage-", "demo"))
TUT_RX = re.compile(r"(?:^|[\s;&|/])tut\s+run\b")
MIN_GAP_US = 1_000_000  # one metrics_1s bucket per point
MAX_SPAN_S = 3600.0  # a run's spread never reaches back past an hour (the /stats curve shows the last 6 hours)
TAIL_LINES, TAIL_CHARS = 20, 2000


def source_of(run: Any) -> str | None:
    """'learner' (a real run the engine watched), 'demo' (a Demo lesson's recorded run) or None (not ours to write)."""
    rid = str(getattr(run, "run_id", "") or "")
    src = next((s for prefix, s in SOURCES if rid.startswith(prefix)), None)
    if src == "learner" and TUT_RX.search(str(getattr(run, "command", "") or "")):
        return None  # `tut run python nn.py` in VS Code's terminal: tut writes this run to Tiger itself
    return src


def points(run: Any) -> dict[str, list[tuple[int, float | None]]]:
    """{name: [(step, value)]} sorted by step; value None = NaN/inf (stored as NaN: divergence is a signal)."""
    out: dict[tuple[str, int], float | None] = {}
    try:
        from . import curated

        for e, v in curated.parse_output([str(x) for x in getattr(run, "output_tail", None) or []])["losses"]:
            out[("loss", int(e))] = float(v)
    except Exception:  # noqa: BLE001 - its ingested metrics still go
        log.exception("tiger: couldn't read %s's loss lines", getattr(run, "run_id", "?"))
    for name, pts in (getattr(run, "metrics", None) or {}).items():
        for s, v in pts or []:
            out[(str(name), int(s))] = v
    series: dict[str, list[tuple[int, float | None]]] = {}
    for (name, s), v in sorted(out.items()):
        series.setdefault(name, []).append((s, v))
    return series


def spread(n: int, started: float, ended: float) -> list[dt.datetime]:
    """n times ending at `ended` (epoch seconds), oldest first, over the run's duration and >= 1 s apart."""
    end = dt.datetime.fromtimestamp(ended, dt.timezone.utc)
    if n <= 1:
        return [end] * n
    span = min(max(0.0, ended - started), MAX_SPAN_S)
    gap = max(MIN_GAP_US, int(span * 1_000_000 / (n - 1)))
    return [end - dt.timedelta(microseconds=gap * (n - 1 - i)) for i in range(n)]


def record(session: Any, run: Any, now: float | None = None) -> int:
    src = source_of(run)
    fn = getattr(getattr(session, "m", None), "record_run", None)
    if src is None or fn is None:
        return 0
    done = getattr(session, "_tiger_written", None)
    if not isinstance(done, dict):
        done = session._tiger_written = {}
    seen = done.get(run.run_id, set())
    new = {name: [(s, v) for s, v in pts if (name, s) not in seen] for name, pts in points(run).items()}
    new = {name: pts for name, pts in new.items() if pts}
    if not new:
        return 0
    ended = time.time() if now is None else now
    started = float(getattr(run, "started_t", None) or ended)
    rows = [(t, name, s, v) for name, pts in new.items()
            for t, (s, v) in zip(spread(len(pts), started, ended), pts)]
    tail = "\n".join(str(x) for x in (getattr(run, "output_tail", None) or [])[-TAIL_LINES:])[-TAIL_CHARS:]
    row = {"id": run.run_id, "lesson_id": ((getattr(session, "graph", None) or {}).get("lesson") or {}).get("id"),
           "step_id": (getattr(session, "step", None) or {}).get("id"), "source": src,
           "command": str(getattr(run, "command", "") or "")[:500] or None,
           "exit_code": getattr(run, "exit_code", None),
           "started_at": dt.datetime.fromtimestamp(min(started, ended), dt.timezone.utc),
           "ended_at": dt.datetime.fromtimestamp(ended, dt.timezone.utc), "tail": tail or None}
    if not fn(row, rows):
        return 0
    done[run.run_id] = seen | {(name, s) for name, pts in new.items() for s, _ in pts}
    log.info("tiger: %s run %s -> %d metric rows (%s)", src, run.run_id, len(rows),
             ", ".join(f"{n} x{len(p)}" for n, p in new.items()))
    return len(rows)
