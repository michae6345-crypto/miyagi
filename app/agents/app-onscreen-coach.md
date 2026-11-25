# app-onscreen-coach

**Status:** first pass done (Nov 24), offline tests + headless stage shots only · **Port:** 5205 (in ports.json) ·
**Branch:** `michael/app-onscreen-coach` (base `origin/michael/v2-integration`) · **Claim PR:** #271 (draft into `adrian/shell`)

## Goal
Michael: "see and circle stuff on screen and type there; it would remove the complexity of the interface on the side".
In an app lesson (lesson.ready `lesson.app`: Blender, AutoCAD, Photoshop...), the buddy circles the target on screen
and writes the step's action (plus its keycaps) right beside the circle. The lesson drawer starts collapsed to the
island; the steps list stays one click away (the Mini pill).

## Owns
- `app/src/renderer/src/features/annotate/` (shared with app-buddy-draw; every change here is additive)
  - `marks.ts`: `OnscreenFields` (local defensive type), `cleanText` (12 words), `cleanKeys` (strings only, 1-12 chars,
    at most 3), `DrawMark.text / keys`, `timedMarks`. `mergeMarks` carries text and keys on "point" marks only; a re-send
    with new text updates it in place (same key and birth, so the stroke does not redraw). Keys need text.
  - `store.ts`: a text mark has no hold timer (holdMs ignored for it). It goes on step.passed, step.started for another
    stepId (kept for the same stepId), lesson.ended, a non-replay lesson.ready, Esc, annotate {clear}, a replacing
    annotate, or the learner reaching it (createReach). Marks without text keep the 6 s default. A replayed
    lesson.ready no longer wipes the drawn marks (it is the same lesson).
    Reached or dismissed marks stay gone this step against a bare re-send, but an explicit ask brings them back
    (review round 1): a Show me press ("where?"), or a `card` with verdict `not_done` for the current stepId ("Not yet").
    The next annotate after the ask runs `askAgain` on its marks (they are born again, with their text). If the
    engine's re-send came before the "Not yet" card (skipped as gone), the card draws it again itself. The panel is
    collapsed in app lessons, so this is the learner's only pointing.
  - `geometry.ts`: pure `textSpot(ring, target, size, box, branch?)`: right of the loop, else left, below, above
    (LABEL_GAP from it); never over the target or the loop's box; 16 pt inside the display; slides along the loop to
    stay 10 pt off the buddy's line; when no side fits, the side covering least of the loop with the target uncovered.
    Also `buddyPath().branch` (the sampled line) and `segmentHitsRect` / `lineHitsRect`.
  - `BuddyLayer.tsx`: `TextBox`, one box beside the loop for a mark with text, replacing the 4-word label. `data-ui`
    (the engine's OCR ignores it), never `data-hit`, click-through. The instruction, then each key in the core `Kbd`.
    At most 280 pt wide and 2 lines (measured before paint). Island black, HUD text, `type2.sm`, `radius2.card`; no
    pass color. Fades in after the stroke with a small spring slide; reduced motion: fade in only.
  - `onscreen.ts` (new): on a non-replay lesson.ready whose lesson has `app.tool`, `emitUi('panel', 'collapse')` one tick
    later (after the drawer's own lesson.ready opened it). Never without app, never on a replay, once per lesson.ready
    (never re-collapses after the learner opens it). Nothing lesson-specific.
  - Tests: `text.test.ts` (text, keys, merge, textSpot at the centre, edges and corners, line clearance) and
    `onscreen.test.ts` (store hold rules with mock timers; the collapse).
- `app/mock/scenarios/onscreen.json` (new): a Blender lesson that walks itself, one step every ~14 s.
- `app/agents/app-onscreen-coach.md`, `app/agents/shots/app-onscreen-coach-*.png`, `"app-onscreen-coach": 5205` in ports.json.

## Contract
- **In:** `annotate` marks with `text?` / `keys?` (why "point"), and `lesson.ready` `lesson.app {tool, label, using?}`
  (the engine lane's contract commit, Nov 24). Both read defensively through local types until that commit reaches
  v2-integration (Core request (a)).
- **Out:** core UI event `panel` `'collapse'` (the drawer's own public seam). Nothing to the engine.

## Test
`npm run dev:web -- --port 5205`, then http://localhost:5205/?scenario=onscreen (add `&draw=slow` to draw 8x slower).
- 0-15 s: step 1. The island is the Mini pill ("Add a torus · 1 of 3"); the circle is mid-screen with "Add a torus from
  the Add menu" and its keycap to the right.
- ~15 s: step 2, a target at the right edge: the text flips to the left of the loop.
- ~30 s: step 3, a bar along the bottom: the text sits above it, beside the line.
- Click the Mini pill (the island): the steps panel opens; the text stays. Esc fades the text; Show me (in the
  panel, or its shortcut) draws it again.
- After a pass the drawer holds "Step done" on the island until Continue / Next step; the next step's mark is
  already drawn under it.
- Compare http://localhost:5205/?scenario=lesson-panel (no lesson.app): the drawer still opens as before.

Checks run (Nov 24): `npm run typecheck`; `node --import tsx --test src/renderer/src/features/annotate/*.test.ts`
(87 pass, round 1: Show me / "Not yet" bring a reached or dismissed text mark back, a bare re-send does not);
`npm test` (746 pass, no failures); brand lint on the added lines in app/src (no hex, rgba, hand-typed
keycaps, Cursor, dangerouslySetInnerHTML, green, capital M; test keycaps are escaped engine data).

Shots (headless Chromium, 1440x900, the stage scales a 1600x1000 display):
`agents/shots/app-onscreen-coach-circle.png`, `-collapsed.png`, `-edge-right.png`, `-edge-bottom.png`, `-steps.png`.
- `-collapsed.png` is its own capture (`&draw=slow`, mid-draw, the island collapsed to "Click to reopen · 1 of 3").
- `-edge-right.png` / `-edge-bottom.png` are taken after pressing Continue on the held "Step done" card, so they show
  only the live step (the Mini pill still reads "Step n passed", the drawer's own wording).

## Unverified
- Nothing ran in Electron or against a live engine: no real `annotate` with text, no real `lesson.app`.
- The stage has no app under the circle, so the shots show the stroke and text over an empty screen.
- Reduced motion was not checked in a browser.
- The text box's size is measured in a layout effect; on a real overlay a font load after the first paint could
  shift it once.

## Core requests
- **(a) Contract merge:** merge the engine lane's contract commit (Annotation `text` / `keys`, `LessonApp`,
  `LessonInfo.app`) into v2-integration, so the local defensive types (`OnscreenFields` in marks.ts, `LessonAppFields`
  in onscreen.ts) can go.
- **(b) Keycap label variant:** a core keycap that renders an engine-given key label (`<Keycap label=...>`) with the
  keycap look, since `bridge.platform.keys` only holds miyagi's own shortcuts. Until then the text box uses core `Kbd`.
- **(c) Optional:** a `useLessonApp()` selector in core/lesson (onscreen.ts reads the lesson.ready payload directly).
