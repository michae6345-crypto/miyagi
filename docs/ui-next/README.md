# miyagi UI next: pages, lesson plans, Blender and CAD

Mockups and content from Nov 22 2026. No app code. The app pages and the engine are built from these in their own lanes.

## What is here

| Folder | What |
|---|---|
| `mock/` | The mock, plain HTML. Open `mock/index.html?s=<screen>&t=light` (or `t=dark`). |
| `shots/` | Every new screen at 2880 px wide, light and dark. |
| `catalog/` | The lesson plans: 40 plans, 382 lessons, 372 skills. |
| `INTEGRATIONS.md` | How Blender and CAD work should be checked, and the contract ask. |
| `tools/render.mjs` | Renders screens to PNG with headless Chrome. |

## Screens

`home`, `progress`, `settings`, `settings-apps`, `settings-data`, `library`, `plans`, `plan`, `plan-playlist`, `plan-goal`, `lesson-blender`, `skills-cad`.

The earlier screens still load from the same file: `skills-path`, `skills-map`, `skills-tracks`, `skills-steps`, `skills-proof`, `skills-share`, `skills-empty`, `course`, `lesson`, `home-link`, the empty states and `onboard-1` to `onboard-3`.

The rules behind the pages:

- One 740 px column, left aligned.
- Numbers sit on one line with hairlines between them. No stat tiles.
- Lists are rows or tables with a hairline between rows. The only card is Continue.
- One sidebar on screen. Settings swaps the app sidebar for its own list.
- Green only for passed. Pastels only on option chips.
- The copy on Settings, Your data is placeholder text. It has to match what the engine does before it ships.

To render a screen:

```
node tools/render.mjs <out dir> 1440 900 2 "home-light=file:///<path>/mock/index.html?s=home&t=light"
```

For a page taller than the window, add `&h=1300` to the URL and pass the same height in place of 900.

## The catalog

- `catalog/plans/<id>.json`: one plan per file. `catalog/SCHEMA.md` is the format.
- `node catalog/build.mjs --check` checks every rule. `node catalog/build.mjs` also writes `catalog.json`, `catalog.js` (read by the mock) and `CATALOG.md` (the readable version).
- A lesson's `goal` is the text to build it from: `learn {query: goal, mode: "lesson"}`.
- A lesson's `passes` is one sentence a machine could verify.
- Skill ids are stable (`py.loops`, `bl.modifiers`) and each skill lists what it needs, so a plan's skills are a graph the skill tree can draw. Names are at most 18 characters.
- `catalog/playlists.json`: 50 YouTube playlists, two for each of 25 plans. Every id, title, channel and length was fetched from the playlist page on Nov 22 2026 and matched against YouTube's oembed answer.

Three plans were written by hand as the pattern (Intro to Python, Intro to Blender, Intro to CAD). The other 37 were drafted by Claude agents and spot-read. None has been walked through in the app yet.
