"""Desktop test 9 (Nov 15 06:12-06:19, "Watch a video": Kie Codes' TensorFlow MNIST video, 7 generated steps): the step
checks of a generated video lesson were graded wrongly. The lesson is the cached build the test used
(fixtures/t9_lesson_5c0ea8a4.json = demo/cache/lessons/5c0ea8a49f419487.json). No model call anywhere.

  V1  the checks ran at step start before the screen reader resumed: "screen reading is off: can't see Terminal" and the
      screen_absent "No terminal errors" PASSED ("screen reading is off, so nothing to flag"), then stayed green.

Run from the repo root:  python -m pytest server/tests/test_t9_checks.py -q"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from server.checks.evaluator import RunContext, evaluate_gate, evaluate_step

FIXTURE = Path(__file__).parent / "fixtures" / "t9_lesson_5c0ea8a4.json"


def lesson() -> dict:
    return copy.deepcopy(json.loads(FIXTURE.read_text()))


def step(sid: str) -> dict:
    return next(s for s in lesson()["steps"] if s["id"] == sid)


def by_id(results: list[dict]) -> dict[str, dict]:
    return {r["checkId"]: r for r in results}


# ------------------------------------------------------------------ V1: no real look, no verdict
def test_v1_no_frame_yet_leaves_every_screen_check_pending():
    s1 = step("s1")
    for seg in (None, True, False):
        res = by_id(evaluate_step(s1, RunContext(segment_done=seg)))  # screen None: the reader isn't live yet
        assert {r["status"] for r in res.values()} == {"pending"}, res
        assert res["s1c3"]["status"] == "pending"  # "No terminal errors" never passes on nothing
        assert not any("screen reading is off" in r["detail"] for r in res.values())
    # the first real frame grades them: the terminal shows no error yet, the command hasn't printed anything
    res = by_id(evaluate_step(s1, RunContext(screen={"Terminal": ["tripi@mac lesson % "]})))
    assert res["s1c1"]["status"] == "fail" and res["s1c3"]["status"] == "pass"


def test_v1_session_step_start_before_the_reader_resumes(tmp_path, monkeypatch):
    """The real session: step.started's first evaluation runs while the FakeScreen has no frame (lines() -> None)."""
    from server.orchestrator.modules import Modules
    from server.orchestrator.screen_bridge import FakeScreen
    from server.orchestrator.tests.test_session import Rig

    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    screen = FakeScreen()  # no text: no frame yet
    rig = Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,coach,finder,diagrams"), screen=screen)

    async def go():
        await rig.s.load_graph(lesson())
        await rig.settle()
        first = {p["checkId"]: p for p in rig.of("check.updated") if p["stepId"] == "s1"}
        assert first["s1c3"]["status"] == "pending", first
        assert not any("screen reading is off" in (p.get("detail") or "") for p in rig.of("check.updated"))
        # the reader is live: a Terminal frame with an error in it fails the row (it was never latched green)
        screen.text["Terminal"] = ["$ pip3 install jupyter", "ERROR: Could not find a version"]
        await rig.s.evaluate("screen")
        await rig.settle()
        rows = [p for p in rig.of("check.updated") if p["checkId"] == "s1c3"]
        assert all(p["status"] != "pass" for p in rows), rows

    asyncio.run(go())
