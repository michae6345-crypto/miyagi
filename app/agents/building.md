# building

**Status:** round 3 (calm progress) on `michael/app-launcher-feel`: breathing active dot, phase crossfades, elapsed time when there is no eta; typecheck green, checked headless (port 5513) · earlier: v1 done (A5, wave 1): the Home-Building card; typecheck green, checked headless on the stage; draft PR #167 into `adrian/shell` · **Priority:** P1 · **Port:** 5190 · **Branch:** `michael/app-launcher`

## Goal
Home-Building: while a lesson builds, a card grows out of the island (priority 45) and shows what it is built from,
the build phases (Watching the video, Finding the steps, Writing the checks, Ready to start), a white progress line
and about how long is left. "Keep working" (the one primary) folds it back into the building pill; "Stop building"
is a quiet two-tap that sends `end_lesson`.

## Owns
- `app/src/renderer/src/features/building/` (`index.tsx`, `store.ts`, `Card.tsx`)
- `app/mock/scenarios/home.json` (shared with the launcher lane, A5)

## Contract
- **In** (engine → app): `lesson.building` (v2 `stage`, `phases`, `etaS`, `source`, `failed`; read through `core/lesson.ts` `build` / `buildingProgress` / `buildingMessage`), `lesson.ready`, `step.started`, `lesson.ended`
- **Out** (app → engine): `end_lesson {}` (Stop building, second tap). Nothing else.

## Plugs in as
islandModes: `build-card`, priority 45, width 560 (README island table: above the building pill 3 and the overview 20, below every card 50+ and build failed 62).

## Done when
- [x] Opens on a v2 `lesson.building` (phases, stage or source) once per build; an old engine (message + progress only) never opens it
- [x] Closes on `lesson.ready`, a failed build (`failed: true`; A7's build-failed card takes over), a disconnect (`connected` true → false), `step.started`, `lesson.ended` and a reset
- [x] Keep working folds it into the building pill for the rest of that build; the next build opens it again. The `dismiss` UI event does the same (the stage's Esc); in Electron Esc cannot reach the non-focusable overlay yet (Core request 3)
- [x] Done ticks are white in a faint ring, never green; the active phase is the gray ring with a still gray dot (never a spinner); next is a faint ring
- [x] Meter: white line at `progress`; "About N min left" only when `etaS` is there (never a guessed number)
- [x] One primary (Keep working); Stop building is two taps (arm "Tap again to stop" for 3 s, then `end_lesson`)
- [x] No hex outside core/theme.ts; no keycaps; no hue anywhere

## Test
`npm run dev:web -- --port 5190` → `http://localhost:5190/?scenario=home&size=1440x900&clean`, Ctrl+K, paste `https://www.youtube.com/watch?v=hOmEbUiLd01`, Enter. The card grows out of the pill: Watching the video → Finding the steps → held at Writing the checks, "Step 4 of 6", about 3 min left (segment `home_hold`; nothing follows, so it stays for screenshots).
- Stop building: first click "Tap again to stop", second click sends `end_lesson` (the mock answers lesson.ended, the pill goes idle).
- Keep working: back to the building pill; later phases don't reopen it.
- A goal: type "Build a ray tracer", Enter ("Just teach me"): the card says "From your goal" with the bonsai tile, then lesson.ready closes it.
- Failure / disconnect (console): `(await import('/src/core/bus.ts')).dispatch({type:'lesson.building',payload:{message:'',progress:0,failed:true}})` closes it; so does `setConnected(false)` from `core/lesson.ts` (import the `?t=` URL the page loaded if Vite has re-served it).

## Core requests
1. **Engine (E3): send the v2 build fields.** The card only opens when `lesson.building` carries `phases`, `stage` or `source`; `source.url` on a YouTube build gives the thumbnail, `source.channel` / `durationS` the meta line, `etaS` the time left. Without them the building pill alone shows the build, as before.
2. **mock/engine.ts** (integrator): see `launcher.md` Core request 8 (the default hello is lost in the stage; `home.json` sends its own).
3. **Core / main: Esc for island cards in Electron.** See `launcher.md` Core request 16.

## Notes
- **Mockup deviations:** the mockup draws the "Building lesson" pill above a separate card; here the island is one shape, so the pill's words (gray dot, "Building lesson") are the card's top line. Buttons are the core v2 `lg` buttons (44 high, 15 px primary, 13 px quiet). Meta separators " · " like the rest of the app. The tile for a goal is the bonsai, for a library lesson a book glyph, for a video the YouTube thumbnail (`i.ytimg.com`, allowed by the CSP) or a play glyph.
- `lengthLabel` / `etaLabel` (Card.tsx) never invent numbers: under a minute of video says nothing, no `etaS` says nothing.
- Checked headless (Chrome headless shell over CDP): open on the first v2 build, phases update in place, hold, Stop two taps → `end_lesson` → idle, Keep working folds and stays folded, goal source, lesson.ready / failed / disconnect close it. No console errors.
- Shots: `agents/shots/A5-05-building-card.png`, `A5-06-stop-armed.png`, `A5-09-building-goal.png`, `A5-10-folded-pill.png`.

**Round 3 (Nov 20, `michael/app-launcher-feel`).** Calm, honest progress:
- The active phase's gray dot breathes (opacity 1 to 0.4, 2.4 s, ease-in-out): the one moving element, never a spinner, no hue. It keeps going with reduced motion (opacity only), so waiting never looks frozen.
- A phase changing state crossfades its glyph; a tick springs up from 0.6 on the house spring; the label's color eases; rows rise in 40 ms apart on first show.
- Time: "About N min left" from `etaS`; without it, "Building for N min" from the engine's `elapsedS` (the 1 s heartbeat); with neither, nothing. Never a guess.
- Cancel: Stop building (two taps, `end_lesson`) and Keep working are real buttons. Esc folds the card only in the browser stage: the Electron overlay is not focusable, so no key reaches it (Core request 3).
- Not moved: the card grows at `pillTop` like every island card, so it covers the editor's tabs (y 40 to 497 on 1440×900). See launcher.md Core request 14.
