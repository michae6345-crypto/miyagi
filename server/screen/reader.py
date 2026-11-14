"""ScreenReader: the capture loop + OCR + the public API the other engine modules use."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import match as M
from .describe import DescribeError, Describer, to_jpeg
from .metrics import TerminalMetricReader, TigerWriter
from .privacy import is_private_app, redact
from .types import Block, Rect, ScreenObservation, ScreenPermissionError, Window

log = logging.getLogger("server.screen")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
Callback = Callable[[ScreenObservation], object]


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.environ.get("TUT_ENV", "/Users/tripi/sand hacks/sandhacks-tutor/.env"), override=False)
    except Exception:  # noqa: BLE001, S110  (env is optional)
        pass


class ScreenReader:
    """Watches the primary display. Thread-safe; one per engine process (see `get_reader()`).

    interval: seconds between captures. A frame is OCR'd only when it changed (downscaled
    gray-thumbnail diff, overlay masked out), or the window layout changed, or `max_age` passed.
    """

    def __init__(self, interval: float = 2.0, max_age: float = 15.0, diff_pixels: int = 3,
                 fixture: str | None = None, debounce: float = 1.5, heartbeat_with_events: float = 5.0,
                 use_ax: bool = True, use_events: bool = True):
        _load_env()
        self.interval = interval
        self.debounce = debounce
        self.heartbeat_with_events = heartbeat_with_events
        self.use_ax = use_ax and os.environ.get("TUT_AX", "1") != "0"
        self.use_events = use_events and os.environ.get("TUT_EVENTS", "1") != "0"
        self.use_sck = os.environ.get("TUT_CAPTURE", "sck") != "cg"
        self.ax_reader = None       # server.screen.ax.AXReader once started (None: AX unavailable)
        self.events = None          # server.screen.events.EventTriggers once started
        self._sck = None
        self._sck_failed = False
        self._pending_reason = "tick"
        self._force_next = False
        self._last_capture = 0.0
        self.max_age = max_age
        self.diff_pixels = diff_pixels
        # Fixtures are used ONLY when asked for explicitly (arg / TUT_SCREEN_FIXTURE), or under
        # DEMO=1 as a fallback when capture is impossible. Never silently otherwise.
        self.fixture = fixture or os.environ.get("TUT_SCREEN_FIXTURE") or None
        self.demo = os.environ.get("DEMO", "") not in ("", "0", "false", "False")
        self.last_error: str | None = None   # why the last capture failed (None = healthy)
        self._error_cbs: list[Callable[[Exception | None], object]] = []
        self.ocr_ms_history: list[float] = []
        self._latest: ScreenObservation | None = None
        self._latest_image = None
        self._prev_thumb: bytes | None = None
        self._prev_layout: tuple = ()
        self._overlay: list[Rect] = []
        self._subs: list[tuple[Callback, asyncio.AbstractEventLoop | None]] = []
        self._metric_readers: list[TerminalMetricReader] = []
        self._tiger: TigerWriter | None = None
        self._describer = Describer()
        self._lock = threading.RLock()
        self._capture_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._frame = 0
        self._permission_warned = False

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> ScreenReader:
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        if sys.platform == "darwin" and not self.fixture:
            self._start_sensors()
        self.poke("start", force=True)
        self._last_capture = 0.0
        self._thread = threading.Thread(target=self._run, name="screen-reader", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.ax_reader:
            self.ax_reader.stop()
        if self.events:
            self.events.stop()

    def _start_sensors(self) -> None:
        """AX worker (10 Hz) + event-tap triggers. Each degrades to nothing without permission."""
        if self.use_ax and self.ax_reader is None:
            try:
                from .ax import AXReader
                self.ax_reader = AXReader().start()
                if self.ax_reader.available:
                    self.ax_reader.on_change(self._on_ax_change)
            except Exception as e:  # noqa: BLE001
                log.warning("AX reader unavailable: %s", e)
        if self.use_events and self.events is None:
            try:
                from .events import EventTriggers
                self.events = EventTriggers(lambda reason, info: self.poke(reason, force=False)).start()
            except Exception as e:  # noqa: BLE001
                log.warning("event triggers unavailable: %s", e)

    def _on_ax_change(self, snap, what: str) -> None:
        # text changes fire typing_pause later; caret moves are too chatty to capture on
        if what in ("app", "document", "dirty", "terminal", "typing_pause"):
            self.poke(what, force=False)

    def poke(self, reason: str = "manual", force: bool = True) -> None:
        """Capture now instead of waiting for the next tick (e.g. right after a run ended).
        force=True also re-OCRs an unchanged screen. Captures are debounced (>= `debounce` s apart)."""
        self._pending_reason = reason
        self._force_next = self._force_next or force
        self._wake.set()

    @property
    def heartbeat(self) -> float:
        """Seconds between captures when nothing triggers one."""
        return self.heartbeat_with_events if (self.events and self.events.available) else self.interval

    def _run(self) -> None:
        while not self._stop.is_set():
            woke = self._wake.wait(self.heartbeat)
            self._wake.clear()
            if self._stop.is_set():
                break
            wait = self.debounce - (time.time() - self._last_capture)
            if woke and wait > 0:
                self._stop.wait(wait)
                self._wake.clear()  # pokes during the debounce window are coalesced into this capture
            reason = self._pending_reason if woke else "tick"
            force, self._force_next, self._pending_reason = self._force_next, False, "tick"
            try:
                self.observe_now(force=force, trigger=reason)
            except Exception as e:
                if type(e).__name__ == "ScreenUnavailableError":  # asleep/locked/switching Spaces: expected
                    now = time.time()
                    if now - getattr(self, "_unavail_logged", 0.0) > 60:
                        self._unavail_logged = now
                        log.warning("screen unavailable: %s (retrying quietly)", e)
                elif not isinstance(e, ScreenPermissionError):
                    log.exception("screen capture/OCR failed")

    # ------------------------------------------------------------------ health / errors / keys

    @property
    def status(self) -> str:
        """ok | no_permission | error | fixture | idle (nothing captured yet)."""
        if self.last_error:
            return "no_permission" if self.last_error.startswith("no_permission") else "error"
        if self._latest is None:
            return "idle"
        return "fixture" if self._latest.source != "live" else "ok"

    def on_error(self, cb: Callable[[Exception | None], object]) -> Callable[[], None]:
        """cb(exc) when capture starts failing (e.g. ScreenPermissionError: tell the user what to
        grant), cb(None) when it recovers. Called on transitions only, from the reader thread."""
        self._error_cbs.append(cb)
        return lambda: self._error_cbs.remove(cb) if cb in self._error_cbs else None

    def _set_error(self, e: Exception | None) -> None:
        from . import macos
        msg = None if e is None else (
            f"no_permission: {macos.PERMISSION_HELP}" if isinstance(e, macos.ScreenPermissionError)
            else f"{e.__class__.__name__}: {e}")
        if msg == self.last_error:
            return
        self.last_error = msg
        if e is not None:
            log.error("screen reader: %s", msg)
        else:
            log.info("screen reader recovered")
        for cb in list(self._error_cbs):
            try:
                cb(e)
            except Exception:
                log.exception("on_error callback failed")

    def set_keys(self, anthropic: str | None = None, tiger_url: str | None = None, **_ignored) -> dict[str, str]:
        """BYOK from the app's `config.keys` ({anthropic, tigerUrl}; other keys are ignored here:
        the screen reader never uses Gemini). Empty/None = keep using .env.
        Returns the screen reader's part of `config.status`."""
        self._describer.set_key(anthropic)
        self._tiger_writer().set_url(tiger_url)
        return self.key_status()

    def key_status(self) -> dict[str, str]:
        """{"anthropic": KeyState, "tigerUrl": KeyState} (events.ts KeyState: ok|missing|invalid|env)."""
        return {"anthropic": self._describer.key_status, "tigerUrl": self._tiger_writer().status}

    def _tiger_writer(self) -> TigerWriter:
        if self._tiger is None:
            self._tiger = TigerWriter()
        return self._tiger

    # ------------------------------------------------------------------ public API

    def latest(self) -> ScreenObservation | None:
        with self._lock:
            return self._latest

    def subscribe(self, cb: Callback, loop: asyncio.AbstractEventLoop | None = None) -> Callable[[], None]:
        """Call `cb(obs)` on every new observation. Coroutine functions are scheduled on `loop`
        (defaults to the running loop at subscribe time). Returns an unsubscribe function."""
        if loop is None and inspect.iscoroutinefunction(cb):
            loop = asyncio.get_running_loop()
        entry = (cb, loop)
        with self._lock:
            self._subs.append(entry)

        def unsubscribe() -> None:
            with self._lock:
                if entry in self._subs:
                    self._subs.remove(entry)
        return unsubscribe

    def set_overlay_bounds(self, rects) -> None:
        """Rects (points, top-left) covered by our own overlay; OCR inside them is ignored."""
        with self._lock:
            self._overlay = [Rect.from_any(r) for r in (rects or [])]

    def locate(self, match: str, app: str | None = None) -> Rect | None:
        res = self.locate_match(match, app)
        return res.rect if res else None

    def locate_match(self, match: str, app: str | None = None) -> M.LocateResult | None:
        obs = self.latest() or self.observe_now(force=True)
        return M.locate_match(obs, match, app) if obs else None

    def contains(self, pattern: str, app: str | None = None) -> bool:
        obs = self.latest()
        return bool(obs) and M.screen_contains(obs, pattern, app)

    def watch_metrics(self, lesson_id: str, patterns: dict[str, str],
                      callback: Callable[[str, int, float], None] | None = None, app: str | None = None,
                      on_restart: Callable[[str], None] | None = None) -> TerminalMetricReader:
        """Start reading metrics off the screen for a lesson. Returns the reader (call `.reset()`
        on a step change; `unwatch_metrics(reader)` to stop)."""
        r = TerminalMetricReader(lesson_id, patterns, callback, app=app, tiger=self._tiger_writer(),
                                 on_restart=on_restart)
        with self._lock:
            self._metric_readers.append(r)
            obs = self._latest
        if obs:
            r.feed(obs)
        return r

    def unwatch_metrics(self, reader: TerminalMetricReader | None = None) -> None:
        with self._lock:
            if reader is None:
                self._metric_readers.clear()
            elif reader in self._metric_readers:
                self._metric_readers.remove(reader)

    async def _vision_input(self, region=None) -> tuple[bytes, str, ScreenObservation]:
        """JPEG (1280 wide, cursor ringed) + a text context (frontmost app, cursor, what's under it)."""
        try:
            img = await asyncio.to_thread(self.screenshot_pil, region)
        except Exception as e:
            raise DescribeError("no_image", str(e)[:200]) from e
        obs = self.latest()
        if img is None or obs is None:
            raise DescribeError("no_image", self.last_error or "nothing captured yet")
        live = obs.source == "live"  # a replayed screenshot has no meaningful cursor
        ctx = await asyncio.to_thread(self.cursor_context, obs) if live else {}
        origin = (obs.screen.x, obs.screen.y)
        if region is not None:
            r = Rect.from_any(region).clamp(obs.screen)
            origin = (r.x, r.y)
        jpeg = to_jpeg(img, cursor=(ctx["x"], ctx["y"]) if live else None, scale=obs.scale, origin=origin)
        lines = [f"Frontmost app: {obs.app}."]
        if live:
            lines.append(f"Cursor at ({ctx['x']:.0f}, {ctx['y']:.0f}) points, over app {ctx.get('app')!r}.")
        if ctx.get("editor_line"):
            lines.append(f"Cursor is on editor line {ctx['editor_line']}: {ctx.get('editor_line_text')!r}.")
        elif ctx.get("ocr_line"):
            lines.append(f"Text under the cursor: {ctx['ocr_line']!r}.")
        if ctx.get("ax"):
            a = ctx["ax"]
            lines.append(f"UI element under the cursor: role={a.get('role')} title={a.get('title')!r}.")
        if obs.ax and obs.ax.get("document"):
            lines.append(f"Open file: {obs.ax['document']} (unsaved changes: {obs.ax.get('dirty')}).")
        return jpeg, "\n".join(lines), obs

    async def describe(self, question: str, region=None) -> str:
        """Ask Claude (claude-opus-5-5) about the current screen, or a region of it in points.
        Rate-limited. Raises DescribeError (reason: missing_key | invalid_key | no_image | refused |
        unavailable). No other provider is ever used."""
        jpeg, context, obs = await self._vision_input(region)
        key = (question, Rect.from_any(region).rounded() if region else None, obs.frame)
        return await self._describer.describe(jpeg, question, context, key)

    async def where(self, target: str, app: str | None = None) -> M.LocateResult | None:
        """Quick visual "where is X" with Claude (claude-haiku-5-5), for targets text matching can't
        resolve ("the run button", "the cell with the loss plot"). Set-of-mark: Claude picks among the
        numbered OCR lines, so the rect is exact. Try `locate()` first: it's free and instant."""
        jpeg, context, obs = await self._vision_input()
        lines = [ln for ln in M.group_lines(obs.blocks_in(app)) if ln.text.strip()][:400]
        if not lines:
            return None
        ids = await self._describer.where(jpeg, target, [ln.text for ln in lines], context,
                                          (target, app, obs.frame))
        if not ids:
            return None
        best = lines[ids[0]]
        return M.LocateResult(best.rect.pad(6).clamp(obs.screen), best.app, best.text, 100.0, [best])

    # ------------------------------------------------------------------ capture + OCR

    def _grab(self):
        """-> (cgimage, screen_rect, scale, windows, fixture_app, source).

        Live capture, unless a fixture was asked for explicitly. Without Screen Recording
        permission this RAISES ScreenPermissionError (and reports it via last_error/on_error);
        it only substitutes a fixture under DEMO=1, and then marks the observation's source.
        """
        from . import macos
        if self.fixture:
            img, screen, scale, windows, app = load_fixture(self.fixture)
            return img, screen, scale, windows, app, f"fixture:{Path(self.fixture).name}", False
        try:
            if not macos.has_permission():
                raise macos.ScreenPermissionError(macos.PERMISSION_HELP)
            sck = self._sck_capture()
            if sck is not None:
                img, screen, scale, excluded = sck
                windows = [w for w in macos.list_windows(screen) if w.app not in excluded]
                return img, screen, scale, windows, None, "live", True
            f = macos.capture_main_display()
        except macos.ScreenPermissionError:
            if not self._permission_warned:
                print(macos.PERMISSION_HELP, file=sys.stderr)
                self._permission_warned = True
            fixtures = sorted(FIXTURES_DIR.glob("*.png"))
            if self.demo and fixtures:
                log.warning("DEMO=1 and no Screen Recording permission: replaying %s", fixtures[0].name)
                img, screen, scale, windows, app = load_fixture(str(fixtures[0]))
                return img, screen, scale, windows, app, f"fixture:{fixtures[0].name}", False
            raise
        return f.image, f.screen, f.scale, macos.list_windows(f.screen), None, "live", False

    def _sck_capture(self):
        """ScreenCaptureKit with our overlay excluded; None -> use the CoreGraphics fallback."""
        if not self.use_sck or self._sck_failed:
            return None
        try:
            if self._sck is None:
                from .sck import SCKCapturer
                self._sck = SCKCapturer()
            img, screen, scale = self._sck.capture()
            return img, screen, scale, set(self._sck.excluded_apps)
        except ScreenPermissionError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("ScreenCaptureKit failed (%s); falling back to CGDisplayCreateImage + overlay masking", e)
            self._sck_failed = True
            return None

    def observe_now(self, force: bool = True, trigger: str = "manual") -> ScreenObservation | None:
        """Capture + OCR synchronously. With force=False, skips OCR when nothing changed."""
        from . import macos
        with self._capture_lock:
            self._last_capture = time.time()
            try:
                img, screen, scale, windows, fixture_app, source, overlay_excluded = self._grab()
            except Exception as e:
                self._set_error(e)
                raise
            self._set_error(None)
            with self._lock:
                overlay = list(self._overlay)
            layout = tuple((w.app, w.title, w.rect) for w in windows)
            thumb = macos.thumbnail(img)
            thumb = _mask_thumb(thumb, overlay, screen)
            prev = self._latest
            stale = prev is None or (time.time() - prev.t) > self.max_age
            if not force and not stale and layout == self._prev_layout and not _changed(
                    self._prev_thumb, thumb, self.diff_pixels):
                return None
            self._prev_thumb, self._prev_layout = thumb, layout

            blocks, ms = macos.ocr_image(img, screen, scale)
            if not overlay_excluded:  # CG fallback: the overlay is in the pixels, drop its text
                blocks = M.drop_inside(blocks, overlay)
            blocks = M.reading_order(M.assign_windows(blocks, windows))
            blocks = [Block(redact(b.text), b.rect, b.confidence, b.app, b.window) for b in blocks
                      if not is_private_app(b.app)]
            self._frame += 1
            obs = ScreenObservation(t=time.time(), app=fixture_app or macos.frontmost_app(windows),
                                    windows=windows, blocks=blocks, screen=screen, scale=scale,
                                    ocr_ms=ms, frame=self._frame, source=source, trigger=trigger,
                                    overlay_excluded=overlay_excluded)
            if source == "live":
                self._attach_cursor_and_ax(obs)
            self.ocr_ms_history = (self.ocr_ms_history + [ms])[-50:]
            with self._lock:
                self._latest, self._latest_image = obs, img
                subs = list(self._subs)
                readers = list(self._metric_readers)
        for r in readers:
            try:
                r.feed(obs)
            except Exception:
                log.exception("metric reader failed")
        for cb, loop in subs:
            try:
                if loop is not None:
                    if inspect.iscoroutinefunction(cb):
                        asyncio.run_coroutine_threadsafe(cb(obs), loop)
                    else:
                        loop.call_soon_threadsafe(cb, obs)
                else:
                    cb(obs)
            except Exception:
                log.exception("screen subscriber failed")
        return obs

    # ------------------------------------------------------------------ cursor + AX

    def _attach_cursor_and_ax(self, obs: ScreenObservation) -> None:
        snap = self.ax_reader.latest() if self.ax_reader else None
        if snap is not None and time.time() - snap.t > 2.0:
            snap = None
        if snap is not None:
            obs.ax = _redact_ax(snap.to_dict())
            lines = (snap.editor.text.split("\n") if snap.editor else []) + list(snap.terminal_lines)
            if sum(len(x) for x in lines) >= 100:  # under ~100 chars AX is unreliable: OCR only
                obs.ax_lines = {snap.app: [redact(x) for x in lines]}
        ctx = self.cursor_context(obs, snap)
        obs.cursor = (ctx["x"], ctx["y"])
        obs.under_cursor = ctx

    def cursor_context(self, obs: ScreenObservation | None = None, snap=None) -> dict:
        """Where the mouse is and what's under it, for every observation and the coach payload:
        {x, y, app, window, ocr_line, ocr_rect, ax: {role, title, value, rect}, editor_line,
         editor_line_text, caret_line}. Live: cheap enough to call on demand (~1 ms + one AX read)."""
        from .ax import mouse_location
        x, y = mouse_location()
        obs = obs or self.latest()
        out: dict = {"x": round(x, 1), "y": round(y, 1)}
        if obs is not None:
            w = M.window_at_point(obs, x, y)
            out["app"], out["window"] = (w.app, w.title) if w else (None, None)
            ln = M.line_at_point(obs, x, y)
            out["ocr_line"] = ln.text if ln else None
            out["ocr_rect"] = ln.rect.to_dict() if ln else None
        if snap is None and self.ax_reader is not None:
            snap = self.ax_reader.latest()
        if snap is not None:
            if snap.under_mouse is not None:
                out["ax"] = _redact_ax(snap.under_mouse.to_dict())
            ed = snap.editor
            if ed is not None:
                out["caret_line"] = ed.caret_line
                hover = ed.line_at_y(y)
                if hover is not None and ed.line_rect and ed.line_rect.x - 80 <= x <= ed.line_rect.x2:
                    out["editor_line"] = hover
                    t = ed.line_text(hover)
                    out["editor_line_text"] = redact(t) if t is not None else None
                    r = ed.rect_for_line(hover)
                    out["editor_line_rect"] = r.to_dict() if r else None
        return out

    def screenshot_pil(self, region=None):
        """The last captured frame as a PIL image (overlay blacked out), optionally cropped to a
        region in points."""
        from PIL import ImageDraw

        from . import macos
        with self._lock:
            img, obs, overlay = self._latest_image, self._latest, list(self._overlay)
        if img is None:
            obs = self.observe_now(force=True)
            with self._lock:
                img = self._latest_image
        if img is None or obs is None:
            return None
        pil = macos.cgimage_to_pil(img)
        s = obs.scale
        d = ImageDraw.Draw(pil)
        for r in overlay:
            d.rectangle([(r.x - obs.screen.x) * s, (r.y - obs.screen.y) * s,
                         (r.x2 - obs.screen.x) * s, (r.y2 - obs.screen.y) * s], fill=(0, 0, 0))
        if region is not None:
            r = Rect.from_any(region).clamp(obs.screen)
            pil = pil.crop((int((r.x - obs.screen.x) * s), int((r.y - obs.screen.y) * s),
                            int((r.x2 - obs.screen.x) * s), int((r.y2 - obs.screen.y) * s)))
        return pil


# ---------------------------------------------------------------------- helpers

def _changed(a: bytes | None, b: bytes, min_pixels: int) -> bool:
    if a is None or len(a) != len(b):
        return True
    if a == b:
        return False
    n = 0
    for x, y in zip(a, b):
        if abs(x - y) > 12:
            n += 1
            if n >= min_pixels:
                return True
    return False


def _mask_thumb(thumb: bytes, rects: list[Rect], screen: Rect) -> bytes:
    if not rects or screen.w <= 0:
        return thumb
    from .macos import THUMB_H, THUMB_W
    buf = bytearray(thumb)
    sx, sy = THUMB_W / screen.w, THUMB_H / screen.h
    for r in rects:
        r = r.clamp(screen)
        x0, x1 = int((r.x - screen.x) * sx), min(THUMB_W, int((r.x2 - screen.x) * sx) + 1)
        y0, y1 = int((r.y - screen.y) * sy), min(THUMB_H, int((r.y2 - screen.y) * sy) + 1)
        for y in range(max(0, y0), y1):
            buf[y * THUMB_W + max(0, x0): y * THUMB_W + x1] = bytes(max(0, x1 - max(0, x0)))
    return bytes(buf)


def _redact_ax(d: dict) -> dict:
    """Scrub PII from string values of an AX dict (recursively)."""
    def walk(v):
        if isinstance(v, str):
            return redact(v)
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    return walk(d)


def load_fixture(path: str):
    """A saved screenshot + optional sidecar `<name>.json` with screen/scale/app/windows.
    -> (cgimage, screen, scale, windows, app)"""
    from . import macos
    from .macos import Quartz
    img = macos.load_cgimage(str(path))
    side = Path(path).with_suffix(".json")
    meta = json.loads(side.read_text()) if side.exists() else {}
    scale = float(meta.get("scale", 2.0))
    screen = Rect.from_any(meta["screen"]) if "screen" in meta else Rect(
        0, 0, Quartz.CGImageGetWidth(img) / scale, Quartz.CGImageGetHeight(img) / scale)
    windows = [Window(app=w["app"], title=w.get("title", ""), rect=Rect.from_any(w["rect"]))
               for w in meta.get("windows", [])]
    app = meta.get("app") or (windows[0].app if windows else "")
    return img, screen, scale, windows, app


def observe_image(path: str, overlay=None) -> ScreenObservation:
    """OCR a saved screenshot exactly like a live frame (used by tests and the CLI)."""
    from . import macos
    img, screen, scale, windows, app = load_fixture(path)
    blocks, ms = macos.ocr_image(img, screen, scale)
    blocks = M.drop_inside(blocks, [Rect.from_any(r) for r in (overlay or [])])
    blocks = M.reading_order(M.assign_windows(blocks, windows))
    return ScreenObservation(t=time.time(), app=app, windows=windows, blocks=blocks, screen=screen,
                             scale=scale, ocr_ms=ms, frame=1, source=f"fixture:{Path(path).name}")


_READER: ScreenReader | None = None


def get_reader() -> ScreenReader:
    """The process-wide reader (not started; call `.start()` once in the orchestrator)."""
    global _READER
    if _READER is None:
        _READER = ScreenReader()
    return _READER


__all__ = ["Block", "Rect", "ScreenReader", "Window", "get_reader", "load_fixture", "observe_image"]
