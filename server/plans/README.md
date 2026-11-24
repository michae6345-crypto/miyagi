# server/plans: lesson plans (ui-v4)

A plan is a set of lessons in order that ends in a project the learner makes alone (Adrian's `docs/ui-next/catalog`).

| File | What |
|---|---|
| `data/catalog.json` | The 40 catalog plans, copied from `adrian/ui-next:docs/ui-next/catalog/catalog.json` (822ee74a). Format: that folder's `SCHEMA.md`. |
| `data/playlists.json` | The 50 checked YouTube playlists (two each for 25 plans), from the same commit. |
| `catalog.py` | Loads both once, drops malformed plans, `summary()` (a Plans row) and `detail()` (the plan page). |
| `progress.py` | Plans in progress: `<state dir>/plans.json` (PlanState). Lessons done, skipped, un-marked, in progress; links plan lessons to engine lessons. |
| `playlist.py` | A playlist's videos: shipped list, then cache (24 h; a copy stamped in the future is stale), then the public playlist page, then the public feed. No paid call. |
| `goal.py` | Goal text to catalog plans: keyword and alias scoring first (free); one Haiku call through `coach.llm` only when nothing matches clearly. |
| `proposal.py` | PlanProposal for a playlist (deterministic) or a goal (catalog lessons, needs first). |
| `service.py` | The ui-v4 contract's plans commands and their replies. |

Everything stays on this Mac except the playlist id (sent to youtube.com) and, only for an unclear goal, the goal text
(sent to the model through the guarded client, fenced as untrusted).

## Messages (shared/contracts/events.py, UI-V4.md section 3)

| App -> Engine | Reply | Notes |
|---|---|---|
| `plans.list {}` | `plans {items: PlanState[], reqId?}` | instant |
| `plan.start {catalogId}` / `{playlistId, url, proposal}` / `{goal, proposal}` | `plans` | the same catalogId or goal answers with the plan already there |
| `plan.remove {id}` | `plans` | |
| `playlist.get {url, reqId}` | `playlist` twice: the videos (`proposing: true`), then `proposal` | `error`: a LookupError_ code |
| `plan.propose {goal, tool?, reqId}` | `plan.proposal` twice: `proposing: true`, then `proposal` | `error: not_found` when no catalog plan fits |
| `learn` / `learn_url` / `library.start` with `plan {id, index}` | `plans` pushed (the lesson is `in_progress`), then the lesson's usual events | linked on `lesson.ready`; `plans` pushed again on `lesson.complete` / `lesson.ended` |

Ids: the catalog id (preset), `pl-<playlistId>` (playlist), `goal-<8 hex>` (goal). Lesson states: done, in_progress,
next, todo, skipped. Times are ISO strings. v1 records (`kind`, `yt-<id>`) are read as v2. A plan.start that cannot add
the plan answers `error {message, reqId}`. The learner's own un-mark (`progress.mark_done(.., False)`) sticks: the
lesson is never re-marked from history until it is opened again.
