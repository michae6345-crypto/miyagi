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


def current() -> dict | None:
    return _counter.get()


def add_tokens(model: str, input_tokens: int | None, output_tokens: int | None) -> None:
    """Accumulate token usage per model (output includes thinking where the API reports it so)."""
    c = _counter.get()
    if c is None:
        return
    t = c.setdefault("tokens", {}).setdefault(model, {"input": 0, "output": 0, "calls": 0})
    t["input"] += int(input_tokens or 0)
    t["output"] += int(output_tokens or 0)
    t["calls"] += 1


def count(kind: str) -> None:
    c = _counter.get()
    if c is not None:
        c[kind] = c.get(kind, 0) + 1
