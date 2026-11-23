# launch-ease

**Status:** pass 1 done: typecheck green, stage shots (pill without the gear, the pill menu, the Library home with its new sidebar foot, onboarding Start learning). Electron not run (cost freeze; Michael checks on the Mac) · **Priority:** P0 (first impression) · **Port:** 5301 · **Branch:** `michael/app-launch-ease` (from `michael/v2-integration`)

## Goal
Clicking the miyagi app always opens something useful, and the pill never collides with anything at the top of the
screen. Dock icon, Launchpad, Spotlight, or opening it again while it runs: setup if it isn't done, otherwise home (the
Library: Continue, Ready to run, the progress dashboard entry). A menu bar item keeps miyagi reachable with every
window closed. The settings gear that was glued to the pill's right edge (it covered the status dot on Michael's Mac) is
gone: Settings is in the pill's right-click menu, the menu bar item, the overview card's footer, the launcher and the
Library's sidebar.

## Owns
- `app/src/main/features/launch.ts` (new): reopen / second-instance / open-file, cold launch, Tray, pill menu
- `app/src/main/launchIcon.ts` (new): the menu bar icon (brand small tree, color, 18 / 36 px, embedded)
- `app/src/renderer/src/features/launch/**` (new): `index.tsx` (right-click listener, main → overlay relay), `web.ts` (stage stand-in), `StageMenu.tsx` (the stage's drawing of the native menu)
- `app/agents/launch-ease.md`

## What it does
| Piece | How |
|---|---|
| Reopen | `app 'activate'` (macOS sends it when a running app, LSUIElement included, is opened again from the Dock, Launchpad, Spotlight or Finder), `'second-instance'`, `'open-file'` (the dropped file is ignored). Each → `openHome()`: setup not done → `onboarding`; an app window open → bring it forward (Library first); else open `library`. An accessory app's window doesn't come forward by itself, so `app.focus({steal:true})` once it shows (user action only). |
| Setup done? | Read on every open: `userData/onboarding.json` `{done:true}` (onboarding.ts writes it) or `prefs.json` `onboarded`. `MIYAGI_SKIP_ONBOARDING=1` counts as done. |
| Cold launch | First launch with setup not done: onboarding.ts opens setup (unchanged). Setup done, built app: opens the Library once the overlay has loaded. Not at login (`wasOpenedAtLogin`), not in `npm run dev`, not with `MIYAGI_QUIET_LAUNCH=1`. A reopen in the first 3 s of a login launch is ignored. |
| Single instance (Mac) | Built app only: `requestSingleInstanceLock()`, a second copy (`open -n`) exits and the first opens home. Windows keeps features/windows.ts. |
| Menu bar item | `Tray` with the small tree in color (BRAND: no one-color tree; the `-dark` cut, whose lighter bark reads on dark and light menu bars). Menu: Open miyagi · Start a lesson (shows the launcher key, `registerAccelerator:false`) · Settings… · Quit miyagi. Windows: left click opens home. |
| Pill menu | Right-click on a pill-sized island (not a card): `launch:menu {x, y}` pops the same menu as a native menu at the pointer's x, just under the pill (never over its words or dot). If it can't open, Settings opens, so a right-click is never dead. |
| Launcher / Settings from main | They're renderer calls, so main sends `feat:launch:open 'launcher' \| 'settings'` to the overlay window only; `features/launch` runs `launcher:toggle` (skipped when the launcher is already up) or `openSettings()`. |
| Start learning (onboarding) | Suggested lesson on the Ready card → starts it (unchanged); otherwise opens the Library instead of the launcher. |
| Library sidebar foot | "Your progress" (`openProgress()`, the lesson dashboard) and "Settings" (`openSettings()`), neutral `SidebarNav`. |
| Notch / menu bar | `platform.ts fitPillTop`: at launch, `pillTop = max(pillTop, workArea.y - bounds.y + 4)` for the primary display, before any window exists (every renderer gets it in its launch args; overlay-raise's hit poll reads the same value). Default 40 stays on a 24 pt menu bar; a bigger band (notch at a scaled resolution, a top taskbar on Windows) pushes the pill under it. `MIYAGI_PILL_TOP` can no longer put it inside the menu bar. Auto-hidden menu bar (no band): the default 40 stays, which clears a notch. |

## Core changes (small, additive; listed for the integrator)
1. `src/main/platform.ts`: new `fitPillTop(pillTop, display)` + `MENU_BAR_GAP`; the `pillTopFor` comment now says the env value can't go into the menu bar.
2. `src/main/index.ts`: imports `fitPillTop`; one line before the core windows are created: `platform.pillTop = fitPillTop(platform.pillTop, displayNow())`.
3. No change to `appWindows.ts`, `context.ts`, preload or `core/`.

## Edits in other lanes' files (minimal)
- `features/pill/index.tsx`: the `pill-gear` overlay layer and its import removed; `features/pill/Gear.tsx` deleted.
- `features/onboarding/store.ts` (`startLearning` fallback → `openLibrary()`), `features/onboarding/Ready.tsx` (comment).
- `features/library/Library.tsx`: the sidebar foot (Your progress, Settings).
- Not touched: voice, progress, overview (its footer gear stays inside the card).

## Test
`npm run dev:web -- --port 5301 --strictPort`
- `http://localhost:5301/?scenario=lesson-panel&panel=working&os=mac&size=1440x900&clean`: the pill has no gear. Right-click it → the menu (stage drawing), under the pill. Settings… grows Settings out of the pill. `&menu` opens it on load.
- `http://localhost:5301/?scenario=home&window=library&size=1440x900&clean`: Library home, "Your progress" and "Settings" at the sidebar's foot.
- `http://localhost:5301/?scenario=onboarding&onb=ready&size=1440x900&clean`: Start learning starts the suggested lesson (no suggestion → the Library).

Shots (`/Users/tripi/sand hacks/miyagi-v2/screens/round2/`): `launch-before-pill-gear.jpg`, `launch-after-pill-nogear.jpg`, `launch-after-idle-pill.jpg`, `launch-after-pill-menu.jpg`, `launch-after-library-home.jpg`, `launch-onboarding-ready.jpg`, `launch-after-start-learning.jpg`.

**Check on the Mac (unverified here):** Dock / Spotlight / Launchpad reopen while running opens the Library (or setup); the Tray icon shows and its four rows work; right-click on the pill pops the native menu over the non-focusable overlay panel; the Library comes to the front over VS Code; a login launch stays quiet; on a notched Mac the pill sits just under the notch band.

## Core requests
1. `ctx.openLauncher()` / `ctx.openSettings(section?)` in `MainContext`, so main features don't relay through the overlay renderer (`feat:launch:open`).
2. Re-run `fitPillTop` on `display-metrics-changed` once renderers can take a new `pillTop` live (today it's fixed per launch, in the launch args).
3. `Settings…` in the app menu (overlay-raise's `Menu.setApplicationMenu`) with ⌘, while an app window is focused.

## Notes
- No email to Adrian from this session; the lane is claimed by its draft PR.
