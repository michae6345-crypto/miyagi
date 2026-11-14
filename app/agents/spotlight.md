# spotlight

**Status:** v1 built · **Priority:** P0 · **Port:** 5178 · **Branch:** `adrian/spotlight`

## Goal
Screen-first building mode: the engine's screen reader finds where you should work (in any app) and sends a rectangle. We dim the screen to 55%, cut a rounded glowing hole there (it springs when the target moves; the glow pulses once, then stays still), and put a small glass caption beside it with a voice button.

## Owns
- `app/src/renderer/src/features/spotlight/`

## Contract
- **In** (engine → app): `spotlight {rect:{x,y,w,h}, caption, app?, matched?}` in screen points, or `{clear:true}`; cleared on `step.started` / `step.passed`
- **Out** (app → engine): nothing directly; core sends `overlay.bounds` for every `data-hit` / `data-ui` element (keep the caption marked `data-ui`)

## Plugs in as
overlayLayers: spotlight (z 10)

## Done when
- The cut-out lands exactly on the rect (points; multi-display origin via `layout.origin`)
- The caption flips left at the screen edge
- Fallback mode: a glowing outline only, no dim (the cut-order item)
- Never blocks typing (click-through)

## Test
`npm run dev:web -- --port 5178` → `http://localhost:5178/?scenario=full` (or `?scenario=spotlight` once you add `mock/scenarios/spotlight.json`)

## Adrian's spec
_TBD: Adrian fills this in._

## Core requests
_None yet._

## Notes
-
