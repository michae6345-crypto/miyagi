"""Per-build counters of model calls, so speculative work (prebuilds) can log what it cost.

A build sets a fresh counter dict in its context; asyncio tasks it spawns inherit the same dict.
"""

from __future__ import annotations

import contextvars

_counter: contextvars.ContextVar = contextvars.ContextVar("lesson_cost", default=None)


def start() -> dict:
    c = {"gemini_calls": 0, "claude_calls": 0}
    _counter.set(c)
    return c


def count(kind: str) -> None:
    c = _counter.get()
    if c is not None:
        c[kind] = c.get(kind, 0) + 1
