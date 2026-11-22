"""The step-check eval set (server/evals/checks/cases) must not get worse: accuracy, precision and recall stay at or
above baseline.json, and no case outside its known_wrong list gets a wrong verdict. Offline: no model, no network.

    python -m pytest server/evals/checks -q
    python -m server.evals.checks -v            # the scores and the wrong verdicts, worst first
    python -m server.evals.checks --write-baseline   # after the checks got better (or cases were added)
"""
from __future__ import annotations

import json
import socket

import pytest

from server.evals.checks import runner

PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY", "TIGER_DATABASE_URL")


def _offline(mp: pytest.MonkeyPatch, state_dir) -> None:
    mp.setenv("MIYAGI_STATE_DIR", str(state_dir))
    for k in PAID_KEYS:  # an accidental live call fails at once, for free
        mp.setenv(k, "")

    def no_network(*_a, **_k):
        raise AssertionError("the check eval must not touch the network")

    mp.setattr(socket.socket, "connect", no_network)


@pytest.fixture(scope="module")
def outcomes(tmp_path_factory) -> list[runner.Outcome]:
    with pytest.MonkeyPatch.context() as mp:
        _offline(mp, tmp_path_factory.mktemp("miyagi-state"))
        return runner.run_all()


def baseline() -> dict:
    return json.loads(runner.BASELINE.read_text(encoding="utf-8"))


def test_the_set_covers_every_lesson_kind_and_both_kinds_of_trap():
    cases = runner.load_cases()
    assert len(cases) >= 20
    assert {c["kind"] for c in cases} == set(runner.KINDS)
    assert {c["expected"] for c in cases} == {"pass", "not_yet"}
    traps = [c.get("trap", "none") for c in cases]
    assert traps.count("false_pass") >= 5 and traps.count("false_fail") >= 3


def test_every_case_builds_and_runs_without_error(outcomes):
    broken = {o.case["id"]: o.error for o in outcomes if o.error}
    assert not broken, broken


def test_scores_hold_the_baseline(outcomes):
    base, now = baseline(), runner.score(outcomes)
    for metric in ("accuracy", "precision", "recall"):
        assert now[metric] >= base[metric] - 1e-9, (
            f"{metric} dropped: {now[metric]} < baseline {base[metric]}\n\n" + runner.report(outcomes))


def test_no_new_wrong_verdicts(outcomes):
    known = baseline()["known_wrong"]
    new = [o for o in runner.failures(outcomes) if o.case["id"] not in known]
    assert not new, "new wrong verdicts (fix the checks, or the case's expected verdict):\n" + "\n".join(
        f"  {o.label} {o.case['id']}: expected {o.expected}, got {o.got}; rows: "
        + "; ".join(f"{r['checkId']} {r['status']} ({r['detail']})" for r in o.rows) for o in new)


def test_known_wrong_cases_exist():
    ids = {c["id"] for c in runner.load_cases()}
    stale = sorted(set(baseline()["known_wrong"]) - ids)
    assert not stale, f"baseline.json lists cases that no longer exist: {stale}"
