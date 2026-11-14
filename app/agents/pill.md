# pill

**Status:** pass 1 done, waiting on Adrian's review · **Priority:** P0 · **Port:** 5174 · **Branch:** `adrian/pill`

- ✅ Matches mockup 01: measured spacing, type, ring and dot (`shots/pill-vs-mockup.png`). Idle and building polished; building has a progress line.
- ✅ The step-pass moment is one gesture: check draws → ring advances → flash → text crossfades to the next step at 560ms (`shots/pill-step-pass.png`).
- ✅ Off-track: the dot eases to amber and pulses twice with soft halos, once per episode (`shots/pill-offtrack.png`).
- ✅ Last step: "Lesson complete" with the ring closed in green.
- ⚠️ Mac notch: placed at y = 6 by core, but see Core requests 2 (the mockups attach the island to the top edge, and a physical notch would hide the text).
- ❌ Not seen in Electron (Windows). Checked in headless Chrome at 1600×1000 (the Browser pane was hidden).

## Goal
The Dynamic-Island pill hugging the notch: idle ("Learn anything ⌥Space"), building (spinner + the `lesson.building` message), and during a lesson "Step 4 · Define the residual" with a progress ring and status dot (gray watching · amber off-track · green passed). Owns **the step-pass moment**: the checkmark draws, the ring advances, the pill flashes green, the text crossfades to the next step, the video resumes 400ms later.

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
`npm run dev:web -- --port 5174` → `http://localhost:5174/?scenario=full` (or `?scenario=pill` once you add `mock/scenarios/pill.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
1. **Landing overshoot (bug, signature transition).** `core/Island.tsx:80–84`: on `pill:receive` the width snaps to `pill.landingWidth` with `transition={{ duration: 0 }}`. That one-frame jump leaves the width motion value with roughly 2300 px/s of velocity. The next `springOut` inherits it, so the island balloons before settling. Measured every 40ms after landing: 300 → 573 → 594 → 518 → 416 → 332 → 290 → 264 → 243. It shows as a ~590pt black bar right after the launcher lands (`shots/pill-landing-overshoot.png`, frames +508 to +635ms).
   *Fix:* drive width and height with `useMotionValue`, call `width.jump(pill.landingWidth)` and `height.jump(pill.height)` in the `pill:receive` handler (`jump` resets velocity), then `animate(width, size.w, springOut)` as now. Minimal alternative: add `velocity: 0` to the transition, but only for the first animation after landing (a `justLanded` ref, cleared on the next size change). Using `velocity: 0` on every retarget would make the island stutter while it follows the pill's growing text slot.
2. **Notch shape and placement (decide in pass 2).** Mockups 01 and 02 attach the island to the top edge, not as a free stadium at y = 6. Measured in 01: flat top at y = 0, body 258×36, flaring to 278 at y = 0 (two small concave "ears"), bottom corners about 14pt round. Mockup 02's card has the same attachment with about 24pt bottom corners. If adopted, in `core/Island.tsx:69,82`: `top` 0 on Mac, pill height 36, `borderRadius: isPill ? '0 0 14px 14px' : '0 0 24px 24px'`, plus the two inverse-corner ears.
   **Demo risk:** if Michael's Mac has a physical notch (about 185×32pt at the top center), the middle of the text is hidden behind it either way. Then place the pill below the notch (`workArea.y`, about 38 on notched Macs), or widen it and put the content beside the notch. Please check which Mac the demo runs on.
3. **Stage: `?scenario=` is ignored when something listens on 8787.** `bridge.ts:66–69` tries `ws://localhost:8787` first. Right now `npm run mock happy` from `repo/app` is running there, so every agent's stage silently plays *that* server's scenario instead of its own `?scenario=`. Suggest: when `?scenario=` is given explicitly, skip the socket and run inline. Workaround: append `&engine=ws://127.0.0.1:9` (dead port → inline mock after 900ms).

## Notes
- **Ring = steps done / total** (computed in the pill), not core's `useProgress().fraction`, which also counts checks inside the step. With check-level progress the last check already fills the ring, so nothing moves visibly at the pass. Now the ring advances exactly one step on the spring at each pass.
- **The pill runs ahead of the engine after a pass.** At +560ms it shows the next step (`step.passed.nextStepId`, else the next entry in `lesson.steps`). In the mock, `step.started` for the next step arrives about 3.9s later. `step.started` then only confirms it (same key, no second crossfade). If the engine starts a different step, the pill crossfades to that one. If the engine is fast (`step.started` during the 560ms check), the check still finishes first (tested in `?scenario=pill`, step 2).
- **Dot color while watching:** mockups 01 and 02 show it **green** during a step in progress. The handoff spec says gray watching / amber off-track / green passed. I followed the spec. Adrian: pick one in pass 2. It's one line in `features/pill/parts.tsx` (`tone`).
- **Off-track pulse once per episode:** when `offtrack` arrives, the cards feature takes the island at once, so the pill isn't visible. The pulse plays when the pill comes back (Esc or ✕), not again on hover remounts.
- **Building:** keeps the last `lesson.building` message through `lesson.ready` (core clears it there), and the line fills to 100% on `lesson.ready`.
- Reduced motion: `MotionConfig reducedMotion="user"` turns off the y offsets and the scale pulses. Crossfades, color changes and the width spring stay.
- Own pieces in `features/pill/parts.tsx` (`PillRing`, `StatusMark`, `SwapText`, `BuildLine`), not the shared `core/ui/atoms` ones, because the pill sizes (16px ring, 7px dot) differ from the cards'.
- **How to see it:** `http://localhost:5174/?scenario=pill&engine=ws://127.0.0.1:9` runs idle → building → steps 1–2 pass on their own → step 3 off-track (Esc to see the amber pulse) → step 4 → "Lesson complete" in about 35s. `?scenario=full&engine=ws://127.0.0.1:9`: Ctrl+K, type, Enter, Enter → step 4 passes at about +10s → step 6 goes off-track. HUD Reset restarts.
