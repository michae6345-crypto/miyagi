# cards

**Status:** v1 built · **Priority:** P0 · **Port:** 5177 · **Branch:** `adrian/cards`

## Goal
Coach cards that grow out of the pill. **Off-track** (amber): what's wrong in ≤12 words, the yours-vs-tutorial loss curve, "expected vs yours", the checks, and Show me / Explain / Apply fix. **Back on track** (green) after a recovered step; auto-hides. **Explain / Hint / Answer** cards from the engine, with an optional "jump to 7:00" video link. Calm: no shaking, no red.

## Owns
- `app/src/renderer/src/features/cards/`
- `app/mock/scenarios/cards.json` (optional: a `metric` stream for the live curve)

## Contract
- **In** (engine → app): `offtrack`, `step.passed`, `card`, `metric {runId, step, name, value}` (live curve), `check.updated`
- **Out** (app → engine): `action {kind: show_me | explain | apply_fix | hint}`

## Plugs in as
islandModes: offtrack (70), success (60), card (50)

## Done when
- Off-track matches the Apple restyle of mockup 06
- The curve draws from live `metric` events (the mock's `offtrack.curve` is the fallback)
- Apply fix → the card collapses, checks re-run, the success card shows when it passes
- Every card readable in 2 seconds

## Test
`npm run dev:web -- --port 5177` → `http://localhost:5177/?scenario=full` (or `?scenario=cards` once you add `mock/scenarios/cards.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
Tutorial reference curve: still an open question for Michael (optional `offtrack.curve`, or a `metric` with runId "tutorial").
