# Distributing Miyagi

How a brand-new user gets from nothing to ⌥Space on macOS (Windows second), what works today, and the plan.
User-facing steps: [INSTALL.md](INSTALL.md). Written Sat Nov 14, 2026, ~18:30 PST (deadline Sun Nov 15, ~10 AM).

**Recommendation.**
- **Hackathon:** one Terminal line, `curl -fsSL …/scripts/install.sh | bash`, which downloads the real app *and* the engine
  (built in this PR). Three small asks make it work for strangers: make the repo public, publish `Miyagi-Mac.zip`, and
  have the app start the engine.
- **Later:** a single `Miyagi.dmg` whose app installs its own engine on first launch with a bundled `uv`, then Developer ID
  signing and notarization. No PyInstaller.

## 1. Today (audit)

| Piece | State | Gap for a new user |
|---|---|---|
| **App** (`app/`, Electron 45; source on `main`, Adrian's `adrian/shell`) | `electron-builder --mac --dir`, `identity: null`, `LSUIElement` (no Dock icon), appId `dev.sandhacks.miyagi`. CI (`mac-build`, pushes to `main` only) ad-hoc signs it and zips it with `ditto` as artifact `mac-zip` (commit d740d96). Windows: NSIS one-click per-user installer, published as release `windows` on the public `adrian-erlikhman/miyagi`. | The Mac zip is a CI artifact of a **private** repo (needs a GitHub login with access). Release `mac` doesn't exist yet, so miyagi.study's "Download for Mac" is off (`MAC_READY`). **arm64 only** (built on `macos-latest`). Not notarized. The app never starts the engine: without one it just says Offline. |
| **Engine** (`server/`, Python ≥3.11, run as 3.12) | `scripts/miyagi-engine.sh` creates `.venv` with `uv` on first run and then serves `:8787`. Deps: FastAPI/uvicorn, anthropic, google-genai, psycopg, pyobjc (Quartz, Vision, ScreenCaptureKit, ApplicationServices; darwin-only markers), pillow, rapidfuzz. It needs the repo tree at runtime (`REPO_ROOT` = `parents[2]`, `shared/contracts` added to `sys.path`) and **writes its caches into it** (`demo/cache/lessons`, `search`, `transcripts`). | Needs a clone of a private repo, `uv`, and a terminal. Listens on `0.0.0.0` (the LAN) by default. Gemini is "off" only through Michael's `.env` (`LESSON_ENGINE=claude`): the code default is `auto` (Gemini first). |
| **Keys** | The app's Settings stores them with `safeStorage` (Keychain) and sends `config.keys` on every connect. The engine keeps them in memory (`server/config.py`) and mirrors them into `os.environ`. `.env` is only a fallback. | The sheet marks **Gemini as required** (`REQUIRED = ['anthropic','gemini']`), so it opens and nags even though Gemini is off. Bright Data **zone names** can't be entered in Settings: the finder defaults them (`serp_api1`, `web_unlocker1`), but `lesson/transcript.py` and the coach's doc search need `BRIGHTDATA_UNLOCKER_ZONE` in the env. |
| **VS Code companion** (`vscode-ext/`, plain JS, no build) | Built, not installed anywhere. The README's install is a copy into `~/.vscode/extensions` (untested). | No `.vsix`, so no `code --install-extension`. This PR adds `scripts/package-vscode-ext.sh` (zip only, no npm). |
| **Permissions** | Screen Recording: the engine checks it (`CGPreflightScreenCaptureAccess`) and asks for it. Accessibility: optional (`AXIsProcessTrusted`, exact text, window placement). | macOS gives the grant to the **responsible app**, i.e. whatever started the Python process. Today that's **Terminal**, and after granting you have to quit Terminal and start again. |

### What a new user must do today (no installer)

1. Get invited to the private repo; install Xcode Command Line Tools (for `git`), `uv`, Node 22 and VS Code.
2. `git clone`, then `git switch integration/live` (the engine).
3. `scripts/miyagi-engine.sh`: wait for the venv, grant Screen Recording to Terminal, quit Terminal, run it again.
4. Second terminal: check out `main` for the app (`integration/live`'s `app/` is older), `cd app && npm ci && npm run dev`.
   Or download the `mac-zip` artifact from a GitHub Actions run, unzip it twice, then System Settings › Privacy & Security
   › **Open Anyway**.
5. Settings opens: paste the Anthropic key, plus something in Gemini to make the sheet stop asking.
6. Optional: copy `vscode-ext` into `~/.vscode/extensions` and reload VS Code.
7. ⌥Space.

Seven steps with four developer tools. Only a teammate gets through that.

## 2. Options

| | User steps | What ships | Effort | Risk |
|---|---|---|---|---|
| **A. `curl \| bash` installer** (this PR) | Paste one line, grant Screen Recording, paste a key | `scripts/install.sh`: `uv` → engine source tarball → venv in `~/miyagi/engine` → `bin/miyagi-engine` → `Miyagi.app` from the release → `.vsix` (asks first) | **Done** (Michael) | Low. Downloads pinned to `integration/live`. Needs the repo public (or `gh` login). |
| **B. App starts the engine** (on top of A) | Same, minus "start the engine in Terminal" | ~40 lines in `app/src/main`: spawn `~/miyagi/engine/bin/miyagi-engine` | **1–2 h** (Adrian) | Low. The Screen Recording grant moves from Terminal to Miyagi (one prompt, no Terminal restart). |
| **C. Self-contained app, `uv` bootstrap** (later) | Download a DMG, drag to Applications, open, paste a key | `extraResources`: engine source (`server/ shared/ cli/ scripts/ demo/cache`) + a `uv` binary (~28 MB per architecture). First launch runs A's engine steps from the bundle (`install.sh --src <Resources>/engine --no-app --no-vscode`) with a progress card, then B. | **~1 day** (Adrian 0.5, Michael 0.5) | Medium: first launch needs the network for about a minute (Python ~76 MB + packages ~185 MB on disk, measured on the `run-live` venv). |
| **D. PyInstaller / py2app binary** | Same as C, no first-launch wait | A frozen engine in `Contents/Resources` | **2–3 days**, then a rebuild for every engine change | High: pyobjc hooks, data files (schemas, prompts, caches), `REPO_ROOT`/`sys.path` assumptions in several modules, a cache that writes into the bundle (read-only once signed), and every `.so` has to be signed for notarization. Engine changes hourly this weekend. |
| E. Homebrew tap | `brew install --cask …` | Cask + formula | ~2 h | Needs Homebrew; signing problems stay the same. Not worth it before C. |

What decided it:

- **A** is the only option that fits the time and needs nothing from the app to start working. It also avoids the
  Gatekeeper dance: files `curl` downloads aren't quarantined, so an ad-hoc-signed app opens with no "Open Anyway".
- **B** is the cheapest big UX win: the user opens Miyagi and that's it. It also gives the permission prompt the right
  name. One caveat: an ad-hoc signature changes with every build, so each new build asks for Screen Recording again
  until we sign with a Developer ID.
- **C over D for "one download":** C keeps the engine as source, so engine fixes ship with no rebuild (re-run the
  bootstrap), the app stays small, and nothing in `server/` needs to learn about frozen paths. D only pays off once
  the engine stops changing and someone owns the signing of ~200 native libraries.

## 3. Cross-cutting

- **Keys:** always in the app's Settings (safeStorage → Keychain), never in a file. The installer writes
  `~/miyagi/engine/engine.env` for non-secret overrides only (`DEMO`, `MIYAGI_LESSONS_DIR`), and the launcher points
  `TUT_ENV` at it, so no `.env` of anyone else's is ever read. Ask: only Anthropic required (below).
- **Permissions:** whoever starts the engine gets the grant. Terminal with A, Miyagi with B or C. A first-run
  "Miyagi needs to see your screen" card with a button to `x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture`
  would replace the Terminal text (app ask 5; it needs the engine to report the permission, engine follow-up 3).
- **VS Code:** `scripts/package-vscode-ext.sh` builds `miyagi-companion-<version>.vsix` with `zip` (checked: the
  archive has `[Content_Types].xml`, `extension.vsixmanifest`, `extension/{package.json,extension.js,README.md}`).
  The installer installs it with `code --install-extension --force` **only after asking**, and copies the folder into
  `~/.vscode/extensions` if that fails. It finds `code` even when it isn't on PATH (inside `Visual Studio Code.app`).
  Not yet tried in a real VS Code. Later: publish to Open VSX / the Marketplace (1–2 h, needs a publisher).
- **Signing:** unsigned (ad-hoc) for the hackathon. Note: since **macOS 15, right-click › Open no longer works** for
  unsigned apps. Browser downloads need System Settings › Privacy & Security › **Open Anyway**; `curl` installs need
  nothing. Later: Apple Developer Program ($99/yr), Developer ID + hardened runtime + `notarytool` in CI, DMG target.
  0.5–1 day once the account exists. The `uv`-downloaded Python isn't in the bundle, so notarization doesn't cover it,
  and it doesn't need to: it isn't quarantined.
- **Auto-update:** skip for the hackathon. Re-running the installer updates both parts and keeps keys, lessons and
  built lessons (it carries `demo/cache` over). Later: `electron-updater` (needs signing on the Mac) plus the
  bootstrap re-running when the bundled engine version changes. About 0.5 day.
- **Intel Macs:** the CI build is arm64 only. `electron-builder --mac --universal` (or `--x64 --arm64`) roughly doubles
  the Electron part of the download. 15 minutes of config.
- **Windows:** Adrian's NSIS installer covers the app. The engine has no Windows path: the screen reader is macOS
  (Vision, ScreenCaptureKit). An `install.ps1` (`irm … | iex`) that mirrors A with `ORCH_SCREEN=0` is about 1 day
  including a test on Adrian's laptop, and grades from file saves, `tut run` and the VS Code companion. A Windows
  screen reader (Windows.Graphics.Capture + Windows.Media.Ocr) is its own 3–5-day project.

## 4. Plan

### Hackathon (by Sun Nov 15, ~10 AM)

| # | Who | What | Time |
|---|---|---|---|
| 1 | Michael | Merge this PR. Make `sandhacks-tutor` **public** (Devpost wants a public repo anyway) after a real secret scan (`gitleaks detect` or similar). A regex pass over all branches' history found no Anthropic (`sk-ant-`) or Google (`AIza`) keys, no `*_API_KEY=` values, no `Bearer` tokens; the only credentialed URLs are test fixtures like `postgres://u:p@…`. That pass is not a full scan. If it stays private, teammates use `gh auth login` and strangers can't install. | 20 min |
| 2 | Adrian | Publish `Miyagi-Mac.zip` (from CI's `mac-zip`, or `npm run dist:mac` + `codesign -s -` + `ditto -c -k --keepParent`) as release **`mac`** on `adrian-erlikhman/miyagi`, then set `MAC_READY`. The installer already downloads from that URL. | 15 min |
| 3 | Adrian | **App starts the engine** (app ask 1). | 1–2 h |
| 4 | Adrian | Settings: only **Anthropic** required (app ask 2). | 10 min |
| 5 | Adrian | miyagi.study, Mac: show the one-liner as the main action ("Paste this in Terminal") and the zip as the alternative with the Open Anyway note. | 20 min |
| 6 | Michael | Try it as a stranger: System Settings › Users & Groups › add a test user, log in, paste the one-liner, follow INSTALL.md. Nothing else on this Mac gets touched. | 30–45 min |

Without 3, the flow still works: the user starts `~/miyagi/engine/bin/miyagi-engine` in Terminal (INSTALL.md says how).

### Later

1. C: self-contained app with a `uv` bootstrap, a DMG and a progress card (~1 day).
2. Developer ID signing + notarization in CI; universal build (0.5–1 day).
3. Engine data out of the source tree (engine follow-up 1), auto-update (0.5 day).
4. Windows `install.ps1` (1 day), then a Windows screen reader (3–5 days).
5. VS Code extension on Open VSX / the Marketplace (1–2 h).

## 5. App asks (for Adrian)

1. **Start the engine from the app.** In `app/src/main` (new feature, e.g. `features/engine-autostart.ts`):
   - When the app is ready, if `DEMO` isn't set, `ENGINE_URL` isn't set (or points at localhost), nothing answers on
     127.0.0.1:8787, and `~/miyagi/engine/bin/miyagi-engine` exists: `spawn(bin, [], { stdio: 'ignore' })`. The
     launcher logs to `~/miyagi/engine/logs/engine.log` by itself when it has no terminal, fixes PATH for a
     Finder-launched app, and listens on 127.0.0.1 only.
   - On `will-quit`: `child.kill('SIGTERM')`, but only for a child the app started. An engine someone started in Terminal stays up.
   - `EngineLink` already reconnects (500 ms → 4 s backoff). While the child starts (~3–8 s), show "Starting…"
     instead of "Offline".
   - If the file is missing, the Offline pill could say "Install the engine" and copy the one-liner.
   - Contract: that path, no arguments, exit 1 with "port … already in use" when an engine is already up. That's the whole interface.
   - Effect: the macOS Screen Recording and Accessibility prompts name **Miyagi**, not Terminal. To check on the first
     build: an ad-hoc-signed rebuild asks again.
2. **Settings: require only Anthropic.** `REQUIRED = ['anthropic']` in `features/settings/keys.ts`. Hide Gemini, or mark
   it "not used in this build", like ElevenLabs. Today the sheet auto-opens and nags for a key the engine doesn't use.
3. **Publish `Miyagi-Mac.zip` as release `mac`** and turn on `MAC_READY` on miyagi.study (plan row 2). Consider
   `--universal` for Intel Macs.
4. **Later, the self-contained app (C):** `extraResources` for the engine source + `uv`, and a first-launch bootstrap
   card. Michael provides the engine side: `install.sh --src … --no-app --no-vscode` already does it.
5. **Later, a permissions card:** "Miyagi needs to see your screen" with a button that opens the Screen Recording pane,
   driven by a permission field in `config.status` (engine follow-up 3).

## 6. Engine follow-ups (Michael's lane, not done here)

1. Caches live in the source tree (`REPO_ROOT/demo/cache/{lessons,search,transcripts}`). Add `MIYAGI_CACHE_DIR`
   (default `~/miyagi/cache`, shipped demo caches read-only). The installer carries `demo/cache` over on update meanwhile.
   This is required for C and D (a signed bundle is read-only).
2. Default the Bright Data zones everywhere like the finder does (`web_unlocker1` in `lesson/transcript.py` and
   `coach/web.py`), so a Settings-only Bright Data key works for transcripts and doc citations too.
3. Report permissions in `config.status` (screen recording, accessibility) so the app can show the card.
4. `LESSON_ENGINE` defaults to `auto` (Gemini first) in code. The installer's launcher pins `claude`; consider making
   that the code default while Gemini is off.
5. `server/screen/reader.py` falls back to a hard-coded `/Users/tripi/sand hacks/sandhacks-tutor/.env` when `TUT_ENV`
   is unset. That's harmless elsewhere (the file is missing), but better removed. The installer's launcher always sets `TUT_ENV`.

## 7. What this PR adds

- `scripts/install.sh`: the installer (A). `--dry-run`, `--yes`, `--no-app`, `--no-vscode`, `--no-start`,
  `--app-zip`, `--src`, `--ref`.
  - It refuses to replace a `Miyagi.app` with a different bundle id. APFS ignores case, so this protects any other
    "miyagi.app" in the same folder.
  - It checks the app's architecture and reads answers from `/dev/tty`, so `curl | bash` still asks; with no keyboard
    the answer is no.
  - Run from a clone, it uses the checkout in place.
- `scripts/package-vscode-ext.sh`: `.vsix` from `vscode-ext/` with `zip` (no npm).
- `docs/INSTALL.md` (user steps), `docs/DISTRIBUTION.md` (this file).
- Checked: `bash -n` on all three scripts, `--dry-run` from the checkout and piped like `curl | bash` (with `HOME` in a
  scratch folder), the generated `bin/miyagi-engine` (`bash -n`, paths with spaces), and the `.vsix` contents.
- Not run: a real install on any Mac, `code --install-extension`, the app download (release `mac` doesn't exist yet).
