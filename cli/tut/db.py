"""`tut db ...`: schema setup, tutorial reference curves, learner-vs-tutorial comparison."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

from .env import repo_root

STEP_COLS = ("step", "epoch", "iter", "iteration", "global_step")
TIME_COLS = ("time", "timestamp")
ELAPSED_COLS = ("elapsed", "elapsed_s", "wall_time", "seconds")


def _connect():
    import psycopg

    dsn = os.environ.get("TIGER_DATABASE_URL", "")
    if not dsn or "..." in dsn:
        sys.exit("TIGER_DATABASE_URL is not set (put it in .env)")
    return psycopg.connect(dsn, autocommit=True, connect_timeout=10)


def split_sql(text: str) -> list[str]:
    """Split a schema file into statements (no ';' inside strings in our files)."""
    no_comments = "\n".join(re.sub(r"--.*$", "", line) for line in text.splitlines())
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def _root() -> Path:
    root = repo_root()
    if not root:
        sys.exit("run this inside the sandhacks-tutor checkout (can't find shared/contracts/)")
    return root


def apply_schema(conn, root: Path, extras: bool = True) -> list[str]:
    """Each statement on its own in autocommit: continuous aggregates can't be created in a transaction."""
    files = [root / "shared/contracts/tiger-schema.sql"]
    if extras:
        files.append(root / "cli/sql/tiger-extras.sql")
    done = []
    for f in files:
        for stmt in split_sql(f.read_text()):
            conn.execute(stmt)
            done.append(stmt.split("\n")[0][:90])
    return done


def cmd_init(args: argparse.Namespace) -> int:
    root = _root()
    with _connect() as conn:
        for line in apply_schema(conn, root, extras=not args.no_extras):
            print("ok ", line)
        ver = conn.execute("SELECT extversion FROM pg_extension WHERE extname='timescaledb'").fetchone()
        print(f"schema applied (timescaledb {ver[0] if ver else 'MISSING'})")
    return 0


def read_curve_csv(path: str, metric: str) -> list[tuple[int, str, float, float | None, str | None]]:
    """Rows of (step, name, value, elapsed_s|None, iso_time|None).

    Accepts long format (step,name,value) or wide format (step,loss,val_loss,...).
    The step column may be called step/epoch/iter/global_step.
    """
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh)
        cols = [c.strip() for c in (rd.fieldnames or [])]
        lower = {c.lower(): c for c in cols}
        step_col = next((lower[c] for c in STEP_COLS if c in lower), None)
        if not step_col:
            sys.exit(f"{path}: needs a step column ({', '.join(STEP_COLS)}); got {cols}")
        time_col = next((lower[c] for c in TIME_COLS if c in lower), None)
        el_col = next((lower[c] for c in ELAPSED_COLS if c in lower), None)
        long_fmt = "value" in lower
        skip = {step_col, time_col, el_col, lower.get("name"), lower.get("value")} - {None}
        out = []
        for row in rd:
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if not row.get(step_col):
                continue
            step = int(float(row[step_col]))
            el = float(row[el_col]) if el_col and row.get(el_col) else None
            ts = row.get(time_col) if time_col else None
            if long_fmt:
                if row.get(lower["value"]):
                    out.append((step, row.get(lower.get("name", ""), "") or metric, float(row[lower["value"]]), el, ts))
            else:
                for c in cols:
                    if c not in skip and row.get(c):
                        out.append((step, c, float(row[c]), el, ts))
        return out


def cmd_load_ref(args: argparse.Namespace) -> int:
    rows = read_curve_csv(args.csv, args.metric)
    if not rows:
        sys.exit(f"{args.csv}: no data rows")
    run_id = args.run_id or f"ref_{args.step or 'run'}_{secrets.token_hex(3)}"
    steps = sorted({r[0] for r in rows})
    idx = {s: i for i, s in enumerate(steps)}
    # Synthetic timestamps when the CSV has none: one step-row per second ending now, so every
    # point lands in its own metrics_1s bucket and the curve keeps its full resolution.
    base = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=len(steps) + 1)

    def when(r) -> dt.datetime:
        if r[4]:
            t = dt.datetime.fromisoformat(r[4].replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
        if r[3] is not None:
            return base + dt.timedelta(seconds=r[3])
        return base + dt.timedelta(seconds=idx[r[0]])

    times = [when(r) for r in rows]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, lesson_id, step_id, source, command, exit_code, started_at, ended_at, tail) "
            "VALUES (%s,%s,%s,'tutorial',%s,0,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (run_id, args.lesson, args.step, f"reference curve from {os.path.basename(args.csv)}",
             min(times), max(times), args.note),
        )
        with conn.cursor() as cur, cur.copy("COPY training_metrics (time, run_id, step, name, value) FROM STDIN") as cp:
            for r, t in zip(rows, times, strict=True):
                cp.write_row((t, run_id, r[0], r[1], r[2]))
        if not args.no_refresh:
            conn.execute("CALL refresh_continuous_aggregate('metrics_1s', %s::timestamptz, NULL)",
                         (min(times) - dt.timedelta(seconds=1),))
    names = sorted({r[1] for r in rows})
    print(f"loaded {len(rows)} points ({', '.join(names)}) over steps {steps[0]}..{steps[-1]} as run {run_id} (source=tutorial)")
    return 0


def _server_import():
    """server.checks.* is the single source for SQL/stats; make the repo importable."""
    root = _root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _import_curves():
    _server_import()
    from server.checks.curves import compare_to_reference

    return compare_to_reference


def cmd_stats(args: argparse.Namespace) -> int:
    _server_import()
    from server.checks.tiger import stats

    with _connect() as conn:
        while True:
            st = stats(conn, runs=args.runs)
            if args.json:
                print(json.dumps(st), flush=True)
            else:
                tm, le = st["training_metrics"], st["learning_events"]
                q = "  ".join(f"{k} {v} ms" if v is not None else f"{k} n/a" for k, v in st["query_ms"].items())
                print(f"ingest {tm['rows_per_s'] + le['rows_per_s']:.1f} rows/s "
                      f"(metrics {tm['rows_per_s']}/s, events {le['rows_per_s']}/s, last {st['window_s']}s) | "
                      f"rows {tm['total']:,} + {le['total']:,} | chunks {st['chunks']} | query {q}", flush=True)
            if not args.watch:
                return 0
            time.sleep(args.interval)


def cmd_compare(args: argparse.Namespace) -> int:
    compare_to_reference = _import_curves()
    with _connect() as conn:
        res = compare_to_reference(conn, args.learner_run, metric=args.metric, tutorial_run_id=args.ref,
                                   lesson_id=args.lesson, step_id=args.step)
    if args.json:
        print(json.dumps(res, default=str, indent=2))
        return 0
    print(f"learner {args.learner_run} vs tutorial {res['tutorial_run_id']} ({res['metric']})")
    for p in res["points"][-args.last:]:
        tut = f"{p['tutorial']:.4g}" if p["tutorial"] is not None else "-"
        gap = f"{p['gap_decades']:+.2f}" if p["gap_decades"] is not None else "-"
        print(f"  step {p['step']:>7}  learner {p['learner']:.4g}  tutorial {tut:>9}  gap(decades) {gap}")
    print(res["summary"])
    return 0


def add_stats_parser(sub) -> None:
    s = sub.add_parser("stats", help="Tiger Data ingest rows/sec and query latency (ms)")
    s.add_argument("--watch", "-w", action="store_true", help="refresh every --interval seconds")
    s.add_argument("--interval", type=float, default=1.0)
    s.add_argument("--runs", type=int, default=5, help="timed runs per query (median reported)")
    s.add_argument("--json", action="store_true", help="one JSON object per line (for the app)")
    s.set_defaults(func=cmd_stats)


def add_db_parser(sub) -> None:
    d = sub.add_parser("db", help="Tiger Data setup and reference curves")
    dsub = d.add_subparsers(dest="db_cmd", required=True)

    i = dsub.add_parser("init", help="apply shared/contracts/tiger-schema.sql + cli/sql/tiger-extras.sql")
    i.add_argument("--no-extras", action="store_true", help="contract schema only (no refresh policies)")
    i.set_defaults(func=cmd_init)

    lr = dsub.add_parser("load-ref", help="load a tutorial reference curve CSV as a run with source='tutorial'")
    lr.add_argument("csv")
    lr.add_argument("--lesson", help="lesson id")
    lr.add_argument("--step", help="step id")
    lr.add_argument("--metric", default="loss", help="metric name for single-column / long CSVs without names")
    lr.add_argument("--run-id")
    lr.add_argument("--note", help="stored in runs.tail, e.g. where the curve came from")
    lr.add_argument("--no-refresh", action="store_true")
    lr.set_defaults(func=cmd_load_ref)

    c = dsub.add_parser("compare", help="learner curve vs tutorial curve via metrics_1s")
    c.add_argument("learner_run")
    c.add_argument("--ref", help="tutorial run id (default: best match for the learner run's lesson/step)")
    c.add_argument("--lesson", help="lesson id (needed for screen-<lesson> runs without a runs row)")
    c.add_argument("--step", help="step id (prefers that step's reference curve)")
    c.add_argument("--metric", default="loss")
    c.add_argument("--last", type=int, default=15, help="rows to print")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_compare)
