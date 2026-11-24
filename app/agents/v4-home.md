# v4-home: Home v4 (Adrian's ui-next mock, `home` and `home-empty`)

Branch `michael/v4-home` (from `michael/app-ui-v4`, merged with it after `contract: ui-v4 data`). Stage port: any free one (`npm run dev:web -- --port <port> --strictPort`; the Nov 24 fix pass used 5383).

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

## Wired to the contract (Nov 24)

`shared/contracts/UI-V4.md` is on `michael/app-ui-v4` (4330227c). `home/v4.ts` sends `activity.get` and `plans.list` when
Home opens, each only when `engine.hello.capabilities` lists it (`canSend`), and keeps the `activity` / `plans` answers and
pushes. `home/data.ts fromContract` maps them (`V4Parts`, which replaced the `V4Extra` placeholder):
- the week bars: the last 7 of `activity.days` (minutes, or steps when `minutesTracked` is false); the numbers:
  `activity.week` {minutes, stepsPassed, skillsMastered}, no minutes when `minutesTracked` is false;
- Recently passed: `activity.recent` as step rows (When / Step / Skill) with their first skill label;
- Plans: `plans.items` not done (done of total, Next = the lesson at `nextIndex`); Up next adds each plan's next lesson
  after the saved lessons (opening one puts its goal in the ask field);
- Goal: the project of the plan the learner passed a step in last ("A network that finds a circle", lessons done of
  total, `minutesLeft`). The contract has no learner goal field yet; see Core requests;
- first run's Start here: the catalog's intro-python / intro-blender / intro-cad (`home/catalog.ts`, the catalog's own
  numbers and project), minus plans already added;
- Keep fresh: the progress's review list, else `progress.graph.keepFresh` (read from the skills store).

The Continue cover comes from the lesson's tool (a saved lesson's tools, else its plan's tool: the Blender lesson is the
mug); only the stage's demo sample uses the network drawing.

## How to see it

- `http://localhost:<port>/?window=library&scenario=ui-v4` (the contract's mock: every section)
- `?window=library&scenario=home-dashboard` (progress data from an engine before ui-v4)
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

- A learner goal in the contract (the plan or capstone the learner picked) so Home's Goal is not inferred from the last plan.

- A `KeyName` for Return/Enter so the Continue button can show the mock's ↩ keycap.
