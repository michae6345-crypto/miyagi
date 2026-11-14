"""Live-web grounding for the coach (GENERALITY RULE: any tutorial, any library).

`docs_for(library, symbol)` → official docs/changelog pages; `community_signals(query)` →
Stack Overflow / GitHub issues / Reddit snippets. Uses `server.finder.web` (E7) when it
exists, else calls Bright Data directly (SERP API + Web Unlocker).

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
from urllib.parse import quote_plus, urlparse

import httpx

from . import llm

log = logging.getLogger("coach.web")

BRIGHTDATA_URL = "https://api.brightdata.com/request"

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


# ---------- Bright Data transport ---------------------------------------------------

def configured() -> bool:
    return _bd_config() is not None or bool(os.environ.get("COACH_REPLAY_DIR"))


def _bd_config() -> tuple[str, str, str] | None:
    llm._load_env()
    key = os.environ.get("BRIGHTDATA_API_KEY")
    serp = os.environ.get("BRIGHTDATA_SERP_ZONE")
    unlocker = os.environ.get("BRIGHTDATA_UNLOCKER_ZONE")
    return (key, serp, unlocker) if key and serp and unlocker else None


def _fixture(kind: str, url: str) -> str:
    return f"web-{kind}-{hashlib.sha256(url.encode()).hexdigest()[:10]}"


async def _bd_request(client: httpx.AsyncClient, key: str, zone: str, url: str) -> str:
    r = await client.post(
        BRIGHTDATA_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"zone": zone, "url": url, "format": "raw"},
    )
    r.raise_for_status()
    return r.text


async def fetch(kind: str, url: str) -> str | None:
    """kind: "serp" | "unlock". Replays/records fixtures; None on any failure."""
    if rd := os.environ.get("COACH_REPLAY_DIR"):
        p = Path(rd) / f"{_fixture(kind, url)}.json"
        return json.loads(p.read_text())["body"] if p.exists() else None
    cfg = _bd_config()
    if not cfg:
        return None
    key, serp_zone, unlocker_zone = cfg
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            body = await _bd_request(client, key, serp_zone if kind == "serp" else unlocker_zone, url)
    except httpx.HTTPError as e:
        log.info("bright data %s failed for %s: %s", kind, url, e)
        return None
    if wd := os.environ.get("COACH_RECORD_DIR"):
        Path(wd).mkdir(parents=True, exist_ok=True)
        (Path(wd) / f"{_fixture(kind, url)}.json").write_text(json.dumps({"url": url, "body": body[:200_000]}, ensure_ascii=False) + "\n")
    return body


def serp_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(query)}&brd_json=1&num=10"


def parse_serp(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
        return [
            {"url": o.get("link") or o.get("url"), "title": o.get("title", ""), "snippet": o.get("description", "") or o.get("snippet", "")}
            for o in data.get("organic", [])
            if o.get("link") or o.get("url")
        ]
    except (json.JSONDecodeError, AttributeError):
        return [{"url": u, "title": "", "snippet": ""} for u in re.findall(r'href="(https?://[^"]+)"', raw or "")]


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
    q = " ".join(x for x in [library, symbol, f'"{error}"' if error and len(error) < 120 else "", site or "documentation"] if x)
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
    tasks = []
    if library:
        tasks.append(docs_for(library, symbol, error=error))
    if query:
        tasks.append(community_signals(query))
    try:
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout)
    except TimeoutError:
        log.info("web grounding timed out after %.1fs", timeout)
        return []
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
