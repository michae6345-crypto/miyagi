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
from jsonschema import Draft202012Validator

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


_schema_too_complex: set[str] = set()  # schema fingerprints the API rejected for structured output


_fast_ok = True  # flips off for the process if fast mode is rate-limited or unavailable


def _use_fast() -> bool:
    gemini._load_env()
    return _fast_ok and os.environ.get("LESSON_CLAUDE_FAST", "1") != "0"


async def _call(mid: str, system: str, prompt: str, *, effort: str, schema: dict | None):
    global _fast_ok
    output_config: dict = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": strict_schema(schema)}
    kwargs = dict(
        model=mid,
        max_tokens=32000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        thinking={"type": "adaptive"},
        output_config=output_config,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # on a policy decline, the API re-runs on a fallback model
    )
    fast = _use_fast()
    try:
        try:
            async with client().beta.messages.stream(**kwargs, **({"speed": "fast"} if fast else {})) as stream:
                msg = await stream.get_final_message()
        except (anthropic.RateLimitError, anthropic.BadRequestError) as e:
            if not fast or (isinstance(e, anthropic.BadRequestError) and "speed" not in str(e).lower() and "fast" not in str(e).lower()):
                raise
            _fast_ok = False  # fast mode has its own rate limit; fall back to standard speed
            log.warning("fast mode unavailable (%s); using standard speed", str(e)[:120])
            async with client().beta.messages.stream(**kwargs) as stream:
                msg = await stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise RuntimeError(f"Anthropic rejected the API key: {e}") from e
    except anthropic.BadRequestError as e:
        msg_l = str(e).lower()
        if schema is not None and "schema" in msg_l and ("too complex" in msg_l or "too many" in msg_l or "contains too" in msg_l):
            raise _SchemaTooComplex from e
        raise RuntimeError(f"Claude call failed (400): {str(e)[:300]}") from e
    except anthropic.APIStatusError as e:  # 4xx/5xx after the SDK's own retries
        raise RuntimeError(f"Claude call failed ({e.status_code}): {str(e)[:300]}") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Claude unreachable: {e}") from e
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined: {getattr(msg, 'stop_details', None)}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("Claude output hit max_tokens (incomplete JSON)")
    return msg, next((b.text for b in msg.content if b.type == "text"), "")


class _SchemaTooComplex(Exception):
    pass


def extract_json(text: str) -> dict:
    """The JSON object in a reply (tolerates a ```json fence or a sentence around it)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in the reply")
    obj, _ = json.JSONDecoder().raw_decode(t, start)
    return obj


async def _generate_json(system: str, prompt: str, schema: dict, *, effort: str = "high") -> dict:
    """Structured output when the API accepts the schema; otherwise (\"Schema is too complex\") the
    schema goes in the prompt and the reply is validated client-side, with one corrective retry."""
    global last_model
    mid = model()
    key = json.dumps(schema, sort_keys=True)
    if key not in _schema_too_complex:
        try:
            msg, text = await _call(mid, system, prompt, effort=effort, schema=schema)
            last_model = getattr(msg, "model", None) or mid
            return json.loads(text)
        except _SchemaTooComplex:
            _schema_too_complex.add(key)
            log.info("structured output schema too complex for the API; using prompt-described JSON + client validation")

    validator = Draft202012Validator(schema)
    ask = (prompt + "\n\nReply with ONE JSON object (no prose, no code fence) that validates against this JSON Schema:\n"
           + json.dumps(schema))
    errors: list[str] = []
    for _attempt in range(2):
        msg, text = await _call(mid, system, ask, effort=effort, schema=None)
        try:
            obj = extract_json(text)
            errors = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in validator.iter_errors(obj)]
        except ValueError as e:
            errors = [f"not valid JSON: {e}"]
        if not errors:
            last_model = getattr(msg, "model", None) or mid
            return obj
        ask = ask + "\n\nYour previous reply was invalid; fix these and reply with the full JSON object again:\n- " + "\n- ".join(errors[:20])
    raise RuntimeError("Claude reply did not match the schema: " + "; ".join(errors[:5]))


TRANSCRIPT_NOTE = """You cannot see the video. You get its title, description, chapter list and the
timestamped transcript. Timestamps must come from the transcript lines (the moment the presenter
starts the step, and the moment they finish it / see the result). Infer the code from what is said
and from what the tutorial evidently builds; prefer short, distinctive regexes (a function name, an
API call, a command, a printed result) that are very likely to appear on screen whatever the exact
code. Never invent steps the transcript does not cover."""


async def watch_transcript(info: dict, goal: str) -> dict:
    prompt = gemini.WATCH_PROMPT.format(goal=goal, stack_guide=gemini.STACK_GUIDE) + "\n\n" + TRANSCRIPT_NOTE + "\n\n" + format_for_prompt(info)
    return await _generate_json(gemini.WATCH_SYSTEM, prompt, VIDEO_DRAFT_SCHEMA, effort=os.environ.get("LESSON_CLAUDE_EFFORT_WATCH", "medium"))


async def adapt_checks(goal: str, draft_steps: list[dict], workdir_summary: str, feedback: list[str] | None = None) -> dict:
    return await _generate_json(gemini.ADAPT_SYSTEM, gemini.adapt_prompt(goal, draft_steps, workdir_summary, feedback), ADAPTED_SCHEMA, effort=os.environ.get("LESSON_CLAUDE_EFFORT_ADAPT", "low"))
