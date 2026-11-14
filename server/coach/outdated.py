"""fix_outdated(): the tutorial's code broke on a newer library → find the official fix.

1. Offline table of well-known removals (instant, no network).
2. Bright Data SERP (Google, official domains only) → Web Unlocker fetch of the top
   doc/changelog pages → Claude reads them and proposes the fix, citing one fetched URL.

Returns an offtrack-shaped dict (title, body, diff, citation, actions, severity) the
orchestrator can send as-is after adding `stepId`; None when nothing trustworthy found.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
from urllib.parse import quote_plus, urlparse

import httpx

from . import llm
from .common import clamp_title, clamp_words

log = logging.getLogger("coach.outdated")

BRIGHTDATA_URL = "https://api.brightdata.com/request"

OFFICIAL_DOMAINS: dict[str, list[str]] = {
    "torch": ["pytorch.org", "github.com/pytorch"],
    "numpy": ["numpy.org"],
    "pandas": ["pandas.pydata.org"],
    "scikit-learn": ["scikit-learn.org"],
    "sklearn": ["scikit-learn.org"],
    "scipy": ["docs.scipy.org", "scipy.org"],
    "matplotlib": ["matplotlib.org"],
    "tensorflow": ["tensorflow.org"],
    "jax": ["jax.readthedocs.io", "docs.jax.dev"],
    "transformers": ["huggingface.co"],
    "deepxde": ["deepxde.readthedocs.io"],
}

# (error regex, library, title, body, yours, expected, source label, source url)
KNOWN: list[tuple[str, str, str, str, str, str, str, str]] = [
    (
        r"module 'numpy' has no attribute '(float|int|bool|object)'",
        "numpy",
        "np.float was removed in NumPy 1.24",
        "The tutorial predates NumPy 1.24, which removed the np.float/np.int aliases. Use the builtin float/int, or np.float64.",
        "np.float",
        "float  # or np.float64",
        "NumPy 1.24 release notes",
        "https://numpy.org/doc/stable/release/1.24.0-notes.html",
    ),
    (
        r"'DataFrame' object has no attribute 'append'",
        "pandas",
        "DataFrame.append was removed in pandas 2.0",
        "pandas 2.0 removed DataFrame.append. Collect the rows and combine them once with pd.concat.",
        "df = df.append(row, ignore_index=True)",
        "df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)",
        "pandas 2.0.0 release notes",
        "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html",
    ),
]


def _known(error_text: str) -> dict | None:
    for rx, lib, title, body, yours, expected, label, url in KNOWN:
        if re.search(rx, error_text):
            return _payload(title, body, yours, expected, {"label": label, "url": url}, via="known")
    return None


def _payload(title: str, body: str, yours: str, expected: str, citation: dict, via: str) -> dict:
    out = {
        "severity": "fail",
        "title": clamp_title(title),
        "body": clamp_words(body, 34),
        "citation": citation,
        "actions": ["explain", "hint"],
        "_meta": {"route": "fix_outdated", "via": via},
    }
    if expected:
        out["diff"] = {"expected": expected, "yours": yours}
        out["actions"] = ["explain", "hint", "apply_fix"]
    return out


def _bd_config() -> tuple[str, str, str] | None:
    llm._load_env()
    key = os.environ.get("BRIGHTDATA_API_KEY")
    serp = os.environ.get("BRIGHTDATA_SERP_ZONE")
    unlocker = os.environ.get("BRIGHTDATA_UNLOCKER_ZONE")
    return (key, serp, unlocker) if key and serp and unlocker else None


async def _bd_request(client: httpx.AsyncClient, key: str, zone: str, url: str) -> str:
    r = await client.post(
        BRIGHTDATA_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"zone": zone, "url": url, "format": "raw"},
    )
    r.raise_for_status()
    return r.text


def _allowed(url: str, domains: list[str]) -> bool:
    p = urlparse(url)
    host, path = p.netloc.lower(), p.path.lstrip("/").lower()
    for d in domains:
        dhost, _, dpath = d.lower().partition("/")
        if (host == dhost or host.endswith("." + dhost)) and path.startswith(dpath):
            return True
    return False


def _serp_links(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
        return [o.get("link") or o.get("url") for o in data.get("organic", []) if o.get("link") or o.get("url")]
    except (json.JSONDecodeError, AttributeError):
        return re.findall(r'href="(https?://[^"]+)"', raw)


def _text(page: str, limit: int = 6000) -> str:
    page = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page)).strip()[:limit]


def _error_line(error_text: str) -> str:
    lines = [l.strip() for l in error_text.strip().splitlines() if l.strip()]
    for l in reversed(lines):
        if re.match(r"^\w*(Error|Exception|Warning)\b", l):
            return l[:200]
    return (lines[-1] if lines else error_text)[:200]


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

FIX_SYSTEM = """A tutorial's code fails on the learner's newer library version. Using ONLY the official documentation pages provided, state the fix.
- found=false if the pages do not clearly document the change; never guess.
- title <= 8 words naming what changed; body <= 30 words: what changed and in which version, then what to write instead.
- yours: the old call as written in the error/code; expected: the replacement (<= 3 lines).
- source_index: 0-based index of the page that documents it."""


async def fix_outdated(error_text: str, libraries: dict | list | None = None) -> dict | None:
    """`libraries`: {name: tutorial_version} from the step graph, or a list of names."""
    if hit := _known(error_text):
        return hit
    cfg = _bd_config()
    if not cfg:
        log.info("fix_outdated: no Bright Data config; skipping web search")
        return None
    key, serp_zone, unlocker_zone = cfg
    libs = list(libraries.keys()) if isinstance(libraries, dict) else list(libraries or [])
    err = _error_line(error_text)
    lib = next((l for l in libs if l.lower() in error_text.lower()), libs[0] if libs else "")
    domains = OFFICIAL_DOMAINS.get(lib.lower(), [f"pypi.org/project/{lib}"] if lib else [])
    site = " OR ".join(f"site:{d.split('/')[0]}" for d in domains)
    query = f'{lib} "{err}" deprecated removed changelog {site}'.strip()
    serp_url = f"https://www.google.com/search?q={quote_plus(query)}&brd_json=1&num=10"

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            links = [u for u in _serp_links(await _bd_request(client, key, serp_zone, serp_url)) if not domains or _allowed(u, domains)][:2]
            pages = []
            for u in links:
                try:
                    pages.append((u, _text(await _bd_request(client, key, unlocker_zone, u))))
                except httpx.HTTPError as e:
                    log.info("unlocker fetch failed for %s: %s", u, e)
    except httpx.HTTPError as e:
        log.warning("fix_outdated: Bright Data error %s", e)
        return None
    if not pages:
        return None

    versions = json.dumps(libraries, sort_keys=True) if isinstance(libraries, dict) else ", ".join(libs)
    user = f"Tutorial library versions: {versions}\nError:\n{error_text[-1500:]}\n\n" + "\n\n".join(
        f"[{i}] {u}\n{t}" for i, (u, t) in enumerate(pages)
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
        log.warning("fix_outdated: model failed %s", e)
        return None
    d = res.data
    if not d.get("found") or not (0 <= d.get("source_index", -1) < len(pages)):
        return None
    url = pages[d["source_index"]][0]
    return _payload(d["title"], d["body"], d.get("yours", ""), d.get("expected", ""), {"label": urlparse(url).netloc + urlparse(url).path, "url": url}, via="brightdata")
