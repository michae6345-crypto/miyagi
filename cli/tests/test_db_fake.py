"""DB layer against a fake psycopg (no Postgres needed)."""
import argparse
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
        return FakeResult(("2.17.0",) if "extversion" in sql else None)

    def cursor(self):
        return FakeCursor(self.log)


@pytest.fixture
def fake_pg(monkeypatch):
    log: list = []
    state = {"fail_connect": False, "fail_on": None, "dsn": None}

    def connect(dsn, **kw):
        state["dsn"] = dsn
        if state["fail_connect"]:
            raise OSError("connection refused")
        return FakeConn(log, state["fail_on"])

    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(connect=connect))
    monkeypatch.setenv("TIGER_DATABASE_URL", "postgres://fake/db")
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


def test_tiger_sink_db_down_warns_once_and_drops(fake_pg, capsys):
    _, state = fake_pg
    state["fail_connect"] = True
    sink = TigerSink("postgres://fake/db", {"id": "r", "command": "c", "started_at": None}, flush_every=0.05)
    _run(sink)
    assert sink.dead and not sink.ok
    assert capsys.readouterr().err.count("Tiger Data unreachable") == 1
    sink.metric(Metric(1, "loss", 1.0))
    assert sink.q.qsize() <= 3  # no unbounded growth once dead


def test_tiger_sink_write_error_degrades(fake_pg, capsys):
    _, state = fake_pg
    state["fail_on"] = "INSERT INTO runs"
    sink = TigerSink("postgres://fake/db", {"id": "r", "command": "c", "started_at": None}, flush_every=0.05)
    _run(sink)
    assert sink.dead
    assert "Tiger Data write failed" in capsys.readouterr().err


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
    csv.write_text("step,loss\n0,0.25\n100,0.1\n200,0.01\n")
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
