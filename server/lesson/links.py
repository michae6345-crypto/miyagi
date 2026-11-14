"""Links in lesson text must be real: a URL is kept only if the video's own page (description,
chapters) or transcript mentions it, or it answers a live HEAD/GET with 2xx/3xx. Models invent
plausible repo URLs (e.g. github.com/<real user>/<made-up repo>); a learner told to clone a 404
is stuck at step 1."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

log = logging.getLogger("server.lesson")

URL_RE = re.compile(r"https?://[^\s<>()\[\]'\"`]+")
CHECK_TIMEOUT_S = 5.0
_TEXT_FIELDS = ("instructions",)
_LIST_FIELDS = ("hints", "common_mistakes")


def _norm(url: str) -> str:
    u = url.rstrip(".,;:!?")
    u = re.sub(r"\.git$", "", u)
    return u.rstrip("/").lower()


def urls_in_steps(steps: list[dict]) -> set[str]:
    out: set[str] = set()
    for s in steps:
        for f in _TEXT_FIELDS:
            out |= {u.rstrip(".,;:!?") for u in URL_RE.findall(s.get(f) or "")}
        for f in _LIST_FIELDS:
            for item in s.get(f) or []:
                out |= {u.rstrip(".,;:!?") for u in URL_RE.findall(item if isinstance(item, str) else "")}
    return out


async def _resolves(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.head(url)
        if r.status_code in (403, 405, 501):  # some hosts refuse HEAD
            r = await client.get(url)
        return r.status_code < 400
    except Exception:  # noqa: BLE001  unreachable counts as bad
        return False


async def find_bad_urls(steps: list[dict], known_text: str, checked: dict[str, bool] | None = None) -> set[str]:
    """URLs in the steps that the video never mentions and that don't resolve. `checked` caches results."""
    checked = {} if checked is None else checked
    known = known_text.lower()
    todo = [u for u in urls_in_steps(steps) if _norm(u) not in known and u not in checked]
    if todo:
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_S, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 (lesson link check)"}) as c:
            results = await asyncio.gather(*(_resolves(c, u) for u in todo))
        checked.update(zip(todo, results))
    return {u for u in urls_in_steps(steps) if checked.get(u) is False}


def url_problems(steps: list[dict], bad: set[str]) -> list[str]:
    out = []
    for s in steps:
        for u in sorted(bad):
            if u in (s.get("instructions") or ""):
                out.append(f"{s.get('id', '?')}: links {u}, which the video never mentions and which does not resolve; "
                           "give the real link from the description, or the exact commands/files that recreate that starting state")
    return out


def strip_bad_urls(steps: list[dict], bad: set[str]) -> list[str]:
    """Remove dead invented links from the lesson text; returns warnings."""
    warnings = []
    for s in steps:
        text = s.get("instructions") or ""
        for u in bad:
            if u in text:
                text = re.sub(r"\s*\(?\s*" + re.escape(u) + r"\s*\)?", "", text)
                warnings.append(f"{s.get('id', '?')}: removed a link that does not resolve ({u})")
        s["instructions"] = re.sub(r"\s{2,}", " ", text).strip()
        for f in _LIST_FIELDS:
            items = s.get(f) or []
            kept = [i for i in items if not any(u in i for u in bad)]
            if len(kept) != len(items):
                warnings.append(f"{s.get('id', '?')}: dropped {len(items) - len(kept)} {f} with a dead link")
            s[f] = kept
    return warnings
