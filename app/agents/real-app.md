# real-app

**Status:** pass 1 done (typecheck, `ship:mac` and `install-local.sh --dry-run` verified; the installed app itself not opened in this lane) · **Priority:** P1 · **Port:** 5403 (no UI) · **Branch:** `michael/app-real-app`

## Goal
Michael uses the real built miyagi every day, as its own app: "miyagi" in the menu bar, Dock, ⌘Tab, Activity Monitor, About panel and the macOS permission prompts, with the bonsai icon. Never "Electron". One command builds and installs it; opening it from Spotlight just works, with a clear, documented choice of engine.

## What changed
- **Identity.** `electron-builder.yml`: `CFBundleName` / `CFBundleDisplayName` miyagi (explicit, next to `productName`), `copyright` (About panel and `NSHumanReadableCopyright`), Windows shortcut `miyagi` (lowercase brand). `package.json`: `productName: miyagi` (Electron reads it at startup, so `app.name` and userData `~/Library/Application Support/miyagi` are right even before any feature loads; that's the folder already in use), lowercase description, `author` (silences the electron-builder warning), script `install:local`. `scripts/ship-mac.sh`: the helper apps' `CFBundleName` said "Electron Helper (…)"; now it matches their display name ("miyagi Helper (…)") before signing.
- **New `src/main/identity.ts`:** `app.setName('miyagi')` (backstop), About panel options (app version + the engine commit inside the app), and in `npm run dev` only, the Dock icon is the bonsai (the dev name stays "Electron": that comes from Electron.app's bundle).
- **Engine (`src/main/localEngine.ts`):**
  - Engine mode: `bundled` (default, what users get: the engine inside the app + the miyagi cloud) or `dev` (never start or install an engine, only connect to `ENGINE_URL`, default :8787; the state reads `external`, so onboarding says "Running in Terminal" and Restart says to restart it there). Set by env `MIYAGI_ENGINE` or, for a Finder / Spotlight launch, `userData/engine.json` `{"engine": "dev", "cloud": "off"?}`. `cloud: off` sets `MIYAGI_CLOUD_URL=off` before `features/cloud.ts` sets up, so a dev engine uses its `.env` keys. Env always wins.
  - Port 8787 already taken: before, the app always treated it as "external". A force-quit or crashed miyagi leaves its own engine running with the old launch's token (the engine refuses any other token), so the next launch could never connect. Now the app writes `~/miyagi/engine/run/app-engine.json` (pid) when it starts an engine; on launch, a busy port whose pid file names a live process that is provably this app's engine (its command line starts with the app's exact Python or launcher, never just the module name, and its `ps -o lstart` is within 10 s of the pid file's `at`) is reclaimed (SIGTERM its group, SIGKILL after 5 s) and a fresh engine starts. Anything else on the port stays the user's (unchanged), and `engine.log` says which case happened.
- **New `scripts/install-local.sh`** (`npm run install:local`): ship build → copy miyagi.app out of the dmg → verify signature and `CFBundleName` → quit the installed miyagi (SIGTERM to `/Applications/miyagi.app/Contents/MacOS/miyagi` only, which Electron makes a normal quit; no AppleScript, so no Automation prompt; SIGKILL after 10 s) and a dev Electron copy of this app (SIGTERM, main process only) → two same-volume renames into `/Applications/miyagi.app` (rollback if the second fails) → old app to `~/miyagi/app-backups.noindex/miyagi-<date>.app`, keep 2 → strip quarantine → `lsregister -f` → engine mode (`--engine dev|bundled`, `--cloud off`; `--mode-only`, or `--skip-build` with `--engine`, only writes/removes engine.json and reports, so a mode switch never reinstalls or prunes backups) → report: what's on :8787, a `~/Applications/miyagi.app` dev launcher with the same name, and the TCC re-grant steps (System Settings path + `tccutil reset ScreenCapture|Accessibility|AppleEvents dev.sandhacks.miyagi`). `--dry-run` prints every action and changes nothing; `--skip-build`, `--open`, `--ship <opts>`.
- **`electron-builder.yml`:** Electron's generic Microphone / Camera / Bluetooth / Audio capture usage strings are replaced with plain miyagi copy ("miyagi doesn't use the microphone."), so any prompt macOS shows names miyagi.
- **`SHIP.md`:** "Daily use on your own Mac", "Which engine" (table + how to switch + why dev mode exists), the pid-file reclaim and About panel under "How it works".

## Core changes in this lane (core files, kept tiny and additive)
- `src/main/index.ts`: `import { setupIdentity } from './identity'` and one `setupIdentity()` call at the top of `whenReady` (2 lines).
- None in `features/launch.ts` or `overlay-raise.ts`: both are untouched on this branch (fix round 2 dropped the tray edit; it is a Core request below).
- `src/main/localEngine.ts`: `engineMode()` (exported), the pid file (removed again on a normal quit), `reclaimOwnLeftover()` with `isOwnEngineCommand()` and `startedWhenSaved()`, one extra condition in `wanted`. Existing behavior is unchanged when there's no pid file and no engine mode set.

## Verified (Nov 20)
- `npm run typecheck` passes.
- `npm run ship:mac` passes: `dist/Miyagi-Mac.dmg` 126 MB, engine `origin/integration/live@2db862c3`. `plutil -p` on the built app: `CFBundleName` / `CFBundleDisplayName` / `CFBundleExecutable` miyagi, `CFBundleIdentifier` dev.sandhacks.miyagi, `LSUIElement` true, both usage strings name miyagi, `NSHumanReadableCopyright` © 2026 miyagi, icon.icns is the bonsai, helpers named "miyagi Helper (…)" in both `CFBundleName` and `CFBundleDisplayName`, `codesign --verify --deep --strict` OK (in `dist/` and inside the mounted dmg).
- `install-local.sh --dry-run` (also with `--skip-build --engine dev --cloud off`): every step printed, nothing changed; it found the dev Electron copy and the run-live engine on :8787.

## Fix round 1 (Nov 20)
- Reclaim can no longer hit a dev engine: verified the ownership check rejects the run-live engine's command line (pid 14925) for bundled, launcher and unknown runtimes, and accepts the app's own Python / launcher lines; `lstart` parses in the C locale.
- `install-local.sh --dry-run --mode-only --engine dev --cloud off`, `--dry-run --skip-build --engine bundled` (mode only), `--dry-run --mode-only` (error), `--dry-run --skip-build` (full install) all behave; `bash -n` OK; `--help` prints the new header.
- `npm run typecheck` passes. Info.plist strings checked by parsing the YAML (no `ship:mac` rebuild in this round).

## Fix round 2 (Nov 20)
- `install-local.sh`: backup pruning no longer aborts the install when `~/miyagi/app-backups.noindex` holds no `miyagi-*.app` (`ls` exit 1 under `pipefail`); `{ ls ... || true; }`. Sandbox: empty folder rc 0 and the next line runs; four backups with keep 2 prunes the two oldest; the old line gives rc 1.
- About location fixed in `SHIP.md` and `identity.ts`: tray / pill menu > About miyagi, not the app menu (which has only Hide / Quit).
- `features/launch.ts` restored to the launch-ease version (this lane's 13-line tray item removed) and filed under Core requests, so no merge conflict with that lane. Until it lands, the About panel is configured but has no menu entry.
- `npm run typecheck` passes; `bash -n` and `--dry-run` OK.

## Not verified (needs Michael's Mac session)
- Running `npm run install:local` for real, opening the installed app, the About panel (once the tray item lands), the Screen Recording prompt naming miyagi, and the pid-file reclaim after a force quit. None were run here (this lane must not touch /Applications or the running app).

## Core requests
- Launch-ease lane (`src/main/features/launch.ts`, tray / pill menu): add "About miyagi" on macOS, just above "Quit miyagi", so the About panel set up in `main/identity.ts` has a menu entry with no app window open (the accessory app's own menu shows only while an app window is in front). Suggested item, as dropped from this branch in fix round 2:
  ```ts
  ...(process.platform === 'darwin'
    ? [{ label: 'About miyagi', click: (): void => { ctx.app.focus({ steal: true }); ctx.app.showAboutPanel() } } satisfies MenuItemConstructorOptions]
    : []),
  ```
- Optional, core owner of `src/main/features/overlay-raise.ts`: the application menu is `{ label: 'miyagi', submenu: [{ role: 'hide' }, { role: 'quit' }] }`. Add `{ role: 'about' }` first if About should also live there (it shows only while an app window is in front).
- `main/serve.ts` CSP allows only port 8787: an `ENGINE_URL` on another local port works for the WebSocket from main but not for renderer fetches / media. If a second local engine port is ever wanted, derive the CSP from `ENGINE_URL`.
- `features/library.ts`, `overview.ts`, `presenter.ts` and `index.ts` each read `process.env.ENGINE_URL` with their own default; one shared `engineUrl()` in core would keep them in step.

## Notes
- Dev (`npm run dev`) still shows "Electron" in the Dock and ⌘Tab: that name comes from Electron.app's own bundle, and only a built app replaces it. That's why the daily flow is `npm run install:local`.
- Users who never set an engine mode see no change except the force-quit recovery.
