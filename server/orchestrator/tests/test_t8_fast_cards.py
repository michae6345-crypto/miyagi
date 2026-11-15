"""Desktop test 8, the curated neural-net lesson's planted bugs, offline: their "Not yet" cards go out at once from the
files (curated.known_offtrack), never after a model call. The coach is a stub that sleeps 8 s (and costs nothing): a
known failure must not wait for it; an unknown one still goes to it.

t8: nn2's sign bug `(1 + h2 ** 2)`: paste 05:51:20.2 -> card 05:51:31.7 (~11.5 s: 20 s grace + 3 s idle gate, Haiku
triage 3.2 s, Sonnet 3.0 s).
Run from the repo root:  python -m pytest server/orchestrator/tests/test_t8_fast_cards.py -q
"""
from __future__ import annotations

import asyncio
import time

from server.orchestrator import curated
from server.orchestrator.tests.test_stage import rig, settle  # noqa: F401 (fixture)
from shared.contracts.events import validate_engine_payload

STUB_S = 8.0
STEPS = {s["id"]: s for s in curated.lesson_for("x", force=True)["steps"]}
NN2 = (curated.STARTER_FILE.read_text(encoding="utf-8")
       .replace("# The network\n", "# The network\n" + STEPS["nn1"]["code"] + "\n")
       .replace("# Backprop\n", "# Backprop\n" + STEPS["nn2"]["code"] + "\n"))
SIGN = NN2.replace("d_out @ W3.T * (1 - h2 ** 2)", "d_out @ W3.T * (1 + h2 ** 2)")


def run(coro):
    return asyncio.run(coro)


def _slow_coach(rig):  # noqa: F811
    calls: list[float] = []

    async def diagnose(step, failed_checks, metrics, code_excerpt, **_):
        calls.append(time.monotonic())
        await asyncio.sleep(STUB_S)
        return {"stepId": step["id"], "severity": "warn", "title": "From the model", "body": "Slow card.",
                "actions": ["explain", "hint"]}

    rig.s.m.diagnose = diagnose
    return calls


async def _at_nn2(rig):  # noqa: F811
    await rig.s.learn("build a neural network", mode="lesson")
    await settle(rig)
    await rig.s.goto_step(1)
    await settle(rig)
    assert rig.s.step["id"] == "nn2"


async def _first_offtrack(rig, t0: float, limit: float = STUB_S + 2) -> tuple[dict | None, float]:  # noqa: F811
    while time.monotonic() - t0 < limit:
        off = rig.of("offtrack")
        if off:
            return off[0], time.monotonic() - t0
        await asyncio.sleep(0.01)
    return None, limit


def test_sign_bug_card_goes_out_at_paste_without_the_model(rig):  # noqa: F811
    """5 s into nn2 (inside the 20 s grace), the learner pastes backward() with (1 + h2 ** 2): the Not yet card is up
    within a fraction of a second, from the files; the 8 s coach is never asked."""
    calls = _slow_coach(rig)
    line = next(i for i, ln in enumerate(SIGN.splitlines(), 1) if "(1 + h2 ** 2)" in ln)

    async def go():
        await _at_nn2(rig)
        rig.clock.t += 5  # well inside offtrack_grace_s (20)
        p = rig.workdir / "nn.py"
        p.write_text(SIGN)
        t0 = time.monotonic()
        await rig.s.on_file_change([str(p)])
        card, dt = await _first_offtrack(rig, t0)
        await settle(rig)
        return card, dt

    card, dt = run(go())
    assert card is not None, rig.types()
    assert dt < 1.0, dt  # t8: ~11.5 s
    assert not calls  # no model call for a known failure
    assert card["title"] == "Wrong sign in the d_h2 tanh slope"
    assert card["body"] == f"Change + to - on line {line} of nn.py. The slope of tanh is 1 - h2 ** 2."
    assert card["severity"] == "fail" and card["level"] == 2
    assert card["actions"] == ["explain", "show_me", "hint", "apply_fix"]  # as the coach's lesson-mode card
    validate_engine_payload("offtrack", card)
    full = rig.s.last_offtrack
    assert full["diff"] == {"yours": "    d_h2 = d_out @ W3.T * (1 + h2 ** 2)",
                            "expected": "    d_h2 = d_out @ W3.T * (1 - h2 ** 2)", "file": "nn.py", "line": line}
    rows = [p for p in rig.of("check.updated") if p["checkId"] in curated.SIGN_ROWS and p["status"] == "fail"]
    assert rows and rows[-1]["detail"] == f"needs 1 - h2 ** 2 on line {line}, not 1 + h2 ** 2"  # the row says it too
    print(f"\nsign-bug Not yet card: {dt * 1000:.0f} ms after the paste (t8: ~11.5 s)")


def test_sign_bug_card_is_said_once_and_goes_once_fixed(rig):  # noqa: F811
    calls = _slow_coach(rig)

    async def go():
        await _at_nn2(rig)
        rig.clock.t += 5
        p = rig.workdir / "nn.py"
        p.write_text(SIGN)
        await rig.s.on_file_change([str(p)])
        await settle(rig)
        for _ in range(3):  # more frames / ticks of the same code: no second card
            rig.clock.t += 4
            await rig.s.evaluate("screen")
            await rig.s.tick()
            await settle(rig)
        n = len(rig.of("offtrack"))
        p.write_text(NN2)  # fixed
        rig.clock.t += 2
        await rig.s.on_file_change([str(p)])
        await settle(rig)
        return n

    n = run(go())
    assert n == 1 and not calls
    assert rig.of("step.passed") and rig.of("step.passed")[0]["stepId"] == "nn2"


def test_an_unknown_failure_still_goes_to_the_coach(rig):  # noqa: F811
    """A slope that is missing (not the + sign) is not a known failure: Claude (here the slow stub) diagnoses it."""
    calls = _slow_coach(rig)
    bad = NN2.replace("d_out @ W3.T * (1 - h2 ** 2)", "d_out @ W3.T")

    async def go():
        await _at_nn2(rig)
        rig.clock.t += 30
        p = rig.workdir / "nn.py"
        p.write_text(bad)
        assert curated.known_offtrack(rig.s, rig.s.step, [{"checkId": "nn2p4", "status": "fail"}]) is None
        await rig.s.on_file_change([str(p)])
        rig.clock.t += 10  # idle: the ladder speaks
        await rig.s.tick()
        await asyncio.sleep(0.05)
        return list(calls)

    assert run(go())  # the model was asked


def test_known_offtrack_reads_the_plus_sign_only():
    class S:
        graph = curated.lesson_for("x", force=True)
        lesson_mode = True

        def __init__(self, text):
            self.text = text

        def _step_lines(self, step):
            from pathlib import Path

            return Path("nn.py"), self.text.splitlines()

    step, fail = STEPS["nn2"], [{"checkId": "nn2c4", "status": "fail"}]
    orig = curated.active
    curated.active = lambda s: True
    try:
        assert curated.known_offtrack(S(NN2), step, fail) is None  # right: nothing known
        assert curated.known_offtrack(S(SIGN), step, []) is None  # no failing row: nothing to say
        h1 = NN2.replace("(1 - h1 ** 2)", "(1+h1**2)")
        card = curated.known_offtrack(S(h1), step, fail)
        assert card["title"] == "Wrong sign in the d_h1 tanh slope" and card["diff"]["expected"].endswith("(1-h1**2)")
        mid = NN2.replace("d_out @ W3.T * (1 - h2 ** 2)", "d_out @ W3.T * (1 + h")  # still typing: not known
        assert curated.known_offtrack(S(mid), step, fail) is None
        assert curated.known_offtrack(S(SIGN), STEPS["nn3"], fail) is None  # another step
    finally:
        curated.active = orig
