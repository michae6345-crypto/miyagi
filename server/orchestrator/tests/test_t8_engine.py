"""Desktop test 8 (Nov 15, "Just teach me" neural-net lesson), offline: a fake screen, fake Accessibility rows and a
fake VS Code companion. Run from the repo root:  python -m pytest server/orchestrator/tests/test_t8_engine.py -q

1. The "Not yet" cards carry the culprit lines as offtrack.targets (offtrack_targets.py): the app's card steps off them.
2. The curated math rows say what's wrong and where ("needs 1 - h2 ** 2 on line 25, not 1 + h2 ** 2"), never "not in
   nn.py yet" while the code is there.
3. A curated lesson's lesson.ready says builtBy "curated" (the app shows no "Claude wrote this lesson").
A/B (frame review): the loss row reads the run's LAST printed row as nn.py prints it, plain words in rows and cards.
"""
from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace as NS

from server.checks import evaluator
from server.orchestrator import card_copy, curated, lesson_end, offtrack_targets, run_pointing
from server.orchestrator.session import LessonSession
from server.orchestrator.tests.test_box_fresh import NN2_DONE, _boxes, _demo_at as _box_demo_at, _rig as _box_rig
from server.orchestrator.tests.test_box_fresh import vs  # noqa: F401 (fixture)
from server.orchestrator.tests.test_run_pointing import FakeExt, _demo_at, _demo_rig, _line_of, _rows_after_reveal
from server.orchestrator.tests.test_run_pointing import fast  # noqa: F401 (fixture)
from server.orchestrator.tests.test_stage import RANDOM, ZEROS, rig, save, settle  # noqa: F401 (fixture)
from shared.contracts.events import validate_engine_payload

TOP, PITCH = 200.0, 18.0


def run(coro):
    return asyncio.run(coro)


def offtracks(events: list[dict]) -> list[dict]:
    return [e["payload"] for e in events if e["type"] == "offtrack"]


def _rows_on_screen(monkeypatch) -> None:
    """Every line of nn.py on screen, as VS Code's gutter / Accessibility gives its row (no scroll needed)."""
    monkeypatch.setattr(run_pointing, "_line_location",
                        lambda s, path, line: {"rect": {"x": 330.0, "y": TOP + line * PITCH, "w": 700.0, "h": PITCH}})


# ------------------------------------------------------------------------------- 1. offtrack targets

def test_stuck_not_yet_carries_the_w1_to_w3_lines_as_its_targets(tmp_path, monkeypatch, fast):  # noqa: F811
    """t8 05:52:50 nn4 "All weights start at zero" went out with no targets and the card sat on the W1 line."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    _rows_on_screen(monkeypatch)

    async def go():
        await _demo_at(rig, 3)
        m = rig.mark()
        await rig.s.action("run_command")  # the planned stuck run
        await rig.settle()
        return rig.since(m)

    ev = run(go())
    off = offtracks(ev)
    assert off, [e["type"] for e in ev]
    w1, w3 = _line_of(rig, "W1 ="), _line_of(rig, "W3 =")
    t = off[0].get("targets")  # the first send already has them: the lines were on screen
    assert t and len(t) == 1, off[0]
    t = t[0]
    assert t["boxId"] == 0 and t["label"] == "Look at how W1, W2 and W3 start"
    assert t["text"].splitlines() == ["W1 = np.zeros((1, 4))", "W2 = np.zeros((4, 4))", "W3 = np.zeros((4, 1))"]
    assert t["rect"] == {"x": 330.0, "y": TOP + w1 * PITCH, "w": 700.0, "h": (w3 - w1 + 1) * PITCH}
    validate_engine_payload("offtrack", off[0])  # the contract's offtrack.targets shape
    # a reconnect's replay still sends the off-track without targets (0d7ca61: a rect from before is stale)
    replayed = [p for typ, p in rig.s.snapshot() if typ == "offtrack"]
    assert replayed and "targets" not in replayed[-1]


def test_culprit_measured_on_hint_reaches_the_offtrack_once_the_hint_card_closes(tmp_path, monkeypatch, fast):  # noqa: F811
    """The W1..W3 lines are scrolled off when the Not yet goes out (no targets: nothing of them is under the card);
    Hint scrolls there and boxes them while its own card is up, so the off-track isn't re-sent on top of that card;
    once the learner closes it, the off-track (back on top in the app) goes again with those lines as its target."""
    rig, _ = _demo_rig(tmp_path, monkeypatch)
    ext = FakeExt()
    rig.s._vscode_ext = lambda: ext
    _rows_after_reveal(monkeypatch, ext, top=TOP, pitch=PITCH)

    async def go():
        await _demo_at(rig, 3)
        await rig.s.action("run_command")
        await rig.settle()
        first = offtracks(rig.events)
        m = rig.mark()
        await rig.s.action("hint")
        await rig.settle()
        on_hint = rig.since(m)
        m2 = rig.mark()
        hint = [c for c in rig.of("card") if c.get("kind") == "hint"][-1]
        await rig.s.card_seen(False, "nn4", hint["title"], kind="hint", by="user")
        await rig.settle()
        return first, on_hint, rig.since(m2)

    first, on_hint, closed = run(go())
    assert first and "targets" not in first[-1]
    box = [e["payload"] for e in on_hint if e["type"] == "spotlight" and e["payload"].get("rect")][-1]
    assert box["caption"] == "Look at how W1, W2 and W3 start"
    assert not offtracks(on_hint)  # never on top of the hint card
    again = offtracks(closed)
    assert len(again) == 1 and again[0]["title"] == first[-1]["title"]
    assert again[0]["targets"][0]["rect"] == box["rect"] and again[0]["targets"][0]["label"] == box["caption"]


def test_diagnosed_line_goes_out_as_the_offtracks_target_after_the_scroll(tmp_path, vs):  # noqa: F811
    """t8 05:51:31 nn2 "Wrong sign in d_h2 tanh slope … line 25": the card went out, then its line was found, scrolled
    into view and boxed, and the card never heard of it. Now the same off-track goes again with that box as its target
    (measured after the scroll); a card that took its place since holds the next one until it closes."""
    rig = _box_rig(tmp_path, vs)
    vs.lag = 0.2
    wrong = "    d_h2 = d_out @ W3.T * (1 + h2 ** 2)"
    bad = NN2_DONE.replace("(1 - h2 ** 2)", "(1 + h2 ** 2)")
    n = bad.split("\n").index(wrong) + 1

    async def go():
        await _box_demo_at(rig, vs, bad, "nn3")
        await asyncio.sleep(0.4)
        vs.scroll(33)  # the line is far above the screen
        step = rig.s.step
        full = {"stepId": step["id"], "severity": "fail", "title": "Wrong sign in d_h2 tanh slope",
                "body": f"In VS Code, change + to - on line {n} of nn.py.", "actions": ["explain", "hint"],
                "diff": {"yours": wrong, "expected": wrong.replace("+", "-")}}
        m = rig.mark()
        await rig.s._offer_offtrack(rig.s.step_gen, step, [], set(), 3, full, dict(full))
        await rig.settle()
        ev = rig.since(m)
        # a card takes the off-track's place; a box measured now waits for that card to close
        await rig.s.emit("card", {"stepId": step["id"], "kind": "hint", "title": "Look at line 25", "body": "Look."})
        m2 = rig.mark()
        sent = await offtrack_targets.update(rig.s, {"x": 1.0, "y": 2.0, "w": 300.0, "h": 18.0}, "Look here", wrong)
        held = rig.since(m2)
        await rig.s.card_seen(False, step["id"], "Look at line 25", kind="hint", by="user")
        return ev, sent, held, rig.since(m2)

    ev, sent, held, after = run(go())
    types_ = [e["type"] for e in ev]
    off = offtracks(ev)
    assert len(off) == 2 and "targets" not in off[0], types_
    assert types_.index("offtrack") < types_.index("spotlight") < len(types_) - 1 - types_[::-1].index("offtrack")
    box = _boxes(rig, 0)[-1]
    t = off[1]["targets"]
    assert t == [{"boxId": 0, "label": box["caption"], "text": wrong.strip(), "rect": box["rect"]}]
    assert abs(t[0]["rect"]["y"] - vs.row_y(n)) <= 2.0  # the row after VS Code scrolled there
    assert {k: v for k, v in off[1].items() if k != "targets"} == off[0]  # the same card, now with its target
    assert off[0]["body"].startswith("Change + to - on line")  # B: the fix first, no "In VS Code, "
    assert not sent and not offtracks(held)
    late = offtracks(after)
    assert len(late) == 1 and late[0]["targets"][0]["rect"] == {"x": 1.0, "y": 2.0, "w": 300.0, "h": 18.0}


# ------------------------------------------------------------------------------- 2. the math rows

STEPS = {s["id"]: s for s in curated.lesson_for("x", force=True)["steps"]}
NN = (curated.STARTER_FILE.read_text(encoding="utf-8")
      .replace("# The network\n", "# The network\n" + STEPS["nn1"]["code"] + "\n")
      .replace("# Backprop\n", "# Backprop\n" + STEPS["nn2"]["code"] + "\n")
      .replace("# Training\n", "# Training\n" + STEPS["nn3"]["code"] + "\n"))


def _n(text: str, line: str) -> int:
    return next(i for i, ln in enumerate(text.splitlines(), 1) if ln.strip() == line)


def test_math_rows_say_whats_wrong_and_where():
    def say(cid, old, new):
        text = NN.replace(old, new)
        return curated.math_detail(cid, text.splitlines()), text

    assert all(curated.math_detail(cid, NN.splitlines()) is None for cid in curated.MATH_PARTS)  # right: as it was
    d, t = say("nn2c4", "(1 - h2 ** 2)", "(1 + h2 ** 2)")  # t8's nn2c4
    assert d == f"needs 1 - h2 ** 2 on line {_n(t, 'd_h2 = d_out @ W3.T * (1 + h2 ** 2)')}, not 1 + h2 ** 2"
    d, t = say("nn2c4", "d_out @ W3.T * (1 - h2 ** 2)", "d_out @ W3.T")
    assert d == f"needs the tanh slope * (1 - h2 ** 2) on line {_n(t, 'd_h2 = d_out @ W3.T')}"
    d, t = say("nn2c3", "2 * (out - y) / len(X)", "2 * (y - out) / len(X)")
    assert d == f"needs 2 * (out - y) / len(X) on line {_n(t, 'd_out = 2 * (y - out) / len(X)')}, not 2 * (y - out) / len(X)"
    assert say("nn2c2", "d_out @ W3.T", "d_out @ W3")[0].startswith("needs d_out @ W3.T on line ")
    assert say("nn1c4", "return h1, h2, h2 @ W3 + b3", "return h1, h2, np.tanh(h2 @ W3 + b3)")[0].endswith(
        ", not np.tanh(h2 @ W3 + b3)")
    assert say("nn3c2", "W1 -= lr * dW1", "W1 += lr * dW1")[0].endswith(", not W1 += lr * dW1")
    assert say("nn3c2", "    b3 -= lr * db3\n", "")[0] == "still needs b3 -= lr * db3"
    assert say("nn3c4", "np.mean((out - y) ** 2)", "np.mean(out - y)")[0].startswith("needs np.mean((out - y) ** 2)")
    # the code really isn't there: the row's own "not in nn.py yet" stands
    assert curated.math_detail("nn2c4", curated.STARTER_FILE.read_text(encoding="utf-8").splitlines()) is None
    assert curated.math_detail("nn1c1", NN.splitlines()) is None  # not a math row


def test_math_details_never_read_as_the_learners_code_in_the_app():
    """The app's Not yet evidence takes a failing row's detail as "yours" unless it opens like status text (app
    features/cards/code.ts isProse: LEAD words); "line 25 has 1 + h2 ** 2" would have shown as code with expected 1."""
    lead = re.compile(r"^(?:not|no|missing|still|waiting|need|needs|run)(?=\s+[^\s=+\-*/%<>!&|^.,:;)\]}])", re.I)
    for cid, old, new in [("nn2c4", "(1 - h2 ** 2)", "(1 + h2 ** 2)"), ("nn2c4", " * (1 - h1 ** 2)", ""),
                          ("nn3c2", "    b3 -= lr * db3\n", ""), ("nn2c3", "(out - y)", "(y - out)")]:
        d = curated.math_detail(cid, NN.replace(old, new).splitlines())
        assert d and lead.match(d), d


def test_just_teach_me_check_names_the_wrong_sign_on_its_line(rig):  # noqa: F811
    """t8 05:51:25: nn2c4 failed with "not in nn.py yet" on `d_h2 = d_out @W3.T* (1 + h2 ** 2)`."""
    bad = NN.split("# Training")[0].replace("d_out @ W3.T * (1 - h2 ** 2)", "d_out @W3.T* (1 + h2 ** 2)")

    async def go():
        await rig.s.learn("build a neural network", mode="lesson")
        await settle(rig)
        await rig.s.goto_step(1)
        await settle(rig)
        assert rig.s.step["id"] == "nn2"
        (rig.workdir / "nn.py").write_text(bad, encoding="utf-8")
        rig.clock.t += 30
        await rig.s.action("check_step")
        await settle(rig)

    run(go())
    # (no screen here: the drawer shows the files route's rows, nn2p4 for the screen's nn2c4: the same math)
    rows = [p for p in rig.of("check.updated") if p["checkId"] in ("nn2c4", "nn2p4") and p["status"] == "fail"]
    n = _n(bad, "d_h2 = d_out @W3.T* (1 + h2 ** 2)")
    assert rows and rows[-1]["detail"] == f"needs 1 - h2 ** 2 on line {n}, not 1 + h2 ** 2", rows
    assert not [p for p in rig.of("check.updated") if "not in" in (p.get("detail") or "")]
    assert {"nn1c4", "nn1p4", "nn2p4", "nn3p2"} <= set(curated.MATH_PARTS) and "nn3p3" not in curated.MATH_PARTS


# ------------------------------------------------------------------------------- 3. builtBy

def test_curated_lessons_are_not_written_by_claude(rig):  # noqa: F811
    async def go():
        out = []
        for mode in ("lesson", "demo"):
            await rig.s.learn("build a neural network", mode=mode)
            await settle(rig)
            out.append(rig.of("lesson.ready")[-1]["lesson"])
        return out

    for lesson in run(go()):
        assert lesson["builtBy"] == "curated" and lesson["mode"] == "lesson"
    # a lesson saved before (its graph still says "claude") goes out as curated too
    rig.s.graph = curated.lesson_for("x", force=True)
    rig.s.graph["lesson"]["builtBy"] = "claude"
    assert rig.s._lesson_ready_payload()["lesson"]["builtBy"] == "curated"
    assert json.loads(curated.LESSON_FILE.read_text(encoding="utf-8"))["lesson"]["curated"] == curated.KEY


# ------------------------------------------------------------------------------- A / B: the frame review

def test_loss_row_reads_the_last_printed_row():
    """t8 05:53:37 "loss 0.0013 < 0.01 at step 18000": 0.0013 was the epoch-14000 line (the checks module's 3-point
    median); nn.py's last line said "epoch 18000  loss 0.0009"."""
    lines = [f"epoch {e:5d}  loss {v:.4f}" for e, v in
             [(0, 0.8187), (2000, 0.0901), (12000, 0.0018), (14000, 0.0013), (16000, 0.0011), (18000, 0.0009)]]
    step = STEPS[curated.TRAIN_STEP]
    session = NS(step_runs=[NS(run_id="vscode-1", output_tail=lines, metrics={}, running=False)])
    results = [{"checkId": "nn4c1", "label": "Loss falls below 0.01", "status": "pass",
                "detail": "loss 0.0013 < 0.01 at step 18000"}]
    assert curated._loss_rows(session, step, results)[0]["detail"] == "loss 0.0009, below 0.01"
    stuck = [ln.replace(ln.split()[-1], "0.4900") for ln in lines]
    session.step_runs[0].output_tail = stuck
    fail = [{**results[0], "status": "fail", "detail": "loss 0.49 at step 18000, need < 0.01 by step 18000"}]
    assert curated._loss_rows(session, step, fail)[0]["detail"] == "loss 0.4900 at epoch 18000, need < 0.01"  # the app's
    assert curated._loss_rows(session, step, results)[0]["detail"] == results[0]["detail"]  # verdicts differ: as it was


def test_values_are_plain_decimals_as_printed():
    assert evaluator._fmt(9e-4) == "0.0009" and evaluator._fmt(0.0013) == "0.0013" and evaluator._fmt(0.49) == "0.49"
    assert evaluator._fmt(1.234e-5) == "0.00001234" and "e" not in evaluator._fmt(123456.0)
    assert lesson_end._fmt(0.8187) == "0.8187" and lesson_end._fmt(0.0009) == "0.0009" and lesson_end._fmt(9e-5) == "0.00009"
    assert curated._fmt(0.0009) == "0.0009" and curated._fmt(0.8187) == "0.8187"
    c = {"id": "m", "type": "metric_threshold", "label": "loss < 0.3", "metric": "loss", "app": "Terminal",
         "metric_pattern": r"epoch (?P<step>\d+) loss (?P<value>\S+)", "op": "<", "value": 0.3}
    r = evaluator.evaluate_check(c, evaluator.RunContext(screen={"Terminal": ["$ python train.py"]}, segment_done=True))
    assert r["detail"] == "waiting for the run's loss lines in Terminal"  # never "waiting for 'loss'"


def test_not_yet_starts_with_the_fix():
    assert card_copy.fix_first("In VS Code, change + to - on line 25 of nn.py.") == "Change + to - on line 25 of nn.py."
    assert card_copy.fix_first("Every neuron is the same. In VS Code, start W1 random.") == \
        "Every neuron is the same. Start W1 random."
    s = NS(lesson_mode=True, step=None)
    p = {"title": "Wrong sign", "body": "In VS Code, change + to - on line 25 of nn.py.", "actions": ["hint"]}
    card_copy.plain_copy(s, "offtrack", p)
    assert p["body"] == "Change + to - on line 25 of nn.py."
    video = {"title": "Wrong sign", "body": "In VS Code, change + to - on line 25.", "actions": ["hint"]}
    card_copy.plain_copy(NS(lesson_mode=False, step=None), "offtrack", video)
    assert video["body"].startswith("In VS Code, ")  # a video lesson: the place still matters


def test_run_step_names_the_run_button(rig):  # noqa: F811
    async def go():
        await rig.s.learn("build a neural network", mode="lesson")
        await settle(rig)
        await rig.s.goto_step(3)
        await settle(rig)
        step = rig.s.step
        assert step["id"] == "nn4"
        return rig.s._action_line(step), rig.s._run_how(step, rig.s._run_command(step))

    line, how = run(go())
    assert line == "Click ▷ to run nn.py (or run python3 nn.py in the terminal)"
    assert how == line  # no "(or press Run it for me)": outside a Demo no Run it for me button is up
    rows = [p for p in rig.of("check.updated") if p["checkId"] == "nn4-ran" and p.get("detail")]
    assert all("Run it for me" not in p["detail"] for p in rows)


def test_run_row_passed_by_the_files_route_says_the_run_printed_it():
    """nn6's "It answers -1, 0, 1" (a Terminal row) went green as "confirmed by your files": its files route checks
    the run's output, so it says so."""
    assert LessonSession._run_row_ids(STEPS["nn6"]) == {"nn6c1"}
    assert LessonSession._run_row_ids(STEPS["nn1"]) == set()  # code rows: "confirmed by your files" as before
