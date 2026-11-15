"""Event-driven capture triggers (instead of a fixed 1 fps loop).

A listen-only CGEventTap (never modifies or blocks input) reports:
  click        mouse down (with x, y, button)          -> capture right away (debounced)
  typing_pause no key for `pause_s` after typing           -> capture
  scroll_stop  no scroll for `scroll_s` after scrolling     -> capture
plus a cheap poll for
  app_switch   the frontmost window's owner changed        -> capture
Mouse taps need Accessibility; keyboard taps need Input Monitoring. Whatever can't be tapped
is simply missing; the reader keeps a slow heartbeat so nothing depends on taps existing.
Only event *kinds* and click positions are used; key contents are never read.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import Quartz

log = logging.getLogger("server.screen.events")

TriggerCallback = Callable[[str, dict], object]

INPUT_HELP = (
    "Click/typing triggers are off (no event-tap permission); the screen reader falls back to a "
    "periodic capture. Grant: System Settings > Privacy & Security > Accessibility (clicks) and "
    "Input Monitoring (typing pauses) for the app that runs the engine."
)

_MOUSE_DOWN = (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventRightMouseDown, Quartz.kCGEventOtherMouseDown)


def _mask(*types) -> int:
    m = 0
    for t in types:
        m |= Quartz.CGEventMaskBit(t)
    return m


class EventTriggers:
    def __init__(self, callback: TriggerCallback, pause_s: float = 1.0, scroll_s: float = 0.4,
                 app_poll_s: float = 0.3):
        self.callback = callback
        self.pause_s = pause_s
        self.scroll_s = scroll_s
        self.app_poll_s = app_poll_s
        self.mouse_tap = False
        self.key_tap = False
        self._last_key = 0.0
        self._last_scroll = 0.0
        self._key_pending = False
        self._scroll_pending = False
        self._front: str | None = None
        self._stop = threading.Event()
        self._taps: list = []
        self._runloop = None
        self.clicks: list[tuple[float, float, float]] = []   # (t, x, y), last 50

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> EventTriggers:
        ready = threading.Event()
        threading.Thread(target=self._tap_thread, args=(ready,), name="event-tap", daemon=True).start()
        ready.wait(2)
        threading.Thread(target=self._timer_thread, name="event-timers", daemon=True).start()
        if not (self.mouse_tap or self.key_tap):
            log.warning(INPUT_HELP)
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._runloop is not None:
            Quartz.CFRunLoopStop(self._runloop)

    @property
    def available(self) -> bool:
        return self.mouse_tap or self.key_tap

    # ------------------------------------------------------------------ tap

    def _fire(self, reason: str, info: dict | None = None) -> None:
        try:
            self.callback(reason, info or {})
        except Exception:
            log.exception("trigger callback failed")

    def _on_event(self, proxy, etype, event, refcon):
        try:
            if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
                for tap in self._taps:
                    Quartz.CGEventTapEnable(tap, True)
            elif etype in _MOUSE_DOWN:
                loc = Quartz.CGEventGetLocation(event)
                self.clicks = (self.clicks + [(time.time(), float(loc.x), float(loc.y))])[-50:]
                self._fire("click", {"x": float(loc.x), "y": float(loc.y),
                                     "button": {Quartz.kCGEventLeftMouseDown: "left",
                                                Quartz.kCGEventRightMouseDown: "right"}.get(etype, "other")})
            elif etype == Quartz.kCGEventScrollWheel:
                self._last_scroll, self._scroll_pending = time.time(), True
            elif etype == Quartz.kCGEventKeyDown:
                self._last_key, self._key_pending = time.time(), True
        except Exception:
            log.exception("event tap callback failed")
        return event

    def _make_tap(self, mask: int):
        return Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGTailAppendEventTap,
                                       Quartz.kCGEventTapOptionListenOnly, mask, self._on_event, None)

    def _tap_thread(self, ready: threading.Event) -> None:
        loop = Quartz.CFRunLoopGetCurrent()
        mouse = self._make_tap(_mask(*_MOUSE_DOWN, Quartz.kCGEventScrollWheel))
        keys = self._make_tap(_mask(Quartz.kCGEventKeyDown))
        for tap, name in ((mouse, "mouse_tap"), (keys, "key_tap")):
            if tap is None:
                continue
            setattr(self, name, True)
            self._taps.append(tap)
            src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            Quartz.CFRunLoopAddSource(loop, src, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(tap, True)
        self._runloop = loop
        ready.set()
        if not self._taps:
            return
        while not self._stop.is_set():
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.5, False)

    # ------------------------------------------------------------------ timers + app switch

    def _frontmost(self) -> str | None:
        infos = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID) or []
        for w in infos:
            if w.get("kCGWindowLayer", 0) == 0 and (w.get("kCGWindowBounds") or {}).get("Height", 0) > 40:
                return w.get("kCGWindowOwnerName")
        return None

    def _timer_thread(self) -> None:
        last_app_poll = 0.0
        while not self._stop.wait(0.1):
            now = time.time()
            if self._key_pending and now - self._last_key >= self.pause_s:
                self._key_pending = False
                self._fire("typing_pause", {})
            if self._scroll_pending and now - self._last_scroll >= self.scroll_s:
                self._scroll_pending = False
                self._fire("scroll_stop", {})
            if now - last_app_poll >= self.app_poll_s:
                last_app_poll = now
                try:
                    front = self._frontmost()
                except Exception:  # noqa: BLE001
                    front = None
                if front and front != self._front:
                    prev, self._front = self._front, front
                    if prev is not None:
                        self._fire("app_switch", {"from": prev, "to": front})

    def typing_recently(self, within_s: float = 2.0) -> bool:
        """For the don't-nag gate: a keystroke in the last `within_s` seconds."""
        return self.key_tap and time.time() - self._last_key < within_s
