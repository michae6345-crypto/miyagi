# miyagi UI next: pages, lesson plans, Blender and CAD

Mockups and content from Nov 22 to 24 2026. No app code. The app pages and the engine are built from these in their own lanes.

## What is here

| Folder | What |
|---|---|
| `mock/` | The mock, plain HTML. Open `mock/index.html?s=<screen>&t=light` (or `t=dark`). |
| `shots/` | Every screen listed below at 2880 px wide, light and dark. |
| `catalog/` | The lesson plans: 40 plans, 382 lessons, 372 skills. |
| `INTEGRATIONS.md` | How Blender and CAD work should be checked, and the contract ask. |
| `tools/render.mjs` | Renders screens to PNG with headless Chrome. |
| `apps/` | The apps list for Home (MIC-87): the note and its render script. |

## Screens

The live pages, redone on Nov 23 to use the whole window (`mock/v4.js`, `mock/v4.css`):

- `home`, `progress`, `library`, `settings`, `settings-apps`, `settings-data`, `plans`
- for a new learner: `home-empty`, `library-empty`, `progress-empty`
- behind those: `plan` (a preset plan), `course` (a playlist as a plan), `lesson`, `lesson-blender`
- setup: `onboard-1`, `onboard-2`, `onboard-3`

From Nov 22, unchanged: `plan-playlist`, `plan-goal`, `skills-cad`. The two plan dialogs now sit on the wider catalog.

The earlier version of each live page still loads with `-v3` on its name: `home-v3`, `progress-v3`, `library-v3`, `settings-v3`, `plans-v3`, `plan-v3`, `course-v3`, `lesson-v3`, `onboard-1-v3` and so on.

The skill tree screens still load from the same file: `skills-path`, `skills-map`, `skills-tracks`, `skills-steps`, `skills-proof`, `skills-share`, `skills-empty`, and `home-link`.

The rules behind the pages:

- Content is 1040 px wide. Home and Progress are two columns: a 684 px main column and a 316 px rail, with one hairline between them. Settings is two columns of groups. Library and Plans use the full width.
- A plan, a playlist and a lesson are a full-width table with two blocks side by side under it. A setup step keeps its one button on the left and has a quiet rail on the right.
- Numbers sit on one line with hairlines between them. No stat tiles and no dot grids. Charts are plain bars.
- A page is full of things to open or read, and nothing else. A fact is on a page once: no sentence that repeats the numbers beside it, and no text that explains what the page is for.
- No stats made for show: no milestones, no "days of 7", no streaks. A static list such as keyboard shortcuts does not go on a working page.
- A setting with one option is left out until it has two.
- Lists are rows or tables with a hairline between rows. The only card is Continue.
- One sidebar on screen. Settings swaps the app sidebar for its own list.
- A page for a new learner shows things to start: plans, short lessons, goals. It never shows rows of zeros.
- Green only for passed. Pastels only on option chips.
- The learner in the mock is sample data. The week and 12-week numbers and the cache size are made up.
- The copy on Settings, Your data is placeholder text. It has to match what the engine does before it ships.

To render a screen:

```
node tools/render.mjs <out dir> 1440 900 2 "home-light=file:///<path>/mock/index.html?s=home&t=light"
```

For a page taller than the window, add `&h=<height>` to the URL and pass the same height in place of 900. The heights used for the shots: `home` 1102, `progress` 1467, `library` 1436, `settings` 973, `plans` 2505, `home-empty` 958, `library-empty` 1137, `plan` 1223, `course` 1081, `lesson` 1072, `lesson-blender` 959.

## The trim pass, Nov 24

One pass over the live pages to cut filler. The lesson pages did not change.

| Page | Cut | Added |
|---|---|---|
| `home` | The line under the greeting, the three plans to start, the keys list, "days of 7". | "skills mastered" in the week's numbers. |
| `progress` | Milestones, the finished lessons table, "days of 7", "weeks of 12". The top line is now only the skills count. | The hours left sit on the goal. |
| `library` | The sentence of counts. The tabs carry them. | |
| `plans` | The "Starts with" column and the counts in the top line. | "After": the plan to finish first, from each plan's `needs`. |
| `plan`, `course` | One note under the project, the "Added" date, the repeated video count. | |
| `settings` | Language, which has one option. | |
| `settings-apps` | "miyagi looks at the window" on the six screen-only rows. | |
| `settings-data` | "Export my progress". Download covers it. | |
| `home-empty` | The keys list. | |
| `progress-empty` | "What fills this page". | Four short lessons and three plans to start. |
| `onboard-1`, `onboard-2` | The setup list that repeated the three steps at the foot, and one line of fine print. | |

## The apps list, Nov 24 (MIC-87)

Which apps miyagi teaches in, shown on Home. The note is `apps/NOTE.md`. The screens are in `mock/apps.js` and `mock/apps.css`, loaded last. They add screens and change none.

| Screen | What it shows |
|---|---|
| `apps-home-first` | New learner, 4 apps: "Start here" is the "Learn in" table |
| `apps-home-first-10` | The same with 10 apps, the "In your browser" state and the Soon line |
| `apps-home-first-none` | None of the four installed |
| `apps-home`, `apps-home-10` | Returning learner: the block at the foot of the rail |
| `apps-app-blender`, `apps-app-fusion`, `apps-app-vscode` | The page behind a row: installed, not installed, an app with 14 plans |
| `apps-b-home-first`, `apps-b-home`, `apps-b-home-first-10`, `apps-b-home-10` | The option not picked: one line of names under the ask field |

The renders are in `shots/apps/`, light and dark. `node apps/shoot.mjs [screen ...]` renders them again and holds each height.

No third-party logo is drawn: every app is a name. The note says why.

## The catalog

- `catalog/plans/<id>.json`: one plan per file. `catalog/SCHEMA.md` is the format.
- `node catalog/build.mjs --check` checks every rule. `node catalog/build.mjs` also writes `catalog.json`, `catalog.js` (read by the mock) and `CATALOG.md` (the readable version).
- A lesson's `goal` is the text to build it from: `learn {query: goal, mode: "lesson"}`.
- A lesson's `passes` is one sentence a machine could verify.
- Skill ids are stable (`py.loops`, `bl.modifiers`) and each skill lists what it needs, so a plan's skills are a graph the skill tree can draw. Names are at most 18 characters.
- `catalog/playlists.json`: 50 YouTube playlists, two for each of 25 plans. Every id, title, channel and length was fetched from the playlist page on Nov 22 2026 and matched against YouTube's oembed answer.

Three plans were written by hand as the pattern (Intro to Python, Intro to Blender, Intro to CAD). The other 37 were drafted by Claude agents and spot-read. None has been walked through in the app yet.
