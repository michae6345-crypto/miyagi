# voice

**Status:** v1 built · pass 2 · **Priority:** P2 · **Port:** 5181 · **Branch:** `adrian/voice`

## Goal
Optional voice (⌥V): play the engine's `speak` audio (ElevenLabs) for captions and cards. The shortcut bar's Voice tile shows an equalizer while it plays.

## Owns
- `app/src/renderer/src/features/voice/`
- `app/mock/scenarios/voice.json`

## Contract
- **In:** `speak {audioUrl, text}`. **Core now makes `audioUrl` absolute** (main resolves `/tts/<hash>.mp3` against the engine's http origin; Michael P1-1), so just play it. In the browser stage the mock's URL may not exist: fail quietly.
- **Out:** `action {kind:"voice_toggle"}` via the shortcut (not claimed).
- Needs the ElevenLabs key: when `useLesson(s => s.keyStatus?.elevenlabs)` is `missing`, claim ⌥V and call `notify('Add an ElevenLabs key in Settings')` (core/lesson: a one-line pill message) instead of toggling.

## Adrian's spec (pass 2)
- One clip at a time: a new `speak` stops the old one. Voice off stops audio immediately. `lesson.ended` / reset stops it.
- **Desync (Michael P2):** the engine restarts with voice off; after a reconnect, reset `on` to false (core emits `reset` with `{reason:'reconnect'}`).
- Export `useVoice(s => ({ on, speaking, level }))` for the shortcut bar's equalizer (a 0..1 level from an AnalyserNode is a bonus; on/off speaking is enough).
- No UI of your own beyond that. No sparkles, no glow.

## Done when
- Plays and stops cleanly, never overlaps, stops on off / end / reconnect
- Shortcut bar can read `speaking`

## Test
`npm run dev:web -- --port 5181` → `http://localhost:5181/?scenario=voice`, Alt+V.

## Core requests
_None yet._ Mic capture (ask by voice) needs macOS microphone permission: check with Michael before adding it.
