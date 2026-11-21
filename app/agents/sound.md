# sound

**Status:** pass 1 + fix rounds 1 and 2 done: synthesized cues, gate (now also holds for typing in other apps), bus hooks, stage monitor, Node check. Not heard on the Mac (no audio played during the lane) and not run in Electron. · **Priority:** P3 · **Port:** 6013 · **Branch:** `michael/app-sounds`

## Goal
Optional, tasteful UI sounds, **OFF by default** (Michael disliked the old voice). With Sounds set to Subtle:

| Moment | Cue | Shape | Peak | Length |
|---|---|---|---|---|
| A step passed | tick | one soft woody tick, 1244 Hz with a fast-dying inharmonic partial | -30 dBFS | 70 ms |
| Lesson complete, setup finished | done | two gentle notes a fifth apart (G5 then D6, 85 ms later) | -27 dBFS | 240 ms |
| A pointer press on a surface's ONE primary (sub-toggle, off by default) | tap | barely there, 680 Hz | -36 dBFS | 35 ms |

All synthesized from code into a sample buffer (no audio files, no network). Every cue is under -24 dBFS and under 250 ms, has a raised-cosine attack and a 12 ms fade to exact zero (no clicks).

## Owns
- `app/src/renderer/src/features/sound/`
  - `synth.ts`: the cue specs and `renderCue(cue, sampleRate)`. Pure, no imports: the app and the Node check render the same samples.
  - `gate.ts`: when a cue may play, as a pure function of the clock.
  - `player.ts`: WebAudio. One `AudioContext`, made on the first cue (never at startup), one cached `AudioBuffer` per cue, suspended after 2 s idle.
  - `store.ts`: bus hooks, typing and tap listeners, Do Not Disturb polling, the shared clock between windows.
  - `settings.ts`: Off / Subtle and the tap sub-toggle.
  - `Monitor.tsx`: browser stage only (`?sound=…`): the proposed Sounds control, test cues and a readout of the last cue.
  - `sound.check.ts`: the Node check (below).
- `app/src/main/features/sound.ts`: `sound:dnd`, is a macOS Focus on; `sound:idle`, seconds since the last key or mouse input anywhere on the system (`powerMonitor.getSystemIdleTime()`, whole seconds, no permission).

## Rules (gate.ts)
- Off means off. The tap also needs its own sub-toggle.
- Never more than one cue per 400 ms, counted across every miyagi window (shared through localStorage). Every cue is shorter than 250 ms, so two never overlap.
- Never while the learner types: any edit key in an input, textarea or contenteditable, in any miyagi window, holds cues for 1.2 s.
- The learner mostly types in VS Code and the terminal, which miyagi never sees, and steps pass live while they type. So before an engine cue (tick, done) the overlay asks main for `sound:idle`; under 1 s marks the system busy (`withSystemIdle` in gate.ts), so the cue waits. While it is held only by input elsewhere, the overlay asks `sound:idle` again every 225 ms (`SYSTEM_POLL_MS`) and plays at the first sample that reads a quiet second, so a tick after Cmd+S or Shift+Enter lands about 0.5 to 0.9 s after the green instead of a fixed 1.2 s or more, with about ten chances inside the window; it is dropped 2.5 s after the pass if the input never stops. Typing in a miyagi field keeps its fixed 1.2 s quiet wait. This is system-wide input, keys AND mouse: a learner who keeps moving the pointer for 2.5 s after a pass also gets no tick. That is the stricter side on purpose (a missed tick costs nothing; a tick mid-typing is the thing the brief forbids). If it proves too strict in use, the narrower fallback is "keys only": it needs a keyboard-only idle source (CGEventSourceSecondsSinceLastEventType for key events via a native helper), so it is a Core request and needs Michael's OK. A cue answering a click in miyagi (a tap, setup done) never reads system input.
- A tick or done blocked only by the gap or by typing waits (one pending cue; done outranks tick), for at most 2.5 s from when it was FIRST asked for (a second tick while one is held keeps the first one's time), then it is dropped. A lesson reset bumps a generation counter, so a `sound:idle` answer still in flight from the old lesson never plays in the new one. A tap is never held: late feedback is noise. Keyboard "clicks" (Enter / Space) never tap.
- Do Not Disturb: main reads `~/Library/DoNotDisturb/DB/Assertions.json` (macOS 12+), cached 15 s, polled every 30 s only while Sounds is on. Any read or parse failure (newer macOS may need Full Disk Access) means "not detectable: ignore". A scheduled Focus with no assertion is not seen. Windows: never in DND.

## Hooks (bus only, no other feature edited)
- `onMessage('step.passed')`: tick. Not for `skipped` or `already`. The lesson's last step (and `complete`, not `pending`) plays done instead.
- `onMessage('card')` with kind `complete` or a `skillMap`: done, once per lesson (not again if the last step already chimed).
- `onUi('setup-done')` (Core request 4): done, when the learner presses setup's last button. Not `Prefs.onboarded`: `markDone()` also runs on the first frame of setup when every permission is already granted (a reinstall), which would chime before anything happened. Sounds are Off by default and only set in Settings after setup, so in practice this only covers setup reruns.
- A pointer press on a primary, on `pointerdown` (left button, mouse or pen), so the sound lands with the press dip (`pressMotion` whileTap) instead of trailing it on mouse-up: `data-button="primary"` (core/ui/buttons.tsx), else the white-filled `.mg-press-light` (core/ui/atoms.tsx `PrimaryButton`, see Core requests).
- Engine cues play in the overlay window only (the `sound-host` layer), like voice's speaker, since every window gets the feed. Taps play in the window that was clicked.

## Setting
`setSoundMode('off' | 'subtle')`, `setSoundTaps(boolean)`, `useSound(s => s.mode)` from `features/sound/settings.ts`. Until Core adds the prefs it persists in localStorage `miyagi.sound` (every window shares the origin and the `storage` event carries the change). It already reads core Prefs `sounds` / `soundTaps` if they exist, and `setSoundMode` already writes them, so Core's change lights up with no edit here (migration below). The browser stage's control (`?sound=…`) is memory only: it never writes localStorage or Prefs, so a later plain stage load can't come up Subtle and play real audio.

## Test
- Stage: `npm run dev:web -- --port 6013 --strictPort` then
  - `http://localhost:6013/?scenario=happy&sound=1`  Subtle (real audio in your browser)
  - `&sound=taps`  Subtle plus the tap sub-toggle
  - `&sound=dry`  everything on, nothing reaches the speakers (no AudioContext is made). Used for every lane screenshot.
  - `&sound=0`  Off
  - `&busy=1`  the stage answers `sound:idle` with 0: the learner is typing in another app the whole time. Tick / Done wait, then drop ("dropped", "step passed, input elsewhere").
  - `&busy=input`  `sound:idle` is whole seconds since the last key or pointer press in the stage page. Press a key, then a test Tick: the monitor shows "waits 225 ms" until the idle clock reads a quiet second, then "played".
  - `?scenario=complete&sound=dry`: the mock passes every step: ticks, then one done on the last step, none for the complete card.
  The monitor (bottom left) shows the Sounds control, Tick / Done test buttons, a Primary to test the tap, and the last cue: what played or why not ("waits 257 ms", "typing", "sounds are off"), its level and length, and its real loudness outline swept in left to right.
- Node check, no audio device, nothing played: `npx tsx src/renderer/src/features/sound/sound.check.ts` (from `app/`). 93 checks: every cue at 44.1 and 48 kHz (peak under -24 dBFS and on its level, under 250 ms, starts and ends on silence, no DC, finite, deterministic), the gate on a fake clock (off by default, 400 ms gap, typing hold, DND, taps sub-toggle, done outranks a waiting tick, stale drop, cross-window gap, a 5 s burst never plays two cues within 400 ms), typing in another app on a fake system idle clock (re-asked every 225 ms, at least 8 chances, dropped within 2.5 s; a pass 0.3 s after the last key ticks within 1 s; a stray pointer move at +1.2 s and +2.4 s no longer drops it; plays within one poll of the quiet second; an idle system plays at once), a second held tick keeping the first bornAt, the reset generation guard and the DND parse.
- Shots: `/Users/tripi/sand hacks/miyagi-v2/screens/round5/sound-*.jpg` (headless, `--mute-audio`, `?sound=dry`).

## Core requests
1. **Prefs** (`common/prefs.ts`): `sounds: 'off' | 'subtle'` (default `'off'`) and `soundTaps: boolean` (default `false`), kept by `sanitizePrefs`. `settings.ts` already reads and writes them. Migration is handled here, no Core work: once `prefs:get` carries `sounds`, a value saved in localStorage `miyagi.sound` before this lands is copied into Prefs (when Prefs still holds the default) and the local key is removed; until that copy finishes, Prefs only wins when it differs from the default or nothing is saved locally, so the new default `'off'` never silently turns a saved Subtle off. After it, localStorage is no longer written.
2. **Settings lane**: a "Sounds" row, `Segmented` Off / Subtle, and under it a `Toggle` "Tap on a primary press", disabled while Off. Call `setSoundMode` / `setSoundTaps` from `features/sound/settings.ts` (or `setPrefs` once 1 lands). The stage monitor shows the intended look.
3. **core/ui/atoms.tsx** `PrimaryButton` and **core/ui/glass.tsx** `GlassPrimary` (the `mg-press mg-press-light mg-glass` button): add `data-button="primary"` like `core/ui/buttons.tsx` does. The fallback reads the computed white fill, which finds `PrimaryButton` but never `GlassPrimary` in light appearance (its fill is ink there), so that primary gets no tap until it carries the marker.
4. **One-window onboarding lane**: add `'setup-done'` to `UiEvent` in `core/bus.ts` and `emitUi('setup-done')` when the learner presses setup's last button (Start learning), in the window that shows it. Not on `markDone()` from the permissions auto-check. The sound store already listens (`onUi('setup-done' as UiEvent, …)`; the cast goes once the union has it).
5. `agents/ports.json`: `"sound": 6013`.

## Notes
- Not verified by ear: by design nothing was played on Michael's Mac. Levels were chosen low (the loudest cue peaks at -27 dBFS) and are easy to tune in `CUES`.
- Not run in Electron: `sound:dnd` and the overlay host are typechecked and the DND parse is covered by the Node check.
- The keydown and pointerdown listeners return at once while Sounds is Off; the AudioContext is never created while Off.
