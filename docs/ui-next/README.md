# miyagi UI next: pages, lesson plans, Blender and CAD

Mockups and content from Nov 22 and 23 2026. No app code. The app pages and the engine are built from these in their own lanes.

## What is here

| Folder | What |
|---|---|
| `mock/` | The mock, plain HTML. Open `mock/index.html?s=<screen>&t=light` (or `t=dark`). |
| `shots/` | Every screen listed below at 2880 px wide, light and dark. |
| `catalog/` | The lesson plans: 40 plans, 382 lessons, 372 skills. |
| `INTEGRATIONS.md` | How Blender and CAD work should be checked, and the contract ask. |
| `tools/render.mjs` | Renders screens to PNG with headless Chrome. |

## Screens

The live pages, redone on Nov 23 to use the whole window (`mock/v4.js`, `mock/v4.css`):

- `home`, `progress`, `library`, `settings`, `settings-apps`, `settings-data`, `plans`
- for a new learner: `home-empty`, `library-empty`, `progress-empty`

From Nov 22, unchanged: `plan`, `plan-playlist`, `plan-goal`, `lesson-blender`, `skills-cad`. The two plan dialogs now sit on the wider catalog.

The Nov 22 one-column version of each live page still loads with `-v3` on its name: `home-v3`, `progress-v3`, `library-v3`, `settings-v3`, `settings-apps-v3`, `settings-data-v3`, `plans-v3`, `home-empty-v3`, `library-empty-v3`, `progress-empty-v3`.

The earlier screens still load from the same file: `skills-path`, `skills-map`, `skills-tracks`, `skills-steps`, `skills-proof`, `skills-share`, `skills-empty`, `course`, `lesson`, `home-link` and `onboard-1` to `onboard-3`.

The rules behind the pages:

- Content is 1040 px wide. Home and Progress are two columns: a 684 px main column and a 316 px rail, with one hairline between them. Settings is two columns of groups. Library and Plans use the full width.
- Numbers sit on one line with hairlines between them. No stat tiles and no dot grids. Charts are plain bars.
- Lists are rows or tables with a hairline between rows. The only card is Continue.
- One sidebar on screen. Settings swaps the app sidebar for its own list.
- A page for a new learner shows things to start: plans, short lessons, goals. It never shows rows of zeros.
- Green only for passed. Pastels only on option chips.
- The learner in the mock is sample data. The week and 12-week numbers, the milestones and the cache size are made up.
- The copy on Settings, Your data is placeholder text. It has to match what the engine does before it ships.

To render a screen:

```
node tools/render.mjs <out dir> 1440 900 2 "home-light=file:///<path>/mock/index.html?s=home&t=light"
```

For a page taller than the window, add `&h=<height>` to the URL and pass the same height in place of 900. The heights used for the shots: `home` 1356, `progress` 1717, `library` 1460, `settings` 973, `plans` 2505, `home-empty` 958, `library-empty` 1137.

## The catalog

- `catalog/plans/<id>.json`: one plan per file. `catalog/SCHEMA.md` is the format.
- `node catalog/build.mjs --check` checks every rule. `node catalog/build.mjs` also writes `catalog.json`, `catalog.js` (read by the mock) and `CATALOG.md` (the readable version).
- A lesson's `goal` is the text to build it from: `learn {query: goal, mode: "lesson"}`.
- A lesson's `passes` is one sentence a machine could verify.
- Skill ids are stable (`py.loops`, `bl.modifiers`) and each skill lists what it needs, so a plan's skills are a graph the skill tree can draw. Names are at most 18 characters.
- `catalog/playlists.json`: 50 YouTube playlists, two for each of 25 plans. Every id, title, channel and length was fetched from the playlist page on Nov 22 2026 and matched against YouTube's oembed answer.

Three plans were written by hand as the pattern (Intro to Python, Intro to Blender, Intro to CAD). The other 37 were drafted by Claude agents and spot-read. None has been walked through in the app yet.
