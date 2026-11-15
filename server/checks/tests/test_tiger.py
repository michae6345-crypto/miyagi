"""server.checks.tiger against a fake connection (no Postgres needed)."""
import datetime as dt
import json
import logging
import re
from pathlib import Path

import pytest

from server.checks.tiger import TigerWriter, main, replay_spool, spool_status, stats

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


@pytest.fixture(autouse=True)
def _spool_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_SPOOL_DIR", str(tmp_path / "spool"))


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


class Flaky:
    """connect() fails until .up = True; then hands out FakeConns."""

    def __init__(self):
        self.up = False
        self.attempts = 0
        self.conn = FakeConn()

    def __call__(self, dsn):
        self.attempts += 1
        if not self.up:
            raise OSError("connection to server at host:37145 failed: timeout; password=hunter2")
        return self.conn


def test_no_url_spools(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    w = TigerWriter(dsn="", connect=lambda d: (_ for _ in ()).throw(AssertionError("must not connect")))
    w.record_event("step_started", "l", "s1")
    w.record_metric("r", "loss", 1, 0.1)
    w.flush()
    assert w.counters()["rows_spooled"] == 2 and w.counters()["rows_written"] == 0
    assert spool_status()["rows"] == 2
    assert sum("TIGER_DATABASE_URL" in r.message for r in caplog.records) == 1


def test_offline_spools_then_uploads_on_reconnect(caplog):
    caplog.set_level(logging.WARNING)
    flaky = Flaky()
    w = TigerWriter(dsn="postgres://u:hunter2@h:37145/db", flush_every=0.02, connect=flaky, retry_every=0.2)
    for i in range(5):
        w.record_metric("screen-pinn", "loss", i, 1.0 / (i + 1))
    w.record_event("check_fail", "pinn", "s4", 10.0, {"check_id": "s4c2"})
    import time as _t
    _t.sleep(0.1)
    assert not w.online and spool_status()["rows"] == 6 and w.rows_spooled == 6
    attempts = flaky.attempts
    _t.sleep(0.1)
    assert flaky.attempts == attempts  # waits retry_every between attempts, no hammering
    flaky.up = True
    _t.sleep(0.4)  # next retry connects and replays the spool
    w.record_metric("screen-pinn", "loss", 99, 0.01)
    w.flush()
    assert w.online and w.rows_replayed == 6 and w.rows_written == 1
    assert spool_status()["rows"] == 0  # spool file deleted after upload
    copied_metrics = [r for sql, r in flaky.conn.copied if "training_metrics" in sql]
    assert [r[2] for r in copied_metrics] == [0, 1, 2, 3, 4, 99]
    ev = [r for sql, r in flaky.conn.copied if "learning_events" in sql]
    assert ev[0][5] == "check_fail" and ev[0][8] == "s4c2" and isinstance(ev[0][0], dt.datetime)
    msgs = " ".join(r.message for r in caplog.records)
    assert "hunter2" not in msgs and msgs.count("Tiger Data offline") == 1


def test_write_failure_mid_session_spools_the_batch():
    class Breaks(FakeConn):
        def cursor(self):
            raise RuntimeError("SSL connection has been closed unexpectedly")

    w = TigerWriter(dsn="postgres://fake", flush_every=0.02, connect=lambda d: Breaks(), retry_every=60)
    w.record_metric("r", "loss", 1, 0.5)
    w.flush()
    assert not w.online and w.rows_spooled == 1 and w.dropped == 0


def test_replay_handles_tut_run_spool_with_run_row(tmp_path):
    d = tmp_path / "spool"
    d.mkdir()
    (d / "tut-run_1.jsonl").write_text(
        json.dumps({"k": "r", "v": {"id": "run_1", "command": "python t.py", "exit_code": 0, "started_at": "2026-11-14T20:00:00+00:00",
                                    "ended_at": "2026-11-14T20:01:00+00:00", "tail": "ok", "source": "learner"}}) + "\n"
        + json.dumps({"k": "m", "v": ["2026-11-14T20:00:30+00:00", "run_1", 5, "loss", float("nan")]}) + "\n"
        + "not json\n")

    class C(FakeConn):
        def __init__(self):
            super().__init__()
            self.sql = []

        def execute(self, sql, params=None):
            self.sql.append((sql, params))

    c = C()
    assert replay_spool(c, d) == 2
    assert c.sql[0][0].startswith("INSERT INTO runs") and c.sql[0][1]["exit_code"] == 0
    assert isinstance(c.sql[0][1]["ended_at"], dt.datetime)
    m = [r for sql, r in c.copied if "training_metrics" in sql][0]
    assert m[1:4] == ("run_1", 5, "loss") and m[4] != m[4]  # NaN survives the round trip
    assert not list(d.iterdir())


def test_ping_unreachable_never_prints_secrets(monkeypatch, capsys):
    monkeypatch.setenv("TIGER_DATABASE_URL", "postgres://tsdbadmin:hunter2@127.0.0.1:9/tsdb")
    assert main(["--ping"]) == 1
    out = capsys.readouterr().out
    assert "127.0.0.1:9" in out and "NOT REACHABLE" in out and "hint" in out
    assert "hunter2" not in out and "tsdbadmin" not in out


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


def test_follows_a_tiger_url_sent_after_start(monkeypatch):
    """The app's Settings can send a Tiger URL (config.keys -> os.environ) after the writer started with none:
    the writer connects to it instead of spooling until the engine restarts."""
    import time as _time

    monkeypatch.delenv("TIGER_DATABASE_URL", raising=False)
    conn, dsns = FakeConn(), []
    w = TigerWriter(session_id="sess_t", flush_every=0.05, connect=lambda dsn: dsns.append(dsn) or conn)
    w.record_event("step_started", "l", "s1", 1.0)
    _time.sleep(0.2)
    assert w.no_url and not dsns and spool_status()["rows"] == 1
    monkeypatch.setenv("TIGER_DATABASE_URL", "postgres://from-settings")
    w.record_event("check_pass", "l", "s1", 2.0, {"check_id": "s1c1"})
    w.flush()
    assert dsns == ["postgres://from-settings"] and w.online and not w.no_url
    # the row spooled before the URL arrived is uploaded first, then the new one
    assert [r[5] for sql, r in conn.copied if "learning_events" in sql] == ["step_started", "check_pass"]
    assert spool_status()["rows"] == 0
    monkeypatch.setenv("TIGER_DATABASE_URL", "")  # cleared in Settings: back to the spool, no reconnect
    w.record_event("question", "l", "s1", 3.0)
    w.flush()
    assert w.no_url and not w.online and dsns == ["postgres://from-settings"]
