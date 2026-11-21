# dashboard

**Status:** pass 1 done: dashboard as Library's Home and the Progress window body; typecheck green; stage verified · **Priority:** P1 · **Port:** 5303 · **Branch:** `michael/app-dashboard`

## Goal
One calm screen that shows what the learner can do in real software, what to practice next, and a forgiving rhythm.
Every number comes from steps the learner passed with their own work. Research and sources:
`miyagi-v2/DASHBOARD-RESEARCH.md`.

## Owns
- `app/src/renderer/src/features/dashboard/**` (index, types, model, store, stage, parts, Band, Constellation, Rail, Dashboard)
- `app/mock/scenarios/dashboard.json`
- `app/agents/dashboard.md`
- Small edits in other features (listed here so the owners see them):
  - `features/library/store.ts`, `Library.tsx`: a **Home** section (the default view) renders the dashboard; New lesson is a quiet button there so the dashboard keeps one primary.
  - `features/progress/Window.tsx`: the Progress window's body is the dashboard (title bar kept).
  - `features/progress/types.ts`: bug fix, `readProgress` reads the engine's `skills[].skills` and `finishedAt` (it read only `items` and `at`, so every skill row arrived empty and completed dates were blank).

## What it shows
| Part | What | Rules |
|---|---|---|
| Today | A ring toward the daily goal (default 3 reps, 1 to 10 with the stepper) | White fills; closed = green (the day's goal passed). Missing a day changes nothing. |
| This week | Mon to Sun cells, or a 12-week grid ("12 weeks") | Empty well, white active, green ring closed, outline for days to come. |
| Reps | Total and this week | 1 rep per step passed with the learner's own work. Assisted and skipped steps are 0 (engine side). Hints never subtract. |
| Rhythm | Counted weeks, 2 rest-token dots, Pause / Resume | A week counts when its active days reach the weekly goal (default 3). One token per counted week, at most 2, spent on a short week. Pause 1 to 4 weeks: paused weeks count for nothing either way. A break reads "Your rhythm paused at N weeks. Your R reps and S skills are still yours." Never "lost". |
| Skills | One cluster per track | Columns by prerequisite depth (`edges`); track order when there are no edges. Mastered green with a check, practicing white ring, available solid gray outline (every prerequisite mastered), locked dashed gray at 40%. A due review adds a white dot; the node stays green. Edges gray, green when both ends are mastered. `cross` links are a dashed ghost on the left with `note` on hover. Hover: label, state, detail. Click: the skill card. |
| Skill card | Over the constellation's top right | State and track, detail, why it is locked ("Opens after X"), reps / mastered / last practiced, next review, Taught in (Resume / Again via library.start), Learn it in (up-next lessons that unlock it). Esc closes. |
| Review | Due now (white dot) and later | Due = `dueAt <= now` (old shape: the first `due` items). Start review is quiet and disabled until the engine lists `review.start`. |
| Continue | `inProgress`, newest first | Resume = `library.start {libraryId}` (zero model calls), waits for lesson.ready, then closes the window. No libraryId: disabled. |
| Up next | `next` with "Unlocks ..." | Start: `library.start {id}` when cached, else `learn {query: goal, mode: "lesson"}` (same as the completion card), then the window steps aside. |
| Milestones | Footer, quiet text | First step, first skill, first full track, 10 / 50 / 100 / 500 reps, first review passed, 4 / 12 week rhythm; the next one with "N to go". Step, rep and rhythm milestones only when the engine sends `activity`. |

One primary per surface: Resume on the newest saved lesson in progress, else Start on the first up-next lesson. No
leaderboards, no loss copy, no XP boosts, no confetti, no emoji, no pastels (nothing here is an option).

## Data
Reads the `progress` answer through `features/progress/store.ts` (`requestProgress`: capability check, `progress.get`,
the empty-state timeout) and keeps the raw payload itself (`features/dashboard/types.ts`), so it sees fields the
contract type drops. Accepts both wire shapes (engine `skills[].skills` + `finishedAt` epoch s, contract `items` + `at`).
Everything listed under Core requests 2 to 6 is optional: a missing part shows its own empty state.

Computed in the app (`model.ts`, pure): available vs locked, layout, reps totals, ring fill, week strip, 12-week grid,
rhythm and tokens, due flags, milestones, headlines.

Learner choices (daily goal, rhythm pause) are kept on this Mac in `localStorage` (`miyagi.dashboard.prefs`) until
the engine has a settings record (Core request 6); engine `settings` fill in whatever the learner hasn't set.

## Test
`npm run typecheck` green. Stage `npx vite --config vite.web.config.ts --port 5303 --strictPort`:
- `?scenario=dashboard&window=library&size=1440x900&clean`: Home with the full fixture (4 tracks, 20 skills, 11 weeks of activity, 2 reviews due, 2 lessons in progress, 3 up next). The fixture's dates are moved to today in the stage only (`stage.ts`, payload `stageAnchor`), so it looks the same any day.
  - Click a node (e.g. `groupby`): skill card; Esc closes. Hover a node: tooltip.
  - "12 weeks" swaps the strip for the grid. Pause > 1..4 sets a pause; Resume clears it. Goal - / + changes the ring.
  - Resume on the TensorFlow lesson: the mock answers `library.start:dash_mnist` with lesson.ready and the window closes.
- `?scenario=dashboard&window=progress&size=1440x900&clean`: the same dashboard in the Progress window.
- `?scenario=progress&window=library&size=1440x900&clean`: the old contract shape (`items`, `at`, old review items): no edges, no activity, honest empty tiles.
- `?scenario=full&window=library&size=1440x900&clean`: no engine answer, every empty state.
- Brand lint over the package: no hex or rgba, no typed keycaps, no Cursor, no em dashes, no innerHTML, no console.log.

Shots: `miyagi-v2/screens/round2/dashboard-home.jpg`, `dashboard-skill-card.jpg`, `dashboard-12weeks-hover.jpg`,
`dashboard-progress-window.jpg`, `dashboard-empty.jpg`.

Not verified: Electron (`npm run dev`), main's sender / allowlist for `learn` from an app window, a live engine (cost
freeze), the independent reviewer round.

## Core requests
1. **Engine** (`server/sessions/progress.py`, run-live): `tracks()` drops the saved skill maps' `edges`, `cross` and node `detail`. Send them per track: `skills[]: {track, mastered, total, skills[], edges [{from, to}], cross [{track, label, to, note}]}` and `skills[].skills[].detail`. Without edges every not-started skill reads as available and no lines are drawn.
2. **Engine**: per skill `lessons [lessonId]`, `masteredAt`, `lastPracticedAt` (epoch s) and `reps` (passed, unassisted steps behind it). All derivable from history.json and the lesson state.
3. **Engine**: top-level `next [{title, goal, id?, estMinutes?, unlocks [skillId]}]`, `skillMap.next` merged across lessons; `id` when the lesson is cached (library.start, zero model calls).
4. **Engine (new storage)**: `activity [{date "YYYY-MM-DD" local, reps, assisted, hints}]` from an append-only `~/miyagi/state/activity.json` written on every `step.passed` (unassisted = 1 rep) and hint. mastery.json keeps one time per lesson and can't rebuild days. Also persist `assisted_steps` in `STATE_FIELDS` and send `inProgress[].assisted`.
5. **Engine (new storage) + contract**: `review {items [{skillId, label, track, dueAt (epoch s), interval (days), lastResult "passed"|"missed", lastAt}]}` from a `review.json` ladder (3, 7, 21, 60 days after mastery; a pass moves up, a miss goes back to 3 and the node stays green), plus a `review.start {skillId, label}` command (capability, Python mirror, main's outgoing allowlist and `V2_COMMANDS`). Start review stays disabled until it is listed.
6. **Engine + contract**: a learner `settings {dailyGoal, weeklyGoal, pausedFrom, pausedUntil}` record and a `settings.set` command, so goals and pauses follow the learner instead of living in this window's localStorage. Until then the app keeps them locally (see Data).
7. **Contract** (Michael): add the fields above to `Progress` in `shared/contracts/events.ts` (all optional), and fix `skills[].items` → `skills[].skills` and `completed[].at` → `finishedAt` to match the engine (the app now reads both).
8. **Entry point** (other lane): the Dock click and the tray call `openLibrary()` with no id; Home is the default section, so they land on the dashboard. Nothing more is needed from this lane.

## Notes
- `stageRebase` only runs in the inline stage and only for a payload carrying `stageAnchor`.
- The 12-week grid's rest-token tooltip marks weeks a token covered.
- Old contract `week {days, minutes, streak}` is not drawn: it is a day streak (loss-framed) and the engine never sends it.
