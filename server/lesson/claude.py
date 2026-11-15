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

from . import cost, gemini
from .schema import ADAPTED_SCHEMA, VIDEO_DRAFT_SCHEMA
from .transcript import format_for_prompt

log = logging.getLogger("server.lesson")

DEFAULT_MODEL = "claude-sonnet-5-5"  # cost: never Opus by default (an Opus default once cost ~$80 in an hour)
OPUS_MODEL = "claude-opus-5-5"
# Cheapest model that holds quality per job; Opus only when a quality check fails (escalation).
ROLE_MODELS = {"segment": "claude-sonnet-5-5", "detail": "claude-haiku-5-5", "adapt": "claude-haiku-5-5", "judge": "claude-haiku-5-5",
               "escalate": "claude-sonnet-5-5"}
ESCALATION_MODEL = "claude-sonnet-5-5"  # Opus only with LESSON_ALLOW_OPUS=1
last_model: str | None = None  # model that served the most recent successful call (for build.model)
_client: anthropic.AsyncAnthropic | None = None
_override_key: str | None = None


def set_api_key(key: str | None) -> None:
    """Bring-your-own key from the app (config.keys.anthropic). Never logged."""
    global _override_key, _client
    _override_key, _client = key or None, None


def opus_allowed() -> bool:
    """Opus is opt-in only: LESSON_ALLOW_OPUS=1."""
    gemini._load_env()
    return os.environ.get("LESSON_ALLOW_OPUS", "0") == "1"


def _guard(mid: str) -> str:
    if "opus" in mid and not opus_allowed():
        log.warning("%s requested without LESSON_ALLOW_OPUS=1; using %s", mid, DEFAULT_MODEL)
        return DEFAULT_MODEL
    return mid


def model(role: str | None = None) -> str:
    """LESSON_CLAUDE_MODEL forces one model for everything; else LESSON_CLAUDE_MODEL_<ROLE> or ROLE_MODELS.
    Any Opus choice is downgraded to Sonnet unless LESSON_ALLOW_OPUS=1."""
    gemini._load_env()
    if os.environ.get("LESSON_CLAUDE_MODEL"):
        return _guard(os.environ["LESSON_CLAUDE_MODEL"])
    if role is None:
        return DEFAULT_MODEL
    if role == "escalate":
        return escalation_model()
    return _guard(os.environ.get(f"LESSON_CLAUDE_MODEL_{role.upper()}", ROLE_MODELS.get(role, DEFAULT_MODEL)))


def escalation_model() -> str:
    gemini._load_env()
    default = OPUS_MODEL if opus_allowed() else ESCALATION_MODEL
    return _guard(os.environ.get("LESSON_CLAUDE_MODEL_ESCALATE", default))


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
    # fast mode is premium-priced and Opus-only: off unless explicitly enabled (and Opus is allowed)
    return _fast_ok and os.environ.get("LESSON_CLAUDE_FAST", "0") == "1" and opus_allowed()


CONCURRENCY = int(os.environ.get("LESSON_CLAUDE_CONCURRENCY", "4"))  # per process: segment + per-step + adapt batches add up
RATE_RETRIES = 4
_sems: dict = {}


def _sem():
    import asyncio

    loop = asyncio.get_running_loop()
    if loop not in _sems:
        _sems.clear()  # one live loop at a time in practice; don't keep dead loops alive
        _sems[loop] = asyncio.Semaphore(CONCURRENCY)
    return _sems[loop]


async def _call(mid: str, system: str, prompt: str, *, effort: str, schema: dict | None):
    """One Claude request: at most CONCURRENCY in flight per process, and 429s (incl. "Number of
    concurrent requests") retried with backoff, honoring retry-after."""
    import asyncio

    for attempt in range(RATE_RETRIES + 1):
        try:
            async with _sem():
                cost.count("claude_calls")
                return await _call_once(mid, system, prompt, effort=effort, schema=schema)
        except _RateLimited as e:
            if attempt == RATE_RETRIES:
                raise RuntimeError(f"Claude rate-limited after {RATE_RETRIES + 1} attempts: {e}") from e
            wait = min(30.0, e.retry_after or 2.0 * 2 ** attempt)
            log.warning("Claude 429 (%s); retrying in %.0fs", str(e)[:80], wait)
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")


class _RateLimited(Exception):
    def __init__(self, msg: str, retry_after: float | None):
        super().__init__(msg)
        self.retry_after = retry_after


async def _call_once(mid: str, system: str, prompt: str, *, effort: str, schema: dict | None):
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
    )
    # server-side refusal fallback: Opus/Sonnet only (Haiku 5.5 has none); fast mode: Opus 5.5 only
    if "haiku" not in mid:
        kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    fast = _use_fast() and mid.startswith("claude-opus-5-5")
    api = client().beta.messages if "betas" in kwargs else client().messages
    try:
        try:
            async with api.stream(**kwargs, **({"speed": "fast"} if fast else {})) as stream:
                msg = await stream.get_final_message()
        except (anthropic.RateLimitError, anthropic.BadRequestError) as e:
            if not fast or (isinstance(e, anthropic.BadRequestError) and "speed" not in str(e).lower() and "fast" not in str(e).lower()):
                raise
            _fast_ok = False  # fast mode has its own rate limit; fall back to standard speed
            log.warning("fast mode unavailable (%s); using standard speed", str(e)[:120])
            async with api.stream(**kwargs) as stream:
                msg = await stream.get_final_message()
    except anthropic.RateLimitError as e:
        ra = None
        try:
            ra = float(e.response.headers.get("retry-after"))
        except (AttributeError, TypeError, ValueError):
            pass
        raise _RateLimited(str(e)[:200], ra) from e
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
    u = getattr(msg, "usage", None)
    cost.add_tokens(getattr(msg, "model", None) or mid, getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))
    log.info("claude call: model=%s in=%s out=%s fast=%s", getattr(msg, "model", None) or mid,
             getattr(u, "input_tokens", "?"), getattr(u, "output_tokens", "?"), fast)
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


async def _generate_json(system: str, prompt: str, schema: dict, *, effort: str = "high", structured: bool = True,
                         role: str | None = None, escalate: bool = True, check=None) -> dict:
    """Run on the role's (cheap) model; if the reply fails validation or `check(obj)` returns a problem,
    retry once on the escalation model (Opus)."""
    mid = model(role)
    try:
        obj = await _generate_json_on(mid, system, prompt, schema, effort=effort, structured=structured)
        problem = check(obj) if check else None
    except RuntimeError as e:
        if not escalate or mid == escalation_model() or "rejected the API key" in str(e) or "rate-limited" in str(e):
            raise
        problem = str(e)[:160]
    if not problem:
        return obj
    if not escalate or mid == escalation_model():
        raise RuntimeError(f"{mid}: {problem}")
    log.info("%s output failed a quality check (%s); escalating to %s", mid, problem, escalation_model())
    obj = await _generate_json_on(escalation_model(), system, prompt, schema, effort=effort, structured=structured)
    if check and (p2 := check(obj)):
        raise RuntimeError(f"{escalation_model()}: {p2}")
    return obj


async def _generate_json_on(mid: str, system: str, prompt: str, schema: dict, *, effort: str, structured: bool) -> dict:
    """Structured output when the API accepts the schema; otherwise (\"Schema is too complex\") the
    schema goes in the prompt and the reply is validated client-side, with one corrective retry."""
    global last_model
    key = json.dumps(schema, sort_keys=True)
    if structured and key not in _schema_too_complex:
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


SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "libraries": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "version": {"type": "string"}}, "required": ["name", "version"]}},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "start": {"type": "string", "description": "MM:SS"}, "end": {"type": "string", "description": "MM:SS"},
            "title": {"type": "string"}, "instructions": {"type": "string"}}, "required": ["start", "end", "title", "instructions"]}},
    },
    "required": ["title", "libraries", "steps"],
}

SEGMENT_PROMPT = """Learner's goal: {goal}

Break this tutorial into 4-10 sequential steps a learner can code along with. Return ONLY the step list.
- One step = one concrete thing the learner builds or runs. Skip intros, outros, sponsor segments and pure
  theory unless they end in code or a command. Chapters, when given, are strong hints for boundaries.
- start/end are MM:SS taken from the transcript: start = where the presenter begins the step, end = where
  its code is complete or its run finished. In order, no overlaps.
- title: imperative, at most 6 words. instructions: at most 2 sentences, concrete.
- A step shorter than ~20 s belongs to its neighbour.
- The lesson must be playable from an EMPTY folder: if the tutorial starts from code, data or repo state
  prepared off camera, step 1 sets it up (a link from the description, or exact commands/files to recreate it).
- Each step's instructions state any state it depends on that no earlier step created (e.g. "first make two
  commits on main that change the same line"), so a learner who follows only the instructions gets there.
- libraries: every library/tool used, with the version if mentioned, else your best estimate ("18.x").
"""

STEP_PROMPT = """Learner's goal: {goal}. Tutorial: "{lesson}". Its steps: {outline}

Fill in step {index}: "{title}" ({start}-{end}). {instructions}
Transcript of this step (with a little context either side):
{slice}

Return for THIS step only:
- file: the file edited (if any); code: the key lines written, as the presenter evidently types them;
  run_command / expected_output: the command run and what it prints, verbatim if said or obvious.
- checks: machine-checkable from the learner's SCREEN (OCR of editor, terminal, browser), at least one:
  screen_contains (app "Code"/"Terminal"/"Google Chrome", SHORT regex < 60 chars for a distinctive fragment,
  tolerant to spacing), screen_absent (app "Terminal", "Traceback|Error:|ERR!") for "it runs", and
  metric_threshold / metric_trend for numbers the run prints, with metric_pattern (named group value, plus
  step when printed per step/epoch). Never "visual".
{stack_guide}
- targets: app + a short literal on-screen `match` (e.g. "function Header") + caption: a 2-6 word pointer on
  the box ("Type it here", "Type below Header", "Run it here"), never the whole instruction.
- explanations: MM:SS moments in this slice where a concept is explained.
- hints: 2-4, gentlest first. common_mistakes: concrete ones for this step.
"""

STEP_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {k: v for k, v in VIDEO_DRAFT_SCHEMA["properties"]["steps"]["items"]["properties"].items()
                   if k in ("file", "code", "run_command", "expected_output", "checks", "targets", "explanations", "hints", "common_mistakes")},
    "required": ["checks", "hints"],
}
DETAIL_CONCURRENCY = 8


async def watch_transcript(info: dict, goal: str) -> dict:
    """Two phases so a 20-min video builds in well under a minute:
    1. segment: one small call returns the step list with timestamps;
    2. detail: one call per step, in parallel, on just that step's transcript slice."""
    import asyncio

    from .builder import parse_ts
    from .transcript import _mmss

    effort_seg = os.environ.get("LESSON_CLAUDE_EFFORT_WATCH", "medium")
    effort_detail = os.environ.get("LESSON_CLAUDE_EFFORT_DETAIL", "low")
    def seg_ok(o: dict) -> str | None:
        st = o.get("steps") or []
        if not 2 <= len(st) <= 14:
            return f"{len(st)} steps"
        if any(parse_ts(s.get("start")) is None or parse_ts(s.get("end")) is None for s in st):
            return "unparseable timestamps"
        return None

    seg = await _generate_json(gemini.WATCH_SYSTEM, SEGMENT_PROMPT.format(goal=goal) + "\n\n" + TRANSCRIPT_NOTE + "\n\n" + format_for_prompt(info),
                               SEGMENT_SCHEMA, effort=effort_seg, role="segment", check=seg_ok)
    steps = seg.get("steps") or []
    outline = "; ".join(f"{i}. {s.get('title')}" for i, s in enumerate(steps, 1))
    sem = asyncio.Semaphore(DETAIL_CONCURRENCY)

    async def detail(i: int, st: dict) -> dict:
        a, b = parse_ts(st.get("start")), parse_ts(st.get("end"))
        lines = [ln for ln in info["transcript"] if a is not None and b is not None and a - 15 <= ln["t"] <= b + 10]
        prompt = STEP_PROMPT.format(goal=goal, lesson=seg.get("title", ""), outline=outline, index=i, title=st.get("title", ""),
                                    start=st.get("start"), end=st.get("end"), instructions=st.get("instructions", ""),
                                    slice="\n".join(f"[{_mmss(ln['t'])}] {ln['text']}" for ln in lines) or "(no transcript lines)",
                                    stack_guide=gemini.STACK_GUIDE)
        async with sem:
            # too many optional fields for structured output: skip the guaranteed 400, validate client-side
            d = await _generate_json(gemini.WATCH_SYSTEM, prompt, STEP_DETAIL_SCHEMA, effort=effort_detail, structured=False,
                                     role="detail", check=lambda o: None if o.get("checks") else "no checks")
        return {**st, **{k: v for k, v in d.items() if k not in ("start", "end", "title", "instructions")}}

    filled = await asyncio.gather(*(detail(i, st) for i, st in enumerate(steps, 1)))
    return {"title": seg.get("title", ""), "libraries": seg.get("libraries", []), "steps": list(filled)}


async def adapt_checks(goal: str, draft_steps: list[dict], workdir_summary: str, feedback: list[str] | None = None) -> dict:
    # round 1 on the cheap model; a retry round (lint feedback = the quality check failed) goes to Opus
    return await _generate_json(gemini.ADAPT_SYSTEM, gemini.adapt_prompt(goal, draft_steps, workdir_summary, feedback), ADAPTED_SCHEMA,
                                effort=os.environ.get("LESSON_CLAUDE_EFFORT_ADAPT", "low"), structured=False,
                                role="adapt" if not feedback else "escalate")
