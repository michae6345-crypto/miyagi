# pill

**Status:** pass 1 + Miyagi brand pass done, waiting on Adrian's review · **Priority:** P0 · **Port:** 5174 · **Branch:** `adrian/pill`

- ✅ Matches mockup 01: measured spacing, type, ring and dot (`shots/pill-vs-mockup.png`). Idle and building polished; building has a progress line.
- ✅ The step-pass moment is one gesture: check draws → ring advances → flash → text crossfades to the next step at 560ms (`shots/pill-step-pass.png`).
- ✅ Off-track: the dot eases to amber and pulses twice (scale beats only, no glow or halo), once per episode (`shots/pill-brand-offtrack.png`).
- ✅ Last step: "Lesson complete" with the ring closed in green.
- ✅ **Black-and-white pill, color when it opens** (Adrian, Sat): the bonsai in the pill is a one-color template glyph (white on black, like a menu-bar icon), because the tiny two-tone tree read like an emoji. The launcher that grows out of the pill shows it in color (`shots/pill-brand-opens-color.png`). The hover card doesn't show the tree yet (see Core requests 5).
- ✅ Miyagi brand (core db72ef9): the bonsai replaces the sparkle in idle, building and compact; idle says "Ask Miyagi ⌥Space"; white ring, spinner and build line (`color.accent`); green only at the pass, amber only off track, gray watching; no glows; colors from tokens only (`shots/pill-brand-states.png`, `pill-brand-step-pass.png`, `pill-brand-offtrack.png`).
- ✅ Mac notch: core now places the pill just under the notch (`pillTop 40`), which settles the demo risk in Core requests 2.
- ✅ On `adrian/shell` 02566bc (launcher brand pass merged). Pass-1 commits are already merged there (701aa06).
- ❌ Not seen in Electron (Windows). Checked in headless Chrome at 1600×1000 (the Browser pane was hidden).

## Goal
The Dynamic-Island pill hugging the notch: idle ("Ask Miyagi ⌥Space"), building (spinner + the `lesson.building` message), and during a lesson "Step 4 · Define the residual" with a progress ring and status dot (gray watching · amber off-track · green passed). Owns **the step-pass moment**: the checkmark draws, the ring advances, the pill flashes green, the text crossfades to the next step, the video resumes 400ms later.

## Owns
- `app/src/renderer/src/features/pill/`

## Contract
- **In** (engine → app): `lesson.building`, `lesson.ready`, `step.started`, `check.updated`, `step.passed`, `offtrack` (status only), all read from `core/lesson`
- **Out** (app → engine): none (clicking idle opens the launcher via `bridge.emit("launcher:toggle")`)

## Plugs in as
islandModes: idle (0), building (1), compact (2). The morphing container itself is core (`core/Island.tsx`)

## Done when
- Matches mockup 01 (size, type, ring, dot)
- The step-pass sequence feels like one gesture
- Off-track: the dot turns amber and pulses twice, calm
- Mac: hugs the notch (y = 6)

## Test
`npm run dev:web -- --port 5174` → `http://localhost:5174/?scenario=pill` (or `?scenario=full`). Add `&engine=ws://127.0.0.1:9` while a mock server holds 8787 (Core request 3).

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_Written against core `02566bc`._

1. **Landing overshoot (bug, signature transition). Still there on db72ef9 (same code).** In `core/Island.tsx:93–97`, on `pill:receive` (`:33`) the width snaps to `pill.landingWidth` with `transition={{ duration: 0 }}`. That one-frame jump leaves the width motion value with a large velocity. The next `springOut` inherits it, so the island balloons before settling. Measured on 660f238 every 40ms after landing: 300 → 520 → 538 → 478 → 387 → 320 → 285 → 262 → 243. It shows as a ~540pt black bar right after the launcher lands (`shots/pill-landing-overshoot.png`, frames +560 to +622ms).
   *Fix:* drive width and height with `useMotionValue`, call `width.jump(pill.landingWidth)` and `height.jump(pill.height)` in the `pill:receive` handler (`jump` resets velocity), then `animate(width, size.w, springOut)` as now. Minimal alternative: add `velocity: 0` to the transition, but only for the first animation after landing (a `justLanded` ref, cleared on the next size change). Using `velocity: 0` on every retarget would make the island stutter while it follows the pill's growing text slot.
2. **Notch shape (decide in pass 2). Placement is done: `pillTop 40` puts the pill under the notch.** Mockups 01 and 02 attach the island to the top edge, not as a free stadium at y = 6. Measured in 01: flat top at y = 0, body 258×36, flaring to 278 at y = 0 (two small concave "ears"), bottom corners about 14pt round. Mockup 02's card has the same attachment with about 24pt bottom corners. This matters more now that every surface is born from the island, since the launcher grows out of whatever shape the island has. If adopted, in `core/Island.tsx:81` (`top`) and `:95` (`borderRadius`): `top` 0 on Mac, pill height 36, `borderRadius: isPill ? '0 0 14px 14px' : '0 0 24px 24px'`, plus the two inverse-corner ears.
3. **Stage: `?scenario=` is ignored when something listens on 8787. Unchanged on db72ef9.** `bridge.ts:66–69` tries `ws://localhost:8787` first. Right now `npm run mock happy` from `repo/app` is running there, so every agent's stage silently plays *that* server's scenario instead of its own `?scenario=`. Suggest: when `?scenario=` is given explicitly, skip the socket and run inline. Workaround: append `&engine=ws://127.0.0.1:9` (dead port → inline mock after 900ms).
4. **Every `<button>` ignores its Tailwind font size and weight (affects all features).** `styles.css:47–48` has an unlayered `button { font: inherit }`. Tailwind v4 utilities live in `@layer utilities`, and unlayered CSS beats layered CSS, so `text-[14px] font-semibold` on a button does nothing: it renders at the body's 16px / 400. Measured in the stage: the cards' "Explain" and "Apply fix" (`CardButton`, `text-[14px] font-semibold`) compute to 16px/400, and so did the pill's idle label until I moved the type onto an inner span. *Fix:* wrap the reset in `@layer base { button { font: inherit; color: inherit; } }`.
5. **Black-and-white tree in the pill; color once the island opens (Adrian's call).** (a) `core/ui/Mark.tsx`: add `tone: 'mono'`, which renders the cut's SVG as a CSS mask filled with `currentColor` (no redraw), so the pill can drop its local `MonoMark` (`features/pill/parts.tsx`) and use the shared component. (b) `app/brand/BRAND.md` → Logo, Don't: allow the one-color template version in the notch pill only (it currently says "recolor the pads" is a don't). (c) **overview** (hover card, `features/overview/`): put `<MiyagiMark size={16} />` (color) in the top-left of the card header, where the pill's white tree sits, so hovering visibly opens the black-and-white pill into color. The launcher already does this (`Launcher.tsx:429`, color tree in the input).

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
- **How to see it:** `http://localhost:5174/?scenario=pill&engine=ws://127.0.0.1:9` runs idle → building → steps 1–2 pass on their own → step 3 off-track (Esc to see the amber pulse) → step 4 → "Lesson complete" in about 35s. `?scenario=full&engine=ws://127.0.0.1:9`: Ctrl+K, type, Enter, Enter → step 4 passes at about +10s → step 6 goes off-track. HUD Reset restarts.
