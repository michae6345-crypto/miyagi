# app-circle-ask

**Status:** first pass done, stage only · **Port:** 5200 (ports.json `app-circle-ask`) · **Branch:** `michael/app-circle-ask` (from `origin/michael/v2-integration`, with the contract commit `contract: circle-to-ask region and buddy annotations (additive)` cherry-picked)

## Goal
Circle to ask, like Clicky. Hold the push-to-talk keys (Fn+Control), circle anything on screen with the mouse, say a question or nothing, let go. miyagi explains what is inside the circle in a small card beside it. Esc cancels.

## Owns
- `app/src/renderer/src/features/circle/` (new): `machine.ts` (pure state machine), `geometry.ts` (pure: ink to box, box to screen points, ink path, card place), `store.ts`, `Layer.tsx`, `web.ts` (stage only), `index.tsx`
- `app/mock/scenarios/circle.json`, `app/test/circle.test.ts`, shots `app/agents/shots/app-circle-ask-*.png`

Small edits in other renderer feature folders (no core):
- `features/ptt/store.ts`: `claimFinals(fn)`. The circle takes a session's final words before push to talk routes them, so they are not asked twice.
- `features/cards/store.ts`: skips an answer card the circle owns (`circleOwnsCard`), so the answer shows once, beside the circle.
- `features/tips/tips.ts` (+ index doc line): the one-time tip `circle`, "Hold [ptt keycap] and circle anything to ask." The keycap is `Keycap k="ptt"` (or `ptt_alt` for the Control+Option chord), from `bridge.platform.keys`. It shows on the step pill, or on the idle pill once the launcher tip is seen, only while push to talk is on and its helper is ready. Done once a circle was asked about.

## How it works
- A push-to-talk hold (`arming` / `listening`) arms the circle. While armed, and only then, the overlay takes the mouse (`ui:emit 'overlay:interactive' true`, said again every 200 ms and on pointer moves, because core's hover tracking may say "no" when the pointer leaves a card mid-stroke). If "away" is on (another app in front), it is woken first.
- The drawing surface is full screen while armed. It takes pointerdown with button 0 or 2 (Control + click is a right click on a Mac) and swallows `contextmenu`. It is NOT `data-hit`, so core does not report the whole screen as miyagi's UI to the engine (`overlay.bounds`).
- Every way out gives the mouse back once: the keys up, Esc (push to talk's `esc`, main's dismiss, the key), window blur, page hidden, an error, the engine link dropping, and the 8 s cap. Ink drawn before blur or the cap is kept and still asked about.
- On release with ink: the box (ink bounds, 6 px pad, kept on the overlay) becomes a `ScreenRegion` (window origin added, `devicePixelRatio` as scale, `layout.displayId`). The ask goes out as `action {kind: "ask", text, region, source: "circle", askId}`. text is the spoken words, or "What is this?" when nothing was said (helper cancel `empty` / `short` / `keypress` / `timeout`, or no final within 1.5 s). A hold with no ink (or just a click) is plain push to talk, routed as before.
- While the engine thinks, a small "Looking" chip sits by the circle. The answer `card {kind: "answer", askId}` shows beside the circle (right, left, below, above, the first that fits, always 16 px inside the screen edges). It closes on its X, Esc, a new hold, the lesson ending, or after 60 s. No answer in 45 s: the ink goes and the pill says "No answer yet. Try again." An older engine that answers without `askId` gets its usual island card and the ink goes.
- Ink: `tone.mint.solid` (the brand mint, never the pass green), round caps, a faint second pass beside it so it reads as drawn by hand.

## Test
- `npm run typecheck`
- `node --import tsx --import ./test/setup.mjs --test test/circle.test.ts` (36 tests: stroke to box, screen points, clamping, card place, the state machine). The repo has no vitest; tests use node:test like the rest of `app/test/`.
- Stage: `npm run dev:web -- --port 5200`, then
  - drawing: `http://localhost:5200/?scenario=circle&ptt=listen&circle=draw&circle-ms=900&clean`
  - answered: `http://localhost:5200/?scenario=circle&ptt=empty&circle=answered&clean`
  - `?circle=` turns the feature on in the stage even though push to talk is off.

## What is NOT verified
- **Nothing ran in Electron, and nothing ran against a live engine or model.** The stage fakes the hand (`web.ts` draws a loop through the store, not through real pointer events) and the engine (it answers on the bus with the askId).
- **Push to talk is off in the product** (`PTT_ENABLED = false`, common/flags.ts, Adrian, Nov 21, launch register R05/R06). The circle rides on its keys, so it is off in Electron too until that flag flips. Flip it only once the microphone use is disclosed.
- Whether the macOS overlay really takes the mouse over fully transparent pixels while interactive. The surface has a near-clear fill (`rgba(0,0,0,0.012)`) for that; check on the Mac.
- How Chromium on macOS reports Control + click (button 0 or 2) with Fn held, and whether `contextmenu` preventDefault stops every menu. Both are handled; neither is seen.
- Whether the miyagi-listen helper cancels a hold (`keypress`) when the mouse is used. A cancel with ink still asks "What is this?"; only `esc` and `disabled` drop it.
- The ptt:state and ptt:final order from main. Both orders are handled and tested.
- Multi-display: `displayId` needs the core request below; without it the region carries `displayId: 0` (the engine should take the display under the region).
- Buddy draws (the `annotate` event, the branch from the island) is not in this lane.

## Core requests
1. **`Layout.displayId`** (done here as its own tiny commit, `app/src/preload/api.ts` + `app/src/main/index.ts` layoutFor: `displayId: display.id`). Additive and optional. Without it every circle says `displayId: 0`.
2. **`sendAction(kind, text, extra?)`** in `core/shortcuts.ts`: it has no room for `region` / `source` / `askId`, so `features/circle/store.ts` records the press on `usePressed` itself and sends `bridge.send(cmd('action', ...))`. Switch to sendAction once it takes the extra fields.
3. **`'annotate'` in `common/wire.ts` KNOWN** (from the contract commit). Not needed by this lane; the buddy-draws lane needs it or the app never sees the event.
