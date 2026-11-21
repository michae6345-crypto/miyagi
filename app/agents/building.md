# building

**Status:** in progress (A5, wave 1) · **Priority:** P1 · **Port:** 5190 · **Branch:** `michael/app-launcher`

## Goal
Home-Building: while a lesson builds, a card grows out of the island (priority 45) and shows what it is built from,
the build phases (Watching the video, Finding the steps, Writing the checks, Ready to start), a white progress line
and about how long is left. "Keep working" (the one primary) folds it back into the building pill; "Stop building"
is a quiet two-tap that sends `end_lesson`.

## Owns
- `app/src/renderer/src/features/building/`
- `app/mock/scenarios/home.json` (shared with the launcher lane, A5)

## Contract
- **In** (engine → app): `lesson.building` (v2 `stage`, `phases`, `etaS`, `source`, `failed`), `lesson.ready`, `lesson.ended`
- **Out** (app → engine): `end_lesson` (Stop building, second tap)

## Plugs in as
islandModes: `build-card`, priority 45, width 560 (README island table).

## Done when
- [ ] Opens on a v2 `lesson.building` (phases / stage / source) once per build; closes on `lesson.ready`, a failed build, a disconnect, `lesson.ended`, a reset
- [ ] Done ticks are white, never green; the active phase is the gray ring; next is a faint ring
- [ ] One primary (Keep working); Stop building is two taps (arm, then confirm within 3 s) and sends `end_lesson`
- [ ] No hex outside core/theme.ts; no typed keycaps

## Test
`npm run dev:web -- --port 5190` → `http://localhost:5190/?scenario=home&size=1440x900#/launcher`, paste a fixture URL, Enter.

## Core requests
_None yet._

## Notes
