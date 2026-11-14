# settings

**Status:** new · **Priority:** P1 · **Port:** 5183 · **Branch:** `adrian/settings`

## Goal
Bring-your-own-keys. A small settings sheet **born from the notch island** (like the launcher): a focusable window whose panel starts at the island's exact rect and collapses back into it. Five keys: **Anthropic** and **Gemini** (required), **Bright Data** (optional: without it you paste a YouTube link), **ElevenLabs** (optional: voice), **Tiger Data URL** (optional). One status per key, a Test button, Save.

## Owns
- `app/src/renderer/src/features/settings/`: window route `settings`, the sheet, status dots
- `app/src/main/features/settings.ts`: the focusable window, safeStorage, sending `config.keys`
- `app/mock/scenarios/settings.json`

## How the keys flow (the integration, read carefully)
1. **Storage (main only).** Keys live in `userData/keys.bin`: `safeStorage.encryptString(JSON.stringify(keys))` (Keychain on Mac, DPAPI on Windows). If `safeStorage.isEncryptionAvailable()` is false, keep them in memory for this run only and show "Not saved: no secure storage". Never plain text, never logged, never in the repo, never in localStorage.
2. **Renderer never gets a key back.** `bridge.invoke('settings:get')` returns `{ [name]: { set: boolean; last4?: string } }` only. `bridge.invoke('settings:save', partial)` sends new values to main; main merges, encrypts, writes, then sends `config.keys`. An empty field means "unchanged"; a Clear button per key removes it.
3. **Always send ALL stored keys.** The engine's `server/config.py set_app_keys` drops every key that's missing from the payload, so a partial `config.keys` would clear the others. Send the full set every time.
4. **On every (re)connect:** `ctx.engine.onOpen(() => ctx.engine.send(cmd('config.keys', all)))`. While offline nothing is queued; onOpen re-sends.
5. **Status:** the engine answers `config.status` per key: `ok` (your key) · `env` (the engine's own .env: how the demo Mac runs) · `missing` · `invalid` (not produced yet: the engine checks presence only today). Read it from `useLesson(s => s.keyStatus)`.
6. **Test** = re-send `config.keys` and show the new `config.status` (spinner on the Test button until it arrives, 3 s timeout → "No answer from Miyagi").
7. **Opening:** main handles `ctx.handle('settings:open', …)`; anyone calls `bridge.invoke('settings:open')` (the overview's gear does). In the browser stage, `registerWebHandler('settings:open' | 'settings:get' | 'settings:save', …)` with in-memory storage. First run: open it once if Anthropic or Gemini is `missing` (not `env`).

## Born from the island
Core has the hand-over: `ctx.islandSize()` + `ctx.yieldIsland(true|false)` in main, or `bridge.emit('island:yield' | 'island:return')` from the renderer. Copy the launcher's grow/collapse (`features/launcher/Launcher.tsx`): start at the island rect (top = `platform.pillTop`, centered, `shadows.pill`), spring to the sheet (`shadows.card`), reverse on close. Esc closes. The window is focusable (typing) and must not steal focus when hidden.

## Adrian's spec (pass 1, from his feedback on the other features)
- Brand: `app/brand/BRAND.md`. Black island, white text, system font. No blue, no gradients, no glow.
- **Status dots are not green and not amber** (green = passed, amber = off track only): `ok` = white dot, `env` = gray dot + "From engine", `missing` = hollow ring, `invalid` = white text "Invalid". No glow.
- Minimal copy: a title "Keys", one label per row, no paragraphs. Optional rows say "Optional" in `color.faint`. Masked fields show `•••• last4`.
- Save is the one `PrimaryButton`; Test and Clear are neutral (`fill.button`).
- Tokens only (`core/theme.ts`), the one spring.

## Done when
- Keys encrypted, never echoed, sent in full on every connect and on Save / Test
- Status per key from `config.status`; Test works; first run opens it when required keys are missing
- Grows out of the island and collapses back into it

## Test
`npm run dev:web -- --port 5183` → `http://localhost:5183/?scenario=settings` (add `mock/scenarios/settings.json` that answers `config.keys` with a `config.status`; restart the dev server after adding it).

## Core requests
_None yet._ (Ask here for anything in core; keep going with a local workaround.)

## Notes
The overlay window is not focusable, so Settings is its own window. Every `ctx.createWindow` window already follows Spaces / full-screen apps; call `ctx.raise(win)` so it floats on top.
