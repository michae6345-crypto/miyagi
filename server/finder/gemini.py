"""Gemini: plan the per-source queries, score candidates for the learner's goal, and
skim the top videos (low fps, low media resolution) the way server/lesson passes YouTube URLs."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning)  # SDK docstring escapes

from google import genai
from google.genai import types

from .env import skim_models, triage_models

log = logging.getLogger("finder.gemini")
_clients: dict[str, genai.Client] = {}
# model -> monotonic time until which we skip it (free tier has per-model daily caps; 503 = overloaded)
_exhausted: dict[str, float] = {}
_why: dict[str, str] = {}  # model -> "quota" | "overloaded" | "unavailable"


def client(key: str) -> genai.Client:
    if key not in _clients:
        # no SDK-level retries: we have our own timeouts and a model fallback chain
        _clients[key] = genai.Client(
            api_key=key, http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
        )
    return _clients[key]


def _retry_after(err: Exception) -> float:
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", str(err))
    if not m:
        return 60.0
    h, mi, se = (float(x) if x else 0.0 for x in m.groups())
    return h * 3600 + mi * 60 + se


def _mark(model: str, e: Exception, now: float) -> None:
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        _exhausted[model], _why[model] = now + min(_retry_after(e), 3600), "quota"
    elif "503" in msg or "UNAVAILABLE" in msg:
        _exhausted[model], _why[model] = now + 4, "overloaded"  # transient: retry soon
    elif "404" in msg or "NOT_FOUND" in msg:
        _exhausted[model], _why[model] = now + 3600, "unavailable"


async def _json(key: str, models: list[str], parts: list, schema: dict, *, system: str, timeout: float,
                media_low: bool = False, hedge_after: float | None = 2.5) -> dict:
    """First good answer from the model chain within `timeout`. Models out of quota are skipped;
    on an error the next model starts at once; if the current one is slow (> hedge_after s)
    the next one starts too (hedged request) and the first answer wins."""
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
        temperature=0.2,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW if media_low else None,
    )
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    queue = [m for m in models if _exhausted.get(m, 0) <= loop.time()]
    if not queue:
        whys = sorted({_why.get(m, "unavailable") for m in models})
        raise RuntimeError(f"all Gemini models skipped ({'/'.join(whys)})")
    running: dict[asyncio.Task, tuple[str, float]] = {}
    last: Exception | None = None

    def start() -> None:
        m = queue.pop(0)
        coro = client(key).aio.models.generate_content(model=m, contents=types.Content(role="user", parts=parts), config=cfg)
        running[asyncio.ensure_future(coro)] = (m, loop.time())

    start()
    try:
        while running:
            left = end - loop.time()
            if left <= 0:
                break
            wait = min(left, hedge_after) if (hedge_after and queue) else left
            done, _ = await asyncio.wait(running, timeout=wait, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                if queue and hedge_after:
                    start()
                continue
            for t in done:
                m, t0 = running.pop(t)
                try:
                    resp = t.result()
                    out = json.loads(resp.text or "{}")
                    log.info("%s answered in %.1fs", m, loop.time() - t0)
                    return out
                except Exception as e:
                    last = e
                    log.info("%s failed in %.1fs: %s", m, loop.time() - t0, str(e)[:90])
                    _mark(m, e, loop.time())
            if not running and queue:
                start()
    finally:
        for t in running:
            t.cancel()
    if last is None:
        raise asyncio.TimeoutError(f"Gemini did not answer within {timeout:.1f}s")
    raise RuntimeError(f"Gemini failed: {str(last)[:160]}")


# --------------------------------------------------------------------------- query plan

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "youtube_query": {"type": "string"},
        "web_queries": {"type": "array", "items": {"type": "string"}},
        "github_query": {"type": "string"},
        "arxiv_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["topic", "youtube_query", "web_queries", "github_query", "arxiv_terms"],
}

PLAN_SYSTEM = "You write search queries that find hands-on coding tutorials. Output JSON only."
PLAN_PROMPT = """A learner wants to: {query}
Write search queries for each source:
- topic: the subject in <= 6 words, acronyms expanded (e.g. "physics-informed neural networks convection").
- youtube_query: what to type into YouTube to find a code-along tutorial video.
- web_queries: 2 web queries: one for a blog post / written tutorial with code, one for a Colab or Jupyter notebook.
- github_query: 2-4 keywords for GitHub repository search (no quotes, no qualifiers), e.g. "PINN convection".
- arxiv_terms: 2-3 short terms that must all appear in a relevant arXiv paper, e.g. ["physics-informed", "convection"]."""


async def plan(key: str, query: str, *, timeout: float = 4.0) -> dict:
    out = await _json(key, triage_models(), [types.Part(text=PLAN_PROMPT.format(query=query))], PLAN_SCHEMA, system=PLAN_SYSTEM, timeout=timeout)
    out["web_queries"] = [q for q in out.get("web_queries", []) if q.strip()][:3]
    out["arxiv_terms"] = [t for t in out.get("arxiv_terms", []) if t.strip()][:3]
    return out


STOP = set("a an the to on of in for with and or how do i learn learning train training build make using use my me want tutorial".split())


def heuristic_plan(query: str) -> dict:
    words = [w for w in re.findall(r"[\w\-+]+", query.lower()) if w not in STOP]
    kw = " ".join(words) or query
    return {
        "topic": kw,
        "youtube_query": query,
        "web_queries": [f"{kw} tutorial code", f"{kw} colab notebook"],
        "github_query": " ".join(words[:3]) or query,
        "arxiv_terms": words[:2],
    }


# --------------------------------------------------------------------------- triage

STYLES = ["coding", "no-code", "conceptual"]

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                    "style": {"type": "string", "enum": STYLES},
                },
                "required": ["id", "score", "reason", "style"],
            },
        },
        "goal_is_coding": {"type": "boolean"},
    },
    "required": ["items", "goal_is_coding"],
}

SCORE_SYSTEM = """You rank learning resources for one learner. Be strict and honest; only use the information given.

First decide what the goal really asks for. goal_is_coding = true when the learner wants to BUILD, implement,
train or code something (e.g. "build chat gpt" = implement a GPT-style language model in code, NOT use ChatGPT;
"build an LLM" = write the model and training code, NOT call an API or use a no-code tool).

Score 0-100 = how well this resource gets THIS learner to that goal by following along:
1. Topic match decides most of the score. A resource that only shares keywords ("ChatGPT", "AI", "agent", "LLM")
   but teaches a different thing (using ChatGPT, prompt tips, no-code bots, news, a product demo) is NOT a match:
   score it 0-30, however popular or polished.
2. Then: hands-on runnable code, clear, current libraries, sensible length (a long course is fine if it is
   structured, e.g. has chapters).
3. A page that only lists, embeds or links to someone else's tutorial (course aggregators like Class Central,
   link roundups, a Kaggle page pointing at a video) is not the tutorial itself: score it 40 at most.
style: "coding" (writes and runs real code), "no-code" (Zapier, Botpress, GPT builders, drag-and-drop, prompting a
product), or "conceptual" (explains ideas, no code to follow).
reason: at most 12 words. Start with WHY it matches (or doesn't), then a caveat if any.
Examples: "Implements GPT from scratch in PyTorch; 2 hours, chapters" / "No-code Zapier bots, not building an LLM" /
"Explains transformers conceptually; no code to follow"."""

SCORE_PROMPT = """Learner's goal: {goal}

Candidates (JSON):
{items}

Return one item per candidate id."""


async def score(key: str, goal: str, cands: list[dict], *, timeout: float = 7.0, hedge_after: float | None = 2.5) -> dict[str, dict]:
    items = [
        {"id": c["id"], "kind": c["kind"], "title": c["title"][:160], "meta": c.get("meta", ""), "description": (c.get("description") or "")[:350]}
        for c in cands
    ]
    out = await _json(
        key, triage_models(), [types.Part(text=SCORE_PROMPT.format(goal=goal, items=json.dumps(items, ensure_ascii=False)))],
        SCORE_SCHEMA, system=SCORE_SYSTEM, timeout=timeout, hedge_after=hedge_after,
    )
    goal_coding = bool(out.get("goal_is_coding"))
    return {i["id"]: {"score": clamp(i.get("score")), "reason": short(i.get("reason", "")), "style": i.get("style"),
                      "goal_is_coding": goal_coding} for i in out.get("items", []) if i.get("id")}


# --------------------------------------------------------------------------- video skim

SKIM_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "reason": {"type": "string"},
        "hands_on": {"type": "boolean"},
        "library": {"type": "string"},
        "outdated": {"type": "boolean"},
        "style": {"type": "string", "enum": STYLES},
    },
    "required": ["score", "reason", "hands_on", "outdated", "style"],
}

SKIM_SYSTEM = """You skim a tutorial video (sparse frames + audio) to judge if it fits a learner's goal.
Score 0-100. Topic match first: if the goal is to build/implement something and the video only USES a product
(ChatGPT, a no-code bot builder, Zapier...) or just talks about it, score 0-30.
Then: the presenter writes and runs real code on screen, clear, current libraries.
style: "coding" (real code written and run on screen), "no-code" (tools, drag-and-drop, prompting a product),
or "conceptual" (slides/talking, no code to follow).
reason: at most 12 words; say WHY it matches first, then length/library/caveat,
e.g. "Implements GPT in PyTorch on screen, 2 h, clear chapters".
outdated: true if the code uses clearly old APIs (e.g. TensorFlow 1.x sessions) or viewers report it no longer works."""

SKIM_PROMPT = """Learner's goal: {goal}
Video: "{title}" ({meta})
{comments}"""


async def skim(key: str, goal: str, video: dict, warnings_: list[str], *, timeout: float = 11.0, fps: float = 0.05) -> dict:
    comments = ""
    if warnings_:
        comments = "Viewer comments that mention problems:\n" + "\n".join(f"- {w}" for w in warnings_[:5])
    part = types.Part(file_data=types.FileData(file_uri=video["url"]), video_metadata=types.VideoMetadata(fps=fps))
    out = await _json(
        key, skim_models(),
        [part, types.Part(text=SKIM_PROMPT.format(goal=goal, title=video["title"], meta=video.get("meta", ""), comments=comments))],
        SKIM_SCHEMA, system=SKIM_SYSTEM, timeout=timeout, media_low=True, hedge_after=6.0,
    )
    out["score"] = clamp(out.get("score"))
    out["reason"] = short(out.get("reason", ""))
    return out


def failure(e: BaseException) -> str:
    """Why Gemini didn't answer, in the words the row shows: quota | timeout | error."""
    msg = str(e)
    if isinstance(e, asyncio.TimeoutError) or "did not answer" in msg:
        return "timeout"
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "(quota)" in msg:
        return "quota"
    if "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg:
        return "overloaded"
    return "error"


def clamp(v) -> int:
    try:
        return max(0, min(100, int(v)))
    except (TypeError, ValueError):
        return 0


def short(reason: str, words: int = 12) -> str:
    w = (reason or "").strip().rstrip(".").split()
    return " ".join(w[:words])
