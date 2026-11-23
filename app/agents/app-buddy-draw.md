# app-buddy-draw

**Status:** fix round 1 done, offline tests only · **Port:** 5197 (in ports.json) · **Branch:** `michael/app-buddy-draw`

## Goal
When the coach points at something, the buddy draws it. A thin mint line grows out of the island, curves down to the
target and ends in a loose hand-drawn loop around it. It holds, then fades when the learner goes there, the step
changes, or after 6 s. Michael asked for this on Nov 22 (like Clicky). BRAND.md now allows exactly this stroke ("The
buddy stroke, Nov 22", and rule 6 points to it).

## Owns
- `app/src/renderer/src/features/annotate/` (overlay layer `annotate`, z 48, under the island)
  - `geometry.ts`: pure math. Global screen points to overlay points (multi-display offsets, negative ones too), the
    island anchor, the ring around a box, the seeded wobbly loop, the branch curve, the label spot.
  - `marks.ts`: pure mark rules. Validation (max 3 marks, labels cut to 4 words), keys (id, or nearly the same box),
    merge (a re-sent mark keeps its stroke and does not redraw), hold (holdMs within 1.5 to 30 s, default 6 s,
    counted from the newest mark's birth so a re-send does not restart it), and "went there" (createReach).
  - `geometry.test.ts`: 34 offline tests for both (`npx tsx --test src/renderer/src/features/annotate/geometry.test.ts`).
  - `store.ts`: engine `annotate` in, fades out. Also draws today's spotlight boxes until the engine sends its first
    annotate: the bridged mark goes when the spotlight hides (a clear, or its app left the front), and a Show me press
    draws its box again even if the learner already reached it this step.
  - `BuddyLayer.tsx`: the SVG stroke, the optional label, the reach/click fade.
- `app/mock/scenarios/annotate.json`: no lesson, no video. A point mark with a label, a jittered re-send (must not
  redraw), then an answer mark after 30 s.

## Contract
- **In:** `annotate {marks, holdMs?} | {clear: true}` (shared/contracts/events.ts, cherry-picked from
  `claude/contract-circle-ask`). Also reads `spotlight` through the spotlight store (read-only).
- **Out:** nothing. The layer never takes the mouse (no `data-hit`). Only the small label is `data-ui` (so the engine
  never reads miyagi's own words as the learner's screen); the stroke is not, so the engine's screen reader still reads
  the circled text. Because the text under the label is hidden from the reader, the label sits beside the loop.

## Look and motion
- Stroke: `brand.pastel.mint` (the notch glow's mint), 2.25 pt, round caps, over a faint island-black casing (28%) so it
  reads on light and dark editors. Never green. No glow, blur or gradient.
- One path: the branch flows into the loop along the loop's own direction, so it draws as one line (pathLength,
  0.55 to 1.2 s by length, ease.out). The loop is a bit more than one turn and ends a little outside its start, like a
  hand-drawn circle. The wobble is seeded by the mark key, so the same mark always draws the same line.
- The branch's root is frozen when a mark is born, so a card growing out of the island later does not drag it.
- Reduced motion: no grow, the finished stroke fades in.
- The branch's last control point reaches back at most 90 pt from the join, so the curve does not swing past the
  join and hook back (the J over the line above, seen in the first shots).
- Label (if the engine sends one): neutral text on a black chip beside the loop, on the circled line (right, else
  left); under the loop (over it near the bottom) only when neither side fits.

## Fades when
- the learner goes there: a click inside (browser stage), or in Electron the pointer coming into the box from outside
  and resting 280 ms (the overlay is click-through and only gets forwarded mouse moves, never clicks). A cursor already
  resting where the learner circled does not fade the answer;
- holdMs (or 6 s) runs out, counted from the newest mark's birth (a re-send of the same id does not restart it);
  `annotate {clear: true}`; Esc;
- today's bridge: the spotlight hides (it may draw again when it comes back);
- step.started (keeps only marks whose stepId is the new step), step.passed, lesson.ready, lesson.ended, reset.
A mark that faded stays gone for the rest of the step, even if the engine re-sends it. Exception: a Show me press that
brings a new spotlight box draws it again.

## Test
`npm run dev:web -- --port 5197` then `http://localhost:5197/?scenario=annotate&clean` (add `&draw=slow` to draw 8x
slower, for screenshots). Click inside the circled line to fade it.
Shots: `agents/shots/app-buddy-draw-circled.png` (re-shot in fix round 1: label beside the loop, no J hook; port 5197
was busy with another worktree, so that run used a free listed port), `agents/shots/app-buddy-draw-growing.png` (first
pass, label under the loop).

## Unverified
- Nothing ran in Electron. Untested there: the stroke over real apps, the pointer-rest fade with forwarded mouse
  moves, the notch anchor on a real notch, marks on a second display (they are skipped when less than half is on the
  overlay's display, since the overlay only covers one display).
- Nothing ran against a live engine or model: no real `annotate` has been received. The spotlight bridge was only
  checked by typecheck and reading, not in the stage.
- Reduced motion was not checked in a browser (the Browser pane cannot emulate it here).
- The 30 s answer segment of the scenario was not watched.
- Fix round 1: the circled shot was re-taken (no console errors); the spotlight-hide fade and Show me redraw were
  checked by offline tests and reading, not in the stage.
- Show me again: if the engine re-sends the very same spotlight (same box and caption), the spotlight store keeps its
  old target object and nothing redraws; only a new target object (new caption, or after a clear) does.

## Core requests
1. **Done in its own commit (one line):** `common/wire.ts` KNOWN gets `'annotate'`, or the app parser drops the
   event in Electron. Same shape as `screen.avoid`.
2. **Import cycle (not changed):** `core/islandPlace.ts` imports `features/cards/store`, and cards/store ->
   cards/panel -> drawer/store -> diagrams/store -> cards/store is a cycle that only works when the drawer store loads
   first. This feature loads first (A to Z) and uses `core/Island` (useIslandBox), so entering from cards crashed the
   whole renderer ("Cannot access 'useCards' before initialization"). Workaround: `annotate/index.tsx` imports
   `../drawer/store` first, and the spotlight bridge in store.ts is a late `import()`. Please break the cycle in core.
3. **Optional, for an exact "clicked there":** main could broadcast a global left-mouse-down point (screen points) to
   the overlay. Today the fade uses pointer rest as the stand-in.
4. ~~ports.json~~: done, `"app-buddy-draw": 5197`.
