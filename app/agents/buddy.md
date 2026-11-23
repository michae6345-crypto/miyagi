# buddy

**Status:** pass 1 done (the living bonsai mark). Pass 2 built Nov 22 (the pointing branch) and lined up with Michael's `features/annotate` the same night: same mark rules, one stroke per mark, and the two hooks he asked for. Typecheck green, 49 offline tests, checked in the built stage alone and merged with his branches. Not run in Electron. **Open:** which of the two layers draws in the end, and the stroke's color (see With features/annotate) · **Priority:** P2 · **Branch:** `adrian/buddy` · **Stage port:** 5251 (launch config `buddy-stage`)

## Goal
miyagi gets a character without a mascot: the bonsai itself is the buddy (Michael, Nov 22). It stays sleek. It has no face, and its personality comes from motion. Pass 1 is the living mark that the notch ears use. Pass 2 is the branch that reaches out and points at the button or line to click. Later, the tree grows a leaf per mastered skill (see `app/agents/skills.md`).

## Owns
- `app/src/renderer/src/features/buddy/**`
  - `LivingMark.tsx`: `LivingMark` (props `size`, `state: idle | thinking`, `lean` from -1 to 1, `bloom` counter, `tone`, `level`) and `usePointerLean(ref, on, reach)`. It draws the same brand SVGs inline. `livingSvg()` wraps the canopy as lean > sway > bloom and tags the pads. The pot stays outside, so it never moves.
  - `buddy.css`: thinking sways ±2.4° about the trunk base (2.8 s). Lean is up to 6° on ease.out (0.35 s). Bloom swells each pad to 1.14 and back, 60 ms apart (0.56 s), and lifts the canopy 1.2px. Transform only. Reduced motion turns all of it off.
  - `store.tsx`: `useBuddy()` and `<Buddy />`. Thinking comes from `useThinking()`. Bloom counts real `step.passed` events; a Skip is never a pass. While something is pointed at, `<Buddy />` leans toward it.
  - Pass 2, the pointing branch:
    - `marks.ts` (pure): the mark rules (`validMarks`, `keyOf`, `mergeMarks`, `holdFor`, `fadeAt`, `createReach`), the stroke (`reach`: one path, branch then loop), the fork for a second mark (`forkFor`), the label's place (`labelAt`), and the timing (`drawTime`, `timeToDraw`).
    - `pointing.ts`: `usePointing` (what is shown, the lean, the pose), `annotate(payload)`, `fade`, `forget`, `pointAt`. Subscribed to the bus for `annotate`, `step.started`, `step.passed`, `lesson.ready`, `lesson.ended`, reset and Esc.
    - `Reach.tsx`: the overlay layer `buddy-reach` (z 30: over the spotlight's dim, behind the island it grows out of), and `useBonsaiPoint`.
    - `PointStage.tsx`: the try-out strip for the browser stage.
  - `Stage.tsx` + `index.tsx`: previews that show only in the browser stage. No app window.
- `app/mock/scenarios/buddy.json`: `annotate` events through the mock engine (one mark, a jittered re-send, two marks, a clear).
- `app/test/buddyMarks.test.ts`: 49 offline tests for `marks.ts` and `pointing.ts`.

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
- **Several marks.** The first mark's branch is the trunk. A later mark forks off it where it can, starting as the trunk's stroke passes that point. A mark behind the trunk gets its own branch a beat later.
- **The label.** Up to 4 words on an island-black chip, like the spotlight's caption. It takes the side away from the branch, then below, then the branch's side under the loop's top edge, and above last. Always on screen. Only the label is `data-ui`; the stroke is not, or the engine would stop reading what it points at.
- **Motion.** `pathLength` on `ease.out`, `duration.draw` plus time for the distance (1 s at most). Leaving, the stroke runs back and fades in `duration.slow`. Reduced motion: nothing travels, the stroke and label fade in place.
- **The tree.** While something is pointed at, `<Buddy />` leans toward it.

### The mark rules (the same as `features/annotate`, number for number)
Michael's engine is written against his `features/annotate/marks.ts` and `store.ts`. `marks.ts` and `pointing.ts` here follow them exactly, so a mark lives and dies the same way whichever layer draws it. Change them together.
- 3 marks at most. A mark needs `why` "point" or "answer" and a real box. Labels are cut to 4 words.
- A mark is known by its id, or (no id) by its kind and nearly the same box (12 px). A known mark re-sent keeps its stroke, and its place when it only jittered.
- A new annotate replaces the drawn set. The hold is `holdMs` kept between 1.5 and 30 s, or 6 s, counted from the newest mark's birth: a re-send does not restart it, a new mark does.
- A mark that faded stays gone for the rest of the step, however it went (reached, timed out, Esc, `{ clear: true }`), even if it is re-sent. A new `askId` starts fresh.
- "Went there": the pointer coming into the mark's box (6 px bigger) from outside and resting 280 ms fades that mark, and only that one. So does a press inside it. A pointer already resting there when the mark appears does not.
- `step.started` (not a `replay`) keeps only the marks sent with that `stepId` and forgets what was gone. `step.passed`, `lesson.ready`, `lesson.ended` and a reset clear everything.
- Draw a mark only when at least half of its box is on this display.
- Not here: his bridge that also circles today's spotlight boxes until the engine sends its first annotate.

Borrowed from other pointing apps, in miyagi's own look: the travel is an arc and takes longer the farther it goes (Clicky's cursor flies that way: its arc height and flight time grow with distance), the short label at the target (Clicky's bubble, shared-cursor chips), the hold and then the return, and a new request replacing the old one. From circle-to-search: the loop is drawn on, not faded in, and its end overlaps its start.

## With features/annotate (Michael's layer)
Michael claimed "buddy draws" by email at 7:06 PM on Nov 22 and pushed `features/annotate` on `michael/app-buddy-draw`: a mint stroke from the island's middle to a loop, also on `annotate`. This pass was started a few minutes before his commit, so neither side saw the other. He was told by email that night (thread "miyagi: claiming circle-to-ask + buddy drawing on screen"). The two now fit together:
- **One stroke per mark.** While `features/annotate` is mounted, `Reach.tsx` draws nothing (`STAND_DOWN_FOR`), so the branches can merge in either order. With his layer present, his stroke draws and this feature only leans the tree. Without it, this one draws. Which one draws in the end is that one constant.
- **What he asked the buddy to expose** ("its position or a point pose"):
  - `useBonsaiPoint(ref, layout, on)`: where the living mark is, in the overlay window's coordinates, for a branch to start from. `ref` is any direct child of the overlay root.
  - `pointAt(box?)`: the point pose. The tree leans toward the box (screen points) until `pointAt()` with nothing. Marks from `annotate` lean the tree on their own, so this is for anything else his layer circles (a bridged spotlight box).
- **Same rules** (above), so the engine sees one behavior.
- **Still different, and open:**
  - The color. This stroke is bark, the tree's own branch. His is `brand.pastel.mint`, and his branch adds a BRAND.md exception that names mint and `features/annotate` as the one allowed stroke. Brand rules are Adrian's to change.
  - His has the spotlight bridge and the root frozen at a mark's birth; this one starts from the living mark, forks for a second mark, and fits loops to one line of code and to the screen edge.

Checked merged with his branches (`michael/app-buddy-draw` c0841b36 and `michael/app-circle-ask` 622018dd, its fix round 2, on top of this branch, a throwaway merge that was not pushed): no conflict with this feature's files; typecheck passes; these 49 tests and his 34 pass; in the built stage his layer draws each mark once and this one draws none, for `?scenario=buddy`, `?scenario=annotate` and the try-out strip; the strip's tree leans with his stroke. The only conflict in that merge is between his own two branches, in `app/agents/ports.json` (each adds its port on the same line).

## How to see it
Stage port 5251 (`npm run dev:web -- --port 5251`), or build it: `npx vite build --config vite.web.config.ts --base ./ --outDir <a folder outside the worktree>`.
- `?buddy=point&clean`: the try-out strip. One, Two, Answer, Far, Clear; or click anywhere on the desktop to point there. Rest the pointer on a mark, or click inside it, to send it away. The strip sends real `annotate` events through the bus.
- `?scenario=buddy&clean`: marks arriving from the mock engine.
- Add `&notch=below` for the pill under the menu bar.
- `?buddy`: every state of the living mark (pass 1).
- Shots: `shots/buddy-point-one.png`, `shots/buddy-point-two.png`, `shots/buddy-point-far.png`, `shots/buddy-stage.png`.

## Checked
- `npm run typecheck` passes. `test/buddyMarks.test.ts`: 49 of 49 pass. The full suite has one failure, `linkHost.test.ts` (a drawer test that reads only drawer files; untouched here).
- Built stage in headless Chrome (1600x1000): one mark, two marks forking, an unnamed answer mark, a far corner, the pill below the menu bar, frames mid-draw at 120 and 300 ms, the exit 110 ms after a clear, and a light backdrop.
- Same stage, by synthetic mouse and key events: a press points there; a pointer already on the mark does not fade it; leaving, coming back and resting fades it (still there at 150 ms, gone by 800 ms); a press inside clears it; Esc clears it; with two marks, reaching the first leaves the second; the strip's tree leans (`--lm-lean` 1) and stands back up after a clear.
- Reduced motion (emulated): the stroke is whole from its first frame and only fades in.
- `?scenario=buddy`: the mark arrives through the mock engine and the bus, goes 4 s after its birth although it was re-sent in between, then two marks show.
- Not checked: Electron on a Mac. The stroke over real apps, the pointer rule with forwarded mouse moves, the start point on a real notch, a second display, and a live engine sending `annotate`.

## Next
- Adrian and Michael pick which layer draws, and the stroke's color.
- Later: a leaf per mastered skill (Progress and Skills).

## Core requests
1. **The contract.** `annotate` and `Annotation` are on `claude/contract-circle-ask`, not on this branch. Until they land, `marks.ts` mirrors the type and `pointing.ts` casts `onMessage` to subscribe. Both go when the contract is merged.
2. **`common/wire.ts` KNOWN needs `'annotate'`**, or the app's parser drops the event in Electron (the browser stage's mock does not go through the parser, so it works there). Michael has this line in b3ffd388 on `michael/app-buddy-draw`.
3. **A bark token.** `core/theme.ts` has no token for the brand kit's Bark (`#5A4433`, `#A07A5C` on dark). `Reach.tsx` holds the dark value as a local constant.
4. **A real click.** The overlay is click-through, so in Electron a click inside a mark never reaches this window. Main could broadcast a global left-mouse-down point (screen points); today the pointer resting on the mark stands in for it. Michael asks for the same thing in `agents/app-buddy-draw.md`.
5. If the ears should use the living mark everywhere, swap `MiyagiMark` for `Buddy` in `core/Island.tsx` (integrator). The branch then starts from a tree that leans with it.
