# app-circle-ask

**Status:** fix round 1 done, stage only · **Port:** 5200 (ports.json `app-circle-ask`) · **Branch:** `michael/app-circle-ask` (from `origin/michael/v2-integration`, with the contract commit `contract: circle-to-ask region and buddy annotations (additive)` cherry-picked)

## Goal
Circle to ask, like Clicky. Hold the push-to-talk keys (Fn+Control), circle anything on screen with the mouse, say a question or nothing, let go. miyagi explains what is inside the circle in a small card beside it. Esc while the keys are held cancels (push to talk's own Esc).

## Owns
- `app/src/renderer/src/features/circle/` (new): `machine.ts` (pure state machine), `geometry.ts` (pure: ink to box, box to screen points, ink path, card place), `store.ts`, `Layer.tsx`, `web.ts` (stage only), `index.tsx`
- `app/mock/scenarios/circle.json`, `app/test/circle.test.ts`, `app/test/circleStore.test.ts`, shots `app/agents/shots/app-circle-ask-*.png`

Small edits in other renderer feature folders (no core):
- `features/ptt/store.ts`: `claimFinals(fn)`. The circle takes a session's final words before push to talk routes them, so they are not asked twice.
- `features/cards/store.ts`: skips an answer card the circle owns (`circleOwnsCard`), so the answer shows once, beside the circle.
- `features/tips/tips.ts` (+ index doc line): the one-time tip `circle`, "Hold [ptt keycap] and circle anything to ask." The keycap is `Keycap k="ptt"` (or `ptt_alt` for the Control+Option chord), from `bridge.platform.keys`. It shows on the step pill, or on the idle pill once the launcher tip is seen, only while push to talk is on and its helper is ready. Done once a circle was asked about.

## How it works
- A push-to-talk hold (`arming` / `listening`) arms the circle. While armed, and only then, the overlay takes the mouse (`ui:emit 'overlay:interactive' true`, said again every 200 ms and on pointer moves, because core's hover tracking may say "no" when the pointer leaves a card mid-stroke). If "away" is on (another app in front), it is woken first.
- The drawing surface is full screen while armed. It takes pointerdown with button 0 or 2 (Control + click is a right click on a Mac) and swallows `contextmenu`. It is NOT `data-hit`, so core does not report the whole screen as miyagi's UI to the engine (`overlay.bounds`).
- **Nothing over the circle is reported as miyagi's UI.** The ink svg is the whole overlay and its stroke box is exactly the circled region, so it is neither `data-ui` nor `data-hit` (the engine's reader would skip OCR there and black it out in the crop). Only the "Looking" chip (`data-ui`) and the answer card (`data-hit`) are reported, and both sit beside the circle. `test/circleStore.test.ts` renders the layer in sealed / asking / answered and checks no reported node overlaps the circled box.
- Every way out gives the mouse back once: the keys up (also while push to talk is still `arming`: `common/pttState` keeps phase `arming` with `released: true` until the helper says `listening`, and the circle ends the hold on `released`), push to talk's `esc`, window blur, page hidden, an error, the lesson ending, the engine link dropping, and the 8 s cap. Ink drawn before blur or the cap is kept and still asked about. `test/circleStore.test.ts` drives the real store with a fake bridge and checks each path says click-through exactly once, says nothing after, and stops the re-say interval and the ticker.
- On release with ink: the box (ink bounds, 6 px pad, kept on the overlay) becomes a `ScreenRegion` (window origin added, `devicePixelRatio` as scale, `layout.displayId`). The ask goes out as `action {kind: "ask", text, region, source: "circle", askId}`. text is the spoken words, or "What is this?" when nothing was said (helper cancel `empty` / `short` / `keypress` / `timeout`, or no final within 1.5 s). A hold with no ink (or just a click) is plain push to talk, routed as before.
- **Engine link down** when the hold seals (`useLesson.connected` false, never connected included): no ask is sent. The ink goes, the mouse is back, and the pill says "miyagi can't see the screen yet."
- While the engine thinks, a small "Looking" chip sits by the circle. The answer `card {kind: "answer", askId}` shows beside the circle (right, left, below, above, the first that fits, always 16 px inside the screen edges). No answer in 30 s: the ink goes and the pill says "No answer yet. Try again." An older engine that answers without `askId` gets its usual island card and the ink goes.
- **Closing the answer card.** It closes on its X, a new hold, the lesson ending, the engine dropping, or after 25 s. In Electron, Esc does NOT reach it after release: the overlay is `focusable: false` and main relays no Esc (only `dev/Stage.tsx` maps Escape to `dismiss`; the circle's own keydown listener covers the stage). That is Core request 4. Other cards' close (`core/ui/atoms` CloseButton, features/complete, both `emitUi('dismiss')`) no longer wipes the circle: the circle does not listen to `dismiss`.
- **Away.** When a lesson runs and another app has been in front for 3 s, main makes the whole overlay click-through (`overlay:away`), which would make the card's X unclickable. While the answer shows, the circle calls `wake()` (on arrival, when away turns on, and on every tick), so the X stays clickable for its 25 s.
- The chip and the card follow Settings > Appearance (`data-theme="auto"` on the layer, like the lesson panel; the overlay root pins the island's dark set). Shots in both.
- Ink: `tone.mint.solid` (the brand mint, never the pass green), round caps, over a thin neutral casing (`brand.ink` at 0.55, 5.4 px; a plain stroke, no blur or glow), so it reads on white pages and VS Code Light too (mint alone is about 1.3:1 on white). The old 0.4 second pass is gone.
- The drawing surface's near-clear fill is now the theme token `fill.catch` (Core request 5).

## Limits
- **One display.** Circling works only on the display the overlay is on (`layoutFor`'s display in main). A circle on a second display is not possible yet: the overlay does not cover it.
- **The engine half is in no lane yet, and this must land before `PTT_ENABLED` flips.** No `server/` file changes here and no engine branch exists. The engine still needs: handle `action ask` with `region` and `source: "circle"`; crop that region and read the OCR / accessibility text boxes inside it (`server/coach/screen.py` ScreenContext); wrap the screen text with `server/untrusted.py` `wrap()` and `DATA_RULE`; never store or log the crop; with no screen-recording permission or no model, answer from the OCR text or say plainly that miyagi can't see the screen yet; answer with `card {kind: "answer", askId, region}` (Claude, Haiku-class through `server/coach/llm.py`).
- The circle tip shows on the island's step pill or idle pill. In the v2 notch stage (`notch` default) the island has no mode at rest, so no island-anchored tip shows there (the launcher's neither); the tip shot uses `&notch=below`.

## Test
- `npm run typecheck`
- `node --import tsx --import ./test/setup.mjs --test test/circle.test.ts test/circleStore.test.ts` (54 tests: stroke to box, screen points, clamping, card place, the state machine with released-while-arming; the store with a fake bridge: the mouse back once on every exit path and the timers stopped, offline, dismiss, away; the layer's reported nodes never over the circle). The repo has no vitest; tests use node:test like the rest of `app/test/`. Full `npm test`: 652 pass.
- Stage: `npm run dev:web -- --port 5200`, then
  - drawing: `http://localhost:5200/?scenario=circle&ptt=listen&circle=draw&circle-ms=900&clean`
  - answered: `http://localhost:5200/?scenario=circle&ptt=empty&circle=answered&clean` (add `&appearance=light` with a light system appearance for the light card)
  - ink on light content: `...&circle=answered&circle-at=960,556,150,56&clean&appearance=light`
  - the tip: set `localStorage['miyagi.tips'] = '{"off":false,"seen":["check","help","mini","pill","launcher","menubar"]}'`, then `http://localhost:5200/?scenario=tips&tipsDemo=lesson&ptt=idle&clean&notch=below`
  - `?circle=` turns the feature on in the stage even though push to talk is off.
- Shots: `app-circle-ask-drawing.png`, `app-circle-ask-answered.png` (dark), `app-circle-ask-answered-light.png` (light card), `app-circle-ask-light-content.png` (the casing over a white button), `app-circle-ask-tip.png` (the new tip).

## What is NOT verified
- **Nothing ran in Electron, and nothing ran against a live engine or model.** The stage fakes the hand (`web.ts` draws a loop through the store, not through real pointer events) and the engine (it answers on the bus with the askId).
- **Push to talk is off in the product** (`PTT_ENABLED = false`, common/flags.ts, Adrian, Nov 21, launch register R05/R06). The circle rides on its keys, so it is off in Electron too until that flag flips. Flip it only once the microphone use is disclosed and the engine half has landed.
- Whether the macOS overlay really takes the mouse over fully transparent pixels while interactive. The surface has a near-clear fill (`fill.catch`) for that; check on the Mac.
- How Chromium on macOS reports Control + click (button 0 or 2) with Fn held, and whether `contextmenu` preventDefault stops every menu. Both are handled; neither is seen.
- Whether the miyagi-listen helper cancels a hold (`keypress`) when the mouse is used. A cancel with ink still asks "What is this?"; only `esc` and `disabled` drop it.
- The ptt:state and ptt:final order from main. Both orders are handled and tested.
- Buddy draws (the `annotate` event, the branch from the island) is not in this lane.

## Core requests
1. **`Layout.displayId`** (done here as its own tiny commit, `app/src/preload/api.ts` + `app/src/main/index.ts` layoutFor: `displayId: display.id`). Additive and optional. Without it every circle says `displayId: 0`.
2. **`sendAction(kind, text, extra?)`** in `core/shortcuts.ts`: it has no room for `region` / `source` / `askId`, so `features/circle/store.ts` records the press on `usePressed` itself and sends `bridge.send(cmd('action', ...))`. Switch to sendAction once it takes the extra fields.
3. **`'annotate'` in `common/wire.ts` KNOWN** (from the contract commit). Not needed by this lane; the buddy-draws lane needs it or the app never sees the event.
4. **Main relays Esc while a circle card is up.** The overlay never has focus, so after release Esc cannot close the answer card in Electron. Ask: while the renderer says a circle card is up, main registers Esc (or forwards it from the helper) and sends `dismiss` (or a circle-only signal) to the overlay. Until then the card closes on its X or after 25 s.
5. **`fill.catch` in `core/theme.ts`** (done here as its own one-line commit): the near-clear fill `rgba(0,0,0,0.012)` that keeps an interactive transparent overlay hit-testable, so no colour literal sits in feature code.
6. **A hard cap in main for `overlay:interactive`.** Today only renderer timers give the mouse back, so a hung or busy overlay renderer could keep the whole screen grabbed (`ui:ready` only covers a reload). Ask: main drops `overlay:interactive` true if the renderer has not said it again within about 1 s (the circle re-says it every 200 ms while armed).
