from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from server.plans import catalog, playlist
from server.plans.tests.helpers import fixture, youtube_transport

PLID = "PLtestTESTtest0123456789"


@pytest.mark.parametrize("text, want", [
    (f"https://www.youtube.com/playlist?list={PLID}", PLID),
    (f"youtube.com/playlist?list={PLID}", PLID),
    (f"https://m.youtube.com/watch?v=aaaaaaaaaa1&list={PLID}&index=2", PLID),
    (f"https://youtu.be/aaaaaaaaaa1?list={PLID}", PLID),
    (PLID, PLID),
    ("https://www.youtube.com/watch?v=aaaaaaaaaa1", None),
    (f"https://evil.example/playlist?list={PLID}", None),
    (f"https://youtube.com.evil.example/playlist?list={PLID}", None),
    ("https://www.youtube.com/playlist?list=bad id", None),
    ("", None),
])
def test_playlist_id(text, want):
    assert playlist.playlist_id(text) == want


def test_parse_page_classic_layout():
    got = playlist.parse_page(fixture("playlist_page.html"))
    assert got["title"] == "Python for beginners" and got["channel"] == "Example Channel"
    assert [(v["id"], v["seconds"]) for v in got["videos"]] == [
        ("aaaaaaaaaa1", 929), ("aaaaaaaaaa2", 21 * 60 + 12), ("aaaaaaaaaa4", 1745)]  # private and duplicate dropped
    assert got["videos"][2]["title"] == "Lesson 4: Lists, tuples and sets"
    assert got["truncated"] is True  # a continuation: more than the first page


def test_parse_page_lockup_layout():
    got = playlist.parse_page(fixture("playlist_lockup.html"))
    assert got["title"] == "Blender in an afternoon" and got["channel"] == "Donut Studio"
    assert [(v["id"], v["title"], v["seconds"]) for v in got["videos"]] == [
        ("bbbbbbbbbb1", "Blender part 1", 3723), ("bbbbbbbbbb2", "Blender part 2", None)]
    assert got["truncated"] is False


def test_parse_page_and_feed_with_nothing():
    assert playlist.parse_page(fixture("playlist_empty.html")) is None
    assert playlist.parse_page("<html>no data</html>") is None
    assert playlist.parse_feed("<not xml") is None
    assert playlist.parse_feed('<feed xmlns="http://www.w3.org/2005/Atom"><title>t</title></feed>') is None


def test_parse_feed():
    got = playlist.parse_feed(fixture("playlist_feed.xml"))
    assert got["title"] == "Rust from zero" and got["channel"] == "Example Rustacean"
    assert [v["id"] for v in got["videos"]] == ["ccccccccccc", "ddddddddddd"]
    assert all(v["seconds"] is None for v in got["videos"])


@pytest.mark.asyncio
async def test_shipped_playlist_needs_no_network():
    pl = catalog.playlists("intro-python")[0]
    out = await playlist.list_videos(pl["url"])  # the autouse transport fails any fetch
    assert out["source"] == "catalog" and out["planId"] == "intro-python"
    assert out["videoCount"] == len(pl["videos"]) > 5 and out["totalSeconds"] > 0


@pytest.mark.asyncio
async def test_page_fetch_then_cache(monkeypatch, plans_state):
    calls: list[str] = []
    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({"/playlist": (200, fixture("playlist_page.html"))}, calls))
    t0 = time.monotonic()
    out = await playlist.list_videos(f"https://www.youtube.com/playlist?list={PLID}")
    assert time.monotonic() - t0 < 2.0
    assert out["source"] == "page" and out["playlistId"] == PLID and out["videoCount"] == 3
    assert out["totalSeconds"] == 929 + 1272 + 1745 and out["truncated"] is True and out["planId"] is None
    assert len(calls) == 1 and f"list={PLID}" in calls[0]
    cached = json.loads((plans_state / "plans" / "playlists" / f"{PLID}.json").read_text())
    assert cached["playlist"]["videos"][0]["id"] == "aaaaaaaaaa1"
    again = await playlist.list_videos(PLID)
    assert again["source"] == "cache" and again["videos"] == out["videos"] and len(calls) == 1


@pytest.mark.asyncio
async def test_feed_when_the_page_has_no_videos(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({
        "/playlist": (200, fixture("playlist_empty.html")), "/feeds/videos.xml": (200, fixture("playlist_feed.xml"))}, calls))
    out = await playlist.list_videos(PLID)
    assert out["source"] == "feed" and out["title"] == "Rust from zero" and out["totalSeconds"] is None
    assert len(calls) == 2 and "playlist_id=" + PLID in calls[1]


@pytest.mark.asyncio
async def test_missing_playlist(monkeypatch):
    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({}, []))
    with pytest.raises(playlist.PlaylistUnavailable) as e:
        await playlist.list_videos(PLID)
    assert e.value.reason == "not_found"
    with pytest.raises(playlist.PlaylistUnavailable) as e:
        await playlist.list_videos("https://example.com/x")
    assert e.value.reason == "bad_url"


@pytest.mark.asyncio
async def test_offline_serves_a_stale_copy_else_fails(monkeypatch, plans_state):
    down = youtube_transport({"/playlist": (0, httpx.ConnectError("down")),
                              "/feeds/videos.xml": (0, httpx.ConnectTimeout("slow"))}, [])
    monkeypatch.setattr(playlist, "TRANSPORT", down)
    with pytest.raises(playlist.PlaylistUnavailable) as e:
        await playlist.list_videos(PLID)
    assert e.value.reason == "offline"
    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({"/playlist": (200, fixture("playlist_page.html"))}, []))
    await playlist.list_videos(PLID)
    monkeypatch.setattr(playlist, "CACHE_TTL_S", 0.0)
    monkeypatch.setattr(playlist, "TRANSPORT", down)
    out = await playlist.list_videos(PLID)
    assert out["source"] == "cache" and out.get("stale") is True and out["videoCount"] == 3


@pytest.mark.asyncio
async def test_a_slow_page_is_cut_off_by_the_deadline(monkeypatch):
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, text="", request=request)

    monkeypatch.setattr(playlist, "PAGE_TIMEOUT_S", 0.2)
    monkeypatch.setattr(playlist, "FEED_TIMEOUT_S", 0.2)
    monkeypatch.setattr(playlist, "TRANSPORT", httpx.MockTransport(slow))
    t0 = time.monotonic()
    with pytest.raises(playlist.PlaylistUnavailable):
        await playlist.list_videos(PLID)
    assert time.monotonic() - t0 < 4.0


@pytest.mark.asyncio
async def test_two_asks_share_one_fetch(monkeypatch):
    calls: list[str] = []
    page = fixture("playlist_page.html")

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        await asyncio.sleep(0.05)
        return httpx.Response(200, text=page, request=request)

    monkeypatch.setattr(playlist, "TRANSPORT", httpx.MockTransport(handler))
    a, b = await asyncio.gather(playlist.list_videos(PLID), playlist.list_videos(PLID))
    assert a["videos"] == b["videos"] and len(calls) == 1


def test_lessons_from_a_playlist():
    pl = {"videos": [{"id": "aaaaaaaaaa1", "title": "One", "seconds": 61}, {"id": "aaaaaaaaaa2", "title": "Two",
                                                                           "seconds": None}]}
    les = playlist.lessons_from(pl)
    assert les[0] == {"title": "One", "videoId": "aaaaaaaaaa1", "url": "https://www.youtube.com/watch?v=aaaaaaaaaa1",
                      "seconds": 61, "minutes": 2}
    assert les[1]["minutes"] is None


def test_cache_freshness_needs_a_non_negative_age():
    now = 1_800_000_000.0
    assert playlist.fresh(now - 60, now) and playlist.fresh(now, now)
    assert not playlist.fresh(now - playlist.CACHE_TTL_S, now)  # stale
    assert not playlist.fresh(now + 3600, now)  # stamped in the future: the clock moved backwards since


@pytest.mark.asyncio
async def test_a_cache_from_the_future_is_refetched(monkeypatch, plans_state):
    calls: list[str] = []
    monkeypatch.setattr(playlist, "TRANSPORT", youtube_transport({"/playlist": (200, fixture("playlist_page.html"))}, calls))
    await playlist.list_videos(PLID)
    path = plans_state / "plans" / "playlists" / f"{PLID}.json"
    data = json.loads(path.read_text())
    data["fetchedAt"] = time.time() + 7 * 24 * 3600  # written before the clock was set back a week
    path.write_text(json.dumps(data))
    out = await playlist.list_videos(PLID)
    assert out["source"] == "page" and len(calls) == 2
