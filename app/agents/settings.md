# settings

**Status:** new · **Priority:** P1 · **Port:** 5183 · **Branch:** `adrian/settings`

## Goal
Bring-your-own-keys, like cue. **Born from the notch island** like the launcher (a focusable window whose panel starts from the island's shape and collapses back into it; reuse the launcher's pattern, and ask core to generalize the `launcher:open {from}` handoff to settings). A small Apple-style Settings sheet (gear in the overview card; also shown on first run) with fields for **Anthropic** and **Gemini** (required), **Bright Data** (optional: without it you paste a YouTube link instead of searching), **ElevenLabs** (optional voice) and **Tiger Data URL** (optional). Each key shows a status dot (ok / missing / invalid / env), and there's a Test button.

## Owns
- `app/src/renderer/src/features/settings/`: window `settings`, form, status dots, exports `openSettings()`
- `app/src/main/features/settings.ts`: focusable centered window, safeStorage read/write in userData, `engine.onOpen` → send `config.keys`

## Contract
- **In** (engine → app): `config.status` (in `core/lesson.keyStatus`)
- **Out** (app → engine): `config.keys {anthropic?, gemini?, brightdata?, elevenlabs?, tigerUrl?}` on every connect and on Save / Test

## Plugs in as
`windows: [{ route: 'settings', stage: 'fill' }]` + a main feature

## Done when
- Keys encrypted with `safeStorage` (Keychain / DPAPI): never plain text, never logged, never in the repo
- Sent on every (re)connect
- Status dots from `config.status` ("env" = the engine uses its own .env, which is how the demo Mac runs)
- First run opens it if required keys are missing

## Test
`npm run dev:web -- --port 5183` → `http://localhost:5183/?scenario=full` (or `?scenario=settings` once you add `mock/scenarios/settings.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
The overlay window is not focusable, so Settings must be its own focusable window (for typing). In the browser stage use `registerWebHandler` with in-memory storage; never put real keys in localStorage.
