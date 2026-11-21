# bundle (A12)

**Status:** pass 1 done, ready for review · **Branch:** `michael/app-bundle` (from `michael/app-core-v2`) · **PR:** draft #170 into `adrian/shell`

## Goal
One download that works offline on first launch: the Mac app carries a standalone Python 3.12 with the engine's
packages already installed, plus the VS Code companion `.vsix`. First launch copies the engine source to
`~/miyagi/engine/src` and starts it with the bundled Python in seconds: no uv, no Python download, no Terminal.
DISTRIBUTION-PLAN.md section 2 ("The bundle").

## Owns
- `app/scripts/bundle-engine.mjs`
- `app/electron-builder.yml` (`mac.extraResources`)
- `app/src/main/localEngine.ts`
- `app/agents/bundle.md`

## Mockups
None of its own (no UI). It feeds the rows other lanes draw: Onb-Setup-Full, Onb-Checklist-Mixed and
Onb-Setup-Ready ("miyagi engine" and "VS Code companion" rows, A3) and Err-VSCodeSetup (helper sheet, A2).

## What ships

**`scripts/bundle-engine.mjs`** → `app/build/engine/` (gitignored):
- `src/`: engine source by `git archive` (server, shared, cli, scripts, demo), `.pyc` precompiled with
  `checked-hash` (stays valid after the copy to `~/miyagi`, where timestamps change).
- `python/`: python-build-standalone CPython **3.12.16** (release 20261026, `install_only_stripped`), pinned by
  version **and sha256** (arm64 and x64 constants in the script; a mismatch stops the build). Packages from
  `server/pyproject.toml` installed with `uv pip install --target python/lib/python3.12/site-packages
  --python-platform <triple> --only-binary :all: -r pyproject.toml` (dependencies only; the source runs from
  `PYTHONPATH`). Pruned: `PyObjCTest`, every `tests`/`test` folder in site-packages, `psycopg_binary`, site-packages
  `bin/`, stdlib `test`/`idlelib`/`turtledemo`. `ensurepip` and `venv` stay (lesson `.venv`s). Then everything is
  precompiled with `unchecked-hash`, so Python never writes inside the signed app.
- Import check with the bundled Python, keys empty: the packages (fastapi, uvicorn, anthropic, google.genai,
  Quartz, Vision, ScreenCaptureKit, ...) and `import server.orchestrator.main`. A failure stops the build.
- `vscode/miyagi.companion-<ver>.vsix` + `companion.json`: packed with plain `zip` like PR #66's
  `package-vscode-ext.sh` (no npm, no vsce): package.json, extension.js, README.md, icon.png.
- `VERSION`, `PYTHON.json` (version, arch, sha256, package count), and `install.sh` (fallback only, `--no-python`).
- Flags: `--dry-run` (prints every step, downloads and writes nothing), `--no-python` (old layout), `--offline`
  (uv cache only). Env: `MIYAGI_ENGINE_REF`, `MIYAGI_PY_ARCH=arm64|x64` (default arm64), `MIYAGI_BUNDLE_CACHE`
  (archive cache, default `~/.cache/miyagi-bundle`), `MIYAGI_INSTALL_REF`.

**`electron-builder.yml`**: `build/engine` → `Resources/engine` (minus `vscode/`), `build/engine/vscode` →
`Resources/vscode`. extraResources keep symlinks and `__pycache__` (electron-builder's default excludes only apply
to `files`; checked in app-builder-lib 26.18.0).

**`src/main/localEngine.ts`**, start-up order:
1. something listens on the port → `external` (unchanged);
2. the user's own install (launcher, no `BUNDLED` marker) → start the launcher (unchanged: never replaced);
3. **new:** bundled Python present → copy `Resources/engine/src` to `~/miyagi/engine/src` once per bundled version
   (async, swap via `src.new`, `demo/cache` kept), write `BUNDLED`, then spawn
   `Resources/engine/python/bin/python3 -m server.orchestrator.main --host 127.0.0.1 --port <port>` in its own
   process group, cwd `~/miyagi/engine/src`, env `PYTHONPATH=src`, `PYTHONNOUSERSITE=1`,
   `PYTHONDONTWRITEBYTECODE=1`, `MIYAGI_BUNDLED_PYTHON`, the launcher's defaults (`ENGINE_HOST=127.0.0.1`,
   `ORCH_SCREEN`, `ORCH_OPEN_WORKSPACE`, `ORCH_AUTOSTART=0`, `LESSON_ENGINE=claude`, `MIYAGI_EDITOR=vscode`,
   `TUT_ENV`), the per-launch `MIYAGI_ENGINE_TOKEN`; `PYTHONHOME`/`VIRTUAL_ENV` stripped. stdout/stderr go to
   `~/miyagi/engine/logs/engine.log` like the launcher's;
4. older bundles (install.sh, no python) → the old uv install (unchanged);
5. nothing → `missing` with the one-liner (unchanged).
- Status gains `runtime: 'bundled' | 'launcher'` (additive). Exit 1 before running is `external` only when the port
  now answers; otherwise `failed` (a Python error also exits 1).
- PATH for the engine adds VS Code's own `Contents/Resources/app/bin` folders (Finder-launched apps have none).
- Dev: `MIYAGI_AUTOSTART=1 MIYAGI_BUNDLE_DIR=$PWD/build/engine` tries the bundled path in `npm run dev` (ignored
  when packaged). Use `MIYAGI_HOME=<scratch>` and an `ENGINE_URL` port other than 8787 to stay off the live engine.

**VS Code companion IPC** (same file, registered whether or not the app manages the engine):
- `bridge.invoke('engine-local:companion')` → `{state, version?, bundled?, needs?, line?}`, states
  `unavailable | no-vscode | missing | outdated | installed | installing | failed`. Read-only, never prompts, no
  network: finds VS Code's own CLI (`/Applications/Visual Studio Code.app/.../bin/code`, `~/Applications/...`, then
  Spotlight by bundle id `com.microsoft.VSCode`), never a `code` on PATH; `--list-extensions --show-versions`.
- `bridge.invoke('engine-local:companion-install')`: `execFile` (no shell) `code --install-extension <vsix> --force`
  for our `.vsix` from inside the app (skipped when VS Code already has that version or newer), then
  `--install-extension ms-python.python` / `ms-toolsai.jupyter` when missing (Marketplace; a miss leaves `needs`
  set, the companion still counts as installed). One install at a time; progress on `feat:engine-local-companion`.
- Copy in `line` is short and plain ("Installing the companion", "Adding Python support", "VS Code didn't install
  the companion."); the rows' real copy belongs to A3/A2.

## Checks run
- `npm run typecheck`: green.
- `node scripts/bundle-engine.mjs --dry-run`: prints every step.
- Full bundle run (arm64, ~17 MB archive download + packages, mostly from uv's cache, 83 s): `build/engine` 237 MB
  (python 221 MB, 63 packages, about +70 MB zipped), import check passed.
- `electron-vite build && electron-builder --mac --dir --arm64 -c.npmRebuild=false` (Electron zip was cached, no
  big download): `Resources/engine/{src,python,VERSION,PYTHON.json,install.sh}` and `Resources/vscode/` present,
  symlinks and 6147 `.pyc` kept; the bundled Python runs from inside the app (relocatable). `codesign --force --deep
  -s -` then `codesign --verify --deep --strict`: both pass; Quartz/Vision still import after signing.
- Engine smoke on port 8899 (never 8787), isolated `HOME`, no keys, `ORCH_SCREEN=0`, `ORCH_OPEN_WORKSPACE=0`, with
  the exact env the app uses: `GET /health` 200, clean SIGTERM shutdown, 0 `.pyc` written.
- `python -m venv` from the bundled Python works (lesson `.venv`s).
- Not run: the companion install (it would change this Mac's VS Code) and a real first launch of the packaged app
  (the live miyagi app is running). Both are for the end-to-end test with Michael.

## Core requests
1. **`app/scripts/ship-mac.sh`** (integrator, wave 2): check `Contents/Resources/engine/python/bin/python3` and
   `Contents/Resources/vscode/*.vsix` instead of `engine/install.sh` (install.sh is now only written when a ref has
   it), print `engine/PYTHON.json`. When real signing lands: sign every Mach-O under `Resources/engine/python`
   (`.so`, `.dylib`, `bin/python3.12`) before the app, for notarization.
2. **`server/workspace/setup.py:289` `best_python()`** (engine lane, `claude/eng-bundle` per DISTRIBUTION-PLAN):
   fall back to `os.environ.get("MIYAGI_BUNDLED_PYTHON")` when no other Python 3 is found, so a Mac with no
   Homebrew Python can still build a lesson `.venv`. The app already sets the variable.
3. **`app/src/renderer/src/bridge.ts`** (core): web stand-ins for `engine-local:companion` and
   `engine-local:companion-install` (for example `?companion=missing|installed|no-vscode`), so A3 and A2 can draw
   the row and the setup sheet in the stage.
4. **`core/lesson.ts`** (core): `LessonState['localEngine']` may add `runtime?: 'bundled' | 'launcher'`.
5. **A3 onboarding / A2 setup sheet**: the "VS Code companion" row and the Err-VSCodeSetup sheet read
   `engine-local:companion` and call `engine-local:companion-install`; "Get VS Code" goes through `safeOpen`.
6. **`server/pyproject.toml`** (`claude/eng-drop-vendors`): with `psycopg[binary]` gone the prune list can drop
   `psycopg_binary`; nothing else changes here.
7. **`app/SHIP.md`**: describe the new bundle (`--dry-run`, `MIYAGI_PY_ARCH`, sizes) in "Build" and the
   uninstall list (`~/miyagi/engine/BUNDLED`, no `venv/` for bundled installs).

## Notes
- x64 / universal: `MIYAGI_PY_ARCH=x64` builds an Intel Python (wheels resolved for `x86_64-apple-darwin`; precompile
  and the import check need Rosetta). A universal app would need both Pythons and a per-arch pick in
  `localEngine.ts`; arm64 first, as planned.
- An older `~/miyagi/engine/venv` left by the uv installer is not deleted (the bundled path ignores it).
