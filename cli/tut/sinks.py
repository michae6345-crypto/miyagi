"""Background sinks for `tut run`: the engine (/ingest) and Tiger Data.

Both run on daemon threads, never block the passthrough, and degrade to a single
stderr warning when their target is down. The engine sink keeps retrying (with
backoff) so a run started before the engine still shows up once it is back.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .metrics import Metric

MAX_METRICS_PER_NAME_PER_POST = 50


def warn(msg: str, loud: bool = False) -> None:
    """One-line notice on stderr: dim by default; loud (bold yellow WARNING) for data loss."""
    if loud:
        msg = f"WARNING: {msg}"
    style = "\x1b[1;33m" if loud else "\x1b[2m"
    try:
        sys.stderr.write(f"{style}[tut] {msg}\x1b[0m\n" if sys.stderr.isatty() else f"[tut] {msg}\n")
        sys.stderr.flush()
    except Exception:  # noqa: BLE001, S110
        pass


def _thin(points: list[dict], k: int) -> list[dict]:
    if len(points) <= k:
        return points
    stride = len(points) / k
    return [points[int(i * stride)] for i in range(k - 1)] + [points[-1]]


class IngestSink:
    """POSTs JSON arrays of events to the engine, at most ~5 requests per second."""

    def __init__(self, url: str, run_started: dict, interval: float = 0.2, timeout: float = 1.0):
        self.url = url
        self.run_started = run_started
        self.run_id = run_started["run_id"]
        self.interval = interval
        self.timeout = timeout
        self.started_sent = False
        self.reply: dict = {}
        self._lock = threading.Lock()
        self._metrics: list[dict] = []
        self._lines: list[str] = []
        self._ended: dict | None = None
        self._warned = False
        self._down_until = 0.0
        self.unsent = 0  # events still undelivered when the sender stopped
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="tut-ingest", daemon=True)

    def start(self) -> None:
        self._try_send([self.run_started], first=True)  # synchronous: so the engine knows before output flows
        self._thread.start()

    def metric(self, m: Metric) -> None:
        ev = {"kind": "metric", "run_id": self.run_id, "step": m.step, "name": m.name, "value": m.value}
        if not m.finite:
            # NaN/inf isn't valid JSON, but divergence must reach the evaluator:
            # value null + nonfinite "nan"|"inf"|"-inf" (the evaluator treats None as NaN).
            ev["value"] = None
            ev["nonfinite"] = "nan" if m.value != m.value else ("inf" if m.value > 0 else "-inf")
        with self._lock:
            self._metrics.append(ev)

    def output(self, line: str) -> None:
        with self._lock:
            self._lines.append(line[:4000])
            if len(self._lines) > 2000:
                del self._lines[:-2000]

    def end(self, exit_code: int) -> None:
        with self._lock:
            self._ended = {"kind": "run_ended", "run_id": self.run_id, "exit_code": exit_code}

    def close(self, deadline: float) -> None:
        self._stop.set()
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))

    @property
    def still_sending(self) -> bool:
        return self._thread.is_alive()

    # ------------------------------------------------------------
    def _take(self) -> list[dict]:
        with self._lock:
            metrics, self._metrics = self._metrics, []
            lines, self._lines = self._lines, []
            ended, self._ended = self._ended, None
        events: list[dict] = []
        if metrics:
            by_name: dict[str, list[dict]] = collections.defaultdict(list)
            for e in metrics:
                by_name[e["name"]].append(e)
            for pts in by_name.values():
                kept = _thin(pts, MAX_METRICS_PER_NAME_PER_POST)
                bad = [e for e in pts if e["value"] is None and e not in kept]
                events.extend(kept + bad[-1:])  # never thin away a divergence
        if lines:
            events.append({"kind": "output", "run_id": self.run_id, "lines": lines})
        if ended:
            events.append(ended)
        return events

    def _try_send(self, events: list[dict], first: bool = False) -> bool:
        if not self.started_sent and not first:
            events = [self.run_started, *events]
        body = json.dumps(events, allow_nan=False).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
            if not self.started_sent:
                self.started_sent = True
                try:
                    r = json.loads(raw or b"{}")
                    self.reply = r if isinstance(r, dict) else {}
                except ValueError:
                    pass
            if self._warned:
                warn(f"engine reachable again at {self.url}")
                self._warned = False
            return True
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if not self._warned:
                reason = getattr(exc, "reason", exc)
                warn(f"engine not reachable at {self.url} ({reason}); output continues, will retry")
                self._warned = True
            self._down_until = time.monotonic() + 2.0
            return False

    def _loop(self) -> None:
        pending: list[dict] = []
        while True:
            stopping = self._stop.wait(self.interval)
            pending.extend(self._take())
            if pending and (time.monotonic() >= self._down_until or stopping):
                if self._try_send(pending):
                    pending = []
                else:
                    # keep the newest events only while the engine is down
                    pending = [e for e in pending if e["kind"] != "output"][-5000:] + [
                        e for e in pending if e["kind"] == "output"][-50:]
            if stopping:
                self.unsent = len(pending)
                return


def spool_dir() -> Path:
    """Shared offline spool (same format the engine's server.checks.tiger writer uploads)."""
    return Path(os.environ.get("TUT_SPOOL_DIR") or Path.home() / ".miyagi" / "tiger-spool").expanduser()


class TigerSink:
    """Writes `runs` + `training_metrics` rows to Tiger Data with batched COPY.

    Offline-safe: if Tiger can't be reached (or a write fails), the run row and every metric
    not yet stored go to the spool (`~/.miyagi/tiger-spool/tut-<run_id>.jsonl`), which the engine
    uploads when it next reaches Tiger (or: `python -m server.checks.tiger --flush-spool`).
    """

    def __init__(self, dsn: str, run: dict, flush_every: float = 1.0):
        self.dsn = dsn
        self.run = run
        self.flush_every = flush_every
        self.q: queue.Queue = queue.Queue()
        self.ok = False          # connected and the runs row is in
        self.offline = False     # fell back to the spool
        self.dead = False        # kept for compatibility: never set now (the spool catches everything)
        self.finalized = False   # runs row got exit_code/ended_at/tail
        self.received = 0
        self.rows_written = 0
        self.rows_spooled = 0
        self.spool_path: Path | None = None
        self._ended: dict | None = None
        self._abandoned = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="tut-tiger", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def metric(self, m: Metric) -> None:
        self.received += 1
        self.q.put((dt.datetime.now(dt.timezone.utc), self.run["id"], m.step, m.name, m.value))

    def end(self, exit_code: int, tail: str, lesson_id: str | None = None, step_id: str | None = None) -> None:
        self._ended = {"exit_code": exit_code, "tail": tail, "ended_at": dt.datetime.now(dt.timezone.utc),
                       "lesson_id": lesson_id, "step_id": step_id}

    def close(self, deadline: float) -> None:
        self._stop.set()
        self._thread.join(timeout=max(0.0, deadline - 0.5 - time.monotonic()))
        if self._thread.is_alive() and not self.ok:
            # still stuck connecting (e.g. venue Wi-Fi silently drops the port): spool from here
            self._go_offline("connect timed out")
            self._spool(self._drain())
            self._abandoned = True
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))

    @property
    def still_writing(self) -> bool:
        return self._thread.is_alive() and not self._abandoned

    @property
    def unwritten(self) -> int:
        """Metrics neither stored in Tiger nor safe in the spool."""
        return self.received - self.rows_written - self.rows_spooled

    def _drain(self) -> list[tuple]:
        rows = []
        while True:
            try:
                rows.append(self.q.get_nowait())
            except queue.Empty:
                return rows

    def _go_offline(self, why: str) -> None:
        if not self.offline:
            warn(f"Tiger Data unreachable ({why[:120]}); spooling to {spool_dir()}")
        self.offline = True

    def _spool(self, rows: list[tuple]) -> None:
        r, e = self.run, self._ended or {}
        run_row = {"id": r["id"], "lesson_id": e.get("lesson_id") or r.get("lesson_id"),
                   "step_id": e.get("step_id") or r.get("step_id"), "source": r.get("source", "learner"),
                   "command": r.get("command"), "exit_code": e.get("exit_code"),
                   "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
                   "ended_at": e["ended_at"].isoformat() if e.get("ended_at") else None, "tail": e.get("tail")}
        try:
            d = spool_dir()
            d.mkdir(parents=True, exist_ok=True)
            self.spool_path = d / f"tut-{r['id']}.jsonl"
            with open(self.spool_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"k": "r", "v": run_row}) + "\n")
                for row in rows:
                    fh.write(json.dumps({"k": "m", "v": [row[0].isoformat(), *row[1:]]}) + "\n")
            self.rows_spooled += len(rows)
        except OSError as exc:
            warn(f"could not write the Tiger spool ({exc})", loud=True)

    def _loop(self) -> None:
        r = self.run
        conn = None
        try:
            import psycopg

            conn = psycopg.connect(self.dsn, connect_timeout=3, autocommit=True)
            conn.execute(
                "INSERT INTO runs (id, lesson_id, step_id, source, command, started_at) VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (id) DO NOTHING",
                (r["id"], r.get("lesson_id"), r.get("step_id"), r.get("source", "learner"), r["command"], r["started_at"]),
            )
            self.ok = True
        except Exception as exc:  # noqa: BLE001
            self._go_offline(str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__)
            conn = self._close(conn)
        pending: list[tuple] = []
        while True:
            stopping = self._stop.wait(self.flush_every)
            rows = self._drain()
            if rows and conn is not None:
                try:
                    with conn.cursor() as cur, cur.copy(
                        "COPY training_metrics (time, run_id, step, name, value) FROM STDIN"
                    ) as cp:
                        for row in rows:
                            cp.write_row(row)
                    self.rows_written += len(rows)
                    rows = []
                except Exception as exc:  # noqa: BLE001
                    self._go_offline(f"write failed: {str(exc).strip().splitlines()[0][:120]}")
                    conn = self._close(conn)
            pending.extend(rows)
            if stopping:
                break
        if conn is not None and self._ended:
            e = self._ended
            try:
                conn.execute(
                    "UPDATE runs SET exit_code=%s, ended_at=%s, tail=%s, "
                    "lesson_id=COALESCE(lesson_id, %s), step_id=COALESCE(step_id, %s) WHERE id=%s",
                    (e["exit_code"], e["ended_at"], e["tail"], e["lesson_id"], e["step_id"], r["id"]),
                )
                self.finalized = True
            except Exception as exc:  # noqa: BLE001
                self._go_offline(f"write failed: {str(exc).strip().splitlines()[0][:120]}")
                conn = self._close(conn)
        if self._abandoned:
            return  # close() already spooled for us
        if conn is None:
            self._spool(pending)  # run row (with exit code/tail) + every metric not stored
        else:
            self._close(conn)

    @staticmethod
    def _close(conn):
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001, S110
                pass
        return None
