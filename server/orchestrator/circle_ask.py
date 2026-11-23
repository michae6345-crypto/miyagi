"""Circle to ask (Nov 22): the learner held Fn+Control, circled part of the screen and (maybe) said something.

The app sends the existing ask command with the circle's bounding box:
    action {kind: "ask", text: <spoken words or "What is this?">, region: ScreenRegion, source: "circle", askId}
main.py passes region / askId / source to LessonSession.action, whose _action hands an ask with a region here. It runs
inside action(), so proactive cards wait while the question is answered (ASK_KINDS), with or without a lesson.

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

Fast path (Nov 22, server/coach/fast_ask.py, tried first): an ask that carries capture (AskCapture) uses the app's
own JPEG (shared/capture_file.take_capture) and skips step 1. The answer streams as answer.delta, the buddy's mark
goes out as soon as the model's [DRAW] line is read, then the same card. Any failure: steps 2 and 3 as above (a
failure after FALLBACK_MODEL_WITHIN_S: the text read, no second call). Stage timings: AskTimer (ask.metrics).

The crop and the screen text are never logged or stored (the session record keeps the question and the region's size).

Every circle ask gets one card with its askId, so the app's pending ink never waits for its own timeout: the answer,
"I can't see your screen", a failure card (LessonSession.action stamps askId + region on it), or, when the learner
changed step while it was answered, a short "moved on" card. Only an ask whose lesson ended meanwhile gets no card
(the engine drops every answer of an ended lesson): the app's pending-circle timeout covers that one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

log = logging.getLogger("orchestrator.circle_ask")

CAPTURE_S = 3.0  # one capture + OCR is ~0.3-0.5 s; never hold the learner's answer longer than this
LAST_FRAME_S = 5.0  # a failed capture may still use the last frame's text when it is at most this old
HOLD_MS = 6000  # how long the buddy's circle stays (the app also fades it on a click there or a step change)
# The contract's promise (Action ask + region): every circle ask is answered within about this many seconds. Worst
# case: the capture (CAPTURE_S) + connection retries (llm.RETRY_BUDGET_S) + the last try's timeout (circle.TIMEOUT_S).
ANSWER_WITHIN_S = 25.0
# The streamed answer (server/coach/fast_ask.py) failing later than this (a timeout, a dropped link): the card is the
# text read, with no second model call, so the ask still ends within about ANSWER_WITHIN_S. An earlier failure (no
# key, a refusal, an HTTP error at once) answers through the non-streaming call as before.
FALLBACK_MODEL_WITHIN_S = 5.0
OCR_CONTEXT_S = 10.0  # with the app's own capture, the last frame's OCR boxes are context when at most this old
METRICS_FILE = "ask-metrics.jsonl"
EMPTY_OBS = {"blocks": [], "windows": [], "scale": 2.0, "screen": None, "app": ""}


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
                  region: dict | None = None) -> tuple[Any, Any, str | None]:
    """-> (observation, picture, None) or (None, None, reason). `display_id`: the display the learner circled on
    (ScreenRegion.displayId); `region`: the circle, so a display id that is not active still reads the display that
    holds it. Never raises.

    It always tries a fresh capture: the reader's error state (down_reason) may be left over from a stall, a sleep or
    a permission granted since, and the learner asked now. down_reason only picks the words when nothing was seen."""
    if getattr(session, "screen", None) is None:
        return None, None, "no_screen"
    grab = getattr(session.screen, "ask_frame", None)
    if grab is None:
        return None, None, "no_screen"
    box = {k: region[k] for k in ("x", "y", "w", "h") if k in region} if isinstance(region, dict) else None
    try:
        obs, image = await asyncio.wait_for(asyncio.to_thread(grab, display_id, box or None), CAPTURE_S)
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


class AskTimer:
    """Stage timings of one circle ask, seconds from the moment the handler got it. No content: no words, no text,
    no picture, no path. Logged as one `ask.metrics {json}` line and appended to <state dir>/ask-metrics.jsonl (the
    build-metrics file's rolling writer). Marks: received (0), picture (the app's capture read, or a frame taken),
    first_byte (the model's response headers), first_text, mark (annotate sent), first_delta (the first answer.delta
    sent), done, card. Flags: warmAgoS (since the last ask.warm warm-up), capture, picture, model, draw, route,
    fallback."""

    def __init__(self, clock: Any = time.monotonic) -> None:
        self.clock, self.t0 = clock, clock()
        self.marks: dict[str, float] = {"received": 0.0}
        self.flags: dict[str, Any] = {}
        self.closed = False

    def elapsed(self) -> float:
        return self.clock() - self.t0

    def mark(self, name: str) -> None:
        if name not in self.marks:
            self.marks[name] = round(max(0.0, self.elapsed()), 3)

    def flag(self, key: str, value: Any) -> None:
        self.flags[key] = value

    def summary(self, outcome: str) -> dict:
        return {"v": 1, "at": round(time.time(), 3), "outcome": outcome, "marks": dict(self.marks), **self.flags}

    def finish(self, outcome: str) -> dict | None:
        if self.closed:
            return None
        self.closed = True
        try:
            line = self.summary(outcome)
            text = json.dumps(line, separators=(",", ":"), ensure_ascii=False, default=str)
            log.info("ask.metrics %s", text)
            from .build_metrics import BuildMetrics

            BuildMetrics(path=_metrics_path)._append(text)
            return line
        except Exception:  # noqa: BLE001 - metrics never break an ask
            log.debug("ask metrics failed", exc_info=True)
            return None


def _metrics_path() -> Any:
    from server.sessions import store

    return store.state_dir() / METRICS_FILE


def _recent_obs(session: Any) -> Any:
    """The last frame's OCR, for the boxes inside the circle when the app sent its own capture (no new capture)."""
    last = getattr(session, "last_obs", None)
    t = float(getattr(last, "t", 0) or 0) if last is not None else 0.0
    if last is not None and t and time.time() - t <= OCR_CONTEXT_S and _real(last, session):
        return last
    return None


def _take(capture_payload: Any) -> Any:
    try:
        from shared.capture_file import take_capture

        return take_capture(capture_payload)
    except Exception:  # noqa: BLE001 - a bad capture is never worse than no capture
        return None


def _warm_ago() -> float | None:
    try:
        from server.coach import fast_ask

        at = fast_ask.last_warm_at
        return None if at is None else round(time.monotonic() - at, 2)
    except Exception:  # noqa: BLE001
        return None


def _stream_fn(session: Any) -> Any:
    """The coach's streamed answer, or None (MIYAGI_FAST_ASK=0, the coach stubbed or missing)."""
    if os.environ.get("MIYAGI_FAST_ASK", "1").strip() == "0":
        return None
    get = getattr(getattr(session, "m", None), "circle_stream_fn", None)
    try:
        return get() if callable(get) else None
    except Exception:  # noqa: BLE001
        return None


async def answer(session: Any, step: dict | None, text: str | None, region: Any, ask_id: str | None = None, *,
                 ask_capture: Any = None) -> None:
    """Action ask with a region (from LessonSession._action): one answer card next to the circle, maybe a mark.

    Fast path (Nov 22): the app's own capture when the ask carried one (ask_capture: no frame grab here), the answer
    streamed as answer.delta, and the buddy's mark sent as soon as the model's [DRAW] line is read
    (server/coach/fast_ask.py). Any failure there: today's non-streaming answer (session.m.circle_ask), and no second
    mark when one was already drawn."""
    from server.coach.circle import DEFAULT_ASK

    timer = AskTimer()
    if (ago := _warm_ago()) is not None:
        timer.flag("warmAgoS", ago)
    reg = _region(region) or {}
    raw = " ".join(str(text or "").split())
    q = raw or DEFAULT_ASK
    session._record("question", {"kind": "circle", "text": q[:300],
                                 "size": [round(float(reg.get("w") or 0)), round(float(reg.get("h") or 0))]}, step)
    gen = session.step_gen
    if step is not None:
        await session._status("thinking", detail="Looking at that")
    cap = await asyncio.to_thread(_take, ask_capture) if ask_capture is not None else None
    if ask_capture is not None:
        timer.flag("capture", "ok" if cap is not None else "refused")
    if cap is not None:  # the app captured the circle already: no frame grab, the last frame's OCR as context
        obs, image, reason = _recent_obs(session), None, None
    else:  # no capture, or one that failed a check: capture as before
        obs, image, reason = await capture(session, _display_id(reg), reg)
    timer.mark("picture")
    if reason is not None:
        log.info("circle ask: can't see the screen (%s)", reason)
        timer.flag("route", "unseen")
        await _send(session, step, gen, unseen_answer(step, reason, reg, ask_id), reg, ask_id, timer)
        return

    def current() -> bool:
        return step is None or gen == session.step_gen

    async def on_delta(chunk: str, done: bool) -> None:
        if not ask_id or not current():
            return  # no askId: nothing to match it to; moved on: the card says so instead
        payload: dict[str, Any] = {"askId": ask_id, "text": chunk}
        if done:
            payload["done"] = True
        await session.emit("answer.delta", payload)

    async def on_mark(marks: list[dict]) -> None:
        if current():
            await session.emit("annotate", {"marks": marks, "holdMs": HOLD_MS})
            timer.mark("mark")

    out, drew = None, False
    ctx = _context(session, step)
    if (stream := _stream_fn(session)) is not None:
        try:
            out = await stream(step, raw, reg, obs=obs, image=image, capture=cap, context=ctx, ask_id=ask_id,
                               on_delta=on_delta, on_mark=on_mark, timer=timer)
            timer.flag("route", "stream")
        except Exception as e:  # noqa: BLE001 - FastAskError or anything else: today's path answers
            drew = bool(getattr(e, "drew", False))
            kind = str(getattr(e, "kind", "") or type(e).__name__)
            timer.flag("fallback", kind)
            log.info("circle ask: streamed answer failed (%s); answering without streaming", kind)
            if kind in ("timeout", "connection", "api") and timer.elapsed() > FALLBACK_MODEL_WITHIN_S:
                out = offline_answer(step, q, reg, obs if obs is not None else EMPTY_OBS, None, ctx, ask_id)
                timer.flag("route", "reading")  # a slow failure: no second call (ANSWER_WITHIN_S)
    if out is None:
        timer.flag("route", "card")
        try:
            out = await session.m.circle_ask(step, q, reg, obs=obs if obs is not None else EMPTY_OBS, image=image,
                                             context=ctx, ask_id=ask_id, jpeg=cap.jpeg if cap is not None else None)
        except Exception as e:  # noqa: BLE001 - a missing / failing coach: the text read, never "Couldn't reach"
            log.warning("circle ask: coach failed (%s); answering from the text read", type(e).__name__)
            out = offline_answer(step, q, reg, obs if obs is not None else EMPTY_OBS, None, None, ask_id)
    cap = image = None  # the picture is done with: nothing holds it while the card goes out
    if drew:
        out = {**dict(out), "marks": []}  # the streamed mark is already drawn: never a second one
    await _send(session, step, gen, out, reg, ask_id, timer)


async def _send(session: Any, step: dict | None, gen: int, out: Any, reg: dict, ask_id: str | None,
                timer: AskTimer) -> None:
    """The answer card (askId, region, stepId stamped), then its mark; "moved on" when the step changed meanwhile."""
    out = {k: v for k, v in dict(out).items() if not str(k).startswith("_")}
    marks = [m for m in (out.pop("marks", None) or []) if isinstance(m, dict)]
    if step is not None and gen != session.step_gen:
        await moved_on(session, reg, ask_id)  # an answer about the old step would mislead; the ink still gets one
        timer.finish("moved_on")
        return
    if ask_id:
        out["askId"] = ask_id
    if reg:
        out["region"] = {k: reg[k] for k in ("x", "y", "w", "h", "displayId", "scale") if k in reg}
    if step is not None:
        out["stepId"] = step["id"]
    await session._emit_card(out, window_s=0.0)  # a second circle on the same spot is a new question
    timer.mark("card")
    if marks:
        await session.emit("annotate", {"marks": marks, "holdMs": HOLD_MS})
    timer.finish("ok")
    if step is not None:
        await session._status("offtrack" if session.last_offtrack else ("passed" if session.passed else "watching"))
