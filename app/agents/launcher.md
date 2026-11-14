# launcher

**Status:** v1 built · **Priority:** P0 · **Port:** 5176 · **Branch:** `adrian/launcher`

## Goal
Spotlight-style launcher (⌥Space; Ctrl+Shift+Space on Windows). Type what you want to learn → results stream in → Build lesson → the panel morphs into the pill (the signature transition). Pasting a YouTube link skips search. **During a lesson** it becomes "Ask about this step": Enter sends `action {kind:"ask", text}` and the answer comes back as a card.

## Owns
- `app/src/renderer/src/features/launcher/`

## Contract
- **In** (engine → app): `search.result`, `search.done`, `lesson.building`, `lesson.ready`, `error`
- **Out** (app → engine): `learn {query}`, `learn_url {url}`, `build_lesson {resultIds}`, `action {kind:"ask", text}`

## Plugs in as
`windows: [{ route: 'launcher', stage: 'fill' }]`; the window itself is created by core

## Done when
- Matches mockup 03; results stagger in 40ms; the highlight glides
- Build lesson → shrinks onto the pill rect (~450ms), no flicker
- URL paste → `learn_url`
- Ask mode during a lesson
- Empty / searching / error states
- Esc and click-outside close it

## Test
`npm run dev:web -- --port 5176` → `http://localhost:5176/?scenario=full` (or `?scenario=launcher` once you add `mock/scenarios/launcher.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
Window show/hide/focus is core (`src/main/index.ts`); the shrink target comes from `bridge.platform.pillTop` + `theme.pill`.
