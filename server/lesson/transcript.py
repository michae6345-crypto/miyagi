"""Video metadata + timestamped transcript for the transcript-based (Claude) build path.

Sources, in order (first that works wins; the result is cached in demo/cache/transcripts/):
1. The public watch page over plain HTTPS (title, description, caption tracks), then its caption
   track URL directly.
2. youtube-transcript-api.
YouTube rate-limits caption endpoints per IP (429 "Sorry..."), which is what (2) is for.
No frames: we only use what YouTube publishes as text (captions, title, description, chapters).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from server import netsafe

log = logging.getLogger("server.lesson")

WATCH_URL = "https://www.youtube.com/watch?v={vid}&hl=en"
_CHAPTER = re.compile(r"^\s*(?:\(|\[)?((?:\d{1,2}:)?\d{1,2}:\d{2})(?:\)|\])?\s*[-–:|]?\s*(.+?)\s*$", re.M)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept-Language": "en-US,en;q=0.9", "Cookie": "CONSENT=YES+1"}


def _cache_path(video_id: str):
    from .schema import REPO_ROOT

    return REPO_ROOT / "demo" / "cache" / "transcripts" / f"{video_id}.json"


async def fetch_video_info(video_id: str) -> dict:
    p = _cache_path(video_id)
    if p.is_file():
        info = json.loads(p.read_text(encoding="utf-8"))
        info.setdefault("sources", {})["cache"] = p.name
        return info
    info = await _fetch_video_info(video_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info


_meta_tasks: dict[str, asyncio.Task] = {}


async def fetch_metadata(video_id: str) -> dict:
    """Title, description, chapters, length and caption tracks from the watch page, fetched once per
    video per process (both engines use it; it loads even while YouTube 429s the caption endpoints)."""
    t = _meta_tasks.get(video_id)
    if t is None or (t.done() and (t.cancelled() or t.exception() is not None)):
        t = _meta_tasks[video_id] = asyncio.ensure_future(_fetch_metadata(video_id))
    return dict(await asyncio.shield(t))


async def _fetch_metadata(video_id: str) -> dict:
    info: dict = {"video_id": video_id, "title": "", "description": "", "length_s": None, "chapters": [], "transcript": [],
                  "sources": {}, "errors": [], "_tracks": []}
    page = None
    # The plain watch page is fast and loads even while YouTube 429s caption endpoints.
    try:  # netsafe: http(s) only, every redirect hop must be a public host, the page capped
        r = await netsafe.get(WATCH_URL.format(vid=video_id), headers=_HEADERS, timeout=10,
                              max_bytes=netsafe.PAGE_MAX_BYTES)
        r.raise_for_status()
        if _player_response(r.text):
            page = r.text
            info["sources"]["metadata"] = "youtube.com"
        else:
            info["errors"].append("watch page: no player data (consent/bot page?)")
    except Exception as e:  # noqa: BLE001
        info["errors"].append(f"watch page: {str(e)[:160]}")

    player = _player_response(page) if page else None
    if player:
        vd = player.get("videoDetails") or {}
        info["title"] = vd.get("title", "")
        info["description"] = vd.get("shortDescription", "")
        info["length_s"] = int(vd["lengthSeconds"]) if str(vd.get("lengthSeconds", "")).isdigit() else None
        info["chapters"] = parse_chapters(info["description"])
        info["_tracks"] = (((player.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get("captionTracks")) or []
    return info


async def _fetch_video_info(video_id: str) -> dict:
    """-> {video_id, title, description, length_s, chapters:[{t,title}], transcript:[{t,text}], sources:{...}, errors:[...]}.
    Raises RuntimeError when no transcript could be obtained (the transcript path can't work without one)."""
    info = await fetch_metadata(video_id)
    info["errors"] = list(info.get("errors") or [])
    info["sources"] = dict(info.get("sources") or {})
    tracks = info.pop("_tracks", [])
    if not info["transcript"] and tracks:
        try:
            info["transcript"] = await _direct_captions(tracks)
            info["sources"]["transcript"] = "youtube.com timedtext"
        except Exception as e:  # noqa: BLE001
            info["errors"].append(f"timedtext: {str(e)[:160]}")
    if not info["transcript"]:
        try:
            info["transcript"] = await asyncio.to_thread(_yta_transcript, video_id)
            info["sources"]["transcript"] = "youtube-transcript-api"
        except Exception as e:  # noqa: BLE001
            info["errors"].append(f"youtube-transcript-api: {str(e)[:200]}")
    if not info["transcript"]:
        raise RuntimeError(f"no transcript for {video_id}: " + "; ".join(info["errors"]))
    return info


def parse_chapters(description: str) -> list[dict]:
    from .builder import parse_ts  # local import: builder imports this module

    out = []
    for ts, title in _CHAPTER.findall(description or ""):
        t = parse_ts(ts)
        if t is not None:
            out.append({"t": t, "title": title})
    # YouTube only treats it as a chapter list if it starts at 0:00 and has >= 3 entries
    return out if len(out) >= 3 and out[0]["t"] == 0 else []


def format_metadata(info: dict) -> str:
    """Title, length, chapters and description (no transcript): context for the video-watching model."""
    lines = [f"Title: {info.get('title', '')}"]
    if info.get("length_s"):
        lines.append(f"Length: {_mmss(info['length_s'])}")
    if info.get("chapters"):
        lines.append("Chapters (from the description):")
        lines += [f"  {_mmss(c['t'])} {c['title']}" for c in info["chapters"]]
    desc = (info.get("description") or "").strip()
    if desc:
        lines.append("Description (links here are the tutorial's code/data):\n" + desc[:3000])
    return "\n".join(lines)


def format_for_prompt(info: dict, max_chars: int = 120_000) -> str:
    lines = [f"Title: {info['title']}"]
    if info.get("length_s"):
        lines.append(f"Length: {_mmss(info['length_s'])}")
    if info.get("chapters"):
        lines.append("Chapters (from the description):")
        lines += [f"  {_mmss(c['t'])} {c['title']}" for c in info["chapters"]]
    desc = (info.get("description") or "").strip()
    if desc:
        lines.append("Description:\n" + desc[:3000])
    lines.append("Transcript (start time, then the spoken text):")
    body = "\n".join(f"[{_mmss(s['t'])}] {s['text']}" for s in info["transcript"])
    if len(body) > max_chars:  # very long videos: keep it whole rather than silently cut, but warn
        log.warning("transcript is %d chars (> %d); sending it whole", len(body), max_chars)
    lines.append(body)
    return "\n".join(lines)


def _mmss(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def _best_track(tracks: list[dict]) -> str:
    def rank(tr: dict) -> tuple:
        lang = tr.get("languageCode", "")
        return (not lang.startswith("en"), tr.get("kind") == "asr")  # English first, manual before auto

    return sorted(tracks, key=rank)[0]["baseUrl"] + "&fmt=json3"


async def _direct_captions(tracks: list[dict]) -> list[dict]:
    """The caption track's baseUrl comes out of the watch page, so it goes through netsafe like any other link."""
    r = await netsafe.get(_best_track(tracks), headers=_HEADERS, timeout=30, max_bytes=netsafe.PAGE_MAX_BYTES)
    r.raise_for_status()
    return _parse_json3(r.text)


def _parse_json3(raw: str) -> list[dict]:
    out = []
    for ev in json.loads(raw).get("events", []):
        text = "".join(s.get("utf8", "") for s in ev.get("segs") or []).strip()
        if text:
            out.append({"t": ev.get("tStartMs", 0) / 1000.0, "text": text})
    if not out:
        raise RuntimeError("empty caption track")
    return out


def _yta_transcript(video_id: str) -> list[dict]:
    from youtube_transcript_api import YouTubeTranscriptApi

    fetched = YouTubeTranscriptApi().fetch(video_id, languages=("en", "en-US", "en-GB"))
    return [{"t": float(s.start), "text": s.text.replace("\n", " ").strip()} for s in fetched if s.text.strip()]


def _player_response(html: str) -> dict | None:
    i = html.find("ytInitialPlayerResponse")
    if i < 0:
        return None
    j = html.find("{", i)
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, j)
        return obj
    except (ValueError, json.JSONDecodeError):
        return None
