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

1. **Metadata (~1 s):** oEmbed and the watch page in parallel. The watch page is a plain fetch with the
   Bright Data Unlocker as fallback. From these: title, channel, duration, full description, category, tags,
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
3. **buildPlan:** `whole` (≤ 30 min) or `chapters`. `firstChapter` is the window E2 builds first (its
   `plan_windows` when importable, else the same rule). `firstHandsOn` is Claude's hint.
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
               "buildPlan": {"strategy", "firstChapter", "firstHandsOn"?, "estSecondsToFirstSteps"}, "editorNeeded": false, "partial": false}}
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
#   "build"        -> p = self.pending_pick; self.pending_pick = None; await self._run_build(p["url"], self.query)
#                     (hand p["preflight"] to E2 / S2 if they accept it: chapters, duration, style, goalMatch, items)
#   "pick_another" -> self.pending_pick = None; self.phase = "idle"; await self._status("idle")   # the app re-shows its results
#   "install"      -> S2's install flow (text = tool id), same as on the setup card
# _emit_if_pending: emit only while self.pending_pick["url"] == url (a late card must not land after build / pick_another / end_lesson)
# end_lesson(): also clears pending_pick
```
