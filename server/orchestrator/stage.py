"""Demo lessons: the launcher's Demo option (learn mode "demo"), or MIYAGI_STAGE=1 for every lesson.

A Demo lesson is the curated neural-net lesson (curated.py: its folder, cards, hints, Explain and live network
diagrams, unchanged), staged so nothing on stage can break:

  - Any goal starts it (the launcher text is kept as what was asked).
  - A typing step passes on its own once its code is in nn.py or VS Code's buffer (a paste, unsaved: no ⌘S, no Check
    my work; the companion's dirty event or the 1/s tick), or on cue: a save (after the step's first DWELL_S seconds)
    or Check my work, both only when the step's own code is there (its file_contains patterns, so the zeros shortcut,
    a paste in the wrong place or off indentation still count), or the presenter's next key (always). A cue arriving
    for the next step (a second Check my work, a late save) never passes it. The rows go green one by one, then the
    step passes the normal way (step.passed, the next step starts).
  - Every take is fresh (a Demo start, the presenter's restart): the clean nn.py on disk AND in VS Code's open buffer
    (reset_editor: the companion's /apply of the clean text, saved), never the last take's unsaved code.
  - A run step never runs anything: Run it for me (and Check my work, Do it for me, a `python3 nn.py` typed in VS
    Code's terminal) shows a recorded run of the lesson's own code (demo/cache/stage/nn-runs.json, made by
    scripts/make_stage_runs.py: real NumPy output). Its loss lines feed the app's live curve and the network panel.
  - One planned "Not yet": on Train it, the FIRST run is the stuck one (the loss at curated.STUCK_LOSS on every line,
    identical hidden neurons in the panel, the off-track card from demo/cache/coach/nn4.json, the stuck hint ladder)
    when nn.py starts any W<k> without random numbers (the zeros shortcut in step 1). Any later run learns. MIYAGI_STAGE_STUCK=always
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

from . import card_copy, config, curated

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
AGAIN_S = _f("MIYAGI_STAGE_AGAIN_S", 1.0)  # a run press this soon after the last run ended is the same press
CUE_GUARD_S = _f("MIYAGI_STAGE_CUE_GUARD_S", 1.5)  # a Check my work this soon after a step started was for the last one

_RAND = re.compile(r"rand")
_INIT = re.compile(r"^\s*(W\d+)\s*=\s*(.+)$", re.M)


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
        st = {"epoch": epoch, "runs": {}, "passing": set(), "running": set(), "ended": {}, "good": set(),
              "base": {}}  # base: step_gen -> the step's code was already there when it started (Back)
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


async def _begin(session: Any) -> None:
    """Work on the step ends the "Before you start" hold (E4) at once, so its box and the rest follow."""
    if getattr(session, "awaiting_start", False):
        await session._begin("work on a Demo step")


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


def _work_patterns(step: dict) -> list[str]:
    """What says the step's own code is in the file: its file_contains patterns (loose: the zeros shortcut, a paste in
    the wrong place or with off indentation all match), else its on-screen code patterns."""
    pats = [c["pattern"] for c in step.get("precision_checks") or []
            if c.get("type") == "file_contains" and c.get("pattern")]
    return pats or [c["pattern"] for c in step.get("checks") or []
                    if c.get("type") in ("file_contains", "screen_contains") and c.get("pattern")]


async def _work_here(session: Any, step: dict) -> bool:
    """The step's own code is in nn.py: VS Code's buffer (unsaved edits too) or the saved file. A step with nothing
    to look for counts as done (the cue guard still holds a stray Check my work)."""
    pats = _work_patterns(step)
    if not pats:
        return True
    if not getattr(session, "workdir", None):
        return False
    path = Path(session.workdir) / curated.FILE
    texts: list[str] = []
    try:
        session._buffers.clear()  # VS Code's text now (a paste a moment ago), not the last read's
        await session._buffers.refresh([path], session.workdir)
        if (buf := session._buffers.text(path)) is not None:
            texts.append(buf)
    except Exception:  # noqa: BLE001 - no companion: the disk
        pass
    try:
        texts.append(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        pass
    try:  # most of them, not all: a planted bug (the tanh slope's + sign) is still the step's code
        return any(2 * sum(bool(re.search(p, t, re.M)) for p in pats) >= len(pats) for t in texts)
    except re.error:
        return True


async def _stuck_wanted(session: Any) -> bool:
    mode = os.environ.get("MIYAGI_STAGE_STUCK", "zeros").strip().lower()
    if mode in ("always", "1", "yes"):
        return True
    if mode in ("never", "0", "no", "off"):
        return False
    inits = dict(_INIT.findall(await _file_text(session)))
    return any(not _RAND.search(rhs) for rhs in inits.values())  # a W<k> not started random (zeros, ones, ...)


def _quiet() -> None:
    """This press is already being answered (its step's run or pass is under way): no "Nothing to do here" /
    "Not yet" notice for it (LessonSession.action sends one for a press that sent nothing)."""
    from .session import _ANSWERED  # (session imports this module)

    if (answered := _ANSWERED.get()) is not None:
        answered.add("card")


# ---------------------------------------------------------------------------------------------------------- passing

def _detail(step: dict, check: dict, lines: list[str]) -> str:
    if check.get("type") == "metric_threshold":  # test 7: worded like the checks module, so the app reads the values
        if detail := curated.metric_detail(check, curated.parse_output(lines)["losses"]):
            return detail
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
    await asyncio.sleep(STUCK_S)  # the run's output and the identical neurons first, then the verdict
    if gen != session.step_gen or session.passed or sid in _st(session)["good"]:
        return  # moved on, or the presenter's next is passing it
    losses = curated.parse_output(lines)["losses"] or [(18000, curated.STUCK_LOSS)]
    v = losses[-1][1]
    for c in session.display_checks(step):  # the loss row fails on the flat loss; the file rows stay green
        label = c.get("label", c["id"])
        bad = c.get("type") == "metric_threshold"
        # test 7: "loss 0.4900 at step 18000, need < 0.01": the card's evidence shows yours 0.4900 | expected 0.01
        status, detail = ("fail", curated.metric_detail(c, losses)) if bad else ("pass", _detail(step, c, lines))
        session.check_state[c["id"]] = {"label": label, "status": status, "detail": detail}
        await session.emit("check.updated", {"stepId": sid, "checkId": c["id"], "label": label, "status": status,
                                             "detail": detail})
    try:
        card = json.loads(COACH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        card = {"severity": "fail", "title": f"Loss is stuck at {v:.2f}",
                "body": "Every hidden neuron starts the same, so they stay copies. Start the weights random.",
                "actions": ["explain", "show_me", "hint"]}
    card["stepId"] = sid
    session.gate_open = session.screen_gate_open = True
    session.last_offtrack = card
    session._last_card_t = session.clock()
    await session.emit("offtrack", card)
    session._say("offtrack", card)
    await session._status("offtrack")


# ---------------------------------------------------------------------------------------------------------- hooks

async def evaluate(session: Any, trigger: str) -> None:
    """Stands in for LessonSession.evaluate. A typing step passes once its own code is in nn.py or the buffer:
    "edit" (the companion's dirty / save / editor event, quiet_save.on_vscode_event; the 1/s tick) passes it on its
    own, unless that code was already there when the step started (Back to a done step: it waits for a cue, never
    jumps forward again by itself); "file" (a save, after the step's first DWELL_S seconds) is a cue. "start" notes
    whether the code was already there."""
    step = session.step
    if step is None or _is_run(session, step):
        return
    st, gen = _st(session), session.step_gen
    if trigger == "start":
        if gen not in st["base"]:  # the first look at this step decides (Start / _begin look again: not counted)
            st["base"][gen] = await _work_here(session, step)
        return
    if (session.passed or session.phase != "active" or session.awaiting_resume
            or trigger not in ("file", "edit") or step.get("id") in st["passing"]):
        return
    if trigger == "file" and session.clock() - session.step_t0 < DWELL_S:
        return
    if gen not in st["base"]:  # (not seen at its start: this look is its start)
        st["base"][gen] = await _work_here(session, step)
        if trigger == "edit":
            return
    if trigger == "edit" and st["base"][gen]:
        return
    if not await _work_here(session, step) or gen != session.step_gen or session.passed:
        return
    log.info("stage: %s's code is in %s (%s): passing", step.get("id"), curated.FILE, trigger)
    await _begin(session)
    session._spawn(_pass(session, step, gen))


async def tick(session: Any) -> None:
    """1/s, as quiet_save.poll in a real lesson: a pasted (unsaved) step passes within ~1 s, no ⌘S, no Check my work."""
    if session.awaiting_resume:
        return
    await evaluate(session, "edit")


async def check(session: Any, step: dict) -> None:
    """Check my work: a typing step passes now when its code is there; a run step runs (the recorded run) and is graded
    on it. A press in a typing step's first CUE_GUARD_S seconds, or with the step's code not there, passes nothing (a
    second press that arrived after the next step started is not for that step)."""
    if session.awaiting_resume:  # the "Continue where you left off?" card is up: that answer comes first
        return
    if _is_run(session, step):
        await _begin(session)
        await run(session, step)
        return
    gen, sid = session.step_gen, step.get("id")
    if sid in _st(session)["passing"]:
        _quiet()
        return
    if session.clock() - session.step_t0 < CUE_GUARD_S or not await _work_here(session, step):
        log.info("stage: Check my work on %s passes nothing (its code isn't in %s yet, or the press was the last "
                 "step's)", sid, curated.FILE)
        _quiet()
        return
    await _begin(session)
    await _pass(session, step, gen)


async def run(session: Any, step: dict, typed: bool = False) -> None:
    """A recorded run of this step (Run it for me; typed=True: the learner ran it in VS Code's terminal, which
    already shows its output, so no card). The first Train it run is the stuck one when nn.py starts at zeros."""
    gen, sid = session.step_gen, step.get("id")
    st = _st(session)
    # A second press while this step's run (or its pass) is going, or queued behind it (the socket runs commands one
    # at a time, so it arrives just after): one run, not two. A press a second later is a new run. Checked before
    # `passed`: the queued press of a run that LEARNED lands on the step it just passed (nn6: the last one), and
    # "Nothing to do here" must not cover that run's [-1.0, 0.0, 1.0] card (Demo rehearsal, Nov 15).
    if _is_run(session, step) and (sid in st["running"] or sid in st["passing"] or (
            not typed and session.clock() - st["ended"].get(sid, -1e9) < AGAIN_S)):
        _quiet()
        return
    if session.passed or session.awaiting_resume or not _is_run(session, step):
        return  # (a typing step has nothing to run: the session's "Nothing to do here" answers)
    await _begin(session)
    st["running"].add(sid)
    try:
        await _run(session, step, gen, sid, st, typed)
    finally:
        st["running"].discard(sid)
        st["ended"][sid] = session.clock()


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
    if stuck and sid in st["good"]:  # the presenter's next landed during this run: it learns
        stuck, lines = False, _lines(sid, False)
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
        await session._card(step, card_copy.ran(cmd), "It ran without errors.", kind="answer",
                            output="\n".join(lines[-8:]) or "(no output)")
    curated.after_evaluate(session, step, "run_end")  # the panel: identical neurons, or their run
    if stuck:
        await _stuck(session, step, lines)
    else:
        await _pass(session, step, gen, lines)


async def next_step(session: Any) -> bool:
    """Presenter: pass the current step now (a run step gets its good run first, so the panel has its numbers)."""
    step = session.step
    if step is None or session.passed or session.awaiting_resume:
        return False
    await _begin(session)
    if _is_run(session, step):
        st, sid = _st(session), step.get("id")
        st["good"].add(sid)  # never the stuck run, also for a run already under way (_run reads `good`)
        # (no bump of st["runs"] here: _run counts the run it plays, so GET /stage says 1 run, not 2)
        for _ in range(200):  # a Run it for me in flight finishes first (it now learns), then this one passes
            if sid not in st["running"] or session.step is not step:
                break
            await asyncio.sleep(0.05)
        if session.step is step and not session.passed:
            await run(session, step, typed=True)
    else:
        await _pass(session, step, session.step_gen, fast=True)
    return True


async def back(session: Any) -> bool:
    if session.step is None:
        return False
    await session.action("back", "prev")
    return True


async def reset_editor(session: Any, folder: str | Path | None) -> bool:
    """A new take (a Demo start, the presenter's restart): VS Code shows the clean nn.py that is now on disk, not the
    last take's unsaved code (VS Code reloads a clean buffer from disk by itself, never a dirty one). Through the
    companion's /apply: the whole text replaced with the clean file and saved, so the buffer is clean and matches the
    disk (File: Revert File's effect). Nothing open or already clean: untouched. -> reset."""
    if not folder:
        return False
    path = Path(folder) / curated.FILE
    try:
        clean = path.read_text(encoding="utf-8")
    except OSError:
        return False
    ext = await asyncio.to_thread(session._vscode_ext)
    if ext is None or not hasattr(ext, "apply"):
        return False
    try:
        buf = (await asyncio.to_thread(ext.buffer_text, path, folder=str(folder))
               if hasattr(ext, "buffer_text") else {})
        if buf is None or (buf.get("ok", True) and not buf.get("dirty") and buf.get("text") == clean):
            return False  # no VS Code window has the folder, or it already shows the clean file
        res = await asyncio.to_thread(ext.apply, path, clean, save=True, reveal=False, folder=str(folder))
    except Exception:  # noqa: BLE001 - the take still starts; the presenter can File: Revert File
        log.exception("stage: resetting %s in VS Code failed", path.name)
        return False
    try:
        session._buffers.clear()  # the next read sees the clean buffer
    except Exception:  # noqa: BLE001
        pass
    ok = bool(res and res.get("ok"))
    log.info("stage: a new take: %s reset in VS Code (%s)", path.name, "done" if ok else res)
    return ok


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
