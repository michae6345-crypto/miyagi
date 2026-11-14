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
                 fixture: str | None = None):
        _load_env()
        self.interval = interval
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
        self._thread = threading.Thread(target=self._run, name="screen-reader", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def poke(self) -> None:
        """Capture now instead of waiting for the next tick (e.g. right after a run ended)."""
        self._prev_thumb = None
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self.observe_now(force=False)
            except Exception as e:
                if type(e).__name__ == "ScreenUnavailableError":  # asleep/locked/switching Spaces: expected
                    now = time.time()
                    if now - getattr(self, "_unavail_logged", 0.0) > 60:
                        self._unavail_logged = now
                        log.warning("screen unavailable: %s (retrying quietly)", e)
                elif not isinstance(e, ScreenPermissionError):
                    log.exception("screen capture/OCR failed")
            self._wake.wait(max(0.05, self.interval - (time.time() - t0)))
            self._wake.clear()

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

    def set_keys(self, gemini: str | None = None, tiger_url: str | None = None) -> dict[str, str]:
        """BYOK from the app's `config.keys` ({gemini, tigerUrl}). Empty/None = keep using .env.
        Returns the screen reader's part of `config.status`."""
        self._describer.set_key(gemini)
        self._tiger_writer().set_url(tiger_url)
        return self.key_status()

    def key_status(self) -> dict[str, str]:
        """{"gemini": KeyState, "tigerUrl": KeyState} (events.ts KeyState: ok|missing|invalid|env)."""
        return {"gemini": self._describer.key_status, "tigerUrl": self._tiger_writer().status}

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

    async def describe(self, question: str, region=None) -> str:
        """Ask Gemini about the current screen (or a region of it, in points). Rate-limited.
        Raises DescribeError (reason: missing_key | invalid_key | no_image | unavailable)."""
        try:
            img = await asyncio.to_thread(self.screenshot_pil, region)
        except Exception as e:
            raise DescribeError("no_image", str(e)[:200]) from e
        if img is None:
            raise DescribeError("no_image", self.last_error or "nothing captured yet")
        key = (question, Rect.from_any(region).rounded() if region else None, self._frame)
        return await self._describer.describe(to_jpeg(img), question, key)

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
            return img, screen, scale, windows, app, f"fixture:{Path(self.fixture).name}"
        try:
            if not macos.has_permission():
                raise macos.ScreenPermissionError(macos.PERMISSION_HELP)
            f = macos.capture_main_display()
        except macos.ScreenPermissionError:
            if not self._permission_warned:
                print(macos.PERMISSION_HELP, file=sys.stderr)
                self._permission_warned = True
            fixtures = sorted(FIXTURES_DIR.glob("*.png"))
            if self.demo and fixtures:
                log.warning("DEMO=1 and no Screen Recording permission: replaying %s", fixtures[0].name)
                img, screen, scale, windows, app = load_fixture(str(fixtures[0]))
                return img, screen, scale, windows, app, f"fixture:{fixtures[0].name}"
            raise
        return f.image, f.screen, f.scale, macos.list_windows(f.screen), None, "live"

    def observe_now(self, force: bool = True) -> ScreenObservation | None:
        """Capture + OCR synchronously. With force=False, skips OCR when nothing changed."""
        from . import macos
        with self._capture_lock:
            try:
                img, screen, scale, windows, fixture_app, source = self._grab()
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
            blocks = M.drop_inside(blocks, overlay)
            blocks = M.reading_order(M.assign_windows(blocks, windows))
            self._frame += 1
            obs = ScreenObservation(t=time.time(), app=fixture_app or macos.frontmost_app(windows),
                                    windows=windows, blocks=blocks, screen=screen, scale=scale,
                                    ocr_ms=ms, frame=self._frame, source=source)
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
