"""Thin wrapper over the Anthropic SDK: structured JSON out, prompt caching,
record/replay fixtures so tests and the demo never need the network.

Env (loaded from ./.env, then the shared main-checkout .env or $TUT_ENV):
  ANTHROPIC_API_KEY        normal SDK credential (loaded from .env if present)
  COACH_REPLAY_DIR         read responses from fixtures instead of calling the API
  COACH_RECORD_DIR         write every live response to a fixture file
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("coach.llm")

OPUS = "claude-opus-5-5"
HAIKU = "claude-haiku-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class CoachLLMError(RuntimeError):
    """Any failure to get a usable structured answer (callers fall back to the playbook)."""


@dataclass
class CallResult:
    data: dict
    model: str = ""
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    source: str = "live"  # live | replay


_client = None


SHARED_ENV = "/Users/tripi/sand hacks/sandhacks-tutor/.env"  # main checkout; worktrees have none


def _load_env() -> None:
    """Local .env first, then the shared one (TUT_ENV overrides its path). Never overrides set vars."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # pragma: no cover - dotenv is optional at runtime
        return
    if local := find_dotenv(usecwd=True):
        load_dotenv(local)
    shared = os.environ.get("TUT_ENV", SHARED_ENV)
    if os.path.isfile(shared):
        load_dotenv(shared)


def get_client():
    global _client
    if _client is None:
        _load_env()
        import anthropic

        _client = anthropic.AsyncAnthropic(max_retries=1, timeout=45.0)
    return _client


def has_credentials() -> bool:
    _load_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


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
) -> CallResult:
    """One Messages call that must return JSON matching `schema`.

    `system` is a list of text blocks; put `cache_control` on the last stable one.
    """
    replay_dir = os.environ.get("COACH_REPLAY_DIR")
    if replay_dir:
        hit = _replay(purpose, user_text, Path(replay_dir))
        if hit is None:
            raise CoachLLMError(f"no fixture for {purpose} in {replay_dir}")
        return hit

    if not has_credentials():
        raise CoachLLMError("no ANTHROPIC_API_KEY")

    import anthropic

    client = get_client().with_options(timeout=timeout)
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_text}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }
    t0 = time.monotonic()
    try:
        if model == OPUS:
            # Server-side refusal fallback: on a policy decline the API reruns on a fallback model.
            resp = await client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        else:
            resp = await client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        raise CoachLLMError(f"{purpose}: API {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise CoachLLMError(f"{purpose}: connection error") from e
    latency = time.monotonic() - t0

    if resp.stop_reason in ("refusal", "max_tokens"):
        raise CoachLLMError(f"{purpose}: stop_reason={resp.stop_reason}")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        raise CoachLLMError(f"{purpose}: no text block")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CoachLLMError(f"{purpose}: invalid JSON") from e

    u = resp.usage
    usage = {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }
    res = CallResult(data=data, model=resp.model, usage=usage, latency_s=latency, source="live")
    log.info("%s %s %.2fs usage=%s", purpose, resp.model, latency, usage)
    record_dir = os.environ.get("COACH_RECORD_DIR")
    if record_dir:
        _record(Path(record_dir), purpose, model, user_text, text, res)
    return res
