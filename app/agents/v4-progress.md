# v4-progress: the Progress page, v4

Branch `michael/v4-progress` (from `michael/app-ui-v4`). Source of truth: Adrian's `docs/ui-next` mock on
`origin/adrian/ui-next` (`progress`, `progress-empty`, after the Nov 24 trim pass) and mockups -21 / -28.

## Status

- `features/progress/v4/Page.tsx`: two columns (main + 300 px rail, one hairline), the rail drops under the main column
  below 860 px. Lede + the one primary (Continue <step>, or Start a lesson) under the shell's title.
  - Main: This week (minutes a day, Mon-Sun, today in ink) + practiced / steps passed / skills mastered; Last 12 weeks
    (minutes a week, "Now" in ink) + practiced in all / steps passed / lessons finished; Tracks table (green mastered
    bar, next skill or "Needs A and B", last practiced); Recently passed (green check, skill tag, lesson).
  - Rail: bon at its level with "Level N, Name" and steps to the next level (bon growth, from `bon.passed` or the local
    growth count), Goal (bar, "8 of 13 skills", "about 3 hours, around Dec 4"), Closest to mastered, Plans, Keep fresh.
  - First run (nothing passed): empty week, "Start with ten minutes" (4 short lessons, `learn` from the catalog goal),
    "Or start a plan" (3 cards), rail: bon as a seed + "Pick a goal". Never rows of zeros: the 12 weeks and the stats
    hide while empty.
- `features/progress/v4/model.ts`: tolerant reader of the UI-V4 additive `progress` fields (below) + chart/number
  helpers. `store.ts`: `useV4`, fed by `progress` (stage-rebased).
- Minutes unknown (engine sends only reps): the charts say "steps a day / a week" instead, the minutes stats drop out.

## How to see it

`npm run dev:web -- --port 5254 --strictPort`, then
- full: `http://localhost:5254/?window=library&page=progress&clean&scenario=dashboard&v4sample&appearance=light`
- first run: `http://localhost:5254/?window=library&page=progress&clean&scenario=settings`
`?v4sample` (stage only) tops the payload up with Adrian's mock numbers until `mock/scenarios/ui-v4.json` lands; once it
does, `?scenario=ui-v4` should work without it.

Shots: `agents/shots/v4-progress-r{2..4}-* (r2 has the mocks)` (ours vs mock, light and dark; `-first-` is the first run; `-r4-*-{1024,1280,1728}`).

## Data read (placeholders until shared/contracts/UI-V4.md lands; rename to the contract's names then)

`activity[].minutes`, `recent[]` (or `passed[]`) `{at, step, skill?, lesson?}`, `totals {minutes, steps, lessons}`,
`bon {passed}`, `goal {title, mastered, total, minutesLeft?, eta?}`, `plans[] {id?, title, done, total}`,
`milestones[] {label, at}` (read, not shown: the trim pass cut them), `skills[].skills[].need` (steps to master).
First-run lessons, plans and goals are local constants from Adrian's catalog (`STARTERS`, `STARTER_PLANS`, `GOAL_PICKS`).

## Remaining differences vs the mock

- Title: the shell's header draws "Progress" (26 px); the mock's 32 px title has the primary on its row and the lede
  6 px under it. Here the lede + primary sit one row under the title (Core request to the shell lane: let a page pass
  `caption` and `right` to PageHeader).
- The rail shows bon (the buddy, growing with passes) instead of the mock's bonsai with "one leaf for each skill".
- Primary is the brand pill (`PrimaryButton`), no ↩ keycap (no `return` kind in `bridge.platform.keys`).
- Milestones are not shown (Adrian's Nov 24 trim pass cut them; the data is read).
- Keep fresh has no "4 min" total, and "All 58" is not a link yet (no full passes list page).
- First-run covers are simple drawings, not Adrian's illustrated covers.

## Core requests

- Shell: PageHeader `caption` / `right` for Progress (see above).
- Contract (UI-V4): the fields above, plus a `return` key kind for keycaps.
