# pill

**v2 (A2 `michael/app-pill-cards`, port 5187):** in progress. Owner of the pill and the cards for miyagi-v2 BUILD-PLAN A2 (Les-Mini, the pill lines of Les-Checking / NotYet / Passed, the Err-KernelInContext card footer, the Err-VSCodeSetup sheet). See "v2 (A2)" below.

**Status:** pass 2 (functional: notice, thinking, offline, next part) done, waiting on Adrian's review · **Priority:** P0 · **Port:** 5174 · **Branch:** `adrian/pill`

Pass 2 (Michael's audit + live test), on core `be157ff`:
- ✅ **Notice line** (audit P1-2): when core's `notice` changes, the pill shows the bonsai and that one line for 5 s, then returns to its state. Errors are white too: nothing red, no extra icon, `role="alert"`. Engine `error`s and a failed build land there; a failed build no longer leaves its message behind (`shots/pill-notice.png`).
- ✅ **Thinking** (Michael P0-2): while `useThinking()`, the bonsai crossfades to the small core Spinner in the same 16px spot, so Alt+E / Alt+S / Alt+H never look dead (`shots/pill-thinking.png`).
- ✅ **Offline** (audit P1-3): after `connected` has been false for 2 s (no flash at startup or on a hiccup), idle reads "Offline" in gray with no key chip; mid-lesson the status dot goes hollow and gray (`shots/pill-states.png`, last two rows).
- ✅ **Next part** (long videos): after a pass with `pendingNext` (or while the lesson is still `complete: false`), the pill shows "Next part is still building" with the spinner where the ring was, instead of "Lesson complete"; when `lesson.updated` appends the next step, the pill moves to it (`shots/pill-next-part.png`).
- ✅ **Calm** (#33): nothing animates without a real state change. Checked: the building text stays the same element across the timer tick; the same notice again only holds longer; thinking and offline crossfade only when they flip.

Earlier passes:
- ✅ Matches mockup 01: measured spacing, type, ring and dot (`shots/pill-vs-mockup.png`).
- ✅ The step-pass moment is one gesture: check draws → ring advances → flash → text crossfades to the next step at 560ms (`shots/pill-step-pass.png`).
- ✅ Off-track: the dot eases to amber and pulses twice (scale only, no glow), once per episode (`shots/pill-offtrack.png`).
- ✅ Last step: "Lesson complete" with the ring closed in green.
- ✅ Miyagi brand: the bonsai is in color, `<MiyagiMark size={16} />` (Adrian, Sun Nov 15; it was a one-color white glyph from Sat 2 PM), "Ask Miyagi ⌥Space", white ring/spinner/line, green only at the pass, amber only off track, gray watching, tokens only.
- ✅ Mac notch: core places the pill just under the notch (`pillTop 40`).
- ❌ Not seen in Electron (Windows). Checked in headless Chrome at 1600×1000 (the Browser pane was hidden). Offline was driven by calling core's `setConnected(false)` in the page (the inline mock can't disconnect).

## Goal
The Dynamic-Island pill hugging the notch: idle ("Ask Miyagi ⌥Space"), building (spinner + the `lesson.building` message), and during a lesson "Step 4 · Define the residual" with a progress ring and status dot (gray watching · amber off-track · green passed). Owns **the step-pass moment**: the checkmark draws, the ring advances, the pill flashes green, the text crossfades to the next step, the video resumes 400ms later.

## Owns
- `app/src/renderer/src/features/pill/`

## Contract
- **In** (engine → app): `lesson.building` (incl. `failed`), `lesson.ready` (`complete`), `lesson.updated`, `step.started`, `check.updated`, `step.passed` (`pending`), `offtrack` (status only), `status thinking`, `error`, all read from `core/lesson` (`notice`, `useThinking()`, `pendingNext`, `complete`, `connected`)
- **Out** (app → engine): none (clicking idle opens the launcher via `bridge.emit("launcher:toggle")`)

## Plugs in as
islandModes: idle (0), building (1), compact (2), notice (5: above the pill states, below hover 20 and cards 40+). The morphing container itself is core (`core/Island.tsx`)

## Done when
- Matches mockup 01 (size, type, ring, dot)
- The step-pass sequence feels like one gesture
- Off-track: the dot turns amber and pulses twice, calm
- Mac: hugs the notch (y = 6)
- Pass 2: notices show for ~5 s then return; thinking never looks dead; offline is visible and gray; a pending pass says the next part is building

## Test
`npm run dev:web -- --port 5174` → `http://localhost:5174/?scenario=pill` (or `?scenario=full`). Add `&engine=ws://127.0.0.1:9` while a mock server holds 8787 (Core request 3).

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_Status on core `be157ff`._

1. ✅ **Landing overshoot: fixed by core** (`justLanded` → `velocity: 0` on the first spring after a landing). Re-measured: 179 → ~298 at the landing → settles at 259, no balloon (was ~540).
2. **Notch shape (decide in pass 2). Placement is done: `pillTop 40` puts the pill under the notch.** Mockups 01 and 02 attach the island to the top edge, not as a free stadium. Measured in 01: flat top at y = 0, body 258×36, flaring to 278 at y = 0 (two small concave "ears"), bottom corners about 14pt round; mockup 02's card has the same attachment with about 24pt bottom corners. If adopted, in `core/Island.tsx` (`top`, `borderRadius`): `top` 0 on Mac, pill height 36, `borderRadius: isPill ? '0 0 14px 14px' : '0 0 24px 24px'`, plus the two inverse-corner ears.
3. **Stage: `?scenario=` is ignored when something listens on 8787. Still open on be157ff** (`bridge.ts:66`). A mock server on 8787 makes every agent's stage play that server's scenario instead of its own `?scenario=`. Suggest: when `?scenario=` is given explicitly, run inline. Workaround: append `&engine=ws://127.0.0.1:9`.
4. ✅ **Button fonts: fixed by core** (`@layer base`). The pill's idle button carries its own `text-[13px] font-medium` again (the inner-span workaround is gone).
5. ✅ **Mono tree: done by core differently.** `MiyagiMark` is now monochrome by default (`mono`, a white filter) and the tree is monochrome everywhere in the app, so "color when it opens" is dropped. The pill still uses its local `MonoMark` (same silhouette, `color.text` mask); switching it to `<MiyagiMark size={16} />` is a safe cleanup for the next pass (left out of pass 2 so every screenshot here matches the code).

## Notes
- **Ring = steps done / total** (computed in the pill), not core's `useProgress().fraction`, which also counts checks inside the step. With check-level progress the last check already fills the ring, so nothing moves visibly at the pass. Now the ring advances exactly one step on the spring at each pass.
- **The pill runs ahead of the engine after a pass.** At +560ms it shows the next step (`step.passed.nextStepId`, else the next entry in `lesson.steps`). In the mock, `step.started` for the next step arrives about 3.9s later. `step.started` then only confirms it (same key, no second crossfade). If the engine starts a different step, the pill crossfades to that one. If the engine is fast (`step.started` during the 560ms check), the check still finishes first (tested in `?scenario=pill`, step 2).
- **Dot color while watching:** settled by the brand: gray watching, amber off track, green passed (mockups 01 and 02 had it green).
- **Off-track pulse once per episode:** when `offtrack` arrives, the cards feature takes the island at once, so the pill isn't visible. The pulse plays when the pill comes back (Esc or ✕), not again on hover remounts.
- **Building:** keeps the last `lesson.building` message through `lesson.ready` (core clears it there), and the line fills to 100% on `lesson.ready`.
- **`island:size` traffic (FYI for core):** when the step text changes, the pill's text slot springs its width over about 300ms. The island re-measures on every frame, so `Island.tsx:63–65` emits `island:size` about 20 times per step change (IPC to main in Electron). This is harmless, but if it ever shows up, emit only when the size settles or while the launcher is closed.
- Generality rule: no PINN-specific UI strings in the pill ("Ask Miyagi", "Building your lesson", "Step N ·", "Lesson complete"). PINN only appears as mock data in `mock/scenarios/pill.json`.
- Reduced motion: `MotionConfig reducedMotion="user"` turns off the y offsets and the scale pulses. Crossfades, color changes and the width spring stay.
- **Mono tree:** `MonoMark` masks the small-cut SVG (`assets/brand/tree-small-dark.svg`) with `color.text`. It's 16px rather than 14, because at 16 the art is about 10.5×12, the optical size of mockup 01's icon, and it sits 15px from the edge and 11px before the text, as in the mockup (pad 13, gap 8). At 14 the tree read as a speck.
- **Slop check (Sat):** the pill has no gradients, glows, emoji, sparkles or purple. It uses one accent (white), the system font, and motion that only marks state changes. The tiny colored tree was the one thing that read as "generated"; it's now the white glyph. Building shows a spinner *and* a progress line on purpose: Adrian chose to keep both (the spinner shows it's alive during long steps, the line shows how far along it is).
- **Brand details:** the ring track is the accent at 22% opacity, like the Activity rings, so no new color. Building now mirrors compact: bonsai left, message, spinner where the ring will be. The check stroke is `color.island` on `color.green`. The ring closes in green only when the lesson is complete, which counts as passed.
- Own pieces in `features/pill/parts.tsx` (`PillRing`, `StatusMark`, `SwapText`, `BuildLine`), not the shared `core/ui/atoms` ones, because the pill sizes (16px ring, 7px dot) differ from the cards'.
- **Notice line:** its own island mode at priority 5, so it replaces whichever pill state is showing and the island springs to the line's width; a card the learner opened (40+) and the hover card (20) stay in front. The pill keeps the notice 5 s (`NOTICE_MS` in `store.ts`). A full reset (dev HUD) clears it; a lesson-scoped reset (reconnect, lesson ended) keeps it, because it may be the reason. Long lines truncate at 380px.
- **Offline:** `OFFLINE_GRACE_MS` 2 s. On reconnect, core resets the lesson (the engine snapshot refills it); the pill just follows.
- **Next part:** the pass moment runs as usual (check, ring, flash), then "Next part is still building" + spinner (the building pill's shape). The next step is looked up again when `lesson.updated` arrives, so the pill doesn't wait for `step.started`.
- **How to see it:** `http://localhost:5174/?scenario=pill&engine=ws://127.0.0.1:9` runs (about 55 s): idle → a build that fails (notice "Couldn't reach Gemini. Try again." for 5 s, back to idle) → a retry build (the timer tick doesn't animate) → step 1 with an error notice mid-step → step 2 with 2 s of thinking (spinner in place of the bonsai) → step 3 off-track (Esc to see the amber pulse) → step 4 passes with `pending` ("Next part is still building") → `lesson.updated` adds step 5 → "Lesson complete". Offline: in the console, `import('/src/core/lesson.ts').then(m => m.setConnected(false))`, wait 2 s. `?scenario=full&engine=ws://127.0.0.1:9`: Ctrl+K, type, Enter, Enter → step 4 passes at about +10s → step 6 goes off-track. HUD Reset restarts.
