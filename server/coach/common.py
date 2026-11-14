"""Shared helpers: lesson context (prompt-cached), word clamps, citations, payload shaping."""

from __future__ import annotations

import json
import re
from typing import Any

from .playbook import CITATIONS

ACTIONS_ORDER = ("explain", "show_me", "hint", "apply_fix")

_lesson: dict | None = None


def set_lesson(graph: dict | None) -> None:
    """Orchestrator calls this once per lesson so every coach call shares a cached prefix."""
    global _lesson
    _lesson = graph


def get_lesson() -> dict | None:
    return _lesson


def lesson_context_text(lesson: dict | None) -> str:
    """Deterministic rendering (sorted keys) so the prompt-cache prefix is byte-stable."""
    if not lesson:
        return "LESSON CONTEXT: (none provided)"
    slim = {
        "lesson": lesson.get("lesson", {}),
        "sources": lesson.get("sources", []),
        "steps": [
            {k: s.get(k) for k in ("id", "index", "title", "instructions", "checks", "hints", "common_mistakes", "explanations") if s.get(k) is not None}
            for s in lesson.get("steps", [])
        ],
    }
    return "LESSON CONTEXT (the tutorial the learner is following):\n" + json.dumps(slim, sort_keys=True, ensure_ascii=False, indent=1)


def system_blocks(instructions: str, lesson: dict | None) -> list[dict]:
    """[stable instructions+playbook] [lesson context] — both cache breakpoints."""
    return [
        {"type": "text", "text": instructions, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": lesson_context_text(lesson), "cache_control": {"type": "ephemeral"}},
    ]


def allowed_citations(lesson: dict | None, sources: list[dict] | None = None) -> dict[str, dict[str, str]]:
    """Whitelist: playbook papers/docs, the lesson's own sources, and this call's live web sources."""
    cites = dict(CITATIONS)
    for src in (lesson or {}).get("sources", []):
        if src.get("url"):
            cites[f"source:{src['id']}"] = {"label": src.get("title", src["url"]), "url": src["url"]}
    for i, s in enumerate(sources or []):
        cites[f"web:{i}"] = {"label": s.get("title") or s["url"], "url": s["url"]}
    return cites


def citation_menu(lesson: dict | None, sources: list[dict] | None = None) -> str:
    return "\n".join(f"- {cid}: {c['label']} <{c['url']}>" for cid, c in allowed_citations(lesson, sources).items())


def resolve_citation(cid: str | None, lesson: dict | None, sources: list[dict] | None = None) -> dict | None:
    if not cid or cid == "none":
        return None
    c = allowed_citations(lesson, sources).get(cid)
    return {"label": c["label"], "url": c["url"]} if c else None


def clamp_words(text: str, limit: int) -> str:
    """Trim to `limit` words, preferring a sentence boundary; never mid-word."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    words = text.split(" ")
    if len(words) <= limit:
        return text
    cut = " ".join(words[:limit])
    m = re.search(r"^(.*[.!?])\s", cut + " ")
    if m and len(m.group(1).split()) >= limit // 2:
        return m.group(1)
    return cut.rstrip(",;:—-") + "…"


def clamp_title(text: str, limit: int = 8) -> str:
    t = clamp_words(text, limit).rstrip(".…")
    return t


def order_actions(actions: list[str], has_diff: bool) -> list[str]:
    s = {a for a in actions if a in ACTIONS_ORDER}
    s |= {"explain", "hint"}
    if has_diff:
        s.add("apply_fix")
    else:
        s.discard("apply_fix")
    return [a for a in ACTIONS_ORDER if a in s]


def step_brief(step: dict) -> str:
    keep = {k: step.get(k) for k in ("id", "title", "instructions", "checks", "hints", "common_mistakes", "explanations", "targets") if step.get(k)}
    return json.dumps(keep, sort_keys=True, ensure_ascii=False, indent=1)


def fmt_t(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def number_lines(code: str, max_lines: int = 160) -> str:
    lines = (code or "").splitlines()[:max_lines]
    return "\n".join(f"{i:>4}| {line}" for i, line in enumerate(lines, start=1))


def failed_checks_text(failed_checks: list[Any]) -> str:
    out = []
    for c in failed_checks or []:
        if isinstance(c, dict):
            out.append(f"- {c.get('label') or c.get('checkId') or c.get('id')}: {c.get('status', 'fail')}" + (f" ({c['detail']})" if c.get("detail") else ""))
        else:
            out.append(f"- {c}")
    return "\n".join(out) or "- (none reported)"
