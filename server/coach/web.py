"""Live-web grounding for the coach (GENERALITY RULE: any tutorial, any library).

`docs_for(library, symbol)` → official docs/changelog pages; `community_signals(query)` →
Stack Overflow / GitHub issues / Reddit snippets. Uses `server.finder.web` (E7) when it
exists, else searches DuckDuckGo's HTML endpoint and reads the pages with a plain GET (no API key).

Each source is a dict: {"url", "title", "snippet", "kind": "docs" | "community"}.
Every function degrades to [] (no keys, timeout, HTTP error) so the coach never blocks on the web.
Responses are recorded/replayed with COACH_RECORD_DIR / COACH_REPLAY_DIR like the LLM calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from server.redact import SECRET_MARK, redact_secrets

from . import llm

log = logging.getLogger("coach.web")

DDG_URL = "https://html.duckduckgo.com/html/"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")
BROWSER_HEADERS = {"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}

# library -> official docs/changelog hosts (path prefix allowed: "github.com/pytorch")
OFFICIAL_DOMAINS: dict[str, list[str]] = {
    # python
    "python": ["docs.python.org"],
    "torch": ["pytorch.org", "docs.pytorch.org", "github.com/pytorch"],
    "numpy": ["numpy.org"],
    "pandas": ["pandas.pydata.org"],
    "scikit-learn": ["scikit-learn.org"],
    "sklearn": ["scikit-learn.org"],
    "scipy": ["docs.scipy.org", "scipy.org"],
    "matplotlib": ["matplotlib.org"],
    "tensorflow": ["tensorflow.org"],
    "keras": ["keras.io"],
    "jax": ["docs.jax.dev", "jax.readthedocs.io"],
    "transformers": ["huggingface.co"],
    "django": ["docs.djangoproject.com"],
    "flask": ["flask.palletsprojects.com"],
    "fastapi": ["fastapi.tiangolo.com"],
    "pydantic": ["docs.pydantic.dev"],
    "requests": ["requests.readthedocs.io"],
    # javascript / web
    "react": ["react.dev", "legacy.reactjs.org"],
    "react-dom": ["react.dev"],
    "next": ["nextjs.org"],
    "vue": ["vuejs.org"],
    "svelte": ["svelte.dev"],
    "angular": ["angular.dev"],
    "vite": ["vite.dev", "vitejs.dev"],
    "typescript": ["typescriptlang.org"],
    "node": ["nodejs.org"],
    "express": ["expressjs.com"],
    "tailwindcss": ["tailwindcss.com"],
    "javascript": ["developer.mozilla.org"],
    "npm": ["docs.npmjs.com"],
    # tools
    "git": ["git-scm.com"],
    "docker": ["docs.docker.com"],
    "blender": ["docs.blender.org"],
    "rust": ["doc.rust-lang.org"],
    "cargo": ["doc.rust-lang.org"],
    "go": ["go.dev", "pkg.go.dev"],
}
COMMUNITY_DOMAINS = ["stackoverflow.com", "github.com", "reddit.com"]

ALIASES = {"np": "numpy", "pd": "pandas", "plt": "matplotlib", "tf": "tensorflow", "sk": "sklearn", "reactdom": "react-dom", "nextjs": "next", "node.js": "node", "nodejs": "node"}


# ---------- library / symbol detection from on-screen text -----------------------

_PY_PATTERNS = [
    (r"module '([\w.]+)' has no attribute '(\w+)'", lambda m: (m[1].split(".")[0], f"{m[1]}.{m[2]}")),
    (r"'(\w+)' object has no attribute '(\w+)'", lambda m: (None, f"{m[1]}.{m[2]}")),
    (r"No module named '([\w.]+)'", lambda m: (m[1].split(".")[0], m[1])),
    (r"cannot import name '(\w+)' from '([\w.]+)'", lambda m: (m[2].split(".")[0], f"{m[2]}.{m[1]}")),
    (r"(\w+)\(\) got an unexpected keyword argument '(\w+)'", lambda m: (None, f"{m[1]}({m[2]}=)")),
    (r"(\w+(?:\.\w+)*) (?:is|has been) deprecated", lambda m: (None, m[1])),
]
_JS_PATTERNS = [
    (r'React Hook "?(\w+)"?', lambda m: ("react", m[1])),
    (r"Invalid hook call", lambda m: ("react", "rules of hooks")),
    (r"(ReactDOM\.\w+)", lambda m: ("react-dom", m[1])),
    (r"Cannot find module '([@\w/.-]+)'", lambda m: (m[1].lstrip("@").split("/")[0], m[1])),
    (r"Module not found: .*?'([@\w/.-]+)'", lambda m: (m[1].lstrip("@").split("/")[0], m[1])),
    (r"(\w+(?:\.\w+)*) is not a function", lambda m: (None, m[1])),
]


def detect(error_text: str = "", code: str = "", libraries: dict | list | None = None, command: str = "") -> tuple[str, str]:
    """Best guess (library, symbol) for an error seen on screen; either may be ""."""
    text = error_text or ""
    lib, sym = None, None
    for rx, fn in _PY_PATTERNS + _JS_PATTERNS:
        if m := re.search(rx, text):
            lib, sym = fn(m)
            break
    if not lib and (m := re.search(r"(?:site-packages|node_modules)/(@?[\w.-]+)", text)):
        lib = m[1].lstrip("@")
    known = list(libraries.keys()) if isinstance(libraries, dict) else list(libraries or [])
    if not lib:
        low = text.lower() + " " + (sym or "").lower()
        lib = next((k for k in known if re.search(rf"\b{re.escape(k.lower())}\b", low)), None)
    if not lib and sym:
        head = sym.split(".")[0]
        lib = next((k for k in known if re.search(rf"\b(import|from)\s+{re.escape(k)}\b.*\b{re.escape(head)}\b|\b{re.escape(head)}\b.*=.*\b{re.escape(k)}\b", code or "")), None)
    if not lib and command:
        first = command.strip().split()[0] if command.strip() else ""
        lib = {"npm": "npm", "npx": "node", "node": "node", "git": "git", "docker": "docker", "cargo": "cargo", "go": "go"}.get(first)
    if not lib and known:
        lib = known[0]
    lib = ALIASES.get((lib or "").lower(), (lib or "").lower())
    return lib, sym or ""


def error_line(error_text: str) -> str:
    lines = [ln.strip() for ln in (error_text or "").strip().splitlines() if ln.strip()]
    for ln in reversed(lines):
        if re.search(r"\b\w*(Error|Exception|Warning|ERR!?)\b|^error\b|React Hook|Invalid hook", ln):
            return ln[:200]
    return (lines[-1] if lines else "")[:200]


# ---------- web transport (DuckDuckGo HTML search + plain GET) -----------------------

def configured() -> bool:
    """Live web grounding is on unless the coach is offline (DEMO / ORCH_STUBS) or COACH_WEB=0.
    Recorded fixtures (COACH_REPLAY_DIR) always replay."""
    if os.environ.get("COACH_REPLAY_DIR"):
        return True
    if os.environ.get("COACH_WEB", "").strip() == "0":
        return False
    return not llm.offline_mode()


def _fixture(kind: str, url: str) -> str:
    return f"web-{kind}-{hashlib.sha256(url.encode()).hexdigest()[:10]}"


async def fetch(kind: str, url: str) -> str | None:
    """kind: "serp" (a DuckDuckGo results page) | "unlock" (any page, plain GET). Replays/records
    fixtures; None on any failure."""
    if rd := os.environ.get("COACH_REPLAY_DIR"):
        p = Path(rd) / f"{_fixture(kind, url)}.json"
        return json.loads(p.read_text())["body"] if p.exists() else None
    if not configured():
        return None
    body = ""
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=BROWSER_HEADERS, follow_redirects=True) as client:
            for attempt in range(2):  # a search page sometimes comes back empty (rate limit); retry once
                r = await client.get(url)
                r.raise_for_status()
                body = r.text
                if _usable(kind, body):
                    break
                log.info("web %s: empty/invalid body (attempt %d)", kind, attempt + 1)
                await asyncio.sleep(0.2)
    except httpx.HTTPError as e:
        log.info("web %s failed for %s: %s", kind, url, e)
        return None
    if not _usable(kind, body):
        return None
    if wd := os.environ.get("COACH_RECORD_DIR"):
        Path(wd).mkdir(parents=True, exist_ok=True)
        (Path(wd) / f"{_fixture(kind, url)}.json").write_text(json.dumps({"url": url, "body": body[:200_000]}, ensure_ascii=False) + "\n")
    return body


def _usable(kind: str, body: str) -> bool:
    if not body or not body.strip():
        return False
    if kind == "serp":
        return "<html" in body[:2000].lower() or "result__a" in body
    return True


def search_safe(text: str) -> str:
    """`text` fit for a web search: every key- or token-shaped value (an error line's `?key=AIza...` URL, a key the
    learner pasted into their question) is dropped, not sent to the search engine (5.2)."""
    if not text:
        return text
    out = redact_secrets(text)
    if SECRET_MARK not in out:
        return text
    return re.sub(r"[ \t]{2,}", " ", out.replace(SECRET_MARK, " ")).strip()


def serp_url(query: str) -> str:
    return f"{DDG_URL}?q={quote_plus(search_safe(query))}"


_DDG_LINK = re.compile(r'<a\b[^>]*\bclass="[^"]*result__a[^"]*"[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>', re.S)
_DDG_SNIPPET = re.compile(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|td|div)>', re.S)


def _unwrap(href: str) -> str:
    """DuckDuckGo wraps result links as //duckduckgo.com/l/?uddg=<encoded url>."""
    href = html.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    u = urlparse(href)
    if u.netloc.endswith("duckduckgo.com") and u.path.startswith("/l/"):
        return unquote((parse_qs(u.query).get("uddg") or [""])[0])
    return href


def _strip(s: str) -> str:
    return html.unescape(re.sub(r"(?s)<[^>]+>", "", s or "")).strip()


def parse_serp(raw: str) -> list[dict]:
    """[{url, title, snippet}] from a DuckDuckGo HTML results page (ads skipped). Falls back to
    every absolute link on the page when the result markup is not recognised."""
    out = []
    for block in re.split(r'(?=<div[^>]+class="[^"]*\bresult\b)', raw or ""):
        m = _DDG_LINK.search(block)
        if not m or "result--ad" in block[:300]:
            continue
        url = _unwrap(m.group(1))
        if url.startswith("http"):
            sn = _DDG_SNIPPET.search(block)
            out.append({"url": url, "title": _strip(m.group(2)), "snippet": _strip(sn.group(1)) if sn else ""})
    if out:
        return out
    links = (_unwrap(u) for u in re.findall(r'href="((?:https?:)?//[^"]+)"', raw or ""))
    return [{"url": u, "title": "", "snippet": ""} for u in links if u.startswith("http") and "duckduckgo.com" not in urlparse(u).netloc]


def page_text(page: str, limit: int = 4000) -> str:
    page = re.sub(r"(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", page or "")
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page)).strip()[:limit]


def allowed(url: str, domains: list[str]) -> bool:
    p = urlparse(url)
    host, path = p.netloc.lower(), p.path.lstrip("/").lower()
    for d in domains:
        dhost, _, dpath = d.lower().partition("/")
        if (host == dhost or host.endswith("." + dhost)) and path.startswith(dpath):
            return True
    return False


def _focus(text: str, terms: list[str], limit: int) -> str:
    """Cut the page around the first mention of a search term (docs pages are long)."""
    low = text.lower()
    for t in terms:
        if t and (i := low.find(t.lower())) >= 0:
            start = max(0, i - limit // 4)
            return text[start : start + limit]
    return text[:limit]


# ---------- the two grounding calls (E7 names) ----------------------------------------

async def _docs_for(library: str, symbol: str = "", *, error: str = "", max_pages: int = 1) -> list[dict]:
    domains = OFFICIAL_DOMAINS.get(library, [])
    site = " OR ".join(f"site:{d.split('/')[0]}" for d in domains)
    # docs pages don't contain error text: search library + symbol (live: quoting the error → 0 hits);
    # with no symbol, fall back to the error's distinctive words
    words = symbol or " ".join(re.findall(r"[A-Za-z_][\w.]{2,}", error or "")[:6])
    q = " ".join(x for x in [library, words, site or "documentation"] if x)
    raw = await fetch("serp", serp_url(q))
    if not raw:
        return []
    hits = [h for h in parse_serp(raw) if not domains or allowed(h["url"], domains)][:max_pages]
    out = []
    for h in hits:
        page = await fetch("unlock", h["url"])
        snippet = _focus(page_text(page or ""), [symbol.split(".")[-1], symbol, library], 1800) if page else h["snippet"]
        out.append({"url": h["url"], "title": h["title"] or h["url"], "snippet": snippet, "kind": "docs"})
    return out


async def _community_signals(query: str, *, max_results: int = 3) -> list[dict]:
    site = " OR ".join(f"site:{d}" for d in COMMUNITY_DOMAINS)
    raw = await fetch("serp", serp_url(f"{query} {site}"))
    if not raw:
        return []
    hits = [h for h in parse_serp(raw) if allowed(h["url"], COMMUNITY_DOMAINS)][:max_results]
    return [{"url": h["url"], "title": h["title"] or h["url"], "snippet": h["snippet"][:400], "kind": "community"} for h in hits]


try:  # E7's shared implementation wins when it lands
    from server.finder.web import community_signals, docs_for  # type: ignore
except ImportError:
    docs_for, community_signals = _docs_for, _community_signals


async def gather(library: str, symbol: str, query: str, *, error: str = "", timeout: float = 8.0) -> list[dict]:
    """Docs + community in parallel, bounded by `timeout`; [] when the web is unavailable."""
    if not configured() or not (library or query):
        return []
    # the learner's question and the terminal's error line go out as search words: no key or token in them (5.2)
    query, error, symbol = search_safe(query), search_safe(error), search_safe(symbol)
    tasks = []
    if library:
        tasks.append(asyncio.ensure_future(docs_for(library, symbol, error=error)))
    if query:
        tasks.append(asyncio.ensure_future(community_signals(query)))
    # keep whatever finished in time (one slow SERP must not sink the other result)
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for t in pending:
        t.cancel()
    if pending:
        log.info("web grounding: %d of %d lookups still running after %.1fs; using the rest", len(pending), len(tasks), timeout)
    results = [t.exception() or t.result() for t in tasks if t in done and not t.cancelled()]
    seen, out = set(), []
    for r in results:
        if isinstance(r, BaseException):
            log.info("web grounding error: %s", r)
            continue
        for s in r:
            if s.get("url") and s["url"] not in seen:
                seen.add(s["url"])
                out.append(s)
    return out


def sources_text(sources: list[dict]) -> str:
    return "\n\n".join(f"[web:{i}] ({s['kind']}) {s['title']} <{s['url']}>\n{s['snippet']}" for i, s in enumerate(sources))
