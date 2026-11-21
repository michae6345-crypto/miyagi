"""Demo pre-test: every demo action (Explain, Hint, Show me, Diagram, Explain on a selection, Check my work) answers
fast, with the right event, for the current step, on BOTH demo paths. Offline: coach / finder / diagrams stubbed.

  path 1  the curated neural-net lesson ("Just teach me", mode "lesson"; and Demo, mode "demo"): nn1 fresh, nn2 after
          the sign bug's Not yet, nn4 after the zero-weights stuck run's Not yet (test_t8_replay's rig)
  path 2  the cached TensorFlow video lesson (demo/cache/lessons/5c0ea8a49f419487.json): s2 fresh, s2 after a typo's
          Not yet (test_video_replay's rig)

Run:  env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY python -m pytest server/tests/test_demo_actions.py -q
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque

import pytest

from server.orchestrator import curated, stage
from server.orchestrator.tests.conftest import _isolated_and_free  # noqa: F401 (autouse: no paid keys, temp state)
from server.orchestrator.tests.test_box_fresh import NN1_DONE, STEPS as NN_STEPS, _pasted  # noqa: F401
from server.orchestrator.tests.test_box_fresh import vs  # noqa: F401 (fixture: the fake VS Code)
from server.orchestrator.tests.test_run_pointing import _code_window
from server.orchestrator.tests.test_video_replay import (STEPS as V_STEPS, Replay, _offline)  # noqa: F401
from server.tests.test_t8_replay import (NN2_BUG, NN3_DONE, NN2_FIXED, RUNS, _zeros, save, settle, t8,  # noqa: F401
                                         tick, vscode_run)

PACE_S = 4.0  # seconds between two presses in a live demo (the rig's clock; nothing sleeps)
FAST_S = 3.0  # the engine answers a press within this (stubs: no model latency; a real answer adds the model's)
SELECTION = "d_h2 = d_out @ W3.T * (1 - h2 ** 2)"
V_SELECTION = "tf.keras.datasets.mnist.load_data()"
ACTIONS = ["explain", "hint", "show_me", "diagram", "explain_text", "check_step"]


async def press(rig, kind: str, text: str | None = None) -> tuple[list[dict], float]:
    """One press as the app sends it: action {kind, text?} -> (the events it caused, seconds to answer)."""
    rig.clock.t += PACE_S  # a presenter reads the last answer before the next press
    m = rig.mark()
    t0 = time.monotonic()
    await asyncio.wait_for(rig.s.action(kind, text), timeout=FAST_S + 2)
    dt = time.monotonic() - t0
    for _ in range(4):
        await rig.settle()
        await asyncio.sleep(0)
    await asyncio.sleep(0.15)
    await rig.settle()
    return rig.since(m), dt


def _of(ev: list[dict], t: str) -> list[dict]:
    return [e["payload"] for e in ev if e["type"] == t]


def box_up(rig) -> bool:
    """The overlay has a box up now: the last spotlight sent (in the whole lesson) is a box, not a clear."""
    sp = [e["payload"] for e in rig.events if e["type"] == "spotlight"]
    return bool(sp) and bool(sp[-1].get("rect"))


def judge(kind: str, ev: list[dict], dt: float, sid: str, text: str | None = None, up: bool = False) -> str | None:
    """None = OK, else what is wrong with this press's answer."""
    if dt > FAST_S:
        return f"slow: {dt:.1f}s"
    if errs := _of(ev, "error"):
        return f"error: {errs}"
    cards = _of(ev, "card") + _of(ev, "offtrack")
    ok_steps = {None, sid} | {p.get("nextStepId") for p in _of(ev, "step.passed")}  # Check passed it: the next step's
    for c in cards:
        if c.get("stepId") not in ok_steps:
            return f"card for the wrong step {c.get('stepId')} (now {sid}): {c.get('title')}"
        if not (c.get("title") or "").strip() or not ((c.get("body") or c.get("output") or "").strip()):
            return f"empty card: {json.dumps(c)[:200]}"
        if "couldn't reach" in (c.get("title", "") + c.get("body", "")).lower():
            return f"failure card: {c.get('title')}: {c.get('body')}"
    for d in _of(ev, "diagram"):
        if d.get("stepId") not in ok_steps:
            return f"diagram for the wrong step {d.get('stepId')}"
    spots = [p for p in _of(ev, "spotlight") if p.get("rect")]
    if kind == "explain" and text:
        ex = [c for c in cards if c.get("kind") == "explain" and c.get("title", "").startswith("About")]
        if not ex:
            return f"no selection Explain card: {[c.get('title') for c in cards]}"
        if text.split("(")[0].split()[0][:6] not in ex[-1]["title"]:
            return f"the card is not about the selection: {ex[-1]['title']}"
        return None
    if kind == "explain":
        if not [c for c in cards if c.get("kind") in ("explain", "answer", "hint", "step")]:
            return f"no Explain card: {[e['type'] for e in ev]}"
        return None
    if kind == "hint":
        h = [c for c in cards if c.get("kind") in ("hint", "where", "answer")]
        if not h:
            return f"no Hint card: {[e['type'] for e in ev]}"
        if not spots and not up and not h[-1].get("targets"):
            return f"Hint without a box or target: {h[-1].get('title')}"
        return None
    if kind == "show_me":
        if not spots and not up and not _of(ev, "video.seek") and not cards:
            return f"Show me answered nothing: {[e['type'] for e in ev]}"
        # a video lesson's Show me replays the step's clip (video.seek: the app's answer to Show me)
        return None
    if kind == "diagram":
        if not _of(ev, "diagram") and not [c for c in cards if "diagram" in (c.get("title", "") + c.get("body", "")).lower()]:
            return f"no diagram (nor a 'no diagram' notice): {[e['type'] for e in ev]}"
        return None
    if kind == "check_step":
        if not (_of(ev, "check.updated") or _of(ev, "step.passed") or cards):
            return f"Check my work answered nothing: {[e['type'] for e in ev]}"
        return None
    return None


async def sweep(rig, sid: str, sel: str, skip: tuple[str, ...] = ()) -> dict[str, str | None]:
    """Every demo action once on the current step `sid` -> {action: None | what was wrong}."""
    out: dict[str, str | None] = {}
    for a in ACTIONS:
        if a in skip:
            continue
        assert rig.s.step["id"] == sid, (a, rig.s.step["id"])
        kind, text = ("explain", sel) if a == "explain_text" else (a, None)
        ev, dt = await press(rig, kind, text)
        out[a] = judge(kind, ev, dt, sid, text, up=box_up(rig) or not rig.s.lesson_mode)
        # (a video lesson stubbed: no window on the FakeScreen and no coach targets, so its Hint is the card alone;
        # live, the coach's hint carries targets and the work window gets the box)
        if rig.s.step["id"] != sid:  # Check my work passed it: the remaining presses are on the next step
            sid = rig.s.step["id"]
    return out


def _ok(res: dict) -> None:
    bad = {f"{where}/{a}": why for where, r in res.items() for a, why in r.items() if why}
    assert not bad, json.dumps(bad, indent=1)


# ------------------------------------------------------------------ path 1: the curated neural-net lesson
def test_curated_lesson_every_action_on_nn1_nn2_nn4(t8):
    rig = t8
    rig.hub.history = deque(maxlen=None)  # the whole lesson (the hub keeps 500 by default: marks would stop moving)
    res: dict[str, dict] = {}

    async def go():
        rig.vs.loop = asyncio.get_running_loop()
        await rig.s.learn("build a neural network", mode="lesson")
        rig.s.last_obs = _code_window(f"nn.py — {rig.workdir.name}")
        rig.s.editor_open = True
        await settle(rig, 0.4)
        await rig.s.action("start")
        await settle(rig, 0.4)
        res["nn1-fresh"] = await sweep(rig, "nn1", SELECTION, skip=("check_step",))
        res["nn1-check"] = await sweep(rig, "nn1", SELECTION, skip=tuple(a for a in ACTIONS if a != "check_step"))
        await save(rig, NN1_DONE)
        await tick(rig, 2)
        assert rig.s.step["id"] == "nn2"
        res["nn2-fresh"] = await sweep(rig, "nn2", SELECTION, skip=("check_step",))
        await save(rig, NN2_BUG)
        await tick(rig, 8)
        assert rig.s.last_offtrack, "nn2: no Not yet on the sign bug"
        res["nn2-notyet"] = await sweep(rig, "nn2", SELECTION)
        await save(rig, NN2_FIXED)
        await tick(rig, 2)
        await save(rig, NN3_DONE)
        await tick(rig, 2)
        await settle(rig, 0.2)
        assert rig.s.step["id"] == "nn4", rig.s.step["id"]
        res["nn4-fresh"] = await sweep(rig, "nn4", SELECTION, skip=("check_step",))
        await save(rig, _zeros(NN3_DONE))
        await vscode_run(rig, RUNS["nn4"]["stuck"])
        await tick(rig, 6)
        assert rig.s.last_offtrack, "nn4: no Not yet on the zero-weights run"
        res["nn4-notyet"] = await sweep(rig, "nn4", SELECTION)

    asyncio.run(go())
    _ok(res)


def test_demo_mode_every_action_on_nn1_and_nn4_stuck(t8, monkeypatch):
    for name in ("GRADE_S", "ROW_S", "RUN_S", "STUCK_S"):
        monkeypatch.setattr(stage, name, 0.0)
    monkeypatch.delenv("MIYAGI_STAGE_STUCK", raising=False)
    rig = t8
    rig.hub.history = deque(maxlen=None)
    res: dict[str, dict] = {}

    async def go():
        rig.vs.loop = asyncio.get_running_loop()
        await rig.s.learn("teach me to build a neural network from scratch", mode="demo")
        rig.s.last_obs = _code_window(f"nn.py — {rig.workdir.name}")
        rig.s.editor_open = True
        await settle(rig, 0.2)
        res["nn1-fresh"] = await sweep(rig, "nn1", SELECTION, skip=("check_step",))
        await save(rig, _zeros(NN1_DONE))
        assert rig.s.step["id"] == "nn2"
        res["nn2-fresh"] = await sweep(rig, "nn2", SELECTION, skip=("check_step",))
        await save(rig, _zeros(NN2_FIXED))
        await save(rig, _zeros(NN3_DONE))
        assert rig.s.step["id"] == "nn4", rig.s.step["id"]
        await rig.s.action("run_command")
        await settle(rig, 0.2)
        assert rig.s.last_offtrack, "Demo nn4: no Not yet on the stuck run"
        res["nn4-notyet"] = await sweep(rig, "nn4", SELECTION)

    asyncio.run(go())
    assert rig.coach.calls == [], rig.coach.calls  # a Demo makes no coach calls
    _ok(res)


# ------------------------------------------------------------------ path 2: the cached TensorFlow video lesson
S2_TYPO = V_STEPS["s2"]["code"].replace("import tensorflow as tf", "import tensorflw as tf")


@pytest.fixture
def rp(tmp_path, monkeypatch) -> Replay:
    return Replay(tmp_path, monkeypatch)


def test_video_lesson_every_action_on_s2_fresh_and_after_a_typo(rp):
    res: dict[str, dict] = {}

    async def go():
        await rp.to("s2")
        rp.rig.mark = rp.rig.mark  # (Rig.mark / since index the hub history)
        res["s2-fresh"] = await sweep(rp.rig, "s2", V_SELECTION, skip=("check_step",))
        # the typo: the cell typed with `tensorflw`, run -> ModuleNotFoundError under it
        cell_out = ["ModuleNotFoundError: No module named 'tensorflw'"]
        from server.orchestrator.tests.test_video_replay import NB, _cell
        c = _cell(S2_TYPO, cell_out)
        c["metadata"]["step"] = "s2"
        rp.cells = [c]
        rp.save_notebook()
        await rp.work()
        await rp.frame(Code=[NB] + S2_TYPO.splitlines() + cell_out)
        ev, dt = await press(rp.rig, "check_step")
        res["s2-check"] = {"check_step": judge("check_step", ev, dt, "s2")}
        assert rp.s.step["id"] == "s2" and not rp.passed("s2")
        res["s2-notyet"] = await sweep(rp.rig, "s2", V_SELECTION)

    asyncio.run(go())
    _ok(res)


def test_a_press_after_its_card_was_replaced_answers_again(t8):
    """Fixed here: Explain -> Hint (or a Not yet) -> Explain within 15 s showed nothing the second time (_emit_card
    dropped it as a duplicate though the Hint had taken the app's one card slot). A repeat press with the card
    still up stays deduped."""
    rig = t8
    rig.hub.history = deque(maxlen=None)

    async def go():
        rig.vs.loop = asyncio.get_running_loop()
        await rig.s.learn("build a neural network", mode="lesson")
        rig.s.last_obs = _code_window(f"nn.py — {rig.workdir.name}")
        rig.s.editor_open = True
        await settle(rig, 0.4)
        await rig.s.action("start")
        await settle(rig, 0.4)
        first, _ = await press(rig, "explain")
        again, _ = await press(rig, "explain")  # the card is still up: no second copy
        await press(rig, "hint")
        after, dt = await press(rig, "explain")  # the Hint replaced it: Explain answers again
        sel1, _ = await press(rig, "explain", SELECTION)
        await press(rig, "hint")
        sel2, _ = await press(rig, "explain", SELECTION)
        return first, again, after, dt, sel1, sel2

    first, again, after, dt, sel1, sel2 = asyncio.run(go())
    ex = [c for c in _of(first, "card") if c.get("stepId") == "nn1"]
    assert ex, [e["type"] for e in first]
    assert not _of(again, "card"), _of(again, "card")
    assert [c["title"] for c in _of(after, "card")] == [ex[-1]["title"]], [e["type"] for e in after]
    assert judge("explain", after, dt, "nn1") is None
    assert _of(sel1, "card") and _of(sel2, "card") == _of(sel1, "card")
