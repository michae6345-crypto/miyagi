# eng-clean-test

**Status:** done, pushed (no PR) · **Priority:** P1 · **Port:** none (shell script + doc) · **Branch:** `claude/eng-clean-test` (from `origin/integration/live`)

## Goal
Michael can delete miyagi from his Mac, download it again, grant permissions and start a lesson, and know the Mac really was clean. DISTRIBUTION-PLAN.md section 5.

## Owns
- `scripts/miyagi-uninstall.sh` (new): dry run by default, `--yes` to act, `--keep-lessons`.
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

## Core requests
- The distribution plan puts the script at `app/scripts/miyagi-uninstall.sh` and asks for a "Test before you publish" rewrite in `app/SHIP.md`. This package was scoped to new files only, so the script lives at `scripts/miyagi-uninstall.sh` and the procedure in `docs/CLEAN-TEST.md`. Whoever owns `app/SHIP.md` (adrian-ui) should replace its "Test before you publish" section with a link to `docs/CLEAN-TEST.md`, and `ship-mac.sh` could print that link at the end.
- When `michael/app-cloud-token` lands, confirm `install.bin` stays under `userData` (the script removes the whole `Application Support/miyagi` folder, so any other location needs adding here).
- When `claude/eng-bundle` lands, check whether the bundled engine writes anywhere new (for example a cache outside `~/miyagi/engine`) and add it to section 6 of the script.

## Notes
- TCC reset runs before the app is deleted: `tccutil` resolves the bundle id through LaunchServices and reports "No such bundle identifier" once the app is gone (treated as nothing to do).
- Microphone is reset too (voice mic), beyond the plan's three services.
