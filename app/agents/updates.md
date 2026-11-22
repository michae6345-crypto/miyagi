# updates

**Status:** first pass done · **Port:** 5611 · **Branch:** `michael/app-updates`

## Goal
Updates people never have to think about. miyagi looks for a newer release on launch and every 6 hours. When there is one, and no lesson is running, a calm card grows from the pill: "A new miyagi is ready." One primary, **Download**, opens the installer in the browser; **What's new** folds the notes open; **Later** (or Esc) puts it away for 24 hours. After Download the card turns into three install steps and offers **Quit miyagi**. Nothing installs by itself: the app is ad-hoc signed, so electron-updater cannot replace it on the Mac.

## Owns
- `app/src/main/features/updates.ts`: the check (fetch, compare, timers, snooze file, IPC)
- `app/src/renderer/src/features/updates/`: `manifest.ts` (pure: source, parser, semver, shared with main), `store.ts`, `Card.tsx`, `index.tsx`, `web.ts` (stage stand-ins)
- `app/mock/scenarios/updates.json`: an idle desktop

## How it works
| | |
|---|---|
| Where it looks | A packaged app: always the GitHub Releases API of the official repo, `https://api.github.com/repos/adrian-erlikhman/miyagi/releases/tags/<mac\|windows>`, the same one `scripts/ship-mac.sh` publishes to. It ignores the environment (A12, R33: a `launchctl setenv` must not steer it). A dev run: `MIYAGI_UPDATE_URL` (a manifest, https; http only for localhost) or the Releases API for `MIYAGI_RELEASE_REPO`; `MIYAGI_UPDATE_URL=off` turns checks off. |
| What it may offer | Only an official release asset (R26): exactly `https://github.com/adrian-erlikhman/miyagi/releases/download/<tag>/<asset>`, asset `Miyagi-Mac.dmg` (Mac) or `Miyagi-Windows-Setup.exe` (Windows), fully uploaded. Anything else: no card (`manifest.ts` `officialInstaller`). The SHA-256 is not checked against the file yet (TODO(R26) in `main/features/updates.ts`). |
| When | 45 s after launch (after the engine start), then every 6 h, and on wake when the last check is older than 6 h. A failed check tries again after 1 h. Only in a packaged app, unless `MIYAGI_UPDATE_URL` is set. |
| What is sent | A plain GET with `User-Agent: miyagi/<version>`. No cookies, no install token, nothing about the learner. |
| Comparing | semver against `app.getVersion()`. A prerelease is offered only to someone already on a prerelease. |
| Trust | The installer URL must pass the safeOpen allowlist (`isAllowedUrl`) or the release is ignored. Main keeps the URL; the renderer never passes one (`updates:download` has no arguments). |
| Snooze | `userData/updates.json`: `{snoozedUntil, openedVersion, checkedAt}`. A manual check that finds an update clears the snooze. |
| Never mid-lesson | The card (island priority 45, the lowest card) shows only with no lesson, no build and no pause, after 4 s of that. A lesson that starts hides it; it comes back when the lesson ends. Every error, lesson and completion card wins over it. |

### Manifest format (any https host on the allowlist, e.g. `downloads.miyagi.study` later)
```json
{ "version": "0.2.0", "notes": ["Lessons open faster."], "url": "https://downloads.miyagi.study/mac/Miyagi-Mac.dmg", "sha256": "<64 hex>", "size": 182400000 }
```
or per platform: `{ "mac": { ... }, "windows": { ... } }`. `dmg` is accepted for `url`.

### Reading a GitHub release
The rolling `mac` release has no version in its tag, so the version is the first semver in `tag_name`, then the release **title** (`miyagi 0.2.0`), then a `Version: 0.2.0` line in the body, then the installer's file name. No version found = no offer (safe default). Installer: the `.dmg` asset (`.exe` on Windows), the one naming this arch when there are several. sha256: the asset's `digest` (GitHub adds `sha256:<hex>`), else a `sha256: <hex>` body line. Notes: the body's plain lines (headings, markdown marks, links, version and hash lines dropped; at most 6).

### IPC (all return `UpdateView`, see `manifest.ts`)
`updates:get` (no network) · `updates:check` · `updates:download` · `updates:later` · `updates:quit` (returns true). Broadcast: `feat:updates`.

## Test
`npm run dev:web -- --port 5611` → `http://localhost:5611/?size=1440x900&scenario=updates`. The card grows from the pill after about 4 s. Click What's new, Download (the install steps), Esc (Later).
Variants: `&upd=current | failed | off | snoozed | pre` (no card for all of these), `&os=win` (Windows steps). Gating: `?scenario=drawer&upd=available` shows a lesson and no update card.

Screens: `/Users/tripi/sand hacks/miyagi-v2/screens/round3/updates-*.jpg` (offer, whats-new, install-steps, steps-windows, later, waits-mid-lesson).

## Core requests
1. **settings lane: "Check for updates"** in Settings (General, under the version, or the sidebar foot). Suggested row: label "Updates", caption from the view, one QuietButton.
   - Press: `const v = await bridge.invoke<UpdateView>('updates:check')` (type from `features/updates/manifest`), or import `checkNow()` from `features/updates/store`.
   - Captions: `phase 'checking'` "Checking…" with the Spinner · `'current'` "You have the latest miyagi." · `'available'` "miyagi {latest.version} is ready." with a **Download** button (`bridge.invoke('updates:download')`) · `'failed'` "Could not check. Try again later." · `'off'` hide the row.
   - In the stage, `features/updates/web.ts` answers these (add `&upd=available` to see an offer).
2. **scripts lane (`scripts/ship-mac.sh --publish`)**: give the `mac` release a version, or the app can't tell it is newer. After the upload: `gh release edit mac --repo "$REPO" --title "miyagi $(node -p "require('./package.json').version")" --notes-file <notes>` (the notes file may end with `Version: x.y.z`). Bump `package.json` `version` for every published build. Same for `windows`. Optional: also upload a `miyagi-update.json` manifest and set `MIYAGI_UPDATE_URL` at build time (or move to R2 at `downloads.miyagi.study/mac/latest.json`).
3. **safeOpen: no change needed.** `github.com` (release downloads) and `miyagi.study` subdomains (a future `downloads.miyagi.study`) are already allowlisted. A different download host (e.g. a raw `*.r2.dev` URL) would need a line in `ALLOWED_HOSTS`.
4. **integrator: `agents/ports.json`**: add `"updates": 5611`.

## Signed-app path (when the Apple Developer account exists)
Design, flag and inert code: `agents/auto-update.md` (`features/updates/auto.ts`, `main/features/autoUpdate.ts`, off behind `AUTO_UPDATE_ENABLED`).

Today: no auto-install, by design. Once the app is signed with a Developer ID and notarized (DISTRIBUTION-PLAN section 3), switch to in-place updates:

1. `npm i electron-updater` (a dependency, not dev).
2. `electron-builder.yml`:
   ```yaml
   mac:
     target: [dmg, zip]          # Squirrel.Mac installs from the zip; the dmg stays for first downloads
     identity: "Developer ID Application: <Name> (<TEAMID>)"
     hardenedRuntime: true
     notarize: true
   publish:
     provider: github            # or: generic, url: https://downloads.miyagi.study/mac
     owner: adrian-erlikhman
     repo: miyagi
   ```
   electron-builder then writes `latest-mac.yml` (version, sha512 of the zip) next to the artifacts; upload it with them. A rolling `mac` tag does not work with the github provider (it reads the latest *versioned* release): publish tagged releases (`v0.2.0`), or use the generic provider on R2.
3. In `src/main/features/updates.ts`, when `app.isPackaged` and the app is signed: `autoUpdater.autoDownload = true; autoUpdater.autoInstallOnAppQuit = true; autoUpdater.checkForUpdates()` on the same timers, and map its events to the same `UpdateView` (`update-available` → available, `update-downloaded` → a "Restart to update" card, primary "Restart" = `autoUpdater.quitAndInstall()`, still never mid-lesson). Keep the manifest path as the fallback for unsigned dev builds.
4. Windows: `nsis` target plus the same `publish` block; electron-updater works there without an Apple account, but SmartScreen warns until the installer is code-signed.
5. A stable signature also keeps Screen Recording and Accessibility grants across updates (today every build asks again).

## Notes
- The pure part (`manifest.ts`) was checked with a throwaway script (semver order and prereleases, env parsing, GitHub and manifest shapes, arch pick, notes cleanup): 23 cases, all pass. No vitest, per the round rules.
- Not checked in Electron (no visible windows this round): the 45 s timer, the real GitHub call, `powerMonitor` resume, `updates:quit`.
