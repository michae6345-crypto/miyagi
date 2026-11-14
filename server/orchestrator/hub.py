"""WebSocket fan-out: every Engine->App event goes to every connected client."""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from typing import Any

from fastapi import WebSocket

from shared.contracts.events import validate_engine_payload



log = logging.getLogger("orchestrator.hub")


class Hub:
    def __init__(self, strict: bool | None = None, history: int = 500):
        self.clients: set[WebSocket] = set()
        self.strict = os.environ.get("ORCH_STRICT") == "1" if strict is None else strict
        self.history: deque[dict] = deque(maxlen=history)  # recent messages, for /events and tests

    def encode(self, type_: str, payload: dict) -> dict:
        try:
            payload = validate_engine_payload(type_, payload)
        except Exception as e:
            if self.strict:
                raise
            log.warning("event %s does not match events.ts (%s); sending anyway", type_, e)
        return {"type": type_, "payload": payload}

    async def emit(self, type_: str, payload: dict[str, Any] | None = None) -> None:
        msg = self.encode(type_, payload or {})
        self.history.append(msg)
        if type_ != "metric":
            log.info("-> %s %s", type_, json.dumps(msg["payload"], ensure_ascii=False)[:200])
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def send_to(self, ws: WebSocket, type_: str, payload: dict) -> None:
        await ws.send_json(self.encode(type_, payload))
