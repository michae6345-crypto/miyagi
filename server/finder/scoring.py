"""The finder's scoring rubric, shared by Claude (the default scorer) and the opt-in Gemini fallback, plus the
keyword query plan and small helpers. No model SDK here: core.py imports it on every search."""

from __future__ import annotations

import re

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


STYLES = ["coding", "no-code", "conceptual"]

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
4. When a video comes with `chapters` and a `transcript_excerpt`, judge what it really teaches from them (they outweigh
   the title and description): does the presenter write and run code, which libraries, does it reach the goal.
style: "coding" (writes and runs real code), "no-code" (Zapier, Botpress, GPT builders, drag-and-drop, prompting a
product), or "conceptual" (explains ideas, no code to follow).
reason: at most 12 words. Start with WHY it matches (or doesn't), then a caveat if any.
Examples: "Implements GPT from scratch in PyTorch; 2 hours, chapters" / "No-code Zapier bots, not building an LLM" /
"Explains transformers conceptually; no code to follow"."""

SCORE_PROMPT = """Learner's goal: {goal}

Candidates (JSON):
{items}

Return one item per candidate id."""


def clamp(v) -> int:
    try:
        return max(0, min(100, int(v)))
    except (TypeError, ValueError):
        return 0


def short(reason: str, words: int = 12) -> str:
    w = (reason or "").strip().rstrip(".").split()
    return " ".join(w[:words])
