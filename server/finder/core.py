"""finder.search: real tutorial search, streamed.

    results = await search("train a PINN on the convection equation", on_result, api_keys)

Who does what (Michael's rule): Claude searches, scores and reads; Gemini only watches videos.

Pipeline (target: first result ~4 s, done < 20 s):
  1. at t=0, in parallel: Claude + its web search tool (plans and runs 2-3 searches), the
     YouTube results page, web search (Bright Data SERP -> Google, else DuckDuckGo) for a
     tutorial and a notebook, GitHub repos, arXiv papers
  2. every candidate is verified (oEmbed for videos, an HTTP request for the rest) and
     scored by Claude for the learner's goal (Gemini only if Claude fails); rows stream
     through on_result as they land
  3. Gemini skims the top videos at low fps (+ Bright Data comments when configured);
     Claude reads the top non-video pages (teaches the goal? prerequisites? code?)
  4. the ranked list is returned (best video first, since build_lesson needs a video) and
     cached in demo/cache/search/.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
import time
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from . import brightdata, cache, claude, env, gemini, sources, youtube
from .env import Keys, resolve_keys
from .verify import verify

log = logging.getLogger("finder")

OnResult = Callable[[dict], Awaitable[None]]

SOURCES_BUDGET_S = 12.0   # stop waiting for slow sources
DEADLINE_S = 19.0         # everything (skim + calibration) must be done by then
CACHE_TTL_S = float(os.environ.get("FINDER_CACHE_TTL", 7 * 24 * 3600))
# tests swap in an httpx.MockTransport that replays recorded real responses
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None

PUBLIC_FIELDS = (
    "id", "kind", "title", "meta", "score", "reason", "thumbnail", "url",
    "source", "videoId", "durationS", "channel", "verified", "warnings",
    "scoredBy", "watched", "prerequisites", "codeNotes", "comments",
    "style", "durationLabel", "long", "chapters", "captions",
)


async def search(
    query: str,
    on_result: OnResult | None = None,
    api_keys: dict | None = None,
    *,
    use_cache: bool = True,
    refresh: bool = False,
    skim_top: int | None = None,
    emit_updates: bool = False,
) -> list[dict]:
    """Stream `search.result` payloads (+ "url") through on_result as they are found,
    return the final ranked list. Every URL is real and was checked to resolve.

    emit_updates: also call on_result again (same id) when the deep pass changes a
    row's score/reason (only if the UI upserts rows by id).
    """
    query = " ".join((query or "").split())
    if not query:
        return []
    if use_cache and not refresh and os.environ.get("FINDER_CACHE", "1") != "0":
        hit = cache.load(query, max_age_s=CACHE_TTL_S)
        if hit:
            log.info("cache hit for %r (%d results)", query, len(hit["results"]))
            for r in hit["results"]:
                await _safe(on_result, r)
            return hit["results"]

    run = _Run(query, resolve_keys(api_keys), on_result, skim_top=env.skim_top() if skim_top is None else skim_top,
               emit_updates=emit_updates)
    results = await run.go()
    if results and os.environ.get("FINDER_CACHE", "1") != "0":
        cache.save(query, results, run.info())
    return results


async def _safe(cb: OnResult | None, payload: dict) -> None:
    if cb is None:
        return
    try:
        await cb(payload)
    except Exception:
        log.exception("on_result callback failed")


# --------------------------------------------------------------------------- helpers

def url_key(url: str) -> str:
    vid = youtube.video_id(url)
    if vid and ("youtu" in url):
        return f"yt:{vid}"
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$", url)
    if m:
        return f"arxiv:{m.group(1)}"
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/').lower()}"


def make_id(c: dict) -> str:
    if c["kind"] == "video" and c.get("videoId"):
        return f"yt-{c['videoId']}"
    k = url_key(c["url"])
    if k.startswith("arxiv:"):
        return "arxiv-" + k[6:].replace("/", "-")
    p = urlparse(c["url"])
    parts = [x for x in p.path.split("/") if x]
    if p.netloc.endswith("github.com") and len(parts) == 2:
        return f"gh-{parts[0]}-{parts[1]}".lower()
    return "web-" + hashlib.sha1(k.encode()).hexdigest()[:10]


def normalize_arxiv(c: dict) -> dict:
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$", c["url"])
    if m:
        return {**c, "url": f"https://arxiv.org/abs/{m.group(1)}", "kind": "paper"}
    return c


def make_meta(c: dict) -> str:
    kind = c["kind"]
    host = urlparse(c["url"]).netloc.removeprefix("www.")
    if kind == "video":
        bits = ["YouTube", c.get("channel"), youtube.fmt_duration(c.get("duration_s")),
                f"chapters: {c['chapters']}" if c.get("chapters") else None, "CC" if c.get("captions") else None,
                c.get("views"), c.get("published")]
    elif c.get("via") == "github":
        stars = c.get("stars")
        bits = ["GitHub", f"★ {youtube.human_count(stars)}" if stars is not None else None, c.get("language"),
                f"updated {c['updated'][:4]}" if c.get("updated") else None]
    elif kind == "paper" and c.get("via") == "arxiv":
        authors = c.get("authors") or []
        who = f"{authors[0].split()[-1]} et al." if len(authors) > 1 else (authors[0] if authors else None)
        bits = ["arXiv", c.get("year"), who]
    elif kind == "notebook":
        bits = ["Colab notebook" if "colab" in host else "Notebook", host]
    elif kind == "repo":
        bits = ["Repo", host + urlparse(c["url"]).path]
    elif kind == "paper":
        bits = ["Paper", host]
    else:
        bits = ["Blog", host]
    return " · ".join(b for b in bits if b)


_STOP = gemini.STOP | {"equation", "using", "with"}


def heuristic_score(goal: str, c: dict) -> tuple[int, str]:
    """Used only when Gemini is unavailable: keyword overlap + popularity, labelled as such."""
    words = {w for w in re.findall(r"[a-z0-9\-+]+", goal.lower()) if w not in _STOP and len(w) > 1}
    text = f"{c.get('title', '')} {c.get('description', '')}".lower()
    hits = sorted(w for w in words if w in text)
    s = 70 * len(hits) / max(1, len(words))
    s += {"video": 10, "notebook": 8, "blog": 6, "repo": 5, "paper": 0}.get(c["kind"], 0)
    if c.get("stars"):
        s += min(10, 2 * math.log10(1 + c["stars"]))
    reason = ("Matches " + ", ".join(hits[:3])) if hits else "Weak keyword match"
    if c.get("duration_s"):
        reason += f", {round(c['duration_s'] / 60)} min"
    return gemini.clamp(round(s)), reason


def _short_err(e: BaseException) -> str:
    msg = str(e)
    if isinstance(e, asyncio.TimeoutError) or "timed out" in msg.lower() or "ReadTimeout" in type(e).__name__:
        return "Bright Data timeout"
    m = re.search(r"Bright Data comments(?: -> HTTP (\d+))?: ?(.*)", msg)
    return (f"Bright Data HTTP {m.group(1)}: " if m and m.group(1) else "Bright Data: ") + (m.group(2) if m else msg)[:70]


def video_fields(c: dict) -> None:
    """durationLabel ('1 h 56 min · 30 chapters') and the long flag for video rows. 'long' uses the
    lesson builder's own threshold (LESSON_LONG_VIDEO_S, 30 min), above which it builds progressively,
    so the result list and the build agree."""
    if c["kind"] != "video" or not c.get("duration_s"):
        return
    label = youtube.duration_label(c["duration_s"])
    c["long"] = c["duration_s"] > env.long_video_s()
    if c["long"]:
        ch = c.get("chapters") or 0
        label += f" · {ch} chapters, builds chapter by chapter" if ch >= 5 else " · no chapters, builds part by part"
    c["durationLabel"] = label


def public(c: dict) -> dict:
    c["scoredBy"] = c.get("scored_by")
    out = {k: c[k] for k in PUBLIC_FIELDS if c.get(k) not in (None, "", [])}
    return out


# --------------------------------------------------------------------------- the run

class _Run:
    def __init__(self, query: str, keys: Keys, on_result: OnResult | None, *, skim_top: int, emit_updates: bool,
                 read_top: int = 3):
        self.query = query
        self.keys = keys
        self.on_result = on_result
        self.skim_top = skim_top
        self.read_top = read_top
        self.emit_updates = emit_updates
        self.t0 = time.monotonic()
        self.seen: set[str] = set()
        self.cands: dict[str, dict] = {}
        self.pending: list[dict] = []
        self.inflight: list[dict] = []
        self.pending_evt = asyncio.Event()
        self.sources_done = False
        self.gemini_ok = bool(keys.gemini)  # for the video skim, only when skim_top > 0
        self.gemini_fallback = self.gemini_ok and env.gemini_fallback()  # Gemini scoring if Claude fails (opt-in)
        self.video_top = 3  # top videos that get Bright Data comments
        self.watching = 0   # videos handed to Gemini so far
        self.plan_used: dict = {}
        self.timings: dict[str, float] = {}
        self.ctx: sources.Ctx | None = None
        self.goal_votes: list[bool] = []  # scorer's goal_is_coding per answer
        self.skims: dict[str, asyncio.Task] = {}   # top videos: Gemini watches them
        self.reads: dict[str, asyncio.Task] = {}   # top pages/repos/notebooks: Gemini reads them

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def left(self, margin: float = 0.0) -> float:
        return DEADLINE_S - margin - self.elapsed()

    def info(self) -> dict:
        return {
            "providers": sorted(self.ctx.used) if self.ctx else [],
            "brightdata": "used" if any(u.startswith("brightdata") for u in (self.ctx.used if self.ctx else ())) else
                          ("no key" if not self.keys.has_brightdata else f"failed: {brightdata.last_error}"),
            "plan": self.plan_used,
            "timings": {k: round(v, 2) for k, v in self.timings.items()},
            "notes": (self.ctx.errors if self.ctx else [])[:20],
            **({"claude": self.ctx.extra["claude"]} if self.ctx and "claude" in self.ctx.extra else {}),
        }

    async def go(self) -> list[dict]:
        limits = httpx.Limits(max_connections=40, max_keepalive_connections=20)
        async with httpx.AsyncClient(headers=sources.BROWSER_HEADERS, follow_redirects=True, limits=limits,
                                     cookies={"CONSENT": "YES+1"}, timeout=8,
                                     transport=HTTP_TRANSPORT) as client:
            self.ctx = sources.Ctx(client=client, keys=self.keys)
            worker = asyncio.create_task(self._triage_worker())
            try:
                await asyncio.wait_for(self._gather_sources(), timeout=SOURCES_BUDGET_S)
            except asyncio.TimeoutError:
                self.ctx.note(f"sources budget ({SOURCES_BUDGET_S}s) hit; continuing with what arrived")
            self.sources_done = True
            self.pending_evt.set()
            try:
                await asyncio.wait_for(worker, timeout=max(0.5, self.left(margin=4)))
            except asyncio.TimeoutError:
                self.ctx.note("triage ran long; emitting the rest with keyword scores")
                rest, self.inflight, self.pending = self.inflight + self.pending, [], []
                await self._emit(rest, {})
            self.timings["sources_done"] = self.elapsed()
            await self._deep_pass(client)
            self.timings["done"] = self.elapsed()
        return self._ranked()

    # ---- sources (all start at t=0)

    async def _gather_sources(self) -> None:
        q = self.query
        plan = gemini.heuristic_plan(q)
        self.plan_used = plan
        topic = plan["topic"]
        jobs = {
            "youtube": sources.youtube_search(self.ctx, q),
            "web-tutorial": sources.web_search(self.ctx, plan["web_queries"][0]),
            "web-notebook": sources.web_search(self.ctx, plan["web_queries"][1]),
            "github": sources.github_search(self.ctx, plan["github_query"]),
            "arxiv": sources.arxiv_search(self.ctx, plan["arxiv_terms"]),
        }
        if cache.normalize(topic) != cache.normalize(q):
            jobs["youtube-2"] = sources.youtube_search(self.ctx, f"{topic} tutorial code", limit=6)
        if self.keys.anthropic:  # primary planner + searcher
            jobs["claude"] = sources.claude_search(self.ctx, q, timeout=max(4.0, SOURCES_BUDGET_S - 1.5))
        tasks = [asyncio.create_task(self._source(name, coro)) for name, coro in jobs.items()]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()

    async def _source(self, name: str, coro) -> None:
        try:
            raw = await coro
        except Exception as e:
            self.ctx.note(f"{name} failed: {type(e).__name__}: {str(e)[:120]}")
            self.timings[f"{name}_failed"] = self.elapsed()
            if name == "youtube":
                self.timings["youtube"] = self.elapsed()
            return
        fresh = []
        for c in raw:
            c = normalize_arxiv(c)
            k = url_key(c["url"])
            if k in self.seen:
                continue
            self.seen.add(k)
            fresh.append(c)
        if not fresh:
            return
        checked = await asyncio.gather(*(self._verify(c) for c in fresh))
        ok = []
        for c in checked:
            if not c:
                continue
            c["id"] = make_id(c)
            if c["id"] in self.cands or any(p["id"] == c["id"] for p in self.pending + self.inflight + ok):
                continue
            c["meta"] = make_meta(c)
            c["source"] = c.get("via")
            if c.get("duration_s"):
                c["durationS"] = c["duration_s"]
            ok.append(c)
        log.info("%s: %d raw, %d new, %d verified (%.1fs)", name, len(raw), len(fresh), len(ok), self.elapsed())
        if ok:
            self.pending.extend(ok)
        self.timings[name] = self.elapsed()  # set after verification: the first batch waits for "youtube"
        self.pending_evt.set()

    async def _verify(self, c: dict) -> dict | None:
        try:
            return await asyncio.wait_for(verify(self.ctx.client, self.keys, c), timeout=7)
        except Exception as e:
            log.info("verify %s failed: %s", c.get("url"), e)
            return None

    # ---- triage + streaming

    async def _triage_worker(self) -> None:
        # Lead with videos: the first batch waits for the YouTube results (or 2 s).
        while "youtube" not in self.timings and self.elapsed() < 2.0 and not self.sources_done:
            await asyncio.sleep(0.05)
        while True:
            if self.sources_done and not self.pending:
                return
            await self.pending_evt.wait()
            self.pending_evt.clear()
            if self.cands:  # after the first batch, coalesce sources that land close together
                await asyncio.sleep(0.4)
                self.pending_evt.clear()
            batch, self.pending = self.pending, []
            if batch:
                self.inflight = batch
                await self._score_and_emit(batch)
                self.inflight = []
                self._start_skims()
            elif self.sources_done:
                return

    async def _score_and_emit(self, batch: list[dict]) -> None:
        # the first batch must land fast (first result < 4 s); later ones can take longer
        first = not self.cands
        # first batch: Claude gets 7 s (Gemini races it after 3 s when it can); later batches more
        timeout = 7.0 if first else max(1.5, min(9.0, self.left(margin=5)))
        # small chunks in parallel: Claude answers ~4 items much faster than 8+
        scores = await self._score_chunks(batch, timeout=timeout, hedge_after=2.5, size=4 if first else 6,
                                          race_after=3.0 if first else None)
        await self._emit(batch, scores)

    async def _score_chunks(self, items: list[dict], *, timeout: float, hedge_after: float, size: int = 8,
                            race_after: float | None = None) -> dict[str, dict]:
        """Score in parallel chunks (small prompts answer much faster than one big one).
        Gemini first; a chunk Gemini can't score (429 / overloaded / slow) goes to Claude;
        only if both fail does it get the labelled keyword score."""

        async def by_claude(ch: list[dict]) -> dict[str, dict]:
            r = await claude.score(self.keys.anthropic, self.query, ch, system=gemini.SCORE_SYSTEM,
                                   prompt=gemini.SCORE_PROMPT, timeout=max(1.5, min(timeout, self.left(margin=1.5))))
            self.ctx.used.add("claude-triage")
            return {k: {**v, "reason": gemini.short(v["reason"]), "by": "claude"} for k, v in r.items()}

        async def by_gemini(ch: list[dict]) -> dict[str, dict]:
            r = await gemini.score(self.keys.gemini, self.query, ch, timeout=max(1.5, min(5.0, self.left(margin=1.5))),
                                   hedge_after=hedge_after)
            self.ctx.used.add("gemini-triage-fallback")
            return {k: {**v, "by": "gemini"} for k, v in r.items()}

        async def one(ch: list[dict]) -> dict[str, dict]:
            """Claude scores. Gemini steps in only if Claude fails, or (first batch only, so the first
            rows land fast) if Claude hasn't answered after `race_after` s; first answer wins.
            Keyword scores only if both fail."""
            claude_ok = bool(self.keys.anthropic) and self.left(margin=1.5) > 1.5
            gemini_ok = self.gemini_fallback and self.left(margin=1.5) > 1.5
            tasks: dict[asyncio.Task, str] = {}
            if claude_ok:
                tasks[asyncio.create_task(by_claude(ch))] = "claude"
            elif gemini_ok:
                tasks[asyncio.create_task(by_gemini(ch))] = "gemini"
            gemini_started = not claude_ok
            try:
                while tasks:
                    wait = race_after if (race_after and gemini_ok and not gemini_started) else None
                    done, _ = await asyncio.wait(tasks, timeout=wait, return_when=asyncio.FIRST_COMPLETED)
                    if not done:
                        tasks[asyncio.create_task(by_gemini(ch))] = "gemini"
                        gemini_started = True
                        continue
                    for t in done:
                        who = tasks.pop(t)
                        try:
                            return t.result()
                        except Exception as e:
                            self.ctx.note(f"{who} triage ({len(ch)} items) failed: {type(e).__name__}: {str(e)[:80]}")
                    if gemini_ok and not gemini_started:
                        tasks[asyncio.create_task(by_gemini(ch))] = "gemini"
                        gemini_started = True
            finally:
                for t in tasks:
                    t.cancel()
            return {}

        chunks = [items[i:i + size] for i in range(0, len(items), size)]
        out: dict[str, dict] = {}
        for r in await asyncio.gather(*(one(ch) for ch in chunks)):
            out.update(r)
        return out

    async def _emit(self, batch: list[dict], scores: dict[str, dict]) -> None:
        for c in batch:
            s = scores.get(c["id"])
            if s:
                c["raw"], c["reason"], c["scored_by"] = s["score"], s["reason"] or "Relevant", s.get("by", "gemini")
                if s.get("style"):
                    c["style"] = s["style"]
                self.goal_votes.append(bool(s.get("goal_is_coding")))
            else:
                c["raw"], c["reason"] = heuristic_score(self.query, c)
                c["scored_by"] = "keywords"
            video_fields(c)
            c["score"] = self._adjusted(c)
        for c in sorted(batch, key=lambda c: -c["score"]):
            self.cands[c["id"]] = c
            if "first_result" not in self.timings:
                self.timings["first_result"] = self.elapsed()
            await _safe(self.on_result, public(c))

    @property
    def goal_coding(self) -> bool:
        return bool(self.goal_votes) and sum(self.goal_votes) * 2 >= len(self.goal_votes)

    def _adjusted(self, c: dict) -> int:
        """The model's score, then the ranking rules (deterministic, so the UI can explain them):
        - for a coding goal, a no-code resource is capped at 35 and a conceptual one at 60
          ("build an LLM" is not "use ChatGPT" or "build a Zapier bot");
        - long videos (> LESSON_LONG_VIDEO_S, 30 min) with chapters get +3 (followable), without chapters -5;
          captions +1."""
        s = c.get("raw", 0)
        style = c.get("style")
        if self.goal_coding and style == "no-code":
            s = min(s, 35)
        elif self.goal_coding and style == "conceptual":
            s = min(s, 60)
        if c["kind"] == "video":
            if c.get("long"):
                s += 3 if (c.get("chapters") or 0) >= 5 else -5
            if c.get("captions"):
                s += 1
        return max(0, min(100, s))

    # ---- deep pass: skim the top videos (+ Bright Data comments), calibrate all scores

    def _start_skims(self) -> None:
        """Bright Data reads the top videos' comments (and Gemini skims them when FINDER_SKIM_TOP > 0);
        Claude reads the top pages. All start as soon as rows are scored (alongside the other sources)."""
        if self.left(margin=2) < 3:
            return
        ranked = sorted(self.cands.values(), key=lambda c: -c["score"])
        videos = [c for c in ranked if c["kind"] == "video"]
        pages = [c for c in ranked if c["kind"] != "video"]
        for v in videos[: self.video_top]:
            if v["id"] not in self.skims and len(self.skims) < self.video_top + 1:
                v["_watch"] = self.watching < self.skim_top  # Gemini skim is opt-in (FINDER_SKIM_TOP)
                self.watching += int(v["_watch"])
                self.skims[v["id"]] = asyncio.create_task(self._skim(v))
        for c in pages[: self.read_top]:
            if c["id"] not in self.reads and len(self.reads) < self.read_top + 1:
                self.reads[c["id"]] = asyncio.create_task(self._read(c))

    def _not_watched(self, c: dict, why: str) -> None:
        c["watched"] = f"not {'watched' if c['kind'] == 'video' else 'read'}: {why}"

    async def _read(self, c: dict) -> None:
        """Claude reads the page (fetched via the Bright Data Unlocker when configured, else plain HTTP)."""
        if not self.keys.anthropic:
            return self._not_watched(c, "no Anthropic key")
        url = c["url"]
        nb = re.match(r"https://colab\.research\.google\.com/github/([^/]+/[^/]+)/blob/(.+?\.ipynb)", url)
        if nb:  # Colab is a JS app; read the notebook it opens from GitHub instead
            url = f"https://raw.githubusercontent.com/{nb.group(1)}/{nb.group(2)}"
        try:
            if brightdata.available(self.keys) and not nb:
                html = await brightdata.unlock(self.ctx.client, self.keys, url, timeout=min(8.0, self.left(margin=6)))
                self.ctx.used.add("brightdata-unlocker")
            else:
                r = await self.ctx.client.get(url, timeout=min(6.0, self.left(margin=6)))
                r.raise_for_status()
                html = r.text
        except Exception as e:
            self.ctx.note(f"read {c['id']}: fetch failed: {type(e).__name__}: {str(e)[:80]}")
            return self._not_watched(c, "page fetch failed")
        text = sources.notebook_text(html) if (nb or url.endswith(".ipynb")) else sources.page_text(html)
        if len(text) < 200:
            return self._not_watched(c, "page has no readable text")
        try:
            c["read"] = await claude.read(self.keys.anthropic, self.query, c, text, timeout=max(1.0, self.left(margin=0.7)))
            self.ctx.used.add("claude-read")
        except Exception as e:
            self.ctx.note(f"read {c['id']} failed: {type(e).__name__}: {str(e)[:80]}")
            self._not_watched(c, f"Claude {claude.failure(e)}")

    async def _skim(self, v: dict) -> None:
        """Gemini watches the video while Bright Data pulls its comments (in parallel: the
        comments dataset takes 5-10 s, too slow to wait for before the skim)."""

        async def comments() -> None:
            if not brightdata.comments_available(self.keys):
                if self.keys.has_brightdata:
                    v["comments"] = "comments not read: " + (brightdata.comments_error or brightdata.last_error or "Bright Data unavailable")[:80]
                return
            try:
                recs = await brightdata.youtube_comments(self.ctx.client, self.keys, v["url"], timeout=max(1.0, min(10.0, self.left(margin=1.0))))
                parsed = youtube.parse_comments(recs)
                warns = youtube.warning_comments(parsed)
                self.ctx.used.add("brightdata-comments")
                v["comments"] = f"{len(parsed)} comments read via Bright Data" + (f", {len(warns)} warn of problems" if warns else "")
                if warns:
                    v["warnings"] = warns[:3]
            except Exception as e:
                self.ctx.note(f"comments for {v['videoId']} failed: {type(e).__name__}: {str(e)[:100]}")
                v["comments"] = "comments not read: " + _short_err(e)

        async def watch() -> None:
            if not v.get("_watch"):
                return  # skim off (default): no Gemini call, and no "watched" label on the row
            if not self.gemini_ok:
                return self._not_watched(v, "no Gemini key")
            try:
                v["skim"] = await gemini.skim(self.keys.gemini, self.query, v, [], timeout=max(1.0, self.left(margin=0.7)))
                self.ctx.used.add("gemini-skim")
            except Exception as e:
                self.ctx.note(f"skim {v['videoId']} failed: {type(e).__name__}: {str(e)[:80]}")
                self._not_watched(v, f"Gemini {gemini.failure(e)}")

        await asyncio.gather(comments(), watch())

    async def _deep_pass(self, client: httpx.AsyncClient) -> None:
        if not self.cands:
            return
        before = {k: (c["score"], c["reason"]) for k, c in self.cands.items()}
        cal: dict[str, dict] = {}

        async def calibrate() -> None:
            """Second chance for rows that only got a keyword score (the scorer was slow the first time)."""
            nonlocal cal
            items = [c for c in self.cands.values() if c.get("scored_by") == "keywords"]
            if not (self.gemini_fallback or self.keys.anthropic) or not items or self.left(margin=1) < 1.5:
                return
            cal = await self._score_chunks(items, timeout=self.left(margin=1), hedge_after=2.0)

        self._start_skims()
        deep = {**self.skims, **self.reads}
        await calibrate()
        if deep:
            _, late = await asyncio.wait(deep.values(), timeout=max(0.1, self.left(margin=0.5)))
            for t in late:
                t.cancel()
            for cid, t in deep.items():
                c = self.cands.get(cid)
                if t in late and c is not None and c["kind"] == "video" and not c.get("comments") and self.keys.has_brightdata:
                    c["comments"] = "comments not read: Bright Data timeout"
                if t in late and c is not None and not c.get("watched") and (c["kind"] != "video" or c.get("_watch")):
                    self._not_watched(c, f"{'Gemini' if c['kind'] == 'video' else 'Claude'} ran out of time")
        self.timings["deep"] = self.elapsed()

        for c in self.cands.values():
            base = cal.get(c["id"])
            if base:
                c["raw"], c["reason"], c["scored_by"] = base["score"], base["reason"] or c["reason"], base.get("by", "gemini")
                if base.get("style"):
                    c["style"] = base["style"]
                self.goal_votes.append(bool(base.get("goal_is_coding")))
            c["score"] = c.get("raw", c.get("score", 0))  # merge on the model's own scale; rules re-applied below
            sk = c.get("skim")
            if sk:  # what the video actually shows outweighs its title
                c["score"] = round(0.4 * c["score"] + 0.6 * sk["score"])
                c["reason"] = sk.get("reason") or c["reason"]
                if sk.get("style"):
                    c["style"] = sk["style"]  # Gemini saw the screen: its call wins
                c["scored_by"] = f"{c['scored_by']}+gemini-watch"
                c["watched"] = "watched by Gemini"
            rd = c.get("read")
            if rd:  # what the page actually teaches outweighs its title (read by Claude)
                c["score"] = round(0.4 * c["score"] + 0.6 * rd["score"])
                if not rd.get("teaches_goal"):
                    c["score"] = min(c["score"], 45)
                c["reason"] = rd.get("summary") or c["reason"]
                c["prerequisites"] = rd.get("prerequisites") or []
                c["codeNotes"] = rd.get("code") or ""
                c["scored_by"] = f"{c['scored_by']}+claude-read"
                c["watched"] = "read by Claude"
            c["raw"] = c["score"]
            video_fields(c)
            c["score"] = self._adjusted(c)
            if str(c.get("watched", "")).startswith("not "):
                c["meta"] = f"{c['meta']} · {c['watched']}"
        if self.emit_updates:
            for k, c in self.cands.items():
                if before.get(k) != (c["score"], c["reason"]):
                    await _safe(self.on_result, public(c))

    def _ranked(self) -> list[dict]:
        ranked = sorted(self.cands.values(), key=lambda c: -c["score"])
        vids = [c for c in ranked if c["kind"] == "video"]
        if self.goal_coding:  # coding goal: lead with the best coding video when there is one
            vids = [c for c in vids if c.get("style") == "coding"] + [c for c in vids if c.get("style") != "coding"]
        if vids and ranked[0] is not vids[0]:  # build_lesson needs a video: the best video goes first
            ranked.remove(vids[0])
            ranked.insert(0, vids[0])
        return [public(c) for c in ranked]
