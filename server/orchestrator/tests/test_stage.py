"""Demo lessons (stage.py): the launcher's Demo option walks the neural-net lesson without grading anything.
Run from the repo root:  python -m pytest server/orchestrator/tests/test_stage.py -q"""

from __future__ import annotations

import asyncio

import pytest

from server.orchestrator import stage
from server.orchestrator.tests.test_session import Rig
from shared.contracts.events import parse_app_message

ZEROS = "W1 = np.zeros((2, 4))\nW2 = np.zeros((4, 1))\n"
RANDOM = "W1 = np.random.randn(2, 4) * 0.5\nW2 = np.random.randn(4, 1) * 0.5\n"


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
        assert not [c for c in rig.of("card") if c.get("kind") == "setup"]  # never "Install NumPy"
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
        await save(rig, ZEROS)
        rows = {c["checkId"]: c["status"] for c in rig.of("check.updated") if c["stepId"] == "nn1"}  # the latest
        assert rows and set(rows.values()) == {"pass"}
        assert passed(rig) == ["nn1"] and rig.s.step["id"] == "nn2"
        # step 2: a save passes it, whatever the file holds
        await save(rig, "\n")
        # step 3: Check my work passes it without a save
        rig.clock.t += 1
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
        assert any(c["title"].startswith("Ran ") and "0.2500" in (c.get("output") or "") for c in cards)
        rows = {e["payload"]["checkId"]: e["payload"]["status"] for e in ev if e["type"] == "check.updated"}
        assert sorted(rows.values()) == ["fail", "pass"]  # the loss row fails, the saved file's row stays green
        off = [e["payload"] for e in ev if e["type"] == "offtrack"]
        assert off and off[0]["stepId"] == "nn4" and "0.25" in off[0]["title"]
        diag = [e["payload"] for e in ev if e["type"] == "diagram"]
        assert diag and "same neuron" in diag[-1].get("caption", "")  # four identical neurons in the panel
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
        assert good["status"] == "pass" and "0.0009" in good.get("detail", "")
        # step 5: save; step 6: run -> the lesson is done, the panel shows their network answering
        await save(rig, "\n")
        m = rig.mark()
        await rig.s.action("run_command")
        await settle(rig)
        assert passed(rig) == ["nn1", "nn2", "nn3", "nn4", "nn5", "nn6"]
        assert any("0 1 1 0" in (e["payload"].get("caption") or "") for e in rig.since(m) if e["type"] == "diagram")
        assert not rig.of("error")
        assert not [c for c in rig.of("card") if c.get("title") == "Not yet"]
    run(go())


def test_no_stuck_run_when_nn_py_starts_random(rig):
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        for _ in range(3):
            await save(rig, RANDOM)
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
        await save(rig, ZEROS)
        for _ in range(2):
            await save(rig, "\n")
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
        (rig.workdir / "nn.py").write_text("x = 1" + chr(10))
        await rig.s.on_file_change([str(rig.workdir / "nn.py")])  # the save's pass starts
        await rig.s.action("check_step")  # and Check my work right behind it
        await settle(rig)
        await asyncio.sleep(0.3)
        await settle(rig)
        assert passed(rig) == ["nn1"]
        assert not [c for c in rig.of("card") if c["title"] in ("Nothing to do here", "Not yet")]
    run(go())
