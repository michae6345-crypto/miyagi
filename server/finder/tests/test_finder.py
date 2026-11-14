"""Finder tests. They replay REAL responses recorded from YouTube, DuckDuckGo, GitHub, arXiv
and YouTube oEmbed (server/finder/tests/fixtures, re-record with
`python -m server.finder.tests.record`). No network, no Gemini."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest

from server.finder import cache, core as search_mod, env, gemini, sources, youtube
from server.finder import search

FX = Path(__file__).parent / "fixtures"
YT = json.loads((FX / "youtube_results.json").read_text())
OEMBED = json.loads((FX / "oembed.json").read_text())
DDG = (FX / "ddg.html").read_text()
GH = json.loads((FX / "github.json").read_text())
AX = (FX / "arxiv.xml").read_text()
KINDS = {"video", "blog", "notebook", "paper", "repo"}
DEAD = "https://lazyjobseeker.github.io/en/posts/physics-informed-neural-network-tutorials/"


# --------------------------------------------------------------------------- parsers

def test_parse_youtube_results():
    vids = youtube.parse_search(YT)
    assert len(vids) >= 5
    for v in vids:
        assert re.fullmatch(r"[\w-]{11}", v["videoId"])
        assert v["url"] == f"https://www.youtube.com/watch?v={v['videoId']}"
        assert v["duration_s"] >= 120 and v["title"] and v["channel"]
    assert any("convection" in v["title"].lower() and "pinn" in v["title"].lower() for v in vids)


def test_parse_ddg():
    hits = sources.parse_ddg(DDG)
    assert len(hits) >= 5
    assert all(h["url"].startswith("http") and "duckduckgo.com" not in h["url"] for h in hits)
    assert any(h["description"] for h in hits)


def test_parse_github_and_arxiv():
    repos = sources.parse_github(GH)
    assert repos and all(r["url"].startswith("https://github.com/") for r in repos)
    assert {r["kind"] for r in repos} <= {"repo", "notebook"}
    papers = sources.parse_arxiv(AX)
    assert papers and all(re.match(r"https://arxiv\.org/abs/\d{4}\.\d{4,5}$", p["url"]) for p in papers)
    assert all(p["kind"] == "paper" and p["authors"] and p["year"] for p in papers)


@pytest.mark.parametrize("url,kind", [
    ("https://www.youtube.com/watch?v=unBU1PwCnvQ", "video"),
    ("https://youtu.be/unBU1PwCnvQ", "video"),
    ("https://arxiv.org/abs/2109.01050", "paper"),
    ("https://colab.research.google.com/github/a/b/blob/main/x.ipynb", "notebook"),
    ("https://github.com/a1k12/characterizing-pinns-failure-modes", "repo"),
    ("https://towardsdatascience.com/some-pinn-post", "blog"),
])
def test_classify(url, kind):
    assert sources.classify(url) == kind


def test_helpers():
    assert youtube.parse_duration("22:40") == 1360 and youtube.parse_duration("1:02:03") == 3723
    assert youtube.fmt_duration(1360) == "22:40"
    assert gemini.short("one two three four five six seven eight nine ten eleven twelve thirteen.") .count(" ") == 11
    assert search_mod.url_key("https://arxiv.org/pdf/2109.01050v2.pdf") == search_mod.url_key("https://arxiv.org/abs/2109.01050")
    assert search_mod.make_id({"kind": "repo", "url": "https://github.com/Owner/Repo"}) == "gh-owner-repo"


# --------------------------------------------------------------------------- end to end (replayed)

def _transport(calls: list[str]) -> httpx.MockTransport:
    yt_page = f"<html><script>var ytInitialData = {json.dumps(YT)};</script></html>"

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        calls.append(url)
        host = req.url.host
        if host == "www.youtube.com" and req.url.path == "/results":
            return httpx.Response(200, text=yt_page)
        if host == "www.youtube.com" and req.url.path == "/oembed":
            vid = youtube.video_id(req.url.params["url"])
            data = OEMBED.get(vid)
            return httpx.Response(200, json=data) if data else httpx.Response(404, text="Not Found")
        if host == "html.duckduckgo.com":
            return httpx.Response(200, text=DDG)
        if host == "api.github.com":
            return httpx.Response(200, json=GH)
        if host == "export.arxiv.org":
            return httpx.Response(200, text=AX)
        if url == DEAD:
            return httpx.Response(404, text="gone")
        return httpx.Response(200, text="<html><title>ok</title></html>")  # HEAD/GET verification of indexed pages

    return httpx.MockTransport(handler)


def _known_urls() -> set[str]:
    urls = {youtube.watch_url(v) for v in OEMBED}
    urls |= {h["url"] for h in sources.parse_ddg(DDG)}
    urls |= {"https://github.com/joshuamills98/Convection-Diffusion-PINN"}
    urls |= {r["url"] for r in sources.parse_github(GH)} | {p["url"] for p in sources.parse_arxiv(AX)}
    return urls


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "_loaded", True)
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.setenv(k, "")
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(search_mod, "HTTP_TRANSPORT", _transport(calls))
    return calls


def _check_rows(rows: list[dict]) -> None:
    known = _known_urls()
    assert rows
    for r in rows:
        assert set(r) >= {"id", "kind", "title", "meta", "score", "reason", "url"}
        assert r["kind"] in KINDS
        assert isinstance(r["score"], int) and 0 <= r["score"] <= 100
        assert r["reason"] and len(r["reason"].split()) <= 12
        assert r["url"] in known, f"invented URL {r['url']}"  # never emit a URL no source returned
    assert len({r["id"] for r in rows}) == len(rows)


def test_search_replay_without_gemini(offline):
    streamed: list[dict] = []

    async def on_result(r):
        streamed.append(r)

    rows = asyncio.run(search("train a PINN on the convection equation", on_result))
    _check_rows(rows)
    assert {r["id"] for r in streamed} == {r["id"] for r in rows}  # everything returned was streamed
    assert rows[0]["kind"] == "video"  # build_lesson needs a video: the best one leads
    assert rows[0]["url"].startswith("https://www.youtube.com/watch?v=") and rows[0]["videoId"]
    assert DEAD not in {r["url"] for r in rows}  # a 404 is never emitted
    kinds = {r["kind"] for r in rows}
    assert {"video", "paper", "repo"} <= kinds
    assert not any(youtube.video_id(r["url"]) not in OEMBED for r in rows if r["kind"] == "video")
    # cached, and a second call is served from the cache without touching the network
    offline.clear()
    again = asyncio.run(search("Train a PINN on the convection   equation"))
    assert [r["id"] for r in again] == [r["id"] for r in rows] and offline == []


def test_search_replay_with_gemini_scores(offline, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def fake_score(key, goal, cands, **kw):
        return {c["id"]: {"score": 90 if "convection" in c["title"].lower() else 40,
                          "reason": "Exact topic, runnable code" if "convection" in c["title"].lower() else "Adjacent topic"}
                for c in cands}

    async def fake_skim(key, goal, video, warns, **kw):
        return {"score": 99 if "S5" in video["title"] else 10, "reason": "Clear, 22 min, PyTorch code-along",
                "hands_on": True, "outdated": False}

    async def no_grounding(ctx, q):
        return []

    monkeypatch.setattr(gemini, "score", fake_score)
    monkeypatch.setattr(gemini, "skim", fake_skim)
    monkeypatch.setattr(sources, "gemini_grounded", no_grounding)
    rows = asyncio.run(search("train a PINN on the convection equation", use_cache=False))
    _check_rows(rows)
    top = rows[0]
    assert top["kind"] == "video" and "S5" in top["title"]
    assert top["reason"] == "Clear, 22 min, PyTorch code-along"
    assert rows == sorted(rows, key=lambda r: -r["score"]) or rows[1:] == sorted(rows[1:], key=lambda r: -r["score"])


def test_orchestrator_call_shape(offline):
    """E4 calls `await finder.search(query)` and passes row["url"] to lesson.build_lesson."""
    rows = asyncio.run(search("train a PINN on the convection equation", use_cache=False))
    assert isinstance(rows, list) and all(isinstance(r["url"], str) for r in rows)
    assert youtube.video_id(rows[0]["url"])
    assert asyncio.run(search("   ")) == []
