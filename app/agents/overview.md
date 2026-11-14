# overview

**Status:** v1 built · pass 2 · **Priority:** P1 · **Port:** 5175 · **Branch:** `adrian/overview`

## Goal
Hover the pill (150 ms) → it morphs into the step card: what step you're on, what to do now, and which checks pass. It also has the gear that opens Settings.

## Owns
- `app/src/renderer/src/features/overview/`
- `app/mock/scenarios/overview.json` (optional: a long-video lesson that sends `lesson.updated`)

## Contract (read from `core/lesson`, nothing to send)
- `stepTitle`, **`instructions`** (Michael P1-6: stored and never shown today: show it), `checks`, `stepVideo`, `useProgress()`, `useStatus()`
- `lesson.builtBy` → `builtByLabel()` ("Gemini watched this video")
- `lesson.goalMatch` → when `score < 0.5`, show `goalMatch.note` in amber under the title (Michael asked; it is the only amber here)
- `complete === false` → a quiet "More steps coming" line; `pendingNext` → "Next part is still building"
- `lesson.updated` replaces `steps`: update the count and segments without re-animating existing ones

## Adrian's spec (pass 2)
- **Precise, no unnecessary text.** Per row: label + value. No sentences that explain the UI. Cut "Video continues past 9:48 when all pass": the footer is just `Ask` + `<Kbd>{bridge.platform.keys.launcher}</Kbd>` and the gear.
- Instructions: one line, clamp to 2 lines, `color.label`.
- Segmented progress: white done, `fill.track` to go. Check rows use core `CheckList`.
- Gear (lucide `Settings`, 14px, neutral) → `bridge.invoke('settings:open').catch(() => {})` (the settings agent handles it; until it lands the call just fails quietly).
- Tokens only: replace the `.88/.18/.08` and `white/55`, `white/45` literals with `color.*` / `fill.*`.
- Brand: `app/brand/BRAND.md`. No blue, no glow, no gradients. Pastels only on options (none here).

## Done when
- Shows instructions, builtBy, the goalMatch note, "More steps coming"
- No hardcoded colors or keycaps; ≤12 words of chrome copy

## Test
`npm run dev:web -- --port 5175` → `http://localhost:5175/?scenario=full`, hover the pill.

## Core requests
_None yet._
