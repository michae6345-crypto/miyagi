"""Circle to ask (Nov 22): the learner held Fn+Control, circled part of the screen and (maybe) said something.

The app sends the existing ask command with the circle's bounding box:
    action {kind: "ask", text: <spoken words or "What is this?">, region: ScreenRegion, source: "circle", askId}
main.py passes region / askId / source to LessonSession.action, whose _action hands an ask with a region here. It runs
inside action(), so proactive cards wait while the question is answered (ASK_KINDS), with or without a lesson.

1. One frame captured now (ScreenBridge.ask_frame: also while the reader is paused, since the learner asked; the
   picture is dropped again after). No Screen Recording / no reader / the display asleep: a plain "I can't see your
   screen" card. A capture that fails otherwise falls back to the last frame's text (no picture) when it is fresh.
2. The coach (server/coach/circle.py) reads the boxes inside the region, crops it, and asks Haiku; with no model it
   answers with the text it read.
3. The answer: card {kind: "answer", askId, region, stepId?}. When the answer names one box inside the region, an
   annotate {marks: [{why: "answer", askId, ...}], holdMs} follows, so the buddy circles it.

The crop and the screen text are never logged or stored (the session record keeps the question and the region's size).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

log = logging.getLogger("orchestrator.circle_ask")

CAPTURE_S = 3.0  # one capture + OCR is ~0.3-0.5 s; never hold the learner's answer longer than this
LAST_FRAME_S = 5.0  # a failed capture may still use the last frame's text when it is at most this old
HOLD_MS = 6000  # how long the buddy's circle stays (the app also fades it on a click there or a step change)


def _region(region: Any) -> dict | None:
    if region is None:
        return None
    if hasattr(region, "model_dump"):
        region = region.model_dump()
    return dict(region) if isinstance(region, dict) else None


def _down(session: Any) -> str | None:
    """Why the screen can't be read now, before trying ("no_screen" without any reader)."""
    if getattr(session, "screen", None) is None:
        return "no_screen"
    try:
        return session.screen_down_reason(include_ax=False)
    except Exception:  # noqa: BLE001
        return None


async def capture(session: Any) -> tuple[Any, Any, str | None]:
    """-> (observation, picture, None) or (observation | None, None, reason). Never raises."""
    if (reason := _down(session)) is not None:
        return None, None, reason
    grab = getattr(session.screen, "ask_frame", None)
    if grab is None:
        return None, None, "no_screen"
    try:
        obs, image = await asyncio.wait_for(asyncio.to_thread(grab), CAPTURE_S)
    except Exception as e:  # noqa: BLE001 - permission, timeout, a dead capture: say so, never crash the ask
        if type(e).__name__ == "ScreenPermissionError":
            return None, None, "no_permission"
        log.info("circle ask: capture failed (%s)", type(e).__name__)
        obs, image = None, None
    if obs is None:  # no fresh frame: the last one's text (no picture) while it is still what's on screen
        last = getattr(session, "last_obs", None)
        t = float(getattr(last, "t", 0) or 0) if last is not None else 0.0
        if last is not None and t and time.time() - t <= LAST_FRAME_S:
            return last, None, None
        return None, None, "no_frame"
    return obs, image, None


def offline_answer(step: dict | None, question: str, region: dict, obs: Any = None, image: Any = None,
                   context: dict | None = None, ask_id: str | None = None) -> dict:
    """The coach is stubbed (ORCH_STUBS) or failed: the text read inside the region, said plainly."""
    try:
        from server.coach import circle

        clip = circle.clamp_region(region, circle._get(obs, "screen"))
        if obs is None:
            card = circle.unseen_card("no_frame")
        elif clip is None:
            card = circle.unseen_card("other_display")
        else:
            card = circle.reading_card(circle.screen_for(obs, None, clip, context), "stub")
        return circle._finish(card, [], region, ask_id, step)
    except Exception:  # noqa: BLE001 - never a silent ask
        log.exception("circle ask: offline answer failed")
        return {**({"stepId": step["id"]} if step else {}), "kind": "answer", "title": "I can't see that yet",
                "body": "miyagi couldn't read that part of the screen.", **({"askId": ask_id} if ask_id else {}),
                "region": region, "marks": []}


def unseen_answer(step: dict | None, reason: str, region: dict, ask_id: str | None = None) -> dict:
    """No frame: say plainly that miyagi can't see the screen (and why, when it is the permission)."""
    try:
        from server.coach import circle

        return circle._finish(circle.unseen_card(reason), [], region, ask_id, step)
    except Exception:  # noqa: BLE001
        log.exception("circle ask: unseen card failed")
        return {**({"stepId": step["id"]} if step else {}), "kind": "answer", "title": "I can't see your screen",
                "body": "miyagi can't see your screen yet.", "marks": []}


def _context(session: Any, step: dict | None) -> dict:
    ctx: dict[str, Any] = {"lesson": (getattr(session, "graph", None) or {}).get("lesson", {}),
                           "lesson_folder": str(getattr(session, "workdir", "") or "") if step is not None else ""}
    if step is not None and hasattr(session, "_memory_kw"):  # server/context: the lesson's saved notes ({} when off)
        try:
            ctx.update(session._memory_kw(step, "explain"))
        except Exception:  # noqa: BLE001 - memory never costs the answer
            log.exception("circle ask: memory block failed")
    return ctx


async def answer(session: Any, step: dict | None, text: str | None, region: Any, ask_id: str | None = None) -> None:
    """Action ask with a region (from LessonSession._action): one answer card next to the circle, maybe a mark."""
    from server.coach.circle import DEFAULT_ASK

    reg = _region(region) or {}
    q = " ".join(str(text or "").split()) or DEFAULT_ASK
    session._record("question", {"kind": "circle", "text": q[:300],
                                 "size": [round(float(reg.get("w") or 0)), round(float(reg.get("h") or 0))]}, step)
    gen = session.step_gen
    if step is not None:
        await session._status("thinking", detail="Looking at that")
    obs, image, reason = await capture(session)
    if reason is not None:
        out = unseen_answer(step, reason, reg, ask_id)
        log.info("circle ask: can't see the screen (%s)", reason)
    else:
        try:
            out = await session.m.circle_ask(step, q, reg, obs=obs, image=image, context=_context(session, step),
                                             ask_id=ask_id)
        except Exception as e:  # noqa: BLE001 - a missing / failing coach: the text read, never "Couldn't reach"
            log.warning("circle ask: coach failed (%s); answering from the text read", type(e).__name__)
            out = offline_answer(step, q, reg, obs, None, None, ask_id)
    image = None  # the picture is done with: nothing holds it while the card goes out
    out = {k: v for k, v in dict(out).items() if not str(k).startswith("_")}
    marks = [m for m in (out.pop("marks", None) or []) if isinstance(m, dict)]
    if step is not None and gen != session.step_gen:
        return  # the learner moved to another step meanwhile: an answer about the old one would mislead
    if ask_id:
        out["askId"] = ask_id
    if reg:
        out["region"] = {k: reg[k] for k in ("x", "y", "w", "h", "displayId", "scale") if k in reg}
    if step is not None:
        out["stepId"] = step["id"]
    await session._emit_card(out, window_s=0.0)  # a second circle on the same spot is a new question
    if marks:
        await session.emit("annotate", {"marks": marks, "holdMs": HOLD_MS})
    if step is not None:
        await session._status("offtrack" if session.last_offtrack else ("passed" if session.passed else "watching"))
