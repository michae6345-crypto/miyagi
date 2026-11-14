# voice

**Status:** v1 built · **Priority:** P2 · **Port:** 5181 · **Branch:** `adrian/voice`

## Goal
Optional voice: when Voice is on (⌥V), play the engine's `speak` audio (ElevenLabs) for captions and cards; the Voice button shows an equalizer while it plays. Stretch: the launcher's mic button records a question (ask by voice).

## Owns
- `app/src/renderer/src/features/voice/`

## Contract
- **In** (engine → app): `speak {audioUrl, text}`
- **Out** (app → engine): `action {kind:"voice_toggle"}` (via the shortcut; not claimed)

## Plugs in as
overlayLayers: voice-player (z 0, no UI)

## Done when
- Plays / stops cleanly; never overlaps two clips
- Turning voice off stops audio immediately

## Test
`npm run dev:web -- --port 5181` → `http://localhost:5181/?scenario=full` (or `?scenario=voice` once you add `mock/scenarios/voice.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
Mic capture needs microphone permission on macOS; check with Michael before adding it.
