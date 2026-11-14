# overview

**Status:** pass 2 done and merged with UI polish (`origin/adrian/shell` efed46a + be157ff), not pushed · **Priority:** P1 · **Port:** 5175 · **Branch:** `adrian/overview`

### Pass 2 (functional), Sat
- Done, in new files (`Lines.tsx`, `Gear.tsx`); `index.tsx` only gained wiring lines:
  - **Instructions** under the header, `color.label`, 14/20 (UI polish's clamped-caption size), clamped to 2 lines (full text in `title`).
  - **goalMatch note** in amber under the title, only when `score < 0.5` (null score = no goal → hidden).
  - **Meta row** above the footer, `color.faint`: `builtByLabel()` left; right: "Next part is still building" (`pendingNext`) or "More steps coming" (`complete === false`). Hidden when there's nothing to say.
  - **Segments**: `lesson.updated` appends; existing segments keep key and state (measured per frame: opacity 1, same color, width just reflows), only new ones fade in (0.3 s, opacity only, from their own `fill.track`).
  - **Footer** (UI polish's): one fact left ("Video waits at 56:40" / "Passed", `color.faint`), right `Ask <Kbd>` and the **gear** (lucide `Settings` 14px, `color.label` → `color.text` on hover) → `bridge.invoke('settings:open').catch(() => {})`. Checked: no unhandled rejection without a handler.
- Merged UI polish (merge, no rebase): their tokens (`color.text` / `fill.track` segments, `fill.rule` hairline, `color.label` step line), Kbd and footer kept; my pieces were already on tokens (`color.label` / `faint` / `amber` / `text`). No hard-coded colors or keycaps left in `features/overview/`.
- Open: the current segment is white like the done ones while watching (`color.accent`); a distinct "current" look is a styling call for UI polish / Adrian.
- Stage: `http://localhost:5175/?scenario=overview` (long lesson, ~30 s script; hover the pill). Timeline: 0–8 s two steps + "More steps coming"; ~8.5 s `lesson.updated` → 4 segments; ~21–30 s step 4 passed with "Next part is still building"; then 7 steps, step 5 steady. `?scenario=pill` shows a lesson without any of the new fields.
- Shots: `agents/shots/overview-{long,updated,pending,steady,plain}.png`.

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
