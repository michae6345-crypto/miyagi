"""Bright Data: SERP API (Google results as JSON) and Web Unlocker (any page, unblocked).

Both go through the same endpoint: POST https://api.brightdata.com/request with
{"zone", "url", "format": "raw"} and `Authorization: Bearer <BRIGHTDATA_API_KEY>`.
Zones come from BRIGHTDATA_SERP_ZONE / BRIGHTDATA_UNLOCKER_ZONE.
"""

from __future__ import annotations

import asyncio
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
    # the API answers 200 even when the target failed; the real status is in these headers
    target = r.headers.get("x-brd-status-code")
    if (target and not target.startswith(("2", "3"))) or (r.headers.get("x-brd-error") and not r.content):
        raise BrightDataError(
            f"Bright Data {zone}: target HTTP {target or '?'} ({r.headers.get('x-brd-error-code', '')}: {r.headers.get('x-brd-error', '')[:120]})"
        )
    return r


async def unlock(client: httpx.AsyncClient, keys: Keys, url: str, *, timeout: float = 15) -> str:
    """Fetch any page through Web Unlocker; returns the HTML."""
    r = await request(client, keys, keys.unlocker_zone, url, timeout=timeout)
    return r.text


async def google(client: httpx.AsyncClient, keys: Keys, query: str, *, num: int = 10, timeout: float = 12) -> list[dict]:
    """Google results via the SERP API (brd_json=1 -> parsed JSON): the organic results plus
    Google's video results (YouTube links with durations). Returns [{url, title, description,
    rank, kind?, duration_s?, channel?}] with google.com/goto redirects resolved to the real page."""
    # note: `num` is rejected by the SERP API (the request then fails with an empty 200)
    url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en&gl=us&brd_json=1"
    r = await request(client, keys, keys.serp_zone, url, timeout=timeout)
    try:
        data = r.json()
    except (ValueError, json.JSONDecodeError) as e:
        raise BrightDataError(f"SERP returned non-JSON: {r.text[:120]}") from e
    hits = parse_serp(data)[:num] + parse_serp_videos(data)
    resolved = await asyncio.gather(*(resolve_goto(client, h["url"]) for h in hits))
    return [{**h, "url": u} for h, u in zip(hits, resolved) if u]


async def resolve_goto(client: httpx.AsyncClient, url: str) -> str | None:
    """google.com/goto?url=<opaque> 302s to the real page; read the Location, don't follow it."""
    if "google.com/goto?" not in url:
        return url
    try:
        r = await client.get(url, follow_redirects=False, timeout=4)
    except httpx.HTTPError:
        return None
    loc = r.headers.get("location", "")
    return loc if loc.startswith("http") and "google.com/" not in loc else None


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


def parse_serp_videos(data: dict) -> list[dict]:
    out = []
    for v in data.get("videos") or []:
        link = v.get("link")
        if not link or not link.startswith("http"):
            continue
        src = (v.get("source") or "").split("·")
        out.append({
            "url": link,
            "title": (v.get("title") or "").strip(),
            "description": "",
            "rank": v.get("rank"),
            "kind": "video",
            "duration_s": v.get("duration_sec"),
            "channel": src[1].strip() if len(src) > 1 else "",
        })
    return out


_comments_off_until = 0.0
comments_error: str | None = None


def comments_available(keys: Keys) -> bool:
    """Separate breaker: a dataset the account can't use must not switch off SERP / Unlocker."""
    return available(keys) and time.monotonic() >= _comments_off_until


async def youtube_comments(client: httpx.AsyncClient, keys: Keys, video_url: str, *, timeout: float = 5) -> list:
    """Top comments of a video via the Web Scraper API (synchronous scrape of the YouTube
    comments dataset; id overridable with BRIGHTDATA_YT_COMMENTS_DATASET)."""
    import os

    global _comments_off_until, comments_error
    if not comments_available(keys):
        raise BrightDataError(comments_error or last_error or "BRIGHTDATA_API_KEY is not set")
    dataset = os.environ.get("BRIGHTDATA_YT_COMMENTS_DATASET", "gd_lk9q0ew71spt1mxywf")
    r = await client.post(
        "https://api.brightdata.com/datasets/v3/scrape",
        params={"dataset_id": dataset, "format": "json", "include_errors": "true"},
        headers={"Authorization": f"Bearer {keys.brightdata}", "Content-Type": "application/json"},
        json={"input": [{"url": video_url, "num_of_comments": 40}]},
        timeout=timeout,
    )
    if r.status_code >= 400:
        comments_error = f"Bright Data comments -> HTTP {r.status_code}: {r.text[:160]}"
        if r.status_code in (401, 402, 403, 404):  # no dataset access: stop asking for 10 min
            _comments_off_until = time.monotonic() + 600
        raise BrightDataError(comments_error)
    if r.status_code == 202:  # still running (snapshot); too slow for a 20 s search
        raise BrightDataError("Bright Data comments: snapshot not ready in time")
    data = r.json()
    rows = data if isinstance(data, list) else (data.get("data") or [])
    errs = [x for x in rows if isinstance(x, dict) and x.get("error") and not (x.get("comment_text") or x.get("text"))]
    if rows and len(errs) == len(rows):  # e.g. {"error": "No comments exists on the video", "error_code": "dead_page"}
        raise BrightDataError(f"Bright Data comments: {errs[0].get('error_code')}: {str(errs[0].get('error'))[:100]}")
    return rows
