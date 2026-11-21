"""WebSocket fan-out: every Engine->App event goes to every connected client."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections import deque
from typing import Any

from fastapi import WebSocket

from shared.contracts import events as _contract
from shared.contracts.events import validate_engine_payload

log = logging.getLogger("orchestrator.hub")

# v2 events (BUILD-PLAN W0-1). Until this tree's contract lists them they pass unvalidated, even under ORCH_STRICT=1
# (engine.hello goes to every app on connect), with one DEBUG line per type instead of a warning on every send.
V2_EVENTS = frozenset({"engine.hello", "health", "lesson.paused", "lesson.resumed", "blocker", "library", "library.item",
                       "progress"})
_KNOWN_EVENTS = frozenset(getattr(_contract, "ENGINE_EVENTS", {}))
PROGRESS_EVENTS = frozenset({"lesson.ready", "lesson.ended", "step.started", "check.updated", "lesson.complete"})
SEND_TIMEOUT_S = 5.0  # a client taking longer than this to accept a message is dropped, not waited on
QUIET_EVENTS = frozenset({"metric", "screen.seen"})  # several a second / OCR'd screen text: no line at all


def _clip(text: Any, n: int = 60) -> str:
    t = " ".join(str(text or "").split())
    return json.dumps(t[:n] + ("…" if len(t) > n else ""), ensure_ascii=False)


def log_received(type_: str, p: Any) -> None:
    """One INFO line per App->Engine command, the mirror of emit's '->' line: '<- action ask "why does divide…"'.
    A desktop test can then tell a press that never arrived from one that arrived and did nothing. config.keys is
    logged by name only (never a key); video.state / overlay.bounds (several a second) go to DEBUG."""
    if type_ == "action":
        line = f"action {p.kind}" + (f" {_clip(p.text)}" if p.text else "")
    elif type_ == "learn":
        line = f"learn {_clip(p.query)}" + (f" mode={p.mode}" if getattr(p, "mode", None) else "")
    elif type_ == "learn_url":
        line = f"learn_url {_clip(p.url, 120)}"
    elif type_ == "build_lesson":
        line = f"build_lesson {list(p.resultIds)[:5]}"
    elif type_ == "video.state":
        log.debug("<- video.state t=%s playing=%s", p.t, p.playing)
        return
    elif type_ == "overlay.bounds":
        log.debug("<- overlay.bounds %d rects", len(p.rects))
        return
    elif type_ in ("card.shown", "card.closed"):  # E14: what the learner really has on screen
        line = f"{type_} {p.kind or 'card'} {_clip(p.title)}" + (f" by={p.by}" if getattr(p, "by", None) else "")
    elif type_ == "permission.open":
        line = f"permission.open {getattr(p, 'kind', '?')}"
    elif type_ in ("library.get", "library.start"):  # the id matched ^[A-Za-z0-9_-]{1,64}$ before we got here
        line = f"{type_} {getattr(p, 'id', '?')}"
    elif type_ == "panel.state":  # follows every panel move: DEBUG
        log.debug("<- panel.state open=%s rect=%s", getattr(p, "open", None), "yes" if getattr(p, "rect", None) else "no")
        return
    elif type_ == "health.get":  # polled while onboarding / settings is open: DEBUG
        log.debug("<- health.get")
        return
    else:  # end_lesson, library.list, progress.get, config.keys / config.validate (name only)
        line = type_
    log.info("<- %s", line)


class Hub:
    def __init__(self, strict: bool | None = None, history: int = 500):
        self.clients: set[WebSocket] = set()
        self._close_tasks: set[asyncio.Task] = set()  # strong refs to in-flight ws.close() tasks
        self.strict = os.environ.get("ORCH_STRICT") == "1" if strict is None else strict
        self.history: deque[dict] = deque(maxlen=history)  # recent messages, for /events and tests
        self._pending_noted: set[str] = set()
        self.on_progress_event: Any = None  # called (sync) when a lesson starts, ends or a step is done

    def encode(self, type_: str, payload: dict) -> dict:
        if type_ in V2_EVENTS and type_ not in _KNOWN_EVENTS:
            if type_ not in self._pending_noted:
                self._pending_noted.add(type_)
                log.debug("event %s is not in this tree's events.py yet (W0-1); sent unvalidated", type_)
            return {"type": type_, "payload": payload}
        try:
            payload = validate_engine_payload(type_, payload)
        except Exception as e:
            if self.strict:
                raise
            log.warning("event %s does not match events.ts (%s); sending anyway", type_, e)
        return {"type": type_, "payload": payload}

    def join(self, ws: WebSocket) -> None:
        self.clients.add(ws)
        log.info("app connected (%d client%s)", len(self.clients), "" if len(self.clients) == 1 else "s")

    def drop(self, ws: WebSocket, why: str) -> None:
        """E14: a WebSocket close is logged (an off-track went out to a vanished app and nothing said so)."""
        if ws in self.clients:
            self.clients.discard(ws)
            log.info("app disconnected (%s); %d client%s left", why, len(self.clients), "" if len(self.clients) == 1 else "s")

    def _drop_and_close(self, ws: WebSocket, why: str) -> None:
        """A send timeout / error: a cancelled mid-frame send leaves the stream unusable, and merely forgetting the
        client left the receive loop (and the app's ping/pong heartbeat) alive on a socket that gets no events. Close
        it (1011) so the app sees the disconnect and reconnects for a fresh snapshot."""
        self.drop(ws, why)
        try:
            task = asyncio.get_running_loop().create_task(self._close_quietly(ws))
        except RuntimeError:
            return
        self._close_tasks.add(task)
        task.add_done_callback(self._close_tasks.discard)

    @staticmethod
    async def _close_quietly(ws: WebSocket) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(ws.close(code=1011), 2.0)

    async def emit(self, type_: str, payload: dict[str, Any] | None = None) -> None:
        msg = self.encode(type_, payload or {})
        self.history.append(msg)
        if type_ in PROGRESS_EVENTS and self.on_progress_event is not None:
            self.on_progress_event()  # the app's coalesced library / progress reads must not serve a stale answer
        if type_ not in QUIET_EVENTS:  # screen.seen carries OCR'd screen text: keep it out of logs
            # BUILD-PLAN section 6: payloads (learner code, card text, titles) only at DEBUG; INFO keeps the type, so a
            # desktop test still sees what went out and when
            if log.isEnabledFor(logging.DEBUG):
                log.debug("-> %s %s", type_, json.dumps(msg["payload"], ensure_ascii=False)[:200])
            else:
                log.info("-> %s", type_)
        clients = list(self.clients)
        if not clients:
            return
        # Concurrent sends, each capped: one stalled socket (backgrounded renderer, App Nap) used to block every
        # emitter (_status, the 1 s tick, check results) behind it with no limit. A client that cannot take a message
        # within SEND_TIMEOUT_S is dropped; the app reconnects and gets the snapshot.
        results = await asyncio.gather(*(self._send_capped(ws, msg) for ws in clients))
        for ws, e in zip(clients, results):
            if e is not None:
                self._drop_and_close(ws, f"send of {type_} failed: {type(e).__name__}")

    async def _send_capped(self, ws: WebSocket, msg: dict) -> BaseException | None:
        try:
            await asyncio.wait_for(ws.send_json(msg), SEND_TIMEOUT_S)
            return None
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - TimeoutError included
            return e

    async def send_to(self, ws: WebSocket, type_: str, payload: dict) -> None:
        await ws.send_json(self.encode(type_, payload))
