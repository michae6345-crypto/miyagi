"""/stats page + /stats/data against a fake Tiger connection (no Postgres needed)."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.checks import stats_web
from server.checks.stats_web import DB, OPEN_STATS_LINK, router


class Res:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeTiger:
    """Answers the page's queries with canned rows; records what was asked."""

    def __init__(self):
        self.sql = []
        self.closed = False

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        s = " ".join(sql.split())
        if "FROM training_metrics WHERE time > now() - interval '1 day'" in s:
            return Res([("screen-pinn",)])
        if s.startswith("SELECT lesson_id FROM runs WHERE id"):
            return Res([])  # screen run: no runs row → lesson from the screen- prefix
        if "FROM metrics_1s WHERE run_id = %s AND bucket" in s:
            return Res([("loss", 100, 0.25), ("loss", 200, 0.2504), ("loss", 300, float("nan")), ("acc", 100, 0.5)])
        if "SELECT lesson_id, step_id FROM runs" in s:
            return Res([])
        if "FROM runs WHERE source = 'tutorial'" in s:
            return Res([("ref_pinn_s4",)] if params["lesson"] == "pinn" else [])
        if "FROM metrics_1s WHERE run_id = %s ORDER BY step" in s:
            return Res([("loss", 100, 0.2), ("loss", 200, 0.05)])
        if "FROM time_per_step" in s:
            return Res([("s1", 3, 41.5, 20.0, 70.0), ("s4", 1, 182.0, 182.0, 182.0)])
        if "FROM check_fail_rate" in s:
            return Res([("s4", "s4c2", 6, 1, 7, 6 / 7)])
        if "SELECT source_id FROM learning_events" in s:
            return Res([("yt:abc",)])
        if "FROM stuck_heatmap" in s:
            assert params == {"source": "yt:abc"}
            return Res([(210.0, 9), (225.0, 2)])
        if "interval '10 seconds'" in s:
            return Res([(20,)])
        if "approximate_row_count" in s:
            return Res([(12345,)])
        if "timescaledb_information.chunks" in s:
            return Res([(4,)])
        return Res([])

    def close(self):
        self.closed = True


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("TUT_SPOOL_DIR", str(tmp_path / "spool"))
    DB.conn, DB.down_until, DB.last_error = None, 0.0, None
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    DB.conn, DB.down_until = None, 0.0
    DB.connect = DB._default_connect


def test_page_is_html_with_chart_and_2s_refresh(client):
    r = client.get("/stats")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" in html
    assert "setTimeout(tick,2000)" in html and "/stats/data" in html
    assert "Tiger offline: " in html and "rows spooled, will upload on reconnect" in html
    assert "innerHTML" not in html  # learner-controlled ids are rendered with textContent only


def test_data_from_continuous_aggregates(client):
    fake = FakeTiger()
    DB.connect = lambda: fake
    d = client.get("/stats/data").json()
    assert d["online"] and d["run_id"] == "screen-pinn" and d["lesson_id"] == "pinn"
    assert d["curve"]["loss"] == [[100, 0.25], [200, 0.2504], [300, None]]  # NaN → null, never invented
    assert d["reference"] == {"run_id": "ref_pinn_s4", "curve": {"loss": [[100, 0.2], [200, 0.05]]}}
    assert d["time_per_step"][1] == {"step_id": "s4", "passes": 1, "avg_s": 182.0, "min_s": 182.0, "max_s": 182.0}
    assert d["check_fail_rate"][0]["check_id"] == "s4c2" and d["check_fail_rate"][0]["fail_rate"] == pytest.approx(6 / 7)
    assert d["stuck"] == [{"video_t": 210.0, "stuck": 9}, {"video_t": 225.0, "stuck": 2}]
    assert d["ingest"] == {"rows_per_s": 4.0, "metrics_total": 12345, "events_total": 12345, "chunks": 4}
    assert set(d["timings_ms"]) >= {"curve (metrics_1s)", "time_per_step", "check_fail_rate", "stuck_heatmap"}
    asked = " ".join(s for s, _ in fake.sql)
    for view in ("metrics_1s", "time_per_step", "check_fail_rate", "stuck_heatmap"):
        assert view in asked
    json.dumps(d, allow_nan=False)  # valid strict JSON


def test_explicit_run_and_lesson_params(client):
    fake = FakeTiger()
    DB.connect = lambda: fake
    d = client.get("/stats/data", params={"run_id": "run_x", "lesson_id": "react"}).json()
    assert d["run_id"] == "run_x" and d["lesson_id"] == "react" and d["reference"] is None  # no other lesson's curve


def test_offline_shows_spool_and_no_numbers(client, tmp_path):
    (tmp_path / "spool").mkdir()
    (tmp_path / "spool" / "engine-x.jsonl").write_text('{"k":"m","v":[]}\n' * 42)
    calls = []

    def down():
        calls.append(1)
        raise ConnectionError("connection to server at h:37145 failed: timeout")

    DB.connect = down
    d = client.get("/stats/data").json()
    assert d == {"online": False, "error": "connection to server at h:37145 failed: timeout",
                 "spool": {"dir": str(tmp_path / "spool"), "files": 1, "rows": 42}}
    client.get("/stats/data")
    assert len(calls) == 1  # back-off: no reconnect storm every 2 s


def test_lost_connection_mid_query_goes_offline(client):
    class Dies(FakeTiger):
        def execute(self, sql, params=None):
            if "time_per_step" in sql:
                raise RuntimeError("SSL SYSCALL error: EOF detected")
            return super().execute(sql, params)

    fake = Dies()
    DB.connect = lambda: fake
    d = client.get("/stats/data").json()
    assert d["online"] is False and "EOF" in d["error"] and fake.closed
    assert "curve" not in d  # partial numbers are not shown


def test_no_url_is_offline(client, monkeypatch):
    monkeypatch.setenv("TIGER_DATABASE_URL", "")
    monkeypatch.setattr(stats_web, "CONNECT_TIMEOUT_S", 1)
    monkeypatch.setattr("server.checks.tiger.load_env", lambda: None)
    d = client.get("/stats/data").json()
    assert d["online"] is False and "TIGER_DATABASE_URL" in d["error"]


def test_open_stats_link():
    assert OPEN_STATS_LINK == '<a href="http://localhost:8787/stats" target="_blank" rel="noopener">Open stats</a>'


