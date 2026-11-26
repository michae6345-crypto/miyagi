# Ship miyagi for Mac

One download, `Miyagi-Mac.dmg` (about 126 MB, see `SIZE.md`): the app **with the engine inside it**. Open it, drag miyagi onto Applications. Nobody needs Terminal, git or Python.

**First open (no Apple Developer account yet, so the app is signed ad hoc):** open miyagi once, press Done, then go to System Settings › Privacy & Security and press **Open Anyway**.

What a new user sees the first time they open it:

1. The pill says **Setting up miyagi**. The app copies its engine source to `~/miyagi/engine` and starts it with the Python inside the app. This takes seconds and needs no network.
2. **Starting miyagi**, then **ask miyagi ⌥Space**. The engine runs as long as the app does. Quitting (⌥Q) stops it.
3. macOS asks for **Screen Recording for miyagi** (the app started the engine, so the prompt names miyagi, not Terminal).
4. Settings (the gear, typing "settings" in the launcher, or ⌘,): paste the **Anthropic** key. That's the only required key.

If an engine is already running on port 8787 (say you started one in Terminal), the app uses that one and never stops it. The one exception is the app's own engine from an earlier launch that didn't quit cleanly (force quit, crash): the app recognizes it and starts a fresh one (see "Which engine").

## Daily use on your own Mac

Use the real app, not `npm run dev` (in dev the Dock and ⌘Tab say "Electron"; the built app says miyagi everywhere: menu bar, Dock, ⌘Tab, Activity Monitor, About, the permission prompts, with the bonsai icon).

```bash
cd app
npm run install:local                  # ship build, then installs /Applications/miyagi.app
npm run install:local -- --dry-run     # see every step first; changes nothing
```

Then open miyagi from Spotlight (⌘Space, "miyagi") or Applications. After a code change, run `npm run install:local` again.

`scripts/install-local.sh` builds the dmg (`ship:mac`), copies miyagi.app out of it (exactly what users download), checks the signature, quits a running miyagi and a dev copy of this app (`npm run dev` Electron) with SIGTERM (Electron makes that a normal quit, so the app's engine stops; no AppleScript, so no "wants access to control miyagi" Automation prompt), then swaps the app into /Applications with two renames on one volume. The previous app goes to `~/miyagi/app-backups.noindex/` (the last 2 are kept; `.noindex` keeps them out of Spotlight). It strips quarantine (your own build) and registers the app with Launch Services so Spotlight and the Dock pick up the name and icon at once. It never touches `~/Applications`, VS Code or an engine you started.

Options: `--skip-build` (install the dmg already in `dist/`), `--open`, `--mode-only --engine dev|bundled` and `--cloud off` (next section), `--ship <ship:mac options>`.

**Permissions after a reinstall.** The app is signed ad hoc, so macOS treats every rebuild as a new app. A Screen Recording or Accessibility switch can look on and still belong to the old build. Fix: System Settings › Privacy & Security › Screen & System Audio Recording (macOS 15; "Screen Recording" on 14), select miyagi, press −, open miyagi again and allow it. Same under Accessibility. Or reset only miyagi's grants and let it ask again:

```bash
tccutil reset ScreenCapture dev.sandhacks.miyagi
tccutil reset Accessibility dev.sandhacks.miyagi
tccutil reset AppleEvents dev.sandhacks.miyagi
```

**Two miyagis in Spotlight?** A dev launcher in `~/Applications/miyagi.app` has the same name. Pick the one in /Applications, or rename the dev one.

## Which engine

| Mode | What the app does | Who it's for |
|---|---|---|
| **bundled** (default) | Starts the engine inside the app on 127.0.0.1:8787 (offline, its own Python), AI calls through the miyagi cloud (`features/cloud.ts`, anonymous install token). An engine already on :8787 that the app didn't start is used as is and left running. | Every user. Test this before you ship. |
| **dev** | Never starts or installs an engine. Only connects to `ENGINE_URL` (default `ws://localhost:8787`): your engine in Terminal, with the repo's `.env`. The pill waits while it restarts. | Michael's Mac while working on the engine. |

Switch it, for an app opened from Spotlight (no shell environment):

```bash
npm run install:local -- --mode-only --engine dev               # writes ~/Library/Application Support/miyagi/engine.json
npm run install:local -- --mode-only --engine dev --cloud off   # also no cloud token, so your engine uses .env keys
npm run install:local -- --mode-only --engine bundled           # back to what users get (removes engine.json)
```

`--mode-only` only writes or removes that file and prints the mode: no build, no dmg needed, miyagi isn't quit or reinstalled, and the backups in `~/miyagi/app-backups.noindex/` stay as they are. (`--skip-build --engine …` does the same; add `--reinstall` to also install the dmg in `dist/`.) Quit and reopen miyagi after switching. The file is `{"engine": "dev"}`, plus `"cloud": "off"` if asked. From Terminal, env wins over the file: `MIYAGI_ENGINE=dev|bundled`, `MIYAGI_CLOUD_URL=off`, and `ENGINE_URL` for an engine elsewhere (the built app's page policy only allows port 8787 on this Mac, so keep a local engine on 8787). Example: `open -a miyagi --env MIYAGI_ENGINE=dev`.

Why dev mode exists: in bundled mode, if miyagi opens while your engine is restarting (`update-engine.sh`), the app starts its own engine on 8787 and your restart then fails on a busy port. Dev mode never takes the port.

## Build (on your Mac)

You need Node 22, git, and the Xcode command line tools (for `codesign` and `ditto`).

```bash
git fetch origin && git checkout main && git pull
cd app && npm ci
npm run ship:mac                 # Apple silicon → app/dist/Miyagi-Mac.dmg
npm run ship:mac -- --zip        # also app/dist/Miyagi-Mac.zip (install.sh --app still downloads the zip)
npm run ship:mac -- --universal  # Apple silicon + Intel (bigger)
npm run ship:mac -- --x64        # Intel only → app/dist/Miyagi-Mac-x64.dmg
```

`ship:mac` does four things. It puts the engine in (`scripts/bundle-engine.mjs`), builds the app (`--dir`) and signs it ad hoc. Then it packs that signed app into the dmg: electron-builder's `dmg` target with the art in `build/dmg/` (layout in `agents/dmg-art.md`), recompressed to lzma (ULMO). Set `MIYAGI_DMG_FORMAT=ULFO` for lzfse. A zip is made only with `--zip`. The engine comes from the commit you build (set `MIYAGI_ENGINE_REF` to use another ref). `install.sh` comes from the same commit, or from `origin/claude/distribution` until PR #66 is merged. The last lines print which engine commit went in.

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

This uploads `dist/Miyagi-Mac.dmg` to the **`mac`** release on `adrian-erlikhman/miyagi` and sets that release's title (`miyagi <version> (unsigned)`) and notes from `RELEASE-NOTES.txt`. The in-app update card reads the version from that title, so bump `version` in `package.json` first: it offers a release only to apps with a lower version. The tagged workflow in `RELEASING.md` is the usual way to release; this is the by-hand path. It needs `gh auth login` and write access there; otherwise send the dmg to Adrian, or set `MIYAGI_RELEASE_REPO`. miyagi.study's "Download for Mac" should link to `…/releases/download/mac/Miyagi-Mac.dmg`. Michael's `install.sh --app` still downloads `Miyagi-Mac.zip`, so add `--zip` (`npm run ship:mac -- --zip --publish`) to refresh that one too.

## How it works (for debugging)

- `app/src/main/localEngine.ts` runs it, and the pill shows its state (`core/lesson` `localEngine`).
- It only runs in a built app on macOS. In dev, set `MIYAGI_AUTOSTART=1` to try it. `DEMO=1`, engine mode dev (`MIYAGI_ENGINE=dev` or `engine.json`), or an `ENGINE_URL` that points at another machine, turns it off.
- The app writes the pid of the engine it started to `~/miyagi/engine/run/app-engine.json`. If miyagi was force-quit, that engine keeps running and still expects the old launch's token, so the next launch would never connect. On launch, when :8787 is busy, the app checks that pid file: a live process is its own leftover only when its command line starts with this app's exact Python (`Resources/engine/python/bin/python3`) or launcher (`~/miyagi/engine/bin/miyagi-engine`, or an interpreter under `~/miyagi/engine` running the engine module), and it started within a few seconds of the time in the pid file. Then it stops it (SIGTERM, SIGKILL after 5 s) and starts a fresh one. Anything else on the port, a dev engine from a repo checkout included, is left alone. A normal quit removes the pid file. `engine.log` notes which one happened.
- About miyagi (tray / pill menu > About miyagi) shows the app version and the engine commit inside the app. The application menu has only Hide and Quit. The tray item is a Core request to the launch-ease lane (`features/launch.ts`, see `agents/real-app.md`); until it lands, the panel is set up (`main/identity.ts`) but has no menu entry.
- Engine files live in `~/miyagi/engine`: `src/`, `venv/`, `bin/miyagi-engine`, `logs/engine.log`. `MIYAGI_HOME` moves them.
- An app update carrying a newer engine reinstalls it on the next launch, but only if the app installed it (the `BUNDLED` marker). An engine someone installed with the one-liner is never touched. Built lessons in `src/demo/cache` are kept either way.
- To start over: quit, `rm -rf ~/miyagi/engine`, open again.

## Known gaps

- **Unsigned (ad hoc):** every new build asks for Screen Recording again. Developer ID signing and notarization fix that later.
- **Size:** 126 MB to download, 457 MB installed. `SIZE.md` covers where it goes and what could still be cut.
- **Windows:** the installer has the app only. The engine needs macOS to read the screen.
