"""Desktop test 7 (Demo mode, Nov 15 03:54-03:59): the cards' payloads and copy.

  5. The Not yet card on the stuck run read "yours 0.49 / expected —" and its citation was cut ("Goodfellow et al.,
     Deep Learning §8.4 (br…"); a crashed run must never show an older run's loss.
  6. The completion card said "You built a neural net"; nothing may say "Lesson complete".
  7. Copy: no markdown backticks, no sentence cut with "…", runs named in plain words ("Ran nn.py").

The app-side readers below mirror app/src/renderer/src/features/cards/{Evidence,code}.ts (adrian/shell #124):
yoursValue reads a failing check's detail, expectedValue its label, and the loss curve's expected cell is the last
point of the metric series with runId "tutorial".
Run from the repo root:  python -m pytest server/orchestrator/tests/test_t7_cards.py -q"""

from __future__ import annotations

import asyncio
import re

from server.checks.evaluator import RunContext, evaluate_check
from server.coach import common
from server.coach.diagnose import _lesson_action
from server.orchestrator import card_copy, curated, lesson_end, stage
from server.orchestrator.tests.test_stage import RANDOM, ZEROS, passed, rig, save, settle  # noqa: F401 (fixture)

# ------------------------------------------------------------------ the app's readers (Evidence.tsx, code.ts)
_READING = re.compile(r"(?:^|\s)([-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?|[-+]?(?:nan|inf(?:inity)?))\s+at step\s+\d",
                      re.I)


def app_yours(detail: str) -> str | None:
    """Evidence.tsx yoursValue, the reading branch (the one a metric row takes)."""
    m = _READING.search(detail or "")
    return m.group(1) if m else None


def app_expected(label: str) -> str | None:
    """Evidence.tsx expectedValue."""
    cmp = re.search(r"(<=|>=|==|!=|≤|≥|<|>|=)\s*([^<>=≤≥]+)$", label)
    if cmp:
        return f"{cmp.group(1)} {cmp.group(2).strip()}"
    nums = re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:e[-+]?\d+)?(?![\w])", label, re.I)
    return nums[-1] if nums else None


def run(coro):
    return asyncio.run(coro)


async def _to_train_step(rig) -> None:  # noqa: F811
    await rig.s.learn("anything", mode="demo")
    await settle(rig)
    await save(rig, ZEROS)  # the presenter's zeros shortcut
    await save(rig, "\n")
    rig.clock.t += 1
    await rig.s.action("check_step")
    await settle(rig)
    assert rig.s.step["id"] == curated.TRAIN_STEP


# ------------------------------------------------------------------ 5. the Not yet card on the stuck run
def test_stuck_not_yet_card_has_yours_expected_citation_and_actions(rig):  # noqa: F811
    async def go():
        await _to_train_step(rig)
        m = rig.mark()
        await rig.s.action("run_command")
        await settle(rig)
        ev = rig.since(m)
        types = [e["type"] for e in ev]
        off = [e["payload"] for e in ev if e["type"] == "offtrack"]
        assert off, types
        card = off[-1]
        # the failing loss row: yours 0.4900, expected 0.01 (read by the app from the detail and the label)
        row = [e["payload"] for e in ev if e["type"] == "check.updated" and e["payload"]["status"] == "fail"][-1]
        assert row["detail"] == "loss 0.4900 at step 18000, need < 0.01"
        assert app_yours(row["detail"]) == "0.4900" and app_expected(row["label"]) == "0.01"
        # the loss curve's expected cell: the lesson's own run, as runId "tutorial", sent before the card
        tut = [e["payload"] for e in ev if e["type"] == "metric" and e["payload"]["runId"] == "tutorial"]
        assert tut and tut[-1]["name"] == "loss" and tut[-1]["step"] == 18000 and tut[-1]["value"] < 0.01
        assert tut[0]["step"] == 0 and tut[0]["value"] > 0.5  # it falls, from 0.8187
        assert max(i for i, e in enumerate(ev) if e["type"] == "metric" and e["payload"]["runId"] == "tutorial") \
            < types.index("offtrack")
        # this run's own curve is the flat one (yours), never the reference
        mine = [e["payload"] for e in ev if e["type"] == "metric" and e["payload"]["runId"] != "tutorial"]
        assert mine and {p["value"] for p in mine} == {curated.STUCK_LOSS}
        # a citation that fits its line, Hint and Show me on the card, plain text
        assert card["citation"]["label"] == "Goodfellow et al. 2016, §8.4"
        assert len(card["citation"]["label"]) <= card_copy.CITE_CHARS
        assert {"hint", "show_me"} <= set(card["actions"]) and set(card["actions"]) <= set(
            card_copy.LESSON_OFFTRACK_ACTIONS)
        assert not any("`" in (card.get(k) or "") or (card.get(k) or "").endswith("…")
                       for k in ("title", "body", "guidingQuestion"))
        # the run's own card is named in plain words
        ran = [e["payload"]["title"] for e in ev if e["type"] == "card" and e["payload"]["title"].startswith("Ran ")]
        assert ran == ["Ran nn.py"]
        # random weights: the second run passes, its row says so the same way
        await save(rig, RANDOM)
        await rig.s.action("run_command")
        await settle(rig)
        assert passed(rig)[-1] == curated.TRAIN_STEP
        good = [c for c in rig.of("check.updated") if c["stepId"] == curated.TRAIN_STEP][-1]
        assert good["status"] == "pass" and re.fullmatch(r"loss 0\.\d{4} < 0\.01 at step 18000", good["detail"])
    run(go())


def test_reference_curve_is_the_lessons_own_run():
    step = next(s for s in curated.lesson_for("build a neural network", force=True)["steps"]
                if s["id"] == curated.TRAIN_STEP)
    ref = curated.reference_losses(step)
    assert [e for e, _ in ref] == list(range(0, 18001, 2000))  # as nn.py prints it, up to the check's by_step
    assert ref[0][1] > 0.8 and ref[-1][1] < 0.01 and all(a[1] >= b[1] for a, b in zip(ref, ref[1:]))


def test_metric_detail_words_like_the_checks_module():
    check = {"metric": "loss", "op": "<", "value": 0.01, "by_step": 18000}
    assert curated.metric_detail(check, [(0, 0.49), (18000, 0.49)]) == "loss 0.4900 at step 18000, need < 0.01"
    assert curated.metric_detail(check, [(0, 0.8187), (18000, 0.0009)]) == "loss 0.0009 < 0.01 at step 18000"
    assert curated.metric_detail(check, []) is None  # a crash printed no loss: nothing to show


def test_a_crashed_run_says_it_has_no_loss():
    check = {"id": "c", "type": "metric_threshold", "label": "Loss falls below 0.01", "metric": "loss", "op": "<",
             "value": 0.01, "metric_pattern": r"epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>[0-9.eE+-]+)"}
    crashed = RunContext(exit_code=1, output_tail=["NameError: name 'forward' is not defined"])
    r = evaluate_check(check, crashed)
    detail = r["detail"] if isinstance(r, dict) else r.detail
    assert detail == "no loss: the run stopped with an error"
    assert app_yours(detail) is None  # no yours value: no row with an older run's number
    clean = RunContext(exit_code=0, output_tail=["done"])
    r = evaluate_check(check, clean)
    assert (r["detail"] if isinstance(r, dict) else r.detail) == "the run printed no loss"


# ------------------------------------------------------------------ 6. the completion card
def test_completion_card_is_plain(rig):  # noqa: F811
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        for _ in range(6):
            assert await stage.next_step(rig.s)
            await settle(rig)
        assert lesson_end.finished(rig.s)
        card = lesson_end.card(rig.s)
        assert card["title"] == "Neural networks · 8 skills mastered"
        text = f"{card['title']} {card['body']} {card['skillMap']['headline']}"
        for slop in ("You built", "Lesson complete", "Lesson finished", "You finished", "You reached"):
            assert slop not in text
        assert "1-4-4-1" in card["body"] and re.search(r"Loss 0\.819 → 0\.000\d+ in your last run\.", card["body"])
        # node details and the cross-track notes stay in the payload (the app shows them on click)
        assert all(n.get("detail") for n in card["skillMap"]["nodes"])
        assert card["skillMap"]["cross"] and all(c.get("note") for c in card["skillMap"]["cross"])
        assert card["skillMap"]["track"] == "Neural networks"
    run(go())


def test_completion_title_without_mastery_is_the_lessons_title():
    assert lesson_end.title({"title": "A neural net from scratch", "goal": "x"}) == "A neural net from scratch"
    assert lesson_end.title({"goal": "build a to-do app in React"}) == "Build a to-do app in React"
    assert lesson_end.title({}) == "All steps done"
    assert lesson_end.mastery_title({"track": "React", "nodes": [{"state": "next"}]}) is None
    assert lesson_end.mastery_title({"track": "React", "nodes": [{"state": "mastered"}]}) == "React · 1 skill mastered"


# ------------------------------------------------------------------ 7. plain copy
def test_ran_names_the_file():
    assert card_copy.ran("python3 nn.py") == "Ran nn.py"
    assert card_copy.ran(".venv/bin/python nn.py") == "Ran nn.py"
    assert card_copy.ran('"/a b/.venv/bin/python" "/a b/nn.py"') == "Ran nn.py"  # VS Code's ▷
    assert card_copy.ran("cd /x && python3 main.py") == "Ran main.py"
    assert card_copy.ran("npm test") == "Ran npm test"
    assert card_copy.ran("python -m pytest") == "Ran python -m pytest"


def test_card_text_is_plain():
    assert card_copy.plain("`forward` defined after the **training** loop") == "forward defined after the training loop"
    assert card_copy.plain("```python\nx = 1\n```") == "x = 1\n"
    cut = "Your run stopped early. In VS Code, move the data, weights, forward and backward under #…"
    assert card_copy.whole_sentences(cut) == "Your run stopped early."
    assert card_copy.whole_sentences("Saved. Running it again…") == "Saved. Running it again…"  # a status line
    assert card_copy.short_citation("Goodfellow et al., Deep Learning §8.4 (breaking symmetry)") == \
        "Goodfellow et al., Deep Learning §8.4"
    assert card_copy.short_citation("NumPy broadcasting explained in plain words - Real Python") == \
        "NumPy broadcasting explained in plain words"


def test_lesson_offtrack_offers_hint_and_show_me():
    from types import SimpleNamespace as NS

    s = NS(lesson_mode=True)
    p = {"title": "`forward` defined after the training loop", "body": "Move it up.", "actions": ["explain", "apply_fix"],
         "citation": {"label": "A long page title about tanh (and its slope)", "url": "https://x"}}
    card_copy.plain_copy(s, "offtrack", p)
    assert p["title"] == "forward defined after the training loop"
    assert p["actions"] == ["explain", "show_me", "hint", "apply_fix"]
    assert p["citation"] == {"label": "A long page title about tanh", "url": "https://x"}


def test_coach_never_cuts_a_sentence():
    card = {"body": "forward runs before it is defined. In VS Code, move the data, weights, forward and backward "
                    "under # The network, above the training loop in nn.py."}
    _lesson_action(card)
    assert card["body"].startswith("In VS Code, move") and card["body"].endswith("in nn.py.")
    long_cause = " ".join(["The weights all start at zero so every neuron computes the same thing."] * 4)
    body = common.clamp_body(f"{long_cause} Start W1, W2 and W3 random.")
    assert "…" not in body and body.endswith("Start W1, W2 and W3 random.") and len(body.split()) <= 42


def test_steps_typed_by_do_it_for_me_are_practiced_not_mastered():
    from types import SimpleNamespace as NS

    from server.lesson import skillmap

    graph = curated.lesson_for("build a neural network", force=True)
    ids = [s["id"] for s in graph["steps"]]
    s = NS(graph=graph, steps=graph["steps"], idx=len(ids) - 1, passed=True, skipped_steps=[], assisted_steps=["nn2"],
           phase="done", waiting_more=False)
    res = skillmap.session_results(s)
    assert res["passed"] == ids and res["assisted"] == ["nn2"]
    m = skillmap.skill_map(graph, res)
    nodes = {n["id"]: n for n in m["nodes"]}
    assert nodes["backpropagation"]["state"] == "learning"
    assert nodes["backpropagation"]["detail"] == "Step 2 typed by Do it for me"
    assert nodes["forward-pass"]["state"] == "mastered"
    assert lesson_end.mastery_title(m) == "Neural networks · 6 skills mastered"
