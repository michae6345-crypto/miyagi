# tips

**Status:** first pass done (stage-checked, not run in Electron) · **Port:** 5613 · **Branch:** `michael/app-first-tips`

## Goal
First-time guidance that teaches the overlay without a manual. At most one small coach mark at a time, only the first
time each thing appears, beside the real element (never over it). Got it or Esc closes it for good; "..." > Don't show
tips turns them all off.

| Tip | Points at | Copy | Shows when |
|---|---|---|---|
| check | the panel's Check my work | Press it when you think you're done. miyagi checks your real work. | panel in its Working view |
| help | the panel's Need help row | Try [Hint] first, then [Show me]. (pastel chips) | first Not yet, or from step 2 on |
| mini | the Mini pill | It keeps your place. Click it to open the panel again. | the panel collapsed to Mini (also counts the pill tip as seen) |
| pill | the step pill | Click it to open your lesson. | a step is on and the panel is not docked open (video lessons) |
| launcher | the idle pill | Press [⌥Space] in any app to start a lesson. (keycap from `bridge.platform.keys.launcher`) | no lesson |
| menubar | the menu bar (taskbar) item | Open it from the menu bar, even with every window closed. | after the launcher tip, idle, and main says where the item is |

Calm rules: the element must hold still 700 ms (no tips mid-animation), nothing in the first 1.5 s, 1.4 s between two
tips, nothing while another surface has the floor (a card out of the island, the launcher or Settings borrowing the
island, the spotlight's hole, a diagram flyout, a concept, the pill's menu). If the element leaves, the tip goes too and
counts as seen only if it was up 4 s. Enter: fade plus a 6 px rise toward the element on the house spring; reduced
motion: the fade only. The mark reserves its rect (`reserveRect('tips')`) so island cards step around it.

## Owns
- `app/src/renderer/src/features/tips/` (index.tsx layer at z 70, store.ts, tips.ts, place.ts, CoachMark.tsx, stage.ts)
- `app/mock/scenarios/tips.json` (unique trigger keys only: `stage.tips:lesson`, `action:*@step_tips*`, so `full` is unchanged)

## Test
`npm run dev:web -- --port 5613 --strictPort`, then:
- `http://localhost:5613/?scenario=tips&os=mac&size=1440x900&clean&tips=reset`: launcher tip, Got it, then the menu bar tip (a stand-in tree is drawn in the stage menu bar)
- `...?scenario=tips&tipsDemo=lesson&os=mac&size=1440x900&clean&tips=reset`: Check my work, Got it, then Need help
- add `&panel=mini`: the Mini tip · `?scenario=player&...&tips=reset`: the step pill tip · `&os=win`: Windows keycaps
- Esc closes the open "..." menu first, then the tip. **In the stage tips are off unless `?tips` (any value) or
  `scenario=tips` is in the URL**, so other lanes' review shots stay clean. Electron: always on.

Shots: `/Users/tripi/sand hacks/miyagi-v2/screens/round3/tips-1-launcher.jpg` to `tips-7-pill.jpg`.

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

## Notes
- Esc: a capture-phase window listener takes Esc only while a tip is up, so the panel under it does not also collapse.
  An `onUi('dismiss')` from elsewhere (a card's close, Electron's Esc path) also closes the tip.
- The overlay window is not focusable in Electron, so Got it (a click) is the main way out there; Esc works in the stage
  and in any focused window.
- Unverified in Electron (cost freeze, no live run): click-through over the mark and its menu (both `data-hit`), the
  tray bounds (request 2), localStorage persistence in the overlay renderer.
