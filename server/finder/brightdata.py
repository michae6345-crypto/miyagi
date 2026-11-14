"""Bright Data: SERP API (Google results as JSON) and Web Unlocker (any page, unblocked).

Both go through the same endpoint: POST https://api.brightdata.com/request with
{"zone", "url", "format": "raw"} and `Authorization: Bearer <BRIGHTDATA_API_KEY>`.
Zones come from BRIGHTDATA_SERP_ZONE / BRIGHTDATA_UNLOCKER_ZONE.
"""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import quote_plus

import httpx

from .env import Keys

log = logging.getLogger("finder.brightdata")
ENDPOINT = "https://api.brightdata.com/request"


class BrightDataError(RuntimeError):
    pass


# Circuit breaker: an inactive account / missing zone fails every call, so stop trying for a while.
_off_until = 0.0
last_error: str | None = None
_FATAL = ("Customer is not active", "not found", "Unauthorized", "Invalid token", "Forbidden")


def available(keys: Keys) -> bool:
    return keys.has_brightdata and time.monotonic() >= _off_until


def _trip(msg: str) -> None:
    global _off_until, last_error
    last_error = msg
    if any(f.lower() in msg.lower() for f in _FATAL) or " 401" in msg or " 403" in msg:
        _off_until = time.monotonic() + 300
        log.warning("Bright Data disabled for 5 min: %s", msg[:160])


async def request(client: httpx.AsyncClient, keys: Keys, zone: str, url: str, *, timeout: float = 15) -> httpx.Response:
    if not available(keys):
        raise BrightDataError(last_error or "BRIGHTDATA_API_KEY is not set")
    r = await client.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {keys.brightdata}", "Content-Type": "application/json"},
        json={"zone": zone, "url": url, "format": "raw"},
        timeout=timeout,
    )
    if r.status_code >= 400:
        msg = f"Bright Data {zone} -> HTTP {r.status_code}: {r.text[:200]}"
        _trip(msg)
        raise BrightDataError(msg)
    return r


async def unlock(client: httpx.AsyncClient, keys: Keys, url: str, *, timeout: float = 15) -> str:
    """Fetch any page through Web Unlocker; returns the HTML."""
    r = await request(client, keys, keys.unlocker_zone, url, timeout=timeout)
    return r.text


async def google(client: httpx.AsyncClient, keys: Keys, query: str, *, num: int = 10, timeout: float = 12) -> list[dict]:
    """Google organic results via the SERP API (brd_json=1 → parsed JSON).
    Returns [{url, title, description}] in rank order."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&hl=en&gl=us&brd_json=1"
    r = await request(client, keys, keys.serp_zone, url, timeout=timeout)
    try:
        data = r.json()
    except (ValueError, json.JSONDecodeError) as e:
        raise BrightDataError(f"SERP returned non-JSON: {r.text[:120]}") from e
    return parse_serp(data)


def parse_serp(data: dict) -> list[dict]:
    out = []
    for item in data.get("organic") or []:
        link = item.get("link") or item.get("url")
        if not link or not link.startswith("http"):
            continue
        out.append({
            "url": link,
            "title": (item.get("title") or "").strip(),
            "description": (item.get("description") or item.get("snippet") or "").strip(),
            "rank": item.get("rank"),
        })
    return out


async def youtube_comments(client: httpx.AsyncClient, keys: Keys, video_url: str, *, timeout: float = 12) -> list:
    """Top comments of a video via the Web Scraper API (synchronous scrape of the YouTube
    comments dataset; id overridable with BRIGHTDATA_YT_COMMENTS_DATASET)."""
    import os

    if not available(keys):
        raise BrightDataError(last_error or "BRIGHTDATA_API_KEY is not set")
    dataset = os.environ.get("BRIGHTDATA_YT_COMMENTS_DATASET", "gd_lk9q0ew71spt1mxywf")
    r = await client.post(
        "https://api.brightdata.com/datasets/v3/scrape",
        params={"dataset_id": dataset, "format": "json", "include_errors": "true"},
        headers={"Authorization": f"Bearer {keys.brightdata}", "Content-Type": "application/json"},
        json={"input": [{"url": video_url, "num_of_comments": 40}]},
        timeout=timeout,
    )
    if r.status_code >= 400:
        msg = f"Bright Data comments -> HTTP {r.status_code}: {r.text[:200]}"
        _trip(msg)
        raise BrightDataError(msg)
    if r.status_code == 202:  # still running (snapshot); too slow for a 20 s search
        raise BrightDataError("Bright Data comments: snapshot not ready in time")
    data = r.json()
    return data if isinstance(data, list) else (data.get("data") or [])
