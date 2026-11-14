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
source, verified, videoId?, durationS?, channel?, warnings?}`.
Example: `{"id": "yt-unBU1PwCnvQ", "kind": "video", "title": "S5 Solving Linear convection equation using PINNs",
"meta": "YouTube · SimCom · 22:40 · 314 · 1y ago", "score": 86, "reason": "Clear, 22 min, hands-on, uses PyTorch, explains PINNs for convection", "url": "https://www.youtube.com/watch?v=unBU1PwCnvQ", ...}`

## Pipeline (first result ~2-4 s, done < 20 s)
1. **t = 0, all in parallel:**
   - **YouTube:** the real results page for the query and a topic variant. Goes through the Bright Data Web Unlocker when configured, otherwise direct.
   - **Web:** a written tutorial and a notebook, via the **Bright Data SERP API** (Google) when configured, otherwise DuckDuckGo's HTML endpoint.
   - **GitHub** repository search (Jupyter-language repos become `notebook`) and the **arXiv** API.
   - **Gemini + Google Search grounding:** only the cited result URLs are used (redirects resolved, titles read), never model-written URLs.
2. **Verify:**
   - Videos: YouTube **oEmbed** must return 200 (public and embeddable). It also supplies the title, channel and thumbnail.
   - Everything else: an HTTP HEAD/GET must resolve (< 400).
   - Bot-blocked pages (401/403/429) are re-checked through the Unlocker. Without Bright Data they are kept only if a search engine returned them (`verified: "indexed"`).
   - GitHub and arXiv rows come straight from their APIs.
3. **Triage:** Gemini (flash-lite) scores each batch 0-100 for the learner's goal and writes the reason. Batches go out in parallel chunks of 8.
   - The first batch waits for the YouTube results so the UI leads with videos.
   - If Gemini is slow or out of quota, the row gets a keyword score that says so ("Matches pinn, convection, 22 min").
4. **Deep pass:**
   - The top 3 videos get a **low-fps Gemini skim** of the actual YouTube video (0.05 fps, low media resolution, same `file_data` URI as server/lesson). The final score is 40% text, 60% skim, and the skim writes the reason.
   - With Bright Data, the **YouTube comments** are pulled too, and "outdated / doesn't work" comments feed the skim and show up as `warnings`.
   - Rows that only got a keyword score get a second Gemini try.
5. **Rank:** best first, but the best **video** always leads (build_lesson needs a video). The ranked list is cached in `demo/cache/search/<slug>-<hash>.json` (real results; 7-day TTL, `FINDER_CACHE=0` to disable).

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
| `GEMINI_API_KEY` | triage, skim, grounding |
| `BRIGHTDATA_API_KEY`, `BRIGHTDATA_SERP_ZONE` (default `serp_api1`), `BRIGHTDATA_UNLOCKER_ZONE` (default `web_unlocker1`) | SERP + Unlocker; any failure falls back, and an inactive account or missing zone trips a 5-min circuit breaker |
| `BRIGHTDATA_YT_COMMENTS_DATASET` | Web Scraper API dataset id for YouTube comments |
| `GITHUB_TOKEN` | optional, raises the GitHub search rate limit |
| `FINDER_MODEL`, `FINDER_SKIM_MODEL`, `FINDER_GROUNDING_MODEL` | comma-separated Gemini fallback chains (default flash-lite only, so server/lesson's `gemini-4-hydrogen` / `gemini-3.8-flash` daily quota is left alone) |

Gemini calls use no SDK retries. Each call has its own timeout and a **hedged** fallback (if model 1 is slow, model 2 starts too), and a model that returns 429 is skipped until its quota resets.

## Tests
`pytest server/finder/tests`: 13 tests, offline in < 1 s. They replay **recorded real responses** (YouTube results page data, oEmbed, DuckDuckGo, GitHub, arXiv) through an `httpx.MockTransport`. They check:
- every emitted URL came from a source response (none invented);
- a 404 is dropped;
- everything returned was streamed;
- the best video leads;
- the cache round-trips.

Re-record the fixtures with `python -m server.finder.tests.record`.
