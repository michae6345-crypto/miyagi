"""Demo lessons (stage.py): the launcher's Demo option walks the neural-net lesson without grading anything.
Run from the repo root:  python -m pytest server/orchestrator/tests/test_stage.py -q"""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from server.orchestrator import curated, stage
from server.orchestrator.tests.test_session import Rig
from shared.contracts.events import parse_app_message

# The lesson's weights (curated.LAYERS), started at zeros (the presenter's shortcut) or random (the lesson's code).
_SHAPES = list(zip(curated.LAYERS, curated.LAYERS[1:]))
ZEROS = "".join(f"W{k} = np.zeros(({r}, {c}))\n" for k, (r, c) in enumerate(_SHAPES, 1))
RANDOM = "".join(f"W{k} = np.random.randn({r}, {c})\n" for k, (r, c) in enumerate(_SHAPES, 1))
_STEPS = {st["id"]: st for st in json.loads(curated.LESSON_FILE.read_text(encoding="utf-8"))["steps"]}


def code(sid: str) -> str:
    """A step's code as the drawer's Copy pastes it (a typing step passes only once its own code is there)."""
    return "\n" + _STEPS[sid]["code"].strip() + "\n"


NN1_ZEROS = "\n".join(ln for ln in code("nn1").splitlines() if not re.match(r"W\d+ =", ln)) + "\n" + ZEROS
_RUNS = json.loads(stage.RUNS_FILE.read_text(encoding="utf-8"))
STUCK = f"{curated.STUCK_LOSS:.4f}"
GOOD_LAST = curated.parse_output(_RUNS["nn4"]["good"])["losses"][-1][1]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.delenv("MIYAGI_STAGE", raising=False)
    monkeypatch.delenv("MIYAGI_STAGE_STUCK", raising=False)
    for name in ("GRADE_S", "ROW_S", "RUN_S", "STUCK_S"):
        monkeypatch.setattr(stage, name, 0.0)
    r = Rig(tmp_path)
    r.s.offtrack_grace_s = 20  # as in the app: nothing the stage does may depend on it
    return r


def run(coro):
    return asyncio.run(coro)


async def settle(rig: Rig) -> None:
    for _ in range(4):
        await rig.settle()
        await asyncio.sleep(0)


async def save(rig: Rig, text: str, wait: float = 5.0) -> None:
    rig.clock.t += wait  # past the step's first seconds
    p = rig.workdir / "nn.py"
    p.write_text(p.read_text() + text if p.exists() else text)
    await rig.s.on_file_change([str(p)])
    await settle(rig)


def passed(rig: Rig) -> list[str]:
    return [p["stepId"] for p in rig.of("step.passed") if not p.get("skipped")]


def test_demo_mode_is_in_the_contract():
    assert parse_app_message({"type": "learn", "payload": {"query": "x", "mode": "demo"}}).payload.mode == "demo"


def test_any_goal_starts_the_staged_nn_lesson(rig):
    async def go():
        await rig.s.learn("how do rockets land", mode="demo")
        await settle(rig)
        lesson = rig.of("lesson.ready")[-1]["lesson"]
        assert lesson["id"] == "lesson-nn-from-scratch"
        assert rig.s.step["id"] == "nn1"
        assert stage.on(rig.s)
    run(go())


def test_video_and_just_teach_me_are_untouched(rig):
    async def go():
        await rig.s.learn("build a neural network", mode="lesson")
        await settle(rig)
        assert not stage.on(rig.s)  # the real curated lesson, really graded
    run(go())


def test_the_whole_demo(rig):
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        # a save in the step's first seconds doesn't count (the last step's own save)
        await save(rig, "# nothing yet\n", wait=0.5)
        assert passed(rig) == []
        # step 1: paste with the zeros shortcut, save -> every row green, then the step passes
        await save(rig, NN1_ZEROS)
        rows = {c["checkId"]: c["status"] for c in rig.of("check.updated") if c["stepId"] == "nn1"}  # the latest
        assert rows and set(rows.values()) == {"pass"}
        assert passed(rig) == ["nn1"] and rig.s.step["id"] == "nn2"
        # step 2: a save with only step 1's code passes nothing; with its own code it passes
        await save(rig, "\n")
        assert rig.s.step["id"] == "nn2"
        await save(rig, code("nn2"))
        # step 3: Check my work passes it once its code is there
        (rig.workdir / "nn.py").write_text((rig.workdir / "nn.py").read_text() + code("nn3"))
        rig.clock.t += 2
        await rig.s.action("check_step")
        await settle(rig)
        assert passed(rig) == ["nn1", "nn2", "nn3"] and rig.s.step["id"] == "nn4"
        # step 4: a save never passes a run step
        await save(rig, "\n")
        assert rig.s.step["id"] == "nn4"
        # the first run is the stuck one (W1 / W2 start at zeros): its output card, a fail row, the coach's card
        m = rig.mark()
        await rig.s.action("run_command")
        await settle(rig)
        ev = rig.since(m)
        cards = [e["payload"] for e in ev if e["type"] == "card"]
        assert any(c["title"].startswith("Ran ") and STUCK in (c.get("output") or "") for c in cards)
        rows = {e["payload"]["checkId"]: e["payload"]["status"] for e in ev if e["type"] == "check.updated"}
        assert sorted(rows.values()) == ["fail", "pass"]  # the loss row fails, the saved file's row stays green
        off = [e["payload"] for e in ev if e["type"] == "offtrack"]
        assert off and off[0]["stepId"] == "nn4" and f"{curated.STUCK_LOSS:.2f}" in off[0]["title"]
        diag = [e["payload"] for e in ev if e["type"] == "diagram"]
        assert diag and "same neuron" in diag[-1].get("caption", "")  # identical hidden neurons in the panel
        assert [e["payload"]["name"] for e in ev if e["type"] == "metric"]  # the live curve
        assert rig.s.step["id"] == "nn4"
        # the hint is the stuck ladder's first hint
        await rig.s.action("hint")
        await settle(rig)
        assert "W1" in (rig.of("card")[-1].get("title", "") + rig.of("card")[-1].get("body", ""))
        # fix it, run again: it learns
        await save(rig, RANDOM)
        await rig.s.action("run_command")
        await settle(rig)
        assert passed(rig)[-1] == "nn4"
        good = [c for c in rig.of("check.updated") if c["stepId"] == "nn4"][-1]
        assert good["status"] == "pass" and f"{GOOD_LAST:.4f}" in good.get("detail", "")
        # step 5: save; step 6: run -> the lesson is done, the panel shows their network answering
        await save(rig, code("nn5"))
        m = rig.mark()
        await rig.s.action("run_command")
        await settle(rig)
        assert passed(rig) == ["nn1", "nn2", "nn3", "nn4", "nn5", "nn6"]
        assert [e for e in rig.since(m) if e["type"] == "diagram"]  # the panel: their trained network answering
        assert not rig.of("error")
        assert not [c for c in rig.of("card") if c.get("title") == "Not yet"]
    run(go())


def test_no_stuck_run_when_nn_py_starts_random(rig):
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        for sid in ("nn1", "nn2", "nn3"):
            await save(rig, code(sid))  # nn1's own code starts every W random
        await rig.s.action("run_command")
        await settle(rig)
        assert passed(rig)[-1] == "nn4" and not rig.of("offtrack")
    run(go())


def test_presenter_next_back_restart(rig):
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        for _ in range(4):  # next on typing steps and on the run step (never the stuck run)
            assert await stage.next_step(rig.s)
            await settle(rig)
        assert passed(rig) == ["nn1", "nn2", "nn3", "nn4"] and not rig.of("offtrack")
        assert await stage.back(rig.s)
        await settle(rig)
        assert rig.s.step["id"] == "nn4"
        (rig.workdir / "nn.py").write_text("junk\n")
        assert await stage.restart(rig.s)
        await settle(rig)
        assert rig.s.step["id"] == "nn1" and stage.on(rig.s)
        assert (rig.workdir / "nn.py").read_text().startswith("# A neural net from scratch")  # clean starter
    run(go())


def test_stage_env_makes_every_lesson_a_demo(rig, monkeypatch):
    monkeypatch.setenv("MIYAGI_STAGE", "1")

    async def go():
        await rig.s.learn("teach me guitar")  # a video search otherwise
        await settle(rig)
        assert stage.on(rig.s) and rig.s.step["id"] == "nn1"
    run(go())


def test_a_double_press_is_one_run(rig, monkeypatch):
    monkeypatch.setattr(stage, "RUN_S", 0.05)

    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        await save(rig, NN1_ZEROS)
        for sid in ("nn2", "nn3"):
            await save(rig, code(sid))
        assert rig.s.step["id"] == "nn4"
        await asyncio.gather(rig.s.action("run_command"), rig.s.action("run_command"))
        await settle(rig)
        assert len([c for c in rig.of("card") if c["title"].startswith("Ran ")]) == 1
        assert rig.s.step["id"] == "nn4" and rig.of("offtrack")  # the one run was the stuck one
        assert not [c for c in rig.of("card") if c["title"] in ("Nothing to do here", "Not yet")]
    run(go())


def test_check_during_a_saves_pass_is_quiet(rig, monkeypatch):
    monkeypatch.setattr(stage, "GRADE_S", 0.1)

    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        rig.clock.t += 5
        (rig.workdir / "nn.py").write_text(NN1_ZEROS)
        await rig.s.on_file_change([str(rig.workdir / "nn.py")])  # the save's pass starts
        await rig.s.action("check_step")  # and Check my work right behind it
        await settle(rig)
        await asyncio.sleep(0.3)
        await settle(rig)
        assert passed(rig) == ["nn1"]
        assert not [c for c in rig.of("card") if c["title"] in ("Nothing to do here", "Not yet")]
    run(go())


async def to_train(rig: Rig) -> None:
    await rig.s.learn("anything", mode="demo")
    await settle(rig)
    await save(rig, NN1_ZEROS)
    for sid in ("nn2", "nn3"):
        await save(rig, code(sid))
    assert rig.s.step["id"] == "nn4"


def test_a_queued_second_press_is_the_same_run(rig):
    async def go():
        await to_train(rig)
        await rig.s.action("run_command")  # the socket runs commands one at a time: the second comes right after
        await settle(rig)
        await rig.s.action("check_step")
        await settle(rig)
        assert rig.s.step["id"] == "nn4" and rig.of("offtrack")  # still the stuck run's "Not yet"
        assert len([c for c in rig.of("card") if c["title"].startswith("Ran ")]) == 1
        rig.clock.t += 5  # a press later on is a new run: it learns
        await rig.s.action("check_step")
        await settle(rig)
        assert passed(rig)[-1] == "nn4"
    run(go())


def test_a_queued_second_press_after_a_run_that_passed_is_quiet(rig):
    """Demo rehearsal (Nov 15): Run it for me double-clicked on a run that LEARNS. The socket runs the second press
    after the first one's run passed the step, so it found the step passed and answered "Nothing to do here" over the
    run's own card (on nn6: over [-1.0, 0.0, 1.0], the Demo's last beat). One press, one run, nothing else."""
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        await save(rig, code("nn1"))
        for sid in ("nn2", "nn3"):
            await save(rig, code(sid))
        for sid in ("nn4", "nn6"):
            assert rig.s.step["id"] == sid
            m = rig.mark()
            await rig.s.action("run_command")
            await rig.s.action("run_command")  # queued behind the first: it arrives once the step has passed
            await settle(rig)
            cards = [e["payload"]["title"] for e in rig.since(m) if e["type"] == "card"]
            assert passed(rig)[-1] == sid
            assert len([t for t in cards if t.startswith("Ran ")]) == 1
            assert "Nothing to do here" not in cards, cards
            if sid == "nn4":
                await save(rig, code("nn5"))
        assert passed(rig) == ["nn1", "nn2", "nn3", "nn4", "nn5", "nn6"]
    run(go())


def test_next_during_a_run_passes_without_not_yet(rig, monkeypatch):
    monkeypatch.setattr(stage, "RUN_S", 0.2)

    async def go():
        await to_train(rig)
        press = asyncio.create_task(rig.s.action("run_command"))
        await asyncio.sleep(0.05)  # the run is under way (it would be the stuck one)
        assert await stage.next_step(rig.s)
        await press
        await settle(rig)
        assert passed(rig)[-1] == "nn4" and not rig.of("offtrack")
    run(go())


def test_work_ends_the_before_you_start_hold(rig):
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        held = rig.s.awaiting_start
        await save(rig, NN1_ZEROS)
        assert passed(rig) == ["nn1"]
        assert not rig.s.awaiting_start, f"still held (was held: {held})"
    run(go())


# ---------------------------------------------------------------------------------------------------------- fresh takes
# Michael runs the Demo many times in a row: every Demo start is step 1 with a clean nn.py, whatever the last take, a
# deploy or an engine restart left behind (Nov 15: the stable-progress resume paths must never reach a Demo).

def _code(*ids: str) -> str:
    by = {st["id"]: st for st in curated.lesson_for(stage.GOAL)["steps"]}
    return "import numpy as np\n\n" + "\n\n".join(by[i]["code"] for i in ids) + "\n"


def _engine(tmp_path):
    """A (re)started engine on the same disk: a session with its Resumer (sessions.resume)."""
    from server.sessions import Resumer

    r = Rig(tmp_path)
    return r, Resumer(r.s)


async def _auto_resume(rig: Rig, resumer) -> None:
    """main.Engine.auto_resume as the first app connection after a restart runs it."""
    import types

    from server.orchestrator import main

    eng = types.SimpleNamespace(resumer=resumer, hub=types.SimpleNamespace(clients=set()), session=rig.s,
                                seen_lesson=None, _lesson_id=lambda: None)
    await main.Engine.auto_resume(eng)
    await settle(rig)


def test_every_demo_start_is_a_fresh_take(tmp_path, monkeypatch):
    from server.sessions import store

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("MIYAGI_STAGE", raising=False)
    nn = tmp_path / "nn.py"
    starter = curated._starter()

    async def go():
        # take 1: three steps on cue, nn.py full of code, then a deploy's POST /end ("interrupted", place kept)
        r1, res1 = _engine(tmp_path)
        await r1.s.learn("anything", mode="demo")
        await settle(r1)
        for _ in range(3):
            assert await stage.next_step(r1.s)
            await settle(r1)
        assert r1.s.step["id"] == "nn4"
        nn.write_text(_code("nn1", "nn2", "nn3"))
        res1.save_now()
        await r1.s.end_lesson("interrupted")
        assert store.load() is None  # a Demo take is never saved
        # an older engine's Demo save on disk: dropped when the engine starts, never offered back
        g = stage.mark(curated.lesson_for(stage.GOAL))
        store.save({"lessonId": g["lesson"]["id"], "title": "x", "stepIndex": 3, "stepCount": len(g["steps"]),
                    "stepId": "nn4", "workdir": str(tmp_path), "startedAt": 1.0, "lastActiveAt": 9e12}, g)
        r2, res2 = _engine(tmp_path)
        assert store.load() is None
        assert not [p for t, p in r2.s.snapshot() if t == "card" and p.get("kind") == "resume"]
        # ... and one written after it started: the first app connection doesn't auto-resume it
        from server.orchestrator import main  # noqa: F401 - (its import starts an engine: before the save below)
        store.save({"lessonId": g["lesson"]["id"], "title": "x", "stepIndex": 3, "stepCount": len(g["steps"]),
                    "stepId": "nn4", "workdir": str(tmp_path), "startedAt": 1.0, "lastActiveAt": 9e12}, g)
        await _auto_resume(r2, res2)
        assert r2.s.graph is None
        # take 2 (the launcher's Demo, not a restart): step 1, the clean starter, no resume / skip ahead
        await r2.s.learn("anything", mode="demo")
        await settle(r2)
        assert r2.s.step["id"] == "nn1" and stage.on(r2.s)
        assert nn.read_text() == starter
        assert [p["stepId"] for p in r2.of("step.started")] == ["nn1"]
        assert not [p for p in r2.of("step.started") + r2.of("lesson.ready") if p.get("replay")]
        assert passed(r2) == []
        # the presenter pastes ahead: "next" still goes one step at a time (no "You already did steps 2-3")
        nn.write_text(_code("nn1", "nn2", "nn3"))
        assert await stage.next_step(r2.s)
        await settle(r2)
        assert r2.s.step["id"] == "nn2" and passed(r2) == ["nn1"]
        assert not [p for p in r2.of("step.passed") if p.get("already")]
        assert not [c for c in r2.of("card") if c.get("title", "").startswith("You already did")]
        # "build a neural network" re-sent as a Demo while the Demo runs: a new take, never "continuing"
        await r2.s.learn(stage.GOAL, mode="demo")
        await settle(r2)
        assert r2.s.step["id"] == "nn1" and nn.read_text() == starter
        # ⌃⌥⌘R mid-take: step 1, clean nn.py
        assert await stage.next_step(r2.s)
        await settle(r2)
        nn.write_text(_code("nn1", "nn2", "nn3"))
        assert await stage.restart(r2.s)
        await settle(r2)
        assert r2.s.step["id"] == "nn1" and stage.on(r2.s) and nn.read_text() == starter
        assert store.load() is None

    run(go())


def test_just_teach_me_still_continues_after_a_restart_but_never_a_demo(tmp_path, monkeypatch):
    from server.sessions import store

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("MIYAGI_STAGE", raising=False)
    nn = tmp_path / "nn.py"

    async def go():
        # the real lesson at nn3, then a deploy's POST /end keeps the place
        r1, res1 = _engine(tmp_path)
        await r1.s.learn(stage.GOAL, mode="lesson")
        await settle(r1)
        assert not stage.on(r1.s) and r1.s.step["id"] == "nn1"
        for _ in range(2):
            await r1.s.force_pass()
            await settle(r1)
        assert r1.s.step["id"] == "nn3"
        nn.write_text(_code("nn1", "nn2"))
        res1.save_now()
        await r1.s.end_lesson("interrupted")
        assert (store.load() or {}).get("stepId") == "nn3"
        # restarted engine, the goal typed again: continues at nn3, nn.py untouched (the Nov 15 behaviour)
        r2, _res2 = _engine(tmp_path)
        await r2.s.learn(stage.GOAL, mode="lesson")
        await settle(r2)
        assert r2.s.step["id"] == "nn3" and not stage.on(r2.s)
        assert nn.read_text() == _code("nn1", "nn2")
        # the Demo from there: a fresh take (step 1, clean nn.py), not the real lesson's step
        await r2.s.learn("anything", mode="demo")
        await settle(r2)
        assert r2.s.step["id"] == "nn1" and stage.on(r2.s) and nn.read_text() == curated._starter()
        # "Just teach me" during a Demo starts the real lesson (step 1), it doesn't continue the Demo
        assert await stage.next_step(r2.s)
        await settle(r2)
        await r2.s.learn(stage.GOAL, mode="lesson")
        await settle(r2)
        assert not stage.on(r2.s) and r2.s.step["id"] == "nn1"
    run(go())


SIGN_BUG = "    d_h1 = d_h2 @ W2.T * (1 + h1 ** 2)" + chr(10)


def test_the_planted_sign_bug_is_the_not_yet(rig):
    async def go():
        await rig.s.learn("build a neural network", mode="demo")
        await settle(rig)
        # each step's own code (a Demo step passes only once its code is in nn.py), nn2 with the planted + sign
        await save(rig, code("nn1"))
        await save(rig, code("nn2").replace("(1 - h1 ** 2)", "(1 + h1 ** 2)"))
        await save(rig, code("nn3"))
        assert rig.s.step["id"] == "nn4"
        line = (rig.workdir / "nn.py").read_text().splitlines().index(SIGN_BUG.rstrip(chr(10))) + 1
        await rig.s.action("run_command")
        await settle(rig)
        off = rig.of("offtrack")
        assert off and off[-1]["title"] == "Wrong sign in tanh slope"
        assert f"line {line}" in off[-1]["body"] and off[-1]["diff"]["line"] == line
        assert "(1 - h1 ** 2)" in off[-1]["diff"]["expected"]
        rows = {c["checkId"]: c for c in rig.of("check.updated") if c["stepId"] == "nn4"}
        assert any(r["status"] == "fail" for r in rows.values())  # the loss row, on the stalled loss
        rig.clock.t += 5  # fixed (or not), the next run learns
        await rig.s.action("run_command")
        await settle(rig)
        assert passed(rig)[-1] == "nn4"
    run(go())


def test_install_on_the_setup_card_always_ends_installed(rig, monkeypatch):
    from server.orchestrator import workspace as wsmod

    def offline(item, workdir, on_line):
        raise OSError("no network")

    monkeypatch.setattr(wsmod, "install", offline)

    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        rig.s.reqs = [{"tool": "numpy", "label": "numpy", "needed": True, "ok": False,
                       "install": {"method": "pip", "pip_name": "numpy"}}]
        rig.s._setup_card = {"kind": "setup", "title": "Missing: numpy", "body": "", "actions": ["install"]}
        await rig.s.action("install", "numpy")
        await settle(rig)
        done = [c for c in rig.of("card") if c.get("kind") == "setup"][-1]
        assert done["title"] == "numpy installed ✓" and done["dismissAfterMs"] > 0 and done["actions"] == []
        assert [p for p in rig.of("setup.progress") if p.get("done")][-1]["ok"] is True
        assert not rig.of("error")
    run(go())


# ---------------------------------------------------------------------------------------------------------- the locked flow
# Michael's locked demo flow (email, Nov 15 3:43 AM), step for step, on the same code paths as the live curated lesson:
# the sheet -> Start -> "Missing: numpy" -> Install -> "numpy installed ✓" -> steps 1-3 pasted from the drawer -> Train it
# (run step: the drawer tucks and the network floats in the app on kind "run"; the ▷ box with zoom + "Click ▷ to run
# nn.py"; the planted tanh-sign bug's Not yet; the fixed run 0.8187 -> 0.0009) -> steps 5-6 -> the completion card.

LOCK_WIN = {"x": 0.0, "y": 0.0, "w": 1200.0, "h": 900.0}
LOCK_RUN_BTN = {"x": 1150.0, "y": 60.0, "w": 22.0, "h": 22.0}  # VS Code's editor-title ▷ (~22 pt)
LOCK_TERMINAL = {"x": 260.0, "y": 640.0, "w": 900.0, "h": 220.0}
SIGN_BUG_H2 = "    d_h2 = d_out @ W3.T * (1 + h2 ** 2)"


@pytest.fixture
def flow(tmp_path, monkeypatch):
    """A Demo session as the app sees it: VS Code on screen (its ▷ and terminal), the setup check on, Install offline."""
    import time as _time
    from types import SimpleNamespace as NS

    from server.orchestrator import lesson_end, run_pointing, workspace as wsmod
    from server.orchestrator.screen_bridge import FakeScreen
    from server.orchestrator.workspace import Workspace

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    for name in ("DEMO", "MIYAGI_STAGE", "MIYAGI_STAGE_STUCK"):
        monkeypatch.delenv(name, raising=False)
    for name in ("GRADE_S", "ROW_S", "RUN_S", "STUCK_S"):
        monkeypatch.setattr(stage, name, 0.0)
    monkeypatch.setattr(lesson_end, "CARD_DELAY_S", 0.0)
    monkeypatch.setattr(run_pointing, "RETRY_S", (0.01, 0.01, 0.01, 0.01))
    monkeypatch.setattr(run_pointing, "SLOW_S", 0.01)
    monkeypatch.setattr(wsmod, "install", lambda item, workdir, on_line: {"ok": True, "tool": item["tool"]})
    screen = FakeScreen()
    screen.regions = {"terminal": dict(LOCK_TERMINAL), "run_button": dict(LOCK_RUN_BTN)}
    r = Rig(tmp_path, screen=screen)
    r.s.offtrack_grace_s = 20
    r.s.workspace = Workspace(enabled=True, runner=lambda argv: True)

    def front() -> None:  # VS Code in front on the lesson's nn.py
        r.s.last_obs = NS(app="Code", windows=[NS(app="Code", title=f"nn.py — {tmp_path.name}", rect=dict(LOCK_WIN))])

    async def click_run() -> None:  # VS Code's ▷: the companion's command_end for `python3 nn.py` in the folder
        front()
        await curated.on_command_end(r.s, {"command": {"commandLine": "python3 nn.py", "cwd": str(tmp_path),
                                                       "startedAt": _time.time() * 1000, "exitCode": 0}})
        await settle(r)

    r.front, r.click_run = front, click_run
    return r


async def _until(cond, s: float = 2.0) -> bool:
    import time as _time

    end = _time.monotonic() + s
    while _time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


def _paste(rig: Rig, code: str) -> None:
    """The drawer's code pasted under the step's line (its type box's `match`)."""
    anchor = next(t["match"] for t in rig.s.step["targets"] if t.get("match"))
    p = rig.workdir / "nn.py"
    src = p.read_text()
    p.write_text(src.replace(anchor, f"{anchor}\n{code}", 1) if anchor in src
                 else src.rstrip("\n") + f"\n\n{anchor}\n{code}\n")


def _beats(events: list[dict]) -> list[str]:
    """The flow's beats in the order they first went out."""
    out: list[str] = []
    for e in events:
        t, pl = e["type"], e["payload"]
        beat = {("card", "Set up first"): "setup", ("card", "numpy installed ✓"): "installed",
                ("offtrack", "Wrong sign in tanh slope"): "not yet"}.get((t, pl.get("title")))
        if t == "lesson.ready":
            beat = "sheet"
        elif t == "step.started":
            beat = pl["stepId"]
        elif t == "card" and pl.get("skillMap"):
            beat = "complete"
        if beat and beat not in out:
            out.append(beat)
    return out


def test_demo_follows_the_locked_nn_flow(flow):
    rig = flow
    lesson = curated.lesson_for(stage.GOAL)
    steps = {st["id"]: st for st in lesson["steps"]}

    def last(type_: str, **match) -> dict:
        hits = [p for p in rig.of(type_) if all(p.get(k) == v for k, v in match.items())]
        assert hits, f"no {type_} {match}"
        return hits[-1]

    async def go():
        # 1. the launcher's Demo chip: the curated lesson at once, held under "Before you start"
        await rig.s.learn(stage.GOAL, mode="demo")
        await settle(rig)
        ready = rig.of("lesson.ready")[-1]["lesson"]
        assert ready["id"] == lesson["lesson"]["id"] and ready["builtBy"] == "curated"
        assert "1-4-4-1" in ready["build"]["summary"] and "sin(x)" in ready["build"]["summary"]
        assert ready.get("flow") and ready.get("overview")  # the sheet's fields, as the live lesson sends them
        assert rig.s.awaiting_start and rig.s.step["id"] == "nn1"
        # 3 (sent while the sheet is up, as in the live lesson): "Missing: numpy", Install first (the white primary)
        setup = last("card", kind="setup")
        assert setup["title"] == "Set up first" and setup["body"].startswith("Missing: numpy")
        assert setup["actions"][0] == "install"
        assert [it["tool"] for it in setup["setup"]["items"]] == ["numpy"]
        # 2. Start the lesson (action {kind: 'start'})
        await rig.s.action("start")
        await settle(rig)
        assert not rig.s.awaiting_start
        snap = rig.s.snapshot()  # a reconnect right after Start never brings the sheet back
        assert not rig.s.awaiting_start and [e for e, _ in snap][:2] == ["lesson.ready", "step.started"]
        # 3. Install -> "numpy installed ✓", and the card goes away by itself
        await rig.s.action("install", "numpy")
        await settle(rig)
        assert [p for p in rig.of("setup.progress") if p.get("done")][-1] == {"tool": "numpy", "done": True, "ok": True}
        assert last("card", kind="setup") == {"kind": "setup", "title": "numpy installed ✓", "body": "", "actions": [],
                                              "dismissAfterMs": 4000}
        assert rig.s._setup_card is None
        # 4. steps 1-3: the box under # The network / # Backprop / # Training, the drawer's code, the network panel
        for sid, anchor in (("nn1", "# The network"), ("nn2", "# Backprop"), ("nn3", "# Training")):
            st = last("step.started", stepId=sid)
            assert st["kind"] == "code" and st["code"] == steps[sid]["code"]  # the drawer's code, as written
            assert rig.s.step["targets"][0]["match"] == anchor  # the type box's line
            net = last("diagram", stepId=sid)
            assert net["kind"] == "network" and net["data"]["layers"] == [1, 4, 4, 1] and net["data"]["preview"]
            code = steps[sid]["code"]
            if sid == "nn2":  # the planted bug: d_h2's tanh slope with +
                code = code.replace("(1 - h2 ** 2)", "(1 + h2 ** 2)")
            rig.clock.t += 5
            _paste(rig, code)
            await rig.s.on_file_change([str(rig.workdir / "nn.py")])
            await settle(rig)
            rows = {c["checkId"]: c["status"] for c in rig.of("check.updated") if c["stepId"] == sid}
            assert set(rows.values()) == {"pass"} and passed(rig)[-1] == sid
        # 5. Train it: a run step (the app tucks the drawer and floats the network), the ▷ boxed with the loupe
        st = last("step.started", stepId="nn4")
        assert st["kind"] == "run" and st["code"] == "python3 nn.py"
        rig.front()
        assert await _until(lambda: any(p.get("rect") and p.get("caption") == "Click ▷ to run nn.py"
                                        for p in rig.of("spotlight")))
        box = [p for p in rig.of("spotlight") if p.get("rect")][-1]
        assert box["zoom"] is True and box["app"] == "Code"
        # the first ▷: the planted bug's run (real NumPy output), the loss row fails, "Wrong sign in tanh slope"
        p = rig.workdir / "nn.py"
        bug_line = p.read_text().splitlines().index(SIGN_BUG_H2) + 1
        m = rig.mark()
        await rig.click_run()
        ev = rig.since(m)
        losses = [e["payload"]["value"] for e in ev
                  if e["type"] == "metric" and e["payload"]["runId"].startswith("stage-")]
        assert losses == [v for _, v in curated.parse_output(_RUNS["nn4"]["sign_h2"])["losses"]]
        row = [e["payload"] for e in ev if e["type"] == "check.updated" and e["payload"]["stepId"] == "nn4"][-1]
        assert row["status"] == "fail" and "need < 0.01" in row["detail"]  # the loss evidence: yours vs 0.01
        off = [e["payload"] for e in ev if e["type"] == "offtrack"]
        assert off and off[-1]["title"] == "Wrong sign in tanh slope"
        assert f"Change + to − on line {bug_line}" in off[-1]["body"] and off[-1]["diff"]["line"] == bug_line
        assert "(1 - h2 ** 2)" in off[-1]["diff"]["expected"] and "(1 + h2 ** 2)" in off[-1]["diff"]["yours"]
        assert [e for e in ev if e["type"] == "metric" and e["payload"]["runId"] == curated.TUTORIAL_RUN]  # expected
        assert rig.s.step["id"] == "nn4"
        snap = dict(rig.s.snapshot())  # a reconnect keeps the step and its Not yet, no sheet
        assert snap["step.started"]["stepId"] == "nn4" and snap["offtrack"]["title"] == "Wrong sign in tanh slope"
        assert not rig.s.awaiting_start
        for want in (f"Look at line {bug_line}", f"Fix line {bug_line}"):  # Hint: this bug's line, then its fix
            await rig.s.action("hint")
            await settle(rig)
            hint = rig.of("card")[-1]
            assert hint["kind"] == "hint" and hint["title"] == want, hint
        assert "(1 - h2 ** 2)" in hint["body"]
        # the fix (+ back to -), ▷ again: it learns, 0.8187 -> 0.0009, the panel draws the run's own frames
        p.write_text(p.read_text().replace("(1 + h2 ** 2)", "(1 - h2 ** 2)"))
        rig.clock.t += 5
        await rig.s.on_file_change([str(p)])
        await settle(rig)
        m = rig.mark()
        await rig.click_run()
        ev = rig.since(m)
        good = curated.parse_output(_RUNS["nn4"]["good"])["losses"]
        assert (good[0][1], good[-1][1]) == (0.8187, 0.0009)
        net = [e["payload"] for e in ev if e["type"] == "diagram" and e["payload"]["stepId"] == "nn4"][-1]
        frames = net["data"]["frames"]
        assert net["data"]["mode"] == "train" and not net["data"].get("preview") and len(frames) > 2
        assert frames[0]["loss"] == pytest.approx(0.8187, abs=1e-3) and frames[-1]["loss"] < 0.01
        row = [e["payload"] for e in ev if e["type"] == "check.updated" and e["payload"]["stepId"] == "nn4"][-1]
        assert row["status"] == "pass" and "0.0009" in row["detail"]
        assert passed(rig)[-1] == "nn4"
        # 6. step 5 (paste the test), step 6 (▷) -> the completion card with the skill map
        assert last("step.started", stepId="nn5")["code"] == steps["nn5"]["code"]
        rig.clock.t += 5
        _paste(rig, steps["nn5"]["code"])
        await rig.s.on_file_change([str(p)])
        await settle(rig)
        assert passed(rig)[-1] == "nn5" and last("step.started", stepId="nn6")["kind"] == "run"
        await rig.click_run()
        assert await _until(lambda: any(c.get("skillMap") for c in rig.of("card")))
        assert passed(rig) == ["nn1", "nn2", "nn3", "nn4", "nn5", "nn6"]
        end = [c for c in rig.of("card") if c.get("skillMap")][-1]
        assert end["kind"] == "step" and end["title"] == "Neural networks · 8 skills mastered"
        assert "Loss 0.8187 → 0.0009 in your last run." in end["body"] and end["actions"] == ["end_lesson"]
        assert end["skillMap"]["track"] == "Neural networks"
        assert sum(n["state"] == "mastered" for n in end["skillMap"]["nodes"]) == 8
        assert not rig.of("error") and not [c for c in rig.of("card") if c.get("title") == "Not yet"]
        assert _beats(rig.events) == ["sheet", "nn1", "setup", "installed", "nn2", "nn3", "nn4", "not yet", "nn5",
                                      "nn6", "complete"]
        # the presenter's restart: from the top, step 1 with a clean nn.py, the sheet and "Missing: numpy" again
        m = rig.mark()
        assert await stage.restart(rig.s)
        await settle(rig)
        assert rig.s.step["id"] == "nn1" and p.read_text() == curated._starter() and rig.s.awaiting_start
        assert _beats(rig.since(m)) == ["sheet", "nn1", "setup"]
    run(go())


def test_presenter_keys_walk_the_same_states(flow):
    """next / back step through the flow's own states: each step starts as in a take, a run step passes on its good
    run (never the planted bug's Not yet), back goes to the step before, and the last next ends on the skill map."""
    rig = flow

    async def go():
        await rig.s.learn(stage.GOAL, mode="demo")
        await settle(rig)
        await rig.s.action("start")
        await settle(rig)
        for sid in ("nn1", "nn2", "nn3", "nn4", "nn5"):
            assert rig.s.step["id"] == sid
            assert await stage.next_step(rig.s)
            await settle(rig)
        assert [e["stepId"] for e in rig.of("step.started")] == ["nn1", "nn2", "nn3", "nn4", "nn5", "nn6"]
        assert not rig.of("offtrack")
        assert await stage.back(rig.s)
        await settle(rig)
        assert rig.s.step["id"] == "nn5" and not rig.s.awaiting_start
        assert await stage.next_step(rig.s)
        await settle(rig)
        assert rig.s.step["id"] == "nn6"
        assert await stage.next_step(rig.s)  # See what it learned: its good run, then the ending
        assert await _until(lambda: any(c.get("skillMap") for c in rig.of("card")))
        assert passed(rig)[-1] == "nn6"
    run(go())


# ---------------------------------------------------------------------------------------------------------- T7 docs audit
# 1. a paste passes on its own (no ⌘S, no Check my work); 2. a stray cue never passes the next step; 3. a new take
# resets VS Code's open nn.py through the companion (the stub below stands in for server.workspace.vscode_ext).

class FakeBuffers:
    """VS Code's open nn.py as the companion reads it (editor_text.EditorBuffers' surface): unsaved text included."""

    def __init__(self) -> None:
        self.buf: str | None = None

    def clear(self) -> None:
        pass

    async def refresh(self, paths, folder=None) -> None:
        pass

    def text(self, path):
        return self.buf


class FakeCompanion:
    """The companion's HTTP API on :8791 (vscode_ext.buffer_text / apply), recording every call."""

    def __init__(self, bufs: FakeBuffers) -> None:
        self.bufs, self.calls = bufs, []

    def buffer_text(self, file, *, folder=None, **_kw):
        self.calls.append(("text", str(file)))
        return {"ok": True, "file": str(file), "text": self.bufs.buf, "dirty": True}

    def apply(self, file, new_text=None, *, edits=None, save=True, reveal=True, folder=None):
        self.calls.append(("apply", str(file), new_text, save, reveal))
        self.bufs.buf = new_text  # VS Code now shows it, saved
        return {"ok": True, "file": str(file), "saved": save, "dirty": False}


def _paste_unsaved(rig: Rig, bufs: FakeBuffers, text: str) -> None:
    """A paste into VS Code, NOT saved: only the buffer has it."""
    disk = (rig.workdir / "nn.py").read_text()
    bufs.buf = (bufs.buf if bufs.buf is not None else disk) + text


def test_a_paste_passes_without_a_save(rig):
    """Demo, like a real lesson: the pasted step passes from VS Code's buffer within a tick, nothing saved, no Check
    my work; Back to a done step never bounces forward on its own."""
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        bufs = FakeBuffers()
        rig.s._buffers = bufs
        on_disk = (rig.workdir / "nn.py").read_text()
        await rig.s.tick()  # nothing pasted yet: nothing passes
        await settle(rig)
        assert passed(rig) == []
        _paste_unsaved(rig, bufs, NN1_ZEROS)
        rig.clock.t += 0.5
        await rig.s.tick()  # the 1/s tick (the companion's dirty event does the same, ~0.2 s)
        await settle(rig)
        assert passed(rig) == ["nn1"] and rig.s.step["id"] == "nn2"
        assert (rig.workdir / "nn.py").read_text() == on_disk  # never saved
        from server.orchestrator import quiet_save  # the companion's dirty event: the same pass
        _paste_unsaved(rig, bufs, code("nn2"))
        quiet_save.on_vscode_event(rig.s, {"type": "dirty", "file": str(rig.workdir / "nn.py")})
        await settle(rig)
        assert passed(rig) == ["nn1", "nn2"] and rig.s.step["id"] == "nn3"
        # Back to nn2 (its code is there): it waits for a cue, never passes again by itself
        assert await stage.back(rig.s)
        await settle(rig)
        assert rig.s.step["id"] == "nn2"
        rig.clock.t += 5
        await rig.s.tick()
        await settle(rig)
        assert rig.s.step["id"] == "nn2" and passed(rig) == ["nn1", "nn2"]
        assert not [c for c in rig.of("card") if c["title"] in ("Nothing to do here", "Not yet")]
    run(go())


def test_a_stray_cue_never_passes_the_next_step(rig):
    """A second Check my work, or a late save, landing after the next step started: that step's code isn't there, so
    it doesn't pass (and says nothing). The presenter's next key still passes it on purpose."""
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        await save(rig, NN1_ZEROS)
        assert passed(rig) == ["nn1"] and rig.s.step["id"] == "nn2"
        m = rig.mark()
        await rig.s.action("check_step")  # the second press, right after nn2 started
        await settle(rig)
        rig.clock.t += 3
        await rig.s.action("check_step")  # and a later one
        await settle(rig)
        await save(rig, "\n")  # a late save
        assert rig.s.step["id"] == "nn2" and passed(rig) == ["nn1"]
        assert not [e for e in rig.since(m) if e["type"] == "card"
                    and e["payload"].get("title") in ("Nothing to do here", "Not yet")]
        assert not [e for e in rig.since(m) if e["type"] == "check.updated" and e["payload"]["status"] == "pass"]
        # nn2's code saved behind it, but the press is within the cue guard of nn3's start: not for nn3
        await save(rig, code("nn2"))
        assert passed(rig) == ["nn1", "nn2"] and rig.s.step["id"] == "nn3"
        (rig.workdir / "nn.py").write_text((rig.workdir / "nn.py").read_text() + code("nn3"))
        await rig.s.action("check_step")
        await settle(rig)
        assert rig.s.step["id"] == "nn3"
        rig.clock.t += stage.CUE_GUARD_S + 0.1  # a real press: passes
        await rig.s.action("check_step")
        await settle(rig)
        assert passed(rig) == ["nn1", "nn2", "nn3"]
        # the presenter's next key passes a typing step with nothing in it, on purpose
        await stage.next_step(rig.s)  # nn4 (run step: its good run)
        await settle(rig)
        assert rig.s.step["id"] == "nn5"
        assert await stage.next_step(rig.s)
        await settle(rig)
        assert passed(rig)[-1] == "nn5"
    run(go())


def test_a_new_take_resets_vs_codes_open_nn_py(rig, monkeypatch):
    """⌃⌥⌘R and a new Demo start put the clean nn.py back on disk AND in VS Code's open (unsaved) buffer, through
    the companion's /apply (saved), so the take starts on a clean editor."""
    async def go():
        bufs = FakeBuffers()
        comp = FakeCompanion(bufs)
        monkeypatch.setattr(type(rig.s), "_vscode_ext", lambda self: comp)
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        starter = curated._starter()
        rig.s._buffers = bufs
        _paste_unsaved(rig, bufs, NN1_ZEROS)  # the take's unsaved code in VS Code
        comp.calls.clear()
        assert await stage.restart(rig.s)
        await settle(rig)
        applies = [c for c in comp.calls if c[0] == "apply"]
        assert applies and applies[0][1].endswith("nn.py") and applies[0][2] == starter and applies[0][3] is True
        assert bufs.buf == starter and (rig.workdir / "nn.py").read_text() == starter
        assert rig.s.step["id"] == "nn1" and passed(rig) == []
        # a new Demo start from the launcher: the same reset
        _paste_unsaved(rig, bufs, code("nn1"))
        comp.calls.clear()
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        assert [c for c in comp.calls if c[0] == "apply"] and bufs.buf == starter
        # VS Code already clean: left alone
        comp.calls.clear()
        monkeypatch.setattr(comp, "buffer_text", lambda file, **kw: {"ok": True, "text": starter, "dirty": False})
        assert not await stage.reset_editor(rig.s, str(rig.workdir))
        assert not [c for c in comp.calls if c[0] == "apply"]
    run(go())
