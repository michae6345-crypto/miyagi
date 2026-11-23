"""Fast circle to ask (lane eng-fast-ask, Nov 22): the circled region is captured, cropped and encoded BEFORE release.

The app sends `ask.region {askId, region}` when the ink closes (each pointer-up while Fn+Control is still held).
main.py answers it beside the command queue (INSTANT) with remember_soon(): one frame of that display is captured
now (circle_ask.capture: the same permission, fixture and last-frame rules as the ask itself), the region is cropped
from the frame's ScreenContext (secret rows blacked out) and encoded to a JPEG (fast_ask.crop_region), and the result
waits in an in-memory slot keyed by askId. The action ask with that askId takes it (take()), so the release only
costs the words: no capture + OCR (0.3 to 0.5 s, up to CAPTURE_S 3 s) after the keys come up.

The slot: memory only, never written to disk or logged (log lines carry timings and sizes). It is dropped when taken,
when a newer ask.region with the same askId replaces it, after SLOT_TTL_S, or when more than MAX_SLOTS wait. It keeps
the frame (obs + picture) too, so a region that moved a little at release is cropped again from the same frame
without a new capture, and the non-streaming path (session.m.circle_ask) gets the same frame.

    pre = await fast_region.frame_for(session, ask_id, reg)   # the slot, else capture + crop now
    pre.reason / pre.obs / pre.image                   # what circle_ask.capture returned
    pre.crop -> (jpeg, rect_points, W, H) | None       # fast_ask.ask_stream's first four arguments
    pre.screen_text, pre.app                           # the circled OCR text and the frontmost app

This module needs circle_ask.capture and coach/circle.py (lane eng-circle-ask) for the capture; without them
remember_soon() does nothing and the ask captures on release as before.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("orchestrator.fast_region")

SLOT_TTL_S = 10.0  # a slot nobody asks with is dropped after this long
MAX_SLOTS = 2  # one hold at a time; a second only while the first is being answered
WAIT_S = 3.0  # take() waits at most this long for a capture still running (circle_ask.CAPTURE_S)
REGION_SLOP_PT = 2.0  # the ask's region may differ this much from ask.region's and still use its crop as is

Capture = Callable[[Any, "int | None", "dict | None"], Awaitable[tuple[Any, Any, "str | None"]]]  # circle_ask.capture


@dataclass
class Prepared:
    """One circled region, captured and cropped. reason: circle_ask.capture's (no_permission | no_screen | no_frame
    | ...) or "other_display" (the region is off the captured display); None when the frame is there."""

    region: dict
    obs: Any = None
    image: Any = None
    reason: str | None = None
    jpeg: bytes | None = None
    rect: dict | None = None
    w: int = 0
    h: int = 0
    screen_text: str = ""
    app: str = ""
    lesson_folder: str = ""
    captured_at: float = 0.0

    @property
    def crop(self) -> tuple[bytes, dict, int, int] | None:
        """(jpeg, rect_points, W, H) for fast_ask.ask_stream, or None (no picture: use the non-streaming path)."""
        if self.jpeg is None or self.rect is None:
            return None
        return self.jpeg, self.rect, self.w, self.h


_capture: Capture | None = None  # tests: a fake capture; None: circle_ask.capture
_slots: OrderedDict[str, tuple[float, asyncio.Task]] = OrderedDict()


def _capture_fn() -> Capture | None:
    if _capture is not None:
        return _capture
    try:
        from .circle_ask import capture
    except ImportError:  # lane eng-circle-ask not merged yet
        return None
    return capture


def _get(o: Any, k: str, default: Any = None) -> Any:
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _region(region: Any) -> dict | None:
    """The ScreenRegion as a dict with finite x, y, w > 0, h > 0, or None."""
    if hasattr(region, "model_dump"):
        region = region.model_dump()
    if not isinstance(region, dict):
        return None
    x, y, w, h = (_num(region.get(k)) for k in ("x", "y", "w", "h"))
    if None in (x, y, w, h) or w <= 0 or h <= 0:  # type: ignore[operator]
        return None
    return dict(region)


def _display_id(region: dict | None) -> int | None:
    did = (region or {}).get("displayId")
    if isinstance(did, bool) or not isinstance(did, (int, float)):
        return None
    return int(did) if float(did).is_integer() else None


def _same(a: dict, b: dict) -> bool:
    if _display_id(a) != _display_id(b):
        return False
    return all(abs(float(a[k]) - float(b[k])) <= REGION_SLOP_PT for k in ("x", "y", "w", "h"))


def _lesson_folder(session: Any) -> str:
    """The lesson's folder while a step runs (other projects' VS Code windows are greyed out), as circle_ask does."""
    if getattr(session, "step", None) is None:
        return ""
    return str(getattr(session, "workdir", "") or "")


def _clip_alone(region: dict, screen: Any) -> dict | None:
    """Without coach/circle.py: the region cut to the captured display (None when it lies wholly outside)."""
    x, y, w, h = (float(region[k]) for k in ("x", "y", "w", "h"))
    if screen is None:
        return {"x": x, "y": y, "w": w, "h": h}
    try:
        sx, sy = float(_get(screen, "x")), float(_get(screen, "y"))
        sw, sh = float(_get(screen, "w", _get(screen, "width"))), float(_get(screen, "h", _get(screen, "height")))
    except (TypeError, ValueError):
        return {"x": x, "y": y, "w": w, "h": h}
    x0, y0, x1, y1 = max(x, sx), max(y, sy), min(x + w, sx + sw), min(y + h, sy + sh)
    if x1 <= x0 or y1 <= y0:
        return None
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def prepare(obs: Any, image: Any, region: dict, lesson_folder: str = "") -> Prepared:
    """One frame + the circled region -> Prepared (blocking: PIL; run it in a thread). The crop comes from the
    frame's ScreenContext.pil(), so every secret row of the frame and other projects' windows are blacked out."""
    from server.coach import fast_ask

    pre = Prepared(region=dict(region), obs=obs, image=image, lesson_folder=lesson_folder)
    try:
        from server.coach import circle
    except ImportError:  # lane eng-circle-ask not merged: the whole frame's context, no circled text
        circle = None
    if circle is not None:
        clip = circle.clamp_region(region, _get(obs, "screen"))
        if clip is None:
            pre.reason = "other_display"
            return pre
        sc = circle.screen_for(obs, image, clip, {"lesson_folder": lesson_folder})
        pre.screen_text = circle.region_text(sc)
    else:
        from server.coach.screen import ScreenContext

        clip = _clip_alone(region, _get(obs, "screen"))
        if clip is None:
            pre.reason = "other_display"
            return pre
        centre = (clip["x"] + clip["w"] / 2, clip["y"] + clip["h"] / 2)
        extra = {"lesson_folder": lesson_folder} if lesson_folder else {}
        sc = ScreenContext.from_observation(obs, image, cursor=centre, **extra)
    pre.app = str(getattr(sc, "app", "") or "")
    if image is not None:
        try:
            crop = fast_ask.crop_region(sc, clip)
        except Exception as e:  # noqa: BLE001 - no picture: the non-streaming path still answers from the text
            log.info("ask.region: no crop (%s)", type(e).__name__)
            crop = None
        if crop is not None:
            pre.jpeg, pre.rect, pre.w, pre.h = crop
    return pre


async def capture_and_crop(session: Any, region: Any, *, capture: Capture | None = None,
                           clock: Callable[[], float] = time.monotonic) -> Prepared | None:
    """Capture the region's display now and crop it (what ask.region does ahead of time; also the path when no slot
    is waiting). None when there is no capture to use (lane eng-circle-ask not merged) or the region is unreadable."""
    reg = _region(region)
    cap = capture or _capture_fn()
    if reg is None or cap is None:
        return None
    t0 = clock()
    obs, image, reason = await cap(session, _display_id(reg), reg)
    t1 = clock()
    if reason is not None:
        return Prepared(region=reg, reason=reason, captured_at=t0)
    folder = _lesson_folder(session)
    try:
        pre = await asyncio.to_thread(prepare, obs, image, reg, folder)
    except Exception as e:  # noqa: BLE001 - the frame is still good for the non-streaming path
        log.info("ask.region: no crop (%s)", type(e).__name__)
        pre = Prepared(region=reg, obs=obs, image=image, lesson_folder=folder)
    pre.captured_at = t0
    log.info("ask.region %s", json.dumps({"captureS": round(t1 - t0, 3), "cropS": round(clock() - t1, 3),
                                          "px": [pre.w, pre.h], "picture": pre.jpeg is not None,
                                          "reason": pre.reason}, separators=(",", ":")))  # sizes only
    return pre


def remember_soon(session: Any, ask_id: Any, region: Any, *,
                  clock: Callable[[], float] = time.monotonic) -> asyncio.Task | None:
    """ask.region: start capture + crop + encode now, into the slot for ask_id (a newer one replaces it). Returns at
    once (the task), never raises. None: nothing to do (no askId, a bad region, no capture, no running loop)."""
    reg = _region(region)
    cap = _capture_fn()
    if not ask_id or not isinstance(ask_id, str) or reg is None or cap is None:
        if cap is None:
            log.info("ask.region: no capture here (lane eng-circle-ask); the ask captures on release")
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    drop(ask_id)
    task = loop.create_task(capture_and_crop(session, reg, capture=cap, clock=clock))
    task.add_done_callback(_quiet)
    _slots[ask_id] = (clock(), task)
    while len(_slots) > MAX_SLOTS:
        _, (_, old) = _slots.popitem(last=False)
        old.cancel()
    loop.call_later(SLOT_TTL_S, _expire, ask_id, task)
    return task


def _quiet(task: asyncio.Task) -> None:
    """A failed capture is logged (its type only), never raised into the loop."""
    if not task.cancelled() and task.exception() is not None:
        log.info("ask.region: capture failed (%s)", type(task.exception()).__name__)


def _expire(ask_id: str, task: asyncio.Task) -> None:
    entry = _slots.get(ask_id)
    if entry is not None and entry[1] is task:
        _slots.pop(ask_id, None)
        task.cancel()


def drop(ask_id: str) -> None:
    """Forget the slot for ask_id (its capture is cancelled when it still runs)."""
    entry = _slots.pop(ask_id, None)
    if entry is not None:
        entry[1].cancel()


def clear() -> None:
    """Forget every slot (tests, lesson.ended)."""
    for ask_id in list(_slots):
        drop(ask_id)


async def take(ask_id: Any, region: Any, *, clock: Callable[[], float] = time.monotonic) -> Prepared | None:
    """The action ask: the slot ask.region filled for ask_id (dropped from the slot now), waiting at most WAIT_S
    for a capture still running. A region that moved a little is cropped again from the same frame; one on another
    display, an expired slot, a failed capture: None (the caller captures now, as before)."""
    if not isinstance(ask_id, str) or not ask_id:
        return None
    entry = _slots.pop(ask_id, None)
    reg = _region(region)
    if entry is None or reg is None:
        if entry is not None:
            entry[1].cancel()
        return None
    at, task = entry
    if clock() - at > SLOT_TTL_S:
        task.cancel()
        return None
    try:
        pre = await asyncio.wait_for(asyncio.shield(task), WAIT_S)
    except Exception:  # noqa: BLE001 - a timeout or a failed capture: capture again on release
        task.cancel()
        return None
    if pre is None or _same(pre.region, reg):
        return pre
    if _display_id(pre.region) != _display_id(reg) or pre.obs is None:
        return None
    again = await asyncio.to_thread(prepare, pre.obs, pre.image, reg, pre.lesson_folder)
    again.captured_at = pre.captured_at
    return again


async def frame_for(session: Any, ask_id: Any, region: Any, *,
                    clock: Callable[[], float] = time.monotonic) -> Prepared:
    """The action ask's one call: the slot ask.region filled (take), else a capture + crop now. Always a Prepared:
    .reason set when there is no frame (circle_ask.capture's reason, "other_display", or "no_screen" without a
    capture here); .crop None when there is a frame but no picture to send (answer it the non-streaming way)."""
    reg = _region(region)
    if reg is None:
        return Prepared(region={}, reason="no_frame")
    pre = await take(ask_id, reg, clock=clock)
    if pre is not None:
        return pre
    try:
        pre = await capture_and_crop(session, reg, clock=clock)
    except Exception as e:  # noqa: BLE001 - the caller's own capture path still answers
        log.info("fast ask: capture failed (%s)", type(e).__name__)
        pre = None
    return pre if pre is not None else Prepared(region=reg, reason="no_screen")


def lesson_context(session: Any, step: dict | None, screen_text: str = "", app: str = "") -> dict:
    """fast_ask.ask_stream's lesson_context as plain strings: {lesson, step, memory, screen_text, app}."""
    ctx: dict[str, Any] = {"screen_text": screen_text or "", "app": app or ""}
    lesson = (getattr(session, "graph", None) or {}).get("lesson") or {}
    if isinstance(lesson, dict) and (about := " ".join(str(lesson.get(k) or "") for k in ("title", "goal")).strip()):
        ctx["lesson"] = about
    if step is not None:
        ctx["step"] = "\n".join(str(step[k]) for k in ("title", "instructions") if step.get(k))
        if hasattr(session, "_memory_kw"):
            try:
                ctx["memory"] = session._memory_kw(step, "explain").get("memory", "")
            except Exception:  # noqa: BLE001 - memory never costs the answer
                log.exception("fast ask: memory block failed")
    return ctx
