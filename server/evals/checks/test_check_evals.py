"""The step-check eval set (server/evals/checks/cases) must not get worse: accuracy, precision and recall stay at or
above baseline.json (train and held-out apart), and no case outside its known_wrong / known_wrong_held_out list gets
a wrong verdict. Offline: no model, no network.

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
    train, _ = runner.split(outcomes)
    base, now = baseline(), runner.score(train)
    for metric in ("accuracy", "precision", "recall"):
        assert now[metric] >= base[metric] - 1e-9, (
            f"train {metric} dropped: {now[metric]} < baseline {base[metric]}\n\n" + runner.report(outcomes))


def test_held_out_scores_hold_the_baseline(outcomes):
    """A regression guard only: held-out cases are never used to tune a fix, but a fix must not make them worse."""
    _, held = runner.split(outcomes)
    base, now = baseline().get("held_out") or {}, runner.score(held)
    for metric in ("accuracy", "precision", "recall"):
        if metric in base:
            assert now[metric] >= base[metric] - 1e-9, f"held-out {metric} dropped: {now[metric]} < {base[metric]}"


def test_no_new_wrong_verdicts(outcomes):
    base = baseline()
    known = {**base["known_wrong"], **(base.get("known_wrong_held_out") or {})}
    new = [o for o in runner.failures(outcomes) if o.case["id"] not in known]
    assert not new, "new wrong verdicts (fix the checks, or the case's expected verdict):\n" + "\n".join(
        f"  {o.label} {o.case['id']}{' (held out)' if runner.is_held_out(o.case) else ''}: expected {o.expected}, "
        f"got {o.got}" + ("" if runner.is_held_out(o.case) else "; rows: " + "; ".join(
            f"{r['checkId']} {r['status']} ({r['detail']})" for r in o.rows)) for o in new)


def test_known_wrong_cases_exist():
    base = baseline()
    cases = {c["id"]: runner.is_held_out(c) for c in runner.load_cases()}
    stale = sorted(set(base["known_wrong"]) - {i for i, h in cases.items() if not h})
    stale += sorted(set(base.get("known_wrong_held_out") or {}) - {i for i, h in cases.items() if h})
    assert not stale, f"baseline.json lists cases that no longer exist (or moved between train and held out): {stale}"


def test_every_held_out_trap_kind_is_also_in_train():
    """A held-out case measures whether a fix made on train cases generalises: its kind of trap has train cases."""
    cases = runner.load_cases()
    held = [c for c in cases if runner.is_held_out(c)]
    if not held:
        return
    assert all(isinstance(c.get("heldOut", False), bool) for c in cases)
    train_traps = {c.get("trap", "none") for c in cases if not runner.is_held_out(c)}
    assert {c.get("trap", "none") for c in held} <= train_traps
