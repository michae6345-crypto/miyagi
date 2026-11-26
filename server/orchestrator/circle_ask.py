"""Circle to ask (Nov 22): the learner held Fn+Control, circled part of the screen and (maybe) said something.

The app sends the existing ask command with the circle's bounding box:
    action {kind: "ask", text: <spoken words or "What is this?">, region: ScreenRegion, source: "circle", askId}
main.py passes region / askId / source to LessonSession.action, whose _action hands an ask with a region here. It runs
inside action(), so proactive cards wait while the question is answered (ASK_KINDS), with or without a lesson.

0. Fast path (Nov 22, coach/fast_ask.py, answer -> _stream): the ask may carry capture (AskCapture), the crop the
   app's helper made while the keys were held; shared.capture_file.take_capture checks, reads and deletes it, so
   nothing is captured at release. That crop is the raw screen: fast_region.from_capture runs Vision on it, redacts
   the text and blacks out every secret row (and greys other projects' windows) in its pixels before it is sent.
   Without one (or with no OCR, or a private app under the circle), fast_region.frame_for captures + crops now. The
   answer then streams (answer.delta, an annotate as soon as the model's first line names a spot, answer.done) and
   the card below carries the same text with no extra annotate. Nothing streamed (offline, no key, a 4xx, no
   picture): steps 1 to 3, as before, while the deadline allows. Words streamed and then it broke, a refusal, or no
   time left: a failed card. A miyagi cloud refusal (paused, quota, auth): its own card. Neither calls again.
   One deadline (ASK_DEADLINE_S after release_t) covers the stream, its retry and steps 1 to 3.
1. One frame captured now on the display the learner circled on (ScreenBridge.ask_frame(region.displayId, region)
   -> ScreenReader.capture_once: also while the reader is paused, since the learner asked; the frame is never
   published to the session or kept by the reader). It always tries, whatever the reader's last error says (that can
   be stale). No Screen Recording / no reader / a blank frame / only a DEMO fixture frame: a plain "I can't see your
   screen" card, worded from the reader's down_reason. A capture that fails otherwise falls back to the last frame's text
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
HOLD_MS = 10_000  # how long the buddy's circle stays, longer than 6 s so bon is seen there (Adrian, Nov 24; the app also fades it on a click there or a step change)
# The contract's promise (Action ask + region): every circle ask is answered within about this many seconds; the
# app (v2-integration features/circle) gives up at ASK_MAX_MS = 30 s. One deadline, ASK_DEADLINE_S after release_t,
# covers everything: the app crop's OCR, the stream, its one retry (fast_ask.ask_stream deadline=) and the one-shot
# answer (capture + session.m.circle_ask). A step starts only when enough of it is left, else the failed card goes.
ANSWER_WITHIN_S = 25.0
ASK_DEADLINE_S = 22.0  # after release_t: the last card goes out by then (plus the emit), under ANSWER_WITHIN_S
MIN_ONESHOT_S = 4.0  # the one-shot answer (session.m.circle_ask) starts only with this much of the deadline left
MIN_FALLBACK_S = 5.0  # ...and a capture at release before it only with this much


def _region(region: Any) -> dict | None:
    if region is None:
        return None
    if hasattr(region, "model_dump"):
        region = region.model_dump()
    return dict(region) if isinstance(region, dict) else None


def _down(session: Any) -> str | None:
    """Why the screen couldn't be read, for the wording of the "can't see" card only: it never stops a capture
    (last_error clears only when the reader's own loop captures again, so it can be stale for a paused reader)."""
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


async def capture(session: Any, display_id: int | None = None,
                  region: dict | None = None, *, timeout: float = CAPTURE_S) -> tuple[Any, Any, str | None]:
    """-> (observation, picture, None) or (None, None, reason). `display_id`: the display the learner circled on
    (ScreenRegion.displayId); `region`: the circle, so a display id that is not active still reads the display that
    holds it. `timeout`: at most CAPTURE_S (less when the ask's deadline is near). Never raises.

    It always tries a fresh capture: the reader's error state (down_reason) may be left over from a stall, a sleep or
    a permission granted since, and the learner asked now. down_reason only picks the words when nothing was seen."""
    if getattr(session, "screen", None) is None:
        return None, None, "no_screen"
    grab = getattr(session.screen, "ask_frame", None)
    if grab is None:
        return None, None, "no_screen"
    box = {k: region[k] for k in ("x", "y", "w", "h") if k in region} if isinstance(region, dict) else None
    try:
        obs, image = await asyncio.wait_for(asyncio.to_thread(grab, display_id, box or None),
                                            max(0.1, min(CAPTURE_S, timeout)))
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
        return None, None, _down(session) or "no_frame"
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


def cloud_card(step: dict | None, code: str) -> dict:
    """The miyagi cloud turned the ask away (fast_ask error "cloud:<code>": paused, quota, auth): its own words
    (server.config.CLOUD_ERRORS), the same as every other call's cloud card. No second call: it would be refused too."""
    try:
        from server.config import CLOUD_ERRORS
    except ImportError:  # pragma: no cover
        CLOUD_ERRORS = {}
    body = CLOUD_ERRORS.get(code) or "Try circling it again in a moment."
    return {**({"stepId": step["id"]} if step else {}), "kind": "answer", "title": "I can't answer right now",
            "body": body}


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


def _fast_ok() -> bool:
    """Can the streamed ask leave the engine? Offline (DEMO / ORCH_STUBS) or no key: the non-streaming path answers."""
    try:
        from server.coach import llm

        return not llm.offline_mode() and llm.has_credentials()
    except Exception:  # noqa: BLE001
        return False


def _take(capture_payload: Any) -> Any:
    """The helper's crop (shared.capture_file.take_capture: path checks, read, delete), or None. Never raises."""
    if capture_payload is None:
        return None
    try:
        from shared.capture_file import take_capture

        return take_capture(capture_payload)
    except Exception:  # noqa: BLE001 - a bad capture is never worse than no capture
        log.info("circle ask: the app's capture was not usable")
        return None


async def _stream(session: Any, step: dict | None, q: str, reg: dict, ask_id: str | None, capture_payload: Any,
                  release_t: float | None, moved: Any, deadline: float | None = None) -> tuple[Any, Any]:
    """The fast path (coach/fast_ask.py): -> (FastAskResult | None, fast_region.Prepared | None).

    1. The app's own crop (action ask capture: AskCapture), made by the helper while the keys were held: read and
       deleted now (take_capture), never a capture at release. It is always taken, also offline, so the file goes.
       The helper's crop is the raw screen: nothing in it is blacked out. fast_region.from_capture runs Vision on it
       off the event loop, redacts the text (server/screen/privacy), blacks out every row that held a secret and
       greys out other projects' VS Code windows in its pixels, then encodes it again; the redacted text goes as
       screen_text. Only that crop is ever sent.
    2. No app crop, OCR unavailable or failed, or a private app under the circle: capture + crop now
       (fast_region.frame_for, ask_frame under it: the reader's frame, with the same rows and windows hidden).
    deadline: the ask's one deadline (time.monotonic), for the stream and its retry (ask_stream).
    res None: nothing streamed (offline, no key, no picture); Prepared: the frame for the non-streaming answer."""
    cap = _take(capture_payload)
    if not _fast_ok():
        return None, None
    from server.coach import fast_ask

    from . import fast_region

    pre = None
    safe = None
    if cap is not None:  # never sent as is: OCR, secrets blacked out, other projects greyed (fast_region)
        safe = await fast_region.from_capture(session, cap)
        display_id = cap.displayId
    cap = None  # the helper's bytes: only the redacted crop goes on
    if safe is not None and safe.crop is not None:
        crop, screen_text, app = safe.crop, safe.screen_text, safe.app
    else:  # no app crop, no OCR, or a private app under the circle: capture at release (its frame leaves those out)
        pre = await fast_region.frame_for(session, ask_id, reg)
        if pre.reason is not None or pre.crop is None:
            return None, pre
        crop, screen_text, app, display_id = pre.crop, pre.screen_text, pre.app, _display_id(reg)
    safe = None
    jpeg, rect, w, h = crop
    del crop
    res = await fast_ask.ask_stream(
        jpeg, rect, w, h, q, fast_region.lesson_context(session, step, screen_text, app),
        emit=session.emit, ask_id=ask_id, display_id=display_id, step_id=step["id"] if step else None,
        release_t=release_t, should_stop=moved, deadline=deadline)
    return res, pre


async def answer(session: Any, step: dict | None, text: str | None, region: Any, ask_id: str | None = None, *,
                 app_capture: Any = None, release_t: float | None = None) -> None:
    """Action ask with a region (from LessonSession._action): one answer card next to the circle, maybe a mark.

    Fast path first (coach/fast_ask.py): the answer streams as answer.delta, a mark goes out as soon as the model's
    first line names one, answer.done closes it, then the card {kind: "answer", askId, region} with the same text and
    no extra annotate. `app_capture`: the app's crop (AskCapture), used (redacted) instead of a capture at release.
    `release_t`: time.monotonic() when the action arrived (main.py), for the ask's metrics and its one deadline
    (ASK_DEADLINE_S later; None: from now). Nothing streamed (offline, no key, a 4xx, no picture): the
    non-streaming path below (session.m.circle_ask), only while enough of the deadline is left. A refusal or a
    miyagi cloud refusal with no words: the failed card or the cloud card at once, never a second call."""
    from server.coach.circle import DEFAULT_ASK

    reg = _region(region) or {}
    q = " ".join(str(text or "").split()) or DEFAULT_ASK
    session._record("question", {"kind": "circle", "text": q[:300],
                                 "size": [round(float(reg.get("w") or 0)), round(float(reg.get("h") or 0))]}, step)
    gen = session.step_gen
    if step is not None:
        await session._status("thinking", detail="Looking at that")

    def moved() -> bool:
        return step is not None and gen != session.step_gen

    deadline = (time.monotonic() if release_t is None else float(release_t)) + ASK_DEADLINE_S
    res, pre = await _stream(session, step, q, reg, ask_id, app_capture, release_t, moved, deadline)
    if res is not None and (res.error == "moved_on" or moved()):
        await moved_on(session, reg, ask_id)  # deltas and answer.done pass the step-gen guard: say so with a card
        return
    err = str(res.error or "") if res is not None else ""
    if res is not None and res.ok:
        out: dict = {"kind": "answer", "title": res.title, "body": res.text, "marks": []}  # the mark went out already
    elif res is not None and res.deltas > 0:
        out = failed_card(step, reg, ask_id)  # words showed, then it broke: no second answer underneath
    elif err == "refusal":  # a second paid call on the same picture would most likely refuse again
        out = failed_card(step, reg, ask_id)
    elif err.startswith("cloud:"):  # paused / quota / auth: the one-shot call would be turned away the same way
        out = failed_card(step, reg, ask_id, cloud_card(step, err[len("cloud:"):]))
    elif pre is None and deadline - time.monotonic() < MIN_FALLBACK_S:
        log.info("circle ask: no time left for the one-shot answer (%s)", err or "none")
        out = failed_card(step, reg, ask_id)
    else:
        if pre is not None:  # the fast path already captured this frame
            obs, image, reason = pre.obs, pre.image, pre.reason
        else:
            obs, image, reason = await capture(session, _display_id(reg), reg,
                                               timeout=min(CAPTURE_S, deadline - time.monotonic() - MIN_ONESHOT_S))
        left = deadline - time.monotonic()
        if reason is not None:
            out = unseen_answer(step, reason, reg, ask_id)
            log.info("circle ask: can't see the screen (%s)", reason)
        elif left < MIN_ONESHOT_S:
            log.info("circle ask: no time left for the one-shot answer (%.1f s)", left)
            out = failed_card(step, reg, ask_id)
        else:
            try:
                out = await asyncio.wait_for(
                    session.m.circle_ask(step, q, reg, obs=obs, image=image, context=_context(session, step),
                                         ask_id=ask_id), left)
            except asyncio.TimeoutError:  # past the ask's deadline: the app is about to give up on it
                log.info("circle ask: the one-shot answer ran past the deadline")
                out = failed_card(step, reg, ask_id)
            except Exception as e:  # noqa: BLE001 - a missing / failing coach: the text read, never "Couldn't reach"
                log.warning("circle ask: coach failed (%s); answering from the text read", type(e).__name__)
                out = offline_answer(step, q, reg, obs, None, None, ask_id)
        image = None  # the picture is done with: nothing holds it while the card goes out
    pre = None
    out = {k: v for k, v in dict(out).items() if not str(k).startswith("_")}
    marks = [m for m in (out.pop("marks", None) or []) if isinstance(m, dict)]
    if moved():
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
