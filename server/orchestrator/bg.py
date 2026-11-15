"""Strong references for fire-and-forget asyncio tasks.

The event loop only keeps weak references to tasks: a pending task that nothing else holds can be garbage-collected
mid-flight ("Task was destroyed but it is pending!", V13). `spawn` / `keep` hold each task in a set until it ends."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

log = logging.getLogger(__name__)

_LIVE: set[asyncio.Future] = set()


def _done(t: asyncio.Future) -> None:
    _LIVE.discard(t)
    if not t.cancelled() and (e := t.exception()) is not None:
        log.error("background task failed", exc_info=e)


def keep(t: asyncio.Future) -> asyncio.Future:
    """Hold `t` until it is done (a failure is logged, never lost)."""
    if not t.done():
        _LIVE.add(t)
        t.add_done_callback(_done)
    return t


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Future:
    """asyncio.ensure_future(coro), held until it ends."""
    return keep(asyncio.ensure_future(coro))
