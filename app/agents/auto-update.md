# auto-update

**Status:** design + inert code behind a flag (off) · **Priority:** after the Developer ID · **Branch:** `michael/app-auto-update` · **Owner after this pass:** Adrian (signing, releases, site)

## Goal
miyagi updates itself the way a good Mac app does. It finds a new version, downloads it in the background, and installs it when the learner quits. A learner who wants it sooner sees one calm card when no lesson is running: "miyagi 0.3.0 is ready." with **Restart to update**. If miyagi-cloud says a version is too old (a broken engine contract, a security fix, a pulled build), the island shows one card, "Update miyagi", before the next lesson starts. Learners can choose Stable or Beta in Settings.

Today none of this runs. The check-only card (`agents/updates.md`, ROADMAP 1.2) stays the update path until the two locks below open.

## Why not today
- **macOS refuses it for ad-hoc apps.** electron-updater on the Mac hands the zip to Squirrel.Mac (Electron's `autoUpdater`). Squirrel.Mac installs an update only if the new app's code signature meets the running app's designated requirement. An ad-hoc signature (`electron-builder.yml` `mac.identity: null`, then `codesign --force --deep -s -` in `scripts/ship-mac.sh`) has no team and a new hash every build, so the update fails. Without a Developer ID there is nothing for us to fix in code.
- **electron-updater is not a dependency** (`app/package.json`). Per the round rules this PR installs nothing. The code loads it with a dynamic import of a variable name, so the typecheck and the bundle stay green without it.
- **No feed exists yet.** electron-updater reads `latest-mac.yml` plus a `.zip`. Today `ship-mac.sh` builds a dmg only (`mac.target: dmg`, `dmg.writeUpdateInfo: false`).

## Owns (this PR)
| File | What |
|---|---|
| `app/src/renderer/src/features/updates/auto.ts` | Pure (no Electron, no electron-updater): the flag, both locks, `codesign` parsing, channel, feed, `configureUpdater()`, miyagi-cloud's version policy, `AutoView` |
| `app/src/main/features/autoUpdate.ts` | Main feature (auto-discovered). Registers all four `autoUpdate:*` handles in every build. Off: they answer phase `off` (`check` returns the view, `restart` returns false, `channel` saves the choice and returns the view) and nothing else runs: no timer, no network, no `codesign`, no broadcast. On: drives electron-updater |
| `app/test/autoUpdate.test.ts` | Offline tests for the pure part, plus one proving that with the flag off all four handles exist and none starts a timer, `codesign` or a network call |
| `app/agents/auto-update.md` | This brief |

No renderer UI yet (see "Left to build"). Core is not edited here: no change to `package.json`, `electron-builder.yml`, `common/flags.ts` or `main/index.ts`.

## The two locks
1. **The flag.** `AUTO_UPDATE_ENABLED = false` in `features/updates/auto.ts` (move to `common/flags.ts`, see Core requests). In an unpackaged dev run, `MIYAGI_AUTO_UPDATE=1` turns it on and `=0` turns it off. A packaged build ignores the environment (A12, R33: a `launchctl setenv` must not turn updates on or off or point them anywhere).
2. **The build can replace itself.** `canAutoInstall()`: packaged, Mac, `codesign -dv --verbose=2 <miyagi.app>` shows `Authority=Developer ID Application: … (TEAMID)` and a TeamIdentifier, not `Signature=adhoc`, and the .app is not on a mounted dmg (`/Volumes/…`) and sits in a folder it can write. Windows stays off unless someone turns it on (`windows: true`). It is not a launch target, and NSIS updates would need their own decision.

If both locks are open and electron-updater is missing or fails to load, the phase is `unavailable` and the check-only card stays in charge.

The handles do not depend on the locks: `autoUpdate:get`, `:check`, `:restart` and `:channel` are registered in every build, so the Settings "Updates" row (Left to build) works on builds that ship before signing. With lock 1 closed they never start a timer, run `codesign` or touch the network.

## How it works once on
| | |
|---|---|
| Feed | Generic provider, `https://downloads.miyagi.study/<mac\|windows>` (`OFFICIAL_FEED_BASE`), pinned in a packaged build. Dev runs may set `MIYAGI_UPDATE_FEED` (https, or http on localhost) to test against a local folder. |
| Files in the feed | `latest-mac.yml` (stable) or `beta-mac.yml` (beta), plus the zip and its `.blockmap`, all written by electron-builder. `electron-builder.yml` sets `artifactName` only on the dmg (`Miyagi-Mac`), so the zip gets electron-builder's default `${productName}-${version}-${arch}-mac.zip`: `miyagi-<version>-arm64-mac.zip` for the arm64 build DISTRIBUTION-PLAN makes first, `miyagi-<version>-universal-mac.zip` once it is universal. Keep that default: Rollback step 3 needs a versioned name, so never give the zip a fixed `artifactName` like the dmg's. The dmg stays for first downloads from the site. |
| When | 60 s after launch, then every 6 h (`CHECK_EVERY_MS`, the same timer the card uses). `autoUpdate:check` runs a check now. |
| Download | `autoDownload = true`, in the background, with `download-progress` turned into `percent` in the view. |
| Install | `autoInstallOnAppQuit = true`: the update goes in when the learner quits. `autoUpdate:restart` (phase `ready` only) calls `quitAndInstall(false, true)` for "Restart to update". The renderer must call it only when no lesson, build or pause is running (the same gate the update card uses). |
| Integrity | electron-updater checks the zip's sha512 from the yml (https only). Squirrel.Mac then checks that the new app's code signature matches this one's designated requirement (the same Developer ID team). This also closes the update card's open TODO(R26): the app now holds and verifies the bytes. |
| What is sent | The feed GETs, plus the version-policy GET below. No install token, no user, no cookies. |
| Downgrades | `allowDowngrade = false`, always. Rollback means shipping a newer build (see Rollback). `configureUpdater()` sets it last, after `channel`: electron-updater's `channel` setter quietly sets `allowDowngrade = true`. A test pins the order with a fake updater that does the same. |

### Minimum version (miyagi-cloud)
`GET <cloud>/v1/app/version?os=mac&channel=stable`. The host comes from `cloudUrl()` (`main/features/cloud.ts`), so env overrides are ignored when packaged. It sends no token. Answer:
```json
{ "min": "0.2.0", "blocked": ["0.2.3"], "latest": "0.2.4" }
```
- `min`: a version below it is `required` and must update before the next lesson.
- `blocked`: exact versions pulled after release. They are treated the same as being below `min`.
- `latest`: informational. The feed, not this answer, decides what gets downloaded.
- Fail open. If the endpoint is offline, missing or malformed, or the version is unreadable, the answer is `ok`. A cloud outage must never lock anyone out.
- `required: true` in `AutoView` becomes one island card, "Update miyagi", with one primary action. With an update `ready`: **Restart to update**. Still downloading: progress, then the restart. With phase `off` (lock 1 open, lock 2 closed: an ad-hoc or dmg-mounted build) or `unavailable` (no electron-updater): the check-only card's **Download** (opens the dmg). The engine-side guard against an incompatible client stays the engine contract's job. This card is the polite version of that guard.
- The policy check runs only when lock 1 is open, on the same timers as the feed check (60 s, then every 6 h, plus `autoUpdate:check`). Those timers start as soon as lock 1 is open, before lock 2 is read, so the policy also runs in phases `off` and `unavailable`; the feed itself is checked only once electron-updater is loaded. With lock 1 closed (every build today) nothing asks. Wiring the policy into the check-only card for builds with lock 1 closed is a separate decision for Adrian.

### Channels
- `stable` | `beta`, saved in `userData/auto-update.json` and set with `autoUpdate:channel`. Mapped to electron-updater's `latest` | `beta`, so it reads `latest-mac.yml` | `beta-mac.yml`. `allowPrerelease` is on for beta only.
- A prerelease build (`0.3.0-beta.2`) stays on beta even without a saved choice, so a beta tester never silently drops to an older stable. Moving from beta back to stable takes effect at the next stable version that is newer than theirs (no downgrade).
- Release side: a prerelease `version` in `package.json` plus `electron-builder --publish` with `generateUpdatesFilesForAllChannels: true` writes `beta-mac.yml` (and `latest-mac.yml` for stable builds). The beta feed then always holds the newest of beta and stable.

### Rollback
1. **Stop a bad rollout.** Ship with `stagingPercentage: 10` in `latest-mac.yml` (electron-updater supports it on the generic provider). Raise it to 100 when crash reports and telemetry look clean. To stop, set it to 0 or put back the previous `latest-mac.yml`. Installs that already updated keep the bad build (no downgrade). New installs and those still waiting do not get it.
2. **Fix those who already updated (roll forward).** Rebuild the last good code as a higher version (0.2.3 bad → 0.2.4 = 0.2.2's code), publish it, and add `"blocked": ["0.2.3"]` to the cloud policy so 0.2.3 shows "Update miyagi" right away instead of waiting for the 6 h tick and a quit.
3. **Keep the last 3 zips in the feed**, so pointing `latest-mac.yml` back at an older one is just a file edit and needs no rebuild.
4. **If the install itself fails**, Squirrel.Mac leaves the old app in place. The `error` event logs and the phase becomes `failed`. Nothing is half-installed.

### Feed hosting (Adrian's call)
- **Recommended: Cloudflare R2 behind `downloads.miyagi.study`** (generic provider). It works whether or not `michae6345-crypto/miyagi` goes private, needs no token in the app, and `miyagi.study` subdomains are already on safeOpen's allowlist, so the check-only card can switch to it later.
- **Alternative: a public releases repo** (e.g. `adrian-erlikhman/miyagi` as today, or a new `miyagi-releases`) with `provider: github`. It needs versioned tags (`v0.2.0`): the rolling `mac` tag that `ship-mac.sh` uses today does not work with the github provider. Never point the github provider at a private repo: it would need a token in the app.
- The site (`adrian-erlikhman/miyagi`, GitHub Pages) keeps linking the dmg. The feed is only for the app.

## Core requests (for Adrian)
1. **package.json:** add `electron-updater` to `dependencies` (not dev: main loads it at run time from the asar). Nothing else changes. `autoUpdate.ts` already loads it with a dynamic import. Once installed, the local `UpdaterLike` type can be swapped for `import type { AppUpdater } from 'electron-updater'`.
2. **electron-builder.yml (only once the Developer ID exists, DISTRIBUTION-PLAN section 3):** this merges with DISTRIBUTION-PLAN section 3's `mac:` block (keep its `gatekeeperAssess: false` and the rest); it does not replace it.
   ```yaml
   mac:
     target: [dmg, zip]          # Squirrel.Mac installs from the zip
     # No `identity:` line at all (delete today's `identity: null`: null means "never sign", even with a certificate).
     # CI supplies the Developer ID Application certificate through CSC_LINK (base64 .p12) + CSC_KEY_PASSWORD.
     hardenedRuntime: true
     entitlements: build/entitlements.mac.plist
     entitlementsInherit: build/entitlements.mac.plist
     notarize: true              # electron-builder 26: reads APPLE_API_KEY (path to the .p8), APPLE_API_KEY_ID, APPLE_API_ISSUER
   publish:
     provider: generic
     url: https://downloads.miyagi.study/mac
   generateUpdatesFilesForAllChannels: true
   ```
   **Identity.** Do not write `identity: "Developer ID Application: <Name> (<TEAMID>)"`. electron-builder 26.18 refuses it: `app-builder-lib/out/codeSign/macCodeSign.js` `checkPrefix()` throws `InvalidConfigurationError` (`Please remove prefix "Developer ID Application:" …`), so the signed build fails. Either leave `identity` out and let CI hand over the certificate with `CSC_LINK` + `CSC_KEY_PASSWORD` (recommended: no name in the repo, and the keychain on a build Mac is not needed), or write it without the prefix: `identity: "<Name> (<TEAMID>)"`. **DISTRIBUTION-PLAN section 3 (line 101, `identity: "Developer ID Application: <Name> (<TEAMID>)"`) has the same bug; fix it there too.** Its `notarize: true` with `APPLE_API_KEY` / `APPLE_API_KEY_ID` / `APPLE_API_ISSUER` is right for 26.18 (`mac/MacTargetHelper.js`).

   Without the two `entitlements` lines the hardened runtime blocks things miyagi needs. `build/entitlements.mac.plist` (it does not exist yet) should hold:
   - `com.apple.security.cs.allow-jit` and `com.apple.security.cs.allow-unsigned-executable-memory` (Electron, pyobjc's libffi)
   - `com.apple.security.automation.apple-events` (AppleScript to VS Code)
   - `com.apple.security.device.audio-input` (push to talk: miyagi-listen records while Fn+Control is held). DISTRIBUTION-PLAN section 3 is missing this one too; add it there.
   - `com.apple.security.cs.disable-library-validation` only if Python's `.so` extensions fail to load under the hardened runtime

   **Nested code.** Everything executable under `Contents/Resources` must be re-signed with the Developer ID, the hardened runtime and a secure timestamp (`codesign --force --options runtime --timestamp --sign "Developer ID Application: …" --entitlements build/entitlements.mac.plist`), or notarization fails. That means the bundled Python (`Resources/engine/python`: the interpreter and every `.so` / `.dylib`) and `Resources/helpers/miyagi-listen`, which `native/listen/build.sh` signs ad hoc today. electron-builder signs some of these from `extraResources` on its own; check the notarytool log, which lists every unsigned or ad-hoc binary, and sign the rest before the app is sealed. Prefer `mac.binaries`: electron-builder signs those with the same certificate it got from `CSC_LINK`, which sits in a temporary keychain a hand-written `afterPack` `codesign` would have to find. (The full `Developer ID Application: …` name is fine for `codesign` itself; only electron-builder's `identity` rejects the prefix.)

   Also remove the ad-hoc `codesign --force --deep -s -` from `ship-mac.sh` (it overwrites the real signature) and keep `resetAdHocDarwinSignature` only for unsigned CI builds. The fuses stay as they are: electron-builder flips them before it signs.
3. **Release pipeline:** upload `latest-mac.yml` (or `beta-mac.yml`), the zip and its blockmap to the feed after notarization, last of all the yml (so a client never sees a yml whose zip is not there yet). Bump `package.json` `version` for every published build (the zip's default name carries it). Secrets live in CI secrets, never in the repo or the app: `CSC_LINK` (the Developer ID .p12, base64) and `CSC_KEY_PASSWORD` for signing; the App Store Connect key (a CI step writes it to a temporary `.p8` and sets `APPLE_API_KEY` to that path), `APPLE_API_KEY_ID`, `APPLE_API_ISSUER` for notarization; and the R2 keys for the upload.
4. **Flag:** move `AUTO_UPDATE_ENABLED` to `common/flags.ts` beside `VOICE_ENABLED` and the rest, and turn it on in the first signed release.
5. **Wiring in main (`main/index.ts` and `features/updates.ts`):**
   - No registration needed: `features/autoUpdate.ts` is picked up by the `./features/*.ts` glob.
   - `features/updates.ts` should step aside when auto-update is active (phase not `off` or `unavailable`): skip its own timers and card so there are never two update cards. Suggested: `autoUpdate.ts` exports `autoUpdateActive(): boolean`, and `updates.ts` reads it before each check.
   - **Verify install-on-quit with R44.** `will-quit` in `main/index.ts` calls `preventDefault()` while the engine stops, then `app.exit(0)`. Check on a signed build that a downloaded update still installs on that path. If it doesn't, call `quitAndInstall(true, false)` from that `exit()` when `phase === 'ready'`.
   - LSUIElement app: `quitAndInstall` closes every window and quits. Make sure no `close` handler (overlay, player) cancels the close while an install is pending.
6. **miyagi-cloud:** `GET /v1/app/version?os=&channel=`, public, cacheable for 5 min, answering `{min, blocked, latest}`. A config row or env var on the server, so pulling a build needs no deploy.

## Left to build (renderer, after the Core requests)
- `features/updates/`: subscribe to `feat:autoUpdate`. Phase `ready` → a card at the update card's priority (45) with the same gating: "miyagi {version} is ready." with **Restart to update** (PrimaryButton) and **Later** (it installs on quit anyway). `downloading` shows nothing (no progress bar for a background download).
- `required` → one card that wins over the home and launcher but never interrupts a running step: shown when the lesson ends, or before the next one starts.
- Settings > General: "Updates" row with the channel (Stable / Beta) next to the existing "Check for updates" (`agents/updates.md` Core request 1).
- `web.ts` stand-ins for `autoUpdate:*` and a mock scenario (`&auto=ready | required | beta`).

## Test
- Now: `cd app && npm run typecheck` and `node --import tsx --import ./test/setup.mjs --test --test-force-exit test/autoUpdate.test.ts` (offline: locks, codesign parsing, channel, feed pin, version policy, and with the flag off all four handles present and inert).
- Once signed (Adrian, on a Mac, not in this pass): build and install 0.2.0 into /Applications, publish 0.2.1 to a beta feed, set the channel to beta. Check that the zip downloads in the background, that Quit installs it, that "Restart to update" works, that a dmg-mounted copy and an ad-hoc build answer `off`, and that a cloud `min` above the running version shows "Update miyagi".

## Notes
- Not run in Electron (offline round, no app launches). The electron-updater event names and fields (`update-available`, `download-progress.percent`, `update-downloaded.version`, `stagingPercentage`, `generateUpdatesFilesForAllChannels`) are from electron-updater 6.x. Recheck them against the version Adrian installs.
- `codesign` runs only when lock 1 is open (never today), with a 10 s timeout, and only on the running app's own bundle.
