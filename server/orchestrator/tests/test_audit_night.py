"""Integration audit (Nov 15, before the 9 AM freeze): interactions between features that landed separately tonight.
Run from the repo root:  python -m pytest server/orchestrator/tests/test_audit_night.py -q

offtrack_targets (t8) x the culprit going away: Hint measured the W1..W3 lines while its own card was up, so the
off-track's targets wait for that card to close. When the learner has started the weights random by then, the
off-track is stale (t8b's advice_clear takes such cards down); its card.closed must not re-send the old "Not yet"
with targets over the fixed code. With the culprit still there it is re-sent (the t8 test covers that half).
"""
from __future__ import annotations

import asyncio

from server.orchestrator.tests.test_run_pointing import FakeExt, _demo_at, _demo_rig, _rows_after_reveal
from server.orchestrator.tests.test_run_pointing import fast  # noqa: F401 (fixture)
from server.orchestrator.tests.test_stage import RANDOM, ZEROS

TOP, PITCH = 200.0, 18.0


def offtracks(events: list[dict]) -> list[dict]:
    return [e["payload"] for e in events if e["type"] == "offtrack"]


def test_hint_targets_never_bring_back_a_not_yet_whose_cause_is_fixed(tmp_path, monkeypatch, fast):  # noqa: F811
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    ext = FakeExt()
    rig.s._vscode_ext = lambda: ext
    _rows_after_reveal(monkeypatch, ext, top=TOP, pitch=PITCH)

    async def go():
        await _demo_at(rig, 3)
        await rig.s.action("run_command")  # the planned stuck run -> "Loss is stuck at 0.49"
        await rig.settle()
        assert offtracks(rig.events)
        await rig.s.action("hint")  # boxes W1..W3: the off-track's targets wait for the hint card to close
        await rig.settle()
        assert (rig.s._ot_state or {}).get("pending"), rig.s._ot_state
        p = rig.workdir / "nn.py"
        p.write_text(p.read_text(encoding="utf-8").replace(ZEROS, RANDOM), encoding="utf-8")  # the fix: random weights
        hint = [c for c in rig.of("card") if c.get("kind") == "hint"][-1]
        m = rig.mark()
        await rig.s.card_seen(False, "nn4", hint["title"], kind="hint", by="timeout")
        await rig.settle()
        return rig.since(m)

    closed = asyncio.run(go())
    assert not offtracks(closed), offtracks(closed)  # no stale "Loss is stuck" re-sent over the fixed code
    assert rig.s._ot_state["pending"] is None
