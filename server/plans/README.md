# server/plans: lesson plans (ui-v4)

A plan is a set of lessons in order that ends in a project the learner makes alone (Adrian's `docs/ui-next/catalog`).

| File | What |
|---|---|
| `data/catalog.json` | The 40 catalog plans, copied from `adrian/ui-next:docs/ui-next/catalog/catalog.json` (822ee74a). Format: that folder's `SCHEMA.md`. |
| `data/playlists.json` | The 50 checked YouTube playlists (two each for 25 plans), from the same commit. |
| `catalog.py` | Loads both once, drops malformed plans, `summary()` (a Plans row) and `detail()` (the plan page). |
| `progress.py` | Plans in progress: `<state dir>/plans.json`. Lessons done, current, next, resume; links plan lessons to engine lessons. |
| `playlist.py` | A playlist's videos: shipped list, then cache (24 h), then the public playlist page, then the public feed. No paid call. |
| `goal.py` | Goal text to catalog plans: keyword and alias scoring first (free); one Haiku call through `coach.llm` only when nothing matches clearly. |
| `service.py` | The App -> Engine messages and their replies. |

Everything stays on this Mac except the playlist id (sent to youtube.com) and, only for an unclear goal, the goal text
(sent to the model through the guarded client, fenced as untrusted).

## Messages

These names are provisional until the ui-v4 contract (`shared/contracts/events.py`) carries them. The parsing is in
`service.parse` (the same fallback `main.parse_command` uses for the v2 commands).

| App -> Engine | Reply | Notes |
|---|---|---|
| `plans.list {}` | `plans {plans: [row + progress?], playlists: [playlist plan rows]}` | instant |
| `plan.get {id}` | `plan {id, kind, plan, progress, playlists}` | `id`: a catalog id or `yt-<playlistId>` |
| `plans.progress.get {}` | `plans.progress {plans: [view], resume: view \| null}` | instant |
| `plan.start {id, goal?}` or `{url}` | `plan.progress view` | adds the plan (or touches it) and makes it active |
| `plan.goal {text}` | `plan.matches {goal, matches: [{planId, title, line, score?, first?}], confident, source}` | `first`: the plan to finish before this one |
| `plan.playlist {url, refresh?}` | `plan.playlist {id, playlistId, title, channel, url, videos, videoCount, totalSeconds, truncated, source}` | a preview; `plan.start {id}` adds it |
| `plan.lesson.done {id, index, done?}` | `plan.progress view` | the learner's own mark |
| `plan.remove {id}` | `plans.progress` | |
| `plan.lesson.start {id, index?}` | `plan.progress view`, then the lesson's usual events | queued like any lesson start; `index` omitted: the next lesson |

A progress view: `{key, kind, title, planId?, playlistId?, channel?, goal?, lessons: [{index, title, minutes, state: done|current|todo, videoId?, seconds?}], done, total, complete, next: {index, title, steps?: {passed, total}} | null, minutesLeft, active, startedAt, lastActiveAt}`.

Failures go out as the existing `error {message}`.
