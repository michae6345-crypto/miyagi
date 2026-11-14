"""explain(): learner asks "why?" (or types a question) → `card` payload."""

from __future__ import annotations

import logging
import re

from . import llm, web
from .common import (
    citation_menu,
    clamp_title,
    clamp_words,
    fmt_t,
    get_lesson,
    number_lines,
    resolve_citation,
    step_brief,
    system_blocks,
)
from .diagnose import COACH_SYSTEM, LAST
from .metrics import summarize

log = logging.getLogger("coach.explain")

EXPLAIN_TASK = """
TASK NOW: explain, do not diagnose. Answer the learner's question (or, if there is no question, explain the reason behind the current card) for someone who just watched the tutorial. At most 60 words, plain prose, one idea per sentence, intuition first, then the precise statement (no labels such as "Intuition:"; just the sentences). If one of the step's `explanations` moments in the video covers the topic, set explanation_index to its 0-based index in the step's explanations list, else -1. citation_id from the CITATIONS list or "none"."""

CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "explanation_index": {"type": "integer"},
        "citation_id": {"type": "string"},
    },
    "required": ["title", "body", "explanation_index", "citation_id"],
    "additionalProperties": False,
}

_STOP = {"the", "a", "an", "of", "to", "is", "why", "what", "how", "does", "do", "in", "on", "and", "it", "this", "my", "i", "for", "with"}


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Zβ_]+", (s or "").lower()) if w not in _STOP and len(w) > 1}


def match_explanation(step: dict, text: str) -> int:
    """Index of the step explanation whose topic best overlaps `text`, or -1."""
    q = _tokens(text)
    best, best_i = 0, -1
    for i, e in enumerate(step.get("explanations") or []):
        overlap = len(q & _tokens(e.get("topic", "")))
        if overlap > best:
            best, best_i = overlap, i
    return best_i


def video_jump(step: dict, idx: int) -> dict | None:
    exps = step.get("explanations") or []
    if 0 <= idx < len(exps) and exps[idx].get("t") is not None:
        t = float(exps[idx]["t"])
        return {"t": t, "label": f"Explained at {fmt_t(t)}"}
    return None


async def explain(step: dict, question: str | None = None, context: dict | None = None) -> dict:
    """`context` may hold: code_excerpt, metrics_summary, offtrack (last card), lesson."""
    ctx = context or {}
    lesson = ctx.get("lesson") or get_lesson()
    last = ctx.get("offtrack") or LAST.get(step.get("id", ""))
    kind = "answer" if question else "explain"
    about = question or (f"Why? (about the card: {last.get('title')} — {last.get('body')})" if last else f"Explain the idea behind this step: {step.get('title')}")

    metrics_text, _ = summarize(ctx.get("metrics_summary"))
    if question:  # ground a free question in live docs/community pages
        libs = ((lesson or {}).get("lesson") or {}).get("libraries") or {}
        lib, sym = web.detect(question, ctx.get("code_excerpt", ""), libs)
        sources = await web.gather(lib, sym, question, timeout=6.0)
    else:  # "why?" about the card: reuse what diagnose() already fetched
        sources = ((last or {}).get("_meta") or {}).get("web_sources") or []
    user = "\n\n".join(
        x
        for x in [
            f"CURRENT STEP:\n{step_brief(step)}",
            f"CURRENT CARD: {last.get('title')} — {last.get('body')}" if last else "",
            f"METRICS:\n{metrics_text}" if ctx.get("metrics_summary") is not None else "",
            f"LEARNER CODE:\n{number_lines(ctx['code_excerpt'], 80)}" if ctx.get("code_excerpt") else "",
            f"WEB SOURCES (fetched live):\n{web.sources_text(sources)}" if sources else "",
            f"CITATIONS you may use:\n{citation_menu(lesson, sources)}",
            f"LEARNER ASKS: {about}",
        ]
        if x
    )
    det_idx = match_explanation(step, about)
    try:
        res = await llm.structured_call(
            purpose="explain",
            model=llm.OPUS,
            system=system_blocks(COACH_SYSTEM + EXPLAIN_TASK, lesson),
            user_text=user,
            schema=CARD_SCHEMA,
            effort="low",
            max_tokens=8000,
            timeout=40.0,
        )
        d = res.data
        idx = d.get("explanation_index", -1)
        if not (0 <= idx < len(step.get("explanations") or [])):
            idx = det_idx
        card = {
            "stepId": step.get("id"),
            "kind": kind,
            "title": clamp_title(d.get("title", "")),
            "body": clamp_words(d.get("body", ""), 64),
        }
        cit = resolve_citation(d.get("citation_id"), lesson, sources)
        meta = {"web_sources": [x["url"] for x in sources], "model": res.model, "latency_s": round(res.latency_s, 2), "usage": res.usage, "source": res.source}
    except llm.CoachLLMError as e:
        if not llm.demo_mode():
            raise llm.CoachUnavailable(f"explanation unavailable: {e}") from e
        log.warning("explain failed (%s); DEMO=1 so using the offline card", e)
        idx = det_idx
        body = last.get("body") if last else step.get("instructions", "")
        card = {"stepId": step.get("id"), "kind": kind, "title": clamp_title(last.get("title") if last else step.get("title", "")), "body": body}
        cit = last.get("citation") if last else None
        meta = {"fallback_reason": str(e)}
    if jump := video_jump(step, idx):
        card["videoJump"] = jump
    if cit:
        card["citation"] = cit  # extra field (contract allows additions)
    card["_meta"] = meta
    return card
