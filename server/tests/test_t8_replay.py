"""Desktop test 8 (Nov 15 05:48-05:54, "Just teach me" neural-net lesson), replayed offline end to end.

Run from the repo root:  python -m pytest server/tests/test_t8_replay.py -q

The real LessonSession (the real checks module, curated.py, run_pointing, box_follow, card_copy, lesson_end) on a temp
lesson folder; around it only fakes: the fake VS Code of test_box_fresh (Accessibility rows that follow its scroll, the
companion's /state, /open and buffer), a FakeScreen whose Run ▷ region is VS Code's editor-title button, VS Code's
command_end for the ▷ runs (curated.on_command_end, as POST /vscode/event routes it) with the recorded real NumPy output
of nn.py (demo/cache/stage/nn-runs.json), and a coach model that answers what Claude answered in test 8. No network.

The sequence (t8 checkpoints.log CP2-CP10, engine-t8.log):
  nn1  Just teach me -> fresh nn.py, the box on line 5 under # The network; Start; paste + save -> pass
  nn2  box under # Backprop (line 23); paste with the sign bug (1 + h2 ** 2) -> the math row names line 25, Not yet
       "Wrong sign in d_h2 tanh slope ... line 25", Hint boxes line 25; the fix -> nn2 passes
  nn3  box under # Training (line 31); paste -> pass
  nn4  the ▷ box; W1-W3 at zeros, ▷ -> loss 0.4900 on every line: Not yet "All weights start at zero", the loss row
       "0.4900 ... need < 0.01"; Hint 1 of 2 boxes the W1-W3 lines; random weights again -> the ▷ box is back;
       ▷ -> 0.8187 to 0.0009, nn4 passes
"""
from __future__ import annotations

import asyncio
import json
import re

import pytest

from server.orchestrator import curated, quiet_save, run_pointing, stage, typo_card
from server.orchestrator import workspace as wsmod
from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.conftest import _isolated_and_free  # noqa: F401 (autouse: no paid keys, temp state)
from server.orchestrator.tests.test_box_fresh import NN1_DONE, STARTER, STEPS, _pasted
from server.orchestrator.tests.test_box_fresh import vs  # noqa: F401 (fixture: the fake VS Code)
from server.orchestrator.tests.test_curated_panel import is_preview, is_run
from server.orchestrator.tests.test_run_pointing import RUN_BTN, TERMINAL, _code_window
from server.orchestrator.tests.test_session import Rig
from server.workspace import vscode_ext

RUNS = json.loads(stage.RUNS_FILE.read_text(encoding="utf-8"))  # real NumPy output of the lesson's nn.py
SIGN_BUG = "    d_h2 = d_out @ W3.T * (1 + h2 ** 2)"
NN2_BUG = _pasted(NN1_DONE, "# Backprop", STEPS["nn2"]["code"].replace("(1 - h2 ** 2)", "(1 + h2 ** 2)"))
NN2_FIXED = NN2_BUG.replace("(1 + h2 ** 2)", "(1 - h2 ** 2)")
NN3_DONE = _pasted(NN2_FIXED, "# Training", STEPS["nn3"]["code"])
W_RANDOM = ["W1 = np.random.randn(1, 4)", "W2 = np.random.randn(4, 4)", "W3 = np.random.randn(4, 1) * 0.1"]
W_ZEROS = ["W1 = np.zeros((1, 4))", "W2 = np.zeros((4, 4))", "W3 = np.zeros((4, 1))"]


def _zeros(text: str) -> str:
    for a, b in zip(W_RANDOM, W_ZEROS):
        text = text.replace(a, b)
    return text


def _line(text: str, line: str) -> int:
    return next(i for i, ln in enumerate(text.split("\n"), 1) if ln.strip() == line.strip())


# ------------------------------------------------------------------------------------------------------ the fakes

class T8Coach:
    """The coach model as it answered in test 8 (engine-t8.log 05:51:31 and 05:52:50), from the code it is shown."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def diagnose(self, step, failed_checks, metrics, code_excerpt, **kw):
        self.calls.append(step["id"])
        if "(1 + h2 ** 2)" in code_excerpt:
            n = _line(code_excerpt, SIGN_BUG) if SIGN_BUG.strip() in code_excerpt else 25
            return {"severity": "fail", "title": "Wrong sign in d_h2 tanh slope",
                    "body": f"In VS Code, change + to - on line {n} of nn.py.",
                    "actions": ["explain", "show_me", "hint", "apply_fix"],
                    "diff": {"yours": SIGN_BUG.strip(), "expected": SIGN_BUG.strip().replace("+", "-")}}
        if "np.zeros((1, 4))" in code_excerpt and step["id"] == curated.TRAIN_STEP:
            return {"severity": "warn", "title": "All weights start at zero",
                    "body": "In VS Code, initialize W1, W2 and W3 randomly in nn.py.",
                    "actions": ["explain", "show_me", "hint", "apply_fix"]}
        return {"notStarted": True, "title": "Start here", "body": step.get("instructions", "")}


def _command_end(rig: Rig, lines: list[str], seq: int) -> dict:
    """VS Code's command_end for the Run ▷ (the companion's shell integration), as POST /vscode/event receives it."""
    py = f"{rig.workdir}/.venv/bin/python"
    started = int((rig.s._step_wall_t0 + 1) * 1000)
    return {"type": "command_end", "seq": seq, "folders": [str(rig.workdir)],
            "command": {"id": seq, "commandLine": f"{py} {rig.workdir}/nn.py", "cwd": str(rig.workdir),
                        "exitCode": 0, "outputTail": list(lines), "startedAt": started}}


@pytest.fixture
def t8(tmp_path, vs, monkeypatch):  # noqa: F811
    """The session as test 8 ran it: real checks, the fake VS Code, the ▷ on screen, the t8 coach."""
    monkeypatch.setattr(run_pointing, "RETRY_S", (0.01, 0.01, 0.01, 0.01))
    monkeypatch.setattr(run_pointing, "SLOW_S", 0.01)
    monkeypatch.setattr(run_pointing, "REVEAL_WAIT_S", 0.15)  # the fake VS Code scrolls 0.05 s after /open
    monkeypatch.setattr(curated, "ADOPT_AFTER_S", 0.0)
    vs.lag = 0.05
    screen = FakeScreen()
    screen.reader = type("Reader", (), {})()  # "the real screen reader is running": AX rows, the companion
    screen.regions = {"terminal": dict(TERMINAL), "run_button": dict(RUN_BTN)}
    rig = Rig(tmp_path, screen=screen, modules=Modules(demo=False, force_stubs="lesson,coach,finder,diagrams"))
    ws = wsmod.Workspace(enabled=False, runner=lambda argv: True)
    ws.goto = vs.cli_goto
    rig.s.workspace = ws
    coach = T8Coach()
    rig.s.m.diagnose = coach.diagnose
    rig.coach = coach
    rig.vs = vs
    vscode_ext.reset_events()
    yield rig
    vscode_ext.reset_events()


def run(coro):
    return asyncio.run(coro)


async def settle(rig: Rig, secs: float = 0.0) -> None:
    for _ in range(4):
        await rig.settle()
        await asyncio.sleep(0)
    if secs:
        await asyncio.sleep(secs)
        for _ in range(2):
            await rig.settle()
            await asyncio.sleep(0)


async def save(rig: Rig, text: str) -> None:
    rig.clock.t += 5
    p = rig.workdir / "nn.py"
    p.write_text(text, encoding="utf-8")
    await rig.s.on_file_change([str(p)])
    await settle(rig, 0.3)


async def tick(rig: Rig, n: int, dt: float = 1.0) -> None:
    for _ in range(n):
        rig.clock.t += dt
        await rig.s.tick()
        await settle(rig)
    await settle(rig, 0.1)


async def frame(rig: Rig) -> None:
    """A new screen frame with the lesson's VS Code window in front (the screen reader's on_screen)."""
    await rig.s.on_screen(_code_window(f"nn.py — {rig.workdir.name}"))
    await settle(rig, 0.1)


async def vscode_run(rig: Rig, lines: list[str]) -> None:
    """The learner clicks the real ▷: VS Code runs nn.py and its companion posts the command_end, routed as
    main.vscode_event routes it (recorded for the session's run row, curated's run, the typo card)."""
    rig.runs_done = getattr(rig, "runs_done", 0) + 1
    item = vscode_ext.record_event(_command_end(rig, lines, rig.runs_done))
    quiet_save.on_vscode_event(rig.s, item)
    if curated.active(rig.s):
        rig.s._spawn(curated.on_command_end(rig.s, item))
    rig.s._spawn(typo_card.on_vscode_event(rig.s, item))
    await tick(rig, 4)


def boxes(events: list[dict]) -> list[dict]:
    return [e["payload"] for e in events if e["type"] == "spotlight" and e["payload"].get("rect")]


def of(events: list[dict], type_: str) -> list[dict]:
    return [e["payload"] for e in events if e["type"] == type_]


def near(rig: Rig, box: dict, line: int, top: int | None = None) -> bool:
    """The box sits on `line`'s row (as the fake VS Code shows it now, or scrolled to `top`)."""
    return abs(box["rect"]["y"] - rig.vs.row_y(line, top)) <= 2.0


def box_up_at(rig: Rig, events: list[dict], line: int, top: int) -> bool:
    """The box up at the end of `events` is on `line` (the last spotlight is a box, not a clear)."""
    sp = of(events, "spotlight")
    return bool(sp) and "rect" in sp[-1] and near(rig, sp[-1], line, top)


def rows(events: list[dict], step: str) -> dict[str, dict]:
    """The latest check row of each check of `step` in `events`."""
    return {p["checkId"]: p for p in of(events, "check.updated") if p["stepId"] == step}


def no_stale(events: list[dict]) -> None:
    """Nothing about a step goes out once it passed: no off-track, hint / answer card or check row of a done step
    (the completion card is a "step" card of the last step)."""
    done: set[str] = set()
    for e in events:
        p, t = e["payload"], e["type"]
        if t == "step.passed":
            done.add(p["stepId"])
        elif t in ("offtrack", "check.updated") and p.get("stepId") in done:
            raise AssertionError(f"{t} for {p['stepId']} after it passed: {json.dumps(p)[:200]}")
        elif t == "card" and p.get("stepId") in done and p.get("kind") != "step":
            raise AssertionError(f"card for {p['stepId']} after it passed: {json.dumps(p)[:200]}")


def previews_only_until_a_run(events: list[dict], first_run: int) -> None:
    """t7 item 7: a preview never carries epoch / loss, and nothing before the learner's first real run (the event
    mark `first_run`) is a run's picture."""
    for i, e in enumerate(events):
        if e["type"] != "diagram" or e["payload"].get("kind") != "network":
            continue
        d = e["payload"]
        if d["data"].get("preview"):
            assert is_preview(d), json.dumps(d)[:300]
        else:
            assert i >= first_run, "a run's picture before any run: " + json.dumps(d)[:300]
            assert is_run(d) or d["data"].get("mode") == "stuck", json.dumps(d)[:300]


# ------------------------------------------------------------------------------------------------------ the replay

async def just_teach_me_nn1_to_nn4(rig: Rig) -> dict:
    """CP2-CP9. -> the event mark at each beat."""
    rig.vs.loop = asyncio.get_running_loop()
    nn = rig.workdir / "nn.py"
    at: dict[str, int] = {}
    # CP2: Just teach me -> a fresh nn.py, the box on line 5 under # The network (also before Start)
    await rig.s.learn("build a neural network", mode="lesson")
    rig.s.last_obs = _code_window(f"nn.py — {rig.workdir.name}")
    rig.s.editor_open = True
    await settle(rig, 0.4)
    assert nn.read_text(encoding="utf-8") == STARTER
    # CP3: Start
    at["start"] = rig.mark()
    await rig.s.action("start")
    await settle(rig, 0.4)
    # CP4: paste nn1, save -> pass; nn2's box under # Backprop
    at["nn1"] = rig.mark()
    await save(rig, NN1_DONE)
    await tick(rig, 2)
    # CP5: nn2 pasted with the sign bug -> the math row, Not yet on line 25, Hint
    at["nn2"] = rig.mark()
    await save(rig, NN2_BUG)
    await tick(rig, 8)
    at["nn2-hint"] = rig.mark()
    await rig.s.action("hint")
    await settle(rig, 0.3)
    # CP6: the fix -> Step 2 done; nn3's box under # Training
    at["nn2-fix"] = rig.mark()
    await save(rig, NN2_FIXED)
    await tick(rig, 2)
    # CP7: nn3 pasted -> pass; nn4's ▷ box
    at["nn3"] = rig.mark()
    await save(rig, NN3_DONE)
    await tick(rig, 2)
    await settle(rig, 0.2)
    # CP8: W1-W3 at zeros, the real ▷ -> loss 0.4900 on every line, Not yet; Hint boxes W1-W3
    at["nn4-zeros"] = rig.mark()
    await save(rig, _zeros(NN3_DONE))
    await vscode_run(rig, RUNS["nn4"]["stuck"])
    await tick(rig, 6)
    at["nn4-hint"] = rig.mark()
    await rig.s.action("hint")
    await settle(rig, 0.4)
    # CP9: random weights again -> the ▷ box is back; ▷ -> 0.8187 to 0.0009, Step 4 done
    at["nn4-fix"] = rig.mark()
    await save(rig, NN3_DONE)
    await frame(rig)
    await tick(rig, 2)
    await frame(rig)
    at["nn4-good"] = rig.mark()
    await vscode_run(rig, RUNS["nn4"]["good"])
    await tick(rig, 3)
    at["end"] = rig.mark()
    return at


def test_t8_just_teach_me_nn1_to_nn4(t8):
    rig = t8
    at = run(just_teach_me_nn1_to_nn4(rig))
    ev = rig.events

    def seg(a: str, b: str) -> list[dict]:
        return ev[at[a]:at[b]]

    # -- CP2 / CP3: the curated lesson, builtBy curated, step 1, the box on line 5
    ready = of(ev, "lesson.ready")[-1]["lesson"]
    assert ready["id"] == "lesson-nn-from-scratch" and ready["builtBy"] == "curated"
    assert of(ev, "step.started")[0]["stepId"] == "nn1"
    b = boxes(ev[:at["nn1"]])
    assert b and b[-1]["caption"] == "Type it here", b
    assert near(rig, b[-1], 5, top=1), (b[-1], "line 5, under # The network")
    # -- CP4: nn1 passes on its save, nn2 starts with its box on line 23 (under # Backprop on 22)
    s = seg("nn1", "nn2")
    assert {"stepId": "nn1", "nextStepId": "nn2"} in of(s, "step.passed")
    assert rows(s, "nn1") and all(r["status"] == "pass" for r in rows(s, "nn1").values()), rows(s, "nn1")
    assert [p["stepId"] for p in of(s, "step.started")] == ["nn2"]
    assert _line(NN1_DONE, "# Backprop") == 22
    b = boxes(s)
    assert b and b[-1]["caption"] == "Type it here" and near(rig, b[-1], 23, top=8), b
    # -- CP5: the sign bug: the math row and the Not yet card name line 25, the box is on line 25
    s = seg("nn2", "nn2-hint")
    assert _line(NN2_BUG, SIGN_BUG) == 25
    r = rows(s, "nn2")["nn2c4"]
    assert r["status"] == "fail" and r["detail"] == "needs 1 - h2 ** 2 on line 25, not 1 + h2 ** 2", r
    off = of(s, "offtrack")
    assert off and off[0]["stepId"] == "nn2" and "sign" in off[0]["title"].lower(), off
    assert "line 25" in off[0]["body"] and not off[0]["body"].startswith("In VS Code"), off[0]
    assert {"hint", "show_me"} <= set(off[0]["actions"]), off[0]["actions"]  # the app's Hint / Show me (t7 item 5)
    assert box_up_at(rig, ev[:at["nn2-hint"]], 25, top=8), boxes(s)
    assert not of(s, "step.passed")
    # Hint: about line 25, the box still on line 25
    s = seg("nn2-hint", "nn2-fix")
    hint = [c for c in of(s, "card") if c.get("kind") == "hint"]
    assert hint and "line 25" in hint[-1]["title"] + " " + hint[-1]["body"], of(s, "card")
    assert box_up_at(rig, ev[:at["nn2-fix"]], 25, top=8), boxes(ev[:at["nn2-fix"]])[-1:]
    # -- CP6: the fix passes nn2 (every row green, no Not yet again), nn3's box on line 31 under # Training
    s = seg("nn2-fix", "nn3")
    assert {"stepId": "nn2", "nextStepId": "nn3"} in of(s, "step.passed")
    assert all(r["status"] == "pass" for r in rows(s, "nn2").values()), rows(s, "nn2")
    assert not of(s, "offtrack")
    assert _line(NN2_FIXED, "# Training") == 30
    b = boxes(s)
    assert b and b[-1]["caption"] == "Type it here" and near(rig, b[-1], 31, top=16), b
    # -- CP7: nn3 passes, nn4 boxes the ▷ (+ loupe) at once
    s = seg("nn3", "nn4-zeros")
    assert {"stepId": "nn3", "nextStepId": "nn4"} in of(s, "step.passed")
    b = boxes(s)
    assert b and b[-1]["caption"] == "Click ▷ to run nn.py" and b[-1].get("zoom") is True, b
    # -- CP8: the zero-weights run: the loss row (yours 0.49 vs < 0.01), Not yet, the stuck panel; nn4 still on
    s = seg("nn4-zeros", "nn4-hint")
    r = rows(s, "nn4")["nn4c1"]
    assert r["status"] == "fail" and "0.49" in r["detail"] and re.search(r"<\s*0\.01|below 0\.01", r["detail"]), r
    off = of(s, "offtrack")
    assert off and off[-1]["stepId"] == "nn4" and off[-1]["title"] == "All weights start at zero", off
    assert {"hint", "show_me"} <= set(off[-1]["actions"]), off[-1]["actions"]
    assert [m for m in of(s, "metric") if m["runId"] == curated.TUTORIAL_RUN], "the card's expected curve (never '—')"
    assert any("0.4900" in d.get("caption", "") for d in of(s, "diagram")), [d.get("caption") for d in of(s, "diagram")]
    assert not of(s, "step.passed")
    # Hint 1 of 2 boxes the W1-W3 lines, never the ▷
    s = seg("nn4-hint", "nn4-fix")
    hint = [c for c in of(s, "card") if c.get("kind") == "hint"]
    assert hint and hint[-1]["title"] == "Hint 1 of 2" and "W1" in hint[-1]["body"], of(s, "card")
    b = boxes(s)
    w1, w3 = _line(_zeros(NN3_DONE), W_ZEROS[0]), _line(_zeros(NN3_DONE), W_ZEROS[2])
    assert b and b[-1]["caption"] == "Look at how W1, W2 and W3 start", b
    assert near(rig, b[-1], w1, top=1) and b[-1]["rect"]["h"] >= (w3 - w1) * rig.vs.H, (b[-1], w1, w3)  # (scrolled to the top)
    assert not [x for x in b if x["caption"].startswith("Click ▷")]
    # -- CP9: random again -> the ▷ box is back, the stuck card is not sent again; the run learns, nn4 passes
    s = seg("nn4-fix", "nn4-good")
    assert not of(s, "offtrack")
    b = boxes(s)
    assert b and b[-1]["caption"] == "Click ▷ to run nn.py", b
    s = seg("nn4-good", "end")
    assert {"stepId": "nn4", "nextStepId": "nn5"} in of(s, "step.passed")
    r = rows(s, "nn4")["nn4c1"]
    assert r["status"] == "pass" and r["detail"] == "loss 0.0009, below 0.01", r
    assert any("0.8187" in d.get("caption", "") and "0.0009" in d.get("caption", "") for d in of(s, "diagram"))
    # -- the whole way: no stale cards, previews never carry a run's numbers, the contract holds (strict hub)
    no_stale(ev)
    previews_only_until_a_run(ev, at["nn4-zeros"])
    assert not of(ev, "error"), of(ev, "error")
    assert set(rig.coach.calls) <= {"nn2", "nn4"}, rig.coach.calls


NN5_DONE = _pasted(NN3_DONE, "# Test it", STEPS["nn5"]["code"])


def test_t8_just_teach_me_nn5_nn6_completion_and_end(t8, monkeypatch):
    """CP10: nn5 boxed under # Test it and passed on its paste; nn6 the ▷ box, the real ▷ run completes the lesson:
    "Neural networks · 8 skills mastered" (no "You built…", no "Lesson complete"); End lesson in one tap."""
    from server.orchestrator import lesson_end

    monkeypatch.setattr(lesson_end, "CARD_DELAY_S", 0.05)
    rig = t8

    async def go():
        at = await just_teach_me_nn1_to_nn4(rig)
        at["nn5"] = rig.mark()
        await save(rig, NN5_DONE)
        await tick(rig, 2)
        await settle(rig, 0.2)
        at["nn6"] = rig.mark()
        await vscode_run(rig, RUNS["nn6"]["good"])
        await tick(rig, 3)
        await settle(rig, 0.3)
        at["done"] = rig.mark()
        await rig.s.action("end_lesson")
        await settle(rig, 0.2)
        at["ended"] = rig.mark()
        return at

    at = run(go())
    ev = rig.events
    # nn5: its box under # Test it (line 47 in t8), then the paste passes it; nn6 starts on the ▷ box
    s = ev[at["end"]:at["nn5"]]
    n = _line(NN3_DONE, "# Test it") + 1
    assert n == 47
    b = boxes(ev[at["nn4-good"]:at["nn5"]])
    assert b and b[-1]["caption"] == "Type it here" and abs(b[-1]["rect"]["y"] - rig.vs.row_y(n, n - 15)) <= 2.0, b
    s = ev[at["nn5"]:at["nn6"]]
    assert {"stepId": "nn5", "nextStepId": "nn6"} in of(s, "step.passed")
    b = boxes(s)
    assert b and b[-1]["caption"] == "Click ▷ to run nn.py" and b[-1].get("zoom") is True, b
    # nn6: the run passes it and the lesson is complete
    s = ev[at["nn6"]:at["done"]]
    assert {"stepId": "nn6"} in [{k: v for k, v in p.items() if k != "nextStepId"} for p in of(s, "step.passed")]
    done = [c for c in of(s, "card") if c.get("stepId") == "nn6" and c.get("kind") == "step"]
    assert done, of(s, "card")
    card = done[-1]
    assert card["title"] == "Neural networks · 8 skills mastered", card
    words = (card["title"] + " " + card.get("body", "")).lower()
    assert "you built" not in words and "lesson complete" not in words, card
    assert "0.0009" in card.get("body", ""), card  # the learner's own last run, not a canned number
    assert any("-1" in d.get("caption", "") and "1" in d.get("caption", "") for d in of(s, "diagram"))
    # End: one tap ends it, the box goes
    s = ev[at["done"]:at["ended"]]
    assert of(s, "lesson.ended") and of(s, "lesson.ended")[-1]["reason"] == "completed", of(s, "lesson.ended")
    assert {"clear": True} in of(s, "spotlight")
    no_stale(ev)
    previews_only_until_a_run(ev, at["nn4-zeros"])
    assert not of(ev, "error"), of(ev, "error")


# ------------------------------------------------------------------------------------------------------ Demo takes

async def demo_take(rig: Rig) -> dict:
    """One Demo take as docs/DEMO.md runs it: zeros at step 1, Run it for me -> the recorded stuck run, Hint, random
    weights + Check my work -> it learns, nn5, Run it for me on nn6 -> complete; then End."""
    at = {"start": rig.mark()}
    await rig.s.learn("teach me to build a neural network from scratch", mode="demo")
    rig.s.last_obs = _code_window(f"nn.py — {rig.workdir.name}")
    rig.s.editor_open = True
    await settle(rig, 0.2)
    at["starter"] = (rig.workdir / "nn.py").read_text(encoding="utf-8") == STARTER
    await save(rig, _zeros(NN1_DONE))
    await save(rig, _zeros(NN2_FIXED))
    await save(rig, _zeros(NN3_DONE))
    at["nn4"] = rig.mark()
    await rig.s.action("run_command")
    await settle(rig, 0.2)
    at["nn4-hint"] = rig.mark()
    await rig.s.action("hint")
    await settle(rig, 0.3)
    at["nn4-fix"] = rig.mark()
    await save(rig, NN3_DONE)
    rig.clock.t += 2
    await rig.s.action("check_step")
    await settle(rig, 0.2)
    at["nn5"] = rig.mark()
    await save(rig, NN5_DONE)
    at["nn6"] = rig.mark()
    await rig.s.action("run_command")
    await settle(rig, 0.3)
    at["done"] = rig.mark()
    await rig.s.action("end_lesson")
    await settle(rig, 0.1)
    at["end"] = rig.mark()
    return at


def test_t8_two_demo_takes_in_a_row_each_fresh(t8, monkeypatch):
    from server.orchestrator import lesson_end

    for name in ("GRADE_S", "ROW_S", "RUN_S", "STUCK_S"):
        monkeypatch.setattr(stage, name, 0.0)
    monkeypatch.setattr(lesson_end, "CARD_DELAY_S", 0.05)
    monkeypatch.delenv("MIYAGI_STAGE_STUCK", raising=False)
    rig = t8

    async def go():
        rig.vs.loop = asyncio.get_running_loop()
        return [await demo_take(rig), await demo_take(rig)]

    takes = run(go())
    ev = rig.events
    for k, at in enumerate(takes, 1):
        s = ev[at["start"]:at["end"]]
        assert at["starter"], f"take {k}: nn.py was not the clean starter"
        started = [p["stepId"] for p in of(s, "step.started")]
        assert started == ["nn1", "nn2", "nn3", "nn4", "nn5", "nn6"], (k, started)  # step 1, one step at a time
        assert not [p for p in of(s, "step.started") + of(s, "lesson.ready") if p.get("replay")], k
        assert [p["stepId"] for p in of(s, "step.passed") if not p.get("skipped")] == \
            ["nn1", "nn2", "nn3", "nn4", "nn5", "nn6"], k
        # the recorded stuck run: its output card, the loss row, the Not yet
        st = ev[at["nn4"]:at["nn4-hint"]]
        assert any(c["title"].startswith("Ran ") and "0.4900" in (c.get("output") or "") for c in of(st, "card")), k
        assert rows(st, "nn4")["nn4c1"]["status"] == "fail", (k, rows(st, "nn4"))
        off = of(st, "offtrack")
        assert off and off[0]["stepId"] == "nn4" and "0.49" in off[0]["title"], (k, off)
        assert {"hint", "show_me"} <= set(off[0]["actions"]), (k, off[0]["actions"])
        # Hint 1 of 2 about W1-W3, its box on those lines, never the ▷
        st = ev[at["nn4-hint"]:at["nn4-fix"]]
        hint = [c for c in of(st, "card") if c.get("kind") == "hint"]
        assert hint and hint[-1]["title"] == "Hint 1 of 2" and "W1" in hint[-1]["body"], (k, of(st, "card"))
        b = boxes(st)
        assert b and b[-1]["caption"] == "Look at how W1, W2 and W3 start", (k, b)
        # random weights + Check my work: it learns
        st = ev[at["nn4-fix"]:at["nn5"]]
        assert {"stepId": "nn4", "nextStepId": "nn5"} in of(st, "step.passed"), k
        assert not of(st, "offtrack"), (k, of(st, "offtrack"))
        # nn6 -> the plain completion card, then End
        st = ev[at["nn6"]:at["done"]]
        done = [c for c in of(st, "card") if c.get("kind") == "step" and c.get("stepId") == "nn6"]
        assert done and done[-1]["title"] == "Neural networks · 8 skills mastered", (k, of(st, "card"))
        assert "you built" not in (done[-1]["title"] + done[-1].get("body", "")).lower()
        assert of(ev[at["done"]:at["end"]], "lesson.ended"), k
        no_stale(s)
        previews_only_until_a_run(s, at["nn4"] - at["start"])
        assert not of(s, "error"), (k, of(s, "error"))
    assert rig.coach.calls == [], rig.coach.calls  # a Demo makes no coach calls
