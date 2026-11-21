# Clean test: delete miyagi, download it again, start a lesson

The test every release has to pass before we hand out a link: a Mac that has never seen miyagi downloads it, grants permissions and starts a lesson, with no Terminal and no API keys. Source: DISTRIBUTION-PLAN.md section 5.

There are two ways to get a clean Mac. Pick one, then run [the test](#the-test).

## Option A (best): a fresh macOS user

A new user account is clean by definition: no app data, no keychain items, no permissions, no VS Code extensions.

1. System Settings > Users & Groups > Add User. Name it "Miyagi Test", a Standard account is fine.
2. Log out (or use fast user switching) and log in as Miyagi Test.
3. Install VS Code in that account if `/Applications/Visual Studio Code.app` is not already there (it is shared by all users).
4. Run [the test](#the-test).

Things that are shared across users and are not reset by a new account: `/Applications/miyagi.app` (delete it first, or the test reuses it), anything listening on port 8787 from another user (the new miyagi would talk to it instead of its own engine: stop it first).

## Option B (repeat runs): the uninstall script on your own Mac

`scripts/miyagi-uninstall.sh` removes everything miyagi left on this Mac. It is a **dry run by default**: it only lists what it found.

```bash
scripts/miyagi-uninstall.sh                # 1. read the list, change nothing
scripts/miyagi-uninstall.sh --yes          # 2. remove it
scripts/miyagi-uninstall.sh                # 3. check: only the permission and "kept" lines remain
```

**On a dev Mac, `--yes` also removes your dev setup:** `~/Library/Application Support/miyagi-overlay` (`keys.bin` with the BYOK keys pasted into the dev app; the dry run shows how big it is) and its `miyagi-overlay Safe Storage` keychain item, and `~/miyagi/state` (the Gemini usage file). Paste the keys into the dev app again afterwards. Option A avoids this.

Before step 2:
- Quit miyagi (packaged or npm run dev) with ⌥Q. The script also asks the packaged app to quit, but it never kills a process. Anything that still has files open in `~/Library/Application Support/miyagi` or `miyagi-overlay` (the dev app, for example) is listed as a **BLOCKER** with its pid and command, and `--yes` stops before removing anything.
- Stop anything listening on port 8787 (a dev engine, for example). The dry run lists it as a **BLOCKER** with its pid and command; `--yes` stops before removing anything while it is still there.

`--keep-lessons` leaves `~/miyagi/lessons` in place. Without it the folder is moved aside to `~/miyagi-lessons-<date>-<time>`, never deleted. To bring it back afterwards: `mv ~/miyagi-lessons-<date>-<time> ~/miyagi/lessons`.

### What the script removes

| # | What | Where |
|---|---|---|
| 1 | Processes | asks miyagi to quit, then requires port 8787 to be free (`lsof -nP -iTCP:8787 -sTCP:LISTEN`) and no process to have files open in the app data folders (`lsof +D`, which catches the npm run dev app) |
| 2 | Permissions | `tccutil reset` ScreenCapture, Accessibility, AppleEvents and Microphone for `dev.sandhacks.miyagi` (done before the app is deleted, while macOS still knows the id); the "miyagi" login item through System Events |
| 3 | App | `/Applications/miyagi.app`, `~/Applications/miyagi.app`, any mounted miyagi disk image, `miyagi*.zip`, `miyagi*.dmg` and `miyagi*.app` in `~/Downloads`. An `.app` goes only if its `CFBundleIdentifier` is `dev.sandhacks.miyagi`; anything else with that name (a dev launcher applet in `~/Applications`, for example) is kept and listed as "not the miyagi app" |
| 4 | App data | `~/Library/Application Support/miyagi` and `miyagi-overlay` (dev runs): `keys.bin`, `install.bin`, prefs, player bounds; `~/Library/Caches`, `~/Library/HTTPStorages`, `~/Library/Saved Application State` and `~/Library/Preferences` entries for `dev.sandhacks.miyagi` (the preferences domain is cleared with `defaults delete` first); `~/Library/Logs/miyagi` |
| 5 | Keychain | the safeStorage items `Miyagi Safe Storage` / `miyagi Safe Storage` (packaged app, named after electron-builder's productName, which is `Miyagi` on integration/live) and `miyagi-overlay Safe Storage` (dev runs). The script tries all three names |
| 6 | Engine and state | `~/miyagi/engine`, `~/miyagi/state`, `~/.miyagi/tiger-spool`, `~/.cache/sandhacks-tutor/tts`; `~/miyagi/lessons` moved aside |
| 7 | VS Code | `code --uninstall-extension miyagi.companion` (VS Code's own CLI inside the app if `code` is not on PATH) and any `~/.vscode/extensions/miyagi.companion-*`. Reload open VS Code windows afterwards |

Kept on purpose: `~/.cache/uv` and `~/.local/share/uv` (other projects use them; the new bundle does not), the Python and Jupyter VS Code extensions, and the `Electron Safe Storage` keychain item (shared by every Electron app run from source).

What it never does: kill a process, delete lessons, print a keychain secret, remove an `.app` whose bundle id is not `dev.sandhacks.miyagi`, or remove anything outside your home folder except `/Applications/miyagi.app`. Run it as yourself, not with sudo.

If a line says `FAILED`, it names the manual fix (Finder, Keychain Access, or System Settings > Privacy & Security). A `tccutil` line saying macOS no longer knows `dev.sandhacks.miyagi` is fine: the app was already gone, so there was nothing left to reset.

## The test

Write down the build (version and commit) and the macOS version before you start.

1. **Download.** Open the release link in Safari and download the zip (or dmg). Unzip and drag miyagi to Applications.
2. **Open Anyway.** Until the app is notarized, macOS 15 and later block it: open it once, press Done, then System Settings > Privacy & Security > **Open Anyway**, and enter your password. Do not use `xattr -dr com.apple.quarantine` for this test: it skips the step every real user sees.
3. **Onboarding.** One screen, four rows, all green with no Terminal. The first three turn green from their own button; the engine row has no button:
   - Screen Recording: Allow, then Relaunch if macOS asks.
   - Accessibility: Open System Settings.
   - VS Code companion: Install in VS Code (adds the companion, Python and Jupyter extensions).
   - miyagi engine: Running (no button: it turns green on its own within seconds, offline-capable, no key prompt anywhere).
4. **Cached lesson (free).** "Start learning", pick a cached lesson, pass the first step.
5. **One fresh build (costs money).** Ask Michael before this step. Build one new lesson from a YouTube link and start it.
6. **Proxy.** `/admin` on miyagi-cloud shows a new install token, and its spend matches the one build.

### Pass criteria

- No Terminal, no API key, no "Setup stopped" at any point.
- Every onboarding row green; "Start learning" opens the launcher.
- The cached lesson starts and its first step can pass.
- The fresh build reaches step 1.
- `/admin` shows exactly one new token for this run.

### Record

Build, macOS version, Option A or B, time from first open to the onboarding screen being all green, which rows needed a relaunch, anything that asked for a password more than once, and a screenshot of any error card.

## Known rough edges

- Builds are ad hoc signed until we have a Developer ID, so every new build has a new code hash and Screen Recording asks again. Expected, not a failure.
- A login item added by "Open at login" can survive the app's deletion on some macOS versions. The script tries to remove it; check System Settings > General > Login Items anyway.
- macOS may ask once to let Terminal control System Events while the script removes the login item. Declining only skips that step.
