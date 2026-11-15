"""Video metadata for preflight: oEmbed + the watch page (plain fetch, Bright Data Unlocker as the
fallback), and chapters (YouTube's own chapter list, else timestamps in the description).

Everything here is parsed from what YouTube actually serves; nothing is guessed."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

from server.finder import brightdata, youtube
from server.finder.env import Keys

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
HEADERS["Cookie"] = "CONSENT=YES+1; SOCS=CAI"  # skip the EU consent interstitial

_TS = r"(?:\d{1,2}:)?\d{1,2}:\d{2}"
_TS_LINE = re.compile(rf"^\s*[\[(]?(?P<ts>{_TS})[\])]?\s*(?:[-–—:|•·]\s*)?(?P<title>.*\S)?\s*$")
_TS_END = re.compile(rf"^(?P<title>.*\S)\s*[-–—:|(\[]?\s*(?P<ts>{_TS})[\])]?\s*$")


def to_seconds(ts: str) -> int:
    secs = 0
    for part in ts.split(":"):
        secs = secs * 60 + int(part)
    return secs


def _finish(chs: list[dict], duration_s: int | None) -> list[dict]:
    for i, c in enumerate(chs):
        nxt = chs[i + 1]["start"] if i + 1 < len(chs) else duration_s
        c["end"] = nxt if nxt and nxt > c["start"] else None
        c["index"] = i
    return chs


def parse_chapters(description: str, duration_s: int | None = None) -> list[dict]:
    """Chapters from description timestamps, YouTube's rules: the list starts at 0:00, ascends,
    and has at least 3 entries. A later non-ascending timestamp (a "Corrections:" list, a comment
    about a moment) ends the run. Returns [{index, start, end, title}] or []."""
    lines = (description or "").splitlines()
    best: list[dict] = []
    run: list[dict] = []
    for line in lines:
        m = _TS_LINE.match(line)
        ts, title = (m.group("ts"), m.group("title") or "") if m else (None, "")
        if not ts and (m2 := _TS_END.match(line)) and len(m2.group("title")) < 120:
            ts, title = m2.group("ts"), m2.group("title")
        if not ts:
            continue
        start = to_seconds(ts)
        if duration_s and start > duration_s:
            continue
        title = re.sub(r"^[\s\-–—:|•·]+|[\s\-–—:|•·]+$", "", title)[:120] or f"Part at {ts}"
        if start == 0:  # a new candidate run
            if len(run) > len(best):
                best = run
            run = [{"start": 0, "title": title}]
        elif run and start > run[-1]["start"]:
            run.append({"start": start, "title": title})
        elif run:  # out of order: the chapter list is over
            if len(run) > len(best):
                best = run
            run = []
    if len(run) > len(best):
        best = run
    return _finish(best, duration_s) if len(best) >= 3 else []


def chapters_from_page(data: dict | None, duration_s: int | None) -> list[dict]:
    """YouTube's own chapter list (chapterRenderer in ytInitialData), when the page has one."""
    if not data:
        return []
    out, seen = [], set()
    for ch in youtube._walk(data, "chapterRenderer"):
        if not isinstance(ch, dict) or "timeRangeStartMillis" not in ch:
            continue
        start = int(ch["timeRangeStartMillis"]) // 1000
        if start in seen:
            continue
        seen.add(start)
        out.append({"start": start, "title": youtube._text(ch.get("title") or {})[:120] or f"Chapter {len(out) + 1}"})
    out.sort(key=lambda c: c["start"])
    return _finish(out, duration_s) if len(out) >= 2 else []


def _json_str(html: str, key: str) -> str | None:
    m = re.search(rf'"{key}":\s?"((?:[^"\\]|\\.)*)"', html)
    if not m:
        return None
    try:
        return json.loads(f'"{m.group(1)}"')
    except ValueError:
        return None


def parse_watch_page(html: str) -> dict:
    """title, channel, duration_s, description (full), keywords, category, published, chapters."""
    out: dict = {}
    m = re.search(r'"lengthSeconds":\s?"(\d+)"', html)
    if m:
        out["duration_s"] = int(m.group(1))
    if (d := _json_str(html, "shortDescription")) is not None:
        out["description"] = d
    for key, name in (("title", "title"), ("ownerChannelName", "channel"), ("category", "category")):
        # videoDetails.title comes before any other "title" key inside ytInitialPlayerResponse
        seg = html[html.find('"videoDetails"'):] if key == "title" and '"videoDetails"' in html else html
        if (v := _json_str(seg, key)) and name not in out:
            out[name] = v
    if not out.get("channel") and (v := _json_str(html, "author")):
        out["channel"] = v
    m = re.search(r'"keywords":\s?(\[[^\]]*\])', html)
    if m:
        try:
            out["keywords"] = [str(k) for k in json.loads(m.group(1))][:20]
        except ValueError:
            pass
    m = re.search(r'"(?:uploadDate|publishDate)":\s?"([\d-]+)', html)
    if m:
        out["published"] = m.group(1)
    chs = chapters_from_page(youtube.initial_data(html), out.get("duration_s"))
    if chs:
        out["chapters"], out["chaptersFrom"] = chs, "youtube"
    elif (chs := parse_chapters(out.get("description", ""), out.get("duration_s"))):
        out["chapters"], out["chaptersFrom"] = chs, "description"
    return out


async def _direct(client: httpx.AsyncClient, url: str, timeout: float) -> str:
    r = await client.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError(f"watch page HTTP {r.status_code}")
    if "lengthSeconds" not in r.text:
        raise RuntimeError("watch page has no player data (consent / bot wall)")
    return r.text


async def fetch(client: httpx.AsyncClient, url: str, keys: Keys, *, timeout: float = 3.0) -> tuple[dict, list[str]]:
    """(meta, notes). meta has videoId/url plus whatever parsed; notes say what failed."""
    vid = youtube.video_id(url)
    notes: list[str] = []
    meta: dict = {"videoId": vid, "url": youtube.watch_url(vid) if vid else url}
    if not vid:
        notes.append("not a YouTube video URL")
        return meta, notes
    watch = youtube.watch_url(vid) + "&hl=en"

    async def page() -> str | None:
        try:
            return await _direct(client, watch, timeout)
        except Exception as e:  # noqa: BLE001
            notes.append(f"watch page: {str(e)[:100]}")
        if brightdata.available(keys):
            try:
                html = await brightdata.unlock(client, keys, watch, timeout=timeout)
                if "lengthSeconds" in html:
                    notes.append("watch page via Bright Data Unlocker")
                    return html
                notes.append("Bright Data Unlocker: no player data")
            except Exception as e:  # noqa: BLE001
                notes.append(f"Bright Data Unlocker: {str(e)[:100]}")
        return None

    async def oembed() -> dict | None:
        try:
            return await asyncio.wait_for(youtube.oembed(client, meta["url"]), timeout)
        except TimeoutError:
            return None

    oe, html = await asyncio.gather(oembed(), page())
    if oe:
        meta["title"] = oe.get("title") or ""
        meta["channel"] = oe.get("author_name") or ""
        meta["thumbnail"] = oe.get("thumbnail_url") or ""
    else:
        notes.append("oEmbed: no answer (private, removed or not embeddable?)")
    if html:
        parsed = parse_watch_page(html)
        for k, v in parsed.items():
            if v not in (None, "", []) and not (k in ("title", "channel") and meta.get(k)):
                meta[k] = v
    return meta, notes
