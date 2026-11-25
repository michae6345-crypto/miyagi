"""read_link(url): fetch any http(s) link through server.netsafe and turn it into an Extraction, or raise LinkUnreadable
with a plain reason the learner sees.

The rules (shared/contracts/ANY-LINK.md "Fetch safely"):
- http(s) only; never localhost, *.local, or a private / loopback / link-local address, by spelling, after DNS and
  after every redirect (netsafe): "unsupported";
- no cookie jar, no credentials, at most MAX_REDIRECTS redirects, TIMEOUT_S per read and DEADLINE_S for the whole page,
  at most MAX_PAGE_BYTES read (a longer page is read up to the cap, not refused);
- READ_DEADLINE_S caps the whole read (robots.txt, the page, a redirect's robots.txt, every GitHub API call and raw
  file): past it the link is "offline" ("<site> took too long to answer."), so link.get / learn_url never hang;
- the HTML extraction (pure CPU, up to ~2 s on a 2 MB nested page) runs in a worker thread, off the engine's loop;
- robots.txt is read first (ROBOTS_*): a Disallow for our token ("Miyagi") or for * is "blocked". A robots.txt that
  is missing (4xx) allows everything; one that cannot be read (5xx, timeout) is treated as allowing too: this is one
  page the learner asked for, as a browser would open it, not a crawl. The final host is checked again after a
  redirect to another host;
- 401 / 402 / 403 / 451 and a paywall or sign-in wall in the page are "blocked"; 404 / 410 "not_found"; 429 "busy";
  a network failure "offline"; a PDF, an image, JSON or a page with no readable text "no_content".
Tests swap TRANSPORT for an httpx.MockTransport (netsafe still checks schemes and literal addresses on every hop).
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.robotparser
from urllib.parse import urlsplit

import httpx

from server import netsafe

from . import github
from .html import extract as extract_html
from .markdown import parse_markdown, parse_plain
from .model import Extraction, LinkUnreadable

log = logging.getLogger("server.linkread")

TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests: an httpx.MockTransport serving fixtures
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT_S = 10.0
DEADLINE_S = 15.0
READ_DEADLINE_S = 20.0  # the whole read_link, every fetch in it (a GitHub link makes up to 3 API calls + raw files)
ROBOTS_TIMEOUT_S = 4.0
ROBOTS_MAX_BYTES = 256 * 1024
MAX_TEXT_CHARS = 120_000  # the extraction keeps the page's first sections up to this (the build cuts to its own budget)
MIN_TEXT_CHARS = 200  # less readable text than this (and no code) is "no_content"
ROBOTS_TOKEN = "Miyagi"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36 Miyagi/1.0")
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9",
           "Accept": "text/html,application/xhtml+xml,text/markdown;q=0.9,text/plain;q=0.8,*/*;q=0.1"}
_YOUTUBE = re.compile(r"(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)$")


def link_kind(url: str) -> str:
    """"youtube" (the video path handles it), "github" (a repo link), "web" (any other http(s) link) or "unsupported"."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return "unsupported"
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme.lower() not in ("http", "https") or not host:
        return "unsupported"
    if _YOUTUBE.search(host):
        return "youtube"
    if github.parse_repo_url(url) is not None:
        return "github"
    return "web"


def site_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def _check(url: str) -> None:
    """Refuse what is never fetched, before any network: not http(s), credentials, this Mac, a .local name, a private
    literal address."""
    kind = link_kind(url)
    if kind == "unsupported":
        raise LinkUnreadable("unsupported", "Only web links (http or https) can become lessons.")
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if host.endswith((".local", ".internal", ".lan")) or "." not in host and ":" not in host:
        raise LinkUnreadable("unsupported", "That link points to this Mac or a private network, so I won't open it.")
    try:
        netsafe.check_url(url)
    except netsafe.BlockedURL:
        raise LinkUnreadable("unsupported", "That link points to this Mac or a private network, so I won't open it.") from None


class _Fetcher:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    async def get(self, url: str, *, accept: str | None = None, max_bytes: int | None = None,
                  timeout: float | None = None, deadline: float | None = None) -> httpx.Response:
        max_bytes = MAX_PAGE_BYTES if max_bytes is None else max_bytes
        timeout = TIMEOUT_S if timeout is None else timeout
        deadline = DEADLINE_S if deadline is None else deadline
        headers = dict(HEADERS)
        if accept:
            headers["Accept"] = accept
        try:
            return await netsafe.get(url, client=self.client, headers=headers, timeout=timeout, deadline=deadline,
                                     max_bytes=max_bytes, max_redirects=MAX_REDIRECTS, truncate=True)
        except netsafe.BlockedURL as e:
            log.info("linkread: refused %s: %s", site_of(url), e)
            if "redirects" in str(e):
                raise LinkUnreadable("unknown", "That link redirects too many times.") from None
            raise LinkUnreadable("unsupported", "That link leads to this Mac or a private network, so I won't open it.") from None
        except httpx.TimeoutException:
            raise LinkUnreadable("offline", f"{site_of(url)} took too long to answer.") from None
        except httpx.HTTPError as e:
            log.info("linkread: %s unreachable: %s", site_of(url), type(e).__name__)
            raise LinkUnreadable("offline", f"I couldn't reach {site_of(url)}. Check your connection.") from None

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            self.robots[origin] = await self._robots(origin)
        rp = self.robots[origin]
        return True if rp is None else rp.can_fetch(ROBOTS_TOKEN, url)

    async def _robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        try:
            resp = await self.get(f"{origin}/robots.txt", accept="text/plain", max_bytes=ROBOTS_MAX_BYTES,
                                  timeout=ROBOTS_TIMEOUT_S, deadline=ROBOTS_TIMEOUT_S + 1)
        except LinkUnreadable as e:
            if e.code == "unsupported":
                raise
            return None
        if resp.status_code != 200 or "html" in resp.headers.get("content-type", "").lower():
            return None  # no robots.txt (or a soft-404 page): everything allowed
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp


def _status(resp: httpx.Response, site: str) -> None:
    s = resp.status_code
    if s in (401, 402, 403, 407, 451):
        raise LinkUnreadable("blocked", f"{site} needs a sign-in or won't let me read this page.", site=site)
    if s in (404, 410):
        raise LinkUnreadable("not_found", "That page doesn't exist (anymore). Check the link.", site=site)
    if s == 429:
        raise LinkUnreadable("busy", f"{site} is asking me to slow down. Try again in a minute.", site=site)
    if s >= 400:
        raise LinkUnreadable("unknown", f"{site} didn't answer properly (error {s}). Try again in a bit.", site=site)


def _content_kind(resp: httpx.Response, url: str) -> str:
    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    path = urlsplit(url).path.lower()
    if ctype in ("text/markdown", "text/x-markdown") or path.endswith((".md", ".markdown")) and ctype in ("text/plain", ""):
        return "markdown"
    if ctype in ("text/html", "application/xhtml+xml") or (not ctype and resp.content[:512].lstrip()[:1] == b"<"):
        return "html"
    if ctype == "text/plain":
        return "plain"
    if ctype == "application/pdf" or path.endswith(".pdf"):
        return "pdf"
    if ctype.startswith(("image/", "video/", "audio/")):
        return ctype.split("/")[0]
    return "other"


_NOT_TEXT = {"pdf": "It's a PDF, which I can't read yet.", "image": "It's an image, not a page with text.",
             "video": "It's a video file, not a page I can read.", "audio": "It's an audio file, not a page I can read.",
             "other": "It isn't a web page with text I can read."}


async def read_link(url: str, *, client: httpx.AsyncClient | None = None) -> Extraction:
    """The link's readable content. Raises LinkUnreadable (code + plain reason). A YouTube link is "unsupported" here:
    the video path reads those."""
    url = (url or "").strip()
    _check(url)
    if link_kind(url) == "youtube":
        raise LinkUnreadable("unsupported", "That's a YouTube link: it's read as a video.")
    repo = github.parse_repo_url(url)
    site = repo.site if repo is not None else site_of(url)
    try:
        async with asyncio.timeout(READ_DEADLINE_S):
            if client is None:
                async with netsafe.async_client(transport=TRANSPORT, timeout=TIMEOUT_S) as c:
                    return await _read(url, _Fetcher(c))
            return await _read(url, _Fetcher(client))
    except TimeoutError:
        log.info("linkread: %s: no complete read within %g s", site, READ_DEADLINE_S)
        raise LinkUnreadable("offline", f"{site} took too long to answer.", site=site) from None


async def _read(url: str, f: _Fetcher) -> Extraction:
    repo = github.parse_repo_url(url)
    if repo is not None:
        ex = await github.read_repo(repo, f.get, url)
        return _finish(ex)
    site = site_of(url)
    if not await f.allowed(url):
        raise LinkUnreadable("blocked", f"{site} asks tools like me not to read this page (robots.txt).", site=site)
    resp = await f.get(url)
    final = str(resp.url)
    final_site = site_of(final)
    if final != url:  # a short link that lands on a repo or a video: read it as one
        if (repo := github.parse_repo_url(final)) is not None:
            return _finish(await github.read_repo(repo, f.get, url))
        if link_kind(final) == "youtube":
            raise LinkUnreadable("unsupported", "That link leads to a YouTube video: paste the video's own link.",
                                 site=final_site, final_url=final)
    _status(resp, final_site)
    if not await f.allowed(final):  # robots.txt is per origin; the same origin is answered from the cache
        raise LinkUnreadable("blocked", f"{final_site} asks tools like me not to read this page (robots.txt).",
                             site=final_site, final_url=final)
    kind = _content_kind(resp, final)
    if kind in _NOT_TEXT:
        raise LinkUnreadable("no_content", _NOT_TEXT[kind], site=final_site, final_url=final)
    text = _decode(resp, kind)
    if kind == "html":
        try:
            page = await asyncio.to_thread(extract_html, text, site=final_site)  # CPU only: off the event loop
        except RecursionError:  # MAX_DEPTH keeps the tree shallow; this is the last guard
            raise LinkUnreadable("no_content", "This page is too tangled for me to read.", site=final_site,
                                 final_url=final) from None
        if page.wall:
            raise LinkUnreadable("blocked", page.wall, title=page.title or None, site=final_site, final_url=final)
        ex = Extraction(kind="web", url=url, final_url=final, title=page.title or final_site, site=final_site,
                        blocks=page.blocks, author=page.author, description=page.description)
        if page.script_only and _readable_chars(ex) < MIN_TEXT_CHARS:
            raise LinkUnreadable("no_content", "This page draws its text with JavaScript, so I can't read it.",
                                 title=page.title or None, site=final_site, final_url=final)
    else:
        blocks = parse_markdown(text) if kind == "markdown" else parse_plain(text)
        title = next((b.text for b in blocks if b.kind == "heading"), None) or urlsplit(final).path.rsplit("/", 1)[-1] or final_site
        ex = Extraction(kind="web", url=url, final_url=final, title=title[:200], site=final_site, blocks=blocks)
    return _finish(ex)


_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([A-Za-z0-9_-]{2,40})""", re.IGNORECASE)


def _decode(resp: httpx.Response, kind: str) -> str:
    """The body as text: the header's charset, else (HTML) a <meta charset> in the first 4 KB, else UTF-8."""
    if "charset=" not in resp.headers.get("content-type", "").lower() and kind == "html":
        m = _META_CHARSET.search(resp.content[:4096])
        if m:
            try:
                return resp.content.decode(m.group(1).decode("ascii"), errors="replace")
            except LookupError:
                pass
        return resp.content.decode("utf-8", errors="replace")
    return resp.text


def _readable_chars(ex: Extraction) -> int:
    return sum(len(b.text) for b in ex.blocks)


def _finish(ex: Extraction) -> Extraction:
    if not ex.code_blocks and _readable_chars(ex) < MIN_TEXT_CHARS:
        what = "repo has no README I can read" if ex.kind == "github" else "page has no text I can read"
        raise LinkUnreadable("no_content", f"This {what}.", title=ex.title, site=ex.site, final_url=ex.final_url)
    return ex.cut(MAX_TEXT_CHARS)
