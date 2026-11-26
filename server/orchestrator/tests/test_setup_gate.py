"""The setup gate (user test Nov 25): the lesson waits while its environment installs; a check-less step that asks the
learner to act holds the video at its end instead of passing itself."""

from __future__ import annotations

import asyncio
import threading

import pytest

from server.orchestrator import setup_gate as G
from server.orchestrator import stubs
from server.orchestrator.tests.test_session import Rig, run


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


# --------------------------------------------------------------------------- the state machine


def test_idle_gate_never_holds():
    g = G.SetupGate(Clock())
    assert g.phase == "idle" and not g.holds and g.payload()["items"] == []


def test_install_all_runs_holds_and_releases_when_everything_settles():
    c = Clock()
    g = G.SetupGate(c, wall=lambda: 1_700_000_000.0)
    for t in ("numpy", "tensorflow", "matplotlib", "tensorflow-metal"):
        g.queue(t, t, optional=t == "tensorflow-metal")
    assert g.phase == "running" and g.holds
    g.start("numpy")
    g.finish("numpy", {"ok": True})
    g.start("tensorflow")
    g.progress("tensorflow", {"phase": "downloading", "pct": 41, "bytes": 92, "totalBytes": 224})
    c.t += 75
    p = g.payload()
    assert p["done"] == 1 and p["total"] == 4 and p["current"] == "tensorflow" and p["elapsedS"] == 75
    row = next(r for r in p["items"] if r["tool"] == "tensorflow")
    assert row["status"] == "installing" and row["pct"] == 41 and row["elapsedS"] == 75
    assert p["startedAt"] == 1_700_000_000_000
    g.progress("tensorflow", {"phase": "installing"})  # the bar goes with its phase
    assert "pct" not in next(r for r in g.payload()["items"] if r["tool"] == "tensorflow")
    g.finish("tensorflow", {"ok": True})
    g.start("matplotlib")
    g.finish("matplotlib", {"ok": True})
    assert not g.holds  # only an optional row left in line
    g.finish("tensorflow-metal", {"ok": True, "skipped": True, "errorCode": "skipped_incompatible"})
    assert g.phase == "done" and not g.holds and g.payload()["done"] == 4


def test_a_required_failure_holds_until_retry_or_continue():
    g = G.SetupGate(Clock())
    g.start("tensorflow", "TensorFlow")
    g.finish("tensorflow", {"ok": False, "error": "The download of tensorflow kept stalling.", "errorCode": "timeout",
                            "log": "Read timed out"})
    assert g.phase == "failed" and g.holds
    row = g.payload()["items"][0]
    assert row["status"] == "failed" and row["errorCode"] == "timeout" and row["log"] == "Read timed out"
    assert g.retry() == ["tensorflow"] and g.phase == "running" and g.payload()["items"][0]["status"] == "queued"
    g.start("tensorflow")
    g.finish("tensorflow", {"ok": False, "error": "x"})
    g.continue_anyway()
    assert g.phase == "done" and not g.holds
    g.queue("numpy")  # a new round of installs: the gate holds again
    assert g.holds


def test_optional_rows_skip_and_never_hold_on_failure():
    g = G.SetupGate(Clock())
    g.start("tensorflow-metal", optional=True)
    assert not g.holds  # optional only
    assert not G.SetupGate(Clock()).skip("nothing")
    g.queue("numpy")
    assert g.holds
    assert not g.skip("numpy")  # required rows can't be skipped one by one (Continue anyway covers them)
    assert g.skip("tensorflow-metal") and g.payload()["items"][0]["status"] == "skipped"
    g.finish("tensorflow-metal", {"ok": False, "cancelled": True, "errorCode": "cancelled"})
    assert g.rows["tensorflow-metal"].status == "skipped"  # the cancelled install's result keeps it skipped


def test_call_install_passes_extras_only_when_taken():
    seen = {}

    def old(item, folder, on_line):
        return {"ok": True}

    def new(item, folder, on_line, on_progress=None, cancel=None):
        seen.update(progress=on_progress, cancel=cancel)
        return {"ok": True}

    ev = threading.Event()
    assert G.call_install(old, {}, "/x", print, on_progress=print, cancel=ev) == {"ok": True}
    G.call_install(new, {}, "/x", print, on_progress=print, cancel=ev)
    assert seen == {"progress": print, "cancel": ev}


# --------------------------------------------------------------------------- in a session


def _reqs(state):
    def reqs(graph, folder):
        return [{"tool": t, "label": t, "kind": "python_package", "why": "lesson", "needed": True,
                 "installed": state.get(t, False), "ok": state.get(t, False),
                 "install": {"method": "pip", "command": f"pip install {t}", "url": None}}
                for t in ("numpy", "tensorflow")]
    return reqs


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator import workspace as wsmod
    from server.orchestrator.workspace import Workspace
    from server.workspace import setup_card

    state: dict = {"fail": set()}
    monkeypatch.setattr(wsmod, "requirements", _reqs(state))
    monkeypatch.setattr(wsmod, "setup_card", setup_card)

    def fake_install(item, folder, on_line, on_progress=None, cancel=None):
        t = item["tool"]
        on_line(f"Collecting {t}")
        if on_progress:
            on_progress({"phase": "downloading", "pct": 50})
        if t in state["fail"]:
            return {"ok": False, "tool": t, "error": "The download stalled.", "errorCode": "timeout", "log": "Read timed out"}
        state[t] = True
        return {"ok": True, "tool": t, "version": "1.0"}

    monkeypatch.setattr(wsmod, "install", fake_install)
    r = Rig(tmp_path)
    r.s.workspace = Workspace(enabled=True, runner=lambda argv: True)
    r.state = state
    return r


def test_install_all_holds_the_lesson_and_releases_it(rig):
    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        m = rig.mark()
        await rig.s.action("install_all")
        await asyncio.sleep(0.1)
        await rig.settle()
        return rig.since(m)

    after = run(go())
    gates = [e["payload"] for e in after if e["type"] == "setup.gate"]
    assert gates[0]["holds"] and gates[0]["phase"] == "running" and gates[0]["total"] == 2 and gates[0]["done"] == 0
    types_ = [e["type"] for e in after]
    assert "video.pause" in types_[types_.index("setup.gate"):]  # the video stops as the gate engages
    assert any(g.get("current") == "tensorflow" for g in gates)
    assert gates[-1]["phase"] == "done" and not gates[-1]["holds"] and gates[-1]["done"] == 2


def test_a_failed_install_holds_until_continue_anyway(rig):
    rig.state["fail"].add("tensorflow")

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.s.action("install_all")
        await asyncio.sleep(0.1)
        await rig.settle()
        failed = rig.of("setup.gate")[-1]
        seg_end = rig.s._segment(rig.s.step)["end"]
        await rig.s.video_state(seg_end, True)  # the wall clock / a stray report: the held step doesn't end
        await rig.settle()
        held_done = rig.s.segment_done
        await rig.s.action("setup_continue")
        await rig.settle()
        return failed, held_done, rig.of("setup.gate")[-1]

    failed, held_done, after = run(go())
    assert failed["phase"] == "failed" and failed["holds"]
    row = next(r for r in failed["items"] if r["tool"] == "tensorflow")
    assert row["status"] == "failed" and row["errorCode"] == "timeout" and row["log"] == "Read timed out"
    assert held_done is False
    assert after["phase"] == "done" and not after["holds"]


def test_retry_installs_the_failed_row_again(rig):
    rig.state["fail"].add("tensorflow")

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.s.action("install", "tensorflow")
        await asyncio.sleep(0.05)
        await rig.settle()
        rig.state["fail"].clear()
        await rig.s.action("setup_retry", "tensorflow")
        await asyncio.sleep(0.05)
        await rig.settle()
        return rig.of("setup.gate")

    gates = run(go())
    assert any(g["phase"] == "failed" for g in gates)
    assert gates[-1]["phase"] == "done" and not gates[-1]["holds"]


def test_a_preflight_install_is_not_gated(rig):
    assert not G.applies(rig.s)  # no lesson yet: the preflight card's own progress, no gate


# --------------------------------------------------------------------------- pause at action steps


def _lesson(kind: str | None, *, checks: bool):
    g = stubs.load_fixture_lesson()
    st = g["steps"][0]
    if not checks:
        st["checks"], st["precision_checks"] = [], []
    if kind:
        st["kind"] = kind
    return g


@pytest.mark.parametrize("kind,passes", [("code", False), ("run", False), ("read", True)])
def test_a_checkless_step_that_asks_for_work_waits_at_its_end(tmp_path, kind, passes):
    r = Rig(tmp_path)

    async def go():
        await r.s.load_graph(_lesson(kind, checks=False))
        await r.settle()
        m = r.mark()
        await r.end_segment()
        await asyncio.sleep(0.05)
        await r.settle()
        return [e["type"] for e in r.since(m)]

    types_ = run(go())
    assert ("step.passed" in types_) is passes
    if not passes:
        assert "video.pause" in types_ and r.s.segment_done


# --------------------------------------------------------------------------- review fixes (H1-H3, M2)


def test_continue_without_it_survives_the_next_queued_row():
    g = G.SetupGate(Clock())
    g.queue("tensorflow")
    g.queue("matplotlib")
    g.start("tensorflow")
    g.continue_anyway()  # "Continue without it" after a minute
    g.finish("tensorflow", {"ok": True})
    g.start("matplotlib")  # Install all goes on: the lesson doesn't stop again
    assert not g.holds
    g.finish("matplotlib", {"ok": True})
    g.start("numpy")  # a new Install press is a new round
    assert g.holds


def test_retry_runs_beside_the_command_queue(rig, monkeypatch):
    from server.orchestrator import workspace as wsmod

    go_on = threading.Event()

    def slow_install(item, folder, on_line, on_progress=None, cancel=None):
        go_on.wait(5)
        return {"ok": True, "tool": item["tool"], "version": "2.21.0"}

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        G.gate(rig.s).start("tensorflow", "tensorflow")
        G.gate(rig.s).finish("tensorflow", {"ok": False, "error": "x"})
        monkeypatch.setattr(wsmod, "install", slow_install)
        await asyncio.wait_for(rig.s.action("setup_retry"), 1.0)  # returns at once: the install is a task (H1)
        await asyncio.sleep(0.05)
        installing = G.gate(rig.s).rows["tensorflow"].status
        await asyncio.wait_for(rig.s.action("setup_continue"), 1.0)  # Continue still gets through meanwhile
        released = not G.gate(rig.s).holds
        go_on.set()
        await asyncio.sleep(0.1)
        await rig.settle()
        return installing, released, G.gate(rig.s).rows["tensorflow"].status

    installing, released, final = run(go())
    assert installing == "installing" and released and final == "done"


def test_retry_rebuilds_a_failed_python_environment_and_settles_strays(rig, tmp_path):
    from server.workspace import paths

    folder = tmp_path / "lesson"
    folder.mkdir()

    def broken():
        return False  # ensure_lesson_venv never raises; no .venv after it = failed

    def works():
        vpy = paths.venv_python(folder / ".venv")
        vpy.parent.mkdir(parents=True, exist_ok=True)
        vpy.write_text("", encoding="utf-8")
        return True

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await G.run_venv(rig.s, str(folder), broken)
        failed = G.gate(rig.s).payload()
        rig.s._venv_job = (str(folder), works)
        G.gate(rig.s).queue("ghost")  # a row nothing will install (an early return)
        G.gate(rig.s).finish("ghost", {"ok": False, "error": "x"})
        await rig.s.action("setup_retry")
        await asyncio.sleep(0.1)
        await rig.settle()
        return failed, G.gate(rig.s).payload()

    failed, after = run(go())
    assert failed["phase"] == "failed" and failed["items"][0]["tool"] == "venv"
    rows = {r["tool"]: r["status"] for r in after["items"]}
    assert rows["venv"] == "done" and rows["ghost"] in ("skipped", "failed") and after["phase"] != "running"
    assert not after["holds"] or after["phase"] == "failed"


def test_a_live_gate_follows_lesson_ready_and_every_reconnect(rig):
    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        idle = rig.s.snapshot()
        G.gate(rig.s).start("tensorflow", "tensorflow")  # mid-install
        return idle, rig.s.snapshot()

    idle, busy = run(go())
    assert "setup.gate" not in [t for t, _ in idle]  # nothing installing: the connect burst is unchanged
    kinds = [t for t, _ in busy]
    assert kinds[kinds.index("lesson.ready") + 1] == "setup.gate"  # the app clears on lesson.ready, then gets it back
    gp = dict(busy)["setup.gate"]
    assert gp["phase"] == "running" and gp["holds"] and gp["current"] == "tensorflow"


def test_can_i_move_on_passes_a_held_checkless_step_without_the_judge(tmp_path):
    r = Rig(tmp_path)

    async def go():
        await r.s.load_graph(_lesson("code", checks=False))
        await r.settle()
        await r.end_segment()
        await r.settle()
        assert not r.of("step.passed")
        m = r.mark()
        await r.s.action("check_step")
        await r.settle()
        return [e["type"] for e in r.since(m)]

    assert "step.passed" in run(go())


# --------------------------------------------------------------------------- the notebook kernel (user test Nov 26)


def test_a_notebook_kernel_that_cant_start_is_a_failed_gate_row_until_retry(rig, monkeypatch):
    from server.orchestrator import lesson_notebook
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(lesson_notebook, "name", lambda s: "mnist.ipynb")
    base = _reqs(rig.state)

    def reqs(graph, folder):
        return [{**base(graph, folder)[0], "tool": "ipykernel", "label": "Jupyter kernel (ipykernel)",
                 "installed": rig.state.get("ipykernel", False), "ok": rig.state.get("ipykernel", False)}]
    monkeypatch.setattr(wsmod, "requirements", reqs)
    probes = []
    answers = [{"ok": False, "errorCode": "missing", "error": "The notebook kernel can't start: zmq isn't installed in "
                "the lesson's .venv. Press Retry to install the Jupyter kernel (ipykernel)."}, {"ok": True, "version": "7"}]
    monkeypatch.setattr(G, "kernel_probe", lambda folder: probes.append(folder) or answers[len(probes) - 1])

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.s.action("install", "ipykernel")
        await asyncio.sleep(0.05)
        await rig.settle()
        failed = G.gate(rig.s).payload()
        await rig.s.action("setup_retry", G.KERNEL)
        await asyncio.sleep(0.1)
        await rig.settle()
        return failed, G.gate(rig.s).payload()

    failed, after = run(go())
    row = next(r for r in failed["items"] if r["tool"] == G.KERNEL)
    assert failed["phase"] == "failed" and failed["holds"]
    assert row["label"] == "Notebook kernel" and row["status"] == "failed" and "zmq" in row["error"]
    assert next(r for r in after["items"] if r["tool"] == G.KERNEL)["status"] == "done"
    assert after["phase"] == "done" and not after["holds"] and len(probes) == 2


def test_no_kernel_row_outside_a_vs_code_notebook_lesson(rig, monkeypatch):
    monkeypatch.setattr(G, "kernel_probe", lambda folder: (_ for _ in ()).throw(AssertionError("probed")))

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        return await G.check_kernel(rig.s)

    assert run(go()) is None and G.KERNEL not in G.gate(rig.s).rows


def _nb_rig(rig, monkeypatch, tools=("ipykernel",)):
    from server.orchestrator import lesson_notebook
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(lesson_notebook, "name", lambda s: "mnist.ipynb")
    base = _reqs(rig.state)

    def reqs(graph, folder):
        return [{**base(graph, folder)[0], "tool": t, "label": t, "installed": rig.state.get(t, False),
                 "ok": rig.state.get(t, False)} for t in tools]
    monkeypatch.setattr(wsmod, "requirements", reqs)


def test_retry_on_a_broken_kernel_force_reinstalls_ipykernel_and_pyzmq(rig, monkeypatch):
    _nb_rig(rig, monkeypatch)
    probes, repairs = [], []
    answers = [{"ok": False, "errorCode": "broken_import", "error": "The notebook kernel can't start in the lesson's "
                ".venv: ImportError: dlopen(libzmq). Press Retry."}, {"ok": True}]
    monkeypatch.setattr(G, "kernel_probe", lambda folder: probes.append(folder) or answers[len(probes) - 1])
    monkeypatch.setattr(G, "kernel_repair", lambda folder, on_line, cancel: repairs.append(folder) or {"ok": True})

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.s.action("install", "ipykernel")
        await asyncio.sleep(0.05)
        await rig.settle()
        failed = G.gate(rig.s).payload()
        await rig.s.action("setup_retry", G.KERNEL)
        await asyncio.sleep(0.1)
        await rig.settle()
        return failed, G.gate(rig.s).payload()

    failed, after = run(go())
    assert next(r for r in failed["items"] if r["tool"] == G.KERNEL)["errorCode"] == "broken_import"
    assert len(repairs) == 1 and len(probes) == 2
    assert after["phase"] == "done" and not after["holds"]


def test_install_all_goes_on_to_tensorflow_while_the_kernel_loads(rig, monkeypatch):
    _nb_rig(rig, monkeypatch, tools=("ipykernel", "tensorflow"))
    tf_started = threading.Event()
    from server.orchestrator import workspace as wsmod

    inner = wsmod.install

    def install(item, folder, on_line, on_progress=None, cancel=None):
        if item["tool"] == "tensorflow":
            tf_started.set()
        return inner(item, folder, on_line, on_progress=on_progress, cancel=cancel)
    monkeypatch.setattr(wsmod, "install", install)
    # the kernel check only answers once TensorFlow's install has begun: an inline check would wait 2 s and fail
    monkeypatch.setattr(G, "kernel_probe", lambda folder: {"ok": tf_started.wait(2.0)})

    async def go():
        await rig.start_lesson()
        await asyncio.sleep(0.05)
        await rig.s.action("install_all")
        await asyncio.sleep(0.1)
        await rig.settle()
        return G.gate(rig.s).payload()

    after = run(go())
    assert {r["tool"]: r["status"] for r in after["items"]} == {"ipykernel": "done", "tensorflow": "done", G.KERNEL: "done"}
    assert after["phase"] == "done"
