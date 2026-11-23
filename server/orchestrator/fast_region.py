"""Fast circle to ask (lane eng-fast-ask, Nov 22): the app's crop made safe to send, and the fallback capture + crop.

The normal path: the app's helper (miyagi-listen) captures the circled region while Fn+Control is still held and
the action ask carries it (capture: AskCapture); circle_ask.answer reads it with shared.capture_file.take_capture.
That crop is the raw screen, so it is never sent as is: from_capture() runs redact_capture() in a worker thread
(Vision OCR on the crop, every line through server/screen/privacy, every secret row blacked out and other projects'
VS Code windows greyed in its pixels, encoded again) and the redacted OCR text becomes the ask's screen text.

    safe = await fast_region.from_capture(session, cap)   # Prepared, or None: no OCR, a private app -> frame_for

frame_for() runs when that capture is missing or fails its checks (an older app, a helper without Screen
Recording), OCR is unavailable or failed, or a private app is under the circle: one frame of the circled display
is captured now
(circle_ask.capture: the same permission, fixture and last-frame rules as the ask itself), the region is cropped
from the frame's ScreenContext.pil() (secret rows and other projects' windows blacked out) and encoded to a JPEG
(fast_ask.crop_region). Memory only, never written to disk or logged (log lines carry timings and sizes).

    pre = await fast_region.frame_for(session, ask_id, reg)   # capture + crop now
    pre.reason / pre.obs / pre.image                   # what circle_ask.capture returned
    pre.crop -> (jpeg, rect_points, W, H) | None       # fast_ask.ask_stream's first four arguments
    pre.screen_text, pre.app                           # the circled OCR text and the frontmost app

There is no capture before release here (the ask.region command was dropped for the native capture): one capture
path while the keys are held (the helper), one fallback at release (this), never a pile of capture threads.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("orchestrator.fast_region")

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
            log.info("fast ask: no crop (%s)", type(e).__name__)
            crop = None
        if crop is not None:
            pre.jpeg, pre.rect, pre.w, pre.h = crop
    return pre


async def capture_and_crop(session: Any, region: Any, *, capture: Capture | None = None,
                           clock: Callable[[], float] = time.monotonic) -> Prepared | None:
    """Capture the region's display now and crop it. None when there is no capture to use (lane eng-circle-ask not
    merged) or the region is unreadable."""
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
        log.info("fast ask: no crop (%s)", type(e).__name__)
        pre = Prepared(region=reg, obs=obs, image=image, lesson_folder=folder)
    pre.captured_at = t0
    log.info("fast ask capture %s", json.dumps({"captureS": round(t1 - t0, 3), "cropS": round(clock() - t1, 3),
                                          "px": [pre.w, pre.h], "picture": pre.jpeg is not None,
                                          "reason": pre.reason}, separators=(",", ":")))  # sizes only
    return pre


async def frame_for(session: Any, ask_id: Any, region: Any, *,
                    clock: Callable[[], float] = time.monotonic) -> Prepared:
    """The action ask without a usable app capture: a capture + crop now. Always a Prepared: .reason set when there
    is no frame (circle_ask.capture's reason, "other_display", or "no_screen" without a capture here); .crop None
    when there is a frame but no picture to send (answer it the non-streaming way). ask_id: for the caller's logs."""
    reg = _region(region)
    if reg is None:
        return Prepared(region={}, reason="no_frame")
    try:
        pre = await capture_and_crop(session, reg, clock=clock)
    except Exception as e:  # noqa: BLE001 - the caller's own capture path still answers
        log.info("fast ask: capture failed (%s)", type(e).__name__)
        pre = None
    return pre if pre is not None else Prepared(region=reg, reason="no_screen")


# ---------------------------------------------------------------------------------------------------- the app's crop

OCR_TIMEOUT_S = 2.0  # Vision on a 1092 px crop is ~0.1-0.3 s; past this the ask captures at release instead
SECRET_PAD_PT = 2.0  # a secret row is blacked out this much past its OCR box (Vision's boxes can be tight)
PRIVATE_GRID = 6  # private-app check: the front window at a 6 x 6 grid of points across the crop

# tests: fakes, never Vision or the real window list. _ocr(jpeg, rect, scale) -> blocks {text, rect};
# _windows(rect) -> windows {app, title, rect}, front to back
_ocr: Callable[[bytes, tuple, float], list] | None = None
_windows: Callable[[tuple], list] | None = None


def _mac_ocr(jpeg: bytes, rect: tuple, scale: float) -> list:
    from server.screen import macos
    from server.screen.types import Rect

    blocks, _ms = macos.ocr_image(macos.cgimage_from_bytes(jpeg), Rect(*rect), scale)
    return blocks


def _mac_windows(rect: tuple) -> list:
    from server.screen import macos
    from server.screen.types import Rect

    return [w for w in macos.list_windows(Rect(*rect)) if w.app not in macos._OVERLAY_OWNERS]


def _box(r: Any) -> tuple[float, float, float, float] | None:
    vals = tuple(_num(_get(r, k)) for k in ("x", "y", "w", "h")) if r is not None else ()
    if len(vals) != 4 or None in vals or vals[2] <= 0 or vals[3] <= 0:  # type: ignore[operator]
        return None
    return vals  # type: ignore[return-value]


def _front_at(windows: list, x: float, y: float) -> Any:
    for w in windows:  # front to back
        r = _box(_get(w, "rect"))
        if r is not None and r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]:
            return w
    return None


def redact_capture(cap: Any, lesson_folder: str = "") -> Prepared | None:
    """The app's crop (shared.capture_file.Capture) made as safe to send as frame_for's crop (blocking: Vision and
    PIL; run it in a thread). Vision reads the crop (server/screen/macos.ocr_image, screen = cap.rect, scale =
    cap.w / rect.w), every line goes through server/screen/privacy.redact, and in the crop's pixels every line that
    held a secret (privacy.holds_secret) is blacked out and every other project's VS Code window greyed out
    (ScreenContext.pil(), as for the screen reader's frames); then the crop is encoded again. Nothing to hide: the
    helper's bytes as they are.

    -> Prepared (the crop, the redacted OCR text as screen_text, the app under the circle), or None: a private app
    (privacy.is_private_app: a password manager, Messages) is in front somewhere in the crop or owns a line in it.
    None (or a raise: no Vision, a bad picture) means: capture at release instead (frame_for), whose frame leaves
    those out."""
    from server.coach import fast_ask
    from server.coach.screen import ScreenContext
    from server.screen.privacy import holds_secret, is_private_app, redact

    rect = tuple(float(v) for v in cap.rect)
    w, h = int(cap.w), int(cap.h)
    scale = w / rect[2] if rect[2] > 0 else 0.0
    if not math.isfinite(scale) or scale <= 0:
        return None
    blocks = (_ocr or _mac_ocr)(cap.jpeg, rect, scale)
    windows = list((_windows or _mac_windows)(rect))
    for i in range(PRIVATE_GRID):  # the window in front at each point: is any part of the crop a private app?
        for j in range(PRIVATE_GRID):
            px = rect[0] + rect[2] * (i + 0.5) / PRIVATE_GRID
            py = rect[1] + rect[3] * (j + 0.5) / PRIVATE_GRID
            if (win := _front_at(windows, px, py)) is not None and is_private_app(str(_get(win, "app", "") or "")):
                return None
    lines, secret = [], []
    for b in blocks or []:
        r = _box(_get(b, "rect"))
        text = str(_get(b, "text", "") or "")
        if r is None or not text.strip():
            continue
        owner = _front_at(windows, r[0] + r[2] / 2, r[1] + r[3] / 2)
        app = str(_get(owner, "app", "") or "") if owner is not None else ""
        if is_private_app(app):
            return None
        text = redact(text)
        if holds_secret(text):
            secret.append(r)
        lines.append({"text": text, "rect": {"x": r[0], "y": r[1], "w": r[2], "h": r[3]}, "app": app or None,
                      "window": str(_get(owner, "title", "") or "") if owner is not None else None})
    centre = (rect[0] + rect[2] / 2, rect[1] + rect[3] / 2)
    front = _front_at(windows, *centre)
    app = str(_get(front, "app", "") or "") if front is not None else ""
    wins = []
    for x in windows:
        if (r := _box(_get(x, "rect"))) is not None:
            wins.append({"app": str(_get(x, "app", "") or ""), "title": str(_get(x, "title", "") or ""),
                         "rect": {"x": r[0], "y": r[1], "w": r[2], "h": r[3]}})
    obs = {"blocks": lines, "windows": wins, "screen": {"x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3]},
           "scale": scale, "app": app}
    sc = ScreenContext.from_observation(obs, cap.jpeg, cursor=centre,
                                        **({"lesson_folder": lesson_folder} if lesson_folder else {}))
    jpeg = cap.jpeg
    if secret or sc._layers:  # something to hide: black it out in the crop's own pixels, then encode again
        from PIL import ImageDraw

        img = sc.pil()  # secret rows black, other projects' windows grey
        draw = ImageDraw.Draw(img)
        for x, y, rw, rh in secret:
            (x0, y0) = sc.to_px(x - SECRET_PAD_PT, y - SECRET_PAD_PT)
            (x1, y1) = sc.to_px(x + rw + SECRET_PAD_PT, y + rh + SECRET_PAD_PT)
            draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))
        jpeg, w, h = fast_ask.encode_crop(img)
        del img
    try:
        from server.coach.circle import region_text

        screen_text = region_text(sc)
    except ImportError:  # pragma: no cover - lane eng-circle-ask not merged
        screen_text = "\n".join(b.text for b in sc.boxes)
    box = {"x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3]}
    return Prepared(region=dict(box), jpeg=jpeg, rect=box, w=w, h=h, screen_text=screen_text, app=app or sc.app,
                    lesson_folder=lesson_folder)


async def from_capture(session: Any, cap: Any, *, timeout: float = OCR_TIMEOUT_S) -> Prepared | None:
    """redact_capture off the event loop, bounded by `timeout`. None (the log line names only the error's type):
    capture at release instead. Never raises."""
    t0 = time.monotonic()
    try:
        pre = await asyncio.wait_for(asyncio.to_thread(redact_capture, cap, _lesson_folder(session)), timeout)
    except Exception as e:  # noqa: BLE001 - no Vision, a timeout, a bad picture: the release capture still answers
        log.info("fast ask: the app's crop was not read (%s); capturing at release", type(e).__name__)
        return None
    log.info("fast ask redact %s", json.dumps({"s": round(time.monotonic() - t0, 3), "used": pre is not None,
                                               "px": [pre.w, pre.h] if pre else None}, separators=(",", ":")))
    return pre


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
