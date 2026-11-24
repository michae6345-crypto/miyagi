# v4-progress: the Progress page, v4

Branch `michael/v4-progress` (from `michael/app-ui-v4`). Source of truth: Adrian's `docs/ui-next` mock on
`origin/adrian/ui-next` (`progress`, `progress-empty`, after the Nov 24 trim pass) and mockups -21 / -28.

## Status

- `features/progress/v4/Page.tsx`: two columns (main + 300 px rail, one hairline), the rail drops under the main column
  below 860 px. Lede + the one primary (Continue <step>, or Start a lesson) under the shell's title.
  - Main: This week (the last 7 days of `activity`, today in ink) + practiced / steps passed / skills mastered
    (`activity.week`); Last 12 weeks (Monday-to-Sunday sums of the 84 days, "Now" in ink) + practiced in all / steps
    passed / lessons finished (`activity.totals`); Tracks table (green mastered bar, next skill or "Needs A and B",
    last practiced: the skills' `lastPracticedAt` or the newest `activity.recent` pass of one of its skills); Recently
    passed (green check, skill tag, lesson).
  - Rail: bon at its level with "Level N, Name" and steps to the next level (`bon`, else the local growth count; never
    Seed at 0 once `activity.totals.stepsPassed` > 0), Goal, Closest to mastered, Plans (`plans`), Keep fresh.
  - First run (nothing passed): empty week, "Start with ten minutes" (4 short lessons, `learn` from the catalog goal),
    "Or start a plan" (3 cards), rail: bon as a seed + "Pick a goal". Never rows of zeros: the week waits for
    `activity` (nothing drawn until it lands), the 12 weeks and the stats hide while empty.
- `features/progress/v4/model.ts`: readers for the UI-V4 messages (`readActivity`, `readBon`, `readPlans`), `readV4` for
  what is still only on `progress`, and the chart/number helpers. `store.ts`: `useV4`; `requestV4()` (called when the
  page opens and on reconnect) sends `activity.get {}`, `bon.get {}` and `plans.list {}`, each only when `canSend`.
- `minutesTracked: false`: the charts say "steps a day / a week" instead, the minutes stats drop out.

## How to see it

`npm run dev:web -- --port 5254 --strictPort`, then
- full: `http://localhost:5254/?window=library&page=progress&clean&scenario=ui-v4&appearance=light` (the UI-V4 mock:
  activity, bon at 24 (Sapling; "Can I move on?" passes step 3 and grows it to Budding), plans).
- first run: `http://localhost:5254/?window=library&page=progress&clean&scenario=settings`
`?v4sample` is gone: `?scenario=ui-v4` is the stage check.

Shots: `agents/shots/v4-progress-r6-*` (ui-v4 data: ours light/dark at 1024/1280/1728, `-tall-` and `-bottom-` at
1440x1500; `-r6-mock-*` is Adrian's mock at 1440). Older rounds: r2-r5.

## Data read (shared/contracts/UI-V4.md)

- `activity`: `minutesTracked`, `days[] {date, minutes, steps}`, `week {minutes, stepsPassed, skillsMastered}`,
  `totals {lessonsFinished, stepsPassed, minutes, skillsMastered}`, `recent[] {at (ISO), stepTitle, skills[0],
  lessonTitle}`. Milestones are not read (the trim pass cut them).
- `bon`: `steps`, `level`, `name`, `next {name, left}`. The level drawn comes from `steps` through growth.ts LEVELS (the
  same table as the contract's `BON_LEVELS`).
- `plans`: `items[] {id, title, done, total}`.
- Still placeholders on `progress` (not in the UI-V4 contract): `goal {title, mastered, total, minutesLeft?, eta?}` and
  `review.minutes` (Keep fresh's "4 min"), and `skills[].skills[].need` (steps to master, Closest to mastered). Under
  `?scenario=ui-v4` none of them is sent, so Goal, Closest to mastered and Keep fresh do not show.
- First-run lessons, plans and goals are local constants from Adrian's catalog (`STARTERS`, `STARTER_PLANS`, `GOAL_PICKS`).

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
- Milestones are not shown (Adrian's Nov 24 trim pass cut them).
- This week is the last 7 days (the contract), so it runs Monday to Sunday only on a Sunday (the mock's day).
- Under `?scenario=ui-v4` the passes are dated Nov 22 (the mock's today), so on another day "Recently passed" says
  "Sunday" where the mock says "Today, 4:12 PM"; the charts end on `activity`'s last day, so they match the mock.
- Goal, Closest to mastered and Keep fresh do not show under ui-v4 (no goal, `need` or review in that mock).
- Not done this pass (fix 8): the lede is still ~20 px under the shell's title (mock 6 px); waits on the shell lane's
  PageHeader `caption` / `right`.
- "4 min" over Keep fresh is plain text until the engine lists `review.start`; "All 58" is not a link yet (no full
  passes list page).
- First-run plan cards at 1280: the meta line wraps before "about 2.5 hr" (the cards are 157 px; the mock's are wider).
- First-run covers are simple drawings, not Adrian's illustrated covers.

## Core requests

- Shell: PageHeader `caption` / `right` for Progress (see above).
- Contract (UI-V4): a goal (`{title, mastered, total, minutesLeft, eta}`), the Keep fresh review length
  (`review.minutes`) and steps to master per skill (`need`) are not in UI-V4 yet; plus a `return` key kind for keycaps.
