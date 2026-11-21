# real-app

**Status:** pass 1 done (typecheck, `ship:mac` and `install-local.sh --dry-run` verified; the installed app itself not opened in this lane) · **Priority:** P1 · **Port:** 5403 (no UI) · **Branch:** `michael/app-real-app`

## Goal
Michael uses the real built miyagi every day, as its own app: "miyagi" in the menu bar, Dock, ⌘Tab, Activity Monitor, About panel and the macOS permission prompts, with the bonsai icon. Never "Electron". One command builds and installs it; opening it from Spotlight just works, with a clear, documented choice of engine.

## What changed
- **Identity.** `electron-builder.yml`: `CFBundleName` / `CFBundleDisplayName` miyagi (explicit, next to `productName`), `copyright` (About panel and `NSHumanReadableCopyright`), Windows shortcut `miyagi` (lowercase brand). `package.json`: `productName: miyagi` (Electron reads it at startup, so `app.name` and userData `~/Library/Application Support/miyagi` are right even before any feature loads; that's the folder already in use), lowercase description, `author` (silences the electron-builder warning), script `install:local`. `scripts/ship-mac.sh`: the helper apps' `CFBundleName` said "Electron Helper (…)"; now it matches their display name ("miyagi Helper (…)") before signing.
- **New `src/main/identity.ts`:** `app.setName('miyagi')` (backstop), About panel options (app version + the engine commit inside the app), and in `npm run dev` only, the Dock icon is the bonsai (the dev name stays "Electron": that comes from Electron.app's bundle).
- **Engine (`src/main/localEngine.ts`):**
  - Engine mode: `bundled` (default, what users get: the engine inside the app + the miyagi cloud) or `dev` (never start or install an engine, only connect to `ENGINE_URL`, default :8787; the state reads `external`, so onboarding says "Running in Terminal" and Restart says to restart it there). Set by env `MIYAGI_ENGINE` or, for a Finder / Spotlight launch, `userData/engine.json` `{"engine": "dev", "cloud": "off"?}`. `cloud: off` sets `MIYAGI_CLOUD_URL=off` before `features/cloud.ts` sets up, so a dev engine uses its `.env` keys. Env always wins.
  - Port 8787 already taken: before, the app always treated it as "external". A force-quit or crashed miyagi leaves its own engine running with the old launch's token (the engine refuses any other token), so the next launch could never connect. Now the app writes `~/miyagi/engine/run/app-engine.json` (pid) when it starts an engine; on launch, a busy port whose pid file names a live engine process (command line `server.orchestrator.main` / `miyagi-engine`) is reclaimed (SIGTERM its group, SIGKILL after 5 s) and a fresh engine starts. Anything else on the port stays the user's (unchanged), and `engine.log` says which case happened.
- **New `scripts/install-local.sh`** (`npm run install:local`): ship build → copy miyagi.app out of the dmg → verify signature and `CFBundleName` → quit the installed miyagi (AppleScript, guarded by `is running` so it never launches it) and a dev Electron copy of this app (SIGTERM, main process only) → two same-volume renames into `/Applications/miyagi.app` (rollback if the second fails) → old app to `~/miyagi/app-backups.noindex/miyagi-<date>.app`, keep 2 → strip quarantine → `lsregister -f` → engine mode (`--engine dev|bundled`, `--cloud off`) → report: what's on :8787, a `~/Applications/miyagi.app` dev launcher with the same name, and the TCC re-grant steps (System Settings path + `tccutil reset ScreenCapture|Accessibility|AppleEvents dev.sandhacks.miyagi`). `--dry-run` prints every action and changes nothing; `--skip-build`, `--open`, `--ship <opts>`.
- **`SHIP.md`:** "Daily use on your own Mac", "Which engine" (table + how to switch + why dev mode exists), the pid-file reclaim and About panel under "How it works".

## Core changes in this lane (core files, kept tiny and additive)
- `src/main/index.ts`: `import { setupIdentity } from './identity'` and one `setupIdentity()` call at the top of `whenReady` (2 lines).
- `src/main/features/overlay-raise.ts` (owned by the overlay-raise lane): the app menu gains `{ role: 'about' }` and a separator ahead of Hide / Quit, so About miyagi is reachable (1 line).
- `src/main/localEngine.ts`: `engineMode()` (exported), the pid file, `reclaimOwnLeftover()`, one extra condition in `wanted`. Existing behavior is unchanged when there's no pid file and no engine mode set.

## Verified (Nov 20)
- `npm run typecheck` passes.
- `npm run ship:mac` passes: `dist/Miyagi-Mac.dmg` 126 MB, engine `origin/integration/live@2db862c3`. `plutil -p` on the built app: `CFBundleName` / `CFBundleDisplayName` / `CFBundleExecutable` miyagi, `CFBundleIdentifier` dev.sandhacks.miyagi, `LSUIElement` true, both usage strings name miyagi, `NSHumanReadableCopyright` © 2026 miyagi, icon.icns is the bonsai, helpers named "miyagi Helper (…)" in both `CFBundleName` and `CFBundleDisplayName`, `codesign --verify --deep --strict` OK (in `dist/` and inside the mounted dmg).
- `install-local.sh --dry-run` (also with `--skip-build --engine dev --cloud off`): every step printed, nothing changed; it found the dev Electron copy and the run-live engine on :8787.

## Not verified (needs Michael's Mac session)
- Running `npm run install:local` for real, opening the installed app, the About panel, the Screen Recording prompt naming miyagi, and the pid-file reclaim after a force quit. None were run here (this lane must not touch /Applications or the running app).

## Core requests
- Tray menu (`features/launch.ts`): an "About miyagi" item would make About reachable with no app window open (the app menu only shows while an app window is in front, since miyagi is an accessory app).
- `main/serve.ts` CSP allows only port 8787: an `ENGINE_URL` on another local port works for the WebSocket from main but not for renderer fetches / media. If a second local engine port is ever wanted, derive the CSP from `ENGINE_URL`.
- `features/library.ts`, `overview.ts`, `presenter.ts` and `index.ts` each read `process.env.ENGINE_URL` with their own default; one shared `engineUrl()` in core would keep them in step.

## Notes
- Dev (`npm run dev`) still shows "Electron" in the Dock and ⌘Tab: that name comes from Electron.app's own bundle, and only a built app replaces it. That's why the daily flow is `npm run install:local`.
- Users who never set an engine mode see no change except the force-quit recovery.
