"""Real search sources. Each returns raw candidates: dicts with at least url/title/kind/via.

Nothing here invents a URL: every candidate comes from a search index (YouTube's own
results page, Google via Bright Data SERP, DuckDuckGo, GitHub, arXiv) or from the result
blocks of Claude's web search tool (never from model-written text).
"""

from __future__ import annotations

import asyncio
import html as htmllib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import httpx

from . import brightdata, youtube
from .env import Keys

log = logging.getLogger("finder.sources")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

SKIP_DOMAINS = (
    "pinterest.", "facebook.com", "instagram.com", "tiktok.com", "twitter.com", "x.com", "quora.com",
    "linkedin.com", "amazon.", "duckduckgo.com", "bing.com", "google.com/search", "scribd.com",
    "researchgate.net", "sciencedirect.com", "coursehero.com", "chegg.com",
)


@dataclass
class Ctx:
    client: httpx.AsyncClient
    keys: Keys
    errors: list[str] = field(default_factory=list)
    used: set[str] = field(default_factory=set)  # which providers actually answered
    extra: dict = field(default_factory=dict)  # per-provider info for the cache file (e.g. Claude's queries)

    def note(self, msg: str) -> None:
        log.info(msg)
        self.errors.append(msg)


def classify(url: str) -> str:
    u = url.lower()
    host = urlparse(u).netloc
    if youtube.video_id(url) and ("youtube.com" in host or "youtu.be" in host):
        return "video"
    if "arxiv.org" in host or "openreview.net" in host or "proceedings." in host or "papers.nips.cc" in host or u.endswith(".pdf"):
        return "paper"
    if "colab.research.google.com" in host or "kaggle.com/code" in u or "nbviewer" in host or u.endswith(".ipynb") or "/blob/" in u and ".ipynb" in u:
        return "notebook"
    if host in ("github.com", "www.github.com", "gitlab.com") and len([p for p in urlparse(u).path.split("/") if p]) >= 2:
        return "repo"
    return "blog"


def skip(url: str) -> bool:
    u = url.lower()
    if not u.startswith("http"):
        return True
    if any(d in u for d in SKIP_DOMAINS):
        return True
    host = urlparse(u).netloc
    if ("youtube.com" in host or "youtu.be" in host) and not youtube.video_id(url):
        return True  # channels / playlists / search pages
    return False


# --------------------------------------------------------------------------- YouTube

async def youtube_search(ctx: Ctx, query: str, limit: int = 10) -> list[dict]:
    params = {"search_query": query, "hl": "en"}  # (the "videos only" sp filter made relevance worse)
    url = "https://www.youtube.com/results?" + urlencode(params)
    page, via = None, "youtube"
    if brightdata.available(ctx.keys):
        try:
            page = await brightdata.unlock(ctx.client, ctx.keys, url, timeout=10)
            ctx.used.add("brightdata-unlocker")
            via = "brightdata"
        except Exception as e:
            ctx.note(f"bright data unlocker (youtube) failed: {e}")
    if page is None:
        r = await ctx.client.get(url, timeout=8)
        r.raise_for_status()
        page = r.text
        ctx.used.add("youtube")
    data = youtube.initial_data(page)
    if not data:
        raise RuntimeError("YouTube results page had no ytInitialData")
    out = []
    for v in youtube.parse_search(data, limit=limit):
        out.append({**v, "kind": "video", "via": via})
    return out


# --------------------------------------------------------------------------- web search

_DDG_RESULT = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_DDG_SNIPPET = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
_GH_README = re.compile(r"^(https://github\.com/[^/]+/[^/]+)/blob/[^/]+/readme(\.md|\.rst)?$", re.I)
_TAG = re.compile(r"<[^>]+>")


def page_text(html: str, limit: int = 20000) -> str:
    """Readable text of a page: drops scripts/styles/nav, tags and extra whitespace."""
    html = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|pre|tr)>", "\n", html)
    text = htmllib.unescape(_TAG.sub(" ", html))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:limit]


def notebook_text(raw: str, limit: int = 20000) -> str:
    """Markdown + code cells of a .ipynb, in order."""
    import json as _json

    try:
        nb = _json.loads(raw)
    except ValueError:
        return page_text(raw, limit)
    parts = []
    for cell in nb.get("cells", []):
        src = cell.get("source", "")
        src = "".join(src) if isinstance(src, list) else str(src)
        parts.append(("# [code]\n" if cell.get("cell_type") == "code" else "") + src)
    return "\n\n".join(parts)[:limit]


def _clean(s: str | None) -> str:
    return htmllib.unescape(_TAG.sub("", s or "")).strip()


def parse_ddg(page: str) -> list[dict]:
    out = []
    for block in page.split('class="result results_links')[1:]:
        if "result--ad" in block[:200]:
            continue
        m = _DDG_RESULT.search(block)
        if not m:
            continue
        href = htmllib.unescape(m.group(1))
        if href.startswith("//duckduckgo.com/l/") or "duckduckgo.com/l/?" in href:
            q = parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query)
            href = unquote(q.get("uddg", [""])[0])
        if not href.startswith("http"):
            continue
        sn = _DDG_SNIPPET.search(block)
        out.append({"url": href, "title": _clean(m.group(2)), "description": _clean(sn.group(1)) if sn else ""})
    return out


async def web_search(ctx: Ctx, query: str, limit: int = 8) -> list[dict]:
    """Google via Bright Data SERP when configured, else DuckDuckGo's HTML endpoint."""
    hits: list[dict] = []
    via = "duckduckgo"
    if brightdata.available(ctx.keys):
        try:
            hits = await brightdata.google(ctx.client, ctx.keys, query, num=limit + 2)
            via = "brightdata"
            ctx.used.add("brightdata-serp")
        except Exception as e:
            ctx.note(f"bright data SERP failed: {e}")
    if not hits:
        r = await ctx.client.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "us-en"}, timeout=8)
        if r.status_code != 200:
            raise RuntimeError(f"DuckDuckGo HTTP {r.status_code}")
        hits = parse_ddg(r.text)
        ctx.used.add("duckduckgo")
    out = []
    for h in hits:
        m = _GH_README.match(h["url"])
        if m:  # a repo's README page is the repo
            h = {**h, "url": m.group(1)}
        t = re.match(r"GitHub - ([\w.\-]+/[\w.\-]+)", h.get("title", ""))
        if t:  # "GitHub - owner/repo: description" -> "owner/repo"
            h = {**h, "title": t.group(1)}
        if skip(h["url"]):
            continue
        out.append({**h, "kind": classify(h["url"]), "via": via, "indexed": True})
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- GitHub

async def github_search(ctx: Ctx, query: str, limit: int = 6) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if ctx.keys.github:
        headers["Authorization"] = f"Bearer {ctx.keys.github}"
    r = await ctx.client.get("https://api.github.com/search/repositories", params={"q": query, "per_page": limit}, headers=headers, timeout=8)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub search HTTP {r.status_code}: {r.text[:120]}")
    ctx.used.add("github")
    return parse_github(r.json(), limit)


def parse_github(data: dict, limit: int = 6) -> list[dict]:
    out = []
    for it in (data.get("items") or [])[:limit]:
        if it.get("archived") and it.get("stargazers_count", 0) < 20:
            continue
        lang = it.get("language") or ""
        out.append({
            "url": it["html_url"],
            "title": it["full_name"],
            "description": (it.get("description") or "")[:300],
            "kind": "notebook" if lang == "Jupyter Notebook" else "repo",
            "stars": it.get("stargazers_count", 0),
            "language": lang,
            "updated": (it.get("pushed_at") or "")[:10],
            "thumbnail": f"https://opengraph.githubassets.com/1/{it['full_name']}",
            "via": "github",
            "verified": True,  # returned by the GitHub API itself
        })
    return out


# --------------------------------------------------------------------------- arXiv

_ATOM = {"a": "http://www.w3.org/2005/Atom"}


async def arxiv_search(ctx: Ctx, terms: list[str], limit: int = 5) -> list[dict]:
    terms = [t.strip().replace('"', "") for t in terms if t and t.strip()][:4]
    if not terms:
        return []
    q = " AND ".join(f'all:"{t}"' if " " in t else f"all:{t}" for t in terms)
    r = await ctx.client.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": q, "max_results": limit, "sortBy": "relevance"},
        timeout=8,
    )
    if r.status_code != 200:
        raise RuntimeError(f"arXiv HTTP {r.status_code}")
    ctx.used.add("arxiv")
    return parse_arxiv(r.text)


def parse_arxiv(xml_text: str) -> list[dict]:
    out = []
    root = ET.fromstring(xml_text)
    for e in root.findall("a:entry", _ATOM):
        url = (e.findtext("a:id", "", _ATOM) or "").strip()
        if not url:
            continue
        url = re.sub(r"v\d+$", "", url).replace("http://", "https://")
        authors = [a.findtext("a:name", "", _ATOM) for a in e.findall("a:author", _ATOM)]
        out.append({
            "url": url,
            "title": " ".join((e.findtext("a:title", "", _ATOM) or "").split()),
            "description": " ".join((e.findtext("a:summary", "", _ATOM) or "").split())[:500],
            "kind": "paper",
            "authors": authors,
            "year": (e.findtext("a:published", "", _ATOM) or "")[:4],
            "arxiv_id": url.rsplit("/", 1)[-1],
            "via": "arxiv",
            "verified": True,  # returned by the arXiv API itself
        })
    return out


# --------------------------------------------------------------------------- Claude + web search tool

async def claude_search(ctx: Ctx, query: str, *, timeout: float = 11.0, extra_results: int = 4) -> list[dict]:
    """Claude plans and runs the searches (server-side web_search tool). Only URLs from the tool's
    result blocks are kept (see claude.search); Claude's own picks lead, with its 'why'."""
    if not ctx.keys.anthropic:
        return []
    from . import claude

    found, info = await claude.search(ctx.keys.anthropic, query, timeout=timeout)
    ctx.used.add("claude-search")
    ctx.extra["claude"] = info
    out, extras = [], 0
    for r in found:
        url = r["url"]
        if skip(url):
            continue
        if not r.get("picked"):
            if extras >= extra_results:
                continue
            extras += 1
        kind = classify(url)
        if kind == "blog" and r.get("kind") in ("notebook", "paper"):
            kind = r["kind"]
        m = _GH_README.match(url)
        if m:
            url = m.group(1)
        out.append({
            "url": url,
            "title": r.get("title") or url,
            "description": r.get("why") or "",
            "kind": kind,
            "via": "claude",
            "indexed": True,  # came from the search tool's results, not from the model's text
            "claude_pick": bool(r.get("picked")),
        })
    return out
