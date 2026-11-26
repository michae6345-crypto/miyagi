"""Every URL is checked before it is emitted: videos via YouTube oEmbed (public + embeddable),
everything else by an HTTP request that must resolve (< 400)."""

from __future__ import annotations

import logging

import httpx

from . import youtube
from .env import Keys

log = logging.getLogger("finder.verify")

BOT_BLOCKED = {401, 403, 429, 999}


async def check_url(client: httpx.AsyncClient, url: str, *, timeout: float = 6) -> tuple[int, str]:
    """(status, final_url). HEAD first, GET when the server doesn't do HEAD. 0 = unreachable."""
    try:
        r = await client.head(url, timeout=timeout)
        if r.status_code in (400, 403, 404, 405, 406, 501) or r.status_code >= 500:
            async with client.stream("GET", url, timeout=timeout) as g:
                return g.status_code, str(g.url)
        return r.status_code, str(r.url)
    except (httpx.HTTPError, ValueError) as e:
        log.debug("unreachable %s: %s", url, e)
        return 0, url


async def verify(client: httpx.AsyncClient, keys: Keys, cand: dict) -> dict | None:
    if cand["kind"] == "video":
        return await verify_video(client, keys, cand)
    if cand.get("verified") is True:  # returned by the GitHub / arXiv API or already fetched
        return cand
    status, final = await check_url(client, cand["url"])
    if 200 <= status < 400:
        return {**cand, "url": final, "verified": True}
    if status in BOT_BLOCKED and cand.get("indexed"):
        # The page is in a search engine's index (real) but refuses bots.
        return {**cand, "verified": "indexed"}
    log.info("dropping %s (HTTP %s)", cand["url"], status)
    return None


async def verify_video(client: httpx.AsyncClient, keys: Keys, cand: dict) -> dict | None:
    vid = cand.get("videoId") or youtube.video_id(cand["url"])
    if not vid:
        return None
    url = youtube.watch_url(vid)
    meta = await youtube.oembed(client, url)
    if not meta:
        log.info("dropping video %s (oEmbed failed: private, removed or not embeddable)", vid)
        return None
    out = {
        **cand,
        "videoId": vid,
        "url": url,
        "title": meta.get("title") or cand.get("title", ""),
        "channel": meta.get("author_name") or cand.get("channel", ""),
        "thumbnail": meta.get("thumbnail_url") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "verified": True,
    }
    if not out.get("duration_s"):
        try:
            page = (await client.get(url, timeout=6)).text
            out.update({k: v for k, v in youtube.parse_watch(page).items() if v and not out.get(k)})
        except Exception as e:
            log.info("watch page for %s failed: %s", vid, e)
    return out
