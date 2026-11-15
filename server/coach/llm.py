"""Thin wrapper over the Anthropic SDK: structured JSON out, prompt caching,
record/replay fixtures so tests and the demo never need the network.

Keys (bring-your-own-key): the app's keys via `set_keys()` / `server.config`, else env
(./.env, plus the file at $TUT_ENV if set):
  ANTHROPIC_API_KEY        Anthropic credential
  DEMO=1                   demo mode: offline playbook cards are allowed when the API fails
  COACH_REPLAY_DIR         read responses from fixtures instead of calling the API
  COACH_RECORD_DIR         write every live response to a fixture file
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("coach.llm")

OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Cost policy (Michael): Sonnet writes the diagnosis card (Opus only via COACH_MODEL_DIAGNOSE); everything else is Haiku.
# Override per purpose with COACH_MODEL_<PURPOSE>, e.g. COACH_MODEL_EXPLAIN=claude-opus-5-5.
MODELS = {"diagnose": SONNET}  # spend cap (Michael, $84/$100): never Opus by default; COACH_MODEL_DIAGNOSE overrides


def model_for(purpose: str) -> str:
    return os.environ.get(f"COACH_MODEL_{purpose.upper()}") or MODELS.get(purpose, HAIKU)


def cached_system(text: str) -> list[dict]:
    """A one-block system prompt marked for prompt caching (short prompts just won't cache)."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


class CoachLLMError(RuntimeError):
    """Any failure to get a usable structured answer from the model.

    `kind`: "connection" (network/proxy down, timeout) | "api" (HTTP error) | "refusal" | "no_key"
    | "replay" | "bad_output".
    """

    def __init__(self, msg: str, kind: str = "api"):
        super().__init__(msg)
        self.kind = kind


class CoachUnavailable(RuntimeError):
    """The coach could not produce a real answer (no key, API error, refusal...).

    Raised instead of returning a canned card outside DEMO=1. `reason` is safe to show.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class OutdatedFixUnavailable(CoachUnavailable):
    """fix_outdated() could not search or read the docs (no Bright Data config, fetch/model failure)."""


def offline_mode() -> bool:
    """Zero-cost mode: DEMO=1, or ORCH_STUBS names the coach ("all" / "lesson,coach,..."). No paid call
    leaves the coach (Claude, Bright Data, ElevenLabs); recorded fixtures (COACH_REPLAY_DIR) still replay.
    S11: with DEMO=1 the coach still made 19 Claude calls in one rehearsal take."""
    if os.environ.get("DEMO", "").strip() == "1":
        return True
    stubs = {t.strip().lower() for t in re.split(r"[,\s]+", os.environ.get("ORCH_STUBS", "")) if t.strip()}
    return bool(stubs & {"coach", "all", "*", "1"})


def demo_mode() -> bool:
    """Offline answers (playbook / template cards) stand in for model answers."""
    return offline_mode()


def offline_fallback() -> bool:
    """COACH_OFFLINE_FALLBACK=1: on a *connection* failure in live mode, a confident playbook match
    on the learner's own code may stand in (labelled offline). Off by default (no-fake rule)."""
    return os.environ.get("COACH_OFFLINE_FALLBACK", "").strip() == "1"


@dataclass
class CallResult:
    data: dict
    model: str = ""
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    source: str = "live"  # live | replay


_client = None
_client_key: str | None = None
_local_keys: dict[str, str] = {}

KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "brightdata": "BRIGHTDATA_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}


def _load_env() -> None:
    """./.env (searched upward from cwd), then $TUT_ENV if set. Never overrides set vars."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # pragma: no cover - dotenv is optional at runtime
        return
    if local := find_dotenv(usecwd=True):
        load_dotenv(local)
    if (shared := os.environ.get("TUT_ENV")) and os.path.isfile(shared):
        load_dotenv(shared)


def set_keys(keys: dict) -> None:
    """Bring-your-own-key: store the app's keys (names as in events.ts `config.keys`).

    Delegates to `server.config.set_app_keys` when that module exists, so every engine
    module sees the same keys. Keys live in memory only and are never logged.
    """
    try:
        from server.config import set_app_keys  # type: ignore
    except ImportError:
        for name, v in (keys or {}).items():
            v = (v or "").strip()
            if v and "..." not in v:
                _local_keys[name] = v
            else:
                _local_keys.pop(name, None)
        return
    set_app_keys(keys)


def get_key(name: str) -> str | None:
    """App key > environment (.env) > None. `name` is a config.keys name or an env var name."""
    try:
        from server.config import get_key as shared_get_key  # type: ignore
    except ImportError:
        shared_get_key = None
    if shared_get_key is not None:
        if v := shared_get_key(name):
            return v
    elif name in _local_keys:
        return _local_keys[name]
    _load_env()
    v = os.environ.get(KEY_ENV.get(name, name), "")
    return v if v and "..." not in v else None


def get_client():
    """AsyncAnthropic bound to the current key; rebuilt when the app sends a new key."""
    global _client, _client_key
    key = get_key("anthropic")
    if _client is None or key != _client_key:
        import anthropic

        _client = anthropic.AsyncAnthropic(api_key=key, max_retries=1, timeout=45.0) if key else anthropic.AsyncAnthropic(max_retries=1, timeout=45.0)
        _client_key = key
    return _client


def has_credentials() -> bool:
    return bool(get_key("anthropic") or get_key("ANTHROPIC_AUTH_TOKEN"))


def _key(purpose: str, user_text: str) -> str:
    return f"{purpose}-{hashlib.sha256(user_text.encode()).hexdigest()[:10]}"


def _replay(purpose: str, user_text: str, replay_dir: Path) -> CallResult | None:
    for name in (_key(purpose, user_text), purpose):
        p = replay_dir / f"{name}.json"
        if p.exists():
            rec = json.loads(p.read_text())
            resp = rec["response"]
            return CallResult(
                data=json.loads(resp["text"]),
                model=resp.get("model", ""),
                usage=resp.get("usage", {}),
                latency_s=resp.get("latency_s", 0.0),
                source="replay",
            )
    return None


def _record(record_dir: Path, purpose: str, model: str, user_text: str, text: str, res: CallResult) -> None:
    record_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "purpose": purpose,
        "request": {"model": model, "user": user_text},
        "response": {"model": res.model, "text": text, "usage": res.usage, "latency_s": round(res.latency_s, 2)},
    }
    (record_dir / f"{_key(purpose, user_text)}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")


async def structured_call(
    *,
    purpose: str,
    model: str,
    system: list[dict],
    user_text: str,
    schema: dict,
    effort: str = "low",
    max_tokens: int = 8000,
    timeout: float = 45.0,
    user_content: list[dict] | None = None,
    on_text: Callable[[str, str], Any] | None = None,
    thinking: dict | None = None,
) -> CallResult:
    """One Messages call that must return JSON matching `schema`.

    `system` is a list of text blocks; put `cache_control` on the last stable one.
    `user_content` (content blocks, e.g. screen images) replaces `user_text` as the message;
    `user_text` still keys the fixtures. With `on_text(delta, snapshot)` the reply is streamed
    and the callback runs on every text delta (sync or async); cancelling the awaiting task
    closes the stream.
    """
    replay_dir = os.environ.get("COACH_REPLAY_DIR")
    if replay_dir:
        hit = _replay(purpose, user_text, Path(replay_dir))
        if hit is None:
            raise CoachLLMError(f"no fixture for {purpose} in {replay_dir}", "replay")
        if on_text is not None:
            full = json.dumps(hit.data, ensure_ascii=False)
            await _maybe_await(on_text(full, full))
        return hit

    if offline_mode():
        raise CoachLLMError(f"{purpose}: offline mode (DEMO / ORCH_STUBS), no live call", "offline")
    if not has_credentials():
        raise CoachLLMError("no ANTHROPIC_API_KEY", "no_key")

    import anthropic

    client = get_client().with_options(timeout=timeout)
    api, kwargs = _request(client, model, system, user_content or user_text, schema, effort, max_tokens, thinking)
    t0 = time.monotonic()
    ttft = None
    try:
        if on_text is None:
            resp = await api.create(**kwargs)
        else:
            async with api.stream(**kwargs) as stream:
                async for event in stream:
                    if getattr(event, "type", "") == "text":
                        if ttft is None:
                            ttft = time.monotonic() - t0
                        await _maybe_await(on_text(event.text, event.snapshot))
                resp = await stream.get_final_message()
    except anthropic.APIStatusError as e:
        raise CoachLLMError(f"{purpose}: API {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise CoachLLMError(f"{purpose}: connection error", "connection") from e
    latency = time.monotonic() - t0

    if resp.stop_reason in ("refusal", "max_tokens"):
        raise CoachLLMError(f"{purpose}: stop_reason={resp.stop_reason}", "refusal" if resp.stop_reason == "refusal" else "bad_output")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        raise CoachLLMError(f"{purpose}: no text block", "bad_output")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CoachLLMError(f"{purpose}: invalid JSON", "bad_output") from e

    u = resp.usage
    usage = {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }
    if ttft is not None:
        usage["first_text_s"] = round(ttft, 2)
    res = CallResult(data=data, model=resp.model, usage=usage, latency_s=latency, source="live")
    log.info("%s %s %.2fs usage=%s", purpose, resp.model, latency, usage)
    record_dir = os.environ.get("COACH_RECORD_DIR")
    if record_dir:
        _record(Path(record_dir), purpose, model, user_text, text, res)
    return res


RETRY_DELAYS_S = (0.5, 1.5, 3.0)  # QA 11-14: a 2 s network blip (VPN rebuild) killed a question (one 0.5 s retry)
RETRY_BUDGET_S = 12.0


async def structured_call_retrying(*, delays: tuple[float, ...] = RETRY_DELAYS_S, budget_s: float = RETRY_BUDGET_S,
                                   **kwargs: Any) -> CallResult:
    """structured_call() for the learner's own question: a *connection* failure is retried after each of `delays`
    (s) while the whole try stays within `budget_s` (a slow timeout is not retried). Any other failure (HTTP error,
    refusal, no key, offline, replay) raises at once."""
    t0 = time.monotonic()
    for i, delay in enumerate((*delays, None)):
        try:
            return await structured_call(**kwargs)
        except CoachLLMError as e:
            if e.kind != "connection" or delay is None or time.monotonic() - t0 + delay > budget_s:
                raise
            log.warning("%s: connection failed (try %d); retrying in %.1fs", kwargs.get("purpose"), i + 1, delay)
            await asyncio.sleep(delay)
    raise CoachLLMError("unreachable", "api")  # pragma: no cover - the loop always returns or raises


def _request(client, model: str, system: list[dict], content: Any, schema: dict, effort: str, max_tokens: int, thinking: dict | None = None):
    """The one place a coach request is shaped (warm() must send the same prefix to hit the cache)."""
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": content}],
        "thinking": thinking or {"type": "adaptive"},  # Haiku pointing passes {"type": "disabled"} for speed
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }
    if model in (OPUS, SONNET):  # server-side refusal fallback: on a policy decline the API reruns on a fallback model
        return client.beta.messages, {"betas": [FALLBACK_BETA], "fallbacks": "default", **kwargs}
    return client.messages, kwargs


async def _maybe_await(x: Any) -> None:
    if inspect.isawaitable(x):
        await x


async def warm(requests: list[dict] | None = None) -> dict:
    """Open the TLS connection, then pre-warm the prompt cache for each request shape.

    `requests`: [{"model", "system", "schema", "effort"}], the same values the real call will use
    (the cached prefix includes the output format). Best effort: never raises; returns timings.
    """
    if offline_mode():
        return {"skipped": "offline"}
    out: dict[str, Any] = {}
    if not has_credentials():
        return {"skipped": "no key"}
    client = get_client()
    t0 = time.monotonic()
    try:
        await client.models.retrieve(model_for("diagnose"))
        out["tls_s"] = round(time.monotonic() - t0, 2)
    except Exception as e:  # noqa: BLE001 - warm-up is best effort
        out["tls_error"] = type(e).__name__

    async def one(r: dict) -> Any:
        # max_tokens=1: writes the cached prefix for one output token (0 is rejected with output_config.format)
        api, kwargs = _request(client, r.get("model") or model_for("diagnose"), r["system"], "warm", r["schema"], r.get("effort", "low"), 1)
        return await api.create(**kwargs)

    t0 = time.monotonic()
    results = await asyncio.gather(*(one(r) for r in requests or []), return_exceptions=True)
    if requests:
        out["cache_s"] = round(time.monotonic() - t0, 2)
        out["cache"] = [type(r).__name__ if isinstance(r, BaseException) else getattr(r.usage, "cache_creation_input_tokens", 0) + getattr(r.usage, "cache_read_input_tokens", 0) for r in results]
    return out
