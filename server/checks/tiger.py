"""Tiger Data writers + stats for the engine (GENERALITY RULE: the time-series memory of every session).

    from server.checks.tiger import record_event, record_metric, record_run

    record_event("step_started", lesson_id, step_id, video_t=212.0)
    record_event("check_fail", lesson_id, step_id, video_t, {"check_id": "s4c2", "detail": "plateau"})
    record_event("step_passed", lesson_id, step_id, video_t)   # duration_s filled in from step_started
    record_metric("screen-pinn", "loss", 1200, 0.2504)          # any numeric signal
    record_run({"id": "vscode-7-1731670000000", "lesson_id": "text-nn", "source": "learner", ...})  # its runs row

All three are non-blocking (an in-memory queue). A daemon thread COPYs batches into
``learning_events`` / ``training_metrics`` (and upserts ``runs``) every 0.5 s. **Offline-safe:** when Tiger can't be
reached (venue Wi-Fi blocking the port, no URL yet, a write error), batches are appended to a
local spool (``~/.miyagi/tiger-spool/*.jsonl``, override ``$TUT_SPOOL_DIR``). The writer retries
every 30 s and uploads the whole spool (including ``tut run``'s) as soon as Tiger answers. It
logs one warning per outage and never blocks or raises into the engine.

    python -m server.checks.tiger --ping          # prove connection + schema (no secrets printed)
    python -m server.checks.tiger --flush-spool   # upload the spool now

``stats(conn)`` returns ingest rows/sec, row counts, chunk count and query latency (ms) for the
Tiger-track performance readout (``tut stats``).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import queue
import statistics
import threading
import time
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger("server.checks.tiger")

EVENT_KINDS = frozenset({"step_started", "check_pass", "check_fail", "offtrack", "fix_applied", "question", "step_passed"})
MAX_QUEUE = 100_000
RETRY_S = 30.0                       # reconnect attempt interval while offline
CONNECT_TIMEOUT_S = 5
MAX_SPOOL_BYTES = 200 * 1024 * 1024  # stop spooling (and count drops) beyond this


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def default_spool_dir() -> Path:
    return Path(os.environ.get("TUT_SPOOL_DIR") or Path.home() / ".miyagi" / "tiger-spool").expanduser()


def _iso(t: dt.datetime) -> str:
    return t.isoformat()


def _parse_t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def spool_status(spool_dir: str | Path | None = None) -> dict:
    """Rows waiting in the offline spool (``*.jsonl`` + claimed-but-unfinished files)."""
    d = Path(spool_dir) if spool_dir else default_spool_dir()
    files = sorted(d.glob("*.jsonl")) + sorted(d.glob("*.replaying-*")) if d.is_dir() else []
    rows = 0
    for f in files:
        try:
            with open(f, "rb") as fh:
                rows += sum(1 for _ in fh)
        except OSError:
            pass
    return {"dir": str(d), "files": len(files), "rows": rows}


RUN_COLS = ("id", "lesson_id", "step_id", "source", "command", "exit_code", "started_at", "ended_at", "tail")
INSERT_RUN_SQL = (
    "INSERT INTO runs (id, lesson_id, step_id, source, command, exit_code, started_at, ended_at, tail) "
    "VALUES (%(id)s, %(lesson_id)s, %(step_id)s, %(source)s, %(command)s, %(exit_code)s, %(started_at)s, %(ended_at)s, %(tail)s) "
    "ON CONFLICT (id) DO UPDATE SET exit_code = COALESCE(EXCLUDED.exit_code, runs.exit_code), "
    "ended_at = COALESCE(EXCLUDED.ended_at, runs.ended_at), tail = COALESCE(EXCLUDED.tail, runs.tail), "
    "lesson_id = COALESCE(runs.lesson_id, EXCLUDED.lesson_id), step_id = COALESCE(runs.step_id, EXCLUDED.step_id)"
)
EVENT_COPY = ("COPY learning_events (time, lesson_id, step_id, source_id, video_t, kind, payload, session_id, check_id) "
              "FROM STDIN")
METRIC_COPY = "COPY training_metrics (time, run_id, step, name, value) FROM STDIN"


def write_batch(conn: Any, events: list[tuple], metrics: list[tuple], runs: list[dict] | None = None) -> int:
    """COPY one batch (events/metrics as row tuples with datetime first). Returns rows written."""
    with conn.cursor() as cur:
        if events:
            with cur.copy(EVENT_COPY) as cp:
                for r in events:
                    cp.write_row(r)
        if metrics:
            with cur.copy(METRIC_COPY) as cp:
                for r in metrics:
                    cp.write_row(r)
    for r in runs or []:
        conn.execute(INSERT_RUN_SQL, {k: r.get(k) for k in
                                      ("id", "lesson_id", "step_id", "source", "command", "exit_code", "started_at", "ended_at", "tail")})
    return len(events) + len(metrics) + len(runs or [])


def replay_spool(conn: Any, spool_dir: str | Path | None = None, stale_claim_s: float = 600) -> int:
    """Upload every spooled file (from any process: engine or `tut run`), deleting each once stored.

    Spool format, one JSON object per line:
      {"k": "e", "v": [iso_time, lesson_id, step_id, source_id, video_t, kind, payload_json, session_id, check_id]}
      {"k": "m", "v": [iso_time, run_id, step, name, value]}           # value may be NaN/Infinity
      {"k": "r", "v": {id, lesson_id, step_id, source, command, exit_code, started_at, ended_at, tail}}
    A file is claimed by renaming it to ``*.replaying-<pid>``, so two processes never upload it twice.
    """
    d = Path(spool_dir) if spool_dir else default_spool_dir()
    if not d.is_dir():
        return 0
    now = time.time()
    for orphan in d.glob("*.replaying-*"):  # a crashed uploader: put it back in the queue
        try:
            if now - orphan.stat().st_mtime > stale_claim_s:
                orphan.rename(orphan.with_name(orphan.name.split(".replaying-")[0]))
        except OSError:
            pass
    total = 0
    for f in sorted(d.glob("*.jsonl")):
        claim = f.with_name(f"{f.name}.replaying-{os.getpid()}")
        try:
            f.rename(claim)
        except OSError:
            continue  # someone else took it
        try:
            events, metrics, runs = [], [], []
            with open(claim, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        o = json.loads(line)
                        if o["k"] == "e":
                            events.append((_parse_t(o["v"][0]), *o["v"][1:]))
                        elif o["k"] == "m":
                            metrics.append((_parse_t(o["v"][0]), *o["v"][1:]))
                        elif o["k"] == "r":
                            r = dict(o["v"])
                            for k in ("started_at", "ended_at"):
                                if r.get(k):
                                    r[k] = _parse_t(r[k])
                            runs.append(r)
                    except (ValueError, KeyError, TypeError, IndexError):
                        log.warning("tiger spool: skipping a malformed line in %s", f.name)
            # runs first so a replayed run row exists before its metrics are looked up
            total += write_batch(conn, [], [], runs) + write_batch(conn, events, metrics)
            claim.unlink()
        except Exception:
            try:
                claim.rename(f)
            except OSError:
                pass
            raise
    return total


class TigerWriter:
    """Non-blocking writer: queue → background thread → COPY, or → local spool while offline."""

    def __init__(self, dsn: str | None = None, session_id: str | None = None, flush_every: float = 0.5,
                 connect: Any = None, spool_dir: str | Path | None = None, retry_every: float = RETRY_S):
        self._env_dsn = dsn is None  # follows TIGER_DATABASE_URL (see _sync_dsn)
        self.dsn = dsn if dsn is not None else os.environ.get("TIGER_DATABASE_URL", "")
        self.session_id = session_id or os.environ.get("TUT_SESSION_ID") or f"sess_{uuid.uuid4().hex[:10]}"
        self.flush_every = flush_every
        self.retry_every = retry_every
        self._connect = connect  # injectable for tests; default psycopg.connect
        self.spool_dir = Path(spool_dir) if spool_dir else default_spool_dir()
        self.spool_file = self.spool_dir / f"engine-{self.session_id}-{os.getpid()}.jsonl"
        self._q: queue.Queue = queue.Queue(MAX_QUEUE)
        self._step_started: dict[tuple[str | None, str | None], dt.datetime] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.no_url = not self.dsn or "..." in self.dsn
        self.online = False
        self.last_error: str | None = "TIGER_DATABASE_URL not set" if self.no_url else None
        self._next_retry = 0.0
        self._warned_offline = False
        self.rows_written = 0
        self.rows_spooled = 0
        self.rows_replayed = 0
        self.flushes = 0
        self.last_flush_ms = 0.0
        self.dropped = 0
        if self.no_url:
            log.warning("TIGER_DATABASE_URL not set; learning events/metrics are spooled to %s", self.spool_dir)

    # ------------------------------------------------------------ public
    def record_event(self, kind: str, lesson_id: str | None, step_id: str | None, video_t: float | None = None,
                     payload: dict | None = None, source_id: str | None = None, time: dt.datetime | None = None) -> None:
        if kind not in EVENT_KINDS:
            log.debug("record_event: non-standard kind %r", kind)
        t = time or _now()
        payload = dict(payload or {})
        key = (lesson_id, step_id)
        with self._lock:
            if kind == "step_started":
                self._step_started[key] = t
            elif kind == "step_passed":
                started = self._step_started.pop(key, None)
                if started is not None and "duration_s" not in payload:
                    payload["duration_s"] = round((t - started).total_seconds(), 3)
        row = (t, lesson_id, step_id, source_id, video_t, kind, json.dumps(payload, default=str),
               self.session_id, payload.get("check_id"))
        self._put(("e", row))

    def record_metric(self, run_id: str, name: str, step: int, value: float, time: dt.datetime | None = None) -> None:
        try:
            v = math.nan if value is None else float(value)  # NaN/inf are stored: divergence is a signal
        except (TypeError, ValueError):
            return
        self._put(("m", (time or _now(), run_id, int(step), name, v)))

    def record_run(self, run: dict) -> None:
        """A `runs` row (RUN_COLS; started_at / ended_at as datetimes or None), upserted: /stats reads a run's
        lesson and source ('learner' | 'tutorial' | 'demo') from it."""
        if not isinstance(run, dict) or not run.get("id"):
            return
        self._put(("r", {k: run.get(k) for k in RUN_COLS}))

    def flush(self, timeout: float = 5.0) -> None:
        """Write (or spool) everything queued now: blocking, for shutdown and tests."""
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout)
        self._thread = None
        self._stop = threading.Event()

    close = flush

    @property
    def disabled(self) -> bool:  # kept for callers of the first version: "not writing to Tiger right now"
        return not self.online

    def counters(self) -> dict:
        return {"session_id": self.session_id, "online": self.online, "last_error": self.last_error,
                "rows_written": self.rows_written, "rows_spooled": self.rows_spooled,
                "rows_replayed": self.rows_replayed, "flushes": self.flushes,
                "last_flush_ms": round(self.last_flush_ms, 2), "dropped": self.dropped,
                "queued": self._q.qsize(), "spool_dir": str(self.spool_dir)}

    # ------------------------------------------------------------ internals
    def _put(self, item: tuple) -> None:
        try:
            self._q.put_nowait(item)
        except queue.Full:
            self.dropped += 1
            return
        self._ensure_thread()

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            with self._lock:
                if self._thread is None or not self._thread.is_alive():
                    self._thread = threading.Thread(target=self._loop, name="tiger-writer", daemon=True)
                    self._thread.start()

    def _drain(self) -> tuple[list[tuple], list[tuple], list[dict]]:
        ev, me, rs = [], [], []
        while True:
            try:
                k, row = self._q.get_nowait()
            except queue.Empty:
                return ev, me, rs
            (ev if k == "e" else rs if k == "r" else me).append(row)

    def _open(self):
        if self._connect is not None:
            return self._connect(self.dsn)
        import psycopg

        return psycopg.connect(self.dsn, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S)

    def _sync_dsn(self) -> bool:
        """A writer built from the environment follows TIGER_DATABASE_URL. The app's Settings can send a Tiger URL
        (config.keys -> os.environ, orchestrator.apply_keys) after this writer started; without this it would keep
        spooling, or writing to the old service, until the engine restarts. True if the URL changed."""
        if not self._env_dsn:
            return False
        dsn = os.environ.get("TIGER_DATABASE_URL", "")
        if dsn == self.dsn:
            return False
        self.dsn = dsn
        self.no_url = not dsn or "..." in dsn
        self.online = False
        self.last_error = "TIGER_DATABASE_URL not set" if self.no_url else None
        self._next_retry = 0.0
        self._warned_offline = False
        log.info("Tiger Data URL changed (%s)", "cleared" if self.no_url else "connecting")
        return True

    def _go_offline(self, why: str) -> None:
        self.online = False
        self.last_error = why[:200]
        self._next_retry = time.monotonic() + self.retry_every
        if not self._warned_offline:
            self._warned_offline = True
            log.warning("Tiger Data offline (%s); spooling to %s, retrying every %ds",
                        self.last_error, self.spool_dir, int(self.retry_every))

    def _try_connect(self):
        try:
            conn = self._open()
        except Exception as exc:  # noqa: BLE001
            self._go_offline(_redact(str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__, self.dsn))
            return None
        self.online = True
        self.last_error = None
        if self._warned_offline:
            log.warning("Tiger Data reachable again; uploading the spool")
            self._warned_offline = False
        try:
            self.rows_replayed += replay_spool(conn, self.spool_dir)
        except Exception as exc:  # noqa: BLE001
            self._close(conn)
            self._go_offline(f"spool upload failed: {_redact(str(exc).strip()[:160], self.dsn)}")
            return None
        return conn

    @staticmethod
    def _close(conn) -> None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001, S110
            pass

    def _spool(self, events: list[tuple], metrics: list[tuple], runs: list[dict] | None = None) -> None:
        runs = runs or []
        n = len(events) + len(metrics) + len(runs)
        try:
            self.spool_dir.mkdir(parents=True, exist_ok=True)
            if sum(f.stat().st_size for f in self.spool_dir.glob("*.jsonl")) > MAX_SPOOL_BYTES:
                self.dropped += n
                return
            with open(self.spool_file, "a", encoding="utf-8") as fh:
                for r in runs:  # the same {"k": "r"} line `tut run` spools (replay_spool stores runs first)
                    fh.write(json.dumps({"k": "r", "v": {k: _iso(v) if isinstance(v, dt.datetime) else v
                                                         for k, v in r.items()}}, default=str) + "\n")
                for r in events:
                    fh.write(json.dumps({"k": "e", "v": [_iso(r[0]), *r[1:]]}, default=str) + "\n")
                for r in metrics:
                    fh.write(json.dumps({"k": "m", "v": [_iso(r[0]), *r[1:]]}) + "\n")
            self.rows_spooled += n
        except OSError as exc:
            self.dropped += n
            log.warning("tiger spool write failed (%s); %d rows dropped", exc, n)

    def _loop(self) -> None:
        conn = None
        try:
            while True:
                stopping = self._stop.wait(self.flush_every)
                ev, me, rs = self._drain()
                if self._sync_dsn() and conn is not None:
                    self._close(conn)
                    conn = None
                if conn is None and not self.no_url and time.monotonic() >= self._next_retry:
                    conn = self._try_connect()
                if ev or me or rs:
                    if conn is not None:
                        t0 = time.perf_counter()
                        try:  # runs first: an upsert, so spooling it again when the COPY after it fails is harmless
                            self.rows_written += write_batch(conn, [], [], rs) + write_batch(conn, ev, me)
                            self.flushes += 1
                            self.last_flush_ms = (time.perf_counter() - t0) * 1000
                        except Exception as exc:  # noqa: BLE001
                            self._close(conn)
                            conn = None
                            self._go_offline(f"write failed: {_redact(str(exc).strip()[:160], self.dsn)}")
                            self._spool(ev, me, rs)
                    else:
                        self._spool(ev, me, rs)
                if stopping:
                    return
        finally:
            if conn is not None:
                self._close(conn)


def _redact(msg: str, dsn: str) -> str:
    """Strip the password (and whole DSN) from an error message before it is logged or printed."""
    try:
        from psycopg.conninfo import conninfo_to_dict

        pw = conninfo_to_dict(dsn).get("password")
    except Exception:  # noqa: BLE001
        pw = None
    if dsn:
        msg = msg.replace(dsn, "<dsn>")
    if pw:
        msg = msg.replace(str(pw), "***")
    return msg


_writer: TigerWriter | None = None
_writer_lock = threading.Lock()


def get_writer() -> TigerWriter:
    global _writer
    if _writer is None:
        with _writer_lock:
            if _writer is None:
                _writer = TigerWriter()
    return _writer


def record_event(kind: str, lesson_id: str | None, step_id: str | None, video_t: float | None = None,
                 payload: dict | None = None, **kw: Any) -> None:
    """Record a learning state transition (step_started, check_pass/fail, offtrack, fix_applied,
    question, step_passed). Non-blocking; never raises."""
    try:
        get_writer().record_event(kind, lesson_id, step_id, video_t, payload, **kw)
    except Exception:  # noqa: BLE001
        log.exception("record_event failed")


def record_metric(run_id: str, name: str, step: int, value: float, **kw: Any) -> None:
    """Record any numeric signal (loss, accuracy, tests passing, build time...). Non-blocking; never raises."""
    try:
        get_writer().record_metric(run_id, name, step, value, **kw)
    except Exception:  # noqa: BLE001
        log.exception("record_metric failed")


def record_run(run: dict) -> None:
    """Upsert a run's ``runs`` row: its lesson, step and source ('learner' | 'tutorial' | 'demo'), which /stats
    reads. Non-blocking; never raises."""
    try:
        get_writer().record_run(run)
    except Exception:  # noqa: BLE001
        log.exception("record_run failed")


# ---------------------------------------------------------------- stats
RATE_WINDOW_S = 10
LATENCY_QUERIES = {
    # what the live curve does: the newest run's points from the continuous aggregate
    "live_curve": "SELECT bucket, value, step FROM metrics_1s WHERE run_id = "
                  "(SELECT run_id FROM training_metrics ORDER BY time DESC LIMIT 1) ORDER BY bucket DESC LIMIT 300",
    # what the creator dashboard does: the stuck heatmap across all learners
    "stuck_heatmap": "SELECT video_bucket, sum(stuck) FROM stuck_heatmap GROUP BY 1 ORDER BY 2 DESC LIMIT 20",
}


def _timed(conn: Any, sql: str, runs: int) -> float:
    ms = []
    for _ in range(runs):
        t0 = time.perf_counter()
        conn.execute(sql).fetchall()
        ms.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(ms), 2)


def stats(conn: Any, runs: int = 5) -> dict:
    """Ingest rate (rows/s over the last 10 s), totals, chunks and median query latency (ms)."""
    out: dict[str, Any] = {"window_s": RATE_WINDOW_S}
    for table in ("training_metrics", "learning_events"):
        recent = conn.execute(f"SELECT count(*) FROM {table} WHERE time > now() - interval '{RATE_WINDOW_S} seconds'").fetchone()[0]  # noqa: S608
        try:
            total = conn.execute("SELECT approximate_row_count(%s)", (table,)).fetchone()[0]
        except Exception:  # noqa: BLE001  (plain Postgres / no timescaledb)
            total = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
        out[table] = {"rows_per_s": round(recent / RATE_WINDOW_S, 1), "total": int(total or 0)}
    try:
        out["chunks"] = conn.execute(
            "SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name IN ('training_metrics','learning_events')"
        ).fetchone()[0]
    except Exception:  # noqa: BLE001
        out["chunks"] = None
    out["query_ms"] = {}
    for name, sql in LATENCY_QUERIES.items():
        try:
            out["query_ms"][name] = _timed(conn, sql, runs)
        except Exception as exc:  # noqa: BLE001
            out["query_ms"][name] = None
            out.setdefault("errors", {})[name] = str(exc).strip().splitlines()[0][:120]
    return out


# ---------------------------------------------------------------- CLI: --ping / --flush-spool
EXPECTED_HYPERTABLES = ("training_metrics", "learning_events")
EXPECTED_CAGGS = ("metrics_1s", "stuck_heatmap", "time_per_step", "check_fail_rate", "learner_progress")


def load_env() -> str | None:
    """Load .env like `tut` does: $TUT_ENV, cwd and up, repo root, main checkout (from a worktree)."""
    root = Path(__file__).resolve().parents[2]
    cands = []
    if os.environ.get("TUT_ENV"):
        cands.append(Path(os.environ["TUT_ENV"]).expanduser())
    cands += [d / ".env" for d in [Path.cwd(), *Path.cwd().parents]]
    cands.append(root / ".env")
    if root.parent.name == "worktrees" and root.parent.parent.name == ".claude":
        cands.append(root.parent.parent.parent / ".env")
    for p in cands:
        if p.is_file():
            for raw in p.read_text().splitlines():
                line = raw.strip().removeprefix("export ").strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                        v = v[1:-1]
                    os.environ.setdefault(k.strip(), v)
            return str(p)
    return None


def ping(dsn: str, runs: int = 5) -> dict:
    """Connection + schema check. Never returns user, password or the DSN."""
    import socket

    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    info = conninfo_to_dict(dsn)
    host, port = info.get("host") or "localhost", int(info.get("port") or 5432)
    out: dict[str, Any] = {"host": host, "port": port, "ok": False, "spool": spool_status()}
    t0 = time.perf_counter()
    try:
        socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_S).close()
    except OSError as exc:
        out["tcp_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        out["error"] = f"TCP to {host}:{port} failed: {exc}"
        out["hint"] = (f"this network blocks port {port}: try a phone hotspot, or the pooler port from the Tiger Console "
                       f"(same host, different port). Events are spooled meanwhile.")
        return out
    out["tcp_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    t0 = time.perf_counter()
    try:
        conn = psycopg.connect(dsn, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S * 2)
    except Exception as exc:  # noqa: BLE001
        out["error"] = "login failed: " + _redact(str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__, dsn)
        return out
    out["login_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    with conn:
        out["server"] = conn.execute("SHOW server_version").fetchone()[0]
        ext = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'").fetchone()
        out["timescaledb"] = ext[0] if ext else None
        out["round_trip_ms"] = _timed(conn, "SELECT 1", runs)
        if ext:
            hts = {r[0] for r in conn.execute("SELECT hypertable_name FROM timescaledb_information.hypertables")}
            caggs = {r[0] for r in conn.execute("SELECT view_name FROM timescaledb_information.continuous_aggregates")}
        else:
            hts, caggs = set(), set()
        out["hypertables"] = sorted(hts & set(EXPECTED_HYPERTABLES))
        out["missing"] = [n for n in (*EXPECTED_HYPERTABLES, *EXPECTED_CAGGS) if n not in hts | caggs]
        out["continuous_aggregates"] = sorted(caggs & set(EXPECTED_CAGGS))
        rows = {}
        for t in ("training_metrics", "learning_events", "runs"):
            try:
                rows[t] = int(conn.execute("SELECT approximate_row_count(%s)" if t in hts else f"SELECT count(*) FROM {t}",  # noqa: S608
                                           (t,) if t in hts else None).fetchone()[0])
            except Exception:  # noqa: BLE001  (table not created yet)
                rows[t] = None
        out["rows"] = rows
    out["ok"] = True
    return out


def _print_ping(r: dict) -> None:
    print(f"Tiger ping → {r['host']}:{r['port']}  (user/password not shown)")
    print(f"  tcp connect     {r.get('tcp_ms', '-'):>8} ms")
    if "login_ms" in r:
        print(f"  postgres login  {r['login_ms']:>8} ms   PostgreSQL {r.get('server')}, timescaledb {r.get('timescaledb') or 'MISSING'}")
        print(f"  round trip      {r['round_trip_ms']:>8} ms   (SELECT 1, median)")
        print(f"  hypertables     {', '.join(r['hypertables']) or 'none'}")
        print(f"  continuous aggs {', '.join(r['continuous_aggregates']) or 'none'}")
        if r["missing"]:
            print(f"  MISSING         {', '.join(r['missing'])}  → run `tut db init`")
        print("  rows            " + "  ".join(f"{k} {'?' if v is None else f'{v:,}'}" for k, v in r["rows"].items()))
    sp = r["spool"]
    print(f"  spool           {sp['rows']} rows waiting in {sp['dir']}")
    if r.get("error"):
        print(f"  FAILED          {r['error']}")
        if r.get("hint"):
            print(f"  hint            {r['hint']}")
    print("OK" if r["ok"] and not r.get("missing") else ("OK (schema incomplete)" if r["ok"] else "NOT REACHABLE"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m server.checks.tiger", description=__doc__.split("\n")[0])
    ap.add_argument("--ping", action="store_true", help="connect latency, hypertables/aggregates present, row counts")
    ap.add_argument("--flush-spool", action="store_true", help="upload the offline spool now")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    load_env()
    dsn = os.environ.get("TIGER_DATABASE_URL", "")
    if not args.ping and not args.flush_spool:
        ap.print_help()
        return 2
    if not dsn or "..." in dsn:
        msg = {"ok": False, "error": "TIGER_DATABASE_URL is not set (put it in .env)", "spool": spool_status()}
        print(json.dumps(msg) if args.json else f"{msg['error']}; spool: {msg['spool']['rows']} rows in {msg['spool']['dir']}")
        return 1
    if args.ping:
        r = ping(dsn)
        if args.json:
            print(json.dumps(r))
        else:
            _print_ping(r)
        if not r["ok"]:
            return 1
    if args.flush_spool:
        import psycopg

        try:
            with psycopg.connect(dsn, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S * 2) as conn:
                n = replay_spool(conn)
        except Exception as exc:  # noqa: BLE001
            print(f"spool upload failed: {_redact(str(exc).strip()[:200], dsn)}")
            return 1
        print(f"uploaded {n} spooled rows; {spool_status()['rows']} left")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
