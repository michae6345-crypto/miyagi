# shortcut-bar

**Status:** v1 built · **Priority:** P1 · **Port:** 5179 · **Branch:** `adrian/shortcut-bar`

## Goal
The bottom bar during a lesson (mockup 04): "Ask anything ⌥Space" (opens the launcher in ask mode) and Back ⌥← · Explain ⌥E · Diagram ⌥D · Show me ⌥S · Hint ⌥H · Voice ⌥V. Buttons light up for an open diagram / voice on; the Voice button shows an equalizer while audio plays. A pressed shortcut scales to 0.94 for 90ms.

## Owns
- `app/src/renderer/src/features/shortcut-bar/`

## Contract
- **In** (engine → app): `core/lesson` (lesson active), diagrams store (open), voice store (on, speaking)
- **Out** (app → engine): `action {kind}` via `triggerShortcut(kind)`

## Plugs in as
overlayLayers: shortcut-bar (z 60), 24px above the dock / taskbar

## Done when
- Matches mockup 04 with Mac and Windows labels
- Appears with the lesson (y 16 → 0)
- Global shortcut presses animate the button

## Test
`npm run dev:web -- --port 5179` → `http://localhost:5179/?scenario=full` (or `?scenario=shortcut-bar` once you add `mock/scenarios/shortcut-bar.json`)

## Adrian's spec
_TBD: Adrian fills this in._

## Core requests
_None yet._

## Notes
Registering the global shortcuts is core (`src/main/index.ts`).
