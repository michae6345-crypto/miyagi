# Why the Mac download is the size it is

`npm run ship:mac` makes `dist/Miyagi-Mac.dmg`. Measured on Nov 20 (arm64, engine `integration/live@34435e0`):

| | Before | After |
|---|---|---|
| Download | `Miyagi-Mac.zip` 208 MB | **`Miyagi-Mac.dmg` 126 MB** (the same app zipped: 180 MB) |
| miyagi.app on disk | 566 MB | 457 MB |
| Electron (`Frameworks/`) | 252 MB | 243 MB |
| `app.asar` | 52 MB | 3.7 MB |
| Engine (`Resources/engine`) | 252 MB | 200 MB |
| … Python (`engine/python`) | 235 MB, 62 packages | 187 MB, 61 packages |
| … engine source (`engine/src`) | 17 MB | 13 MB |

Of the 126 MB, roughly 83 MB is Electron and 40 MB is the engine.

## Where the bytes go

**Electron (Chromium + Node), about 240 MB on disk and 83 MB compressed.** The `Electron Framework` binary alone is 197 MB, because it is a whole browser engine. We can't make it smaller without leaving Electron. The only easy cut was the 220 UI locale folders. `electronLanguages: [en]` keeps English (9 MB on disk, 2.5 MB compressed).

**Python, about 190 MB on disk and 40 MB compressed.** It's a standalone CPython 3.12 (an 18 MB interpreter) plus the engine's packages. The biggest are `anthropic` (33 MB: thousands of pydantic type modules), Pillow (15 MB, including its image codecs), `google-genai` and `google-auth` (13 MB), PyObjC (about 20 MB across `objc`, Quartz, AppKit, Vision and the rest), `cryptography` (12 MB) and `rapidfuzz` (6 MB). Most of the remaining weight is the pure-Python packages, which ship both their source (34 MB of `.py`) and their bytecode (35 MB of `.pyc`).

**Compression.** electron-builder writes the dmg as ULFO (lzfse), which comes out at 163 MB. `ship-mac.sh` then recompresses the same image to ULMO (lzma), which comes out at 126 MB. Lzma does much better on the Chromium and Python binaries. ULMO needs macOS 10.15, and Electron 45 already needs macOS 12. The cost is a few extra seconds when the image is mounted. To use lzfse instead, set `MIYAGI_DMG_FORMAT=ULFO`.

## What was cut

All of these are in `scripts/bundle-engine.mjs` (`PRUNE_*`), `electron-builder.yml` and `package.json`. Each Python removal was checked against the engine's imports (`server/`, `shared/`, `cli/`). The build still runs the import check, and it now also fails if any remaining binary links a library that was pruned.

| Cut | Disk | Why it's safe |
|---|---|---|
| React, motion, lucide-react and zustand moved to `devDependencies` | 48 MB (asar 52 → 3.7 MB) | Vite bundles them into `out/renderer`. Only `ws` is required at runtime (by `main/engine.ts`). |
| Chromium locales except English | 9 MB | The app's copy is English only. |
| `lib/libpython3.12.dylib` | 18 MB | `bin/python3.12` is statically linked. No `.so` loads the dylib (checked with `otool -L` at build time). |
| `pip` in site-packages, plus the `pip`, `2to3`, `pydoc` and `*-config` scripts | 13 MB | The engine never runs the bundled Python's pip. Lesson `.venv`s get their own pip from `ensurepip`, which stays (checked: `python3 -m venv` gives a venv with pip 26.2). |
| Tcl/Tk (`tkinter`, `turtle`, `_tkinter`, `libtcl`, `libtk` and the script folders) | 10 MB | The engine never imports them. |
| Engine `tests/` folders and `conftest.py` | 4 MB | No runtime module imports them. They stay in git. |
| `include/` (C headers), `share/`, `lib/pkgconfig` | 2 MB | These are only used to compile extensions against this Python. |
| `lib2to3`, `pydoc_data` | 2 MB | Deprecated tooling, and `help()` topics. |
| `.pyi`, `.pyx`, `.pxd`, `.c` and `.cpp` in site-packages, plus each dist-info's `RECORD` | 1 MB | These are build-time and install-time files. `METADATA`, `entry_points.txt` and licenses stay. |
| Already pruned before: `PyObjCTest`, `*/tests`, `psycopg_binary` (Tiger), `test`, `idlelib`, `turtledemo` | | |

Source maps: none ship (`out/` has no `.map`).

## What stays, and why

- **Both `.py` and `.pyc` for site-packages.** Shipping bytecode only would save roughly 5 MB compressed, but anyio 4.16 builds its lazy-import table by reading its own source (`anyio/_lazyimport.py`, `inspect.getsource`). Without that source, `anyio.to_thread` and friends disappear, and FastAPI and Starlette break. Shipping source only would save roughly 10 MB compressed, but then the engine would recompile every start: importing the engine takes 2 to 2.5 s instead of about 1 s, and lazy imports later on are slower too. The stdlib `.pyc` files must stay regardless: a lesson `.venv` runs without `-B` and would otherwise try to write bytecode inside the signed app.
- **Every package that `server/pyproject.toml` pulls in.** That includes `cryptography` (a dependency of `google-auth`), `uvloop`, `httptools` and `watchfiles` (`uvicorn[standard]`), and `requests` (`youtube-transcript-api`). Some are only loaded on some code paths, so removing them would pass the import check and then fail later.
- **`ensurepip` and `venv`.** Lesson `.venv`s are built from this Python when the Mac has no other Python.
- **`LICENSES.chromium.html` (5 MB) and the package licenses.** We redistribute these components, so their licenses stay.
- **Known tradeoff:** with Tk gone, a tkinter lesson on a Mac whose only Python is ours fails at `import tkinter`. Apple's Command Line Tools Python and Homebrew's `python-tk` still work. Without the headers, a lesson that pip-installs a package with no arm64 wheel can't compile it against our Python.

## What could go later

- **Download Python on first run** (about −40 MB). Ship the app with only the engine source, and fetch the pinned python-build-standalone archive and a prebuilt site-packages tarball (sha256-checked) the first time it opens. This brings back the first-run network dependency that the bundle was built to remove (DISTRIBUTION-PLAN.md section 2).
- **Lazy vendor SDKs** (about −10 MB). Make `anthropic` and `google-genai` optional downloads, or call their REST APIs with `httpx`. `anthropic/types` alone is 22 MB.
- **A native Swift shell** (about −80 MB). The pill, cards and launcher are small, but Electron costs about 83 MB compressed. A SwiftUI overlay with a `WKWebView` for the React UI would land around 5–10 MB. That means rewriting `src/main`: windows, the overlay click-through, IPC and settings.
- **Universal builds** carry both architectures of every binary, so `--universal` is much bigger. Ship separate arm64 and x64 dmgs instead.
