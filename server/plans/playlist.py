"""A YouTube playlist's videos, fast and with no paid call (Adrian: "can the engine list a playlist's videos fast?").

In order, the first that answers:
1. playlists.json shipped with the engine (the 50 playlists picked for the catalog): instant, no network.
2. The cache on this Mac (<state dir>/plans/playlists/<id>.json), when 0 <= its age < CACHE_TTL_S.
3. YouTube's public playlist page (ytInitialData: the first ~100 videos with titles and lengths). One GET, PAGE_TIMEOUT_S.
4. The playlist's public Atom feed (feeds/videos.xml?playlist_id=): the first 15 videos, no lengths. FEED_TIMEOUT_S.
5. An older cached copy (stale beats nothing).
Every fetch goes through server.netsafe (public hosts only, no cookie jar, the body capped, a hard deadline). Only the
playlist id leaves the Mac. Tests pass a recorded page through TRANSPORT (an httpx.MockTransport).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from server import netsafe
from server.finder import youtube
from server.sessions.store import _read, _write_atomic, state_dir

from . import catalog

log = logging.getLogger("plans.playlist")

PAGE_TIMEOUT_S = 5.0
FEED_TIMEOUT_S = 4.0
CACHE_TTL_S = 24 * 3600.0
MAX_VIDEOS = 200
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9", "Cookie": "CONSENT=YES+1"}
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests: an httpx.MockTransport with recorded pages
_GONE_TITLES = ("[Private video]", "[Deleted video]")
_ATOM = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


class PlaylistUnavailable(RuntimeError):
    """No source could list the playlist. `reason`: bad_url | not_found | offline."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def playlist_id(text: str) -> str | None:
    """The playlist id in a YouTube URL (playlist?list=, watch?v=..&list=, youtu.be/x?list=) or a bare id."""
    t = (text or "").strip()
    if catalog.PLAYLIST_ID_RE.fullmatch(t) and t[:2] in ("PL", "UU", "OL", "FL", "RD", "LL"):
        return t
    try:
        u = urlparse(t if "://" in t else "https://" + t)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if not (host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")):
        return None
    lst = (parse_qs(u.query).get("list") or [""])[0]
    return lst if catalog.PLAYLIST_ID_RE.fullmatch(lst) else None


# ------------------------------------------------------------------------------------------------ parsing


def _text(o: Any) -> str:
    if isinstance(o, dict) and isinstance(o.get("content"), str):  # view models: {content: "..."}
        return o["content"]
    return youtube._text(o)


def _int(v: Any) -> int | None:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _lockup_seconds(lockup: dict) -> int | None:
    for badge in youtube._walk(lockup, "thumbnailBadgeViewModel"):
        if isinstance(badge, dict) and (s := youtube.parse_duration(badge.get("text"))) is not None:
            return s
    return None


def parse_page(html: str) -> dict | None:
    """{title, channel, videos: [{id, title, seconds}], truncated} from a playlist page; None when it has no videos.
    Reads both layouts YouTube serves: playlistVideoRenderer rows, and the newer lockupViewModel rows."""
    data = youtube.initial_data(html)
    if not data:
        return None
    videos: list[dict] = []
    seen: set[str] = set()

    def add(vid: Any, title: str, secs: int | None) -> None:
        if isinstance(vid, str) and catalog.VIDEO_ID_RE.fullmatch(vid) and vid not in seen and title not in _GONE_TITLES:
            seen.add(vid)
            videos.append({"id": vid, "title": " ".join(title.split())[:200] or "Video", "seconds": secs})

    for r in youtube._walk(data, "playlistVideoRenderer"):
        if isinstance(r, dict) and r.get("isPlayable", True) is not False:
            secs = _int(r.get("lengthSeconds"))
            add(r.get("videoId"), _text(r.get("title")),
                secs if secs is not None else youtube.parse_duration(_text(r.get("lengthText")) or None))
    for lk in youtube._walk(data, "lockupViewModel"):
        if isinstance(lk, dict) and "VIDEO" in str(lk.get("contentType", "")):
            meta = next(iter(youtube._walk(lk, "lockupMetadataViewModel")), {})
            add(lk.get("contentId"), _text(meta.get("title")) if isinstance(meta, dict) else "", _lockup_seconds(lk))
    if not videos:
        return None
    title = ""
    for key in ("playlistMetadataRenderer", "microformatDataRenderer"):
        m = next(iter(youtube._walk(data, key)), None)
        if isinstance(m, dict) and isinstance(m.get("title"), str):
            title = m["title"]
            break
    channel = ""
    hdr = next(iter(youtube._walk(data, "playlistHeaderRenderer")), None)
    if isinstance(hdr, dict):
        channel = _text(hdr.get("ownerText"))
    if not channel:
        owner = next(iter(youtube._walk(data, "videoOwnerRenderer")), None)
        channel = _text(owner.get("title")) if isinstance(owner, dict) else ""
    truncated = any(True for _ in youtube._walk(data, "continuationItemRenderer"))
    return {"title": " ".join(title.split())[:200], "channel": " ".join(channel.split())[:120],
            "videos": videos[:MAX_VIDEOS], "truncated": truncated or len(videos) > MAX_VIDEOS}


def parse_feed(xml: str) -> dict | None:
    """The playlist's Atom feed: the first 15 videos (no lengths)."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    videos = []
    for e in root.findall("a:entry", _ATOM):
        vid = e.findtext("yt:videoId", default="", namespaces=_ATOM)
        if catalog.VIDEO_ID_RE.fullmatch(vid):
            videos.append({"id": vid, "title": " ".join((e.findtext("a:title", default="", namespaces=_ATOM)).split())[:200]
                           or "Video", "seconds": None})
    if not videos:
        return None
    return {"title": " ".join((root.findtext("a:title", default="", namespaces=_ATOM)).split())[:200],
            "channel": " ".join((root.findtext("a:author/a:name", default="", namespaces=_ATOM)).split())[:120],
            "videos": videos, "truncated": len(videos) >= 15}


# ------------------------------------------------------------------------------------------------ cache


def _cache_path(plid: str) -> Path:
    return state_dir() / "plans" / "playlists" / f"{plid}.json"


def _cached(plid: str) -> tuple[dict, float] | None:
    data = _read(_cache_path(plid))
    if isinstance(data, dict) and isinstance(data.get("playlist"), dict) and isinstance(data.get("fetchedAt"), (int, float)):
        pl = catalog._clean_playlist(data["playlist"])
        if pl:
            pl.update({k: data["playlist"].get(k) for k in ("truncated", "source") if k in data["playlist"]})
            return pl, float(data["fetchedAt"])
    return None


def fresh(fetched_at: float, now: float | None = None) -> bool:
    """A cached copy younger than CACHE_TTL_S. A copy stamped in the future (the clock moved backwards since) is not
    fresh: a negative age must never keep a stale list forever."""
    age = (time.time() if now is None else now) - fetched_at
    return 0 <= age < CACHE_TTL_S


def _save(pl: dict) -> None:
    try:
        _write_atomic(_cache_path(pl["playlistId"]), {"fetchedAt": time.time(), "playlist": pl})
    except OSError as e:
        log.warning("could not cache playlist %s: %s", pl["playlistId"], e)


# ------------------------------------------------------------------------------------------------ fetching


async def _get(client: httpx.AsyncClient, url: str, timeout: float) -> httpx.Response:
    return await netsafe.get(url, client=client, timeout=timeout, deadline=timeout + 1.0,
                             max_bytes=netsafe.PAGE_MAX_BYTES)


async def _fetch(plid: str) -> dict | None:
    async with netsafe.async_client(transport=TRANSPORT, headers=HEADERS, timeout=PAGE_TIMEOUT_S) as client:
        not_found = False
        try:
            r = await _get(client, f"https://www.youtube.com/playlist?list={plid}", PAGE_TIMEOUT_S)
            if r.status_code == 200:
                got = parse_page(r.text)
                if got:
                    return dict(got, source="page")
                log.info("playlist %s: the page had no videos (layout change or empty); trying the feed", plid)
            else:
                not_found = r.status_code == 404
        except (httpx.HTTPError, netsafe.BlockedURL) as e:
            log.info("playlist %s: page fetch failed (%s)", plid, type(e).__name__)
        try:
            r = await _get(client, f"https://www.youtube.com/feeds/videos.xml?playlist_id={plid}", FEED_TIMEOUT_S)
            if r.status_code == 200:
                got = parse_feed(r.text)
                if got:
                    return dict(got, source="feed")
            not_found = not_found or r.status_code == 404
        except (httpx.HTTPError, netsafe.BlockedURL) as e:
            log.info("playlist %s: feed fetch failed (%s)", plid, type(e).__name__)
        if not_found:
            raise PlaylistUnavailable("That playlist is private or no longer on YouTube.", "not_found")
        return None


_inflight: dict[str, asyncio.Future] = {}


async def list_videos(url_or_id: str, *, refresh: bool = False) -> dict:
    """{playlistId, title, channel, url, videos: [{id, title, seconds}], totalSeconds, truncated, source}.
    Raises PlaylistUnavailable. Two asks for one playlist at once share one fetch."""
    plid = playlist_id(url_or_id)
    if not plid:
        raise PlaylistUnavailable("That is not a YouTube playlist link.", "bad_url")
    shipped = catalog.shipped_playlist(plid)
    if shipped and not refresh:
        return _out(dict(shipped, source="catalog", truncated=False))
    cached = _cached(plid)
    if cached and not refresh and fresh(cached[1]):
        return _out(dict(cached[0], source="cache"))
    if plid in _inflight:
        return await asyncio.shield(_inflight[plid])
    fut = asyncio.get_running_loop().create_future()
    _inflight[plid] = fut
    try:
        try:
            got = await _fetch(plid)
        except PlaylistUnavailable:
            raise
        except Exception:
            log.exception("playlist %s: fetch failed", plid)
            got = None
        if got:
            pl = catalog._clean_playlist(dict(got, playlistId=plid, planId=None))
            if pl:
                pl.update(truncated=bool(got.get("truncated")), source=got["source"])
                _save(pl)
                out = _out(pl)
                fut.set_result(out)
                return out
        if cached:
            out = _out(dict(cached[0], source="cache", stale=True))
            fut.set_result(out)
            return out
        raise PlaylistUnavailable("Could not reach YouTube to list that playlist. Try again in a moment.", "offline")
    except BaseException as e:
        if not fut.done():
            fut.set_exception(e)
            fut.exception()  # read: no "never retrieved" warning when nobody else waited
        raise
    finally:
        _inflight.pop(plid, None)


def _out(pl: dict) -> dict:
    secs = [v["seconds"] for v in pl["videos"] if isinstance(v.get("seconds"), int)]
    out = {k: pl.get(k) for k in ("playlistId", "title", "channel", "url", "planId")}
    out["videos"] = [dict(v) for v in pl["videos"]]
    out["videoCount"] = len(pl["videos"])
    out["totalSeconds"] = sum(secs) if len(secs) == len(pl["videos"]) else None
    out["truncated"] = bool(pl.get("truncated"))
    out["source"] = pl.get("source") or "page"
    if pl.get("stale"):
        out["stale"] = True
    return out


def video_minutes(seconds: int | None) -> int | None:
    return max(1, math.ceil(seconds / 60)) if isinstance(seconds, int) and seconds > 0 else None


def lessons_from(pl: dict) -> list[dict]:
    """A playlist's videos as plan lessons (one video, one lesson; built from the video like any pasted link)."""
    return [{"title": v["title"], "videoId": v["id"], "url": youtube.watch_url(v["id"]), "seconds": v.get("seconds"),
             "minutes": video_minutes(v.get("seconds"))} for v in pl["videos"]]


def dumps(pl: dict) -> str:  # debugging aid: python -m server.plans.playlist <url>
    return json.dumps(pl, ensure_ascii=False, indent=1)


if __name__ == "__main__":  # pragma: no cover - a manual check against the real page
    import sys

    print(dumps(asyncio.run(list_videos(sys.argv[1], refresh=True))))
