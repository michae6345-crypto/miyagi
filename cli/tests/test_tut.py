import json
import math
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tut.db import read_curve_csv, split_sql
from tut.metrics import clean_line, parse_metric

FAKE_TRAIN = r"""
import time, sys
def log_metric(step, name, value): print(f'::metric:: {{"step": {step}, "name": "{name}", "value": {value}}}', flush=True)
print("\x1b[1mtraining\x1b[0m", flush=True)
for s in range(0, 40):
    log_metric(s * 100, "loss", 0.25 * 0.9 ** s)
    if s % 10 == 0: print(f"epoch {s}", file=sys.stderr, flush=True)
    time.sleep(0.02)
print("done", flush=True)
sys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
"""


# ---------------------------------------------------------------- parser
def test_parse_metric_contract_line():
    m = parse_metric('::metric:: {"step": 1200, "name": "grad_norm/layer3", "value": 1.3e-4}')
    assert (m.step, m.name, m.value) == (1200, "grad_norm/layer3", 1.3e-4)


def test_parse_metric_tolerates_common_slips():
    assert parse_metric('\x1b[32m::metric:: {"step": 5, "name": "loss", "value": 0.5}\x1b[0m').value == 0.5
    m = parse_metric('::metric:: {"step": 5, "name": "loss", "value": tensor(0.2504, grad_fn=<MseLossBackward0>)}')
    assert m.value == pytest.approx(0.2504)
    assert math.isnan(parse_metric('::metric:: {"step": 5, "name": "loss", "value": nan}').value)
    assert parse_metric("::metric:: {'step': 7, 'name': 'loss', 'value': 1e-3}").step == 7
    assert parse_metric("loss 0.25") is None
    assert parse_metric("::metric:: garbage") is None


def test_clean_line_progress_bar():
    assert clean_line("10%|#   \r50%|#####\r") == "50%|#####"


# ---------------------------------------------------------------- db helpers
def test_split_sql_on_contract_schema():
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    stmts = split_sql(open(os.path.join(root, "shared/contracts/tiger-schema.sql")).read())
    assert any(s.startswith("CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1s") for s in stmts)
    assert all(";" not in s for s in stmts)


def test_read_curve_csv_wide_and_long(tmp_path):
    w = tmp_path / "w.csv"
    w.write_text("epoch,loss,val_loss\n0,1.0,1.1\n100,0.5,0.6\n")
    rows = read_curve_csv(str(w), "loss")
    assert {(r[0], r[1]) for r in rows} == {(0, "loss"), (0, "val_loss"), (100, "loss"), (100, "val_loss")}
    lg = tmp_path / "l.csv"
    lg.write_text("step,value\n0,1.0\n10,0.5\n")
    assert [(r[0], r[1], r[2]) for r in read_curve_csv(str(lg), "loss")] == [(0, "loss", 1.0), (10, "loss", 0.5)]


# ---------------------------------------------------------------- end to end
class _Capture(BaseHTTPRequestHandler):
    posts: list = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).posts.append(json.loads(body))
        out = json.dumps({"ok": True, "step_id": "s5"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def engine():
    _Capture.posts = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Capture)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/ingest", _Capture.posts
    srv.shutdown()


def tut(*args, env_extra=None):
    env = dict(os.environ, TIGER_DATABASE_URL="", TUT_QUIET="1", **(env_extra or {}))
    return subprocess.run([sys.executable, "-m", "tut", *args], capture_output=True, env=env, timeout=60)


def test_run_streams_and_posts_to_ingest(engine):
    url, posts = engine
    p = tut("run", "--engine", url, sys.executable, "-c", FAKE_TRAIN, "3")
    assert p.returncode == 3  # exit code passes through
    out = p.stdout.decode()
    assert "\x1b[1mtraining\x1b[0m" in out  # colors untouched (child saw a tty)
    assert "epoch 10" in out  # stderr shares the pty
    assert out.count("::metric::") == 40  # passthrough untouched by default
    assert "\r\n" not in out
    events = [e for batch in posts for e in batch]
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "run_started" and kinds[-1] == "run_ended"
    assert events[-1]["exit_code"] == 3
    metrics = [e for e in events if e["kind"] == "metric"]
    assert [m["step"] for m in metrics] == [s * 100 for s in range(40)]
    lines = [ln for e in events if e["kind"] == "output" for ln in e["lines"]]
    assert "training" in lines and "done" in lines  # ANSI stripped
    assert len({e["run_id"] for e in events}) == 1
    assert len(posts) <= 15  # batched (~5/s), not one POST per line


NAN_TRAIN = r"""
for s in range(5): print(f'::metric:: {{"step": {s}, "name": "loss", "value": {0.5 / (s + 1)}}}', flush=True)
print('::metric:: {"step": 5, "name": "loss", "value": nan}', flush=True)
"""


def test_nan_metric_is_forwarded_as_null_nonfinite(engine):
    url, posts = engine
    p = tut("run", "--engine", url, sys.executable, "-c", NAN_TRAIN)
    assert p.returncode == 0
    metrics = [e for b in posts for e in b if e["kind"] == "metric"]
    assert len(metrics) == 6
    assert metrics[-1]["value"] is None and metrics[-1]["nonfinite"] == "nan" and metrics[-1]["step"] == 5


def test_run_survives_engine_down():
    p = tut("run", "--engine", "http://127.0.0.1:9/ingest", sys.executable, "-c", FAKE_TRAIN)
    assert p.returncode == 0
    assert b"done" in p.stdout
    assert p.stderr.count(b"engine not reachable") == 1  # warn once


def test_hide_metrics(engine):
    url, posts = engine
    p = tut("run", "--hide-metrics", "--engine", url, sys.executable, "-c", FAKE_TRAIN)
    assert b"::metric::" not in p.stdout and b"done" in p.stdout
    assert sum(1 for b in posts for e in b if e["kind"] == "metric") == 40


def test_command_not_found(engine):
    url, posts = engine
    p = tut("run", "--engine", url, "definitely-not-a-command-xyz")
    assert p.returncode == 127
    assert [e for b in posts for e in b][-1] == {"kind": "run_ended", "run_id": posts[0][0]["run_id"], "exit_code": 127}
