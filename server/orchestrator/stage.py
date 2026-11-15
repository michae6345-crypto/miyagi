"""Demo lessons: the launcher's Demo option (learn mode "demo"), or MIYAGI_STAGE=1 for every lesson.

A Demo lesson is the curated neural-net lesson (curated.py: its folder, cards, hints, Explain and live network
diagrams, unchanged), staged so nothing on stage can break:

  - Any goal starts it (the launcher text is kept as what was asked).
  - A typing step passes on cue: a save of the lesson folder (after the step's first DWELL_S seconds), Check my work,
    or the presenter's next key. Whatever the file holds, even nothing. The rows go green one by one, then the step
    passes the normal way (step.passed, the next step starts).
  - A run step never runs anything: Run it for me (and Check my work, Do it for me, a `python3 nn.py` typed in VS
    Code's terminal) shows a recorded run of the lesson's own code (demo/cache/stage/nn-runs.json, made by
    scripts/make_stage_runs.py: real NumPy output). Its loss lines feed the app's live curve and the network panel.
  - One planned "Not yet": on Train it, the FIRST run is the stuck one (loss 0.2500 on every line, four identical
    neurons in the panel, the off-track card from demo/cache/coach/nn4.json, the stuck hint ladder) when nn.py starts
    W1 or W2 without random numbers (the zeros shortcut in step 1). Any later run learns. MIYAGI_STAGE_STUCK=always
    makes the first run stuck whatever the file says; never: no stuck run.
  - No grading, judging, screen reading, setup card, idle nudges or coach calls: evaluate() and tick() stand back.

Presenter (main.py): POST /stage/next (pass the step), /stage/back, /stage/restart (step 1, clean nn.py), GET /stage.
The app's main process binds them to keys while a Demo lesson runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from . import config, curated

log = logging.getLogger("orchestrator.stage")

GOAL = "build a neural network"
RUNS_FILE = config.DEMO_CACHE / "stage" / "nn-runs.json"
COACH_FILE = config.DEMO_CACHE / "coach" / f"{curated.TRAIN_STEP}.json"


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


DWELL_S = _f("MIYAGI_STAGE_DWELL_S", 2.5)  # a save in a step's first seconds (the last step's own save) doesn't count
GRADE_S = _f("MIYAGI_STAGE_GRADE_S", 1.0)  # "checking" before the first row goes green
ROW_S = _f("MIYAGI_STAGE_ROW_S", 0.35)  # between rows
RUN_S = _f("MIYAGI_STAGE_RUN_S", 1.4)  # Run it for me: how long the run takes
STUCK_S = _f("MIYAGI_STAGE_STUCK_S", 2.0)  # the stuck run's output on screen before the "Not yet" card

_RAND = re.compile(r"rand")
_INIT = re.compile(r"^\s*(W1|W2)\s*=\s*(.+)$", re.M)


def forced() -> bool:
    """MIYAGI_STAGE=1 (set when starting the engine): every lesson is a Demo lesson."""
    return os.environ.get("MIYAGI_STAGE", "").strip().lower() in ("1", "true", "on", "yes")


def wanted(mode: str | None) -> bool:
    return mode == "demo" or forced()


def mark(graph: dict) -> dict:
    graph.setdefault("lesson", {})["stage"] = True
    return graph


def on_graph(graph: dict | None) -> bool:
    return bool(((graph or {}).get("lesson") or {}).get("stage"))


def on(session: Any) -> bool:
    return on_graph(getattr(session, "graph", None))


# ---------------------------------------------------------------------------------------------------------- state

def _st(session: Any) -> dict:
    """Per lesson start (lesson_epoch): how many times each step ran, which steps are being passed."""
    epoch = getattr(session, "lesson_epoch", 0)
    st = getattr(session, "_stage", None)
    if not isinstance(st, dict) or st.get("epoch") != epoch:
        st = {"epoch": epoch, "runs": {}, "passing": set(), "running": set()}
        session._stage = st
    return st


def _runs() -> dict:
    try:
        return json.loads(RUNS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("stage: %s missing (python3 scripts/make_stage_runs.py)", RUNS_FILE)
        return {}


def _lines(sid: str, stuck: bool) -> list[str]:
    runs = _runs().get(sid) or {}
    return list(runs.get("stuck" if stuck else "good") or runs.get("good") or [])


def _is_run(session: Any, step: dict) -> bool:
    return bool(session._run_command(step) or (step.get("run_command") or "").strip())


async def _file_text(session: Any) -> str:
    """nn.py as VS Code has it (the companion's exact text, unsaved edits too), else as saved."""
    path = Path(session.workdir) / curated.FILE
    try:
        await session._buffers.refresh([path], session.workdir)
        text = session._buffers.text(path)
        if text is not None:
            return text
    except Exception:  # noqa: BLE001 - no companion: the disk
        pass
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


async def _stuck_wanted(session: Any) -> bool:
    mode = os.environ.get("MIYAGI_STAGE_STUCK", "zeros").strip().lower()
    if mode in ("always", "1", "yes"):
        return True
    if mode in ("never", "0", "no", "off"):
        return False
    inits = dict(_INIT.findall(await _file_text(session)))
    return any(not _RAND.search(rhs) for rhs in inits.values())  # W1 or W2 not started random (zeros, ones, ...)


def _quiet() -> None:
    """This press is already being answered (its step's run or pass is under way): no "Nothing to do here" /
    "Not yet" notice for it (LessonSession.action sends one for a press that sent nothing)."""
    from .session import _ANSWERED  # (session imports this module)

    if (answered := _ANSWERED.get()) is not None:
        answered.add("card")


# ---------------------------------------------------------------------------------------------------------- passing

def _detail(step: dict, check: dict, lines: list[str]) -> str:
    if check.get("type") == "metric_threshold":
        losses = curated.parse_output(lines)["losses"]
        if losses:
            e, v = losses[-1]
            return f"loss {v:.4f} at epoch {e}"
    if check.get("type") == "output_contains" or (check.get("app") or "") == "Terminal":
        return next((ln.strip() for ln in lines if ln.strip().startswith("[")), "seen in the terminal")
    return f"found in {step.get('file') or curated.FILE}"


async def _pass(session: Any, step: dict, gen: int, lines: list[str] | None = None, fast: bool = False) -> None:
    """The step's rows go green one by one, then the step passes the normal way."""
    st = _st(session)
    sid = step.get("id")
    if gen != session.step_gen or session.passed or sid in st["passing"]:
        if sid in st["passing"]:
            _quiet()
        return
    st["passing"].add(sid)
    try:
        await session._status("thinking")
        await asyncio.sleep(0.2 if fast else GRADE_S)
        for c in session.display_checks(step):
            if gen != session.step_gen or session.passed:
                return
            label = c.get("label", c["id"])
            detail = _detail(step, c, lines or [])
            session.check_state[c["id"]] = {"label": label, "status": "pass", "detail": detail}
            await session.emit("check.updated", {"stepId": sid, "checkId": c["id"], "label": label, "status": "pass",
                                                 "detail": detail})
            await asyncio.sleep(0.1 if fast else ROW_S)
        async with session._lock:
            if gen == session.step_gen and not session.passed:
                session.last_offtrack = None
                await session._pass_step()
    finally:
        st["passing"].discard(sid)


async def _stuck(session: Any, step: dict, lines: list[str]) -> None:
    """The planned "Not yet": the training check fails on the run's flat loss, and the coach's card says why."""
    sid, gen = step.get("id"), session.step_gen
    await asyncio.sleep(STUCK_S)  # the run's output and the four identical neurons first, then the verdict
    if gen != session.step_gen or session.passed:
        return
    losses = curated.parse_output(lines)["losses"]
    v = losses[-1][1] if losses else curated.STUCK_LOSS
    e = losses[-1][0] if losses else 4000
    for c in session.display_checks(step):  # the loss row fails on the flat loss; the file rows stay green
        label = c.get("label", c["id"])
        bad = c.get("type") == "metric_threshold"
        status, detail = ("fail", f"loss {v:.4f} at epoch {e}") if bad else ("pass", _detail(step, c, lines))
        session.check_state[c["id"]] = {"label": label, "status": status, "detail": detail}
        await session.emit("check.updated", {"stepId": sid, "checkId": c["id"], "label": label, "status": status,
                                             "detail": detail})
    try:
        card = json.loads(COACH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        card = {"severity": "fail", "title": f"Loss is stuck at {v:.2f}",
                "body": "All four hidden neurons start the same, so they stay copies. Start W1 and W2 random.",
                "actions": ["explain", "hint", "show_me"]}
    card["stepId"] = sid
    session.gate_open = session.screen_gate_open = True
    session.last_offtrack = card
    session._last_card_t = session.clock()
    await session.emit("offtrack", card)
    session._say("offtrack", card)
    await session._status("offtrack")


# ---------------------------------------------------------------------------------------------------------- hooks

async def evaluate(session: Any, trigger: str) -> None:
    """Stands in for LessonSession.evaluate: only a save passes a typing step (after its first seconds)."""
    step = session.step
    if (step is None or session.passed or session.phase != "active" or session.awaiting_resume
            or trigger != "file" or _is_run(session, step)):
        return
    if session.clock() - session.step_t0 < DWELL_S:
        return
    session._spawn(_pass(session, step, session.step_gen))


async def check(session: Any, step: dict) -> None:
    """Check my work: a typing step passes now; a run step runs (the recorded run) and is graded on it."""
    if _is_run(session, step):
        await run(session, step)
    else:
        await _pass(session, step, session.step_gen)


async def run(session: Any, step: dict, typed: bool = False) -> None:
    """A recorded run of this step (Run it for me; typed=True: the learner ran it in VS Code's terminal, which
    already shows its output, so no card). The first Train it run is the stuck one when nn.py starts at zeros."""
    gen, sid = session.step_gen, step.get("id")
    st = _st(session)
    if session.passed or sid in st["running"] or sid in st["passing"]:
        if not session.passed:
            _quiet()  # a second press while this step's run (or its pass) is still going: one run, not two
        return
    st["running"].add(sid)
    try:
        await _run(session, step, gen, sid, st, typed)
    finally:
        st["running"].discard(sid)


async def _run(session: Any, step: dict, gen: int, sid: str, st: dict, typed: bool) -> None:
    n = st["runs"].get(sid, 0)
    st["runs"][sid] = n + 1
    stuck = sid == curated.TRAIN_STEP and n == 0 and await _stuck_wanted(session)
    lines = _lines(sid, stuck)
    cmd = session._run_command(step) or (step.get("run_command") or "").strip() or f"python3 {curated.FILE}"
    session._acted()
    if not typed:
        await session._status("thinking")
        await asyncio.sleep(RUN_S)
    if gen != session.step_gen or session.passed:
        return
    run_id = f"stage-{sid}-{n}-{int(time.time() * 1000)}"
    await session.ingest({"kind": "run_started", "run_id": run_id, "command": cmd, "cwd": session.workdir})
    await session.ingest({"kind": "output", "run_id": run_id, "lines": lines})
    losses = curated.parse_output(lines)["losses"]
    if losses:
        await session.ingest({"kind": "metrics", "run_id": run_id,
                              "metrics": [{"step": e, "name": "loss", "value": v} for e, v in losses]})
    await session.ingest({"kind": "run_ended", "run_id": run_id, "exit_code": 0})
    session._record("run_for_me", {"command": cmd[:200], "exit_code": 0, "stage": True}, step)
    if not typed:
        await session._card(step, f"Ran {cmd.splitlines()[0][:60]}", "It ran without errors.", kind="answer",
                            output="\n".join(lines[-8:]) or "(no output)")
    curated.after_evaluate(session, step, "run_end")  # the panel: four identical neurons, or their run
    if stuck:
        await _stuck(session, step, lines)
    else:
        await _pass(session, step, gen, lines)


async def next_step(session: Any) -> bool:
    """Presenter: pass the current step now (a run step gets its good run first, so the panel has its numbers)."""
    step = session.step
    if step is None or session.passed:
        return False
    if _is_run(session, step):
        st = _st(session)
        st["runs"][step.get("id")] = max(1, st["runs"].get(step.get("id"), 0))  # never the stuck run
        await run(session, step, typed=True)
    else:
        await _pass(session, step, session.step_gen, fast=True)
    return True


async def back(session: Any) -> bool:
    if session.step is None:
        return False
    await session.action("back", "prev")
    return True


async def restart(session: Any) -> bool:
    """Presenter: the Demo lesson from step 1 with a clean nn.py (the last attempt is kept, curated.prepare_folder)."""
    goal = ((session.graph or {}).get("lesson") or {}).get("asked") or getattr(session, "query", "") or GOAL
    await session.learn_demo(goal, fresh=True)
    return True


def last_hint(session: Any, step: dict) -> dict | None:
    """Hint pressed past the cached ladder: its last rung again (the coach's generic rungs mention a tutorial and a
    linked source this lesson doesn't have)."""
    for level in range(int(getattr(session, "hint_level", 0) or 0) - 1, -1, -1):
        if (card := curated.hint_card(session, step, level)) is not None:
            return card
    return None


def fallback_answer(session: Any, kind: str, text: str | None) -> dict | None:
    """A question that couldn't reach Claude (no Wi-Fi): Explain more on a selection gets its offline card, any other
    question the step's own Explain card, in place of "Couldn't reach Claude"."""
    step = session.step
    if step is None:
        return None
    try:
        if kind == "explain" and (text or "").strip():
            from .selection import offline_card, recall

            sel = recall(session, text)
            return {**offline_card(step, sel), "stepId": step["id"], "title": sel["title"]}
        card = curated.explain_card(session, step)
        return {**card, "kind": "answer"} if card else None
    except Exception:  # noqa: BLE001 - the plain failure card is still there
        log.exception("stage: no fallback answer")
        return None


def state(session: Any) -> dict:
    step = session.step
    return {"on": on(session), "forced": forced(), "step": (step or {}).get("id"),
            "runs": dict(_st(session)["runs"]) if on(session) else {}}
