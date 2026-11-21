# tips

**Status:** fix round 1 done (stage-checked, not run in Electron) · **Port:** 5613 · **Branch:** `michael/app-first-tips`

## Goal
First-time guidance that teaches the overlay without a manual. At most one small coach mark at a time, only the first
time each thing appears, beside the real element (never over it). Got it or Esc closes it for good, and so does doing
what it says (however briefly the tip was up); "..." > Don't show tips turns them all off.

| Tip | Points at | Copy | Shows when | Done when the learner (`done` in tips.ts) |
|---|---|---|---|---|
| check | the panel's Check my work | Press it when you think you're done. miyagi checks your real work. | panel docked open, in its Working view | sends check_step (button or key), or the panel shows Checking, Not yet or Passed |
| help | the panel's Need help row | Try [Hint] first, then [Show me]. (pastel chips) | panel docked open: the first Not yet, or from step 2 on after 20 s on the step; never while a hint is shown | asks for a Hint or Show me (tile or key), or the panel shows a hint |
| mini | the Mini pill | It keeps your place. Click it to open the panel again. | the panel collapsed to Mini (also counts the pill tip as seen, on every way it closes) | opens the panel again |
| pill | the step pill | Point at it to see your step. (the pill takes no click; hovering opens the step card) | a step is on, no panel docked open and no video player docked | points at it (the overview card grows out of the island) |
| launcher | the idle pill | Press [⌥Space] in any app to start a lesson. (keycap from `bridge.platform.keys.launcher`) | no lesson, engine reachable | opens the launcher (`launcher:open`: the key, the pill, the menu bar) |
| menubar | the menu bar (taskbar) item | Open it from the menu bar, even with every window closed. | after the launcher tip, idle, engine reachable, and main says where the item is | (Got it or Esc only) |

A press on the element a tip points at (capture-phase pointerdown inside its target) also counts as done.

Calm rules: nothing while first-run setup is open (the overlay asks `onboarding:get` until it says done), the element must hold still 700 ms (no tips mid-animation), nothing in the first 1.5 s (after start-up, or after setup finishes), 1.4 s between two
tips, nothing while another surface has the floor (a card out of the island, the launcher or Settings borrowing the
island, the spotlight's hole, a diagram flyout, a concept, the pill's menu). If the element leaves, the tip goes too and
counts as seen only if it was up 4 s, unless the learner did what it says (then it is seen at once). The same goes for a
dismiss from elsewhere (a card's close, a lesson completing): only Got it, the tip's own Esc, doing what it says and
Don't show tips are final. Every final path also marks the tip's `alsoSeen` (dismissTip in store.ts).
Battery: the layer reads the DOM about 10 times a second while a tip is up (every frame only while its element moves),
4 times a second while none is, and stops entirely once every tip is seen or tips are off. Enter: fade plus a 6 px rise toward the element on the house spring; reduced
motion: the fade only. The mark reserves its rect (`reserveRect('tips')`) so island cards step around it.

## Owns
- `app/src/renderer/src/features/tips/` (index.tsx layer at z 70, store.ts, tips.ts, place.ts, CoachMark.tsx, stage.ts)
- `app/mock/scenarios/tips.json` (unique trigger keys only: `stage.tips:lesson`, `action:*@step_tips*`, so `full` is unchanged)

## Test
`npm run dev:web -- --port 5613 --strictPort`, then:
- `http://localhost:5613/?scenario=tips&os=mac&size=1440x900&clean&tips=reset`: launcher tip, Got it, then the menu bar tip (a stand-in tree is drawn in the stage menu bar)
- `...?scenario=tips&tipsDemo=lesson&os=mac&size=1440x900&clean&tips=reset`: Check my work, Got it, then Need help
- add `&panel=mini`: the Mini tip (the Check my work mark leaves as the panel starts to collapse) · `?scenario=player&...&tips=reset`:
  no pill tip (the player already shows the step) · `&os=win`: Windows keycaps
- Esc closes the open "..." menu first, then the tip. Opening the menu from the keyboard moves focus to Don't show
  tips and closing it puts focus back on "..."; opened with the mouse, focus is left alone (no focus ring). **In the stage tips are off unless `?tips` (any value) or
  `scenario=tips` is in the URL**, so other lanes' review shots stay clean. Electron: always on.

Shots: `/Users/tripi/sand hacks/miyagi-v2/screens/round3/tips-1-launcher.jpg` to `tips-7-pill.jpg`; fix round 1: `tips-fixr1-*.jpg` (headless, 1440x900).

## Core requests
1. **Pref key** (`common/prefs.ts`, core): add `tips: { off: boolean; seen: string[] }` to `Prefs`, `DEFAULT_PREFS`
   (`{ off: false, seen: [] }`) and `sanitizePrefs` (boolean, and an array of at most 32 short strings). Today the state
   lives in the overlay renderer's localStorage (`miyagi.tips`), which persists in Electron too but not across windows or
   a Settings reset. `store.ts` switches to prefs by itself as soon as `DEFAULT_PREFS` carries `tips`; no change here.
2. **Menu bar item position** (`main/features/launch.ts`, launch-ease lane): `ctx.handle('launch:tray-bounds', () =>
   tray?.getBounds())` (screen points). Until it exists the invoke fails and the menu bar tip never shows (graceful).
3. **Show tips again** (settings lane): a row in Settings > General that calls `resetTips()` from `features/tips/store`
   (or, once request 1 lands, sets `tips: { off: false, seen: [] }`).
4. **Stable anchors** (optional, drawer and pill lanes): `data-tip-anchor="check"` on the panel's Check my work button,
   `data-tip-anchor="help"` on the Need help row, `data-tip-anchor="panel"` on the panel root. Tips already prefer
   these; today they fall back to `[data-part="lesson-panel"][data-view="working"] [data-button="primary"]`,
   `[data-part="panel-help"]`, `[data-part="lesson-panel"]` and `[data-island-layer="idle|compact|mini"]`. If any of
   those change, that tip just waits (no crash, no misplaced mark).

5. **Setup finished** (`main/features/onboarding.ts`, onboarding lane): in the `onboarding:done` handler, after saving,
   `ctx.broadcast('onboarding:done')`. Tips already listen for it; until it lands they ask `onboarding:get` every 2 s
   while setup is unfinished, so the first tip comes up to 2 s later than it could.
6. **Esc reaches the tip first** (main dismiss-key routing + core `bus`; real-app and core lanes): the overlay window
   can't take focus, so in Electron Esc never reaches the tip's own keydown listener (store.ts); it lands in the app in
   front. `dismiss` is a UI key (main/platform.ts `UiKeyKind`), not a global shortcut, so today the overlay hears a
   dismiss only as `onUi('dismiss')` (a card's close, a lesson completing, and any Esc path main adds). That path
   withdraws the tip without marking it seen and also hides the lesson panel and cards under it, so the spec's
   "dismiss with Esc" does not work in Electron; Got it (a click) or doing what it says are the only ways out there. Ask: whenever a dismiss key
   reaches the overlay, and a tip is active, route it to the tip first and stop there. Suggested shape: `emitUi('dismiss')`
   lets a handler claim the press (it already returns `claimed`), the dismiss-key path in the overlay stops when it is
   claimed, and tips claims it (calls `dismissTip()`, returns true) only for a key press, never for a card's ✕, so the
   panel and cards never see that Esc. Tips needs a way to tell the key from a ✕ (a payload such as `{ key: true }`).

## Notes
- Offline: the launcher and menu bar tips read `usePill`'s `offline` (read only). While the idle pill says Can't reach
  miyagi (or Setting up, Install the engine, Engine didn't start) neither tip shows.
- Got it is a QuietButton: the element the tip teaches (Check my work) stays the one primary on screen.
- The "..." menu reserves its rect next to the mark's while open, and a press anywhere else closes it.
- The tray position is asked for only after the launcher tip is seen, while the island is idle and setup is done; the
  first failed invoke (no handler before request 2) stops the asking for the session.
- Stage: `?scenario=tips&onb=full` shows setup with no tip over it; finish setup and the launcher tip follows.
- Esc: a capture-phase window listener takes Esc only while a tip is up, so the panel under it does not also collapse.
  An `onUi('dismiss')` from elsewhere (a card's close, a lesson completing, any Electron Esc path) withdraws the tip: it
  is kept as seen only if it was up 4 s.
- The overlay window is not focusable in Electron, so Got it (a click) or doing what the tip says is the way out there;
  Esc works in the stage and in any focused window (Core request 6).
- **Nothing here has been verified in Electron yet** (cost freeze, no live run; stage only): click-through over the
  mark and its menu (both `data-hit`), localStorage persistence in the overlay renderer across restarts, the Esc path
  (request 6), and Core requests 1 (prefs key), 2 (tray bounds) and 5 (`onboarding:done` broadcast). Also unchecked
  there: `launcher:open` reaching the overlay when the launcher opens from its global key (the launcher tip's done).
