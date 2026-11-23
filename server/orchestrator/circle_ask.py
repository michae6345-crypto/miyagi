"""Circle to ask (Nov 22): the learner held Fn+Control, circled part of the screen and (maybe) said something.

The app sends the existing ask command with the circle's bounding box:
    action {kind: "ask", text: <spoken words or "What is this?">, region: ScreenRegion, source: "circle", askId}
main.py passes region / askId / source to LessonSession.action, whose _action hands an ask with a region here. It runs
inside action(), so proactive cards wait while the question is answered (ASK_KINDS), with or without a lesson.

1. One frame captured now on the display the learner circled on (ScreenBridge.ask_frame(region.displayId) ->
   ScreenReader.capture_once: also while the reader is paused, since the learner asked; the frame is never published
   to the session or kept by the reader). No Screen Recording / no reader / the display asleep / only a DEMO fixture
   frame: a plain "I can't see your screen" card. A capture that fails otherwise falls back to the last frame's text
   (no picture) when it is fresh and live.
2. The coach (server/coach/circle.py) reads the boxes inside the region, crops it, and asks Haiku; with no model it
   answers with the text it read.
3. The answer: card {kind: "answer", askId, region, stepId?}. When the answer names one box inside the region, an
   annotate {marks: [{why: "answer", askId, ...}], holdMs} follows, so the buddy circles it.

The crop and the screen text are never logged or stored (the session record keeps the question and the region's size).

Every circle ask gets one card with its askId, so the app's pending ink never waits for its own timeout: the answer,
"I can't see your screen", a failure card (LessonSession.action stamps askId + region on it), or, when the learner
changed step while it was answered, a short "moved on" card. Only an ask whose lesson ended meanwhile gets no card
(the engine drops every answer of an ended lesson): the app's pending-circle timeout covers that one.
"""

from __future__ import annotations

import asyncio
import logging
import os
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


def _display_id(region: dict | None) -> int | None:
    did = (region or {}).get("displayId")
    if isinstance(did, bool) or not isinstance(did, (int, float)):
        return None
    return int(did) if float(did).is_integer() else None


def _dev_fixture(session: Any) -> bool:
    """A screen fixture was asked for on purpose (TUT_SCREEN_FIXTURE / the reader's fixture arg: dev and tests)."""
    if os.environ.get("TUT_SCREEN_FIXTURE"):
        return True
    return bool(getattr(getattr(getattr(session, "screen", None), "reader", None), "fixture", None))


def _real(obs: Any, session: Any) -> bool:
    """Is this frame the learner's real screen? DEMO=1 without Screen Recording swaps in a fixture PNG (source
    "fixture:..."): explaining that would explain a screen the learner never saw."""
    src = obs.get("source", "live") if isinstance(obs, dict) else getattr(obs, "source", "live")
    return str(src or "live") == "live" or _dev_fixture(session)


async def capture(session: Any, display_id: int | None = None) -> tuple[Any, Any, str | None]:
    """-> (observation, picture, None) or (None, None, reason). `display_id`: the display the learner circled on
    (ScreenRegion.displayId). Never raises."""
    if (reason := _down(session)) is not None:
        return None, None, reason
    grab = getattr(session.screen, "ask_frame", None)
    if grab is None:
        return None, None, "no_screen"
    try:
        obs, image = await asyncio.wait_for(asyncio.to_thread(grab, display_id), CAPTURE_S)
    except Exception as e:  # noqa: BLE001 - permission, timeout, a dead capture: say so, never crash the ask
        if type(e).__name__ == "ScreenPermissionError":
            return None, None, "no_permission"
        log.info("circle ask: capture failed (%s)", type(e).__name__)
        obs, image = None, None
    if obs is not None and not _real(obs, session):
        log.info("circle ask: only a fixture frame (DEMO without Screen Recording); not explaining it")
        return None, None, "no_permission"
    if obs is None:  # no fresh frame: the last one's text (no picture) while it is still what's on screen
        last = getattr(session, "last_obs", None)
        t = float(getattr(last, "t", 0) or 0) if last is not None else 0.0
        if last is not None and t and time.time() - t <= LAST_FRAME_S and _real(last, session):
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


MOVED_ON = {"kind": "answer", "title": "We moved on", "body": "Circle it again to ask about this step."}


def failed_card(step: dict | None, region: dict, ask_id: str | None, card: dict | None = None) -> dict:
    """The ask failed (LessonSession.action's except path): `card` (the session's "Claude couldn't answer", with Try
    again) or a plain one, stamped with askId and region so the app can match it to the ink and stop waiting."""
    out = dict(card) if card else {**({"stepId": step["id"]} if step else {}), "kind": "answer",
                                   "title": "I couldn't read that", "body": "Try circling it again in a moment."}
    if ask_id:
        out["askId"] = ask_id
    if region:
        out["region"] = {k: region[k] for k in ("x", "y", "w", "h", "displayId", "scale") if k in region}
    return out


async def moved_on(session: Any, region: dict, ask_id: str | None) -> None:
    """The learner changed step while this was answered: no answer about the old step, but one short card with the
    askId (no stepId), so the app's pending circle is answered instead of waiting for its timeout."""
    from .session import _GEN

    card = failed_card(None, region, ask_id, MOVED_ON)
    token = _GEN.set(session.step_gen)  # emit drops an answer made for an older step; this one is about none
    try:
        await session._emit_card(card, window_s=0.0)
    finally:
        _GEN.reset(token)


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
    obs, image, reason = await capture(session, _display_id(reg))
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
        await moved_on(session, reg, ask_id)  # an answer about the old step would mislead; the ink still gets one
        return
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
