"""Thin wrapper over the Anthropic SDK: structured JSON out, prompt caching,
record/replay fixtures so tests and the demo never need the network.

Keys (bring-your-own-key): the app's keys via `set_keys()` / `server.config`, else env
(./.env, plus the file at $TUT_ENV if set):
  ANTHROPIC_API_KEY        Anthropic credential
  DEMO=1                   demo mode: offline playbook cards are allowed when the API fails
  COACH_REPLAY_DIR         read responses from fixtures instead of calling the API
  COACH_RECORD_DIR         write every live response to a fixture file

Never sends secrets (ROADMAP 5.2): `_request`, the one place a coach request is shaped, runs the user message (the
learner's code, terminal output, screen text, a selection) through server.redact.redact_secrets.
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

try:  # the shared key store, miyagi cloud routing and Opus guard (absent only when coach/ runs on its own)
    from server import config as _cfg
except ImportError:  # pragma: no cover
    _cfg = None  # type: ignore[assignment]

try:
    from server.redact import redact_secrets as _redact_secrets
except ImportError:  # pragma: no cover - coach/ on its own
    def _redact_secrets(text: str) -> str:
        return text

try:  # the <untrusted> fences carry random nonces: fixtures are keyed by the prompt with them taken out
    from server.untrusted import unfence as _unfence
except ImportError:  # pragma: no cover - coach/ on its own
    def _unfence(text: str) -> str:
        return text

OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Cost policy (Michael): Sonnet writes the diagnosis card; everything else is Haiku.
# Override per purpose with COACH_MODEL_<PURPOSE>, e.g. COACH_MODEL_EXPLAIN=claude-sonnet-5-5. An Opus override
# (COACH_MODEL_DIAGNOSE=claude-opus-5-5) also needs MIYAGI_ALLOW_OPUS=1 and no miyagi cloud, else it runs on Sonnet.
MODELS = {"diagnose": SONNET}  # spend cap (Michael, $84/$100): never Opus by default


def guard(model: str) -> str:
    """The shared Opus guard (server.config.guard_model): Opus / Fable / Mythos become Sonnet unless opted in."""
    if _cfg is not None:
        return _cfg.guard_model(model, SONNET)
    return SONNET if any(p in (model or "") for p in ("opus", "fable", "mythos")) else model


def model_for(purpose: str) -> str:
    return guard(os.environ.get(f"COACH_MODEL_{purpose.upper()}") or MODELS.get(purpose, HAIKU))


def _cost_mod() -> Any:
    try:
        from server.lesson import cost
    except Exception:  # noqa: BLE001 - coach/ running on its own
        return None
    return cost


def record_cost(model: str, usage: Any, *, source: str = "coach", label: str = "") -> float:
    """Dollars and cache hit rate of one call into the session tally (server.lesson.cost). Every billed call
    counts, refused or cut short included. Returns the dollars (0.0 when coach/ runs on its own). Never raises."""
    cost = _cost_mod()
    if cost is None or usage is None:
        return 0.0
    try:
        return cost.record_usage(model, usage, source=source, label=label or source)
    except Exception:  # noqa: BLE001 - cost accounting never breaks a call
        log.debug("cost record failed", exc_info=True)
        return 0.0


def usd(model: str, input_tokens: int = 0, output_tokens: int = 0) -> float:
    """One call's dollars from the shared price table (server.lesson.cost); Haiku's rate when coach/ runs alone."""
    cost = _cost_mod()
    if cost is not None:
        return cost.usd(model, input_tokens, output_tokens)
    return (input_tokens * 0.10 + output_tokens * 0.50) / 1e6


def _record_cost(model: str, usage: dict, purpose: str) -> None:
    record_cost(model, usage, source="coach", label=f"coach {purpose}")


def cached_system(text: str) -> list[dict]:
    """A one-block system prompt marked for prompt caching (short prompts just won't cache)."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


class CoachLLMError(RuntimeError):
    """Any failure to get a usable structured answer from the model.

    `kind`: "connection" (network/proxy down, timeout) | "api" (HTTP error) | "refusal" | "no_key"
    | "replay" | "bad_output" | "cloud" (the miyagi cloud refused: the message holds miyagi_paused / miyagi_quota /
    miyagi_auth and the card text from server.config.CLOUD_ERRORS).
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
    """fix_outdated() could not search or read the docs (web search off or empty, fetch/model failure)."""


def offline_mode() -> bool:
    """Zero-cost mode: DEMO=1, or ORCH_STUBS names the coach ("all" / "lesson,coach,..."). No paid call
    leaves the coach (Claude, the live web, ElevenLabs); recorded fixtures (COACH_REPLAY_DIR) still replay.
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

KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}


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


def _client_kwargs() -> dict:
    """{api_key, base_url, ...}: the Settings key direct, the install token through the miyagi cloud, or .env."""
    if _cfg is not None:
        return _cfg.anthropic_kwargs("coach")
    key = get_key("anthropic")
    return {"api_key": key} if key else {}


def get_client():
    """AsyncAnthropic bound to the current key / route; rebuilt when the app sends a new key."""
    global _client, _client_key
    kw = _client_kwargs()
    sig = hashlib.sha256(repr((kw.get("api_key"), kw.get("base_url"))).encode()).hexdigest()
    if _client is None or sig != _client_key:
        import anthropic

        _client = anthropic.AsyncAnthropic(max_retries=1, timeout=45.0, **kw)
        _client_key = sig
    return _client


def has_credentials() -> bool:
    if _cfg is not None and _cfg.has_anthropic():
        return True
    return bool(get_key("anthropic") or get_key("ANTHROPIC_AUTH_TOKEN"))


def cloud_mode() -> bool:
    return _cfg is not None and _cfg.mode("anthropic") == "cloud"


def _key(purpose: str, user_text: str) -> str:
    """The fixture name: purpose + a hash of the user text with its <untrusted> fences (random nonces) taken out."""
    return f"{purpose}-{hashlib.sha256(_unfence(user_text).encode()).hexdigest()[:10]}"


def _replay(purpose: str, user_text: str, replay_dir: Path) -> CallResult | None:
    for name in (_key(purpose, user_text), purpose):
        p = replay_dir / f"{name}.json"
        if p.exists():
            rec = json.loads(p.read_text(encoding="utf-8"))
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
        "request": {"model": model, "user": _redact_secrets(user_text)},  # fixtures get committed: no keys
        "response": {"model": res.model, "text": text, "usage": res.usage, "latency_s": round(res.latency_s, 2)},
    }
    (record_dir / f"{_key(purpose, user_text)}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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

    model = guard(model)
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
        if _cfg is not None and (code := _cfg.cloud_error(e)):  # the miyagi cloud turned it away: paused / quota / auth
            raise CoachLLMError(f"{purpose}: {code}: {_cfg.CLOUD_ERRORS[code]}", "cloud") from e
        raise CoachLLMError(f"{purpose}: API {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise CoachLLMError(f"{purpose}: connection error", "connection") from e
    latency = time.monotonic() - t0

    u = getattr(resp, "usage", None)
    usage = {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }
    _record_cost(resp.model or model, usage, purpose)  # billed even when refused, cut at max_tokens or bad JSON

    if resp.stop_reason in ("refusal", "max_tokens"):
        raise CoachLLMError(f"{purpose}: stop_reason={resp.stop_reason}", "refusal" if resp.stop_reason == "refusal" else "bad_output")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        raise CoachLLMError(f"{purpose}: no text block", "bad_output")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CoachLLMError(f"{purpose}: invalid JSON", "bad_output") from e

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
    """The one place a coach request is shaped (warm() must send the same prefix to hit the cache). The user message
    is redacted here (redact_user_content): no key or token in the learner's code or screen ever goes out."""
    content = redact_user_content(content)
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": content}],
        "thinking": thinking or {"type": "adaptive"},  # Haiku pointing passes {"type": "disabled"} for speed
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }
    # server-side refusal fallback: on a policy decline the API reruns on a fallback model. Only in a form that
    # cannot reach an Opus nobody opted into (server.config.fallback_kwargs: Sonnet 5.5 -> Sonnet 5 only); none for Haiku.
    if _cfg is not None:
        fb = _cfg.fallback_kwargs(model)
    else:
        fb = {"betas": [FALLBACK_BETA], "fallbacks": "default"} if model == SONNET else {}
    if fb:
        return client.beta.messages, {**fb, **kwargs}
    return client.messages, kwargs


def redact_user_content(content: Any) -> Any:
    """A user message (a string, or content blocks) with secrets redacted in every text part; images pass as is
    (the screen readers black out secret rows before they encode a screenshot)."""
    if isinstance(content, str):
        return _redact_secrets(content)
    if isinstance(content, list):
        out = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                block = {**block, "text": _redact_secrets(block["text"])}
            out.append(block)
        return out
    return content


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
    if not cloud_mode():  # the miyagi cloud forwards /v1/messages only (no models endpoint)
        try:
            await client.models.retrieve(model_for("diagnose"))
            out["tls_s"] = round(time.monotonic() - t0, 2)
        except Exception as e:  # noqa: BLE001 - warm-up is best effort
            out["tls_error"] = type(e).__name__

    async def one(r: dict) -> Any:
        # max_tokens=1: writes the cached prefix for one output token (0 is rejected with output_config.format)
        mid = guard(r.get("model") or model_for("diagnose"))
        api, kwargs = _request(client, mid, r["system"], "warm", r["schema"], r.get("effort", "low"), 1)
        resp = await api.create(**kwargs)
        record_cost(getattr(resp, "model", None) or mid, getattr(resp, "usage", None), label="coach warm")  # cache writes
        return resp

    t0 = time.monotonic()
    results = await asyncio.gather(*(one(r) for r in requests or []), return_exceptions=True)
    if requests:
        out["cache_s"] = round(time.monotonic() - t0, 2)
        out["cache"] = [type(r).__name__ if isinstance(r, BaseException) else getattr(r.usage, "cache_creation_input_tokens", 0) + getattr(r.usage, "cache_read_input_tokens", 0) for r in results]
    return out
