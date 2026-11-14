# drawer

**Status:** new · **Priority:** P2 · **Port:** 5184 · **Branch:** `adrian/drawer`

## Goal
A slim tab on the right edge (vertically centered, 6px from the edge). Click → a lesson drawer slides in: every step as done / current / locked, the current step's checks, and the lesson's sources. With long videos (Michael: Karpathy's 2-hour GPT video) the steps arrive part by part, so the drawer is where you see what's coming.

## Owns
- `app/src/renderer/src/features/drawer/`
- `app/mock/scenarios/drawer.json` (a long lesson: `lesson.ready` with `complete:false`, then two `lesson.updated`)

## Contract (read from `core/lesson`)
- `lesson` (title, sources, `builtBy` → `builtByLabel()`), `steps`, `passed`, `stepId`, `checks`, `complete`, `parts`, `pendingNext`
- **`lesson.updated`** replaces `steps` (ids stable, new steps appended): new rows fade in; existing rows must not re-animate.
- `complete === false` → a last quiet row "More steps coming" (with `parts` → "Part 2 of 5"); `pendingNext` → "Next part is still building".
- Sources: one row each with its kind tile (`theme.kindTone`: notebook/repo sky, paper pink, blog lilac; video = thumbnail). Click opens the URL (`window.open`; main denies new windows and opens https externally).
- Click a step row with `video` → `seekVideo(step.video.start)` (core). There is no "jump to step" command: ask under Core requests if you want one.
- **Out:** none.

## Adrian's spec (pass 1, from his feedback on the other features)
- Black glass panel (`color.glass`), white text, system font, `radius.card`. The tab: 4×40 white at `fill.track`, `data-hit`.
- States: done = check (core `CheckIcon`, white), current = white, locked = `color.faint`. Green only for the passed tick on the current step's checks (core `CheckList`). No amber unless off track.
- Labels only; step titles from the data. ≤12 words of chrome copy.
- Never covers the spotlight target: when a `spotlight` rect intersects the drawer, slide it closed.
- The one spring; transform/opacity only.

## Done when
- Steps, checks, sources; part-by-part updates without re-animating; never covers the spotlight

## Test
`npm run dev:web -- --port 5184` → `http://localhost:5184/?scenario=drawer`. Restart the dev server after adding the folder and the scenario.

## Core requests
_None yet._
