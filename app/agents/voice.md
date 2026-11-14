# voice

**Status:** pass 2 done (stage-verified, not yet on Electron) · **Priority:** P2 · **Port:** 5181 · **Branch:** `adrian/voice`

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

## Store API (for the shortcut bar and any Voice button)
- `useVoice(s => s.on)`: voice is on. `s.speaking`: a clip is audible right now. `s.level`: 0..1 loudness while speaking (fast attack, slow release, 0.05 steps); **`undefined` when the audio can't be measured** (no CORS on the engine's `/tts`), so animate on your own then.
- `toggleVoice()`: use it for any Voice button. It runs the ⌥V path (`triggerShortcut`), so the engine hears every toggle (spotlight's button used to flip only the local state).

## Pass 2 (done)
- `player.ts`: one `<audio>` at a time, played only in the overlay window (the `voice-player` layer attaches it), so a `speak` heard by several windows plays once. A new `speak` stops the old clip; off / `lesson.ended` / any reset stop it in the same tick; a `speak` while off is ignored.
- Bad URL (404, HTML, refused port): one attempt, no `speaking`, nothing thrown.
- Level meter: an AnalyserNode when the audio is readable (same origin, `data:`, or CORS). Cross-origin without CORS: the clip loads as `crossOrigin=anonymous` first, fails, plays again unmeasured, and that origin is remembered (next clips go straight to the plain path). Verified against a local fixture on two ports, with and without `Access-Control-Allow-Origin`.
- ⌥V with the ElevenLabs key `missing` → claimed, `notify('Add an ElevenLabs key in Settings')`; `invalid` → 'Check your ElevenLabs key in Settings'. Turning voice **off** always works.
- Reconnect (`reset {reason:'reconnect'}`) → audio stops and `on` = false.
- Not verified: Electron (Mac). The notice line itself: nothing in `adrian/shell` renders `notice` yet (the pill branch does), so check the line after the pill merge.

Shots: `shots/voice-bar-off.png`, `voice-bar-speaking.png` (tile lit + equalizer), `voice-bar-on-quiet.png` (on, between clips).

## Test
`npm run dev:web -- --port 5181` (Browser pane config `voice-web`) → `http://localhost:5181/?scenario=voice&engine=ws://127.0.0.1:9` (the `engine=` part forces the inline mock while a mock server holds 8787).
- **Alt+V**: voice on; ~0.3 s later a 2.4 s soft hum plays (stand-in for TTS) and the Voice tile shows the equalizer. Alt+V again stops it at once.
- **Alt+E** while it plays: an Explain card and a second, higher hum that replaces the first (never both).
- **Alt+H**: the mock reports the ElevenLabs key as missing; Alt+V (from off) then shows the key line and stays off. **Alt+S** restores the key.
- In `full`, Alt+V plays the same hum.

## Core requests
1. **Voice state echo (contract, Michael).** The engine never says whether voice is on, so `on` is a guess. The brief's rule (off after every reconnect) is right after an engine restart, but a renderer reload also goes connected false → true and emits `reset {reason:'reconnect'}` while the engine may still have voice on → the tile shows off, the engine keeps speaking (we ignore it), and the next ⌥V turns the engine off while the tile says on. Fix either way: `status` carries `voice: boolean` (or a `voice.state {on}` event), or `voice_toggle` accepts `text: "on" | "off"` so the app can send the state it wants. Workaround: the brief's rule.
2. **CORS on `/tts/*` (engine, Michael).** `Access-Control-Allow-Origin: *` lets the renderer (file:// or localhost:5173) read the audio for the level meter. Without it voice still plays, `level` stays undefined, and each new engine origin costs one failed load once.
3. **`usePressed` keeps `voice_toggle` (core/shortcuts).** Nothing answers a voice toggle with a card, so `pressed` stays `voice_toggle` until the next card; a later, unrelated `status thinking` would spin the Voice tile. Clear `pressed` right away for kinds that never think (`voice_toggle`, maybe `back`), or have the bar skip the spinner for Voice.

Mic capture (ask by voice) needs macOS microphone permission: check with Michael before adding it.
