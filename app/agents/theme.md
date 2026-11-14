# theme

**Status:** new · **Priority:** P2 · **Port:** 5185 · **Branch:** `adrian/theme`

## Goal
Adrian's own theme: colors, type, radii, shadows, replacing the placeholder palette.

## Owns
- `app/src/renderer/src/core/theme.ts` and `app/src/renderer/src/styles.css` (an exception to the core rule)
- color values in any feature file, nothing else

## Contract
- **In** (engine → app): -
- **Out** (app → engine): -

## Plugs in as
tokens

## Done when
- All colors come from tokens
- Status colors stay distinguishable (watching / off-track / passed)
- Looks right over light and dark desktops

## Test
`npm run dev:web -- --port 5185` → `http://localhost:5185/?scenario=full` (or `?scenario=theme` once you add `mock/scenarios/theme.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
Run this one alone after the others are merged: it touches color values in every feature.
