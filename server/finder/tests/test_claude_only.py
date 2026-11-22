"""D1 (Claude only): the finder's default path never calls Gemini. Claude scores from the title and description, then
takes a second look at the top videos from their own text (full description, chapter titles, transcript excerpt),
which replaced the Gemini skim. Replayed offline: the recorded search fixtures of test_finder.py plus hand-written
watch pages and caption tracks (fixtures/video_text.json)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from server.finder import claude, core as search_mod, gemini, sources, youtube
from server.finder import search
from server.finder.tests.test_finder import _check_rows, _transport, offline  # noqa: F401  (fixture)

FX = Path(__file__).parent / "fixtures"
VT = {k: v for k, v in json.loads((FX / "video_text.json").read_text(encoding="utf-8")).items() if k != "note"}
GOAL = "train a PINN on the convection equation"


def _watch_page(vid: str) -> str:
    v = VT[vid]
    player = {"videoDetails": {"videoId": vid, "shortDescription": v["description"], "lengthSeconds": "1360"},
              "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": [
                  {"baseUrl": f"https://www.youtube.com/api/timedtext?v={vid}&lang=en", "languageCode": "en", "kind": "asr"}]}}}
    return f"<html><script>var ytInitialPlayerResponse = {json.dumps(player)};</script></html>"


def _with_video_pages(base: httpx.MockTransport, calls: list[str]) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "www.youtube.com" and req.url.path == "/watch" and req.url.params.get("v") in VT:
            calls.append(str(req.url))
            return httpx.Response(200, text=_watch_page(req.url.params["v"]))
        if req.url.host == "www.youtube.com" and req.url.path == "/api/timedtext" and req.url.params.get("v") in VT:
            calls.append(str(req.url))
            return httpx.Response(200, json={"events": VT[req.url.params["v"]]["events"]})
        return base.handler(req)

    return httpx.MockTransport(handler)


def test_transcript_excerpt_keeps_opening_and_samples():
    lines = [{"t": float(i * 10), "text": f"line {i} " + "x" * 40} for i in range(300)]
    ex = sources.transcript_excerpt(lines, limit=2400)
    assert len(ex) <= 2600 and ex.startswith("[0:00] line 0")
    assert "…" in ex and "line 299" not in ex.split("…")[0]  # the opening, then windows through the rest
    assert any(f"line {i} " in ex for i in range(200, 300))  # the end of the video is sampled too
    assert sources.transcript_excerpt([]) == ""


def test_default_path_claude_reads_top_videos_never_gemini(offline, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(search_mod, "HTTP_TRANSPORT", _with_video_pages(_transport(offline), calls))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")  # a key is there, and still nothing goes to Gemini
    monkeypatch.setenv("FINDER_KINDS", "video")
    second_look: list[dict] = []

    async def claude_score(key, goal, cands, **kw):
        out = {}
        for c in cands:
            item = claude.score_item(c)
            if "transcript_excerpt" in item:  # the second look: judge from what the video says it does
                second_look.append(item)
                coding = "class PINN" in item["transcript_excerpt"] and "convection" in item["transcript_excerpt"]
                out[c["id"]] = {"score": 95 if coding else 25, "style": "coding" if coding else "conceptual",
                                "reason": "Codes a convection PINN in PyTorch" if coding else "Slides only, no code",
                                "goal_is_coding": True}
            else:  # titles alone: the generic PINN intro looks best
                t = c["title"].lower()
                s = 88 if "(pinns)" in t else 80 if "convection" in t and "pinn" in t else 45
                out[c["id"]] = {"score": s, "style": "coding", "reason": "Matches the title", "goal_is_coding": True}
        return out

    async def never(*a, **kw):
        raise AssertionError("Gemini was called on the default path")

    async def no_claude_search(ctx, q, **kw):
        return []

    monkeypatch.setattr(claude, "score", claude_score)
    monkeypatch.setattr(gemini, "skim", never)
    monkeypatch.setattr(gemini, "score", never)
    monkeypatch.setattr(gemini, "_json", never)
    monkeypatch.setattr(sources, "claude_search", no_claude_search)

    rows = asyncio.run(search(GOAL, use_cache=False))
    _check_rows(rows)
    by_id = {r["id"]: r for r in rows}

    # Claude saw the video's own words: full description, chapter titles and a transcript excerpt
    seen = {i["id"]: i for i in second_look}
    assert {"yt-unBU1PwCnvQ", "yt--zrY7P2dVC4"} <= set(seen)
    s5 = seen["yt-unBU1PwCnvQ"]
    assert s5["chapters"][:2] == ["Introduction", "Define the network in PyTorch"]
    assert "[1:35] class PINN(nn.Module)" in s5["transcript_excerpt"]
    assert "linear convection equation with a physics-informed" in s5["description"]
    assert any("/api/timedtext" in u for u in calls) and all(httpx.URL(u).host == "www.youtube.com" for u in calls)

    # results quality: the hands-on convection PINN leads, the slide talk that won on its title drops below it
    top = rows[0]
    assert top["id"] == "yt-unBU1PwCnvQ" and top["kind"] == "video"
    assert top["watched"] == "read by Claude (transcript)" and top["scoredBy"] == "claude+claude-transcript"
    assert top["reason"] == "Codes a convection PINN in PyTorch"
    intro = by_id["yt--zrY7P2dVC4"]
    assert intro["style"] == "conceptual" and intro["score"] < top["score"] and intro["score"] <= 60
    assert all("gemini" not in (r.get("scoredBy") or "") for r in rows)
    assert not any(str(r.get("watched", "")).startswith("watched by Gemini") for r in rows)


def test_second_look_off_and_without_key(offline, monkeypatch):
    """FINDER_VIDEO_READS=0, or no Anthropic key: no watch-page fetch, the first scores stand, no labels."""
    calls: list[str] = []
    monkeypatch.setattr(search_mod, "HTTP_TRANSPORT", _with_video_pages(_transport(offline), calls))
    monkeypatch.setenv("FINDER_KINDS", "video")
    monkeypatch.setenv("FINDER_VIDEO_READS", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")

    async def claude_score(key, goal, cands, **kw):
        assert all("transcript_excerpt" not in claude.score_item(c) for c in cands)
        return {c["id"]: {"score": 70, "style": "coding", "reason": "Fits", "goal_is_coding": True} for c in cands}

    async def no_claude_search(ctx, q, **kw):
        return []

    monkeypatch.setattr(claude, "score", claude_score)
    monkeypatch.setattr(sources, "claude_search", no_claude_search)
    rows = asyncio.run(search(GOAL, use_cache=False))
    assert rows and calls == [] and not any(r.get("watched") for r in rows)


def test_finder_default_imports_no_gemini_sdk():
    """The finder's default modules import without google-genai (gemini.py loads it on its first real call)."""
    import subprocess
    import sys

    code = ("import sys; import server.finder.core, server.finder.scoring, server.finder.claude; "
            "bad = sorted(m for m in sys.modules if m.startswith('google.genai')); print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                       cwd=str(Path(__file__).resolve().parents[3]))
    assert r.returncode == 0, r.stdout + r.stderr
    assert youtube.video_id("https://www.youtube.com/watch?v=unBU1PwCnvQ") == "unBU1PwCnvQ"
