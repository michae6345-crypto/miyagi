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
_TBD: Adrian fills this in._

## Core requests
_None yet._

## Notes
-
