# buddy

**Status:** pass 1 done (the living bonsai mark). Pass 2 built Nov 22 (the pointing branch): typecheck green, 37 offline tests, checked in the built stage; local, not pushed, not reviewed by Adrian. **Open:** it overlaps Michael's `features/annotate` (see Overlap) · **Priority:** P2 · **Branch:** `adrian/buddy` · **Stage port:** 5251 (launch config `buddy-stage`)

## Goal
miyagi gets a character without a mascot: the bonsai itself is the buddy (Michael, Nov 22). It stays sleek. It has no face, and its personality comes from motion. Pass 1 is the living mark that the notch ears use. Pass 2 is the branch that reaches out and points at the button or line to click. Later, the tree grows a leaf per mastered skill (see `app/agents/skills.md`).

## Owns
- `app/src/renderer/src/features/buddy/**`
  - `LivingMark.tsx`: `LivingMark` (props `size`, `state: idle | thinking`, `lean` from -1 to 1, `bloom` counter, `tone`, `level`) and `usePointerLean(ref, on, reach)`. It draws the same brand SVGs inline. `livingSvg()` wraps the canopy as lean > sway > bloom and tags the pads. The pot stays outside, so it never moves.
  - `buddy.css`: thinking sways ±2.4° about the trunk base (2.8 s). Lean is up to 6° on ease.out (0.35 s). Bloom swells each pad to 1.14 and back, 60 ms apart (0.56 s), and lifts the canopy 1.2px. Transform only. Reduced motion turns all of it off.
  - `store.tsx`: `useBuddy()` and `<Buddy />`. Thinking comes from `useThinking()`. Bloom counts real `step.passed` events; a Skip is never a pass. While a branch is out, `<Buddy />` leans toward what it points at.
  - Pass 2, the pointing branch:
    - `marks.ts` (pure): the engine's marks cleaned (`cleanMarks`: real numbers, one per id, 4 at most, labels cut to 4 words), the stroke (`reach`: one path, branch then loop), the fork for a second mark (`forkFor`), the label's place (`labelAt`), and the timing (`drawTime`, `timeToDraw`).
    - `pointing.ts`: `usePointing` (what is shown), `annotate(payload)`, and the lifetime rules. Subscribed to the bus for `annotate`, `step.started`, `step.passed`, `lesson.ready`, `lesson.ended`, reset and Esc.
    - `Reach.tsx`: the overlay layer `buddy-reach` (z 30: over the spotlight's dim, behind the island it grows out of).
    - `PointStage.tsx`: the try-out strip for the browser stage.
  - `Stage.tsx` + `index.tsx`: previews that show only in the browser stage. No app window.
- `app/mock/scenarios/buddy.json`: `annotate` events through the mock engine (one mark, a jittered re-send, two marks, a clear), on a loop.
- `app/test/buddyMarks.test.ts`: 37 offline tests for `marks.ts` and `pointing.ts`.

## How to use the mark (Michael wires the notch)
```tsx
import { Buddy, usePointerLean } from '../features/buddy'
const ref = useRef<HTMLSpanElement>(null)
const lean = usePointerLean(ref, hovered)          // hovered: the notch hover state
<span ref={ref}><Buddy size={16} lean={lean} /></span>   // in place of <MiyagiMark size={16} /> (core/Island.tsx:648)
```
In the click-through overlay, the lean needs mouse moves forwarded (`setIgnoreMouseEvents(true, { forward: true })`). Without them the tree simply stays upright.

## Pass 2: what the pointing branch does
It draws the engine's `annotate` event (Michael's contract, Nov 22, branch `claude/contract-circle-ask`): `{ marks: Annotation[]; holdMs? } | { clear: true }`, marks in screen points like `spotlight.rect`.
- **The stroke.** One path per mark in the bonsai's bark (`#A07A5C`, the brand kit's Bark on dark), 2.25 px over a faint ink keyline so it reads over a light app. It leaves the bonsai (the left ear when the ears are out, else inside the notch, else the left of the pill) heading down, bends to the mark, meets the loop a little past its nearest point, and goes once round with a little to spare. No glow, no gradient, no arrowhead.
- **The loop.** A superellipse walked at an even pace, with a small seeded wobble that only ever pushes outward, so it never cuts the target's corners. One line of code gets a loop that stays inside that line's own leading. By a screen edge the loop is pulled in so it stays on screen.
- **Several marks.** The first mark's branch is the trunk. A later mark forks off it where it can, starting as the trunk's stroke passes that point. A mark behind the trunk gets its own branch a beat later. Four marks at most.
- **The label.** Up to 4 words on an island-black chip, like the spotlight's caption. It takes the side away from the branch, then below, then the branch's side under the loop's top edge, and above last. Always on screen. Only the label is `data-ui`; the stroke is not, or the engine would stop reading what it points at.
- **Motion.** `pathLength` on `ease.out`, `duration.draw` plus time for the distance (1 s at most). Leaving, the stroke runs back and fades in `duration.slow`. Reduced motion: nothing travels, the stroke and label fade in place.
- **Lifetime.** A new annotate replaces the marks; a mark re-sent under the same id stays drawn (and keeps its place when it only jittered, under 8 px). Marks go after `holdMs` (default 5 s, kept between 1.2 and 30 s), on `{ clear: true }`, on a new step, when the lesson ends, on reset.
- **The learner.** Moving the pointer onto a mark from outside fades it 1.2 s later ("found it"). A press inside one, or Esc, sends them away at once. A mark the learner sent away stays gone while the engine re-sends the same one; a different mark, a new step or an engine clear ends that.
- **The tree.** While a branch is out, `<Buddy />` leans toward the first mark.

Borrowed from other pointing apps, in miyagi's own look: the travel is an arc and takes longer the farther it goes (Clicky's cursor flies that way: its arc height and flight time grow with distance), the short label at the target (Clicky's bubble, shared-cursor chips), the hold and then the return, and a new request replacing the old one. From circle-to-search: the loop is drawn on, not faded in, and its end overlaps its start.

## How to see it
Stage port 5251 (`npm run dev:web -- --port 5251`), or build it: `npx vite build --config vite.web.config.ts --base ./ --outDir <a folder outside the worktree>`.
- `?buddy=point&clean`: the try-out strip. One, Two, Answer, Far, Clear; or click anywhere on the desktop to point there. Click inside a mark to send it away.
- `?scenario=buddy&clean`: the same marks arriving as engine events through the bus.
- Add `&notch=below` for the pill under the menu bar.
- `?buddy`: every state of the living mark (pass 1).
- Shots: `shots/buddy-point-one.png`, `shots/buddy-point-two.png`, `shots/buddy-point-far.png`, `shots/buddy-stage.png`.

## Checked
- `npm run typecheck` passes. `test/buddyMarks.test.ts`: 37 of 37 pass.
- Built stage in headless Chrome (1600x1000): one mark, two marks forking, an unnamed answer mark, a far corner, the pill below the menu bar, frames mid-draw at 120 and 300 ms, the exit 110 ms after a clear, and a light backdrop.
- Same stage, by synthetic mouse and key events: a press points there; a pointer already on the mark does not fade it; leaving and coming back fades it between 0.9 and 1.7 s; a press inside clears it; Esc clears it and the same mark re-sent stays gone; a different mark shows; the strip's tree leans (`--lm-lean` 1).
- Reduced motion (emulated): the stroke is whole from its first frame and only fades in.
- `?scenario=buddy`: the mark arrives through the mock engine and the bus.
- Not checked: Electron on a Mac. The stroke over real apps, the pointer rule with forwarded mouse moves, the start point on a real notch, a second display, and a live engine sending `annotate`.

## Overlap (open, Adrian's and Michael's call)
Michael claimed "buddy draws" by email at 7:06 PM on Nov 22 and pushed `features/annotate` on `michael/app-buddy-draw` (commit from 6:57 PM): a mint stroke from the island's middle to a loop, also on `annotate`. This pass was started a few minutes before that commit, so neither side saw the other. Both layers subscribe to `annotate`: with both mounted, every mark gets two strokes. Only one may draw. Michael was told by email the same night (thread "miyagi: claiming circle-to-ask + buddy drawing on screen").
- His has, and this lacks: the spotlight bridge (today's spotlight boxes get a mark until the engine sends `annotate`), the root frozen at a mark's birth, and `'annotate'` in `common/wire.ts` KNOWN.
- This has, and his lacks: it starts from the living mark, forks for a second mark, leans the tree, fits loops to the screen edge and to one line of code. This stroke is bark; his is mint, with a BRAND.md exception he proposes on his branch.

## Next
- Settle the overlap, then push.
- Later: a leaf per mastered skill (Progress and Skills).

## Core requests
1. **The contract.** `annotate` and `Annotation` are on `claude/contract-circle-ask`, not on this branch. Until they land, `marks.ts` mirrors the type and `pointing.ts` casts `onMessage` to subscribe. Both go when the contract is merged.
2. **`common/wire.ts` KNOWN needs `'annotate'`**, or the app's parser drops the event in Electron (the browser stage's mock does not go through the parser, so it works there). Michael has this line in b3ffd388.
3. **A bark token.** `core/theme.ts` has no token for the brand kit's Bark (`#5A4433`, `#A07A5C` on dark). `Reach.tsx` holds the dark value as a local constant.
4. **A real click.** The overlay is click-through, so in Electron a click inside a mark never reaches this window. Main could broadcast a global left-mouse-down point (screen points); today the pointer coming onto the mark stands in for it.
5. If the ears should use the living mark everywhere, swap `MiyagiMark` for `Buddy` in `core/Island.tsx` (integrator). The branch then starts from a tree that leans with it.
