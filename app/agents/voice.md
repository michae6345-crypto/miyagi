# voice

**Status:** pass 3 done: system voice, no ElevenLabs (speech checked in Electron's Chromium; stage run skipped at Adrian's call, Mac not checked) · **Priority:** P2 · **Port:** 5181 · **Branch:** `adrian/voice`

## Goal
Optional voice (⌥V): Miyagi reads its own lines aloud. The shortcut bar's Voice tile shows an equalizer while it talks.

## Decision (Adrian, Sat afternoon)
"I want it to be able to talk, but I don't care about ElevenLabs." Voice uses the **computer's own voice** (Web Speech API, `speechSynthesis`): no key, no network, no engine audio. The engine's `speak {audioUrl, text}` and its ElevenLabs key are no longer used by the app.

## Owns
- `app/src/renderer/src/features/voice/` (`store.ts`, `speech.ts`, `index.tsx`)
- `app/mock/scenarios/voice.json`

## What it says (only while on)
- `card`: title, then body (explain, hint, answer, resume, setup, preflight).
- `offtrack`: title, then body.
- `step.passed`: the passed line ("Good. Now the next one.", `copy.passed`).
- `video.pause` (the engine stopped the video for the learner to work) and the moment voice turns on: the step's instructions.
- Markdown/code punctuation is dropped before speaking (`u_t` reads "u t").
- One line at a time, newest wins. Voice off, Esc (`dismiss`), `lesson.ended` and any reset stop it at once. `on` survives reconnects (nothing to sync any more).
- Speaks only in the overlay window (the `voice-speaker` layer attaches it), so a line several windows hear is said once.
- Voice: a downloaded Premium/Enhanced voice in the app's language if the Mac has one, else the system default.

## Store API (shortcut bar, spotlight)
- `useVoice(s => s.on)`, `useVoice(s => s.speaking)`. No `level` (the system voice can't be measured): animate the equalizer on its own while `speaking`.
- `toggleVoice()`: any Voice button. ⌥V is **claimed** (never sent to the engine), so `usePressed` never becomes `voice_toggle`.

## Test
`npm run dev:web -- --port 5181` (Browser pane config `voice-web`) → `http://localhost:5181/?scenario=voice&engine=ws://127.0.0.1:9` (the `engine=` part forces the inline mock while a mock server holds 8787).
- **Alt+V**: voice on; it reads the step's task; the Voice tile shows the equalizer. Alt+V again stops it mid-word.
- **Alt+E**: an Explain card, read aloud. **Alt+H** while it talks: an off-track note that cuts in (never both).
- **Esc** stops it. In `full`, the happy path reads each gate, card and pass.

Electron (Mac): Electron's default `autoplayPolicy` lets the overlay speak without a click; check it once on the Mac.

Shots (pass 2, the tile looks the same): `shots/voice-bar-off.png`, `voice-bar-speaking.png`, `voice-bar-on-quiet.png`.

## Core requests
_None._ For Michael (contract, optional): the app no longer sends `voice_toggle` or uses `speak` / the ElevenLabs key, so the engine can skip TTS entirely. The settings feature can drop the ElevenLabs key row.

Mic capture (ask by voice) needs macOS microphone permission: check with Michael before adding it.
