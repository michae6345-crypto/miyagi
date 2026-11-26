# server/preflight: look at the picked video before building it (≤ 5 s)

```python
from server.preflight import preflight, preflight_card, prefetch

prefetch(rows, query)                         # on search.done: top 3 videos, in the background (memoised 10 min)
res = await preflight(url, goal, row=picked_row, on_late=lambda r: emit("card", preflight_card(r)))
await emit("card", preflight_card(res))       # kind "preflight", actions build / pick_another (+ install)
```

```bash
.venv/bin/python -m server.preflight "https://www.youtube.com/watch?v=kCc8FmEb1nY" --goal "build an LLM" [--json]
.venv/bin/python -m pytest -q server/preflight          # 19 tests, fakes only (no network, no keys)
```

## What it does

1. **Metadata (~1 s):** oEmbed and the watch page in parallel. The watch page is a plain fetch. From these: title, channel, duration, full description, category, tags,
   and chapters (YouTube's own `chapterRenderer` list, else description timestamps; a "Corrections:" tail
   doesn't count).
2. **In parallel:**
   - Claude `claude-haiku-5-5` (`PREFLIGHT_MODEL`), structured output: `style` coding | no-code | conceptual
     (the same vocabulary as E7's finder rows), `topic`, `goalMatch {score 0–1 | null, note}`, the first hands-on chapter, and libraries. It also
     gets the finder's Gemini skim when the picked row or `demo/cache/search/*.json` has one. No new Gemini
     call is made.
   - The picked finder row (E7) is reused rather than re-derived. Its `style` goes into Claude's prompt as a
     prior, and becomes the card's style when Claude is late (`styleFrom: "finder"`). `captions`,
     `durationLabel` and `long` are copied through. `durationS`, title and channel fill in when YouTube
     blocks the watch page. The watch page is still fetched, because the build plan needs the description
     and the chapter *times* (the row only has a chapter count).
   - S2's `server.workspace.requirements()` on a metadata-level step graph (lesson id `preflight-<videoId>`),
     checked locally and read-only. It is skipped with a note if `server.workspace` doesn't export it yet.
   - **Built before?** The same lookup E2's `build_lesson` does: E4's `build_workdir`, then `cache_key`, else
     `find_cached` (same video + same folder layout). On a hit, the card says "Built before: ready instantly
     (N steps)" (`buildPlan.cached`, estimate 0), and the tool check runs on the real cached graph and its
     real folder (e.g. demo/pinn-lab), so it matches the setup card that follows. The check is repeated on
     every memo hit, so a result prefetched before the first build is never stale.
   - **Coding lessons always get the editor.** E2 adapts them to a local folder even when the video uses Colab.
     The metadata-level graph tells S2 this (`LOCAL_NOTE`), and `editorNeeded` is True for `style: coding`.
3. **buildPlan:** `whole` (≤ 30 min) or `chapters`. `firstChapter` is the window E2 builds first (its
   `plan_windows` when importable, else the same rule). `firstHandsOn` is Claude's first hands-on chapter.
   When it starts 1–10 min in, E2 skips the talk-only intro before it (`skippedIntro`), and part 1 starts
   there. A later start isn't trusted, because it would skip real work.
   `video_meta(res)` returns all of this in the shape E2's `build_lesson(..., video_meta=...)` takes (title,
   description, duration_s, chapters, firstHandsOn), so the build skips its own watch-page fetch.
   `estSecondsToFirstSteps` ≈ 30 s + 1.5 s per minute watched.

The deadline is hard (`timeout=5`). A part that misses it is listed in `missing`, keeps running for up to
`late_s=12` s more, and if it lands, `on_late(result)` gets the filled-in result. Re-send the card then: the
second card replaces the first. `preflight()` never raises. Results are memoised per (video, goal) for 10 min.
A pick that arrives while a prefetch for the same video is still running waits for that run instead of
starting another.

## Card

```jsonc
{"kind": "preflight", "title": "<video title>",
 "body": "No-code · 19:29 · 10 chapters · AI Master\n<topic>\n⚠ This video builds no-code support bots, not an LLM.\nBuilding takes ~59 s.\nNo code editor needed for this one.\nNeeds: Botpress (web) Zapier (web)",
 "items": [SetupItem…], "actions": ["build", "pick_another"], "warning": "…", "recommended": "pick_another",
 "preflight": {"videoId", "url", "style", "topic", "durationS", "chapters": 10, "goalMatch": {"score": 0.2, "note"},
               "buildPlan": {"strategy", "firstChapter", "firstHandsOn"?, "skippedIntro"?, "estSecondsToFirstSteps"}, "editorNeeded": false, "partial": false}}
```

`install` is added when a needed tool is missing; it is the same flow as S2's setup card. `warning` and
`recommended` are present only when `goalMatch.score < 0.5`.

## Hook for E4 (`server/orchestrator/session.py`)

Today `build_lesson(result_ids)` / `learn_url(url)` → `_run_build(url, goal)` → `_build` → `m.build_lesson(...)`.
v2 puts preflight in front:

```python
# search(): after `search.done`
from server import preflight as pf
pf.prefetch(list(self.results.values()), self.query)

# build_lesson(result_ids) / learn_url(url): instead of `await self._run_build(url, self.query)`
self.pending_pick = {"url": url, "row": picked[0] if picked else None}
self.phase = "preflight"
res = await pf.preflight(url, self.query, row=self.pending_pick["row"],
                         on_late=lambda r: self._emit_if_pending(url, pf.preflight_card(r)))
self.pending_pick["preflight"] = res
await self.emit("card", pf.preflight_card(res))
await self._status("idle")                     # waiting on the learner

# action(kind):
#   "build"        -> p = self.pending_pick; self.pending_pick = None
#                     await self._run_build(p["url"], self.query, video_meta=pf.video_meta(p["preflight"]))
#                     ... and in _build: m.build_lesson(url, goal, workdir, on_progress=..., video_meta=video_meta)
#                     (E2 1411782: skips its watch-page fetch, starts part 1 at firstHandsOn; S2's setup card is
#                      already warm from preflight's requirements() via #28, keyed by video id)
#   "pick_another" -> self.pending_pick = None; self.phase = "idle"; await self._status("idle")   # the app re-shows its results
#   "install"      -> S2's install flow (text = tool id), same as on the setup card
# _emit_if_pending: emit only while self.pending_pick["url"] == url (a late card must not land after build / pick_another / end_lesson)
# end_lesson(): also clears pending_pick
```
