# buddy

**Status:** pass 1 done: the living bonsai mark (idle, thinking, hover lean, pass bloom); typecheck green; checked in the built stage (`?buddy`) · **Priority:** P2 · **Branch:** `adrian/buddy`

## Goal
miyagi gets a character without a mascot: the bonsai itself is the buddy (Michael, Nov 22). It stays sleek. It has no face, and its personality comes from motion. Pass 1 is the living mark that the notch ears use. Pass 2 is the branch that reaches out and points at the button or line to click. Later, the tree grows a leaf per mastered skill (see `app/agents/skills.md`).

## Owns
- `app/src/renderer/src/features/buddy/**`
  - `LivingMark.tsx`: `LivingMark` (props `size`, `state: idle | thinking`, `lean` from -1 to 1, `bloom` counter, `tone`, `level`) and `usePointerLean(ref, on, reach)`. It draws the same brand SVGs inline. `livingSvg()` wraps the canopy as lean > sway > bloom and tags the pads. The pot stays outside, so it never moves.
  - `buddy.css`: thinking sways ±2.4° about the trunk base (2.8 s). Lean is up to 6° on ease.out (0.35 s). Bloom swells each pad to 1.14 and back, 60 ms apart (0.56 s), and lifts the canopy 1.2px. Transform only. Reduced motion turns all of it off.
  - `store.tsx`: `useBuddy()` and `<Buddy />`. Thinking comes from `useThinking()`. Bloom counts real `step.passed` events; a Skip is never a pass.
  - `Stage.tsx` + `index.tsx`: a preview that shows only in the browser stage with `?buddy`. No app window.

## How to use it (Michael wires the notch)
```tsx
import { Buddy, usePointerLean } from '../features/buddy'
const ref = useRef<HTMLSpanElement>(null)
const lean = usePointerLean(ref, hovered)          // hovered: the notch hover state
<span ref={ref}><Buddy size={16} lean={lean} /></span>   // in place of <MiyagiMark size={16} /> (core/Island.tsx:648)
```
In the click-through overlay, the lean needs mouse moves forwarded (`setIgnoreMouseEvents(true, { forward: true })`). Without them the tree simply stays upright.

## Checked
- `npm run typecheck` passes.
- Built stage (`vite build --config vite.web.config.ts`, opened with `?buddy`), sampled with computed styles: thinking rotates over time, idle stays still, lean is exactly ±6°, bloom pads go to 1.14 and back on each new value, 3 pads per mark, and the pot is not in the canopy. Screenshot: `shots/buddy-stage.png`.
- Not checked: Electron on a Mac (Michael), or the 16px ears in the real notch.

## Next
- Pass 2: the pointing branch. A branch grows out of the ear toward a screen rect (the spotlight target), its tip lands near the target, and it retracts when the step passes. It needs the target rect from the spotlight feature.
- Later: a leaf per mastered skill (Progress and Skills).

## Core requests
- None. If the ears should use it everywhere, swap `MiyagiMark` for `Buddy` in `core/Island.tsx` (integrator).
