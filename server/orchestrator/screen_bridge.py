"""Optional bridge to server.screen (E6), the whole-screen reader.

Disabled (methods become no-ops) when server.screen isn't importable (Linux CI, before E6 merges),
when ORCH_SCREEN=0, or if the reader fails to start. The rest of the engine never imports
server.screen directly, so the hub always starts.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from .config import env_flag

log = logging.getLogger("orchestrator.screen")

MetricCb = Callable[[str, str, int, float], None]  # (run_id, name, step, value), called on the loop


class ScreenBridge:
    """Real bridge over server.screen.get_reader()."""

    def __init__(self, enabled: bool | None = None):
        self.enabled = env_flag("ORCH_SCREEN", True) if enabled is None else enabled
        self.reader: Any = None
        self._unsub: Callable[[], None] | None = None
        self._metrics: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.metric_run_id: str | None = None

    @property
    def active(self) -> bool:
        return self.reader is not None

    def start(self, on_obs: Callable[[Any], Awaitable[None]]) -> bool:
        if not self.enabled:
            return False
        try:
            mod = importlib.import_module("server.screen")
            reader = mod.get_reader()
            if reader is None:
                return False
            # ~1 frame/s (OCR still runs only when the screen changed) so a check flips within ~2 s
            reader.interval = float(os.environ.get("ORCH_SCREEN_INTERVAL_S", "1.0"))
            reader.start()
            self._loop = asyncio.get_running_loop()
            self._unsub = reader.subscribe(on_obs)
            self.reader = reader
            log.info("screen reader started")
            return True
        except Exception as e:  # noqa: BLE001 - permission / platform problems must not kill the hub
            log.warning("screen reader unavailable (%s); running without screen", e)
            self.reader = None
            return False

    def stop(self) -> None:
        try:
            if self._unsub:
                self._unsub()
            self.unwatch()
            if self.reader is not None and hasattr(self.reader, "stop"):
                self.reader.stop()
        except Exception:  # noqa: BLE001
            log.exception("screen stop failed")

    def down_reason(self) -> str | None:
        """Why the reader can't see the screen right now (E6: status error / no_permission), else None."""
        r = self.reader
        if r is None:
            return None
        try:
            status = getattr(r, "status", "ok")
        except Exception:  # noqa: BLE001
            return None
        if status not in ("error", "no_permission"):
            return None
        return "no_permission" if status == "no_permission" else str(getattr(r, "last_error", "") or "capture failed")

    # -- reads
    def latest(self) -> Any:
        return self.reader.latest() if self.reader is not None else None

    def lines(self, obs: Any = None) -> dict[str, list[str]] | None:
        obs = obs if obs is not None else self.latest()
        if obs is None:
            return None
        try:
            return obs.lines_by_app()
        except Exception:  # noqa: BLE001
            log.exception("lines_by_app failed")
            return None

    def locate(self, match: str, app: str | None = None) -> dict | None:
        """-> {rect:{x,y,w,h}, app, matched} or None."""
        if self.reader is None or not match or self.down_reason():
            return None  # capture is failing: a locate would block on a fresh capture for seconds (S1)
        try:
            res = self.reader.locate_match(match, app)
        except Exception:  # noqa: BLE001
            log.exception("locate failed")
            return None
        if res is None:
            return None
        out = {"rect": res.rect.to_dict()}
        if getattr(res, "app", None):
            out["app"] = res.app
        if getattr(res, "matched", None):
            out["matched"] = res.matched[:200]
        return out

    def region(self, name: str, app: str | None = None) -> dict | None:
        """E6: a VS Code region's rect {x, y, w, h} ("terminal" | "editor" | "explorer" | "run_button"), stabilized
        (4-pt grid, kept while edges move < 12 pt), or None when it isn't on screen."""
        if self.reader is None or self.down_reason() or not hasattr(self.reader, "locate_region"):
            return None
        try:
            r = self.reader.locate_region(name, app)
        except Exception:  # noqa: BLE001
            log.exception("locate_region failed")
            return None
        if r is None:
            return None
        d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        return {k: float(d[k]) for k in ("x", "y", "w", "h")}

    async def pick(self, intent: str, app: str | None = "Code") -> dict | None:
        """Haiku set-of-marks pick (server.screen.target): {rect, box_ids, label, confidence, reason, ...} or None
        (low confidence / nothing matches / timeout / budget / no key). Off with MIYAGI_VISION_TARGET=0."""
        if self.reader is None or self.down_reason() or not env_flag("MIYAGI_VISION_TARGET", True):
            return None
        try:
            from server.screen.target import pick_on_screen

            return await pick_on_screen(intent, app, reader=self.reader)
        except Exception:
            log.exception("vision pick failed")
            return None

    async def confirm(self, rect: dict, intent: str, app: str | None = "Code") -> dict | None:
        """Haiku verifier for a box the engine located itself (server.screen.target.verdict): -> the rect to show (the
        same box, or what Haiku picked instead) or None when Haiku is sure nothing on screen matches. Haiku off /
        unavailable / unsure: the box unchanged."""
        if self.reader is None or self.down_reason() or not env_flag("MIYAGI_VISION_TARGET", True):
            return rect
        try:
            from server.screen.target import confirm_on_screen

            out, why = await confirm_on_screen(rect, intent, app, reader=self.reader)
        except Exception:
            log.exception("vision confirm failed; keeping the box")
            return rect
        if why != "agree":
            log.info("targeter %s for %r", why, intent[:80])
        return out

    def set_overlay(self, rects: list[dict]) -> None:
        if self.reader is not None:
            self.reader.set_overlay_bounds(rects)

    def screenshot(self) -> Any:
        """A PIL image of the screen (overlay blacked out by E6), or None. Blocking (~20 ms): use a thread."""
        if self.reader is None or not hasattr(self.reader, "screenshot_pil"):
            return None
        try:
            return self.reader.screenshot_pil()
        except Exception:  # noqa: BLE001
            log.exception("screenshot failed")
            return None

    def poke(self) -> None:
        if self.reader is not None and hasattr(self.reader, "poke"):
            self.reader.poke()

    # -- metrics read off the terminal
    def watch(self, lesson_id: str, patterns: dict[str, str], on_metric: MetricCb) -> None:
        """(Re)start reading `patterns` off the screen. Callbacks arrive on the event loop."""
        self.unwatch()
        if self.reader is None or not patterns or self._loop is None:
            return
        loop = self._loop

        def cb(name: str, step: int, value: float) -> None:  # reader thread
            run_id = self._metrics.run_id if self._metrics is not None else f"screen-{lesson_id}"
            loop.call_soon_threadsafe(on_metric, run_id, name, step, value)

        try:
            self._metrics = self.reader.watch_metrics(lesson_id, patterns, cb)
        except Exception:  # noqa: BLE001
            log.exception("watch_metrics failed")
            self._metrics = None

    def unwatch(self) -> None:
        if self.reader is not None and self._metrics is not None:
            try:
                self.reader.unwatch_metrics(self._metrics)
            except Exception:  # noqa: BLE001
                log.exception("unwatch_metrics failed")
        self._metrics = None


class FakeScreen:
    """In-memory stand-in for tests and the autopilot: set `.text[app] = [...]` and `.rects`."""

    def __init__(self) -> None:
        self.text: dict[str, list[str]] = {}
        self.overlay: list[dict] = []
        self.watched: dict[str, str] = {}
        self.active = True
        self.down: str | None = None  # tests: what down_reason() reports

    def latest(self) -> Any:
        return self.text

    def lines(self, obs: Any = None) -> dict[str, list[str]] | None:
        return dict(self.text) if self.text else None

    def locate(self, match: str, app: str | None = None) -> dict | None:
        import re

        for a, lines in self.text.items():
            if app and app.lower() not in a.lower():
                continue
            for i, ln in enumerate(lines):
                try:
                    hit = re.search(match, ln) is not None
                except re.error:
                    hit = match in ln
                if hit:
                    return {"rect": {"x": 100.0, "y": 100.0 + 20 * i, "w": 400.0, "h": 20.0}, "app": a, "matched": ln}
        return None

    def set_overlay(self, rects: list[dict]) -> None:
        self.overlay = rects

    def down_reason(self) -> str | None:
        return self.down

    def region(self, name: str, app: str | None = None) -> dict | None:
        return getattr(self, "regions", {}).get(name)

    def screenshot(self) -> Any:
        return None

    def poke(self) -> None:
        pass

    def watch(self, lesson_id: str, patterns: dict[str, str], on_metric: MetricCb) -> None:
        self.watched = dict(patterns)

    def unwatch(self) -> None:
        self.watched = {}

    def stop(self) -> None:
        pass
