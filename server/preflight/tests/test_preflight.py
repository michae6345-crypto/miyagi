"""Preflight tests with fakes: YouTube (oEmbed + watch page) via httpx.MockTransport, a fake Claude
client, a fake requirements(). No network, no keys."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from server.finder.env import Keys
from server.preflight import (
    build_plan,
    cached_skim,
    core,
    meta,
    needs_line,
    parse_chapters,
    parse_watch_page,
    prefetch,
    preflight,
    preflight_card,
)

KEYS = Keys(gemini=None, brightdata=None, anthropic="test", serp_zone="serp", unlocker_zone="unlock", github=None)
KEYS_BD = Keys(gemini=None, brightdata="bd", anthropic="test", serp_zone="serp", unlocker_zone="unlock", github=None)

KARPATHY_DESC = """We build a Generatively Pretrained Transformer (GPT).

Chapters:
00:00:00 intro: ChatGPT, Transformers, nanoGPT, Shakespeare
baseline language modeling, code setup
00:07:52 reading and exploring the data
00:09:28 tokenization, train/val split
00:14:27 data loader: batches of chunks of data
00:22:11 simplest baseline: bigram language model, loss, generation
00:34:53 training the bigram model
01:54:32 conclusions

Corrections:
00:57:00 Oops "tokens from the _future_ cannot communicate", not "past". Sorry! :)
01:20:05 Oops I should be using the head_size for the normalization, not C
"""

NOCODE_DESC = """Want to build AI agents but think you need to code? Wrong.
📂 TIMESTAMPS:

0:00 — Build AI Agents Without Coding
1:09 — How to Build an AI Agent with OpenAI
3:49 — How to Build an AI Agent with Botpress
9:11 — How to Build an AI Agent with Zapier
17:21 — Why Botpress for Production
"""


def watch_html(title: str, channel: str, secs: int, desc: str, chapters: list[tuple[int, str]] | None = None) -> str:
    player = {"videoDetails": {"videoId": "x", "title": title, "lengthSeconds": str(secs), "author": channel,
                               "shortDescription": desc, "keywords": ["pytorch", "gpt"]},
              "microformat": {"playerMicroformatRenderer": {"category": "Education", "ownerChannelName": channel,
                                                            "uploadDate": "2023-01-17T08:33:27-08:00"}}}
    data: dict = {"contents": {}}
    if chapters:
        data["playerOverlays"] = {"markers": [{"chapterRenderer": {"title": {"simpleText": t}, "timeRangeStartMillis": s * 1000}}
                                              for s, t in chapters]}
    return (f"<html><script>var ytInitialPlayerResponse = {json.dumps(player)};</script>"
            f"<script>var ytInitialData = {json.dumps(data)};</script></html>")


VIDEOS = {
    "kCc8FmEb1nY": ("Let's build GPT: from scratch, in code, spelled out.", "Andrej Karpathy", 6980, KARPATHY_DESC),
    "zE2MJ3_muNQ": ("How to Build AI Agent with ChatGPT (Beginner Tutorial)", "AI Master", 1169, NOCODE_DESC),
    "MXId-Ae6k_I": ("How to Build a Todo-List-App with React", "Arpan Neupane", 904, "A beginner React project."),
}


def transport(*, page_status: int = 200, unlocker: bool = False, calls: list | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(req.url))
        if req.url.host == "api.brightdata.com":
            body = json.loads(req.content)
            vid = body["url"].split("v=")[1][:11]
            if not unlocker:
                return httpx.Response(502)
            return httpx.Response(200, text=watch_html(*VIDEOS[vid]), headers={"x-brd-status-code": "200"})
        if req.url.path == "/oembed":
            vid = req.url.params["url"].split("v=")[1][:11]
            if vid not in VIDEOS:
                return httpx.Response(404)
            t, ch, *_ = VIDEOS[vid]
            return httpx.Response(200, json={"title": t, "author_name": ch, "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
        if req.url.path == "/watch":
            vid = req.url.params["v"]
            if page_status != 200:
                return httpx.Response(page_status, text="Too Many Requests")
            return httpx.Response(200, text=watch_html(*VIDEOS[vid]))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class FakeClaude:
    """messages.create(...) -> a structured-output reply; records the prompts."""

    def __init__(self, answer: dict | None = None, delay: float = 0.0, by_title: dict | None = None):
        self.answer, self.delay, self.by_title, self.calls = answer, delay, by_title or {}, []
        self.messages = self

    async def create(self, **kw):
        self.calls.append(kw)
        assert kw["output_config"]["format"]["type"] == "json_schema"
        await asyncio.sleep(self.delay)
        prompt = kw["messages"][0]["content"]
        ans = next((a for t, a in self.by_title.items() if t in prompt), self.answer)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(ans))])


CODING = {"kind": "coding", "kindWhy": "writes and trains a transformer in PyTorch", "topic": "Builds a GPT language model from scratch in PyTorch",
          "goalMatch": {"score": 0.92, "note": "Builds a real GPT from scratch."}, "firstHandsOnChapter": 1, "libraries": ["Python", "PyTorch"]}
NOCODE = {"kind": "no-code", "kindWhy": "configures bots in Zapier and Botpress", "topic": "Configures no-code support agents in Botpress and Zapier",
          "goalMatch": {"score": 0.2, "note": "This video builds no-code support bots, not an LLM."}, "firstHandsOnChapter": 1,
          "libraries": ["Botpress", "Zapier"]}
REACT = {"kind": "coding", "kindWhy": "writes React components", "topic": "Builds a todo app with React hooks",
         "goalMatch": {"score": 0.95, "note": "Exactly a React todo app."}, "firstHandsOnChapter": -1, "libraries": ["React", "Node.js"]}

REQ_CODING = [
    {"tool": "vscode", "label": "Visual Studio Code", "kind": "editor", "needed": True, "installed": True, "ok": True, "version": "1.146",
     "why": "", "install": {"method": "brew_cask", "command": "brew install --cask visual-studio-code", "url": "https://code.visualstudio.com"}},
    {"tool": "python", "label": "Python 3", "kind": "runtime", "needed": True, "installed": True, "ok": True, "version": "3.12",
     "why": "", "install": {"method": "brew", "command": "brew install python@3.12", "url": ""}},
    {"tool": "torch", "label": "PyTorch", "kind": "python_package", "needed": True, "installed": False, "ok": False, "version": "",
     "why": "the model", "install": {"method": "pip", "command": "pip install torch", "url": ""}},
]
REQ_NOCODE = [
    {"tool": "vscode", "label": "Visual Studio Code", "kind": "editor", "needed": False, "installed": True, "ok": True,
     "why": "No editor needed: the work happens in web apps.", "install": {"method": "none", "command": "", "url": ""}},
    {"tool": "botpress", "label": "Botpress", "kind": "web_app", "needed": True, "installed": True, "ok": True,
     "why": "", "install": {"method": "open", "command": "", "url": "https://app.botpress.cloud"}},
]


@pytest.fixture(autouse=True)
def _fresh():
    core.clear_memo()
    yield
    core.clear_memo()


def run(coro):
    return asyncio.run(coro)


async def _pf(vid: str, goal: str, *, claude=None, req=None, timeout=5.0, tr=None, keys=KEYS, **kw):
    async with httpx.AsyncClient(transport=tr or transport()) as http:
        return await preflight(f"https://www.youtube.com/watch?v={vid}", goal, timeout=timeout, keys=keys, http=http,
                               claude_client=claude or FakeClaude(CODING), requirements_fn=req, **kw)


# --------------------------------------------------------------------------- parsing

def test_chapters_from_description_stop_at_corrections():
    chs = parse_chapters(KARPATHY_DESC, 6980)
    assert [c["start"] for c in chs] == [0, 472, 568, 867, 1331, 2093, 6872]
    assert chs[0]["title"].startswith("intro") and chs[-1]["title"] == "conclusions"
    assert chs[0]["end"] == 472 and chs[-1]["end"] == 6980 and [c["index"] for c in chs] == list(range(7))


def test_chapters_dash_format_and_rules():
    chs = parse_chapters(NOCODE_DESC, 1169)
    assert len(chs) == 5 and chs[2] == {"start": 229, "title": "How to Build an AI Agent with Botpress", "end": 551, "index": 2}
    assert parse_chapters("0:00 intro\n5:00 end", 600) == []  # fewer than 3
    assert parse_chapters("1:00 a\n2:00 b\n3:00 c", 600) == []  # YouTube chapters start at 0:00
    assert parse_chapters("no timestamps here", 600) == []


def test_watch_page_prefers_youtube_chapter_list():
    html = watch_html("T", "C", 1000, "0:00 a\n1:00 b\n2:00 c", chapters=[(0, "Intro"), (90, "Setup"), (400, "Train")])
    m = parse_watch_page(html)
    assert m["title"] == "T" and m["channel"] == "C" and m["duration_s"] == 1000 and m["category"] == "Education"
    assert m["chaptersFrom"] == "youtube" and [c["title"] for c in m["chapters"]] == ["Intro", "Setup", "Train"]
    assert m["chapters"][-1]["end"] == 1000 and m["keywords"] == ["pytorch", "gpt"] and m["published"] == "2023-01-17"
    m2 = parse_watch_page(watch_html("T", "C", 1000, "0:00 a\n1:00 b\n2:00 c"))
    assert m2["chaptersFrom"] == "description" and len(m2["chapters"]) == 3


def test_build_plan_mirrors_e2_window_1():
    short = {"duration_s": 904, "chapters": []}
    assert build_plan(short)["strategy"] == "whole" and build_plan(short)["firstChapter"] is None
    assert build_plan({"duration_s": 29 * 60, "chapters": []})["strategy"] == "whole"  # E2: progressive only > 30 min
    m = {"duration_s": 6980, "chapters": parse_chapters(KARPATHY_DESC, 6980)}
    p = build_plan(m, 1)
    assert p["strategy"] == "chapters"
    fc = p["firstChapter"]
    # E2's plan_windows: window 1 = chapters from 0:00 grouped to 3-6 min; a 7:52 intro is a window on its own
    assert (fc["index"], fc["lastIndex"], fc["start"], fc["end"]) == (0, 0, 0, 472)
    assert p["firstHandsOn"] == {"index": 1, "title": "reading and exploring the data", "start": 472}
    assert 30 < p["estSecondsToFirstSteps"] < 50
    short_chapters = {"duration_s": 3600, "chapters": parse_chapters("0:00 a\n1:00 b\n2:30 c\n4:00 d\n20:00 e", 3600)}
    fc = build_plan(short_chapters)["firstChapter"]
    assert (fc["start"], fc["end"], fc["lastIndex"]) == (0, 240, 2)  # grouped until >= 3 min (same as E2 plan_windows)
    nochap = build_plan({"duration_s": 5400, "chapters": []})
    assert nochap["strategy"] == "chapters" and nochap["firstChapter"]["window"] and nochap["firstChapter"]["end"] == 480


def test_needs_line():
    assert needs_line(REQ_CODING) == "Needs: Visual Studio Code ✓ Python 3 ✓ PyTorch ✗"
    assert needs_line(REQ_NOCODE) == "Needs: Botpress (web)"  # the editor isn't needed, so not shown
    assert needs_line([]) == ""


# --------------------------------------------------------------------------- preflight() end to end with fakes

def test_coding_long_video_card():
    claude = FakeClaude(CODING)
    res = run(_pf("kCc8FmEb1nY", "build an LLM", claude=claude, req=lambda g: REQ_CODING))
    assert not res["partial"] and res["missing"] == []
    assert res["kind"] == "coding" and res["durationS"] == 6980 and len(res["chapters"]) == 7
    assert res["buildPlan"]["strategy"] == "chapters" and res["editorNeeded"] is True
    prompt = claude.calls[0]["messages"][0]["content"]
    assert "Learner's goal: build an LLM" in prompt and "1:56:20" in prompt and "1. [7:52] reading and exploring the data" in prompt
    card = preflight_card(res)
    assert card["kind"] == "preflight" and card["title"].startswith("Let's build GPT")
    assert card["actions"] == ["build", "pick_another", "install"]  # torch missing
    assert "Coding · 1:56:20 · 7 chapters · Andrej Karpathy" in card["body"]
    assert "Needs: Visual Studio Code ✓ Python 3 ✓ PyTorch ✗" in card["body"]
    assert "Long video: I'll build 0:00–7:52 first" in card["body"] and "Hands-on starts at 7:52" in card["body"]
    assert "warning" not in card
    assert card["preflight"]["goalMatch"]["score"] == 0.92 and card["items"][2]["install"]["method"] == "pip"


def test_nocode_low_match_warns_and_needs_no_editor():
    res = run(_pf("zE2MJ3_muNQ", "build chat gpt", claude=FakeClaude(NOCODE), req=lambda g: REQ_NOCODE))
    card = preflight_card(res)
    assert res["kind"] == "no-code" and res["editorNeeded"] is False
    assert card["warning"] == "This video builds no-code support bots, not an LLM." and card["recommended"] == "pick_another"
    assert "⚠ This video builds no-code support bots, not an LLM." in card["body"]
    assert "No code editor needed" in card["body"] and card["actions"] == ["build", "pick_another"]
    assert res["buildPlan"]["strategy"] == "whole"  # 19 min: one build


def test_light_graph_for_requirements():
    seen = {}

    def req(graph):
        seen.update(graph)
        return REQ_CODING

    run(_pf("kCc8FmEb1nY", "build an LLM", req=req))
    assert seen["lesson"]["id"] == "preflight-kCc8FmEb1nY"  # never collides with the real lesson's S2 cache
    assert seen["sources"][0]["url"].endswith("kCc8FmEb1nY") and len(seen["steps"]) == 7
    assert "Generatively Pretrained" in seen["steps"][0]["instructions"]


def test_hard_timeout_partial_result():
    t = time.monotonic()
    res = run(_pf("MXId-Ae6k_I", "react todo", claude=FakeClaude(REACT, delay=5), timeout=0.6, late_s=0))
    assert time.monotonic() - t < 1.2
    assert res["partial"] and "claude" in res["missing"] and res["title"].startswith("How to Build a Todo")
    card = preflight_card(res)
    assert card["actions"][:2] == ["build", "pick_another"] and "couldn't check this video in time" in card["body"]
    assert "kind" not in res  # never invented


def test_late_requirements_reach_on_late():
    got = []

    def slow_req(graph):
        time.sleep(0.5)
        return REQ_CODING

    async def go():
        async def on_late(r):
            got.append(r)

        res = await _pf("kCc8FmEb1nY", "build an LLM", req=slow_req, timeout=0.4, on_late=on_late, late_s=3)
        assert res["missing"] == ["requirements"] and "Needs:" not in preflight_card(res)["body"]
        for _ in range(40):
            if got:
                break
            await asyncio.sleep(0.05)
        return res

    run(go())
    assert len(got) == 1 and got[0]["late"] and not got[0]["partial"]
    assert "PyTorch ✗" in preflight_card(got[0])["body"] and "install" in preflight_card(got[0])["actions"]


def test_late_claude_fills_the_card_in():
    got = []

    async def go():
        res = await _pf("zE2MJ3_muNQ", "build chat gpt", claude=FakeClaude(NOCODE, delay=0.5), timeout=0.3,
                        on_late=got.append, late_s=3)
        assert "claude" in res["missing"] and "warning" not in preflight_card(res)
        for _ in range(40):
            if got:
                break
            await asyncio.sleep(0.05)
        again = await preflight("https://youtu.be/zE2MJ3_muNQ", "build chat gpt", keys=KEYS)  # memo now has the full one
        return again

    again = run(go())
    assert len(got) == 1 and got[0]["kind"] == "no-code" and not got[0]["partial"]
    assert preflight_card(got[0])["warning"].startswith("This video builds no-code") and again["cached"]


def test_prefetch_then_pick_hits_memo():
    claude = FakeClaude(by_title={"Karpathy": CODING, "AI Master": NOCODE}, answer=REACT)
    rows = [{"url": "https://www.youtube.com/watch?v=kCc8FmEb1nY"}, {"url": "https://github.com/karpathy/nanoGPT"},
            {"url": "https://www.youtube.com/watch?v=zE2MJ3_muNQ"}]

    async def go():
        async with httpx.AsyncClient(transport=transport()) as http:
            kw = dict(keys=KEYS, http=http, claude_client=claude, requirements_fn=None)  # noqa: C408
            tasks = prefetch(rows, "build an LLM", **kw)
            assert len(tasks) == 2  # only the videos
            res = await preflight(rows[2]["url"], "Build an  LLM", **kw)  # while prefetch runs: shares it
            await asyncio.gather(*tasks)
            again = await preflight(rows[0]["url"], "build an llm", **kw)
            return res, again

    res, again = run(go())
    assert res["kind"] == "no-code" and again["cached"] and again["kind"] == "coding"
    assert len(claude.calls) == 2


def test_bright_data_fallback_when_watch_page_blocked():
    calls: list[str] = []
    res = run(_pf("kCc8FmEb1nY", "build an LLM", tr=transport(page_status=429, unlocker=True, calls=calls), keys=KEYS_BD))
    assert res["durationS"] == 6980 and len(res["chapters"]) == 7
    assert any("api.brightdata.com" in c for c in calls) and "watch page via Bright Data Unlocker" in res["notes"]


def test_blocked_without_bright_data_still_has_oembed():
    res = run(_pf("kCc8FmEb1nY", "build an LLM", tr=transport(page_status=429)))
    assert res["title"].startswith("Let's build GPT") and "durationS" not in res and res["chapters"] == []
    assert any("HTTP 429" in n for n in res["notes"])


def test_no_goal_means_no_score():
    res = run(_pf("MXId-Ae6k_I", "", claude=FakeClaude(REACT)))
    assert res["goalMatch"] == {"score": None, "note": ""} and "warning" not in preflight_card(res)


def test_not_youtube():
    res = run(_pf("nope", "x"))
    assert res["partial"] and "metadata" in res["missing"] and preflight_card(res)["actions"][:2] == ["build", "pick_another"]


def test_cached_skim_from_finder_cache(tmp_path):
    (tmp_path / "q.json").write_text(json.dumps({"query": "build gpt", "results": [
        {"videoId": "kCc8FmEb1nY", "url": "https://www.youtube.com/watch?v=kCc8FmEb1nY", "score": 88,
         "reason": "Live-codes a GPT in PyTorch, 2 h", "scoredBy": "claude+gemini-watch"},
        {"videoId": "zE2MJ3_muNQ", "score": 40, "reason": "title only", "scoredBy": "claude"},
    ]}))
    assert cached_skim("kCc8FmEb1nY", cache_dir=tmp_path) == {"score": 88, "reason": "Live-codes a GPT in PyTorch, 2 h", "query": "build gpt"}
    assert cached_skim("zE2MJ3_muNQ", cache_dir=tmp_path) is None  # not watched: no skim
    row = {"url": "https://www.youtube.com/watch?v=zE2MJ3_muNQ", "score": 30, "reason": "no-code platforms", "scoredBy": "claude+gemini-watch"}
    assert cached_skim("zE2MJ3_muNQ", row, cache_dir=tmp_path)["reason"] == "no-code platforms"


def test_skim_goes_into_the_prompt(tmp_path):
    claude = FakeClaude(NOCODE)
    row = {"url": "https://www.youtube.com/watch?v=zE2MJ3_muNQ", "score": 30, "reason": "Botpress and Zapier screens, no code",
           "scoredBy": "claude+gemini-watch"}
    run(_pf("zE2MJ3_muNQ", "build chat gpt", claude=claude, row=row, cache_dir=tmp_path))
    assert "Skim note" in claude.calls[0]["messages"][0]["content"] and "no code" in claude.calls[0]["messages"][0]["content"]


def test_meta_to_seconds():
    assert meta.to_seconds("1:02:03") == 3723 and meta.to_seconds("7:52") == 472
