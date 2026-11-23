# app-buddy-draw

**Status:** first pass built, stage-checked only · **Port:** 5197 (free, not in ports.json) · **Branch:** `michael/app-buddy-draw`

## Goal
When the coach points at something, the buddy draws it. A thin mint line grows out of the island, curves down to the
target and ends in a loose hand-drawn loop around it. It holds, then fades when the learner goes there, the step
changes, or after 6 s. Michael asked for this on Nov 22 (like Clicky). It knowingly overrides the old BRAND.md line
"no hand-drawn annotations".

## Owns
- `app/src/renderer/src/features/annotate/` (overlay layer `annotate`, z 48, under the island)
  - `geometry.ts`: pure math. Global screen points to overlay points (multi-display offsets, negative ones too), the
    island anchor, the ring around a box, the seeded wobbly loop, the branch curve, the label spot.
  - `marks.ts`: pure mark rules. Validation (max 3 marks, labels cut to 4 words), keys (id, or nearly the same box),
    merge (a re-sent mark keeps its stroke and does not redraw), hold (holdMs within 1.5 to 30 s, default 6 s), and
    "went there" (createReach).
  - `geometry.test.ts`: 29 offline tests for both (`npx tsx --test src/renderer/src/features/annotate/geometry.test.ts`).
  - `store.ts`: engine `annotate` in, fades out. Also draws today's spotlight boxes until the engine sends its first
    annotate.
  - `BuddyLayer.tsx`: the SVG stroke, the optional label, the reach/click fade.
- `app/mock/scenarios/annotate.json`: no lesson, no video. A point mark with a label, a jittered re-send (must not
  redraw), then an answer mark after 30 s.

## Contract
- **In:** `annotate {marks, holdMs?} | {clear: true}` (shared/contracts/events.ts, cherry-picked from
  `claude/contract-circle-ask`). Also reads `spotlight` through the spotlight store (read-only).
- **Out:** nothing. The layer never takes the mouse (no `data-hit`). Only the small label is `data-ui`; the stroke is
  not, so the engine's screen reader still reads the circled text.

## Look and motion
- Stroke: `brand.pastel.mint` (the notch glow's mint), 2.25 pt, round caps, over a faint island-black casing (28%) so it
  reads on light and dark editors. Never green. No glow, blur or gradient.
- One path: the branch flows into the loop along the loop's own direction, so it draws as one line (pathLength,
  0.55 to 1.2 s by length, ease.out). The loop is a bit more than one turn and ends a little outside its start, like a
  hand-drawn circle. The wobble is seeded by the mark key, so the same mark always draws the same line.
- The branch's root is frozen when a mark is born, so a card growing out of the island later does not drag it.
- Reduced motion: no grow, the finished stroke fades in.
- Label (if the engine sends one): neutral text on a black chip under the loop (over it near the screen bottom).

## Fades when
- the learner goes there: a click inside (browser stage), or in Electron the pointer coming into the box from outside
  and resting 280 ms (the overlay is click-through and only gets forwarded mouse moves, never clicks). A cursor already
  resting where the learner circled does not fade the answer;
- holdMs (or 6 s) runs out; `annotate {clear: true}`; Esc;
- step.started (keeps only marks whose stepId is the new step), step.passed, lesson.ready, lesson.ended, reset.
A mark that faded stays gone for the rest of the step, even if the engine re-sends it.

## Test
`npm run dev:web -- --port 5197` then `http://localhost:5197/?scenario=annotate&clean` (add `&draw=slow` to draw 8x
slower, for screenshots). Click inside the circled line to fade it.
Shots: `agents/shots/app-buddy-draw-growing.png`, `agents/shots/app-buddy-draw-circled.png`.

## Unverified
- Nothing ran in Electron. Untested there: the stroke over real apps, the pointer-rest fade with forwarded mouse
  moves, the notch anchor on a real notch, marks on a second display (they are skipped when less than half is on the
  overlay's display, since the overlay only covers one display).
- Nothing ran against a live engine or model: no real `annotate` has been received. The spotlight bridge was only
  checked by typecheck and reading, not in the stage.
- Reduced motion was not checked in a browser (the Browser pane cannot emulate it here).
- The 30 s answer segment of the scenario was not watched.

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
4. ports.json: add `"app-buddy-draw": 5197` if you want it reserved.
