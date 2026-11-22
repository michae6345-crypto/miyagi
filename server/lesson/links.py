"""Links in lesson text must be real: a URL is kept only if the video's own page (description,
chapters) or transcript mentions it, or it answers a live HEAD/GET with 2xx/3xx. Models invent
plausible repo URLs (e.g. github.com/<real user>/<made-up repo>); a learner told to clone a 404
is stuck at step 1.

The check goes through server.netsafe (claude/eng-keys-ssrf): the model writes these URLs, so a link (or a redirect)
to this Mac, the LAN or a cloud metadata address is never fetched; it counts as not resolving. The query string is
dropped before the check, so nothing a URL carries in it (a token, the learner's text) is sent anywhere."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from server import netsafe

log = logging.getLogger("server.lesson")

URL_RE = re.compile(r"https?://[^\s<>()\[\]'\"`]+")
CHECK_TIMEOUT_S = 5.0
_TEXT_FIELDS = ("instructions",)
_LIST_FIELDS = ("hints", "common_mistakes")


def _norm(url: str) -> str:
    u = url.rstrip(".,;:!?")
    u = re.sub(r"\.git$", "", u)
    return u.rstrip("/").lower()


_BACKTICKED = re.compile(r"`[^`]*`")
_LOCAL = re.compile(
    r"^https?://(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1?\]|[^/:]+\.localhost|[^/:]+\.local"
    r"|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+"
    r"|\[f[cd][0-9a-f]{0,2}:[0-9a-f:.]*\]|\[fe[89ab][0-9a-f]:[0-9a-f:.]*\])(:\d+)?([/?#]|$)", re.I)
GET_PEEK_BYTES = 64 * 1024  # a GET fallback only needs the status


def _checkable(text: str) -> set[str]:
    """URLs worth checking: not inside a backticked command (that's what the learner types), and not
    the learner's own dev server (localhost etc. is never up at build time)."""
    text = _BACKTICKED.sub(" ", text or "")
    urls = (u.rstrip(".,;:!?") for u in URL_RE.findall(text))  # strip sentence punctuation BEFORE the local test
    return {u for u in urls if not _LOCAL.match(u)}


def urls_in_steps(steps: list[dict]) -> set[str]:
    out: set[str] = set()
    for s in steps:
        for f in _TEXT_FIELDS:
            out |= _checkable(s.get(f) or "")
        for f in _LIST_FIELDS:
            for item in s.get(f) or []:
                out |= _checkable(item if isinstance(item, str) else "")
    return out


def _check_url(url: str) -> str:
    """The URL without its query string or fragment: what the existence check fetches."""
    return url.split("#", 1)[0].split("?", 1)[0]


async def _resolves(client: httpx.AsyncClient, url: str) -> bool:
    target = _check_url(url)
    try:
        r = await netsafe.head(target, client=client, timeout=CHECK_TIMEOUT_S)
        if r.status_code in (403, 405, 501):  # some hosts refuse HEAD
            r = await netsafe.get(target, client=client, timeout=CHECK_TIMEOUT_S, max_bytes=GET_PEEK_BYTES,
                                  truncate=True)
        if r.status_code == 400 and target != url.split("#", 1)[0]:
            return True  # the query we dropped was likely what the server needed (drive.google.com/uc?id=...)
        return r.status_code < 400
    except Exception:  # noqa: BLE001  unreachable (or refused by netsafe) counts as bad
        return False


async def find_bad_urls(steps: list[dict], known_text: str, checked: dict[str, bool] | None = None) -> set[str]:
    """URLs in the steps that the video never mentions and that don't resolve. `checked` caches results."""
    checked = {} if checked is None else checked
    known = known_text.lower()
    todo = [u for u in urls_in_steps(steps) if _norm(u) not in known and u not in checked]
    if todo:
        async with netsafe.async_client(timeout=CHECK_TIMEOUT_S,
                                        headers={"User-Agent": "Mozilla/5.0 (lesson link check)"}) as c:
            results = await asyncio.gather(*(_resolves(c, u) for u in todo))
        checked.update(zip(todo, results))
    return {u for u in urls_in_steps(steps) if checked.get(u) is False}


def _strip_outside_backticks(text: str, url: str) -> str:
    out, last = [], 0
    for m in _BACKTICKED.finditer(text):
        out.append(re.sub(r"\s*\(?\s*" + re.escape(url) + r"\s*\)?", " ", text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(re.sub(r"\s*\(?\s*" + re.escape(url) + r"\s*\)?", " ", text[last:]))
    return "".join(out)


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
            if u in _BACKTICKED.sub(" ", text):  # never cut into a backticked command
                text = _strip_outside_backticks(text, u)
                warnings.append(f"{s.get('id', '?')}: removed a link that does not resolve ({u})")
        s["instructions"] = re.sub(r"[ \t]{2,}", " ", text).strip()
        for f in _LIST_FIELDS:
            items = s.get(f) or []
            kept = [i for i in items if not any(u in _BACKTICKED.sub(" ", i) for u in bad)]
            if len(kept) != len(items):
                warnings.append(f"{s.get('id', '?')}: dropped {len(items) - len(kept)} {f} with a dead link")
            s[f] = kept
    return warnings
