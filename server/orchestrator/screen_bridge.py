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
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from . import bg, perf
from .config import env_flag

log = logging.getLogger("orchestrator.screen")

MetricCb = Callable[[str, str, int, float], None]  # (run_id, name, step, value), called on the loop
LOOP_REGION_MAX_AGE_S = 1e9  # on the event loop: any latest frame (the reader thread keeps it current)


class ScreenBridge:
    """Real bridge over server.screen.get_reader()."""

    def __init__(self, enabled: bool | None = None):
        self.enabled = env_flag("ORCH_SCREEN", True) if enabled is None else enabled
        self.reader: Any = None
        self._unsub: Callable[[], None] | None = None
        self._metrics: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.metric_run_id: str | None = None
        self._confirms = perf.ConfirmMemo()  # one Haiku verdict per (intent, box) for a few seconds, shared
        # E3: no lesson step running (idle, building, "Continue?" unanswered, no app connected): the reader stops
        # capturing; reads answer "nothing" (no stale frame, no targeter call) until resume()
        self.paused = False
        self._fresh_after = 0.0  # wall clock of the last resume(): frames older than that are from before the pause
        self._on_front: Callable[[str], Awaitable[None]] | None = None
        self._pause_lock = threading.Lock()
        # Nov 21 (launch-quiet): the reader is created at boot but never started until the first lesson step: no
        # capture, no Accessibility reader, no event taps, no frontmost poller (and so no permission prompt) before
        # the learner picks a lesson. resume() starts it the first time. ORCH_SCREEN_EAGER=1: the old boot start.
        self.started = False

    @property
    def active(self) -> bool:
        return self.reader is not None

    def start(self, on_obs: Callable[[Any], Awaitable[None]], loop: asyncio.AbstractEventLoop | None = None) -> bool:
        """`loop`: the engine's loop, when this runs in a worker thread (Engine.start does, so the port opens first)."""
        if not self.enabled:
            return False
        try:
            mod = importlib.import_module("server.screen")
            reader = mod.get_reader()
            if reader is None:
                return False
            # ~1 frame/s (OCR still runs only when the screen changed) so a check flips within ~2 s
            reader.interval = float(os.environ.get("ORCH_SCREEN_INTERVAL_S", "1.0"))
            eager = env_flag("ORCH_SCREEN_EAGER", False)  # dev escape hatch: capture from boot, as before Nov 21
            if eager:
                reader.start()
            self._loop = loop or asyncio.get_running_loop()
            self._unsub = reader.subscribe(on_obs)
            self.reader = reader
            self.started = eager
            self.paused = not eager  # launch-quiet: resume() (the first lesson step) starts it
            log.info("screen reader %s", "started" if eager else "ready (starts with the first lesson step)")
            return True
        except Exception as e:  # noqa: BLE001 - permission / platform problems must not kill the hub
            log.warning("screen reader unavailable (%s); running without screen", e)
            self.reader = None
            return False

    def stop(self) -> None:
        try:
            if self._unsub:
                self._unsub()
            if getattr(self, "_front_unsub", None):
                self._front_unsub()
            self.unwatch()
            if self.reader is not None and hasattr(self.reader, "stop"):
                self.reader.stop()
        except Exception:  # noqa: BLE001
            log.exception("screen stop failed")

    def pause(self, why: str = "") -> None:
        """Stop capturing the screen while no lesson step runs (E3: after a lesson ended the reader went on OCR'ing
        every second and /state served the text under the pointer). Stops the capture thread, the Accessibility
        reader, the event taps and the frontmost poller; resume() starts them again. Blocking (joins the capture
        thread): call it in a thread."""
        r = self.reader
        if r is None or self.paused:
            return
        self.paused = True  # reads answer "nothing" from now on, before the thread has even stopped
        with self._pause_lock:
            try:  # metric watchers stay (they're only fed by captures): a resumed step reads its terminal again
                if getattr(self, "_front_unsub", None):
                    self._front_unsub()
                    self._front_unsub = None
                if hasattr(r, "stop"):
                    r.stop()
            except Exception:  # noqa: BLE001
                log.exception("screen pause failed")
        log.info("screen reader paused (%s)", why or "no lesson step")

    def resume(self, why: str = "") -> None:
        """Capture again (a lesson step started / Continue / the app reconnected). Blocking (~0.1-2 s): a thread."""
        r = self.reader
        if r is None or not self.paused:
            return
        with self._pause_lock:
            if not self.paused:  # another resume() got here first
                return
            self._fresh_after = time.time()
            if not self.started:  # launch-quiet: the first lesson step starts the reader (taps, AX, capture) once
                try:
                    r.start()
                    self.started = True
                except Exception:  # noqa: BLE001
                    log.exception("screen start failed")
                    return  # stays paused: the next step / tick tries again
                self.paused = False
                if self._on_front is not None:
                    self.watch_frontmost(self._on_front)
                log.info("screen reader started (%s)", why or "lesson step")
                return
            try:
                ax = getattr(r, "ax_reader", None)
                for t in (getattr(r, "_thread", None), getattr(ax, "_thread", None)):
                    if t is not None and t.is_alive():  # a capture / AX read outlived stop()'s join: start() would
                        t.join(timeout=10)  # return early with the stop flag still set, and the reader would die
                if getattr(r, "events", None) is not None:
                    r.events = None  # event taps can't be restarted once stopped: the reader makes new ones
                r.start()
                stop = getattr(r, "_stop", None)
                if stop is not None and stop.is_set():  # still stopping: stay paused, the next tick tries again
                    log.warning("screen reader still stopping; resume retried (%s)", why or "lesson step")
                    return
                if ax is not None and hasattr(ax, "start"):
                    ax.start()  # the AX reader restarts in place (its change listeners are kept)
            except Exception:  # noqa: BLE001
                log.exception("screen resume failed")
            if not getattr(r, "thread_alive", True):  # start() raised or the thread died: stay paused (retried next tick)
                log.warning("screen reader did not start on resume (%s); staying paused", why or "lesson step")
                return
            self.paused = False
            if self._on_front is not None:
                self.watch_frontmost(self._on_front)
        log.info("screen reader resumed (%s)", why or "lesson step")

    def watch_frontmost(self, on_front: Callable[[str], Awaitable[None]]) -> None:
        """E6 on_frontmost_change: `on_front(app_name)` on the loop within ~0.25 s of an app switch / Space swipe."""
        r = self.reader
        self._on_front = on_front  # re-subscribed by resume()
        if r is None or self._loop is None or not hasattr(r, "on_frontmost_change"):
            return
        if self.paused:  # launch-quiet / paused: no poller until a lesson step resumes the reader
            return
        if getattr(self, "_front_unsub", None):  # never two subscriptions for one watcher
            self._front_unsub()
            self._front_unsub = None
        loop = self._loop

        def cb(new: dict | None, old: dict | None) -> None:  # E6's poller thread
            app = str((new or {}).get("app") or "")
            loop.call_soon_threadsafe(lambda: bg.spawn(on_front(app)))  # held until done (V13)

        try:
            self._front_unsub = r.on_frontmost_change(cb)
        except Exception:  # noqa: BLE001
            log.exception("on_frontmost_change failed")

    def down_reason(self, include_ax: bool = True) -> str | None:
        """Why the reader can't see the screen right now (E6: status error / no_permission), else None.

        With include_ax, a revoked Accessibility grant reads "no_accessibility" once capture itself is fine. It is a
        report-only reason: OCR keeps working without AX, so the gates below ask with include_ax=False."""
        r = self.reader
        if r is None:
            return None
        try:
            status = getattr(r, "status", "ok")
        except Exception:  # noqa: BLE001
            return None
        if not self.paused and not getattr(r, "thread_alive", True):
            return "capture thread stopped"  # a dead reader serves its last frame forever: say so, don't look fine
        if status in ("error", "no_permission"):
            return "no_permission" if status == "no_permission" else str(getattr(r, "last_error", "") or "capture failed")
        if include_ax and getattr(r, "ax_trusted", None) is False:
            return "no_accessibility"
        return None

    def _capture_down(self) -> str | None:
        return self.down_reason(include_ax=False)

    # -- reads
    def latest(self) -> Any:
        if self.reader is None or self.paused:
            return None
        obs = self.reader.latest()
        if obs is not None and self._fresh_after and float(getattr(obs, "t", 0) or 0) < self._fresh_after:
            return None  # captured before the last pause: not what's on screen now
        return obs

    def lines(self, obs: Any = None) -> dict[str, list[str]] | None:
        obs = obs if obs is not None else self.latest()
        if obs is None:
            return None
        try:
            return obs.lines_by_app()
        except Exception:  # noqa: BLE001
            log.exception("lines_by_app failed")
            return None

    def fresh(self, max_age: float = 1.0) -> Any:
        """t10: the latest frame when it is at most max_age s old, else a new capture + OCR (blocking: call it in a
        thread), so locate() / snap_rows() read what is on screen now. None: paused / capture failing / no reader."""
        if self.reader is None or self.paused or self._capture_down():
            return None
        try:
            fn = getattr(self.reader, "_fresh_obs", None)
            return fn(max_age) if fn is not None else self.reader.observe_now(force=True)
        except Exception:  # noqa: BLE001
            log.exception("fresh read failed")
            return None

    def locate(self, match: str, app: str | None = None) -> dict | None:
        """-> {rect:{x,y,w,h}, app, matched} or None."""
        if self.reader is None or self.paused or not match or self._capture_down():
            return None  # capture is failing: a locate would block on a fresh capture for seconds (S1)
        try:
            fn = getattr(self.reader, "locate_match_cached", None) if perf.on_loop() else None
            # the event loop: the latest frame only (a cold start's capture + OCR here blocked every event 1.5-7 s)
            res = fn(match, app) if fn is not None else self.reader.locate_match(match, app)
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

    def snap_rows(self, rect: dict, app: str | None = None) -> dict | None:
        """t8: a text match's box {x, y, w, h} with the y / height of its editor rows (the full-line box's: the
        tight "Look here" box sat 3.4 pt low and cut the next line), x / width kept. None: not on an editor's rows."""
        fn = getattr(self.reader, "snap_rows", None) if self.reader is not None and not self.paused else None
        if fn is None:
            return None
        try:
            from server.screen.types import Rect

            r = fn(Rect(float(rect["x"]), float(rect["y"]), float(rect["w"]), float(rect["h"])), app)
        except Exception:  # noqa: BLE001 - the match's own box stands
            log.exception("snap_rows failed")
            return None
        return {k: float(v) for k, v in r.to_dict().items() if k in ("x", "y", "w", "h")} if r is not None else None

    def region(self, name: str, app: str | None = None) -> dict | None:
        """E6: a VS Code region's rect {x, y, w, h} ("terminal" | "editor" | "explorer" | "run_button"), stabilized
        (4-pt grid, kept while edges move < 12 pt), or None when it isn't on screen."""
        if self.reader is None or self.paused or self._capture_down() or not hasattr(self.reader, "locate_region"):
            return None
        try:
            if perf.on_loop():  # the event loop: the latest frame's region, never a blocking capture + OCR (~0.2-0.5 s
                # each, once a second on a still screen: _screen_lines -> terminal region from every tick / evaluate)
                if self.reader.latest() is None:
                    return None
                try:
                    r = self.reader.locate_region(name, app, max_age=LOOP_REGION_MAX_AGE_S)
                except TypeError:  # a reader without max_age
                    r = self.reader.locate_region(name, app)
            else:
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
        if self.reader is None or self.paused or self._capture_down() or not env_flag("MIYAGI_VISION_TARGET", True):
            return None  # paused: no lesson step / no app to show a box to, so no Haiku call either (E7)
        try:
            from server.screen.target import pick_on_screen

            return await pick_on_screen(intent, app, reader=self.reader)
        except Exception:
            log.exception("vision pick failed")
            return None

    # E6: Haiku answered but couldn't vouch for the box (unsure, "nothing" said without conviction, a garbled answer, no
    # candidates for the app): the box only stands inside the lesson's editor pane (the engine's own line match there).
    UNSURE = frozenset({"kept:low_confidence", "kept:none", "kept:error", "kept:no_candidates"})

    async def confirm(self, rect: dict, intent: str, app: str | None = "Code", pane: dict | None = None,
                      move_conf: float | None = None) -> dict | None:
        """Haiku verifier for a box the engine located itself (server.screen.target.verdict): -> the rect to show (the
        same box, or what Haiku picked instead) or None when Haiku is sure nothing on screen matches, or (E6) is unsure
        and the box isn't inside the lesson's editor pane (`pane`, else E6's "editor" region of the latest frame).
        Haiku off / unavailable (no key, timeout, budget): the box unchanged. move_conf (t5): a box the engine took
        from the file moves only on a pick at least this sure."""
        mc = {"move_conf": move_conf} if move_conf is not None else {}
        if self.reader is None or self._capture_down() or not env_flag("MIYAGI_VISION_TARGET", True):
            return rect
        if self.paused:  # E7: no lesson step / no app: no Haiku call (no box goes out anyway)
            return rect
        async def ask() -> tuple[dict | None, str]:
            try:
                from server.screen.target import confirm_on_screen

                out, why = await confirm_on_screen(rect, intent, app, reader=self.reader, **mc)
            except Exception:
                log.exception("vision confirm failed; keeping the box")
                return rect, "kept:exception"
            if why != "agree":
                log.info("targeter %s for %r", why, intent[:80])
            return out, why

        # the same box + intent from several callers within a second (frame follow, step start, Check) or again a
        # few seconds later: one Haiku call, not three (live: 3 calls in 1 s, then the 6/min budget skipped real ones)
        out, why = await self._confirms.get(intent + (f"\x00move>={move_conf}" if mc else ""), app, rect, ask)
        if why in self.UNSURE:
            pane = pane if pane is not None else self.region("editor", app)
            cx, cy = float(rect["x"]) + float(rect["w"]) / 2, float(rect["y"]) + float(rect["h"]) / 2
            if pane is None or not (pane["x"] - 4 <= cx <= pane["x"] + pane["w"] + 4
                                    and pane["y"] - 4 <= cy <= pane["y"] + pane["h"] + 4):
                log.info("targeter %s and the box isn't in the lesson's editor pane: no box for %r", why, intent[:80])
                return None
        if why == "agree" or why.startswith("kept"):
            return rect  # this caller's own box (a shared verdict may come from a box a few points off)
        return dict(out) if isinstance(out, dict) else out

    def set_overlay(self, rects: list[dict]) -> None:
        if self.reader is not None:
            self.reader.set_overlay_bounds(rects)

    UI_TEXT_KEYS = frozenset({"title", "body", "caption", "instructions", "what", "why", "label", "detail", "action",
                              "reason", "message"})

    def note_ui(self, type_: str, payload: dict | None) -> None:
        """Every Engine->App event: the prose Miyagi puts on screen (card title / body, captions, step lines, check
        labels; never code or snippets) goes to the Haiku targeter, which then never boxes our own overlay's text even
        when overlay.bounds misses it (server.screen.target.note_ui_text)."""
        if self.reader is None or not payload or type_ in ("metric", "screen.seen", "video.state"):
            return
        texts: list[str] = []

        def walk(v: Any, depth: int) -> None:
            if isinstance(v, dict) and depth < 4:
                for k, x in v.items():
                    if isinstance(x, str) and k in self.UI_TEXT_KEYS:
                        texts.append(x)
                    elif isinstance(x, (dict, list)):
                        walk(x, depth + 1)
            elif isinstance(v, list) and depth < 4:
                for x in v[:50]:
                    walk(x, depth + 1)

        walk(payload, 0)
        if not texts:
            return
        try:
            from server.screen.target import note_ui_text

            note_ui_text(texts[:200])
        except Exception:  # noqa: BLE001 - never let this break an emit
            log.debug("note_ui failed", exc_info=True)

    def screenshot(self) -> Any:
        """A PIL image of the screen (overlay blacked out by E6), or None. Blocking (~20 ms): use a thread."""
        if self.reader is None or self.paused or not hasattr(self.reader, "screenshot_pil"):
            return None
        try:
            return self.reader.screenshot_pil()
        except Exception:  # noqa: BLE001
            log.exception("screenshot failed")
            return None

    def poke(self) -> None:
        if self.reader is not None and hasattr(self.reader, "poke"):
            self.reader.poke()

    async def fresh_frame(self, timeout: float) -> bool:
        """A frame captured now (Check: "not one from before their last keystroke"). Was poke + a flat 1.2 s sleep, and
        the poked capture itself waits out the reader's 1.5 s debounce; this captures + OCRs at once in a thread
        (~0.3-0.5 s, no model call), never longer than `timeout`. -> True when the fresh frame is in."""
        r = self.reader
        if r is None or self.paused:
            return False
        if not hasattr(r, "observe_now") or self._capture_down():
            if hasattr(r, "poke"):
                r.poke()
            await asyncio.sleep(timeout)
            return False
        job = asyncio.ensure_future(asyncio.to_thread(r.observe_now, True, "check"))
        try:
            await asyncio.wait_for(asyncio.shield(job), timeout)
            return True
        except Exception as e:  # noqa: BLE001 - slow / failing capture: go on with the latest frame, as before
            job.add_done_callback(lambda t: t.cancelled() or t.exception())
            log.info("check: no fresh frame within %.1fs (%s)", timeout, type(e).__name__)
            return False

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
        self.ax_down = False          # tests: Accessibility revoked
        self.paused = False  # tests: what the session asked for (pause / resume); reads are unchanged

    def pause(self, why: str = "") -> None:
        self.paused = True

    def resume(self, why: str = "") -> None:
        self.paused = False

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

    def down_reason(self, include_ax: bool = True) -> str | None:
        return self.down or ("no_accessibility" if include_ax and self.ax_down else None)

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
