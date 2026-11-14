"""fix_outdated(): code from a tutorial broke on a newer library/tool → the official fix.

Works for any error text seen on screen (Python, JS/TS, CLI tools):
1. a small offline table of well-known removals (instant, no network);
2. detect (library, symbol) from the error → live web: official docs/changelog
   (`web.docs_for`) + community posts (`web.community_signals`) → Claude proposes the fix
   using ONLY those pages and cites one of them.

Returns an offtrack-shaped dict (title, body, diff, citation, actions, severity) the
orchestrator can send after adding `stepId`; None when nothing trustworthy was found.
"""

from __future__ import annotations

import json
import logging
import re

from . import llm, web
from .common import clamp_title, clamp_words

log = logging.getLogger("coach.outdated")

# (error regex, title, body, yours, expected, source label, source url)
KNOWN: list[tuple[str, str, str, str, str, str, str]] = [
    (
        r"module 'numpy' has no attribute '(float|int|bool|object)'",
        "np.float was removed in NumPy 1.24",
        "NumPy 1.24 removed the np.float/np.int aliases the tutorial uses. Use the builtin float/int, or np.float64.",
        "np.float",
        "float  # or np.float64",
        "NumPy 1.24 release notes",
        "https://numpy.org/doc/stable/release/1.24.0-notes.html",
    ),
    (
        r"'DataFrame' object has no attribute 'append'",
        "DataFrame.append was removed in pandas 2.0",
        "pandas 2.0 removed DataFrame.append. Collect the rows and combine them once with pd.concat.",
        "df = df.append(row, ignore_index=True)",
        "df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)",
        "pandas 2.0.0 release notes",
        "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html",
    ),
]


def _payload(title: str, body: str, yours: str, expected: str, citation: dict, via: str, **meta) -> dict:
    out = {
        "severity": "fail",
        "title": clamp_title(title),
        "body": clamp_words(body, 34),
        "citation": citation,
        "actions": ["explain", "hint"],
        "_meta": {"route": "fix_outdated", "via": via, **meta},
    }
    if expected:
        out["diff"] = {"expected": expected, "yours": yours}
        out["actions"] = ["explain", "hint", "apply_fix"]
    return out


def _known(error_text: str) -> dict | None:
    for rx, title, body, yours, expected, label, url in KNOWN:
        if re.search(rx, error_text):
            return _payload(title, body, yours, expected, {"label": label, "url": url}, via="known")
    return None


FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "yours": {"type": "string"},
        "expected": {"type": "string"},
        "source_index": {"type": "integer"},
    },
    "required": ["found", "title", "body", "yours", "expected", "source_index"],
    "additionalProperties": False,
}

FIX_SYSTEM = """Code copied from a tutorial fails because the learner has a newer version of a library, framework or CLI tool (any language). Using ONLY the web pages provided, state the fix.
- found=false if the pages do not clearly document this change or fix; never guess from memory.
- Prefer an official docs/changelog page as the source; use a community page (Stack Overflow, GitHub issue) only if no official page covers it.
- title: 3 to 7 words naming what changed. body: at most 30 words: what changed (and in which version, if the page says), then what to write instead.
- yours: the old code as it appears in the error or the learner's code; expected: the replacement, at most 3 lines, same language and style. Both "" if the fix is not a code change (e.g. a CLI flag or config).
- source_index: 0-based index of the page that documents the fix."""


async def fix_outdated(error_text: str, libraries: dict | list | None = None, *, code: str = "", command: str = "") -> dict | None:
    """`libraries`: {name: tutorial_version} from the step graph, or a list of names (may be empty).

    Returns the fix, or None when the docs were read and none of them documents a fix.
    Raises `OutdatedFixUnavailable` (with `.reason`) when it could not search or read at all.
    """
    if hit := _known(error_text):
        return hit
    if not web.configured():
        raise llm.OutdatedFixUnavailable("web search not configured (Bright Data key and SERP/Unlocker zones)")
    lib, sym = web.detect(error_text, code, libraries, command)
    line = web.error_line(error_text)
    pages = await web.gather(lib, sym, f"{lib} {line}".strip(), error=line, timeout=12.0)
    if not pages:
        raise llm.OutdatedFixUnavailable(f"no docs or community pages found for {lib or 'unknown library'} {sym}".strip())
    versions = json.dumps(libraries, sort_keys=True) if isinstance(libraries, dict) else ", ".join(libraries or [])
    user = (
        f"Library/tool: {lib or 'unknown'} (symbol: {sym or 'unknown'}); tutorial versions: {versions or 'unknown'}\n"
        f"Error seen on screen:\n{error_text[-1500:]}\n"
        + (f"\nLearner code excerpt:\n{code[:2000]}\n" if code else "")
        + "\nPAGES:\n"
        + web.sources_text(pages)
    )
    try:
        res = await llm.structured_call(
            purpose="fix_outdated",
            model=llm.OPUS,
            system=[{"type": "text", "text": FIX_SYSTEM}],
            user_text=user,
            schema=FIX_SCHEMA,
            effort="low",
            max_tokens=6000,
        )
    except llm.CoachLLMError as e:
        raise llm.OutdatedFixUnavailable(f"could not read the docs: {e}") from e
    d = res.data
    i = d.get("source_index", -1)
    if not d.get("found") or not (0 <= i < len(pages)):
        log.info("fix_outdated: pages fetched but none documents a fix for %s %s", lib, sym)
        return None
    src = pages[i]
    return _payload(
        d["title"], d["body"], d.get("yours", ""), d.get("expected", ""),
        {"label": src.get("title") or src["url"], "url": src["url"]},
        via="web", library=lib, symbol=sym, source_kind=src.get("kind"), model=res.model,
    )
