# overlay-gate

**Status:** done, fix round 1 · **Branch:** `michael/app-overlay-gate` (off `michael/v2-integration`)

## Goal
Michael, every launch of the installed app: "Right when it opens, it just opens up everything." Launch must start
from new: sign in first, setup when he reaches it, and nothing else until he picks a lesson. Main owns that gate
(lane login-first). This lane is the renderer backstop: nothing in the overlay window draws, asks or schedules before
the gate opens, even if main shows the overlay early. It covers launch surfaces that are not lesson events, which
main's RunGuard (`main/freshStart.ts`) cannot see.

## Owns
- `app/src/renderer/src/core/gate.ts` (new): the `useGate` store
- `app/src/renderer/src/core/Overlay.tsx`
- `app/src/renderer/src/features/tips/*` (new `tips/gate.ts`, edits in `tips/index.tsx`)
- `app/src/renderer/src/features/updates/index.tsx`
- `app/src/renderer/src/features/errors/index.tsx`, `errors/store.ts`
- `app/src/renderer/src/features/progress/index.tsx`, `progress/store.ts`
- `app/src/renderer/src/features/launch/index.tsx` (only its `feat:launch:open` listener, `onLaunchOpen`)
- `app/test/overlayGate.test.ts` (new)

## Contract (produced by lane login-first; not created here)
- `onboarding:get` answers with a `gate` field `{ login, setup, open }` (plus `profile` in the login-first draft).
- main broadcasts `feat:onboarding:gate` with the same shape.

## What it does
- `core/gate.ts`: `useGate { open, known }`. Closed until main first answers. Asks `onboarding:get` (the same
  `bridge.invoke` features/onboarding uses) once, the tick after load, and listens to `feat:onboarding:gate`.
  Only `open === true` opens it. An answer without `gate` (a main from before the gate) reads OPEN, so this lane
  merges alone. A broadcast outranks an answer that lands after it. Failures:
  - Electron's `No handler registered for 'feat:onboarding:get'` (a main from before onboarding:get) is the only
    rejection that reads as an older main: after `RETRIES` (3) of them, `RETRY_MS` (1 s) apart, the gate opens.
  - Any other rejection (main's handler threw: a bad onboarding.json, an error in its sign-in check) keeps the gate
    closed. It asks again with a capped backoff (1 s, doubling, at most `MAX_RETRY_MS`, 15 s) until main answers.
  - A `feat:onboarding:gate` broadcast stops the retries, and later results never override it.
  Helpers: `useGateOpen()`, `gateIsOpen()`, `onGateOpen(fn)`, `onGateClose(fn)`, `isNoHandler(err)`.
- `Overlay.tsx`: while closed it renders `null`, so no layer (drawer, player, spotlight, tips) and no Island (pill,
  cards, the pill's "miyagi is getting ready" line). Global shortcuts are ignored. Once it was open and closes again
  (sign-out), the overlay tells main and the engine that its rects are now empty, once.
- tips: the loop, and with it the STARTUP_MS clock, starts only once the gate is open. `onboarding:get` polling and
  the tray ask wait for it. "Ask miyagi anything" and the menu bar coach mark can't show before it opens.
- updates: `upd-card` is active only with the gate open; its QUIET_MS wait starts only then.
- errors: `errors:crash-pending` is asked once per launch, the first time the gate opens (not at load). Every errors
  island mode (crash, limit, offline, the pill lines) is `useActive && open`.
- launch: main's `feat:launch:open` (the tray's 'Start a lesson' and 'Settings…') is ignored while the gate is
  closed, so the tray can't open the launcher (and from it a lesson: VS Code, capture, video) before sign-in.
- progress: `engine.hello` arrives before `whenReady`. The caps ask and the launch review check (`progress.get`) wait
  for the gate, then run. A gate that closes again drops a pending check. The `review` mode is `useActive && open`.

## Test
`cd app && node --import tsx --import ./test/setup.mjs --test --test-force-exit test/overlayGate.test.ts`.
Renders the real Overlay and island modes in Node (fake bridge; registry, scenarios, assets and Island stubbed). It
fails on `origin/michael/v2-integration`. Also covers: `launch:open` 'launcher' and 'settings' with the gate closed
(no `launcher:toggle`, no `settings:open`) and open (one each); the retry path (no handler past `RETRIES` opens;
any other rejection stays `{open:false}` and keeps asking; a broadcast during the retries wins).

## Follow-ups (not this lane)
- **Tips 'seen' state is likely lost on every packaged launch.** `tips/store.ts` keeps it in `localStorage`, under
  the packaged renderer's origin. `main/serve.ts` listens on port 0, so the origin (`http://127.0.0.1:<random>`)
  changes every launch, and so does its storage. Fix: a `tips` field in prefs (common/prefs.ts + sanitizePrefs).
  `tips/store.ts` already switches to prefs once `DEFAULT_PREFS` has the key. Core request.
- `updates/store.ts` still asks `updates:get` at load (main's cached view, no network from the renderer). Harmless,
  but not gated. Owner: updates.
- `core/prefs.ts` and `features/onboarding/store.ts` also ask main at load (`prefs:get`, `onboarding:get`). They read
  state and draw nothing in the overlay.
- The progress window's own `requestProgress()` is not gated. It opens only on a click, after the gate.
- `useOnboardingDone` in tips still polls `onboarding:get` every 2 s until setup is done. With the gate contract, the
  gate broadcast could replace it.

- Merged alone, this lane changes nothing Michael sees: today's main answers `onboarding:get` without `gate`, so the
  gate opens at once. The behaviour he asked for needs login-first. Before sign-in, main still: starts the engine at
  whenReady (`setupLocalEngine`); opens the Library on a cold launch once onboarding is done (launch.ts, the flow
  layer, not the login); serves the launcher global shortcut and the tray. Engine-side resume or VS Code reopen on
  engine start: claude/eng-fresh-launch and app-engine-isolation (dev and real apps both default to
  ws://localhost:8787).

## Core requests
- `tips` in prefs (above).
- **login-first: gate main's own launcher paths.** `index.ts` `openLauncher` runs from the launcher global shortcut
  (`globalShortcut.register(platform.accelerators.launcher, ...)`) and from `second-instance`, and the tray's 'Start
  a lesson' sits in `main/features/launch.ts`. The shortcut and second-instance go straight to main and never pass
  through this renderer, so this lane can't stop them. While the gate is closed, `openLauncher` should refuse, the
  tray's 'Start a lesson' and 'Settings…' should be disabled (or route to sign-in), and the Library-on-launch in
  launch.ts should wait for the gate. Add a freshStart-style `.check.ts`: with the gate closed, onboarding does not
  open the Library, `openLauncher` is refused, and no player reveal happens.
