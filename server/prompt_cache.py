"""Prompt caching helpers: where a cache breakpoint goes, so every Claude call shapes its request the same way.

Anthropic rules these helpers follow: at most 4 breakpoints per request; the cached prefix is tools, then system,
then messages, and must be byte-identical across calls (nothing volatile before a breakpoint: no timestamps, ids
or random fence nonces, use server.untrusted.wrap_stable); a prefix under the model's minimum (about 1024 tokens
on Sonnet, 2048 on Haiku) just does not cache, with no error, so short prompts carry a breakpoint at no cost.
"""

from __future__ import annotations

from typing import Any

EPHEMERAL: dict[str, str] = {"type": "ephemeral"}
MAX_BREAKPOINTS = 4


def text_block(text: str, *, cache: bool = False) -> dict[str, Any]:
    b: dict[str, Any] = {"type": "text", "text": text}
    if cache:
        b["cache_control"] = dict(EPHEMERAL)
    return b


def system_blocks(*texts: str) -> list[dict[str, Any]] | str:
    """A system prompt as text blocks, the breakpoint on the last non-empty one (put the most stable text first and
    a per-lesson block after it, so a lesson's calls share both). "" when there is nothing."""
    parts = [t for t in texts if t]
    if not parts:
        return ""
    return [text_block(t, cache=(i == len(parts) - 1)) for i, t in enumerate(parts)]


def user_blocks(prefix: str, rest: str = "") -> list[dict[str, Any]] | str:
    """A user message whose stable `prefix` (a transcript, a lesson outline) is a cached block, followed by the
    volatile `rest`. Joined, the two read as prefix + blank line + rest."""
    if not prefix:
        return rest
    if not rest:
        return [text_block(prefix, cache=True)]
    return [text_block(prefix + "\n\n", cache=True), text_block(rest)]


def cache_tools(tools: list[dict] | None) -> list[dict] | None:
    """`tools` with a breakpoint on the last one (the whole tool list is the first part of the prefix)."""
    if not tools:
        return tools
    out = [dict(t) for t in tools]
    out[-1]["cache_control"] = dict(EPHEMERAL)
    return out


def count_breakpoints(kwargs: dict[str, Any]) -> int:
    """Number of cache_control markers in a request (tools, system, message content blocks)."""
    n = 0
    for t in kwargs.get("tools") or []:
        n += isinstance(t, dict) and "cache_control" in t
    sysm = kwargs.get("system")
    for b in sysm if isinstance(sysm, list) else []:
        n += isinstance(b, dict) and "cache_control" in b
    for m in kwargs.get("messages") or []:
        c = m.get("content") if isinstance(m, dict) else None
        for b in c if isinstance(c, list) else []:
            n += isinstance(b, dict) and "cache_control" in b
    return n


def prefix_through_breakpoint(kwargs: dict[str, Any]) -> str:
    """The request's cacheable prefix as text: tools, then system, then message blocks, up to and including the
    last block that carries cache_control. For tests: two calls with different volatile input must give the
    same string."""
    import json

    out: list[str] = []
    last = -1
    items: list[tuple[str, bool]] = []
    for t in kwargs.get("tools") or []:
        items.append((json.dumps(t, sort_keys=True), isinstance(t, dict) and "cache_control" in t))
    sysm = kwargs.get("system")
    if isinstance(sysm, str):
        items.append((sysm, False))
    for b in sysm if isinstance(sysm, list) else []:
        items.append((b.get("text", ""), "cache_control" in b))
    for m in kwargs.get("messages") or []:
        c = m.get("content")
        if isinstance(c, str):
            items.append((c, False))
        for b in c if isinstance(c, list) else []:
            items.append((b.get("text", "") if b.get("type") == "text" else json.dumps(b, sort_keys=True), "cache_control" in b))
    for i, (_, marked) in enumerate(items):
        if marked:
            last = i
    out = [t for t, _ in items[: last + 1]]
    return "\x1f".join(out)


def as_text(x: Any) -> str:
    """A prompt as plain text, whether it is a string or a list of content blocks (cache_control left out). For
    tests and logs that look at what a prompt says, not how it is split."""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in x)
    return str(x or "")
