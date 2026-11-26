# app-blender-polish

**Status:** pass done (Nov 24), offline tests + headless stage shots only · **Port:** 5206 (in ports.json) ·
**Branch:** `michael/app-blender-polish` (base `origin/michael/v2-integration`) · **PR:** draft into `adrian/shell`

## Goal
The app side of the Blender step: bring the contract level, ship the Blender add-on in the packaged app, re-check the
round-3 on-screen coach fixes, and render the new `open_in_app` card action.

## Owns
- `shared/contracts/events.ts`, `shared/contracts/events.py` (this branch's copy, additive only)
- `app/scripts/bundle-engine.mjs`, `app/test/bundleTarget.test.ts`
- `app/src/renderer/src/features/annotate/**` (round 4, see `app-onscreen-coach.md`)
- `app/src/renderer/src/features/cards/index.tsx` and `store.ts` (open_in_app lines only), `app/test/openInApp.test.ts`
- `app/mock/scenarios/blender-open.json`
- `app/agents/app-blender-polish.md`, the round-4 note in `app/agents/app-onscreen-coach.md`,
  `app/agents/shots/app-onscreen-coach-edge-*.png`, `app/agents/shots/app-blender-polish-open.png`, ports.json

## What changed
- **(a) Contract** (commit `contract: on-screen coach + open_in_app (from integration/live, additive)`). Engine commit
  66950fef does not apply here (this copy lacks BuildSource / LessonInfo.origin and later work), so its hunks are ported
  by hand, text-identical: `LessonApp {tool, label, using?}`, `lesson.ready` lesson `app?: LessonApp` (without
  `origin`), `Annotation.text? / keys?`, and the Annotation / AnnotateMarks / annotate doc text. Plus `open_in_app` in
  the card `actions` union and the `action` kind union (events.ts, with the shared comment) and in the `CardAction` /
  `ActionKind` Literals (events.py, the comment shortened). Every line 66950fef adds is here except the two that carry
  `origin` / `buildS`. The only removed lines are the old doc text and the lines whose union gained a member.
  Then the local defensive types went: `OnscreenFields` (marks.ts) and `LessonAppFields` (onscreen.ts). Behaviour is
  the same: wire values are still cleaned (`cleanText`, `cleanKeys`, `lessonAppOf`).
- **(b) Bundle:** `'blender-addon'` added to `PATHS` in `bundle-engine.mjs` and its header comment, so
  `~/miyagi/engine/src/blender-addon` exists in the packaged app and `blender_ext.BRIDGE_START` /
  `blender.DUMP_SCRIPT` resolve (this also fixes the headless scene dump there). compileall `srcDirs` and `pruneSrc`
  stay server/shared/cli: the add-on runs in Blender's own Python. `bundleTarget.test.ts` asserts both.
- **(c) Round 4 of the on-screen coach:** the quiet state (pause, blockers, idle) now outlives step.passed; a rootFor
  sequence test; shots retaken. See `app-onscreen-coach.md`, "Round 4".
- **(d) open_in_app:** `ACTION.open_in_app = {label: 'Open in app', Icon: ExternalLink, primary: true}` in
  features/cards/index.tsx, and `'open_in_app'` in `SETTLE` (store.ts). The button sends `action {kind: 'open_in_app'}`
  with no text and settles after 900 ms like Open VS Code (the card closes when it was its only job, Skip aside). Its
  label is the engine's `setup.actionLabels.open_in_app` ("Open in Blender"). Not in `PLAN_ACTIONS`. A card with
  `holdVideo: false` never holds the video (setupHold.ts, unchanged). No app name in UI code.

## Test
`npm run dev:web -- --port 5206`, then:
- http://localhost:5206/?scenario=blender-open: after ~1 s the island grows into "Blender is ready" with one white
  "Open in Blender" button. Press it: it spins briefly and the card goes back into the island.
- http://localhost:5206/?scenario=onscreen: the round-3 walk-through (`app-onscreen-coach.md`).

## Checks run (Nov 24)
- `npm run typecheck`: passes. One test line in `text.test.ts` now casts its deliberate wire garbage
  (`[SHIFT_A, 5]`), since `Annotation.keys` is typed `string[]` now.
- `node --import tsx --test src/renderer/src/features/annotate/*.test.ts`: 109 pass, 0 fail (105 before; the 2 new
  pass-crossing store tests fail on the round-3 code).
- `npm test`: 752 pass, 0 fail (new: `openInApp.test.ts`, 5 tests; the `bundle-engine.mjs wiring` PATHS test).
- `node scripts/bundle-engine.mjs --dry-run`: `engine origin/integration/live@80513155 (server, shared, cli, scripts,
  demo, blender-addon) → app/build/engine/src [dry run: nothing is written]`; app/build/engine was not created.
- The Python contract imports with pydantic (an existing /private/tmp venv, no install): `open_in_app` in both
  Literals, `Annotation(text, keys)`, `LessonInfo(app=LessonApp(...))`, `Action(kind='open_in_app')`.
- Headless Chromium (`~/miyagi/tools/playwright/blender-polish-shots.mjs`), 1440x900, port 5206:
  - onscreen: after Continue, each stroke's first point is 2 pt above the island's bottom (y 72 vs 74), on its middle.
  - blender-open: one visible "Open in Blender" button, white fill (`color.accent`) with dark text; a click and a
    second click sent exactly one `action {kind: "open_in_app"}` (counted by wrapping the stage bridge's `send`); the
    card was gone 1.5 s later.
  - The server was stopped; `lsof -iTCP:5206 -sTCP:LISTEN` was empty.
- Brand lint on the added lines in app/src: no hex, rgba, hand-typed keycaps, emoji, Cursor,
  dangerouslySetInnerHTML, capital-M miyagi, green, or "Blender".
- `git diff --stat`: nothing under server/, blender-addon/, core/ or src/main/.

## Shots
- `agents/shots/app-blender-polish-open.png`: scenario blender-open, the setup card with "Open in Blender".
- `agents/shots/app-onscreen-coach-edge-right.png`, `-edge-bottom.png`: retaken (byte-identical to round 3).

## Unverified
- Nothing ran in Electron or against a live engine. The engine side of `open_in_app` (lane "open") is not on this
  branch, so the mock only shows the card. No real Blender was opened (the lane rules allow headless only).
- No real bundle was built; only the dry run lists the path.
- That main/localEngine copies `blender-addon` into `~/miyagi/engine/src` is read from the code (it copies all of src),
  not observed.

## Core requests
- **Contract gap:** this branch's `shared/contracts` still lacks the rest of the engine's contract work on
  integration/live: ambient help, any-link (`BuildSource` on lesson.ready, `LessonInfo.origin`, `buildS`), ui-v4 and
  `cloud.notice`. A `contract:` merge of integration/live's events.ts / events.py into v2-integration would make this
  copy level; this lane ported only 66950fef and `open_in_app`.
- **Keycap label variant** (carried from app-onscreen-coach (b)): a core keycap that renders an engine-given key label
  (`<Keycap label=...>`) with the keycap look, since `bridge.platform.keys` only holds miyagi's own shortcuts. The
  on-screen coach's text box uses core `Kbd` until then.
