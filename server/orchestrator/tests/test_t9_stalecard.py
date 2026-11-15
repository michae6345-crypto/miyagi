"""Desktop test 9, V10 (video lesson s3, 06:17:46-06:19:27): "Not yet · Plot cell not executed yet, no output" stayed up
after the cells ran. advice_clear tracks the checks a generated / video lesson's "Not yet" reported on: one of them
passing clears the card (none left) or sends it again naming only what is left, from a background re-check as well as
Check my work; the step passing clears it. No model calls: the gate is stubbed (Modules force_stubs="all")."""

from __future__ import annotations

import asyncio

from server.orchestrator import advice_clear, stubs
from server.orchestrator.tests.test_session import rig  # noqa: F401 (fixture)

LABELS = {"s1c1": "Training count printed", "s1c2": "Testing count printed"}


def run(coro):
    return asyncio.run(coro)


def _gate(state: dict[str, str]):
    """evaluate_gate stub: one row per check, its status from `state` (flipped by the test)."""

    def gate(step, ctx, screen=None, precision_mode=False):
        rows = [{"checkId": cid, "label": LABELS[cid], "status": st,
                 "detail": "seen on screen" if st == "pass" else "not showing yet"} for cid, st in state.items()]
        ok = all(r["status"] == "pass" for r in rows)
        return {"passed": ok, "via": "checks" if ok else None, "checks": rows, "precision": []}

    return gate


async def _start(rig, monkeypatch, state: dict[str, str]) -> None:  # noqa: F811
    graph = stubs.load_fixture_lesson()
    s1 = graph["steps"][0]
    s1["checks"] = [{**s1["checks"][0], "id": cid, "label": label} for cid, label in LABELS.items()]
    monkeypatch.setattr(rig.s.m, "evaluate_gate", _gate(state))
    await rig.s.load_graph(graph)
    await rig.settle()
    await rig.end_segment()


def _cards(rig, mark: int) -> list[dict]:  # noqa: F811
    return [e["payload"] for e in rig.since(mark) if e["type"] == "card"]


def test_failing_check_card_goes_when_a_background_recheck_passes_it(rig, monkeypatch):  # noqa: F811
    """A stubbed failing check -> Check my work's "Not yet"; the next frame's re-check (not Check) sees it pass ->
    the card goes (the same card, dismissAfterMs 1) before anything else, and nothing tracks it any more."""
    state = {"s1c1": "fail", "s1c2": "pass"}

    async def go():
        await _start(rig, monkeypatch, state)
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        nots = [c for c in _cards(rig, m) if c.get("title") == "Not yet"]
        assert nots and "Training count printed" in nots[-1]["body"] and not nots[-1].get("dismissAfterMs")
        up = rig.s._advice_up
        assert up is not None and set(up["checks"]) == {"s1c1"}
        state["s1c1"] = "pass"  # the cell ran: a background re-check sees it
        m = rig.mark()
        await rig.s.evaluate("screen")
        await rig.settle()
        ev = rig.since(m)
        cleared = [i for i, e in enumerate(ev) if e["type"] == "card" and e["payload"].get("dismissAfterMs") == 1]
        assert cleared, [e["type"] for e in ev]
        assert ev[cleared[0]]["payload"]["title"] == "Not yet"
        assert rig.s._advice_up is None
        passed = [i for i, e in enumerate(ev) if e["type"] == "step.passed"]
        assert not passed or cleared[0] < passed[0]

    run(go())


def test_one_of_two_failing_checks_passing_resends_a_card_naming_only_the_other(rig, monkeypatch):  # noqa: F811
    state = {"s1c1": "fail", "s1c2": "fail"}

    async def go():
        await _start(rig, monkeypatch, state)
        await rig.s.evaluate("screen")  # the background re-check: both red
        await rig.settle()
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        first = [c for c in _cards(rig, m) if c.get("title") == "Not yet"][-1]
        assert "Training count printed" in first["body"] and "Testing count printed" in first["body"]
        assert set(rig.s._advice_up["checks"]) == {"s1c1", "s1c2"}
        await rig.s.evaluate("screen")  # nothing moved: nothing sent
        await rig.settle()
        m = rig.mark()
        state["s1c1"] = "pass"
        await rig.s.evaluate("screen")
        await rig.settle()
        again = _cards(rig, m)
        assert len(again) == 1, again
        card = again[0]
        assert card["title"] == "Not yet" and card["stepId"] == "s1" and not card.get("dismissAfterMs")
        assert "Testing count printed" in card["body"] and "Training count printed" not in card["body"]
        assert set(rig.s._advice_up["checks"]) == {"s1c2"}
        # and the last one passing takes the re-sent card down
        m = rig.mark()
        state["s1c2"] = "pass"
        await rig.s.evaluate("screen")
        await rig.settle()
        gone = _cards(rig, m)
        assert gone and gone[0]["dismissAfterMs"] == 1 and gone[0]["body"] == card["body"]
        assert rig.s._advice_up is None

    run(go())


def test_the_step_passing_clears_its_not_yet_card(rig, monkeypatch):  # noqa: F811
    """A tracked "Not yet" card goes before step.passed (the app closes an off-track on step.passed, not a card)."""
    state = {"s1c1": "fail", "s1c2": "pass"}

    async def go():
        await _start(rig, monkeypatch, state)
        await rig.s.action("check_step")
        await rig.settle()
        up = rig.s._advice_up
        assert up is not None
        up["checks"] = None  # only the pass can take it down now
        m = rig.mark()
        await rig.s.action("skip_step")
        await rig.settle()
        ev = rig.since(m)
        types_ = [e["type"] for e in ev]
        assert "step.passed" in types_
        cleared = [i for i, e in enumerate(ev) if e["type"] == "card" and e["payload"].get("dismissAfterMs") == 1]
        assert cleared and cleared[0] < types_.index("step.passed")
        assert rig.s._advice_up is None

    run(go())


class _S:
    """The bits of LessonSession advice_clear uses (a video lesson: no curated graph)."""

    def __init__(self) -> None:
        self.step, self.step_gen, self.passed = {"id": "s3"}, 1, False
        self.last_offtrack = None
        self._advice_up = None
        self._card_in_use = None
        self.last_failed: list[dict] = []
        self.last_results: list[dict] = []
        self.sent: list[tuple[str, dict]] = []

    def _run_command(self, step):
        return None

    def _step_lines(self, step):
        return None, []

    async def emit(self, type_, payload):
        self.sent.append((type_, payload))

    def rows(self, **status: str) -> None:
        self.last_results = [{"checkId": c, "label": {"s3c2": "Training count printed",
                                                       "s3c3": "Testing count printed"}[c], "status": st}
                             for c, st in status.items()]
        self.last_failed = [r for r in self.last_results if r["status"] == "fail"]


PLOT = {"stepId": "s3", "severity": "warn", "title": "Plot cell not executed yet, no output",
        "body": "Run the print and plotting cell with Shift+Enter.", "actions": ["explain", "show_me", "hint"]}


def test_v10_offtrack_names_what_is_left_then_goes(monkeypatch):
    """The test 9 card itself: the off-track over s3c2 + s3c3. s3c2 passes -> a "Not yet" card (it takes the
    off-track's place) naming only s3c3, keeping the off-track's Hint / Show me; a pending row is no change; s3c3
    passes -> that card goes."""
    from server.orchestrator import stale_advice

    async def state(sess, step, card, anew=False):
        return ""  # the diagnosis has no code evidence: only the checks can move it

    monkeypatch.setattr(stale_advice, "state", state)
    s = _S()
    s.rows(s3c2="fail", s3c3="fail")
    advice_clear.sent_offtrack(s, s.step, PLOT, PLOT)
    assert set(s._advice_up["checks"]) == {"s3c2", "s3c3"}
    s.rows(s3c2="pending", s3c3="fail")  # can't tell (the reader paused): the card stays
    run(advice_clear.checks_moved(s))
    run(advice_clear.follow(s, force=True))
    assert not s.sent
    s.rows(s3c2="pass", s3c3="fail")
    run(advice_clear.checks_moved(s))
    assert len(s.sent) == 1
    kind, card = s.sent[0]
    assert kind == "card" and card["title"] == "Not yet" and card["kind"] == "step" and card["verdict"] == "not_done"
    assert "Testing count printed" in card["body"] and "Training count printed" not in card["body"]
    assert card["actions"] == ["show_me", "hint"]
    s.rows(s3c2="pass", s3c3="pass")
    run(advice_clear.checks_moved(s))
    assert s.sent[-1] == ("card", {**card, "dismissAfterMs": 1}) and s._advice_up is None


def test_curated_lessons_keep_their_own_basis(monkeypatch):
    """The curated lesson's Not yet stays on t8's culprit / diagnosis basis (no checks tracked)."""
    from server.orchestrator import curated

    monkeypatch.setattr(curated, "active", lambda sess: True)
    s = _S()
    s.rows(s3c2="fail", s3c3="fail")
    advice_clear.sent_offtrack(s, s.step, PLOT, PLOT)
    assert s._advice_up is not None and not s._advice_up.get("checks")
