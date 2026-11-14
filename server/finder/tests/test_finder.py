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

from server.finder import cache, claude, core as search_mod, env, gemini, sources, youtube
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
        page = "<html><title>ok</title><body><p>" + "A tutorial paragraph with code. " * 20 + "</p></body></html>"
        return httpx.Response(200, text=page)  # HEAD/GET verification and page reads of indexed pages

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
    monkeypatch.setattr(env, "_shared", lambda name: None)  # ignore server.config app keys
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "GITHUB_TOKEN", "ANTHROPIC_API_KEY"):
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


def test_search_replay_claude_scores_gemini_watches(offline, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")

    async def claude_score(key, goal, cands, **kw):
        return {c["id"]: {"score": 90 if "convection" in c["title"].lower() else 40,
                          "reason": "Exact topic, runnable code" if "convection" in c["title"].lower() else "Adjacent topic"}
                for c in cands}

    async def claude_read(key, goal, item, text, **kw):
        return {"teaches_goal": True, "score": 88, "summary": "Teaches it end to end with PyTorch code",
                "prerequisites": ["autograd"], "code": "PyTorch script"}

    async def fake_skim(key, goal, video, warns, **kw):
        return {"score": 99 if "S5" in video["title"] else 10, "reason": "Clear, 22 min, PyTorch code-along",
                "hands_on": True, "outdated": False}

    async def gemini_must_not_score(*a, **kw):
        raise AssertionError("Gemini scored although Claude answered")

    async def no_claude_search(ctx, q, **kw):
        return []

    monkeypatch.setattr(claude, "score", claude_score)
    monkeypatch.setattr(claude, "read", claude_read)
    monkeypatch.setattr(gemini, "skim", fake_skim)
    monkeypatch.setattr(gemini, "score", gemini_must_not_score)
    monkeypatch.setattr(sources, "claude_search", no_claude_search)
    rows = asyncio.run(search("train a PINN on the convection equation", use_cache=False))
    _check_rows(rows)
    top = rows[0]
    assert top["kind"] == "video" and "S5" in top["title"]
    assert top["reason"] == "Clear, 22 min, PyTorch code-along" and top["watched"] == "watched by Gemini"
    read = [r for r in rows if r.get("watched") == "read by Claude"]
    assert read and all(r["kind"] != "video" and r["prerequisites"] == ["autograd"] for r in read)
    assert all(r["scoredBy"].startswith("claude") for r in rows)


def test_orchestrator_call_shape(offline):
    """E4 calls `await finder.search(query)` and passes row["url"] to lesson.build_lesson."""
    rows = asyncio.run(search("train a PINN on the convection equation", use_cache=False))
    assert isinstance(rows, list) and all(isinstance(r["url"], str) for r in rows)
    assert youtube.video_id(rows[0]["url"])
    assert asyncio.run(search("   ")) == []


# --------------------------------------------------------------------------- Claude search + fallbacks

from types import SimpleNamespace as NS  # noqa: E402

REAL_CLAUDE_URL = "https://github.com/dome272/Diffusion-Models-pytorch"
INVENTED_URL = "https://example-made-up-tutorials.com/diffusion"


def _fake_claude_response():
    results = [NS(url=REAL_CLAUDE_URL, title="dome272/Diffusion-Models-pytorch", page_age=None),
               NS(url="https://www.youtube.com/watch?v=TgTQE_muXec", title="Coding a Diffusion Model From Scratch", page_age=None)]
    text = ("```json\n" + json.dumps([
        {"url": INVENTED_URL, "kind": "blog", "why": "made up"},
        {"url": REAL_CLAUDE_URL + "/", "kind": "repo", "why": "Exact DDPM in PyTorch"},
    ]) + "\n```")
    return NS(
        content=[NS(type="server_tool_use", input={"query": "diffusion pytorch tutorial"}),
                 NS(type="web_search_tool_result", content=results),
                 NS(type="text", text=text)],
        stop_reason="end_turn", usage=NS(input_tokens=1, output_tokens=1),
    )


def test_claude_search_keeps_only_tool_result_urls(monkeypatch):
    async def create(**kw):
        assert kw["tools"][0]["name"] == "web_search"
        return _fake_claude_response()

    monkeypatch.setattr(claude, "client", lambda key: NS(messages=NS(create=create)))
    found, info = asyncio.run(claude.search("k", "train a diffusion model in pytorch"))
    urls = [f["url"] for f in found]
    assert INVENTED_URL not in urls  # Claude wrote it, the search tool never returned it
    assert urls[0] == REAL_CLAUDE_URL and found[0]["picked"] and found[0]["why"] == "Exact DDPM in PyTorch"
    assert "https://www.youtube.com/watch?v=TgTQE_muXec" in urls  # unpicked search results are real too
    assert info["queries"] == ["diffusion pytorch tutorial"] and info["picked"] == 1


def test_rows_say_plainly_when_not_watched_or_read(offline, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")

    async def gemini_429(*a, **kw):
        raise RuntimeError("Gemini failed: 429 RESOURCE_EXHAUSTED quota")

    async def claude_score(key, goal, cands, **kw):
        return {c["id"]: {"score": 77, "reason": "Scored by Claude"} for c in cands}

    async def claude_read_timeout(*a, **kw):
        raise asyncio.TimeoutError()

    async def no_source(ctx, q, **kw):
        return []

    monkeypatch.setattr(gemini, "skim", gemini_429)
    monkeypatch.setattr(claude, "score", claude_score)
    monkeypatch.setattr(claude, "read", claude_read_timeout)
    monkeypatch.setattr(sources, "claude_search", no_source)
    rows = asyncio.run(search("train a PINN on the convection equation", use_cache=False))
    _check_rows(rows)
    assert all(r["scoredBy"] == "claude" for r in rows)
    top_video = rows[0]
    assert top_video["watched"] == "not watched: Gemini quota"  # said plainly, never faked
    assert "not watched: Gemini quota" in top_video["meta"]
    assert any(r.get("watched", "").startswith("not read: Claude") for r in rows if r["kind"] != "video")


def test_gemini_scores_only_when_claude_fails(offline, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")

    async def claude_down(*a, **kw):
        raise RuntimeError("anthropic 529 overloaded")

    async def gemini_score(key, goal, cands, **kw):
        return {c["id"]: {"score": 60, "reason": "Gemini fallback"} for c in cands}

    async def skim_ok(key, goal, video, warns, **kw):
        return {"score": 70, "reason": "Watched", "hands_on": True, "outdated": False}

    async def no_source(ctx, q, **kw):
        return []

    monkeypatch.setattr(claude, "score", claude_down)
    monkeypatch.setattr(claude, "read", claude_down)
    monkeypatch.setattr(gemini, "score", gemini_score)
    monkeypatch.setattr(gemini, "skim", skim_ok)
    monkeypatch.setattr(sources, "claude_search", no_source)
    rows = asyncio.run(search("train a PINN on the convection equation", use_cache=False))
    assert {r["scoredBy"].split("+")[0] for r in rows} == {"gemini"}


def test_claude_candidates_flow_into_results(offline, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")

    async def create(**kw):
        return _fake_claude_response()

    async def claude_fail_score(*a, **kw):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(claude, "client", lambda key: NS(messages=NS(create=create)))
    monkeypatch.setattr(claude, "score", claude_fail_score)
    rows = asyncio.run(search("train a PINN on the convection equation", use_cache=False))
    by_url = {r["url"]: r for r in rows}
    assert by_url[REAL_CLAUDE_URL]["source"] == "claude" and by_url[REAL_CLAUDE_URL]["kind"] == "repo"
    assert INVENTED_URL not in by_url
    assert all(r["scoredBy"] == "keywords" for r in rows)  # both models down -> labelled keyword score


# --------------------------------------------------------------------------- Bright Data

from server.finder import brightdata  # noqa: E402


def _bd_keys():
    return env.Keys(gemini=None, brightdata="test-bd", anthropic=None, serp_zone="serp_api1",
                    unlocker_zone="web_unlocker1", github=None)


def test_brightdata_comments_fail_fast_and_labelled(monkeypatch):
    monkeypatch.setattr(brightdata, "_off_until", 0.0)
    monkeypatch.setattr(brightdata, "_comments_off_until", 0.0)
    keys = _bd_keys()

    def run(handler):
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
                return await brightdata.youtube_comments(c, keys, "https://www.youtube.com/watch?v=V8FvyuObouc")
        return asyncio.run(go())

    # a video without comments: the dataset answers 200 with an error record (real response shape)
    dead = [{"input": {"url": "https://www.youtube.com/watch?v=V8FvyuObouc"}, "error": "No comments exists on the video", "error_code": "dead_page"}]
    with pytest.raises(brightdata.BrightDataError, match="dead_page"):
        run(lambda req: httpx.Response(200, json=dead))
    assert brightdata.comments_available(keys)

    # no dataset access: labelled, and only the comments breaker trips (SERP / Unlocker stay on)
    with pytest.raises(brightdata.BrightDataError, match="HTTP 403"):
        run(lambda req: httpx.Response(403, text="dataset not enabled for this account"))
    assert not brightdata.comments_available(keys)
    assert brightdata.available(keys)
    assert search_mod._short_err(brightdata.BrightDataError("Bright Data comments -> HTTP 403: dataset not enabled")).startswith("Bright Data HTTP 403")


def test_brightdata_serp_resolves_goto_and_keeps_videos():
    serp = {"organic": [{"link": "https://www.sitepoint.com/git-interactive-rebase-guide/", "title": "A Guide", "description": "d"},
                        {"link": "https://www.google.com/goto?url=CAES123&gsessionid=x", "title": "Git Tools", "description": ""}],
            "videos": [{"link": "https://www.youtube.com/watch?v=H7RFt0Pxxp8", "title": "Git Rebase --interactive: EXPLAINED",
                        "duration_sec": 294, "source": "YouTube · DevOps Toolbox"}]}

    def handler(req):
        if req.url.host == "api.brightdata.com":
            return httpx.Response(200, json=serp, headers={"x-brd-status-code": "200"})
        if "/goto" in req.url.path:
            return httpx.Response(302, headers={"location": "https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History"})
        return httpx.Response(404)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await brightdata.google(c, _bd_keys(), "git rebase interactive")

    hits = asyncio.run(go())
    urls = [h["url"] for h in hits]
    assert "https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History" in urls and not any("google.com" in u for u in urls)
    vid = next(h for h in hits if h.get("kind") == "video")
    assert vid["duration_s"] == 294 and vid["channel"] == "DevOps Toolbox"


def test_brightdata_target_failure_is_an_error(monkeypatch):
    monkeypatch.setattr(brightdata, "_off_until", 0.0)

    def handler(req):  # what the SERP API really returns when the target fails: 200, empty body
        return httpx.Response(200, content=b"", headers={"x-brd-status-code": "502", "x-brd-error-code": "captcha",
                                                          "x-brd-error": "redirect location was rejected"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await brightdata.google(c, _bd_keys(), "q")

    with pytest.raises(brightdata.BrightDataError, match="target HTTP 502"):
        asyncio.run(go())


def test_no_code_video_never_leads_a_coding_goal(offline, monkeypatch):
    """Michael's live run: a no-code 'AI agents with Zapier' video was offered for 'build an LLM'."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    vids = youtube.parse_search(YT)
    trap = vids[0]["videoId"]  # pretend the first (most popular) video is the keyword-sharing no-code one

    async def claude_score(key, goal, cands, **kw):
        out = {}
        for c in cands:
            if c["id"] == f"yt-{trap}":
                out[c["id"]] = {"score": 95, "reason": "Shares keywords only, no-code tool", "style": "no-code", "goal_is_coding": True}
            else:
                out[c["id"]] = {"score": 70, "reason": "Implements it in code", "style": "coding", "goal_is_coding": True}
        return out

    async def nothing(*a, **kw):
        raise RuntimeError("off in this test")

    async def no_source(ctx, q, **kw):
        return []

    monkeypatch.setattr(claude, "score", claude_score)
    monkeypatch.setattr(claude, "read", nothing)
    monkeypatch.setattr(sources, "claude_search", no_source)
    rows = asyncio.run(search("build an LLM from scratch", use_cache=False))
    trap_row = next(r for r in rows if r["id"] == f"yt-{trap}")
    assert trap_row["score"] <= 35 and trap_row["style"] == "no-code"
    assert rows[0]["kind"] == "video" and rows[0]["style"] == "coding" and rows[0]["id"] != trap_row["id"]
    assert all("durationLabel" in r for r in rows if r["kind"] == "video")
