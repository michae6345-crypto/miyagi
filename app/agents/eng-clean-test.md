# eng-clean-test

**Status:** done, pushed (no PR) · **Priority:** P1 · **Port:** none (shell script + doc) · **Branch:** `claude/eng-clean-test` (from `origin/integration/live`)

## Goal
Michael can delete miyagi from his Mac, download it again, grant permissions and start a lesson, and know the Mac really was clean. DISTRIBUTION-PLAN.md section 5.

## Owns
- `scripts/miyagi-uninstall.sh` (new): dry run by default, `--yes` to act, `--keep-lessons`, `--keep-state`.
- `docs/CLEAN-TEST.md` (new): fresh-user option, script option, the reinstall test, pass criteria.

## Done when
- [x] Script removes every item the plan lists: processes (quit + port 8787 free), app and downloads, app data (`miyagi`, `miyagi-overlay`, bundle id caches/prefs/saved state/HTTPStorages, logs), keychain safeStorage items, engine and state, VS Code companion, TCC permissions and login item.
- [x] Keeps `~/.cache/uv`, `~/.local/share/uv`, Python/Jupyter extensions, `Electron Safe Storage`; moves `~/miyagi/lessons` aside, never deletes it.
- [x] Never kills a process: asks miyagi to quit, aborts `--yes` before removing anything if miyagi or anything on 8787 is still up.
- [x] Path guard: removes only inside `$HOME` (not `$HOME` or a top-level `~/Library` folder) plus `/Applications/miyagi.app`. Case-insensitive duplicates deduped by inode.
- [x] macOS bash 3.2 compatible; refuses sudo.

## Test (what was run)
- `bash -n scripts/miyagi-uninstall.sh`
- Dry run against a fake `HOME` fixture in the scratchpad (all sections detected, Downloads filename with a space, lessons move, `--keep-lessons`, `--help`, bad option exit 2).
- Read-only dry run on the dev Mac: confirmed the keychain service names `miyagi Safe Storage` and `miyagi-overlay Safe Storage` exist (attribute lookup only), and the running dev engine on 8787 shows as a BLOCKER.
- Never run with `--yes`.

## Fix round 1
- `.app` removal now checks `CFBundleIdentifier` (PlistBuddy) and keeps anything that is not `dev.sandhacks.miyagi`. On the dev Mac `~/Applications/miyagi.app` is Michael's AppleScript dev launcher (no bundle id): it is now kept and listed as "not the miyagi app: bundle id none". Same check for `miyagi*.app` in `~/Downloads`.
- Section 1 now runs `lsof -t +D` on each existing userData folder (`miyagi`, `Miyagi`, `miyagi-overlay`, deduped by inode). Any pid is a BLOCKER in the dry run and a `die ... Nothing was removed.` under `--yes`. This catches the npm run dev app (Electron.app), which the `miyagi.app` pgrep pattern misses. Never kills.
- CLEAN-TEST.md: onboarding copy matches Onb-Setup-Full/Ready ("Open System Settings", "Install in VS Code", "miyagi engine: Running" with no button, "Start learning"); keychain row lists `Miyagi`/`miyagi Safe Storage` (packaged, productName `Miyagi` on integration/live) and `miyagi-overlay Safe Storage` (dev); Option B warns that `--yes` on a dev Mac removes the dev app's `keys.bin` (BYOK keys), its keychain item and `~/miyagi/state`.
- Tested: `/bin/bash -n`; fixture dry run (applet without id kept, other-id app kept, real-id app listed, held file in `miyagi-overlay` shows BLOCKER); `--yes` on a copy truncated after section 1 with the port moved off 8787 (dies with a held file, passes without). Read-only check: the real dev launcher has no `CFBundleIdentifier`. Still never run with `--yes` on the real HOME.

## Fix round 2
- `~/miyagi/state` is no longer removed: it is moved aside to `~/miyagi-state-<time>` like lessons (`--keep-state` leaves it in place). It holds lesson progress (`current.json`, `graph-<lessonId>.json`), `history.json`, `mastery.json`, `recent.json` and `gemini_usage.json` (the daily Gemini video cap in `server/lesson/budget.py`; without it the cap restarts at 25 units). CLEAN-TEST.md dev Mac warning and table row 6 now name all of it.
- `bundle_id_of` returns nothing when `Contents/Info.plist` is missing (PlistBuddy printed "File Doesn't Exist, Will Create: ..." on stdout, which became the shown bundle id) and uses PlistBuddy output only on success.
- `/Volumes/[Mm]iyagi*` is ejected only when `hdiutil info` lists it as a disk image mount point; any other volume (an external drive named Miyagi Backup) is kept with an info line.
- Tested: `/bin/bash -n`; helpers against fixtures (app with no Info.plist gives an empty id; a mounted dmg is a disk image, `/` and an unmounted name are not); dry run against a fake HOME (state and lessons listed as moved aside, `--keep-state --keep-lessons` keeps both, `--help`). Still never run with `--yes` on the real HOME.

## Core requests
- The distribution plan puts the script at `app/scripts/miyagi-uninstall.sh` and asks for a "Test before you publish" rewrite in `app/SHIP.md`. This package was scoped to new files only, so the script lives at `scripts/miyagi-uninstall.sh` and the procedure in `docs/CLEAN-TEST.md`. Whoever owns `app/SHIP.md` (adrian-ui) should replace its "Test before you publish" section with a link to `docs/CLEAN-TEST.md`, and `ship-mac.sh` could print that link at the end.
- When `michael/app-cloud-token` lands, confirm `install.bin` stays under `userData` (the script removes the whole `Application Support/miyagi` folder, so any other location needs adding here).
- When `claude/eng-bundle` lands, check whether the bundled engine writes anywhere new (for example a cache outside `~/miyagi/engine`) and add it to section 6 of the script.

## Notes
- TCC reset runs before the app is deleted: `tccutil` resolves the bundle id through LaunchServices and reports "No such bundle identifier" once the app is gone (treated as nothing to do).
- Microphone is reset too (voice mic), beyond the plan's three services.
