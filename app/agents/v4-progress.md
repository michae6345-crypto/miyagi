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

## Fix pass (Nov 24, review r5)

- Recently passed: one grid per table (rows `display: contents`), When and Skill `max-content`, Lesson takes the rest
  and wraps to two lines (no more "Move, rotate and ..."); a long step wraps too. Tracks' Next wraps instead of cutting.
- `model.ts` `plain()`: skill, step, lesson, goal and plan names lose markdown backticks ("Training with fit");
  Closest to mastered names wrap to two lines (48 px meter).
- Keep fresh: `freshLabel()` (ago, else `when`, else "due in N days", else "due"), never a blank right side; the header
  shows "N min" when `review.minutes` is known (a link to `review.start` once the engine lists it).
- First run plan cards: "about 2.5 hr" uses non-breaking spaces, so it never splits.
- Title: the primary is portaled into this page's own shell header as its right slot (on the title row, as in the
  mock) and the lede sits at the top of the body, 20 px under the title (the shell header's padding; the mock has 6 px).
- Shots: `agents/shots/v4-progress-r5-*` (ours light/dark, 1024/1280/1728, first run; the mock at 1280).

## Remaining differences vs the mock

- Title: the shell's header draws "Progress" (26 px); the mock's 32 px title has the lede 6 px under it. The primary is
  on the title row through a portal (TitleRight in Page.tsx); drop it once PageHeader takes `caption` / `right` from a
  page (Core request to the shell lane), which also closes the last 14 px.
- The rail shows bon (the buddy, growing with passes) instead of the mock's bonsai with "one leaf for each skill".
- Primary is the brand pill (`PrimaryButton`), no ↩ keycap (no `return` kind in `bridge.platform.keys`).
- Milestones are not shown (Adrian's Nov 24 trim pass cut them; the data is read).
- "4 min" over Keep fresh is plain text until the engine lists `review.start`; "All 58" is not a link yet (no full
  passes list page).
- First-run plan cards at 1280: the meta line wraps before "about 2.5 hr" (the cards are 157 px; the mock's are wider).
- First-run covers are simple drawings, not Adrian's illustrated covers.

## Core requests

- Shell: PageHeader `caption` / `right` for Progress (see above).
- Contract (UI-V4): the fields above, plus a `return` key kind for keycaps.
