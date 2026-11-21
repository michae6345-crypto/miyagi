# Ship miyagi for Mac

One download, `Miyagi-Mac.dmg` (about 126 MB, see `SIZE.md`): the app **with the engine inside it**. Open it, drag miyagi onto Applications. Nobody needs Terminal, git or Python.

**First open (no Apple Developer account yet, so the app is signed ad hoc):** open miyagi once, press Done, then go to System Settings › Privacy & Security and press **Open Anyway**.

What a new user sees the first time they open it:

1. The pill says **Setting up miyagi**. The app copies its engine source to `~/miyagi/engine` and starts it with the Python inside the app. This takes seconds and needs no network.
2. **Starting miyagi**, then **ask miyagi ⌥Space**. The engine runs as long as the app does. Quitting (⌥Q) stops it.
3. macOS asks for **Screen Recording for miyagi** (the app started the engine, so the prompt names miyagi, not Terminal).
4. Settings (the gear, typing "settings" in the launcher, or ⌘,): paste the **Anthropic** key. That's the only required key.

If an engine is already running on port 8787 (say you started one in Terminal), the app uses that one and never stops it.

## Build (on your Mac)

You need Node 22, git, and the Xcode command line tools (for `codesign` and `ditto`).

```bash
git fetch origin && git checkout main && git pull
cd app && npm ci
npm run ship:mac                 # Apple silicon → app/dist/Miyagi-Mac.dmg
npm run ship:mac -- --zip        # also app/dist/Miyagi-Mac.zip (install.sh --app still downloads the zip)
npm run ship:mac -- --universal  # Apple silicon + Intel (bigger)
```

`ship:mac` does four things. It puts the engine in (`scripts/bundle-engine.mjs`), builds the app (`--dir`) and signs it ad hoc. Then it packs that signed app into the dmg: electron-builder's `dmg` target with the art in `build/dmg/` (layout in `agents/dmg-art.md`), recompressed to lzma (ULMO). Set `MIYAGI_DMG_FORMAT=ULFO` for lzfse. A zip is made only with `--zip`. The engine comes from `origin/integration/live` (set `MIYAGI_ENGINE_REF` to use another branch). `install.sh` comes from the same branch, or from `origin/claude/distribution` until PR #66 is merged. The last lines print which engine commit went in.

## Test before you publish (about 15 minutes)

Do this as a brand-new user: a test macOS user account, or move your engine aside first with `mv ~/miyagi/engine ~/miyagi/engine.bak`. Then make sure nothing is listening on 8787 (`lsof -nP -iTCP:8787 -sTCP:LISTEN`).

1. Open `Miyagi-Mac.dmg` and drag **miyagi** onto Applications. Open it, press Done, then go to System Settings › Privacy & Security and press **Open Anyway**.
2. Watch the pill: Setting up miyagi → Starting miyagi → ask miyagi. If it says **Engine didn't start**, clicking it opens `~/miyagi/engine/logs/engine.log`.
3. Grant Screen Recording when asked. If macOS wants a restart, quit with ⌥Q and reopen.
4. Settings: paste the Anthropic key and press Test. The dot turns white.
5. ⌥Space, build a lesson, do a step. Then ⌥Q, and `lsof -nP -iTCP:8787 -sTCP:LISTEN` shows nothing: the engine stopped with the app.
6. Start an engine in Terminal, then open the app: it uses yours, and quitting the app leaves yours running.

Also worth checking in the built app, since it has never run on our side:
- Settings → Appearance switching live, and Open at login
- the player in light mode, and a YouTube lesson actually playing (the built app now serves its UI from `http://127.0.0.1`; `file://` got YouTube error 153)
- ⌥Space → End lesson; links from cards and the drawer opening in your browser; the pill over a full-screen app

## Publish

```bash
npm run ship:mac -- --publish
```

This uploads `dist/Miyagi-Mac.dmg` to the **`mac`** release on `adrian-erlikhman/miyagi`. It needs `gh auth login` and write access there; otherwise send the dmg to Adrian, or set `MIYAGI_RELEASE_REPO`. miyagi.study's "Download for Mac" should link to `…/releases/download/mac/Miyagi-Mac.dmg`. Michael's `install.sh --app` still downloads `Miyagi-Mac.zip`, so add `--zip` (`npm run ship:mac -- --zip --publish`) to refresh that one too.

## How it works (for debugging)

- `app/src/main/localEngine.ts` runs it, and the pill shows its state (`core/lesson` `localEngine`).
- It only runs in a built app on macOS. In dev, set `MIYAGI_AUTOSTART=1` to try it. `DEMO=1`, or an `ENGINE_URL` that points at another machine, turns it off.
- Engine files live in `~/miyagi/engine`: `src/`, `venv/`, `bin/miyagi-engine`, `logs/engine.log`. `MIYAGI_HOME` moves them.
- An app update carrying a newer engine reinstalls it on the next launch, but only if the app installed it (the `BUNDLED` marker). An engine someone installed with the one-liner is never touched. Built lessons in `src/demo/cache` are kept either way.
- To start over: quit, `rm -rf ~/miyagi/engine`, open again.

## Known gaps

- **Unsigned (ad hoc):** every new build asks for Screen Recording again. Developer ID signing and notarization fix that later.
- **Size:** 126 MB to download, 457 MB installed. `SIZE.md` covers where it goes and what could still be cut.
- **Windows:** the installer has the app only. The engine needs macOS to read the screen.
