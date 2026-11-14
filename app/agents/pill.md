# pill

**Status:** v1 built · **Priority:** P0 · **Port:** 5174 · **Branch:** `adrian/pill`

## Goal
The Dynamic-Island pill hugging the notch: idle ("Learn anything ⌥Space"), building (spinner + the `lesson.building` message), and during a lesson "Step 4 · Define the residual" with a progress ring and status dot (gray watching · amber off-track · green passed). Owns **the step-pass moment**: the checkmark draws, the ring advances, the pill flashes green, the text crossfades to the next step, the video resumes 400ms later.

## Owns
- `app/src/renderer/src/features/pill/`

## Contract
- **In** (engine → app): `lesson.building`, `lesson.ready`, `step.started`, `check.updated`, `step.passed`, `offtrack` (status only), all read from `core/lesson`
- **Out** (app → engine): none (clicking idle opens the launcher via `bridge.emit("launcher:toggle")`)

## Plugs in as
islandModes: idle (0), building (1), compact (2). The morphing container itself is core (`core/Island.tsx`)

## Done when
- Matches mockup 01 (size, type, ring, dot)
- The step-pass sequence feels like one gesture
- Off-track: the dot turns amber and pulses twice, calm
- Mac: hugs the notch (y = 6)

## Test
`npm run dev:web -- --port 5174` → `http://localhost:5174/?scenario=full` (or `?scenario=pill` once you add `mock/scenarios/pill.json`)

## Adrian's spec
_TBD: Adrian fills this in._

## Core requests
_None yet._

## Notes
If the island container needs a change (timing, landing, flash), write it under Core requests.
