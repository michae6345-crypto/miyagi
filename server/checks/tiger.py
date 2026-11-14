"""Tiger Data writers + stats for the engine (GENERALITY RULE: the time-series memory of every session).

    from server.checks.tiger import record_event, record_metric

    record_event("step_started", lesson_id, step_id, video_t=212.0)
    record_event("check_fail", lesson_id, step_id, video_t, {"check_id": "s4c2", "detail": "plateau"})
    record_event("step_passed", lesson_id, step_id, video_t)   # duration_s filled in from step_started
    record_metric("screen-pinn", "loss", 1200, 0.2504)          # any numeric signal

Both calls are non-blocking (an in-memory queue). A daemon thread COPYs batches into
``learning_events`` / ``training_metrics`` every 0.5 s. With no ``TIGER_DATABASE_URL``, or
when the DB is down, they log ONE warning and become no-ops, so the engine never blocks on Tiger.

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
from typing import Any

log = logging.getLogger("server.checks.tiger")

EVENT_KINDS = frozenset({"step_started", "check_pass", "check_fail", "offtrack", "fix_applied", "question", "step_passed"})
MAX_QUEUE = 100_000


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TigerWriter:
    def __init__(self, dsn: str | None = None, session_id: str | None = None, flush_every: float = 0.5,
                 connect: Any = None):
        self.dsn = dsn if dsn is not None else os.environ.get("TIGER_DATABASE_URL", "")
        self.session_id = session_id or os.environ.get("TUT_SESSION_ID") or f"sess_{uuid.uuid4().hex[:10]}"
        self.flush_every = flush_every
        self._connect = connect  # injectable for tests; default psycopg.connect
        self._events: queue.Queue = queue.Queue(MAX_QUEUE)
        self._metrics: queue.Queue = queue.Queue(MAX_QUEUE)
        self._step_started: dict[tuple[str | None, str | None], dt.datetime] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.disabled = not self.dsn or "..." in self.dsn
        self._warned = False
        self.rows_written = 0
        self.flushes = 0
        self.last_flush_ms = 0.0
        self.dropped = 0
        if self.disabled:
            self._warn("TIGER_DATABASE_URL not set; learning events/metrics are not stored")

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
        if self.disabled:
            return
        self._ensure_thread()
        row = (t, lesson_id, step_id, source_id, video_t, kind, json.dumps(payload, default=str),
               self.session_id, payload.get("check_id"))
        self._put(self._events, row)

    def record_metric(self, run_id: str, name: str, step: int, value: float, time: dt.datetime | None = None) -> None:
        if self.disabled:
            return
        try:
            v = math.nan if value is None else float(value)  # NaN/inf are stored: divergence is a signal
        except (TypeError, ValueError):
            return
        self._ensure_thread()
        self._put(self._metrics, (time or _now(), run_id, int(step), name, v))

    def flush(self, timeout: float = 5.0) -> None:
        """Write everything queued now (blocking, for shutdown and tests)."""
        if self.disabled or self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout)
        self._thread = None
        self._stop = threading.Event()

    close = flush

    def counters(self) -> dict:
        return {"session_id": self.session_id, "enabled": not self.disabled, "rows_written": self.rows_written,
                "flushes": self.flushes, "last_flush_ms": round(self.last_flush_ms, 2), "dropped": self.dropped,
                "queued": self._events.qsize() + self._metrics.qsize()}

    # ------------------------------------------------------------ internals
    def _warn(self, msg: str) -> None:
        if not self._warned:
            self._warned = True
            log.warning(msg)

    def _put(self, q: queue.Queue, row: tuple) -> None:
        try:
            q.put_nowait(row)
        except queue.Full:
            self.dropped += 1

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            with self._lock:
                if self._thread is None or not self._thread.is_alive():
                    self._thread = threading.Thread(target=self._loop, name="tiger-writer", daemon=True)
                    self._thread.start()

    @staticmethod
    def _drain(q: queue.Queue) -> list[tuple]:
        rows = []
        while True:
            try:
                rows.append(q.get_nowait())
            except queue.Empty:
                return rows

    def _open(self):
        if self._connect is not None:
            return self._connect(self.dsn)
        import psycopg

        return psycopg.connect(self.dsn, autocommit=True, connect_timeout=5)

    def _loop(self) -> None:
        try:
            conn = self._open()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Tiger Data unreachable ({str(exc).strip()[:120]}); events/metrics not stored")
            self.disabled = True
            self._drain(self._events)
            self._drain(self._metrics)
            return
        try:
            while True:
                stopping = self._stop.wait(self.flush_every)
                ev, me = self._drain(self._events), self._drain(self._metrics)
                if ev or me:
                    t0 = time.perf_counter()
                    with conn.cursor() as cur:
                        if ev:
                            with cur.copy("COPY learning_events (time, lesson_id, step_id, source_id, video_t, kind, "
                                          "payload, session_id, check_id) FROM STDIN") as cp:
                                for r in ev:
                                    cp.write_row(r)
                        if me:
                            with cur.copy("COPY training_metrics (time, run_id, step, name, value) FROM STDIN") as cp:
                                for r in me:
                                    cp.write_row(r)
                    self.last_flush_ms = (time.perf_counter() - t0) * 1000
                    self.rows_written += len(ev) + len(me)
                    self.flushes += 1
                if stopping:
                    return
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Tiger Data write failed ({str(exc).strip()[:160]}); continuing without it")
            self.disabled = True
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001, S110
                pass


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
