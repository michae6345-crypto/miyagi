"""Claude build path: transcript + metadata -> step-graph draft, and the adapt pass.

Used when Gemini can't watch the video (quota, outage, no key). Same draft schema and the
same adapt prompt as gemini.py, so builder.py treats both engines identically.
"""

from __future__ import annotations

import copy
import json
import logging
import os

import anthropic

from . import gemini
from .schema import ADAPTED_SCHEMA, VIDEO_DRAFT_SCHEMA
from .transcript import format_for_prompt

log = logging.getLogger("server.lesson")

DEFAULT_MODEL = "claude-opus-5-5"
last_model: str | None = None  # model that served the most recent successful call (for build.model)
_client: anthropic.AsyncAnthropic | None = None
_override_key: str | None = None


def set_api_key(key: str | None) -> None:
    """Bring-your-own key from the app (config.keys.anthropic). Never logged."""
    global _override_key, _client
    _override_key, _client = key or None, None


def model() -> str:
    gemini._load_env()
    return os.environ.get("LESSON_CLAUDE_MODEL", DEFAULT_MODEL)


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        gemini._load_env()
        _client = anthropic.AsyncAnthropic(api_key=_override_key) if _override_key else anthropic.AsyncAnthropic()
    return _client


def strict_schema(schema: dict) -> dict:
    """Structured outputs need additionalProperties: false on every object."""
    s = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(s)
    return s


async def _generate_json(system: str, prompt: str, schema: dict, *, effort: str = "high") -> dict:
    global last_model
    mid = model()
    try:
        async with client().beta.messages.stream(
            model=mid,
            max_tokens=32000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": strict_schema(schema)}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # on a policy decline, the API re-runs on a fallback model
        ) as stream:
            msg = await stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise RuntimeError(f"Anthropic rejected the API key: {e}") from e
    except anthropic.APIStatusError as e:  # 4xx/5xx after the SDK's own retries
        raise RuntimeError(f"Claude call failed ({e.status_code}): {str(e)[:300]}") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Claude unreachable: {e}") from e
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined: {getattr(msg, 'stop_details', None)}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("Claude output hit max_tokens (incomplete JSON)")
    text = next((b.text for b in msg.content if b.type == "text"), "")
    last_model = getattr(msg, "model", None) or mid
    return json.loads(text)


TRANSCRIPT_NOTE = """You cannot see the video. You get its title, description, chapter list and the
timestamped transcript. Timestamps must come from the transcript lines (the moment the presenter
starts the step, and the moment they finish it / see the result). Infer the code from what is said
and from what the tutorial evidently builds; prefer short, distinctive regexes (a function name, an
API call, a command, a printed result) that are very likely to appear on screen whatever the exact
code. Never invent steps the transcript does not cover."""


async def watch_transcript(info: dict, goal: str) -> dict:
    prompt = gemini.WATCH_PROMPT.format(goal=goal) + "\n\n" + TRANSCRIPT_NOTE + "\n\n" + format_for_prompt(info)
    return await _generate_json(gemini.WATCH_SYSTEM, prompt, VIDEO_DRAFT_SCHEMA, effort="high")


async def adapt_checks(goal: str, draft_steps: list[dict], workdir_summary: str, feedback: list[str] | None = None) -> dict:
    return await _generate_json(gemini.ADAPT_SYSTEM, gemini.adapt_prompt(goal, draft_steps, workdir_summary, feedback), ADAPTED_SCHEMA, effort="medium")
