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
_TBD: Adrian fills this in._

## Core requests
_None yet._

## Notes
Run this one alone after the others are merged: it touches color values in every feature.
