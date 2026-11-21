"""WebSocket fan-out: every Engine->App event goes to every connected client."""

from __future__ import annotations

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
        self.strict = os.environ.get("ORCH_STRICT") == "1" if strict is None else strict
        self.history: deque[dict] = deque(maxlen=history)  # recent messages, for /events and tests
        self._pending_noted: set[str] = set()

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

    async def emit(self, type_: str, payload: dict[str, Any] | None = None) -> None:
        msg = self.encode(type_, payload or {})
        self.history.append(msg)
        if type_ not in QUIET_EVENTS:  # screen.seen carries OCR'd screen text: keep it out of logs
            # BUILD-PLAN section 6: payloads (learner code, card text, titles) only at DEBUG; INFO keeps the type, so a
            # desktop test still sees what went out and when
            if log.isEnabledFor(logging.DEBUG):
                log.debug("-> %s %s", type_, json.dumps(msg["payload"], ensure_ascii=False)[:200])
            else:
                log.info("-> %s", type_)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception as e:  # noqa: BLE001
                dead.append((ws, e))
        for ws, e in dead:
            self.drop(ws, f"send of {type_} failed: {type(e).__name__}")

    async def send_to(self, ws: WebSocket, type_: str, payload: dict) -> None:
        await ws.send_json(self.encode(type_, payload))
