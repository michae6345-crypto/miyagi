"""Claude does everything except watching videos (Michael's rule, Sat ~2:30 PM):
plans and runs the searches (server-side web search tool), scores every candidate, and reads
the top non-video resources. Gemini only skims YouTube videos.

Search rule: a candidate counts only if its URL appears in the
web_search tool's actual result blocks. URLs Claude writes in its answer that the tool never
returned are dropped.

Model: claude-haiku-5-5 with web_search_20250305 (measured Sat 14:00: 7.4 s / 18 results vs
13.8 s for claude-sonnet-5-5 + web_search_20260209 on the same query). Override with
FINDER_CLAUDE_MODEL / FINDER_CLAUDE_SEARCH_TOOL.
"""

from __future__ import annotations

import json
import logging
import os
import re

import anthropic

log = logging.getLogger("finder.claude")

_clients: dict[str, anthropic.AsyncAnthropic] = {}


def model() -> str:
    return os.environ.get("FINDER_CLAUDE_MODEL", "claude-haiku-5-5")


def search_tool() -> str:
    return os.environ.get("FINDER_CLAUDE_SEARCH_TOOL", "web_search_20250305")


def client(key: str) -> anthropic.AsyncAnthropic:
    if key not in _clients:
        # no SDK retries: a retried timeout doubles the wait; the finder has its own fallbacks
        _clients[key] = anthropic.AsyncAnthropic(api_key=key, max_retries=0, timeout=30)
    return _clients[key]


# --------------------------------------------------------------------------- search

SEARCH_SYSTEM = """You find the best hands-on learning resources on the web for one learner.
Use the web_search tool (2-3 focused searches: one for YouTube code-along videos, one for written
tutorials or notebooks with runnable code, and one more only if needed). Prefer resources that
teach exactly the learner's goal step by step with code, are current, and are free to access.
Then answer with ONLY a JSON array in a ```json block, best first, at most 10 items:
[{"url": "...", "kind": "video|blog|notebook|repo|paper", "why": "<= 12 words: why it fits, caveat if any"}]
Every url MUST be copied exactly from your search results. Never write a URL from memory."""


def _norm(url: str) -> str:
    u = url.strip().rstrip("/").lower()
    u = re.sub(r"^https?://(www\.|m\.)?", "", u)
    return u.split("#")[0]


def _picks_from_text(text: str) -> list[dict]:
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S) or re.search(r"(\[\s*\{.*\}\s*\])", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict) and isinstance(d.get("url"), str)]


async def search(key: str, goal: str, *, timeout: float = 12.0, max_uses: int = 3) -> tuple[list[dict], dict]:
    """Claude searches the web for the goal. Returns (candidates, info).

    candidates: [{url, title, kind?, why?, page_age?}], only URLs from the tool's results:
    Claude's picks first (in its order, with its 'why'), then the remaining search results."""
    resp = await client(key).messages.create(
        model=model(),
        max_tokens=3000,
        system=SEARCH_SYSTEM,
        tools=[{"type": search_tool(), "name": "web_search", "max_uses": max_uses}],
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": f"Learner's goal: {goal}"}],
        timeout=timeout,
    )
    results: dict[str, dict] = {}
    queries: list[str] = []
    text = ""
    for b in resp.content:
        if b.type == "server_tool_use":
            q = (b.input or {}).get("query") if isinstance(b.input, dict) else None
            if q:
                queries.append(q)
        elif b.type == "web_search_tool_result":
            if isinstance(b.content, list):  # an error is an object, results are a list
                for r in b.content:
                    url = getattr(r, "url", None)
                    if url and _norm(url) not in results:
                        results[_norm(url)] = {"url": url, "title": getattr(r, "title", "") or "", "page_age": getattr(r, "page_age", None)}
            else:
                log.info("web_search error: %s", getattr(b.content, "error_code", b.content))
        elif b.type == "text":
            text += b.text
    out, used = [], set()
    for p in _picks_from_text(text):
        n = _norm(p["url"])
        hit = results.get(n)
        if not hit or n in used:
            if not hit:
                log.info("dropping model-written URL not in search results: %s", p["url"])
            continue
        used.add(n)
        out.append({**hit, "kind": p.get("kind"), "why": str(p.get("why") or "")[:160], "picked": True})
    for n, r in results.items():  # the rest of what the search engine returned is real too
        if n not in used:
            out.append({**r, "picked": False})
    info = {"queries": queries, "stop_reason": resp.stop_reason, "results": len(results), "picked": len(used),
            "usage": {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}}
    return out, info


# --------------------------------------------------------------------------- triage fallback

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
                    "style": {"type": "string", "enum": ["coding", "no-code", "conceptual"]},
                },
                "required": ["id", "score", "reason", "style"],
                "additionalProperties": False,
            },
        },
        "goal_is_coding": {"type": "boolean"},
    },
    "required": ["items", "goal_is_coding"],
    "additionalProperties": False,
}


async def score(key: str, goal: str, cands: list[dict], *, system: str, prompt: str, timeout: float = 8.0) -> dict[str, dict]:
    """Same rubric as gemini.score (the prompts are passed in so both stay identical)."""
    items = [
        {"id": c["id"], "kind": c["kind"], "title": c["title"][:160], "meta": c.get("meta", ""), "description": (c.get("description") or "")[:350]}
        for c in cands
    ]
    resp = await client(key).messages.create(
        model=model(),
        max_tokens=4000,
        system=system,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCORE_SCHEMA}},
        messages=[{"role": "user", "content": prompt.format(goal=goal, items=json.dumps(items, ensure_ascii=False))}],
        timeout=timeout,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to score")
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = json.loads(text)
    goal_coding = bool(data.get("goal_is_coding"))
    return {i["id"]: {"score": max(0, min(100, int(i.get("score", 0)))), "reason": i.get("reason", ""), "style": i.get("style"),
                      "goal_is_coding": goal_coding} for i in data.get("items", []) if i.get("id")}


# --------------------------------------------------------------------------- page read (non-video)

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "teaches_goal": {"type": "boolean"},
        "score": {"type": "integer"},
        "summary": {"type": "string"},
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "code": {"type": "string"},
    },
    "required": ["teaches_goal", "score", "summary", "prerequisites", "code"],
    "additionalProperties": False,
}

READ_SYSTEM = """You read a web page (tutorial, notebook, repository README or paper) for a learner.
Judge only from the page text given. teaches_goal: does it actually teach the learner's goal step by step?
score 0-100: exact topic, runnable code, clear, current libraries.
summary: at most 12 words, concrete, e.g. "Teaches DDPM end to end, PyTorch, needs UNet basics".
prerequisites: 0-4 short items the learner must know first. code: one short line on what code it gives
(language, libraries, notebook or script), or "no code"."""

READ_PROMPT = """Learner's goal: {goal}
Page: {title} ({url})

<page_text>
{text}
</page_text>"""


async def read(key: str, goal: str, item: dict, text: str, *, timeout: float = 8.0) -> dict:
    resp = await client(key).messages.create(
        model=model(),
        max_tokens=2000,
        system=READ_SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": READ_SCHEMA}},
        messages=[{"role": "user", "content": READ_PROMPT.format(goal=goal, title=item["title"], url=item["url"], text=text[:14000])}],
        timeout=timeout,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to read the page")
    out = json.loads(next((b.text for b in resp.content if b.type == "text"), "{}"))
    words = str(out.get("summary") or "").strip().rstrip(".").split()
    return {
        "teaches_goal": bool(out.get("teaches_goal")),
        "score": max(0, min(100, int(out.get("score") or 0))),
        "summary": " ".join(words[:12]),
        "prerequisites": [str(p)[:60] for p in (out.get("prerequisites") or [])][:4],
        "code": str(out.get("code") or "")[:140],
    }


def failure(e: BaseException) -> str:
    """Why Claude didn't answer, in the words a row shows."""
    if isinstance(e, anthropic.RateLimitError):
        return "rate limit"
    if isinstance(e, (anthropic.APITimeoutError,)) or "timed out" in str(e).lower():
        return "timeout"
    if isinstance(e, anthropic.APIStatusError) and e.status_code >= 500:
        return "overloaded"
    return "error"
