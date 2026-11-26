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
