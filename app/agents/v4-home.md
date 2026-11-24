# v4-home: Home v4 (Adrian's ui-next mock, `home` and `home-empty`)

Branch `michael/v4-home` (from `michael/app-ui-v4`). Stage port 5252.

## Status

Done (first pass, matched to the mock in 3 rounds):
- **Returning learner** (`22-desktop-ui-v4-20-home`): greeting with the learner's first name and the date; the ask field
  ("ask miyagi, or paste a YouTube link", the launcher keycap, three suggestion chips inside the frame); Continue as the
  page's one card (cover, "Step 4 of 7", the lesson, the step, the one primary, a 3 px progress edge); Plans in progress;
  Up next (cover, title, skill tag, tool · steps · minutes); Recently passed (When / Step / Skill, green checks).
  Rail: This week (Monday to Sunday bars, today in ink, practiced / steps passed / skills mastered), Goal, Skills
  (green bars: mastered), Keep fresh.
- **First run** (`22-desktop-ui-v4-26-home-first-run`): Welcome, the lede, the ask, Start here (three plans), Or one short
  lesson, Make your own; rail: Set up (the real onboarding rows), How a lesson works, Pick a goal.
- 1040 px content; the rail drops under the main column below a 960 px pane (1024 windows). No horizontal scroll, no
  clipped text, no console errors at 1024, 1280, 1440 and 1728, light and dark.
- Every section with nothing to show is left out (no rows of zeros).

Files: `features/library/Home.tsx` (Continue logic + which page), `features/library/home/{data,sample,bits,Top,Page}.tsx|ts`,
`home/data.test.ts` (run by `test/v4home.test.ts`).

## Wire later (the contract)

`shared/contracts/UI-V4.md` and `mock/scenarios/ui-v4.json` were not on `michael/app-ui-v4` yet. Until then
`home/data.ts` takes `V4Extra`, a typed placeholder for what the contract adds: activity minutes per day, plans in
progress, step passes with their skill, the goal, and catalog starters/short lessons/goals (first run uses the local
`FIRST_RUN` list from Adrian's catalog). Wired now from existing data: Continue, Up next, skills per track, keep fresh
(review), steps per day, skills mastered this week, recently finished lessons (shown as "Lesson" rows until passes land).

## How to see it

- `http://localhost:5252/?window=library&scenario=home-dashboard` (real mock data)
- `&homeSample=full` the mock's sample learner (browser stage only), `&homeSample=first` the first-run page
- `&appearance=dark|light`

## Intentional differences from the mock

- The pane is the shell's cream canvas (light) and the shell's sidebar/header (shell lane owns the frame); no "Home" crumb.
- Covers are neutral gray drawings (no pastel code lines: pastels stay on options and tags).
- "Continue" has no ↩ keycap (no platform key name for Return; keycaps only come from `bridge.platform.keys`).
- Keep fresh links to Progress instead of "4 min" (no review-time estimate in the data).
- First-run Set up lists the real onboarding rows (Screen Recording, Accessibility, VS Code companion, engine), not "Signed in".
- The date and week are today's (the mock is fixed on Sunday Nov 22).

## Core requests

- A `KeyName` for Return/Enter so the Continue button can show the mock's ↩ keycap.
