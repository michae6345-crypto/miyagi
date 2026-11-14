"""`tut` entry point.

    tut run [--step ID] [--lesson ID] [--source learner|tutorial] [--hide-metrics] <cmd...>
    tut db init                       # apply shared/contracts/tiger-schema.sql (+ cli/sql/tiger-extras.sql)
    tut db load-ref curve.csv ...     # load a tutorial reference curve as a run with source='tutorial'
    tut db compare <learner_run_id>   # learner vs tutorial curve through the metrics_1s continuous aggregate
    tut stats [--watch] [--json]      # Tiger ingest rows/sec + query latency (ms)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import secrets
import shlex
import sys
import time

from . import __version__
from .env import load_dotenv
from .metrics import parse_metric
from .runner import run_pty
from .sinks import IngestSink, TigerSink, warn

DEFAULT_INGEST = "http://localhost:8787/ingest"


def new_run_id() -> str:
    return f"run_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}"


def ingest_url() -> str:
    if os.environ.get("TUT_INGEST_URL"):
        return os.environ["TUT_INGEST_URL"]
    eng = os.environ.get("ENGINE_URL", "")
    if eng.startswith(("ws://", "wss://", "http://", "https://")):
        base = eng.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
        return base + "/ingest"
    return DEFAULT_INGEST


def cmd_run(args: argparse.Namespace) -> int:
    argv = list(args.cmd)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        print("usage: tut run <cmd...>", file=sys.stderr)
        return 2
    command = shlex.join(argv)
    run_id = args.run_id or os.environ.get("TUT_RUN_ID") or new_run_id()
    started_at = dt.datetime.now(dt.timezone.utc)
    lesson_id = args.lesson or os.environ.get("TUT_LESSON_ID")
    step_id = args.step or os.environ.get("TUT_STEP_ID")

    ingest = None
    if not args.no_engine:
        ingest = IngestSink(args.engine or ingest_url(), {
            "kind": "run_started", "run_id": run_id, "command": command, "cwd": os.getcwd(),
            "lesson_id": lesson_id, "step_id": step_id, "source": args.source,
        })
        ingest.start()
        lesson_id = lesson_id or ingest.reply.get("lesson_id")
        step_id = step_id or ingest.reply.get("step_id")

    tiger = None
    dsn = os.environ.get("TIGER_DATABASE_URL", "")
    if not args.no_db and dsn and "..." not in dsn:
        tiger = TigerSink(dsn, {"id": run_id, "lesson_id": lesson_id, "step_id": step_id, "source": args.source,
                                "command": command, "started_at": started_at})
        tiger.start()
    elif not args.no_db and not os.environ.get("TUT_QUIET"):
        warn("TIGER_DATABASE_URL not set; metrics not stored in Tiger Data")

    n_metrics = 0

    def on_line(line: str) -> None:
        nonlocal n_metrics
        m = parse_metric(line)
        if m is not None:
            n_metrics += 1
            if ingest:
                ingest.metric(m)
            if tiger:
                tiger.metric(m)
        if ingest:
            ingest.output(line)

    env = dict(os.environ, TUT_RUN_ID=run_id, PYTHONUNBUFFERED="1")
    code, tail = run_pty(argv, on_line, hide_metrics=args.hide_metrics, env=env)

    deadline = time.monotonic() + 4.0
    if ingest:
        ingest.end(code)
        ingest.close(deadline)
    if tiger:
        tiger.end(code, "\n".join(tail), lesson_id, step_id)
        tiger.close(deadline)
    report_losses(run_id, ingest, tiger)
    if args.verbose:
        warn(f"run {run_id}: exit {code}, {n_metrics} metrics"
             + (f", tiger rows {tiger.rows_written}" if tiger else "")
             + (f", engine {'ok' if ingest.started_sent else 'down'}" if ingest else ""))
    return code


def report_losses(run_id: str, ingest: IngestSink | None, tiger: TigerSink | None) -> None:
    """Never lose data silently: say exactly what didn't make it, loudly."""
    if tiger is not None:
        if tiger.still_writing:
            warn(f"Tiger Data still writing at exit (deadline hit): up to {tiger.unwritten} of {tiger.received} "
                 f"metrics for run {run_id} may NOT be stored, and the run's exit code/tail may be missing", loud=True)
        elif tiger.unwritten:
            warn(f"{tiger.unwritten} of {tiger.received} metrics for run {run_id} were NOT stored in Tiger Data", loud=True)
        elif tiger.ok and not tiger.finalized:
            warn(f"run {run_id}: exit code/tail not saved to Tiger Data", loud=True)
    if ingest is not None:
        if ingest.still_sending:
            warn(f"engine still receiving at exit (deadline hit): the end of run {run_id} may not reach the tutor", loud=True)
        elif ingest.unsent:
            loud = ingest.started_sent  # the engine was up at some point: a partial run is real loss
            warn(f"{ingest.unsent} events for run {run_id} were not delivered to the engine", loud=loud)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tut", description="Run your code so the tutor can check it.")
    p.add_argument("--version", action="version", version=f"tut {__version__}")
    sub = p.add_subparsers(dest="cmd_name")

    r = sub.add_parser("run", help="run a command and report it to the tutor")
    r.add_argument("--step", help="step id this run belongs to (default: engine's active step)")
    r.add_argument("--lesson", help="lesson id")
    r.add_argument("--source", default="learner", choices=["learner", "tutorial"])
    r.add_argument("--run-id")
    r.add_argument("--engine", help=f"ingest URL (default {DEFAULT_INGEST}, or $TUT_INGEST_URL)")
    r.add_argument("--no-engine", action="store_true", help="don't POST to the engine")
    r.add_argument("--no-db", action="store_true", help="don't write to Tiger Data")
    r.add_argument("--hide-metrics", action="store_true", help="don't echo ::metric:: lines to the terminal")
    r.add_argument("-v", "--verbose", action="store_true", help="print a one-line summary at the end")
    r.add_argument("cmd", nargs=argparse.REMAINDER)
    r.set_defaults(func=cmd_run)

    from .db import add_db_parser, add_stats_parser
    add_db_parser(sub)
    add_stats_parser(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 2
    return int(args.func(args) or 0)
