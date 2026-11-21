"""ScreenReader: the capture loop + OCR + the public API the other engine modules use."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import lines as L
from . import match as M
from . import regions as R
from .describe import DescribeError, Describer, to_jpeg
from .metrics import TerminalMetricReader, TigerWriter
from .privacy import holds_secret, is_private_app, redact
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
        # capture backends, tried in order: sck (overlay left out) -> cli (`screencapture`, overlay
        # masked) -> cg. TUT_CAPTURE=cli skips SCK; TUT_CAPTURE=cg forces the old CG-only path.
        self.capture_mode = os.environ.get("TUT_CAPTURE", "sck")
        self.use_sck = self.capture_mode == "sck"
        self.backend: str | None = None   # which backend produced the latest frame
        self.ax_reader = None       # server.screen.ax.AXReader once started (None: AX unavailable)
        self.events = None          # server.screen.events.EventTriggers once started
        self._sck = None
        self._sck_retry_at = 0.0     # after a ScreenCaptureKit failure, skip it until then
        self._sck_streak = 0         # consecutive SCK failures (backoff 10 s, 20 s, ... 5 min)
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
        self._latest_overlay: list[Rect] = []    # the overlay rects when the latest frame was captured
        self._lesson_folder: str | None = None   # set_lesson_folder: other folders' VS Code windows are left out
        self._subs: list[tuple[Callback, asyncio.AbstractEventLoop | None]] = []
        self._metric_readers: list[TerminalMetricReader] = []
        self._tiger: TigerWriter | None = None
        self._describer = Describer()
        self._regions = R.RegionStabilizer()
        self._front: tuple[float, dict | None] = (0.0, None)
        self._front_cbs: list[Callable[[dict | None, dict | None], object]] = []
        self._front_thread: threading.Thread | None = None
        self._run_btn: tuple[float, Rect | None, float] = (0.0, None, 0.0)  # (when, rect, kept for s)
        self._ui_els: dict[str, tuple[float, Rect | None, float]] = {}  # ax.find_ui results by key (_ax_ui)
        self._lock = threading.RLock()
        self._capture_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._frame = 0
        self._permission_warned = False
        self._blank_streak = 0         # consecutive black / flat frames (a locked or revoked capture)
        self._screen_key: tuple | None = None  # captured display frame at the last capture (change detection)
        self._last_tick = time.time()  # wall clock of the last loop turn (a big gap = the Mac slept)
        self.ax_trusted: bool | None = None   # Accessibility grant at the last check (None = not checked / n.a.)
        self._ax_check = None                  # tests: replaces ax.trusted()
        self._ticks = 0

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
            now_t = time.time()
            if now_t - self._last_tick > max(30.0, 4 * self.heartbeat):  # asleep (the loop was frozen): start clean
                self.reset_capture("wake")
                woke = True
            self._last_tick = now_t
            self._ticks += 1
            if self._ticks % self.AX_CHECK_EVERY == 1:
                self.check_accessibility()
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

    AX_CHECK_EVERY = 3  # loop turns between AXIsProcessTrusted() checks (a cheap call; revocation is rare)

    def check_accessibility(self) -> bool | None:
        """Is the Accessibility grant still there? Revoking it mid-session silently blinds the AX sensors (cursor,
        active file, run button) while OCR keeps working, so it is tracked apart from Screen Recording: it sets
        `ax_trusted` only and never touches `status` / `last_error` (the OCR path is not paused)."""
        if self._ax_check is None and (sys.platform != "darwin" or self.fixture or not self.use_ax):
            return None
        try:
            if self._ax_check is not None:
                ok = bool(self._ax_check())
            else:
                from . import ax
                ok = bool(ax.trusted())
        except Exception:  # noqa: BLE001
            return self.ax_trusted
        if ok != self.ax_trusted and self.ax_trusted is not None:
            log.warning("Accessibility permission %s", "granted" if ok else "REVOKED")
        self.ax_trusted = ok
        return ok

    def reset_capture(self, why: str = "") -> None:
        """Forget capture state that sleep/wake, a display change or a blank frame can leave stale: the SCK filter and
        its backoff, the last thumbnail (so the next frame is OCR'd) and the blank streak. The next capture is forced."""
        log.info("screen capture reset (%s)", why or "manual")
        with self._capture_lock:  # not mid-capture: observe_now holds this while it uses the filter
            sck = self._sck
            if sck is not None:
                sck._filter = None
            self._sck_retry_at, self._sck_streak = 0.0, 0
            self._prev_thumb, self._blank_streak = None, 0
        self.poke("reset", force=True)

    @property
    def thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

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
        from . import health, macos
        msg = None if e is None else (
            f"no_permission: {macos.PERMISSION_HELP}\n{health.permission_hint()}" if isinstance(e, macos.ScreenPermissionError)
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

    def overlay_rects(self) -> list[Rect]:
        """Our overlay's rects to leave out of the latest frame: the ones reported when it was captured and the
        current ones (a card that opened or moved since the capture is covered either way)."""
        with self._lock:
            return list(self._latest_overlay) + [r for r in self._overlay if r not in self._latest_overlay]

    def set_lesson_folder(self, folder: str | None) -> None:
        """Bind the screen to the lesson's own editor window (a folder name or path; None unbinds). VS Code windows
        whose title names ANOTHER folder are then left out of every observation: their OCR text (checks, coach,
        locate), their rects (regions, line spotlights, Show me), AX text of such a window or of one on another
        Space, and the screenshot a model sees (blacked out). They are listed in `obs.foreign`."""
        folder = str(folder) if folder else None
        with self._lock:
            changed, self._lesson_folder = folder != self._lesson_folder, folder
        if changed:
            log.info("screen bound to %s", Path(folder).name if folder else "every window")
            self.poke("lesson_folder", force=True)

    def locate(self, match: str, app: str | None = None) -> Rect | None:
        res = self.locate_match(match, app)
        return res.rect if res else None

    def locate_match(self, match: str, app: str | None = None) -> M.LocateResult | None:
        obs = self.latest() or self.observe_now(force=True)
        return M.locate_match(obs, match, app) if obs else None

    def locate_match_cached(self, match: str, app: str | None = None) -> M.LocateResult | None:
        """locate_match on the latest frame only: never a capture + OCR (for callers on the asyncio loop)."""
        obs = self.latest()
        return M.locate_match(obs, match, app) if obs else None

    def snap_rows(self, rect: Rect, app: str | None = None) -> Rect | None:
        """t8: `rect` (a text match's box) with the y / height of the editor rows it is on (the gutter's, as the
        full-line box has them) in the latest frame; None when it isn't on an editor's rows."""
        obs = self.latest()
        return L.snap_rows(obs, rect, app) if obs else None

    # ------------------------------------------------------------------ editor lines ("just teach me")

    def locate_line(self, file: str | None, line: int, app: str | None = None,
                    obs: ScreenObservation | None = None) -> L.LineLocation:
        """Where file line `line` of `file` is in VS Code / Cursor: a full-width row rect of the editor
        text area, or (falsy result) `rect=None` with `visible_lines`, `direction` and `reason` so the
        caller can scroll there (`cursor -g file:line`) and ask again. OCR of a fresh frame (<= 1 s old),
        cross-checked with the AX editor state when Accessibility is granted."""
        obs = obs or self._fresh_obs()
        loc = L.locate_line(obs, file, line, app) if obs else L.LineLocation(file, line, reason="no_editor")
        if obs is None or obs.source == "live":
            ed, doc = self._ax_editor()
            loc = L.merge_ax(loc, ed, doc, file, line)
        return loc

    def locate_anchor(self, text: str, app: str | None = None, file: str | None = None) -> L.LineLocation:
        """The editor line containing `text` (e.g. "def pde_residual("), as in `locate_line`, plus
        `match_rect` (the text itself) and `line` (its file line number). If the anchor is scrolled
        off screen, `line` + `direction` still come from the AX buffer, or from `file` on disk."""
        obs = self._fresh_obs()
        live = obs is None or obs.source == "live"
        ed, doc = self._ax_editor() if live else (None, None)
        if ed is not None and (file is None or L.same_file(doc, file)):
            n = L.ax_anchor_line(ed, text)
            if n is not None:
                loc = self.locate_line(file or doc, n, app, obs=obs)
                if loc and obs is not None:
                    ocr = L.locate_anchor(obs, text, app, file or doc)
                    if ocr.line == n:
                        loc.match_rect = ocr.match_rect
                return loc
        if obs is None:
            return L.LineLocation(file, None, reason="no_editor")
        return L.locate_anchor(obs, text, app, file, _read_text(file))

    # ------------------------------------------------------------------ regions (lesson spotlights)

    def locate_region(self, name: str, app: str | None = None, max_age: float = 1.0) -> Rect | None:
        """Rect of a VS Code region for a spotlight: "terminal" (integrated terminal panel; None if
        it isn't open), "editor" (text area below tabs + breadcrumb), "explorer" (side bar),
        "run_button" (AX only; None without Accessibility), "terminal_menu" (the Terminal item in the
        macOS menu bar while VS Code is in front; AX, else OCR; None when the menu bar is hidden),
        "menu:<Title>" (any menu-bar item). Stable frame to frame: snapped to a
        4-point grid, unchanged while it moves < 12 points, kept through one missed frame.
        max_age: an older latest frame is re-captured + OCR'd first (blocking); the engine's event loop passes a
        large one (its callers read blocks from that same latest frame, and a capture there froze every tick)."""
        if name == "ui:quickpick":  # t9: VS Code's open quick-pick (ax.find_quickpick), fresh each look (screen.avoid)
            return self._ax_quickpick()
        if name.startswith("ui:"):  # one of VS Code's own controls, by Accessibility only (ax.find_ui)
            return self._ax_ui(name[3:])
        title = R.menu_title(name)            # "terminal_menu" / "menu:Run" keep their case
        name = R.canonical(name)
        obs = self._fresh_obs(max_age)
        if name == "run_button":
            rect = self._ax_run_button() if obs is None or obs.source == "live" else None
            if rect is None and obs is not None:          # the ▷ icon on the tab row, by OCR
                reg = R.find_region(obs, name, app)
                rect = reg.rect if reg else None
        elif title is not None:
            rect = self._ax_menu_item(title) if obs is None or obs.source == "live" else None
            if rect is None and obs is not None:
                reg = R.find_menu_item(obs, title, app)
                rect = reg.rect if reg else None
        else:
            reg = R.find_region(obs, name, app) if obs is not None else None
            rect = reg.rect if reg else None
        with self._lock:
            return self._regions.update((name, app), rect, obs.frame if obs is not None else None)

    def locate_regions(self, names=R.REGIONS, app: str | None = None) -> dict[str, dict | None]:
        """{name: {x, y, w, h} | None} for several regions from one frame (JSON-ready)."""
        out = {}
        for n in names:
            r = self.locate_region(n, app)
            out[n] = r.to_dict() if r else None
        return out

    def candidates(self, intent: str | None = None, app: str | None = None, max_lines: int = 120):
        """Set-of-marks targets from a fresh frame (<= 1 s old): regions with fixed ids (1 terminal,
        2 editor, 3 explorer, 4 terminal_menu; their rects are the same stabilized ones locate_region
        returns) and OCR lines from id 10 (editor code rows with file line numbers first). Hover
        tooltips, the breadcrumb and the tab/title bar are left out. -> list[marks.Candidate];
        `marks.listing(c)` is the prompt text, `marks.by_id(c, id)` the pick."""
        from . import marks
        obs = self._fresh_obs()
        if obs is None:
            return []
        regions = {n: self.locate_region(n, app) for n in marks.REGION_IDS}
        return marks.candidates(obs, intent, app, max_lines=max_lines, regions=regions)

    def _ax_menu_item(self, title: str) -> Rect | None:
        """The frontmost app's menu-bar item (AX: exact, even while the menu bar is auto-hidden in
        full screen, where the rect is where it appears). None without Accessibility."""
        if sys.platform != "darwin" or not self.use_ax:
            return None
        try:
            from . import ax
            if not ax.trusted():
                return None
            el = ax.menu_bar_item(title)
            return el.rect if el is not None else None
        except Exception as e:  # noqa: BLE001
            log.debug("AX menu item lookup failed: %s", e)
            return None

    # t7: a lookup that missed while VS Code was still filling its AX tree (ax.last_miss "settling") is kept only this
    # long: the ▷ was on screen 2 ms after the lookup that switched the tree on, and that miss stood for 6 s
    AX_SETTLING_KEEP_S = 0.25

    def _ax_keep(self, key: str, rect: Rect | None, absent_s: float) -> float:
        """How long a lookup's answer stands: found 1 s; not there `absent_s`, or a moment while the tree fills in."""
        if rect is not None:
            return 1.0
        try:
            from . import ax
            return self.AX_SETTLING_KEEP_S if ax.last_miss(key) == "settling" else absent_s
        except Exception:  # noqa: BLE001
            return absent_s

    def _ax_run_button(self) -> Rect | None:
        if sys.platform != "darwin" or not self.use_ax:
            return None
        t, cached, keep = self._run_btn
        if time.time() - t < keep:  # not there: no new walk of VS Code's tree for 6 s (t7: unless it was filling in)
            return cached
        rect = None
        try:
            from . import ax
            if ax.trusted():
                # the lesson window's "Run Python File" (also while Miyagi's drawer is in front), never the activity
                # bar's "Run and Debug" or the dropdown's "Run or Debug..." (a frontmost-app "^Run" search matched
                # those)
                el = ax.find_run_button(self._lesson_folder)
                rect = el.rect if el is not None else None
        except Exception as e:  # noqa: BLE001
            log.debug("AX run button lookup failed: %s", e)
        self._run_btn = (time.time(), rect, self._ax_keep("run_button", rect, 6.0))
        return rect

    def _ax_ui(self, key: str) -> Rect | None:
        """ax.find_ui(key) in the lesson's window: "terminal_tab", "toggle_panel", "tab:nn.py", "dirty:nn.py",
        "explorer:nn.py", "problems", "interpreter". Cached like the Run ▷ (found: 1 s; not there: no new walk for
        4 s, a moment while the tree fills in). None without Accessibility, in a fixture, or when it isn't on screen."""
        if sys.platform != "darwin" or not self.use_ax or self.fixture:
            return None
        t, cached, keep = self._ui_els.get(key, (0.0, None, 0.0))
        if time.time() - t < keep:
            return cached
        rect = None
        try:
            from . import ax
            if ax.trusted():
                el = ax.find_ui(key, self._lesson_folder)
                rect = el.rect if el is not None else None
        except Exception as e:  # noqa: BLE001
            log.debug("AX %s lookup failed: %s", key, e)
        self._ui_els[key] = (time.time(), rect, self._ax_keep(f"ui:{key}", rect, 4.0))
        return rect

    def _ax_quickpick(self) -> Rect | None:
        """t9: VS Code's open quick-pick (ax.find_quickpick: the focused element and its parents, a dozen AX reads), not
        cached (it opens and closes in a moment). None without Accessibility, in a fixture, or when it is closed."""
        if sys.platform != "darwin" or not self.use_ax or self.fixture:
            return None
        try:
            from . import ax
            if ax.trusted():
                el = ax.find_quickpick(self._lesson_folder)
                return el.rect if el is not None else None
            if getattr(self, "_qp_error", None) != "untrusted":
                self._qp_error = "untrusted"
                log.info("AX quickpick lookup skipped: no Accessibility permission")
        except Exception as e:  # noqa: BLE001
            if str(e) != getattr(self, "_qp_error", None):  # t11: was debug (test 11 sent no screen.avoid at all)
                self._qp_error = str(e)
                log.info("AX quickpick lookup failed: %s", e)
        return None

    # ------------------------------------------------------------------ frontmost app / VS Code window

    def frontmost(self, max_age: float = 0.2) -> dict | None:
        """{app, pid, title, window_id, rect} of the window in front on the CURRENT Space, read live
        from the window server (~0.3 ms; cached `max_age` s). Changes the moment the user swipes to
        another Space or switches apps. Our overlay never counts as frontmost."""
        t, cached = self._front
        if time.time() - t <= max_age:
            return cached
        if self.fixture or sys.platform != "darwin":
            obs = self.latest()
            w = obs.windows[0] if obs is not None and obs.windows else None
            cur = {"app": w.app, "pid": w.pid, "title": w.title, "window_id": w.window_id,
                   "rect": w.rect.to_dict()} if w else None
        else:
            from . import macos
            try:
                cur = macos.frontmost_window()
            except Exception as e:  # noqa: BLE001
                log.debug("frontmost lookup failed: %s", e)
                cur = None
        self._front = (time.time(), cur)
        return cur

    def is_frontmost(self, app: str = "Code") -> bool:
        """Is `app` ("Code", "VS Code", "Cursor", "Terminal" ...) in front on the current Space?"""
        f = self.frontmost()
        return bool(f) and M.app_matches(app, f["app"], f.get("title"))

    def on_frontmost_change(self, cb: Callable[[dict | None, dict | None], object],
                            interval: float = 0.25) -> Callable[[], None]:
        """Call `cb(new, old)` within ~`interval` s whenever the frontmost app/window changes (app
        switch, Space swipe, full-screen toggle). One background poller for all callbacks; it also
        pokes a capture so the next observation shows the new screen. Returns an unsubscribe."""
        with self._lock:
            self._front_cbs.append(cb)
            if self._front_thread is None or not self._front_thread.is_alive():
                self._front_thread = threading.Thread(target=self._watch_front, args=(interval,),
                                                      name="screen-frontmost", daemon=True)
                self._front_thread.start()

        def unsubscribe() -> None:
            with self._lock:
                if cb in self._front_cbs:
                    self._front_cbs.remove(cb)
        return unsubscribe

    def _watch_front(self, interval: float) -> None:
        def key(f):
            return (f["app"], f["pid"], f["window_id"]) if f else None
        last = self.frontmost(max_age=0)
        while not self._stop.is_set():
            with self._lock:
                if not self._front_cbs:
                    self._front_thread = None
                    return
                cbs = list(self._front_cbs)
            self._stop.wait(interval)
            cur = self.frontmost(max_age=0)
            if key(cur) != key(last):
                if self._thread is not None and self._thread.is_alive():
                    self.poke("app_switch", force=True)
                for cb in cbs:
                    try:
                        cb(cur, last)
                    except Exception:
                        log.exception("frontmost callback failed")
                last = cur

    def vscode_window(self, app: str | None = None, fresh: bool = False) -> dict | None:
        """{app, title, folder, file, path, symbol, dirty, sources} of the frontmost VS Code window
        (OCR of a frame + its window title; AX's file and dirty flag when Accessibility is on).
        fresh=True captures a NEW frame first (Check / step changes: never a frame from before the
        learner's last switch). For "which file is open" prefer `active_file()`."""
        from .vscode import vscode_window
        obs = self._fresh_obs(max_age=0.0 if fresh else 1.0)
        win = vscode_window(obs, app) if obs is not None else None
        if win is None:
            return None
        if obs.source == "live":
            snap = self.ax_reader.latest() if self.ax_reader is not None and self.ax_reader.available else None
            if snap is not None and time.time() - snap.t < 2.0 and M.app_matches(win.app, snap.app) \
                    and self._ax_shown(snap, obs):
                if snap.dirty is not None:
                    win.dirty, win.sources["dirty"] = snap.dirty, "ax"
                if snap.document:
                    win.sources["document"] = snap.document
        return win.to_dict()

    def active_file(self, fresh: bool = True, folder: str | None = None) -> dict:
        """THE answer to "which file is the learner on", read fresh from every source, best first:
        the companion extension (/state of the window with `folder`, else the focused one), AX (the
        focused VS Code window's AXDocument), the live window title, then OCR of the active tab +
        breadcrumb in a NEW frame (fresh=True). Extension/AX are trusted alone; title and OCR only when
        they agree. Otherwise file=None, confidence="unsure": callers must not claim a wrong file.
        -> {file, path, folder, dirty, source, confidence, candidates, title, app, t}. Blocking
        (~0.3 s extension timeout + one capture); from async code use asyncio.to_thread."""
        from . import vscode as V
        ext = ax_d = title_d = ocr_d = None
        app = title = None
        try:                                         # 1. the companion extension
            from server.workspace import vscode_ext as vx
            ed = vx.active_editor() if folder is None else None
            if folder is not None:
                st = vx.state(folder=folder)
                if st and st.get("file") and "://" not in str(st["file"]):
                    ed = {"file": Path(st["file"]).name, "path": st["file"], "dirty": bool(st.get("dirty"))}
            if ed and ed.get("file"):
                ext = {"file": ed.get("file"), "path": ed.get("path"), "folder": ed.get("folder"),
                       "dirty": ed.get("dirty")}
        except Exception as e:  # noqa: BLE001
            log.debug("companion extension unavailable: %s", e)
        front = self.frontmost(max_age=0.0) if fresh else self.frontmost()
        front_is_code = bool(front) and any(M.app_matches(a, front["app"]) for a in L.EDITOR_APPS)
        if front_is_code:
            app, title = front["app"], front.get("title") or ""
            if ext is None and sys.platform == "darwin" and self.use_ax:    # 2. AX
                try:
                    from . import ax
                    snap = ax.snapshot() if ax.trusted() else None
                    if snap is not None and snap.document and M.app_matches(snap.app, app):
                        ax_d = {"path": snap.document, "file": Path(snap.document).name, "dirty": snap.dirty}
                except Exception as e:  # noqa: BLE001
                    log.debug("AX document read failed: %s", e)
            t_file, t_folder, t_dirty = V.parse_title(title)                  # 3. the live window title
            if t_file:
                title_d = {"file": t_file, "folder": t_folder, "dirty": t_dirty}
        if ext is None and ax_d is None:                                       # 4. OCR of a fresh frame
            try:
                obs = self._fresh_obs(max_age=0.0 if fresh else 1.0)
                ocr_d = V.ocr_only(V.vscode_window(obs)) if obs is not None else None
            except Exception as e:  # noqa: BLE001
                log.debug("OCR active-file read failed: %s", e)
        out = V.resolve_active(ext, ax_d, title_d, ocr_d)
        out.update(app=app, title=title, t=time.time())
        if out["confidence"] == "unsure":
            log.info("active file unsure: %s", out["candidates"])
        return out

    def _fresh_obs(self, max_age: float = 1.0) -> ScreenObservation | None:
        obs = self.latest()
        if obs is not None and (time.time() - obs.t <= max_age or obs.source != "live"):
            return obs
        try:
            return self.observe_now(force=True, trigger="locate") or self.latest()
        except Exception:
            if obs is not None:
                return obs
            raise

    def _ax_editor(self):
        """(EditorState, document) of the focused editor via AX, or (None, None)."""
        if sys.platform != "darwin" or not self.use_ax:
            return None, None
        try:
            snap = self.ax_reader.latest() if self.ax_reader is not None and self.ax_reader.available else None
            if snap is None or time.time() - snap.t > 1.0:
                from . import ax
                snap = ax.snapshot() if ax.trusted() else None
        except Exception as e:  # noqa: BLE001
            log.debug("AX editor read failed: %s", e)
            return None, None
        if snap is None or snap.editor is None or not self._ax_shown(snap, self.latest()):
            return None, None
        return snap.editor, snap.document

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
        mask = [(b.rect.x, b.rect.y, b.rect.w, b.rect.h) for b in obs.blocks if holds_secret(b.text)]  # 5.2
        jpeg = to_jpeg(img, cursor=(ctx["x"], ctx["y"]) if live else None, scale=obs.scale, origin=origin, mask=mask)
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
            self.backend = None
            img, screen, scale, windows, app = load_fixture(self.fixture)
            return img, screen, scale, windows, app, f"fixture:{Path(self.fixture).name}", False
        try:
            if not macos.has_permission():
                raise macos.ScreenPermissionError(macos.PERMISSION_HELP)
            display_id = macos.target_display_id()  # the display holding the learner's window, not always the primary
            sck = self._sck_capture(display_id)
            if sck is not None:
                img, screen, scale, excluded = sck
                windows = [w for w in macos.list_windows(screen) if w.app not in excluded]
                self.backend = "sck"
                # left out only if SCK found our overlay app to exclude; else its pixels are in: mask by overlay.bounds
                return img, screen, scale, windows, None, "live", bool(getattr(self._sck, "overlay_apps", True))
            f = self._fallback_capture(display_id)
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

    def _fallback_capture(self, display_id: int | None = None):
        """`screencapture` (works when replayd stalls SCK + CG), then CGDisplayCreateImage."""
        from . import macos
        if self.capture_mode != "cg":
            try:
                f = macos.capture_main_display_cli(display_id=display_id)
                self.backend = "cli"
                return f
            except FileNotFoundError:
                pass  # no screencapture binary: CG below
        f = macos.capture_main_display(display_id)
        self.backend = "cg"
        return f

    def _sck_capture(self, display_id: int | None = None):
        """ScreenCaptureKit with our overlay excluded; None -> use the fallback capture.

        A failure (replayd stall, Space switch, sleep) is never permanent: SCK is skipped for 10 s,
        then 20, 40 ... up to 5 min while it keeps failing, and the fallback serves frames meanwhile,
        so the screen never goes blind because of SCK."""
        if not self.use_sck or time.time() < self._sck_retry_at:
            return None
        try:
            if self._sck is None:
                from .sck import SCKCapturer
                self._sck = SCKCapturer()
            img, screen, scale = self._sck.capture(display_id)
            if self._sck_streak:
                log.info("ScreenCaptureKit recovered after %d failure(s)", self._sck_streak)
            self._sck_retry_at, self._sck_streak = 0.0, 0
            return img, screen, scale, set(self._sck.excluded_apps)
        except ScreenPermissionError:
            raise
        except Exception as e:  # noqa: BLE001
            self._sck_streak += 1
            delay = min(300.0, 10.0 * 2 ** (self._sck_streak - 1))
            if e.__class__.__name__ == "SCKDeclined":  # t10 R5: a TCC refusal: the fallback for 5 min straight away
                delay = 300.0
            if self._sck_streak == 1 or self._sck_streak % 5 == 0:  # not a line per frame
                log.warning("ScreenCaptureKit failed (%s: %s); capturing with screencapture + overlay "
                            "masking, retrying SCK in %.0f s", e.__class__.__name__, e, delay)
            self._sck_retry_at = time.time() + delay
            return None

    def observe_now(self, force: bool = True, trigger: str = "manual") -> ScreenObservation | None:
        """Capture + OCR synchronously. With force=False, skips OCR when nothing changed."""
        from . import health, macos
        with self._capture_lock:
            self._last_capture = time.time()
            try:
                img, screen, scale, windows, fixture_app, source, overlay_excluded = self._grab()
            except Exception as e:
                self._set_error(e)
                raise
            key = (screen.x, screen.y, screen.w, screen.h)
            if health.display_changed(self._screen_key, key):  # monitor (un)plugged / resolution switched
                log.info("captured display changed %s -> %s: capture state reset", self._screen_key, key)
                self._prev_thumb, self._sck_retry_at = None, 0.0
                if self._sck is not None:
                    self._sck._filter = None
                force = True
            self._screen_key = key
            thumb = macos.thumbnail(img)
            kind = health.blank_kind(thumb) if source == "live" else None
            if kind:
                self._blank_streak += 1
                if self._blank_streak == 1 and self._sck is not None:
                    self._sck._filter = None  # a stale filter (Space / display swap) can return empty frames
                # a flat NON-black frame is far more often a real solid-colour screen (slide, video): wait longer
                if self._blank_streak >= (health.BLANK_STREAK if kind == "black" else health.FLAT_STREAK):
                    err = macos.ScreenUnavailableError(
                        f"blank frame ({'all black' if kind == 'black' else 'one flat colour'}): the screen shows no content")
                    self._set_error(err)
                    raise err
                return None  # one black frame is usually a transition: the next tick looks again
            self._blank_streak = 0
            self._set_error(None)
            with self._lock:
                overlay = list(self._overlay)
            layout = tuple((w.app, w.title, w.rect) for w in windows)
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
            blocks = M.postprocess(M.reading_order(M.assign_windows(blocks, windows)))
            blocks = repair_code_rows(img, screen, scale, blocks)
            blocks = [Block(redact(b.text), b.rect, b.confidence, b.app, b.window, b.role) for b in blocks
                      if not is_private_app(b.app)]
            from .vscode import scope_to_folder
            with self._lock:
                folder = self._lesson_folder
            blocks, shown, foreign, foreign_rects = scope_to_folder(  # fixture frames (DEMO fallback) are never scoped
                blocks, windows, folder if source == "live" else None)
            self._frame += 1
            obs = ScreenObservation(t=time.time(), app=fixture_app or macos.frontmost_app(windows),
                                    windows=shown, blocks=blocks, screen=screen, scale=scale,
                                    ocr_ms=ms, frame=self._frame, source=source, trigger=trigger,
                                    overlay_excluded=overlay_excluded,
                                    capture=(self.backend or "") if source == "live" else "fixture",
                                    foreign=foreign, foreign_rects=foreign_rects)
            obs.editor = _editor_info(obs)
            if source == "live":
                self._attach_cursor_and_ax(obs)
            self.ocr_ms_history = (self.ocr_ms_history + [ms])[-50:]
            with self._lock:
                self._latest, self._latest_image, self._latest_overlay = obs, img, overlay
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

    @staticmethod
    def _ax_shown(snap, obs: ScreenObservation | None) -> bool:
        """Is the AX snapshot's focused window one this frame shows? VS Code's focused window can be off screen (full
        screen on another Space) or another folder's (set_lesson_folder): its text / caret rect must not count."""
        from .vscode import window_shown
        return obs is None or obs.source != "live" or window_shown(snap.app, snap.window_title, obs.windows)

    def _attach_cursor_and_ax(self, obs: ScreenObservation) -> None:
        snap = self.ax_reader.latest() if self.ax_reader else None
        if snap is not None and (time.time() - snap.t > 2.0 or not self._ax_shown(snap, obs)):
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
        return self.latest_frame(region)[0]

    def latest_frame(self, region=None):
        """(PIL image of the last frame with our overlay blacked out, the ScreenObservation OCR'd from
        that same frame), or (None, None). For vision prompts whose marks come from the OCR
        (server.screen.target)."""
        from PIL import ImageDraw

        from . import macos
        with self._lock:
            img, obs = self._latest_image, self._latest
        if img is None:
            self.observe_now(force=True)
            with self._lock:
                img, obs = self._latest_image, self._latest
        overlay = self.overlay_rects()
        if img is None or obs is None:
            return None, None
        pil = macos.cgimage_to_pil(img)
        s = obs.scale
        d = ImageDraw.Draw(pil)
        for r in overlay + list(getattr(obs, "foreign_rects", None) or []):  # + other folders' VS Code windows
            d.rectangle([(r.x - obs.screen.x) * s, (r.y - obs.screen.y) * s,
                         (r.x2 - obs.screen.x) * s, (r.y2 - obs.screen.y) * s], fill=(0, 0, 0))
        if region is not None:
            r = Rect.from_any(region).clamp(obs.screen)
            pil = pil.crop((int((r.x - obs.screen.x) * s), int((r.y - obs.screen.y) * s),
                            int((r.x2 - obs.screen.x) * s), int((r.y2 - obs.screen.y) * s)))
        return pil, obs


# ---------------------------------------------------------------------- helpers

_BROKEN_DEF = re.compile(r"\b(?:def|class)\s*[(:]")          # keyword with its name missing
_GOOD_DEF = re.compile(r"\b(?:def|class)\s+[A-Za-z_]\w*")


def repair_code_rows(img, screen: Rect, scale: float, blocks: list[Block], max_rows: int = 3,
                     ocr=None) -> list[Block]:
    """Re-read code rows that came out impossible (`def(a, b):` = the coloured name was dropped):
    OCR just that row, cropped, which Vision reads more reliably than the whole screen. The row is
    replaced only if the second read has the name. At most `max_rows` rows per frame (~20 ms each)."""
    bad = [b for b in blocks if not b.role and b.app and _BROKEN_DEF.search(b.text)
           and not _GOOD_DEF.search(b.text)][:max_rows]
    if not bad:
        return blocks
    if ocr is None:
        from . import macos
        ocr = macos.ocr_image
    out = list(blocks)
    for b in bad:
        row = [x for x in out if x.app == b.app and x.window == b.window and not x.role
               and abs(x.rect.cy - b.rect.cy) < 0.5 * b.rect.h and x.rect.x >= b.rect.x - 2]
        right = max(x.rect.x2 for x in row)
        crop = Rect(b.rect.x - 6, b.rect.y - 4, right - b.rect.x + 12, b.rect.h + 8).clamp(screen)
        try:
            fresh, _ = ocr(img, screen, scale, crop=crop)
        except Exception as e:  # noqa: BLE001
            log.debug("row re-OCR failed: %s", e)
            continue
        text = " ".join(f.text for f in sorted(fresh, key=lambda f: f.rect.x)).strip()
        if not _GOOD_DEF.search(text):
            continue
        r = fresh[0].rect
        for f in fresh[1:]:
            r = r.union(f.rect)
        out = [x for x in out if x not in row] + [Block(text, r, min(f.confidence for f in fresh), b.app, b.window)]
        log.info("re-read code row %r -> %r", b.text, text)
    return M.reading_order(out)


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
        if r.w <= 0 or r.h <= 0:  # on another display: nothing of it is in this frame
            continue
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


def _read_text(file: str | None) -> str | None:
    if not file or not os.path.isfile(file):
        return None
    try:
        with open(file, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


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
    blocks = M.postprocess(M.reading_order(M.assign_windows(blocks, windows)))
    blocks = repair_code_rows(img, screen, scale, blocks)
    obs = ScreenObservation(t=time.time(), app=app, windows=windows, blocks=blocks, screen=screen,
                            scale=scale, ocr_ms=ms, frame=1, source=f"fixture:{Path(path).name}")
    obs.editor = _editor_info(obs)
    return obs


def _editor_info(obs: ScreenObservation) -> dict | None:
    try:
        from .vscode import vscode_window
        w = vscode_window(obs)
        return w.to_dict() if w is not None else None
    except Exception:
        log.exception("vscode_window failed")
        return None


_READER: ScreenReader | None = None


def get_reader() -> ScreenReader:
    """The process-wide reader (not started; call `.start()` once in the orchestrator)."""
    global _READER
    if _READER is None:
        _READER = ScreenReader()
    return _READER


__all__ = ["Block", "Rect", "ScreenReader", "Window", "get_reader", "load_fixture", "observe_image"]
