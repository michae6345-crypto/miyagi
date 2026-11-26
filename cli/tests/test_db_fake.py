"""DB layer against a fake psycopg (no Postgres needed)."""
import argparse
import json
import datetime as dt
import sys
import time
import types
from pathlib import Path

import pytest

from tut import db
from tut.metrics import Metric
from tut.sinks import TigerSink

ROOT = Path(__file__).resolve().parents[2]


class FakeCopy:
    def __init__(self, log, sql):
        self.log, self.sql = log, sql

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write_row(self, row):
        self.log.append(("row", self.sql, tuple(row)))


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def copy(self, sql):
        return FakeCopy(self.log, sql)


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


class FakeConn:
    def __init__(self, log, fail_on=None):
        self.log, self.fail_on = log, fail_on

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError(f"boom on {self.fail_on}")
        self.log.append(("sql", sql, params))
        return FakeResult(("2.17.0",) if "extversion" in sql else (7,))

    def cursor(self):
        return FakeCursor(self.log)


@pytest.fixture
def fake_pg(monkeypatch, tmp_path):
    log: list = []
    state = {"fail_connect": False, "fail_on": None, "dsn": None}

    def connect(dsn, **kw):
        state["dsn"] = dsn
        if state["fail_connect"]:
            raise OSError("connection refused")
        return FakeConn(log, state["fail_on"])

    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(connect=connect))
    monkeypatch.setenv("TIGER_DATABASE_URL", "postgres://fake/db")
    monkeypatch.setenv("TUT_SPOOL_DIR", str(tmp_path / "spool"))
    return log, state


def _run(sink: TigerSink, n=3):
    sink.start()
    for i in range(n):
        sink.metric(Metric(i * 10, "loss", 1.0 / (i + 1)))
    sink.end(0, "tail text", "lesson1", "s5")
    sink.close(time.monotonic() + 5)


def test_tiger_sink_writes_run_metrics_and_end(fake_pg):
    log, _ = fake_pg
    run = {"id": "run_x", "command": "python t.py", "started_at": dt.datetime.now(dt.timezone.utc), "source": "learner"}
    sink = TigerSink("postgres://fake/db", run, flush_every=0.05)
    _run(sink)
    sqls = [e[1] for e in log if e[0] == "sql"]
    assert sqls[0].startswith("INSERT INTO runs")
    rows = [e[2] for e in log if e[0] == "row"]
    assert [(r[1], r[2], r[3]) for r in rows] == [("run_x", 0, "loss"), ("run_x", 10, "loss"), ("run_x", 20, "loss")]
    assert all("COPY training_metrics" in e[1] for e in log if e[0] == "row")
    assert sqls[-1].startswith("UPDATE runs SET exit_code")
    assert sink.ok and sink.rows_written == 3


def _spooled(tmp_path):
    out = []
    for f in sorted((tmp_path / "spool").glob("*.jsonl")):
        out += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
    return out


def test_tiger_sink_db_down_spools_everything(fake_pg, tmp_path, capsys):
    _, state = fake_pg
    state["fail_connect"] = True
    sink = TigerSink("postgres://fake/db", {"id": "r", "command": "c", "started_at": None}, flush_every=0.05)
    _run(sink)
    assert sink.offline and not sink.ok and sink.rows_spooled == 3 and sink.unwritten == 0
    assert capsys.readouterr().err.count("Tiger Data unreachable") == 1
    lines = _spooled(tmp_path)
    assert lines[0]["k"] == "r" and lines[0]["v"]["exit_code"] == 0 and lines[0]["v"]["tail"] == "tail text"
    assert [(ln["v"][2], ln["v"][3]) for ln in lines[1:]] == [(0, "loss"), (10, "loss"), (20, "loss")]


def test_tiger_sink_write_error_spools(fake_pg, tmp_path, capsys):
    _, state = fake_pg
    state["fail_on"] = "INSERT INTO runs"
    sink = TigerSink("postgres://fake/db", {"id": "r", "command": "c", "started_at": None}, flush_every=0.05)
    _run(sink)
    assert sink.offline and sink.rows_spooled == 3 and sink.unwritten == 0
    assert "spooling to" in capsys.readouterr().err


def test_apply_schema_runs_each_statement_separately(fake_pg):
    log, _ = fake_pg
    done = db.apply_schema(db._connect(), ROOT)
    sqls = [e[1] for e in log]
    assert any("create_hypertable('training_metrics'" in s for s in sqls)
    assert any("timescaledb.continuous" in s for s in sqls)
    assert any("add_continuous_aggregate_policy('metrics_1s'" in s for s in sqls)
    assert len(done) == len(sqls) and all(";" not in s for s in sqls)


def test_load_ref_inserts_tutorial_run_and_refreshes(fake_pg, tmp_path, capsys):
    log, _ = fake_pg
    csv = tmp_path / "ref.csv"
    csv.write_text("step,loss\n0,0.25\n100,0.1\n200,0.01\n", encoding="utf-8")
    args = argparse.Namespace(csv=str(csv), metric="loss", run_id="ref_t", lesson="pinn", step="s5",
                              note="from video", no_refresh=False)
    assert db.cmd_load_ref(args) == 0
    sql = [e for e in log if e[0] == "sql"]
    assert "'tutorial'" in sql[0][1] and sql[0][2][:3] == ("ref_t", "pinn", "s5")
    rows = [e[2] for e in log if e[0] == "row"]
    assert [(r[1], r[2], r[3], r[4]) for r in rows] == [("ref_t", 0, "loss", 0.25), ("ref_t", 100, "loss", 0.1),
                                                        ("ref_t", 200, "loss", 0.01)]
    assert rows[0][0] < rows[1][0] < rows[2][0]  # 1 s apart → separate metrics_1s buckets
    assert "refresh_continuous_aggregate('metrics_1s'" in sql[-1][1]
    assert "loaded 3 points" in capsys.readouterr().out


def test_apply_schema_includes_generality_aggregates(fake_pg):
    log, _ = fake_pg
    db.apply_schema(db._connect(), ROOT)
    sqls = " ".join(e[1] for e in log)
    for view in ("time_per_step", "check_fail_rate", "learner_progress"):
        assert f"MATERIALIZED VIEW IF NOT EXISTS {view}" in sqls
        assert f"add_continuous_aggregate_policy('{view}'" in sqls
    assert "ADD COLUMN IF NOT EXISTS session_id" in sqls


def test_tut_stats_prints_rate_and_latency(fake_pg, capsys):
    args = argparse.Namespace(watch=False, interval=1.0, runs=2, json=False)
    assert db.cmd_stats(args) == 0
    out = capsys.readouterr().out
    assert "rows/s" in out and "live_curve" in out and " ms" in out


# ---------------------------------------------------------------- no silent loss (QA audit)
from tut.main import report_losses  # noqa: E402


def test_db_down_reports_spool_not_loss(fake_pg, tmp_path, capsys):
    _, state = fake_pg
    state["fail_connect"] = True
    sink = TigerSink("postgres://fake/db", {"id": "r1", "command": "c", "started_at": None}, flush_every=0.05)
    _run(sink, n=4)
    report_losses("r1", None, sink)
    err = capsys.readouterr().err
    assert "4 metrics spooled to" in err and "WARNING" not in err


def test_connect_hang_past_deadline_spools_from_close(monkeypatch, tmp_path, capsys):
    import threading

    monkeypatch.setenv("TUT_SPOOL_DIR", str(tmp_path / "spool"))
    gate = threading.Event()

    def slow_connect(dsn, **kw):
        gate.wait(5)  # venue Wi-Fi silently drops the port
        raise OSError("timeout")

    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(connect=slow_connect))
    sink = TigerSink("postgres://fake/db", {"id": "r2", "command": "c", "started_at": None}, flush_every=0.05)
    sink.start()
    sink.metric(Metric(1, "loss", 0.5))
    sink.end(0, "t")
    sink.close(time.monotonic() + 0.7)
    report_losses("r2", None, sink)
    gate.set()
    err = capsys.readouterr().err
    assert sink.rows_spooled == 1 and not sink.still_writing
    assert "spooled to" in err and "NOT" not in err
    assert [ln["k"] for ln in _spooled(tmp_path)] == ["r", "m"]


def test_unspoolable_loss_is_loud(fake_pg, monkeypatch, capsys):
    _, state = fake_pg
    state["fail_connect"] = True
    monkeypatch.setenv("TUT_SPOOL_DIR", "/dev/null/cannot-create")
    sink = TigerSink("postgres://fake/db", {"id": "r4", "command": "c", "started_at": None}, flush_every=0.05)
    _run(sink, n=2)
    report_losses("r4", None, sink)
    err = capsys.readouterr().err
    assert "WARNING" in err and "2 of 2 metrics for run r4 were NOT stored" in err


def test_tut_stats_offline(fake_pg, tmp_path, capsys):
    _, state = fake_pg
    state["fail_connect"] = True
    (tmp_path / "spool").mkdir()
    (tmp_path / "spool" / "engine-x.jsonl").write_text('{"k":"m","v":[]}\n' * 7, encoding="utf-8")
    assert db.cmd_stats(argparse.Namespace(watch=False, interval=1.0, runs=1, json=False)) == 1
    assert "Tiger offline (connection refused), 7 rows spooled in" in capsys.readouterr().out


def test_no_warning_when_everything_stored(fake_pg, capsys):
    sink = TigerSink("postgres://fake/db", {"id": "r3", "command": "c", "started_at": None}, flush_every=0.05)
    _run(sink)
    report_losses("r3", None, sink)
    assert "WARNING" not in capsys.readouterr().err
