# server/finder: real tutorial search (E7)

`await search(query, on_result=None, api_keys=None) -> list[dict]` finds **real** tutorials for a
learning goal, streams each one as a `search.result` payload as soon as it is verified and scored,
and returns the ranked list. **Nothing is canned:** every row comes from a live search index, and
every URL was checked to resolve before it was emitted.

```python
from server import finder
rows = await finder.search("train a PINN on the convection equation", on_result=emit)  # emit: async (dict) -> None
lesson.build_lesson(rows[0]["url"], goal, workdir)  # rows[0] is always the best *video*
```

Row = `search.result` (+ extra fields, allowed by the contract):
`{id, kind: video|blog|notebook|paper|repo, title, meta, score 0-100, reason (<= 12 words), thumbnail?, url,
source, scoredBy, watched?, style?, durationLabel?, long?, chapters?, captions?, verified, videoId?, durationS?, channel?, prerequisites?, codeNotes?}`.
- `source`: the stage that found the row: `claude`, `youtube`, `duckduckgo`, `github` or `arxiv`.
- `style` (from Claude's scoring; Gemini's skim overrides it for videos it watched): `coding` | `no-code` | `conceptual`. (`kind` stays the contract's resource type.)
- `durationLabel`: e.g. "1 h 56 min · 30 chapters, builds chapter by chapter". `long` is true over `LESSON_LONG_VIDEO_S` (30 min, the same setting server/lesson uses to build progressively); `chapters` and `captions` (CC) come from YouTube's results page and the watch page. `meta` shows "chapters: 30 · CC".
- `scoredBy`: `claude` | `gemini` (only when Claude failed) | `keywords`, plus `+gemini-watch` (video) / `+claude-read` (page).
- `watched`: `watched by Gemini` | `read by Claude` | `not watched: Gemini quota` | `not read: Claude timeout` (or `overloaded`, `page fetch failed`, …). A row that wasn't watched or read says so, in its `meta` too; it is never faked.
Example: `{"id": "yt-unBU1PwCnvQ", "kind": "video", "title": "S5 Solving Linear convection equation using PINNs",
"meta": "YouTube · SimCom · 22:40 · 314 · 1y ago", "score": 86, "reason": "Clear, 22 min, hands-on, uses PyTorch, explains PINNs for convection", "url": "https://www.youtube.com/watch?v=unBU1PwCnvQ", ...}`

## What it returns (default: YouTube videos only)
- **Videos only.** `FINDER_KINDS=video` is the default (Michael: the list is videos; the no-video path is the separate "Build a lesson from the internet" button). So GitHub, arXiv and the blog/notebook web searches **don't run at all**, and Claude doesn't read pages.
  - Claude's web search asks only for YouTube videos (1-2 searches); its non-video hits are dropped.
  - `FINDER_KINDS=all` (or e.g. `video,repo`) brings the other kinds back.
- **Relevance floor.** A row the model scored below `FINDER_MIN_SCORE` (default 40) is never sent. Rows that only got a keyword score (both models failed) are kept and labelled.
  - Rows below the floor are listed in the cache file's `below_floor`.
  - Every row that is sent is in the returned list, so the orchestrator's `search.done.total` (it counts the rows it streamed) stays exact. A row whose score drops after the deep pass stays in the list, ranked lower.

## Who does what (Michael's rule: Gemini only watches YouTube videos; Claude does everything else)
- **Claude searches.**
  - `claude-haiku-5-5` with the server-side `web_search_20250305` tool plans 2-3 searches and returns its picks with a "why".
  - Only URLs that appear in the tool's own result blocks count; a URL Claude writes from memory is dropped.
  - Measured: 5-8 s for 17-26 results. `claude-sonnet-5-5` with `web_search_20260209` took 13.8 s on the same query.
- **Claude scores** every candidate: 0-100 plus a reason, in small parallel chunks.
- **Claude reads** the top 3 non-video results (blogs, notebooks, repos, papers):
  - Pages are fetched with plain HTTP; Colab notebooks are read from their GitHub `.ipynb`.
  - It answers: does the page teach the goal, what are the prerequisites, what code does it give.
  - Its summary becomes the row's `reason`.
- **Gemini is off in the finder by default** (Michael: Gemini only for what the product needs, i.e. the lesson builder). `FINDER_SKIM_TOP=3` (or `FINDER_SKIMS=1`) turns the low-fps skim of the top videos back on, and `FINDER_SKIMS=0` always forces it off; `FINDER_GEMINI_FALLBACK=1` lets Gemini score when Claude fails.
- **The live-web layer is YouTube's own pages, DuckDuckGo's HTML endpoint and plain HTTP.** No third-party scraping service: pages Claude reads are fetched directly, and the web searches go to DuckDuckGo.
- **Fallbacks:**
  - Gemini scores only if Claude fails.
  - Keyword scores only if both fail; those rows are labelled `scoredBy: keywords`.
  - Gemini Google Search grounding was removed: Claude's web search covers it, and the key's grounding quota is 0.

## Pipeline (first result ~3-5 s, done < 20 s)
1. **t = 0, all in parallel:**
   - **Claude + web search** (above).
   - **YouTube:** the real results page for the query and a topic variant.
   - **Web:** a written tutorial and a notebook, via DuckDuckGo's HTML endpoint.
   - **GitHub** repository search (Jupyter-language repos become `notebook`) and the **arXiv** API.
2. **Verify:**
   - Videos: YouTube **oEmbed** must return 200 (public and embeddable). It also supplies the title, channel and thumbnail.
   - Everything else: an HTTP HEAD/GET must resolve (< 400).
   - Bot-blocked pages (401/403/429) are kept only if a search engine returned them (`verified: "indexed"`).
   - GitHub and arXiv rows come straight from their APIs.
3. **Triage:** Claude scores each batch 0-100 for the learner's goal and writes the reason, in parallel chunks (4 for the first batch, 6 after).
   - The first batch waits for the YouTube results so the UI leads with videos.
   - If Claude fails, Gemini scores. If both fail, the row gets a keyword score that says so ("Matches pinn, convection, 22 min").
4. **Deep pass:**
   - The top 3 videos get a **low-fps Gemini skim** of the actual YouTube video (0.05 fps, low media resolution). The final score is 40% text, 60% skim, and the skim writes the reason.
   - The top 3 non-video results get a **Claude read** of the page. The score is 40% text, 60% read, capped at 45 if the page doesn't teach the goal. The read fills `reason`, `prerequisites` and `codeNotes`.
   - Rows that only got a keyword score get a second scoring try.
5. **Rank:** best first, but the best **video** always leads (build_lesson needs a video).
   - **Strict topic match** (Michael's "build chat gpt" run): the rubric says "build an LLM" ≠ using ChatGPT, no-code bots or agents. Keyword-only matches score 0-30, aggregator pages 40 at most, and the reason must say why it matches.
   - **Deterministic rules on top**, for a coding goal (the scorer reports `goal_is_coding`): no-code is capped at 35 and conceptual at 60. Long videos with ≥ 5 chapters get +3, long ones without chapters -5, captions +1. The lead video is the best **coding** video when there is one. The ranked list is cached in `demo/cache/search/<slug>-<hash>.json` (real results; 7-day TTL, `FINDER_CACHE=0` to disable).

## CLI
```bash
python -m server.finder "train a PINN on the convection equation"            # uses the cache if present
python -m server.finder "train a PINN on the convection equation" --refresh  # live search, rewrites the cache
python -m server.finder "..." --no-cache --json -v
```

## Keys and settings
The keys come from the shared `.env` (looked up in `$TUT_ENV`, the repo root, then the main checkout from a worktree). `api_keys` uses the `config.keys` names and wins over the env.

| env | use |
|---|---|
| `ANTHROPIC_API_KEY` | Claude search, scoring and page reads (`server.config.get_key("anthropic")` when that module exists) |
| `FINDER_CLAUDE_MODEL`, `FINDER_CLAUDE_SEARCH_TOOL` | default `claude-haiku-5-5`, `web_search_20250305` |
| `GEMINI_API_KEY` | video skims (and the scoring fallback) |
| `GITHUB_TOKEN` | optional, raises the GitHub search rate limit |
| `FINDER_KINDS` (default `video`; `all`), `FINDER_MIN_SCORE` (default 40) | what to search for, relevance floor |
| `FINDER_SKIM_TOP` (default 0 = no Gemini skim), `FINDER_GEMINI_FALLBACK` (default 0), `FINDER_MODEL` (Gemini scoring fallback), `FINDER_SKIM_MODEL` | comma-separated Gemini fallback chains (default flash-lite only, so server/lesson's `gemini-4-hydrogen` / `gemini-3.8-flash` daily quota is left alone) |

Gemini calls use no SDK retries. Each call has its own timeout and a **hedged** fallback (if model 1 is slow, model 2 starts too), and a model that returns 429 is skipped until its quota resets.

## Tests
`pytest server/finder/tests`: 34 tests, offline in < 1 s. They replay **recorded real responses** (YouTube results page data, oEmbed, DuckDuckGo, GitHub, arXiv) through an `httpx.MockTransport`. They check:
- every emitted URL came from a source response (none invented);
- a 404 is dropped;
- a URL Claude wrote that its search tool never returned is dropped;
- Claude scores and reads while Gemini only skims videos;
- Gemini scores only when Claude fails;
- a no-code video never leads a coding goal (capped at 35);
- with default settings Gemini is never called;
- the default searches videos only (GitHub, arXiv and DuckDuckGo are never called) and rows below the floor are never streamed, while streamed rows == returned rows;
- rows say plainly when they weren't watched ("not watched: Gemini quota") or read ("not read: Claude timeout");
- everything returned was streamed;
- the best video leads;
- the cache round-trips.

Re-record the fixtures with `python -m server.finder.tests.record`.
