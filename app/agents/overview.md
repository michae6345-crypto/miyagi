# overview

**Status:** v1 built · **Priority:** P1 · **Port:** 5175 · **Branch:** `adrian/overview`

## Goal
Hover the pill (150ms) → it morphs into the step card from mockup 02: video thumbnail with timestamp, "Step 4 of 7", segmented progress, live checks, footer ("Video continues past 9:48 when all pass · Ask ⌥Space"). Also hosts the **gear that opens Settings**.

## Owns
- `app/src/renderer/src/features/overview/`

## Contract
- **In** (engine → app): from `core/lesson`: step, checks, stepVideo, progress, status
- **Out** (app → engine): none

## Plugs in as
islandModes: overview (20, width 440)

## Done when
- Matches mockup 02
- Gear → `openSettings()` from features/settings (once it exists)

## Test
`npm run dev:web -- --port 5175` → `http://localhost:5175/?scenario=full` (or `?scenario=overview` once you add `mock/scenarios/overview.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
-
