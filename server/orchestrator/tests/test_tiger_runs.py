"""Real runs' loss values -> Tiger Data (tiger_runs.py). Before: only `tut run` wrote training_metrics, so the judged
lesson's runs (VS Code's ▷ / its terminal, Run it for me) left /stats without a loss curve.
Offline: Tiger is a fake or unreachable here; nothing leaves the machine.
Run from the repo root:  python -m pytest server/orchestrator/tests/test_tiger_runs.py -q"""

from __future__ import annotations

import datetime as dt
import json
import time
from types import SimpleNamespace

import pytest

from server.checks import stats_web, tiger
from server.checks.tiger import TigerWriter, replay_spool
from server.orchestrator import curated, stage, tiger_runs
from server.orchestrator.context import RunInfo
from server.orchestrator.modules import Modules
from server.orchestrator.tests.test_stage import NN1_ZEROS, RANDOM, ZEROS, code, rig, run, save, settle  # noqa: F401

# nn.py's output (the lesson's own run, seed 0): a loss line every 2,000 epochs, then the weights.
NN_OUT = ["epoch     0  loss 0.8187", "epoch  2000  loss 0.0257", "epoch  4000  loss 0.0151", "epoch  6000  loss 0.0048",
          "epoch  8000  loss 0.0028", "epoch 10000  loss 0.0020", "epoch 12000  loss 0.0016", "epoch 14000  loss 0.0012",
          "epoch 16000  loss 0.0010", "epoch 18000  loss 0.0009", "W1 [[1.413, 0.396, 0.324, 1.825]]"]
LOSSES = [(0, 0.8187), (2000, 0.0257), (4000, 0.0151), (6000, 0.0048), (8000, 0.0028), (10000, 0.0020),
          (12000, 0.0016), (14000, 0.0012), (16000, 0.0010), (18000, 0.0009)]
LESSON = "lesson-nn-from-scratch"


class Recorded:
    """Stands in for Modules.record_run: what would be queued for Tiger."""

    def __init__(self) -> None:
        self.runs: list[dict] = []
        self.rows: list[tuple] = []  # (run_id, time, name, step, value)

    def __call__(self, run: dict, metrics: list[tuple]) -> bool:
        self.runs.append(run)
        self.rows += [(run["id"], *m) for m in metrics]
        return True

    def of(self, run_id: str) -> list[tuple]:
        return [r for r in self.rows if r[0] == run_id]


def command_end(rig, cid: int, lines: list[str], cmd: str | None = None) -> dict:
    """The companion's command_end for a run of nn.py in the lesson folder (what /vscode/event hands curated)."""
    started = int(time.time() * 1000)
    return {"type": "command_end", "seq": cid, "received": time.time(),
            "command": {"id": cid, "commandLine": cmd or f"/usr/bin/python3 {rig.s.workdir}/nn.py",
                        "cwd": str(rig.s.workdir), "startedAt": started, "exitCode": 0, "outputTail": lines}}


async def curated_lesson(rig) -> Recorded:
    await rig.s.learn("build a neural network", mode="lesson")
    await settle(rig)
    assert curated.active(rig.s) and not stage.on(rig.s)
    rec = Recorded()
    rig.s.m.record_run = rec
    return rec


@pytest.fixture(autouse=True)
def _no_adopt_wait(monkeypatch):
    monkeypatch.setattr(curated, "ADOPT_AFTER_S", 0.0)


# ------------------------------------------------------------------------------------------------- (a) VS Code's run

def test_vscode_command_end_writes_each_loss_line(rig):
    async def go():
        rec = await curated_lesson(rig)
        ev = command_end(rig, 7, NN_OUT)
        await curated.on_command_end(rig.s, ev)
        await settle(rig)
        rid = f"vscode-7-{ev['command']['startedAt']}"
        assert [r["id"] for r in rec.runs] == [rid]
        row = rec.runs[0]
        assert row["source"] == "learner" and row["lesson_id"] == LESSON and row["step_id"] == rig.s.step["id"]
        assert row["exit_code"] == 0 and row["command"].endswith("nn.py") and "epoch 18000" in row["tail"]
        rows = rec.of(rid)
        assert [(r[3], r[4]) for r in rows] == LOSSES and {r[2] for r in rows} == {"loss"}
        times = [r[1] for r in rows]
        # one metrics_1s bucket per printed epoch: 1 s apart, oldest first, the last one at the run's end
        assert all((b - a) >= dt.timedelta(seconds=1) for a, b in zip(times, times[1:]))
        assert len({t.replace(microsecond=0) for t in times}) == len(times)
        assert abs((dt.datetime.now(dt.timezone.utc) - times[-1]).total_seconds()) < 5
    run(go())


# ------------------------------------------------------------------------------------------ (b) one run, two paths

def test_one_run_seen_by_two_paths_is_written_once(rig):
    async def go():
        rec = await curated_lesson(rig)
        # the companion's command_end (curated) first, then the session's run check and Run it for me's wait reach it
        ev = command_end(rig, 8, NN_OUT)
        await curated.on_command_end(rig.s, ev)
        await settle(rig)
        rid = f"vscode-8-{ev['command']['startedAt']}"
        rig.s._ext_run(ev["command"])  # _need_run: the same run id, already ingested
        mx = [{"step": e, "name": "loss", "value": v} for e, v in LOSSES]  # _terminal_run_result's _metrics_in
        await rig.s.ingest({"kind": "run_started", "run_id": rid, "command": "python3 nn.py"})
        await rig.s.ingest({"kind": "metrics", "run_id": rid, "metrics": mx})
        await rig.s.ingest({"kind": "run_ended", "run_id": rid, "exit_code": 0})
        await settle(rig)
        assert [r["id"] for r in rec.runs] == [rid] and len(rec.of(rid)) == len(LOSSES)

        # the other order: the run check takes the command_end first, curated stands back
        ev = command_end(rig, 9, NN_OUT)
        rig.s._ext_run(ev["command"])
        await curated.on_command_end(rig.s, ev)
        await settle(rig)
        rid9 = f"vscode-9-{ev['command']['startedAt']}"
        assert [r["id"] for r in rec.runs] == [rid, rid9] and len(rec.of(rid9)) == len(LOSSES)

        # the screen's OCR of the same lines, and `tut run` in VS Code's terminal (tut writes its own run): not again
        n = len(rec.rows)
        for e, v in LOSSES:
            await rig.s.ingest({"kind": "metric", "run_id": f"screen-{LESSON}", "step": e, "name": "loss", "value": v,
                                "source": "screen"})
        await rig.s.ingest({"kind": "run_ended", "run_id": f"screen-{LESSON}", "exit_code": 0})
        await curated.on_command_end(rig.s, command_end(rig, 10, NN_OUT, cmd="tut run python3 nn.py"))
        await settle(rig)
        assert len(rec.rows) == n and len(rec.runs) == 2
    run(go())


def test_run_it_for_me_subprocess_run_is_written(rig):
    async def go():
        rec = await curated_lesson(rig)
        rid = "run-for-me-1731670000000"
        await rig.s.ingest({"kind": "run_started", "run_id": rid, "command": ".venv/bin/python nn.py"})
        await rig.s.ingest({"kind": "output", "run_id": rid, "lines": NN_OUT})
        await rig.s.ingest({"kind": "run_ended", "run_id": rid, "exit_code": 0})
        await settle(rig)
        assert rec.runs[0]["source"] == "learner" and [(r[3], r[4]) for r in rec.of(rid)] == LOSSES
    run(go())


# ----------------------------------------------------------------------------------------- (d) Demo recorded runs

def test_demo_recorded_runs_are_tagged_demo_never_learner(rig):
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        rec = Recorded()
        rig.s.m.record_run = rec
        await save(rig, NN1_ZEROS)
        await save(rig, code("nn2"))
        await save(rig, code("nn3"))
        assert rig.s.step["id"] == "nn4"
        await rig.s.action("run_command")  # the recorded stuck run
        await settle(rig)
        await save(rig, RANDOM)
        await rig.s.action("run_command")  # the recorded run that learns
        await settle(rig)
        assert len(rec.runs) == 2 and all(r["id"].startswith("stage-nn4-") for r in rec.runs)
        assert {r["source"] for r in rec.runs} == {"demo"}  # /stats labels these "Demo recording"
        stuck, good = (rec.of(r["id"]) for r in rec.runs)
        assert {r[4] for r in stuck} == {curated.STUCK_LOSS} and good[-1][4] < 0.01
    run(go())


# ------------------------------------------------------------------------------ (c) Tiger down + (e) what /stats reads

class Res:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeTiger:
    """Just enough Tiger for replay_spool's writes and /stats' reads of them. metrics_1s is emulated as the schema
    defines it: time_bucket('1 second', time), avg(value), max(step), per run and name."""

    def __init__(self) -> None:
        self.metrics: list[tuple] = []  # (time, run_id, step, name, value): COPY training_metrics' columns
        self.runs: dict[str, dict] = {}

    def cursor(self):
        conn = self

        class Copy:
            def __init__(self, sql):
                self.sql = sql

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def write_row(self, row):
                if "training_metrics" in self.sql:
                    conn.metrics.append(tuple(row))

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def copy(self, sql):
                assert sql == tiger.METRIC_COPY or "learning_events" in sql
                return Copy(sql)

        return Cur()

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        if s.startswith("INSERT INTO runs"):
            self.runs.setdefault(params["id"], dict(params))
            return Res([])
        if "count(" in s or "approximate_row_count" in s or "timescaledb_information.chunks" in s:
            return Res([(len(self.metrics),)])
        if s == " ".join(stats_web.SQL_CURRENT_RUN.split()):
            tutorial = {k for k, r in self.runs.items() if r.get("source") == "tutorial"}
            mine = sorted((m for m in self.metrics if m[1] not in tutorial), key=lambda m: m[0])
            return Res([(mine[-1][1],)] if mine else [])
        if s == stats_web.SQL_LESSON_OF_RUN:
            return Res([(self.runs[params[0]]["lesson_id"],)] if params[0] in self.runs else [])
        if s == stats_web.SQL_SOURCE_OF_RUN:
            return Res([(self.runs[params[0]]["source"],)] if params[0] in self.runs else [])
        if s == " ".join(stats_web.SQL_CURVE.split()):
            buckets: dict[tuple, list] = {}
            for t, rid, step, name, value in self.metrics:
                if rid == params[0]:
                    buckets.setdefault((t.replace(microsecond=0), name), []).append((step, value))
            return Res([(name, max(p[0] for p in pts), sum(p[1] for p in pts) / len(pts))
                        for (_, name), pts in sorted(buckets.items())])
        return Res([])  # the other panels: empty

    def close(self):
        pass


@pytest.fixture
def stats_db():
    yield stats_web.DB
    stats_web.DB.conn, stats_web.DB.down_until, stats_web.DB.last_error = None, 0.0, None
    stats_web.DB.connect = stats_web.DB._default_connect


def test_tiger_down_never_blocks_spools_and_stats_reads_the_curve(tmp_path, monkeypatch, stats_db):
    spool = tmp_path / "spool"
    monkeypatch.setenv("TUT_SPOOL_DIR", str(spool))

    def unreachable(dsn):  # this network: the connect hangs, then fails
        time.sleep(1.0)
        raise OSError("connection to server at tiger.example:37145 failed: timeout expired")

    w = TigerWriter(dsn="postgres://tsdbadmin:s3cret@tiger.example:37145/tsdb", session_id="sess_t",
                    flush_every=0.05, connect=unreachable, spool_dir=spool)
    monkeypatch.setattr(tiger, "_writer", w)
    m = Modules(demo=False, force_stubs="all")
    m.forced.discard("checks")  # Tiger recording on, as in the engine
    session = SimpleNamespace(m=m, graph={"lesson": {"id": LESSON}}, step={"id": "nn4"})

    learner = RunInfo(run_id="vscode-3-1731670000000", command="/usr/bin/python3 nn.py", exit_code=0,
                      started_t=time.time() - 4)
    learner.add_output(NN_OUT)
    t0 = time.perf_counter()
    assert tiger_runs.record(session, learner) == len(LOSSES)
    first = time.perf_counter() - t0
    time.sleep(0.2)  # the writer thread is now stuck connecting
    demo = RunInfo(run_id="stage-nn4-0-1731670000001", command="python3 nn.py", exit_code=0)
    demo.add_output(NN_OUT[:3])
    t0 = time.perf_counter()
    assert tiger_runs.record(session, demo) == 3
    second = time.perf_counter() - t0
    assert first < 0.1 and second < 0.1  # (c) a step never waits on Tiger
    assert tiger_runs.record(session, learner) == 0  # the same run again: nothing new
    w.flush(timeout=5)
    assert not w.online and "37145" in w.last_error and "s3cret" not in w.last_error
    lines = [json.loads(ln) for f in spool.glob("*.jsonl") for ln in f.read_text(encoding="utf-8").splitlines()]
    assert sum(o["k"] == "r" for o in lines) == 2 and sum(o["k"] == "m" for o in lines) == len(LOSSES) + 3
    assert w.rows_spooled == len(LOSSES) + 3 + 2 and w.dropped == 0

    # (e) the network comes back: the spool uploads, and /stats' own queries find the run and draw its curve
    fake = FakeTiger()
    assert replay_spool(fake, spool) == len(LOSSES) + 3 + 2
    assert not list(spool.glob("*.jsonl"))
    assert fake.runs[learner.run_id]["source"] == "learner" and fake.runs[learner.run_id]["lesson_id"] == LESSON
    stats_db.conn, stats_db.down_until = None, 0.0
    stats_db.connect = lambda: fake
    d = stats_web.collect(run_id=learner.run_id)
    assert d["online"] and d["run_id"] == learner.run_id and d["lesson_id"] == LESSON
    assert d["run_source"] == "learner" and d["curve"]["loss"] == [[e, v] for e, v in LOSSES]
    # the newest run is the Demo's recording: /stats says so (never "you")
    d = stats_web.collect()
    assert d["run_id"] == demo.run_id and d["run_source"] == "demo" and len(d["curve"]["loss"]) == 3
    assert '" (Demo recording)"' in stats_web.PAGE and "not a live run" in stats_web.PAGE


def test_spread_keeps_one_bucket_per_point():
    end = 1_731_670_000.25
    ts = tiger_runs.spread(10, end - 0.4, end)  # a 0.4 s run: still 10 buckets
    assert len({t.replace(microsecond=0) for t in ts}) == 10 and ts[-1].timestamp() == pytest.approx(end)
    ts = tiger_runs.spread(5, end - 40, end)  # a 40 s run: spread over its duration
    assert (ts[-1] - ts[0]).total_seconds() == pytest.approx(40, abs=1e-3)
    assert tiger_runs.spread(1, end, end)[0].timestamp() == pytest.approx(end) and tiger_runs.spread(0, end, end) == []
