"""YouTube: parse the real search results page, verify with oEmbed, read a watch page
(duration, description), and scan comments (fetched via Bright Data) for "outdated" warnings."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([\w-]{11})")
_INITIAL_DATA = re.compile(r"(?:var ytInitialData|window\[\"ytInitialData\"\])\s*=\s*(\{.*?\});\s*</script>", re.S)


def video_id(url: str) -> str | None:
    m = YOUTUBE_ID.search(url or "")
    return m.group(1) if m else None


def watch_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def initial_data(html: str) -> dict | None:
    m = _INITIAL_DATA.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _walk(o: Any, key: str):
    if isinstance(o, dict):
        if key in o:
            yield o[key]
        for v in o.values():
            yield from _walk(v, key)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v, key)


def _text(o: Any) -> str:
    if not isinstance(o, dict):
        return ""
    if "simpleText" in o:
        return o["simpleText"]
    return "".join(r.get("text", "") for r in o.get("runs", []))


def parse_duration(s: str | None) -> int | None:
    if not s or not re.fullmatch(r"\d+(:\d{1,2}){0,2}", s.strip()):
        return None
    secs = 0
    for part in s.strip().split(":"):
        secs = secs * 60 + int(part)
    return secs


def duration_label(secs: int | None) -> str | None:
    """'22 min', '1 h 56 min'."""
    if not secs:
        return None
    h, m = divmod(round(secs / 60), 60)
    return f"{h} h {m} min" if h and m else (f"{h} h" if h else f"{m} min")


def fmt_duration(secs: int | None) -> str | None:
    if not secs:
        return None
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_search(data: dict, limit: int = 12) -> list[dict]:
    """videoRenderer items from ytInitialData of /results (skips shorts, live and ads)."""
    out, seen = [], set()
    for v in _walk(data, "videoRenderer"):
        vid = v.get("videoId")
        if not vid or vid in seen:
            continue
        length = _text(v.get("lengthText") or {})
        secs = parse_duration(length)
        if secs is None or secs < 120:  # live streams have no length; < 2 min is a teaser, not a tutorial
            continue
        seen.add(vid)
        snippet = " ".join(_text(s.get("snippetText", {})) for s in v.get("detailedMetadataSnippets", []) or [])
        thumbs = (v.get("thumbnail") or {}).get("thumbnails") or []
        badges = [((b.get("metadataBadgeRenderer") or {}).get("label") or "") for b in (v.get("badges") or [])]
        em = v.get("expandableMetadata") or {}
        chapters = {_text(m.get("title") or {}) for m in _walk(em, "macroMarkersListItemRenderer")}
        summary = _text(((em.get("expandableMetadataRenderer") or {}).get("header") or {}).get("collapsedTitle") or {})
        out.append({
            "videoId": vid,
            "url": watch_url(vid),
            "title": _text(v.get("title") or {}),
            "channel": _text(v.get("ownerText") or v.get("longBylineText") or {}),
            "duration_s": secs,
            "views": _text(v.get("shortViewCountText") or v.get("viewCountText") or {}),
            "published": _text(v.get("publishedTimeText") or {}),
            "description": " ".join(x for x in (summary, snippet or _text(v.get("descriptionSnippet") or {})) if x)[:900],
            "chapters": len(chapters - {""}),
            "captions": True if "CC" in badges else None,  # V5: no CC badge isn't "no captions" (auto captions have none)
            "thumbnail": thumbs[-1]["url"].split("?")[0] if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        })
        if len(out) >= limit:
            break
    return out


async def oembed(client: httpx.AsyncClient, url: str) -> dict | None:
    """200 only for a real, public, embeddable video. Returns {title, author_name, thumbnail_url}."""
    try:
        r = await client.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=6)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return json.loads(r.content)  # bytes → JSON detects UTF-8 (r.json() mis-decoded some titles)
    except ValueError:
        return None


def parse_watch(html: str) -> dict:
    """Duration / description / view count from a watch page (ytInitialPlayerResponse)."""
    out: dict = {}
    m = re.search(r'"lengthSeconds":"(\d+)"', html)
    if m:
        out["duration_s"] = int(m.group(1))
    m = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html)
    if m:
        try:
            out["description"] = json.loads(f'"{m.group(1)}"')[:1500]
        except ValueError:
            pass
    m = re.search(r'"viewCount":"(\d+)"', html)
    if m:
        out["views"] = f"{human_count(int(m.group(1)))} views"
    chapters = set(re.findall(r'"chapterRenderer":\{"title":\{"simpleText":"((?:[^"\\]|\\.)*)"', html))
    if chapters:
        out["chapters"] = len(chapters)
    if '"captionTracks"' in html:
        out["captions"] = True
    m = re.search(r'"uploadDate":"([\d-]+)', html) or re.search(r'"publishDate":"([\d-]+)', html)
    if m:
        out["published"] = m.group(1)
    return out


def human_count(n: int) -> str:
    for div, suf in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= div:
            v = n / div
            return f"{v:.1f}".rstrip("0").rstrip(".") + suf
    return str(n)


def parse_comments(records: list | dict, limit: int = 40) -> list[dict]:
    """Normalise comment records (Bright Data YouTube-comments dataset output) to {text, likes}."""
    if isinstance(records, dict):
        records = records.get("data") or records.get("comments") or []
    out = []
    for c in records or []:
        if not isinstance(c, dict):
            continue
        text = str(c.get("comment_text") or c.get("text") or c.get("comment") or "").strip()
        if text:
            out.append({"text": text[:400], "likes": c.get("likes") or c.get("num_likes") or 0})
        if len(out) >= limit:
            break
    return out


WARNING_WORDS = re.compile(
    r"outdated|deprecated|doesn'?t work|does not work|not working|broken|error|old version|no longer|"
    r"attributeerror|modulenotfound|importerror|tf ?1\.|tensorflow 1|version",
    re.I,
)


def warning_comments(comments: list[dict], limit: int = 5) -> list[str]:
    return [c["text"][:200] for c in comments if WARNING_WORDS.search(c["text"])][:limit]
