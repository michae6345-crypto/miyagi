# <name>

**Status:** not started · **Priority:** P? · **Port:** see ports.json · **Branch:** `adrian/<name>`

## Goal
One paragraph: what the user sees and does.

## Owns
- `app/src/renderer/src/features/<name>/`
- (if needed) `app/src/main/features/<name>.ts`, `app/mock/scenarios/<name>.json`

## Contract
- **In** (engine → app): …
- **Out** (app → engine): …

## Plugs in as
islandModes / overlayLayers / windows: …

## Done when
- …

## Test
`npm run dev:web -- --port <port>` → `http://localhost:<port>/?scenario=<name>`

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
