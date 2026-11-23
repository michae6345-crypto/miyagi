"""What model calls cost: tokens and dollars per model, per build and per session.

Per build: a build sets a fresh counter dict in its context (`start()`); asyncio tasks it spawns inherit
the same dict. `add_tokens` / `record_usage` add to it, so `build.cost` in a graph carries calls, tokens
per model, `cost_usd` and `cache_hit_rate`.

Per session: every recorded call also lands in one process-wide session tally, by source: lesson (the
learner's build), prebuild (speculative builds), coach (coach calls, screen looks, warm-up), screen (describe,
target picks), diagrams, workspace (starter files, requirements), finder and preflight. A build that failed or
was cancelled moves to "<source>_failed" / "<source>_cancelled". `session_start(lesson_id)` names it when a lesson loads (the build that made the lesson is
already in it); `session_end(reason)` logs it, emits `session_cost` and starts a fresh tally.

Prices are USD per 1M tokens, an estimate for logs and telemetry, never billing. Anthropic rows match the
published rates; Gemini rows are placeholders that match the miyagi cloud's table (cloud/app.py). Override
or add rows with MIYAGI_PRICES_JSON='{"model": [input, output, cache_read]}' (cache_read optional).

Event hook: `emit_event(name, props)` calls whatever `register_event_handler` registered (the telemetry
lane); with nothing registered it does nothing. A handler that raises is logged and never breaks a call.
Events: `build_cost` {kind, outcome, cost_usd, calls, tokens, cache_hit_rate[, lesson_id]}, `session_cost` {lesson_id,
reason, cost_usd, calls, cache_hit_rate, by_model, by_source}.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import os
import threading
from typing import Any, Callable

log = logging.getLogger("server.lesson.cost")

_counter: contextvars.ContextVar = contextvars.ContextVar("lesson_cost", default=None)

# ---------------------------------------------------------------------------------------------- prices

# (input, output, cache_read) USD per 1M tokens. Cache writes bill at CACHE_WRITE_X times input (5 min TTL).
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "gemini-3.8-flash": (0.30, 2.50, 0.03),
    "gemini-4-hydrogen": (1.25, 10.00, 0.125),
}
# a model id not in PRICES is priced by the first family it names (most specific first)
FAMILY_PRICES: list[tuple[str, tuple[float, float, float]]] = [
    ("opus", PRICES["claude-opus-5-5"]),
    ("fable", (8.00, 40.00, 0.20)),
    ("mythos", (8.00, 40.00, 0.20)),
    ("sonnet", PRICES["claude-sonnet-5-5"]),
    ("haiku", PRICES["claude-haiku-5-5"]),
    ("flash-lite", (0.10, 0.40, 0.01)),
    ("flash", PRICES["gemini-3.8-flash"]),
    ("gemini", PRICES["gemini-4-hydrogen"]),
]
DEFAULT_PRICE = (2.00, 10.00, 0.20)
CACHE_WRITE_X = 1.25
WEB_SEARCH_USD = 0.01  # Anthropic's server-side web_search tool: $10 per 1,000 searches, on top of tokens


_overrides_memo: tuple[str, dict[str, tuple[float, float, float]]] = ("", {})


def _overrides() -> dict[str, tuple[float, float, float]]:
    """MIYAGI_PRICES_JSON rows, model ids lowercased (price() lowercases too). Parsed once per distinct value."""
    global _overrides_memo
    raw = os.environ.get("MIYAGI_PRICES_JSON") or ""
    if not raw:
        return {}
    if raw == _overrides_memo[0]:
        return _overrides_memo[1]
    out: dict[str, tuple[float, float, float]] = {}
    try:
        for k, v in json.loads(raw).items():
            v = [float(x) for x in v]
            out[str(k).strip().lower()] = (v[0], v[1], v[2] if len(v) > 2 else v[0] * 0.1)
    except (ValueError, TypeError, AttributeError, IndexError):
        log.warning("MIYAGI_PRICES_JSON is not {model: [input, output, cache_read]}; ignored")
        out = {}
    _overrides_memo = (raw, out)
    return out


def price(model: str | None) -> tuple[float, float, float]:
    """(input, output, cache_read) USD per 1M tokens for `model`: exact row, else its family, else a default."""
    m = (model or "").strip().lower()
    table = {**PRICES, **_overrides()}
    if m in table:
        return table[m]
    for key in sorted(table, key=len, reverse=True):  # a dated id (claude-haiku-5-5-20261001) -> its base row
        if m.startswith(key):
            return table[key]
    for fam, p in FAMILY_PRICES:
        if fam in m:
            return p
    return DEFAULT_PRICE


def usd(model: str | None, input_tokens: int = 0, output_tokens: int = 0, cache_read: int = 0, cache_write: int = 0) -> float:
    """Dollars for one call. `input_tokens` is the uncached input only (Anthropic's `usage.input_tokens`)."""
    pin, pout, pread = price(model)
    return (int(input_tokens or 0) * pin + int(output_tokens or 0) * pout + int(cache_read or 0) * pread
            + int(cache_write or 0) * pin * CACHE_WRITE_X) / 1_000_000


def cache_saved_usd(model: str | None, cache_read: int = 0, cache_write: int = 0) -> float:
    """Dollars the cache saved on one call against sending the same tokens uncached: reads cost 0.1x input instead
    of 1x; writes cost 1.25x, so a write is a small loss (negative) the later reads must repay."""
    pin, _, pread = price(model)
    return (int(cache_read or 0) * (pin - pread) - int(cache_write or 0) * pin * (CACHE_WRITE_X - 1)) / 1_000_000


def hit_rate(input_tokens: int, cache_read: int, cache_write: int) -> float | None:
    """Share of prompt tokens served from the cache, or None when nothing was sent."""
    total = int(input_tokens or 0) + int(cache_read or 0) + int(cache_write or 0)
    return round(int(cache_read or 0) / total, 4) if total else None


# ---------------------------------------------------------------------------------------------- event hook

_handlers: list[Callable[[str, dict], Any]] = []


def register_event_handler(fn: Callable[[str, dict], Any]) -> Callable[[], None]:
    """Send every cost event to `fn(name, props)`. Returns a function that unregisters it."""
    _handlers.append(fn)

    def off() -> None:
        if fn in _handlers:
            _handlers.remove(fn)
    return off


def emit_event(name: str, props: dict | None = None) -> None:
    """Hand an event to the registered handlers; a no-op when none is registered. Never raises."""
    for fn in list(_handlers):
        try:
            fn(name, dict(props or {}))
        except Exception:  # noqa: BLE001 - telemetry must never break a model call
            log.exception("cost event handler failed for %s", name)


# ---------------------------------------------------------------------------------------------- per build

def start(source: str = "lesson") -> dict:
    """A fresh build counter in this context. `source` tags its calls in the session tally's `by_source`
    ("lesson" for the learner's own build, "prebuild" for a speculative one)."""
    c = {"gemini_calls": 0, "claude_calls": 0, "cost_usd": 0.0, "source": source}
    _counter.set(c)
    return c


def current() -> dict | None:
    return _counter.get()


def _add(bucket: dict, model: str, inp: int, out: int, cr: int, cw: int, dollars: float) -> None:
    t = bucket.setdefault("tokens", {}).setdefault(model, {"input": 0, "output": 0, "calls": 0})
    t["input"] += inp
    t["output"] += out
    t["calls"] += 1
    if cr or cw or "cache_read" in t:
        t["cache_read"] = t.get("cache_read", 0) + cr
        t["cache_write"] = t.get("cache_write", 0) + cw
    t["usd"] = round(t.get("usd", 0.0) + dollars, 6)
    if cr or cw:
        bucket["cache_saved_usd"] = round(bucket.get("cache_saved_usd", 0.0) + cache_saved_usd(model, cr, cw), 6)
    bucket["cost_usd"] = round(bucket.get("cost_usd", 0.0) + dollars, 6)
    rate = cache_hit_rate(bucket)
    if rate is not None:
        bucket["cache_hit_rate"] = rate


def add_tokens(model: str, input_tokens: int | None, output_tokens: int | None, *,
               cache_read: int | None = 0, cache_write: int | None = 0, source: str | None = None,
               extra_usd: float = 0.0) -> float:
    """Record one call: tokens and dollars per model in the build counter (if a build is running) and in
    the session tally. `input_tokens` is uncached input (output includes thinking where the API counts it
    so). `source` (by_source in the tally) defaults to the running build's source, else "lesson".
    `extra_usd`: per-call fees beyond tokens (web searches). Returns the call's dollars."""
    inp, out, cr, cw = int(input_tokens or 0), int(output_tokens or 0), int(cache_read or 0), int(cache_write or 0)
    model = model or "unknown"
    dollars = usd(model, inp, out, cr, cw) + max(0.0, float(extra_usd or 0.0))
    c = _counter.get()
    if c is not None:
        _add(c, model, inp, out, cr, cw, dollars)
    source = source or (c or {}).get("source") or "lesson"
    with _lock:
        _add(_session, model, inp, out, cr, cw, dollars)
        _session.setdefault("by_source", {}).setdefault(source, 0.0)
        _session["by_source"][source] = round(_session["by_source"][source] + dollars, 6)
    return dollars


def record_usage(model: str, usage: Any, *, source: str | None = None, label: str = "") -> float:
    """Record an Anthropic `usage` (object or dict): input, output, cache reads and writes. Logs the
    call's cache hit rate and dollars. Returns the dollars. `source` as in add_tokens. Never raises."""
    try:
        return _record_usage(model, usage, source, label)
    except Exception:  # noqa: BLE001 - cost accounting never breaks a model call
        log.debug("cost record failed", exc_info=True)
        return 0.0


def _record_usage(model: str, usage: Any, source: str | None, label: str) -> float:
    def g(k: str) -> int:
        v = usage.get(k, 0) if isinstance(usage, dict) else getattr(usage, k, 0)
        return int(v or 0) if isinstance(v, (int, float)) else 0

    inp, out = g("input_tokens"), g("output_tokens")
    cr, cw = g("cache_read_input_tokens"), g("cache_creation_input_tokens")
    stu = usage.get("server_tool_use") if isinstance(usage, dict) else getattr(usage, "server_tool_use", None)
    v = (stu.get("web_search_requests") if isinstance(stu, dict) else getattr(stu, "web_search_requests", 0)) or 0
    searches = int(v) if isinstance(v, (int, float)) else 0
    dollars = add_tokens(model, inp, out, cache_read=cr, cache_write=cw, source=source,
                         extra_usd=searches * WEB_SEARCH_USD)
    rate = hit_rate(inp, cr, cw)
    # one line per Claude call: which call (label), model, uncached input, output, cache read, cache write
    log.info("%s call: model=%s in=%s out=%s cache_read=%s cache_write=%s searches=%s hit=%s usd=%.5f",
             label or source or "lesson", model, inp, out, cr, cw, searches, "-" if rate is None else f"{rate:.0%}",
             dollars)
    return dollars


def record_gemini(model: str, usage_metadata: Any, *, source: str | None = None, label: str = "gemini") -> float:
    """Record a Gemini `usage_metadata`. Its prompt count includes implicitly cached tokens, so those are split
    out as cache reads; thinking tokens bill as output. Logs the hit rate; returns the dollars."""
    def n(k: str) -> int:
        v = getattr(usage_metadata, k, 0)
        return int(v) if isinstance(v, (int, float)) else 0

    prompt, cached = n("prompt_token_count"), n("cached_content_token_count")
    out = n("candidates_token_count") + n("thoughts_token_count")
    cached = min(cached, prompt)
    try:
        dollars = add_tokens(model, prompt - cached, out, cache_read=cached, source=source)
    except Exception:  # noqa: BLE001 - cost accounting never breaks a model call
        log.debug("cost record failed", exc_info=True)
        return 0.0
    log.info("%s call: model=%s in=%s out=%s cached=%s hit=%s usd=%.5f", label, model, prompt, out, cached,
             f"{cached / prompt:.0%}" if prompt else "-", dollars)
    return dollars


def cache_hit_rate(c: dict | None = None) -> float | None:
    """Cache hit rate over every model in a counter (default: the current build's)."""
    c = c if c is not None else _counter.get()
    if not c:
        return None
    inp = cr = cw = 0
    for t in (c.get("tokens") or {}).values():
        inp += t.get("input", 0)
        cr += t.get("cache_read", 0)
        cw += t.get("cache_write", 0)
    if not (cr or cw):
        return None  # no call in this counter reports cache fields (Gemini, or nothing cached yet)
    return hit_rate(inp, cr, cw)


def count(kind: str) -> None:
    c = _counter.get()
    if c is not None:
        c[kind] = c.get(kind, 0) + 1


def finish_build(c: dict | None, *, kind: str = "video", lesson_id: str | None = None,
                 outcome: str = "ok") -> dict | None:
    """Log a build's dollars and emit `build_cost` (`outcome`: ok, failed or cancelled). The spend of a build
    that did not finish stays in the session tally (it was paid) but moves to by_source "<source>_<outcome>",
    so the next lesson's own spend can be told apart. Returns the props (None without a counter)."""
    if not c:
        return None
    if outcome != "ok":
        src, amt = c.get("source") or "lesson", float(c.get("cost_usd", 0.0) or 0.0)
        with _lock:
            bs = _session.setdefault("by_source", {})
            moved = min(amt, bs.get(src, 0.0))  # less when the tally was reset while the build ran
            if moved > 0:
                bs[src] = round(bs[src] - moved, 6)
                bs[f"{src}_{outcome}"] = round(bs.get(f"{src}_{outcome}", 0.0) + moved, 6)
    props = {"kind": kind, "outcome": outcome, "cost_usd": round(c.get("cost_usd", 0.0), 6),
             "calls": {k: c.get(k, 0) for k in ("gemini_calls", "claude_calls")},
             "tokens": json.loads(json.dumps(c.get("tokens") or {})), "cache_hit_rate": cache_hit_rate(c),
             "cache_saved_usd": round(c.get("cache_saved_usd", 0.0), 6)}
    if lesson_id:
        props["lesson_id"] = lesson_id
    log.info("build cost: %s %s lesson=%s usd=%.4f calls=%s cache_hit=%s", kind, outcome, lesson_id or "-",
             props["cost_usd"], props["calls"], props["cache_hit_rate"])
    emit_event("build_cost", props)
    return props


@contextlib.contextmanager
def build_scope(c: dict | None, *, kind: str):
    """Around one build: emits `build_cost` however it ends (ok, failed, or cancelled, e.g. a prebuild that
    prebuild.cancel() stopped), once, when the counter saw any call. Yields a dict; set its "lesson_id"."""
    info: dict[str, Any] = {"lesson_id": None}
    outcome = "failed"
    try:
        yield info
        outcome = "ok"
    except BaseException as e:
        outcome = "cancelled" if isinstance(e, asyncio.CancelledError) else "failed"
        raise
    finally:
        if c and (c.get("tokens") or c.get("gemini_calls") or c.get("claude_calls")):
            try:
                finish_build(c, kind=kind, lesson_id=info.get("lesson_id"), outcome=outcome)
            except Exception:  # noqa: BLE001 - cost accounting never breaks a build
                log.debug("build cost failed", exc_info=True)


# ---------------------------------------------------------------------------------------------- per session

_lock = threading.Lock()


def _fresh() -> dict:
    return {"lesson_id": None, "cost_usd": 0.0}


_session: dict = _fresh()


def session_start(lesson_id: str | None) -> None:
    """Name the running tally after the lesson that just loaded (spend before it, its build, stays in)."""
    with _lock:
        _session["lesson_id"] = lesson_id or _session.get("lesson_id")


def session() -> dict:
    """A copy of the running session tally."""
    with _lock:
        return json.loads(json.dumps(_session))


def session_end(reason: str = "") -> dict:
    """Log the session's dollars, emit `session_cost`, and start a fresh tally. Returns the props."""
    global _session
    with _lock:
        s, _session = _session, _fresh()
    props = {"lesson_id": s.get("lesson_id"), "reason": reason, "cost_usd": round(s.get("cost_usd", 0.0), 6),
             "calls": sum(t.get("calls", 0) for t in (s.get("tokens") or {}).values()),
             "cache_hit_rate": cache_hit_rate(s),
             "by_model": {m: t.get("usd", 0.0) for m, t in (s.get("tokens") or {}).items()},
             "by_source": dict(s.get("by_source") or {})}
    log.info("session cost: lesson=%s reason=%s usd=%.4f by_model=%s cache_hit=%s", props["lesson_id"] or "-", reason,
             props["cost_usd"], props["by_model"], props["cache_hit_rate"])
    emit_event("session_cost", props)
    return props
