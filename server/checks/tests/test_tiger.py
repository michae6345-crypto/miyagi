"""server.checks.tiger against a fake connection (no Postgres needed)."""
import datetime as dt
import json
import logging
import re
from pathlib import Path

from server.checks.tiger import TigerWriter, stats

SCHEMA = (Path(__file__).resolve().parents[3] / "shared/contracts/tiger-schema.sql").read_text()


class FakeCopy:
    def __init__(self, sink, sql):
        self.sink, self.sql = sink, sql

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write_row(self, row):
        self.sink.append((self.sql, tuple(row)))


class FakeConn:
    def __init__(self):
        self.copied: list = []
        self.closed = False

    def cursor(self):
        conn = self

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def copy(self, sql):
                return FakeCopy(conn.copied, sql)

        return Cur()

    def close(self):
        self.closed = True


def writer(conn=None, **kw):
    conn = conn or FakeConn()
    return TigerWriter(dsn="postgres://fake", session_id="sess_t", flush_every=0.05,
                       connect=lambda dsn: conn, **kw), conn


def test_record_event_and_metric_copy_rows():
    w, conn = writer()
    t0 = dt.datetime(2026, 11, 14, 20, 0, tzinfo=dt.timezone.utc)
    w.record_event("step_started", "pinn", "s4", 212.0, time=t0)
    w.record_event("check_fail", "pinn", "s4", 230.5, {"check_id": "s4c2", "detail": "plateau"},
                   time=t0 + dt.timedelta(seconds=30))
    w.record_event("step_passed", "pinn", "s4", 260.0, time=t0 + dt.timedelta(seconds=95.5))
    w.record_metric("screen-pinn", "loss", 1200, 0.2504)
    w.record_metric("screen-pinn", "loss", 1300, float("nan"))  # kept: divergence is a signal
    w.record_metric("screen-pinn", "acc", 1, "not a number")    # dropped
    w.flush()
    events = [r for sql, r in conn.copied if "learning_events" in sql]
    metrics = [r for sql, r in conn.copied if "training_metrics" in sql]
    assert [e[5] for e in events] == ["step_started", "check_fail", "step_passed"]
    fail = events[1]
    assert fail[1:5] == ("pinn", "s4", None, 230.5) and fail[7] == "sess_t" and fail[8] == "s4c2"
    assert json.loads(events[2][6]) == {"duration_s": 95.5}  # filled in from step_started
    assert [(m[1], m[2], m[3]) for m in metrics] == [("screen-pinn", 1200, "loss"), ("screen-pinn", 1300, "loss")]
    assert metrics[0][4] == 0.2504 and metrics[1][4] != metrics[1][4]  # NaN
    assert w.counters()["rows_written"] == 5 and conn.closed


def test_copy_columns_exist_in_contract_schema():
    w, conn = writer()
    w.record_event("question", "l", "s1")
    w.record_metric("r", "m", 1, 1.0)
    w.flush()
    cols = {c.strip() for sql, _ in conn.copied for c in re.search(r"\((.*)\) FROM", sql).group(1).split(",")}
    for c in cols:
        assert re.search(rf"\b{c}\b", SCHEMA), f"column {c} missing from tiger-schema.sql"
    for view in ("time_per_step", "check_fail_rate", "learner_progress", "stuck_heatmap", "metrics_1s"):
        assert f"MATERIALIZED VIEW IF NOT EXISTS {view} WITH (timescaledb.continuous)" in SCHEMA


def test_no_url_is_a_silent_noop(caplog):
    caplog.set_level(logging.WARNING)
    w = TigerWriter(dsn="", connect=lambda d: (_ for _ in ()).throw(AssertionError("must not connect")))
    w.record_event("step_started", "l", "s1")
    w.record_event("step_passed", "l", "s1")
    w.record_metric("r", "loss", 1, 0.1)
    w.flush()
    assert w.disabled and w.counters()["rows_written"] == 0
    assert sum("TIGER_DATABASE_URL" in r.message for r in caplog.records) == 1


def test_db_down_warns_once_and_disables(caplog):
    caplog.set_level(logging.WARNING)

    def boom(dsn):
        raise OSError("connection refused")

    w = TigerWriter(dsn="postgres://fake", flush_every=0.05, connect=boom)
    for i in range(5):
        w.record_metric("r", "loss", i, 0.1)
    w.flush()
    w.record_metric("r", "loss", 9, 0.1)  # after disable: no-op, no new thread work
    assert w.disabled
    assert sum("unreachable" in r.message for r in caplog.records) == 1


class StatsConn:
    def __init__(self, fail_timescale=False):
        self.fail_timescale = fail_timescale
        self.sql: list[str] = []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        if self.fail_timescale and ("approximate_row_count" in sql or "timescaledb_information" in sql):
            raise RuntimeError("function does not exist")

        class R:
            def fetchone(self_inner):
                if "interval" in sql:
                    return (50 if "training_metrics" in sql else 10,)
                return (1234,)

            def fetchall(self_inner):
                return []

        return R()


def test_stats_rates_totals_latency():
    st = stats(StatsConn(), runs=3)
    assert st["training_metrics"] == {"rows_per_s": 5.0, "total": 1234}
    assert st["learning_events"]["rows_per_s"] == 1.0
    assert st["chunks"] == 1234
    assert set(st["query_ms"]) == {"live_curve", "stuck_heatmap"}
    assert all(isinstance(v, float) and v >= 0 for v in st["query_ms"].values())


def test_stats_on_plain_postgres_falls_back():
    st = stats(StatsConn(fail_timescale=True), runs=1)
    assert st["training_metrics"]["total"] == 1234 and st["chunks"] is None
