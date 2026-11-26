"""Check again never answers a blind "Not yet" (Nov 25, a real learner on a MacBook Neo: six presses, six identical
judge calls, the same "Not yet" each time, no reason). A manual Check runs a self-check (check_health.py: screen
frames, OCR text, the VS Code extension, the cloud's free /healthz) and answers with the reason, or "Couldn't check"
with the next action when it had nothing to look at. No model is ever called here.
Run: python -m pytest server/orchestrator/tests/test_check_again.py"""

from __future__ import annotations

import asyncio

import pytest

from server.orchestrator import check_health
from server.orchestrator.tests.test_check_verdicts import DICE, DICE_BROKEN, _rig, _save
from server.orchestrator.tests.test_session import run

_REAL_ROUTE = check_health._cloud_route


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No cloud and no VS Code scan in these tests, whatever this Mac has running."""
    monkeypatch.setattr(check_health, "_cloud_route", lambda: (None, "off"))
    monkeypatch.setattr(check_health, "vscode_windows", lambda: [])


def _check_cards(rig) -> list[dict]:
    return [c for c in rig.of("card") if c.get("checkedAt")]


def test_screen_recording_off_and_no_file_says_couldnt_check_and_never_judges(tmp_path, monkeypatch):
    """Nothing to look at (Screen Recording off, the step's file not written yet): "Can't see your screen" with the
    fix, a blocking checkIssue, never "Not yet", and no judge call (it would see nothing new)."""
    judged = []

    async def judge(step, screen=None, files=None, **kw):
        judged.append(step["id"])
        return None

    rig, screen = _rig(tmp_path, monkeypatch, judge=judge)

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        screen.down = "no_permission"
        screen.text = {}
        await rig.s.action("check_step")
        await rig.settle()

    run(go())
    card = _check_cards(rig)[-1]
    assert card["title"] == "Can't see your screen"
    assert card["checkIssue"]["kind"] == "screen_off" and card["checkIssue"]["blocking"] is True
    assert "Screen Recording" in card["body"] and "press Check again" in card["body"]
    assert card["checkIssue"]["selfCheck"]["screen"] == "off"
    assert "check_step" in card["actions"] and "hint" in card["actions"]
    assert not [c for c in rig.of("card") if c["title"] == "Not yet"]
    assert judged == []
    assert rig.s.last_self_check["screen"] == "off"
    assert rig.of("status")[-1]["state"] != "thinking"  # the check ended: no spinner left


def test_screen_off_with_the_file_on_disk_is_a_not_yet_with_the_reason_and_the_caveat(tmp_path, monkeypatch):
    """The file stands in for the screen: "Not yet" with what's missing (from the rows), plus why it may be partial."""
    rig, screen = _rig(tmp_path, monkeypatch)

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        await _save(rig, screen, "main.py", DICE_BROKEN)
        screen.down = "no_permission"
        await rig.s.action("check_step")
        await rig.settle()

    run(go())
    card = [c for c in rig.of("card") if c["title"] == "Not yet"][-1]
    assert card["verdict"] == "not_done" and card["checkedAt"] > 0
    assert "invalid syntax" in card["body"]  # the specific reason
    assert "I checked main.py on disk only" in card["body"]
    assert card["checkIssue"]["kind"] == "screen_off" and card["checkIssue"]["blocking"] is False


def test_checks_that_raise_say_couldnt_run_the_checks(tmp_path, monkeypatch):
    """evaluate_gate raising used to send one error per step and then a stale "Not yet" on every later press."""
    rig, screen = _rig(tmp_path, monkeypatch)

    async def boom(*a, **kw):
        raise RuntimeError("checker crashed")

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        await _save(rig, screen, "main.py", DICE_BROKEN)
        rig.s._gate_off_loop = boom
        for _ in range(2):  # every press answers, not only the first
            await rig.s.action("check_step")
            await rig.settle()

    run(go())
    cards = [c for c in _check_cards(rig) if c["title"] == "Couldn't run the checks"]
    assert len(cards) == 2
    assert cards[-1]["checkIssue"]["kind"] == "check_failed" and cards[-1]["checkIssue"]["blocking"] is True


def test_a_cloud_failure_is_named_on_the_not_yet(tmp_path, monkeypatch):
    """The judge couldn't reach miyagi cloud: the rows still say what's missing, and the card says the judge didn't run."""
    rig, screen = _rig(tmp_path, monkeypatch)
    rig.s.m.last_judge_error = lambda: {"kind": "connection", "message": "judge: connection error"}

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        await _save(rig, screen, "main.py", DICE_BROKEN)
        await rig.s.action("check_step")
        await rig.settle()

    run(go())
    card = [c for c in rig.of("card") if c["title"] == "Not yet"][-1]
    assert card["checkIssue"]["kind"] == "cloud_unreachable"
    assert "Only the automatic checks ran" in card["body"]


def test_a_healthy_check_has_no_issue_and_still_passes(tmp_path, monkeypatch):
    rig, screen = _rig(tmp_path, monkeypatch)
    monkeypatch.setattr(check_health, "vscode_windows", lambda: [{"app": "vscode", "port": 8791}])

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        await _save(rig, screen, "main.py", DICE_BROKEN)
        await rig.s.action("check_step")
        await rig.settle()
        card = [c for c in rig.of("card") if c["title"] == "Not yet"][-1]
        assert "checkIssue" not in card and card["verdict"] == "not_done"
        assert rig.s.last_self_check["screen"] == "ok" and rig.s.last_self_check["ocr"] == "ok"
        await _save(rig, screen, "main.py", DICE)

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"


# ------------------------------------------------------------------ check_health alone

def test_issue_for_orders_the_reasons():
    rep = {"screen": "ok", "ocr": "ok", "vscode": "connected", "cloud": "ok"}
    assert check_health.issue_for(rep, has_files=True) is None
    assert check_health.issue_for(rep, has_files=True, eval_error="x")["kind"] == "check_failed"
    off = {**rep, "screen": "off"}
    assert check_health.issue_for(off, has_files=False, eval_error=None)["blocking"] is True
    assert check_health.issue_for(off, has_files=True, file="nn.py")["body"].endswith("I checked nn.py on disk only.")
    assert check_health.issue_for({**rep, "ocr": "empty"}, has_files=False)["blocking"] is False  # a note alone
    assert check_health.issue_for({**rep, "screen": "stale"}, has_files=False)["blocking"] is True
    quota = check_health.issue_for(rep, has_files=True, judge_error={"kind": "cloud", "message": "miyagi_quota: ..."})
    assert quota["kind"] == "cloud_auth" and "free checks" in quota["body"]
    assert check_health.explains_blank(check_health.issue_for(rep, has_files=True, judge_error={"kind": "connection"}))
    assert not check_health.explains_blank(check_health.issue_for({**rep, "ocr": "empty"}, has_files=True))
    ext = check_health.issue_for({**rep, "vscode": "not_connected"}, has_files=True, file="nn.py", lesson_mode=True)
    assert ext["kind"] == "vscode_ext" and "nn.py" in ext["body"]
    assert check_health.issue_for({**rep, "vscode": "not_connected"}, has_files=True, exact=True, lesson_mode=True) is None


def test_cloud_probe_hits_healthz_once_a_minute_never_a_model(monkeypatch):
    """The reachability check is GET <origin>/healthz (free), cached CLOUD_TTL_S."""
    got: list[str] = []

    class Resp:
        status_code = 200

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            got.append(url)
            return Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setattr(check_health, "_cloud_route", lambda: ("https://cloud.example/v1/anthropic", "ok"))
    monkeypatch.setattr(check_health, "_cloud_cache", {"t": -1e9, "url": None, "state": None})

    async def go():
        assert await check_health.cloud_state(True) == "ok"
        assert await check_health.cloud_state(True) == "ok"

    asyncio.run(go())
    assert got == ["https://cloud.example/healthz"]


def test_cloud_not_used_with_a_direct_key(monkeypatch):
    """A key from Settings / .env: the judge never goes through the cloud, so there is nothing to probe."""
    from server import config as sc

    monkeypatch.setattr(check_health, "_cloud_route", _REAL_ROUTE)
    monkeypatch.setattr(sc, "mode", lambda provider: "byok")
    monkeypatch.setattr(sc, "cloud_status", lambda: "ok")
    assert asyncio.run(check_health.cloud_state(True)) == "not_used"
    assert check_health.start_cloud_probe() is None


# ------------------------------------------------------------------ review fixes (F1, F2, F4)

def _slow_screen(age_s: float | None = None):
    """A real-reader-shaped screen (reader set, no down reason) whose newest frame is `age_s` old."""
    import time
    from types import SimpleNamespace as NS

    obs = NS(t=time.time() - age_s) if age_s is not None else None
    scr = NS(active=True, reader=object(), paused=False, latest=lambda: obs, fresh_job=None)
    return NS(screen=scr, screen_down_reason=lambda include_ax=True: None, _screen_lines=lambda: {"Code": ["x"]},
              lesson_mode=True)


def test_a_capture_slower_than_check_wait_is_awaited_not_called_stale(monkeypatch):
    """F2: fresh_frame gives up after check_wait_s (1.2 s) on a slow Mac, but its capture goes on. The self-check waits
    for that same job a little longer: done -> fresh; still running -> slow, never "Couldn't read your screen"."""
    monkeypatch.setattr(check_health, "FRESH_EXTRA_S", 0.05)

    async def go():
        s = _slow_screen(age_s=None)
        loop = asyncio.get_running_loop()
        done_soon = loop.create_future()
        loop.call_later(0.01, done_soon.set_result, None)
        s.screen.fresh_job = done_soon
        rep = await check_health.self_check(s, fresh=False, probe_cloud=False)
        assert rep["fresh"] is True and rep["screen"] == "ok"

        s2 = _slow_screen(age_s=None)
        s2.screen.fresh_job = loop.create_future()  # never finishes
        rep2 = await check_health.self_check(s2, fresh=False, probe_cloud=False)
        assert rep2["screen"] == "ok" and rep2.get("captureSlow") is True
        assert check_health.screen_issue(rep2, has_files=False) is None

        s3 = _slow_screen(age_s=check_health.STALE_S + 5)  # no capture running, newest frame long gone
        rep3 = await check_health.self_check(s3, fresh=False, probe_cloud=False)
        assert rep3["screen"] == "stale" and check_health.screen_issue(rep3, has_files=False)["blocking"] is True

        s4 = _slow_screen(age_s=20.0)  # a still screen between the reader's idle heartbeats: not stale
        rep4 = await check_health.self_check(s4, fresh=False, probe_cloud=False)
        assert rep4["screen"] == "ok"

    asyncio.run(go())


def test_the_vscode_scan_runs_only_for_a_lesson_file(monkeypatch):
    """F4: no localhost port scan in a video / app lesson or a step without a file."""
    scanned = []
    monkeypatch.setattr(check_health, "vscode_windows", lambda: scanned.append(1) or [])

    async def go():
        s = _slow_screen(age_s=1.0)
        s.lesson_mode = False
        assert await check_health.vscode_state(s, exact=False, has_files=True) == "unknown"
        s.lesson_mode = True
        assert await check_health.vscode_state(s, exact=False, has_files=False) == "unknown"
        assert scanned == []
        assert await check_health.vscode_state(s, exact=False, has_files=True) == "not_connected"
        assert scanned == [1]

    asyncio.run(go())


def test_every_notice_answering_check_carries_checked_at(tmp_path, monkeypatch):
    """F1: a Check the engine answers with a notice ("Almost ready", "This step is done", "Not yet") ends the app's
    Checking: each carries checkedAt."""
    rig, screen = _rig(tmp_path, monkeypatch)

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        await rig.s._notice("check_step")

    run(go())
    card = rig.of("card")[-1]
    assert card["checkedAt"] > 0


def test_nn_demo_passes_nothing_press_sends_no_thinking_and_no_card(tmp_path, monkeypatch):
    """F1, the NN demo path: stage.check's "passes nothing" press answers with no event at all (no status thinking, no
    card), which is why the app ends Checking when no thinking follows a press (panelStore NO_THINKING_MS)."""
    from server.orchestrator import stage
    from server.orchestrator.tests.test_session import Rig

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.delenv("MIYAGI_STAGE", raising=False)
    for name in ("GRADE_S", "ROW_S", "RUN_S", "STUCK_S"):
        monkeypatch.setattr(stage, name, 0.0)
    rig = Rig(tmp_path)

    async def go():
        await rig.s.learn("anything", mode="demo")
        for _ in range(4):
            await rig.settle()
        assert stage.on(rig.s)
        m = rig.mark()
        await rig.s.action("check_step")  # nn1's code isn't in nn.py, and inside the cue guard: passes nothing
        for _ in range(4):
            await rig.settle()
        after = rig.since(m)
        assert not [e for e in after if e["type"] == "card"]
        assert not [e for e in after if e["type"] == "status" and e["payload"].get("state") == "thinking"]
        assert not rig.of("step.passed") or all(p.get("stepId") != rig.s.step["id"] for p in rig.of("step.passed"))

    run(go())
