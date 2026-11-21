# login-first

**Status:** pass 1 done (offline tests and typecheck green; not run in Electron) · **Branch:** `michael/app-login-first` (off `michael/v2-integration` d959e0e9)

## Goal
Michael, Nov 21, on the installed app: "Right when it opens, it just opens up everything ... It needs to allow me to log in first, like it's just starting from new."

A launch is a start from new. The first and only thing on screen is the home window at the login: Continue with Google, or Continue without an account. Then setup. The overlay (pill, cards, shortcut bar), the launcher, the global keys and the full tray exist only once the **launch gate** opens. Nothing prompts for Screen Recording or Accessibility until a setup button is clicked.

## The launch gate
- Rules: `src/common/gate.ts` (`GateView {login, setup, open}`, `firstNeeded`, `cleanGate`). Live state: `src/main/gate.ts` (`setGatePart`, `gateIsOpen`, `gateView`, `onGate`, `gateCore`, `resetGateForTests`). Nothing is saved: every launch starts closed and the features report again.
- **login** (features/auth.ts): open with a stored Google session (auth.bin), after a Google sign-in, after "Continue without an account" in this run, with login off (`MIYAGI_LOGIN=0`), or `MIYAGI_SKIP_LOGIN=1`. Closed by `auth:sign-out`. The guest choice is memory only: `login.json` is never read or written again (an old one is ignored), so every launch without a Google session starts at the login.
- **setup** (features/onboarding.ts): open when onboarding.json says done or later ("Set up later"); `onboarding:resume` closes it until setup is done or put off again.
- `MIYAGI_SKIP_ONBOARDING=1` forces it open (dev, tests).
- Broadcast `feat:onboarding:gate` (the `cleanGate` view) on every change; `onboarding:get` carries `gate` and `login: needsLogin()` (whether or not the setup flow is on). Lane overlay-gate's renderer store listens to exactly these.

## What changed
- **index.ts** (Core): the overlay and launcher are still created hidden at whenReady; `gateCore({overlay, launcherKey, closed})` shows the overlay and registers the launcher key only while the gate is open, and hides it, unregisters the key, closes the launcher and hands the lesson keys back when it closes. `openLauncher()` and `registerActionShortcuts()` return early while closed; the lesson.ready hook and the pill's `launcher:toggle` check the gate; `app.on('second-instance', () => openLauncher())` is gone. The engine connect and `setupLocalEngine` are untouched (lanes launch-quiet and engine-isolation).
- **features/launch.ts** (Core-adjacent): single-instance lock on mac in dev too; `onboarded()` reads the gate, never `prefs.json` onboarded; while closed the tray shows only Open miyagi and Quit miyagi (rebuilt on every gate change) and `askOverlay` / `launch:menu` do nothing; a cold launch always opens home (except at login-item start or `MIYAGI_QUIET_LAUNCH=1`); the only `second-instance` handler (opens home).
- **features/auth.ts**: gate reports above; "Continue without an account" stays on the login screen at all times (unchanged in Login.tsx).
- **features/onboarding.ts**: gate reports, the broadcast, `onboarding:get {login, gate}`; at did-finish-load home opens whenever the gate is closed (not only before setup is done), never a second time when launch.ts opened it first; `onboarding:relaunch` in a dev copy only logs "restart npm run dev" (it used to `open -n ~/Applications/miyagi.app`, a second miyagi fighting the dev one). `onboarding:prompt` unchanged: still only from a setup click.
- **features/front-app.ts**: `handBack` only while the gate is open (never steals focus from the login).
- **Renderer** `shell/flow/store.ts`: the flow is on whenever the gate is closed, every launch, starting at `firstNeeded` (login before setup; the intro still plays once per Mac). In Electron the window waits on `pending` (a few ms of plain paper) instead of guessing 'off', so home never flashes over a closed gate. After the login, setup already through goes straight home. A sign-out while home shows brings the flow back at the login. `onboarding/store.ts` keeps the gate (`gate`, `neededFirst()`) and sets `Prefs.onboarded` only once the setup walk really showed. `FlowLayer.tsx` marks setup done only on the setup / ready screens, never on the login.
- **prefs** (main + common): no change was needed. The gate needs nothing stored; the stalled lane's profile field and readPrefs/patchPrefs were for About you, which Michael did not ask for.

## Core requests (edits made in core, Michael's explicit priority for this lane)
1. `src/main/index.ts`: overlay show and launcher key behind the gate (`gateCore`), early returns in `openLauncher` / `registerActionShortcuts`, gated lesson.ready hook and `launcher:toggle`, `second-instance` removed. Reason: these opened the overlay, the launcher and its key at launch before any login.
2. `src/main/features/launch.ts`: tray, `askOverlay`, cold launch, single-instance lock, no prefs.json fallback. Reason: the tray offered Start a lesson / Settings before login, and `prefs.json onboarded:true` skipped the first run after onboarding.json was reset.
3. `src/main/gate.ts` and `src/common/gate.ts` (new core files). Reason: one shared gate state for main and renderer.
4. Prefs (`src/main/prefs.ts`, `src/common/prefs.ts`): none.
5. Tests outside the lane's own files: `test/fakes/electron.ts` gained Menu, Tray, nativeImage, globalShortcut, systemPreferences, desktopCapturer, BrowserWindow and `app.on` fakes (additive); `test/auth.test.ts` line 61 now expects **no** login.json after a sign-in.

## Done when
- `cd app && npm run typecheck`
- `node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts` (gate.test.ts, loginFirst.test.ts)
- `npx tsx src/main/loginFirst.check.ts` (index.ts source scan: fails on `origin/michael/v2-integration`'s index.ts)

## Open
- Unverified in Electron (offline lane): the tray rebuild, the overlay showing on the gate's open in a real run, the single-instance lock in `npm run dev`.
- A lesson.ready that arrives while the gate is closed does not register the lesson keys when the gate opens later; the next lesson.ready does. With lane eng-fresh-launch (no auto-resume) no lesson starts before the gate opens.
- The Dock icon: appWindows.ts shows it when an app window opens; unchanged here.
- The browser stage's `onboarding:get` stand-in (onboarding/web.ts) sends no `gate`, so the stage keeps the old flow rule.
