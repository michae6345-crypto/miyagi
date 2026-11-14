# drawer

**Status:** new · **Priority:** P2 · **Port:** 5184 · **Branch:** `adrian/drawer`

## Goal
A slim tab on the right edge (vertically centered, 6px from the edge). Click → a lesson drawer slides in: all steps as done / current / locked, the current step's checks, and the lesson's sources (video, notebook, paper).

## Owns
- `app/src/renderer/src/features/drawer/`

## Contract
- **In** (engine → app): from `core/lesson`: lesson (title, sources), steps, passed, stepId, checks
- **Out** (app → engine): none (there is no "jump to step" command yet; add a Core request if you want one)

## Plugs in as
overlayLayers: drawer (z 40); the tab and the drawer are marked `data-hit`

## Done when
- Matches the Apple look
- Never covers the spotlight target

## Test
`npm run dev:web -- --port 5184` → `http://localhost:5184/?scenario=full` (or `?scenario=drawer` once you add `mock/scenarios/drawer.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
-
