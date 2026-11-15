"""Small latency helpers for the engine (live3-perf). Kept out of session.py so other branches merge cleanly.

* `until_loaded`: a lesson build holds the learner's command queue only until the lesson is live, not until its
  last step is written (live log 11-15: Install waited 27 s and Diagram 10 s behind "Just teach me"'s build).
* `ConfirmMemo`: one Haiku targeter verdict per (intent, box) for a few seconds; concurrent asks share one call
  (live log: three identical confirms within 1 s, then "budget of 6 calls/min reached" for the next real box).
* `on_loop`: is this the asyncio event loop's thread (never block it on a capture + OCR there)?
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

log = logging.getLogger("orchestrator.perf")


def on_loop() -> bool:
    """True on a thread running an asyncio loop (the engine's): blocking work there freezes every event."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _log_failure(t: asyncio.Future) -> None:
    if not t.cancelled() and (e := t.exception()) is not None:
        log.error("background lesson build failed", exc_info=e)


async def until_loaded(task: asyncio.Future, loaded: asyncio.Event) -> bool:
    """Wait for `task` or `loaded`, whichever comes first. -> True when the task finished (its result/exception is
    the caller's to read); False when `loaded` fired first: the task runs on, detached (a failure is logged, never
    lost; cancel_build still stops it). Cancelled while waiting (app gone / shutdown): the task is cancelled too,
    exactly as a plain `await task` did."""
    waiter = asyncio.ensure_future(loaded.wait())
    try:
        await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        task.cancel()
        raise
    finally:
        waiter.cancel()
    if task.done():
        return True
    task.add_done_callback(_log_failure)
    return False


class ConfirmMemo:
    """Share and briefly remember one async verdict per (intent, app, rect within `slop` points)."""

    def __init__(self, ttl: float = 8.0, slop: float = 12.0, size: int = 16) -> None:
        self.ttl, self.slop, self.size = ttl, slop, size
        self._items: list[tuple[float, str, str, dict, asyncio.Future]] = []

    def _find(self, intent: str, app: str, rect: dict, now: float) -> asyncio.Future | None:
        self._items = [it for it in self._items if now - it[0] <= self.ttl or not it[4].done()]
        for _t, i, a, r, fut in reversed(self._items):
            if i == intent and a == app and all(abs(float(r[k]) - float(rect[k])) <= self.slop
                                                for k in ("x", "y", "w", "h")):
                return fut
        return None

    async def get(self, intent: str, app: str | None, rect: dict, ask: Callable[[], Awaitable[Any]]) -> Any:
        now, app = time.monotonic(), app or ""
        fut = self._find(intent, app, rect, now)
        if fut is None:
            fut = asyncio.ensure_future(ask())
            self._items = (self._items + [(now, intent, app, dict(rect), fut)])[-self.size:]
        out = await asyncio.shield(fut)
        return dict(out) if isinstance(out, dict) else out
