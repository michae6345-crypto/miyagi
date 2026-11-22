"""Desktop test 11 (Nov 15, the Kie Codes "Watch a video" notebook lesson, engine dd85beb): cards that outlived what
they said.

1. s2: the off-track "load_dat() should be load_data()" came back when the learner closed a later Explain card, after
   the fix passed its check (08:31:28), and a later Explain explained the fixed problem: an Explain card had ended
   tracking, so the off-track was never withdrawn, and last_offtrack kept feeding Explain.
2. s5: Check my work mid-run sent "Not yet · Still to do: Training accuracy at least 95%; run Run the cell
   (Shift+Enter) in the terminal." 0.2 s before step.passed (the cell finished during the ~3 s judge call).
3. "Looks done? Yes" passed a notebook step whose cell hadn't run; s3 showed a "Looks done?" 2 s before the real pass
   (only the run's rows were left); judge calls while an off-track was up.
No model calls: Modules(force_stubs="all"); the gate / judge are stubbed per test."""

from __future__ import annotations

import asyncio
import json

from server.orchestrator import advice_clear, code_gate, stale_advice
from server.orchestrator.tests.test_session import rig  # noqa: F401 (fixture)
from server.orchestrator.tests.test_t10_coach import S5_CHECKS, _start

LABELS = {"s2c1": "Imports typed", "s2c2": "mnist load_data called", "s2c3": "No import or load errors"}
OFF = {"stepId": "s2", "severity": "fail", "title": "load_dat() should be load_data()",
       "body": "The call ends in mnist.load_dat(), which is not a TensorFlow function.",
       "diff": {"file": "Untitled.ipynb",
                "yours": "(train_images, train_labels), (test_images, test_labels) = tf.keras.datasets.mnist.load_dat()",
                "expected": "(train_images, train_labels), (test_images, test_labels) = "
                            "tf.keras.datasets.mnist.load_data()"},
       "actions": ["explain", "show_me", "hint"]}
WITHDRAW = {"stepId": "s2", "severity": "fail", "title": "", "body": "", "actions": [], "dismissAfterMs": 1}


def run(coro):
    return asyncio.run(coro)


class _S:
    """The bits of LessonSession advice_clear / stale_advice.forget use (a video lesson: no curated graph)."""

    def __init__(self) -> None:
        self.step, self.step_gen, self.passed = {"id": "s2"}, 1, False
        self.last_offtrack: dict | None = None
        self.full_card: dict | None = None
        self._advice_up = None
        self._offtrack_up = None
        self._card_in_use = None
        self.status = "offtrack"
        self.last_failed: list[dict] = []
        self.last_results: list[dict] = []
        self.sent: list[tuple[str, dict]] = []
        self.statuses: list[str] = []

    def _run_command(self, step):
        return None

    def _step_lines(self, step):
        return None, []

    async def emit(self, type_, payload):
        self.sent.append((type_, payload))

    async def _status(self, state, **kw):
        self.status = state
        self.statuses.append(state)

    def rows(self, **status: str) -> None:
        self.last_results = [{"checkId": c, "label": LABELS[c], "status": st} for c, st in status.items()]
        self.last_failed = [r for r in self.last_results if r["status"] == "fail"]


async def _no_line_state(sess, step, card, anew=False):
    return ""  # only the checks can move it here


def test_offtrack_is_withdrawn_when_its_check_passes_under_an_explain_card(monkeypatch):
    """The t11 s2 sequence: off-track -> Explain card -> Hint resting on the off-track -> the fix passes s2c2. The
    off-track is withdrawn (`offtrack` dismissAfterMs 1, not a `card` the app ignores), the Hint resting on it goes
    too, last_offtrack is forgotten (Explain never gets it again) and the status leaves "offtrack"."""
    monkeypatch.setattr(stale_advice, "state", _no_line_state)
    s = _S()
    s.rows(s2c1="pass", s2c2="fail", s2c3="pending")
    s.last_offtrack = s.full_card = OFF
    advice_clear.sent_offtrack(s, s.step, OFF, OFF)
    assert set(s._offtrack_up["checks"]) == {"s2c2"}  # a pending row is never part of its basis
    advice_clear.sent(s, {"stepId": "s2", "kind": "explain", "title": "The typo stops the MNIST load", "body": "…"})
    assert s._advice_up is None and s._offtrack_up is not None  # the Explain card on top: still tracked
    hint = {"stepId": "s2", "kind": "hint", "title": "Question · Import libraries and load MNIST",
            "body": "load_dat() should be load_data(): what in your code makes that happen?"}
    advice_clear.sent(s, hint)
    assert s._advice_up is not None and s._advice_up is not s._offtrack_up
    assert advice_clear.live_offtrack(s) is OFF
    s.rows(s2c1="pass", s2c2="pass", s2c3="pending")  # the learner fixed the typo
    assert advice_clear.live_offtrack(s) is None  # Explain in the same tick already leaves it out
    run(advice_clear.checks_moved(s))
    assert ("offtrack", WITHDRAW) in s.sent
    assert ("card", {**hint, "dismissAfterMs": 1}) in s.sent
    assert not any(t == "card" and p.get("title") == "Not yet" for t, p in s.sent)
    assert s.last_offtrack is None and s.full_card is None
    assert s._offtrack_up is None and s._advice_up is None
    assert s.statuses == ["watching"]
    n = len(s.sent)
    run(advice_clear.checks_moved(s))  # nothing tracked: nothing sent again
    run(advice_clear.follow(s, force=True))
    assert len(s.sent) == n


def test_offtrack_closed_by_the_learner_is_still_withdrawn(monkeypatch):
    """The learner closed the off-track (✕): the app keeps its off-track state (the pill's ring) until withdrawn."""
    monkeypatch.setattr(stale_advice, "state", _no_line_state)
    s = _S()
    s.rows(s2c2="fail")
    s.last_offtrack = OFF
    advice_clear.sent_offtrack(s, s.step, OFF, OFF)
    advice_clear.closed(s, OFF["title"], "user")
    assert s._advice_up is None and s._offtrack_up is not None
    s.rows(s2c2="pass")
    run(advice_clear.checks_moved(s))
    assert s.sent == [("offtrack", WITHDRAW)] and s.last_offtrack is None


def test_pending_row_turning_green_moves_nothing(monkeypatch):
    """A "Not yet" over a failing row and a pending "No errors" row: only the failing row is its basis, so the pending
    one passing re-sends nothing; the failing one passing takes it down."""
    s = _S()
    s.rows(s2c1="pass", s2c2="fail", s2c3="pending")
    card = {"stepId": "s2", "kind": "answer", "title": "Not yet", "body": "Still to do: mnist load_data called.",
            "actions": ["hint", "show_me", "skip_step"]}
    advice_clear.sent(s, card)
    assert set(s._advice_up["checks"]) == {"s2c2"}
    s.rows(s2c1="pass", s2c2="fail", s2c3="pass")
    run(advice_clear.checks_moved(s))
    assert not s.sent
    s.rows(s2c1="pass", s2c2="pass", s2c3="pass")
    run(advice_clear.checks_moved(s))
    assert s.sent == [("card", {**card, "dismissAfterMs": 1})]


def test_step_passing_drops_the_tracked_offtrack():
    s = _S()
    s.rows(s2c2="fail")
    advice_clear.sent_offtrack(s, s.step, OFF, OFF)
    advice_clear.sent(s, {"stepId": "s2", "kind": "explain", "title": "About it", "body": "…"})
    run(advice_clear.step_passed(s))
    assert s._offtrack_up is None and not s.sent  # the app's step.passed ends the off-track itself


class _NbS:
    """stale_advice.state's reads for a notebook step."""

    def __init__(self, workdir) -> None:
        self.workdir = str(workdir)
        self.last_obs = None
        self._buffers = None
        self.step = {"id": "s2", "file": "Untitled.ipynb"}

    def _step_file(self, step):
        return step.get("file")


def _nb(path, src: str) -> None:
    path.write_text(json.dumps({"cells": [{"cell_type": "code", "source": src.splitlines(True), "outputs": [],
                                           "execution_count": None, "metadata": {}}],
                                "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")


def test_a_notebook_diagnosis_goes_stale_once_its_line_is_gone(tmp_path):
    """stale_advice.state returned "" for any .ipynb, so a notebook diagnosis was never forgotten. Its line still in a
    cell: it stands; gone from every cell: "gone"; a notebook that can't be read: it stands."""
    s = _NbS(tmp_path)
    nb = tmp_path / "Untitled.ipynb"
    _nb(nb, "import tensorflow as tf\n" + OFF["diff"]["yours"] + "\n")
    assert run(stale_advice.state(s, s.step, OFF)) == ""
    _nb(nb, "import tensorflow as tf\n" + OFF["diff"]["expected"] + "\n")
    assert run(stale_advice.state(s, s.step, OFF)) == ""  # never in their cells (nor what the coach read): no claim
    stale_advice.note(s, s.step, OFF, "import tensorflow as tf\n" + OFF["diff"]["yours"])
    assert run(stale_advice.state(s, s.step, OFF)) == "gone"
    nb.write_text("{ not json", encoding="utf-8")
    assert run(stale_advice.state(s, s.step, OFF)) == ""


def test_ran_the_cell_row_never_says_terminal_in_a_notebook_step():
    """s5's Not yet: "run Run the cell (Shift+Enter) in the terminal" -> "run the cell (Shift+Enter)"; a shell
    command still names the terminal."""
    rows = [{"checkId": "s5c3", "label": "Training accuracy at least 95%", "status": "fail"},
            {"checkId": "s5-ran", "label": "Ran the cell", "status": "pending",
             "detail": "run the cell in Untitled.ipynb (Shift+Enter)"}]
    body = code_gate.not_yet_body("", rows, sid="s5", cmd="Run the cell (Shift+Enter)")
    assert body == "Still to do: Training accuracy at least 95%; run the cell (Shift+Enter)."
    assert "terminal" not in code_gate.not_yet_body("", rows, sid="s5", cmd="")
    assert "run Run" not in body
    shell = [{"checkId": "s1-ran", "label": "Ran python3 main.py", "status": "pending"}]
    assert code_gate.not_yet_body("", shell, sid="s1", cmd="python3 main.py") == \
        "Still to do: run python3 main.py in the terminal."
    assert code_gate.ran_part("run python3 app.py", "Ran") == "run python3 app.py in the terminal"


# ------------------------------------------------------------------ the session (rig)
def _gate_from(rows: list[dict]):
    """evaluate_gate stub: `rows` as they are now (the test flips them); passed when every row passes."""

    def gate(step, ctx, screen=None, precision_mode=False):
        out = [dict(r) for r in rows]
        ok = bool(out) and all(r["status"] == "pass" for r in out)
        return {"passed": ok, "via": "checks" if ok else None, "checks": out, "precision": []}

    return gate


def test_no_not_yet_when_the_cell_finishes_during_the_judge_call(rig, monkeypatch):  # noqa: F811
    """s5 08:34:24: the judge said not done while the cell was finishing; the rows passed 0.2 s later. The rows as
    they are after the judge decide: the step passes and no "Not yet" goes out."""
    rows = [{"checkId": "s5c1", "label": "model.compile called", "status": "pass"},
            {"checkId": "s5c2", "label": "model.fit called", "status": "fail"},
            {"checkId": "s5c3", "label": "Training accuracy reaches 0.95", "status": "fail"}]

    async def judge_step(step, screen=None, files=None, **kw):
        for r in rows:
            r["status"] = "pass"  # the run ended while Claude looked
        return {"done": False, "missing": "Training accuracy at least 95%"}

    from server.orchestrator import notebook_runs

    monkeypatch.setattr(notebook_runs, "need_run", lambda *a, **k: None)  # the run's row: in `rows` (the gate)

    async def go():
        await _start(rig, monkeypatch, S5_CHECKS, rows, code="history = model.fit(train_images, train_labels)")
        monkeypatch.setattr(rig.s.m, "evaluate_gate", _gate_from(rows))
        monkeypatch.setattr(rig.s.m, "judge_step", judge_step)
        rig.clock.t += 30
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        ev = rig.since(m)
        assert any(e["type"] == "step.passed" for e in ev), [(e["type"], e["payload"]) for e in ev]
        assert not any(e["type"] == "card" and e["payload"].get("title") == "Not yet"
                       and not e["payload"].get("dismissAfterMs") for e in ev)

    run(go())


def _ran_rows(sid: str, ran: str) -> list[dict]:
    return [{"checkId": "s5c1", "label": "model.compile called", "status": "pass"},
            {"checkId": "s5c2", "label": "model.fit called", "status": "pass"},
            {"checkId": "s5c3", "label": "Training accuracy reaches 0.95", "status": "fail"},
            {"checkId": f"{sid}-ran", "label": "Ran the cell", "status": ran,
             "detail": "run the cell in mnist.ipynb (Shift+Enter)"}]


def test_looks_done_yes_waits_for_the_cell_to_run(rig, monkeypatch):  # noqa: F811
    """Yes on the judge's "Looks done?" in a notebook step whose cell hasn't run: no step.passed, a card saying to run
    the cell, the vouched checks kept green (judged_pass) so the run passes the step."""

    async def go():
        step = await _start(rig, monkeypatch, S5_CHECKS, [], code="history = model.fit(train_images, train_labels)")
        sid = step["id"]
        rig.s.last_results = _ran_rows(sid, "pending")
        rig.s.confirm_check_ids = ["s5c3"]
        rig.clock.t += 30
        m = rig.mark()
        await rig.s.action("confirm")
        await rig.settle()
        ev = rig.since(m)
        assert not any(e["type"] == "step.passed" for e in ev), [e["type"] for e in ev]
        cards = [e["payload"] for e in ev if e["type"] == "card"]
        assert cards and cards[-1]["title"] == "Run the cell first" and "Shift+Enter" in cards[-1]["body"]
        assert "s5c3" in rig.s.judged_pass and not rig.s.passed

    run(go())


def test_looks_done_yes_passes_once_the_cell_ran(rig, monkeypatch):  # noqa: F811
    async def go():
        step = await _start(rig, monkeypatch, S5_CHECKS, [], code="history = model.fit(train_images, train_labels)")
        rig.s.last_results = _ran_rows(step["id"], "pass")
        rig.s.confirm_check_ids = ["s5c3"]
        rig.clock.t += 30
        m = rig.mark()
        await rig.s.action("confirm")
        await rig.settle()
        assert any(e["type"] == "step.passed" for e in rig.since(m))

    run(go())


def test_judge_skipped_when_only_the_run_decides_or_an_offtrack_is_up(rig, monkeypatch):  # noqa: F811
    """No Haiku call while an off-track is up, when only the run's rows are left (output rows, Ran the cell) in a
    notebook step, and none dropped while a code row still fails."""

    async def go():
        step = await _start(rig, monkeypatch, S5_CHECKS, [], code="history = model.fit(train_images, train_labels)")
        sid = step["id"]
        rig.s.last_results = _ran_rows(sid, "pending")
        assert rig.s._judge_needless(step) == "only the run's rows are left"
        rig.s.last_results = [r for r in _ran_rows(sid, "pending") if r["checkId"] != "s5c3"]
        assert rig.s._judge_needless(step) == "only the run's rows are left"  # only "Ran the cell"
        rows = _ran_rows(sid, "pending")
        rows[1]["status"] = "fail"  # model.fit not typed yet: the judge may look
        rig.s.last_results = rows
        assert rig.s._judge_needless(step) == ""
        rig.s.last_offtrack = {**OFF, "stepId": sid}
        assert rig.s._judge_needless(step) == "an off-track is up"

    run(go())


def test_no_looks_done_card_when_only_the_run_is_left(rig, monkeypatch):  # noqa: F811
    """s3 08:33:46: the judge (asked while a code row failed) came back with "Looks done?" once only the run's rows
    were left: dropped, the run passes the step 2 s later."""

    class _Judge:
        async def judge(self, step, results, **kw):
            return {"done": True, "events": [], "card": {
                "stepId": step["id"], "kind": "step", "source": "judge", "verdict": "done", "title": "Looks done?",
                "body": "Notebook has count prints", "actions": ["confirm"], "checkIds": ["s5c3"]}}

        def card_shown(self, *a):
            pass

    async def go():
        step = await _start(rig, monkeypatch, S5_CHECKS, [], code="history = model.fit(train_images, train_labels)")
        rig.s.last_results = _ran_rows(step["id"], "pending")
        rig.s.judge = _Judge()
        m = rig.mark()
        await rig.s._run_judge(rig.s.step_gen, step, None, {})
        await rig.settle()
        assert not any(e["type"] == "card" and e["payload"].get("title") == "Looks done?" for e in rig.since(m))
        assert not rig.s.confirm_check_ids

    run(go())
