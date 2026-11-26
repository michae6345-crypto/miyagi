"""Clip over-long learner text (a pasted essay as the topic, a huge ask) where the engine consumes it.

The wire contract has no length limit, so the engine clips (never rejects): a topic or search query to
MAX_TOPIC_CHARS (at a word boundary), an ask or action text to MAX_ASK_CHARS. One log line per clip."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

MAX_TOPIC_CHARS = 500
MAX_ASK_CHARS = 4000


def clip_text(text: str | None, limit: int, *, what: str = "text", word_boundary: bool = False) -> str | None:
    """`text` cut to at most `limit` characters; None and short text come back unchanged. With `word_boundary` the cut
    backs up to the last whitespace (when that keeps at least half of the limit) so no word is split."""
    if text is None or len(text) <= limit:
        return text
    cut = text[:limit]
    if word_boundary and not text[limit].isspace():
        i = max(cut.rfind(" "), cut.rfind("\n"), cut.rfind("\t"))
        if i >= limit // 2:
            cut = cut[:i]
    cut = cut.rstrip()
    log.warning("clipped %s from %d to %d characters", what, len(text), len(cut))
    return cut


def clip_topic(text: str, limit: int = MAX_TOPIC_CHARS) -> str:
    return clip_text(text, limit, what="topic", word_boundary=True) or ""


def clip_ask(text: str | None, limit: int = MAX_ASK_CHARS) -> str | None:
    return clip_text(text, limit, what="ask text")
