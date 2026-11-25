"""Ambient help, part 1: explain this error (AMBIENT-HELP.md). The engine side of ambient.set, error.seen,
error.explain -> error.explanation and error.dismiss. Spotting and parsing live in server/ambient_errors.

  ambient.set {errors, mutedApps}  per connection; the engine starts with it off. While any connection has it on
                                   and no lesson runs, the screen reader runs (session._sync_screen_soon asks
                                   wants_screen) and its frames come here instead of to the lesson (on_obs)
  error.seen                       to every connection with errors on (hub.send_to: never in /events history, never
                                   logged); none while a lesson runs (a lesson start clears the shown peeks)
  error.explain {id, reqId}        {id, pending} at once, then the explanation: from memory when this id was explained
                                   already, from this Mac when it knows (a curated package that isn't installed), else
                                   one Haiku call counted against server.ambient_cap (shared with help.ask); the cap
                                   full -> {error: "cap", retryInS}; an id no longer held -> {error: "gone"}
  error.dismiss {id}               forget it (lines, explanation); it stays quiet until it goes and comes back

Nothing about an error is written to disk or to the logs (ids and kinds only).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from server import ambient_cap
from server.ambient_errors import explain as explainer
from server.ambient_errors.watcher import ErrorWatcher, apps_on_screen, scan

log = logging.getLogger("orchestrator.ambient")

COMMANDS = ("ambient.set", "error.explain", "error.dismiss")
LESSON_PHASES = frozenset({"building", "preflight", "active"})
Reply = Callable[[str, dict], Awaitable[None]]


class AmbientErrors:
    def __init__(self, hub: Any, session: Any, watcher: ErrorWatcher | None = None) -> None:
        self.hub = hub
        self.session = session
        self.watcher = watcher or ErrorWatcher()
        self.conns: dict[Any, dict] = {}  # ws -> {"errors": bool, "muted": [app, ...]}
        self._inflight: dict[str, asyncio.Future] = {}
        self._was_lesson = False

    # ------------------------------------------------------------------ state
    def errors_on(self) -> bool:
        return any(c.get("errors") for c in self.conns.values())

    def muted(self) -> list[str]:
        out: list[str] = []
        for c in self.conns.values():
            out += [m for m in c.get("muted") or [] if m not in out]
        return out

    def lesson_running(self) -> bool:
        return getattr(self.session, "phase", "idle") in LESSON_PHASES

    def wants_screen(self) -> bool:
        """The screen reader should run for spotting errors: on for a connection, and no lesson runs."""
        return self.errors_on() and not self.lesson_running()

    # ------------------------------------------------------------------ commands
    async def handle(self, type_: str, p: Any, ws: Any, reply: Reply) -> None:
        if type_ == "ambient.set":
            await self.set(ws, getattr(p, "errors", None), getattr(p, "mutedApps", None))
        elif type_ == "error.dismiss":
            self.watcher.dismiss(p.id)
            self._inflight.pop(p.id, None)
        elif type_ == "error.explain":
            await self.explain(p.id, getattr(p, "reqId", None), reply)

    async def set(self, ws: Any, errors: bool | None, muted: list[str] | None) -> None:
        conf = self.conns.setdefault(ws, {"errors": False, "muted": []})
        if errors is not None:
            conf["errors"] = bool(errors)
        if muted is not None:
            conf["muted"] = [str(m) for m in muted if isinstance(m, str) and m.strip()][:50]
        log.info("ambient: spot errors %s (%d muted app%s)", "on" if conf["errors"] else "off", len(conf["muted"]),
                 "" if len(conf["muted"]) == 1 else "s")
        if not self.errors_on():
            self.watcher.forget_all()  # off everywhere: nothing is kept
        self._sync_screen()

    def drop(self, ws: Any) -> None:
        """A connection closed."""
        if self.conns.pop(ws, None) is not None and not self.errors_on():
            self.watcher.forget_all()
            self._sync_screen()

    def _sync_screen(self) -> None:
        sync = getattr(self.session, "_sync_screen_soon", None)
        if sync is not None:
            try:
                sync()
            except Exception:  # noqa: BLE001 - the next tick tries again
                log.exception("ambient: screen sync failed")

    async def explain(self, eid: str, req_id: str | None, reply: Reply) -> None:
        def tagged(payload: dict) -> dict:
            return {**payload, **({"reqId": req_id} if req_id else {})}

        held = self.watcher.get(eid)
        if held is None:
            await reply("error.explanation", tagged({"id": eid, "error": "gone"}))
            return
        if held.explanation is not None:  # the same id again: from memory, no call
            await reply("error.explanation", tagged(held.explanation))
            return
        await reply("error.explanation", tagged({"id": eid, "pending": True}))
        fut = self._inflight.get(eid)
        if fut is None:
            fut = asyncio.ensure_future(self._answer(held))
            self._inflight[eid] = fut
            fut.add_done_callback(lambda _f, k=eid: self._inflight.pop(k, None) if self._inflight.get(k) is _f else None)
        try:
            out = await asyncio.shield(fut)
        except Exception:  # noqa: BLE001
            log.exception("ambient: explain failed")
            out = {"id": eid, "error": "failed"}
        await reply("error.explanation", tagged(out))

    async def _answer(self, held: Any) -> dict:
        out = explainer.local_answer(held)
        if out is None:
            cap = ambient_cap.shared_cap()
            wait = await asyncio.to_thread(cap.take)
            if wait is not None:
                log.info("ambient: explain %s capped (%d s)", held.id, wait)
                return {"id": held.id, "error": "cap", "retryInS": int(wait)}
            out = await explainer.explain(held)
            if out.get("error") == "offline":  # never reached a model: it does not count
                await asyncio.to_thread(cap.refund)
        if not out.get("error") and self.watcher.get(held.id) is held:
            held.explanation = out  # kept with the error: gone with it (dismiss, clear, 10 min)
        return out

    # ------------------------------------------------------------------ frames and ticks
    async def on_obs(self, obs: Any) -> None:
        if not self.wants_screen() or obs is None:
            return
        try:
            events = self.watcher.frame(scan(obs, self.muted()), apps_on_screen(obs))
        except Exception:  # noqa: BLE001 - a frame the parser can't read is skipped
            log.exception("ambient: frame failed")
            return
        await self._send(events)

    async def tick(self) -> None:
        lesson = self.lesson_running()
        if lesson and not self._was_lesson:  # a lesson started: its own off-track card covers errors
            await self._send(self.watcher.forget_all())
        self._was_lesson = lesson
        if self.wants_screen():
            await self._send(self.watcher.tick())

    async def _send(self, events: list[tuple[str, dict]]) -> None:
        if not events:
            return
        targets = [ws for ws, c in self.conns.items() if c.get("errors") and ws is not None]
        for type_, payload in events:
            log.info("ambient: %s %s%s", type_, payload.get("id"), " clear" if payload.get("clear") else
                     f" {payload.get('kind')}")
            for ws in targets:
                try:
                    await self.hub.send_to(ws, type_, payload)
                except Exception:  # noqa: BLE001 - that app left; ws_endpoint drops it
                    log.info("ambient: send of %s failed", type_)
