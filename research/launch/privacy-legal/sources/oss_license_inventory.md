# Open-source license inventory: miyagi desktop app, engine, cloud and site (as of 2026-11-21)

> DRAFT. Not legal advice. Built from files on disk only (no installs). Two read-only `gh api` calls checked repo visibility, license and release assets. The per-package tables are at the end.

## Bottom line

- **Nothing strong-copyleft was found in anything miyagi distributes.** No GPL, AGPL, SSPL, BUSL, Commons Clause, CC-BY-NC or CC-BY-SA component. Two Mac-only items couldn't be checked here and could still change this: the bundled python-build-standalone interpreter (#16: GNU readline or gdbm?) and the macOS Pillow wheel (#13: libimagequant?). The copyleft that does ship is weak and file- or library-level: LGPL-2.1+ and MPL-2.0 parts inside Electron/Chromium (including ffmpeg), MPL-2.0 `certifi` in the bundled Python, a 7-Zip-based NSIS plug-in in the Windows installer (probably LGPL), and the CPL-1.0 LZMA module in NSIS, which has a linking exception.
- **The real gap is attribution.** No build ships a third-party notices file or an "open-source licenses" screen. The next Mac build drops the `node_modules` copies that currently carry the LICENSE files. The public site serves a React/lucide/motion bundle with every license comment stripped.
- **miyagi's own licensing is undefined.** Both GitHub repos are public and have no LICENSE file. There are no contributor or IP-assignment terms, and the app and VS Code companion are `private`/`UNLICENSED`.
- **Some items are UNKNOWN on this machine.** These are the Windows installer's NSIS plug-ins and `elevate.exe` (no license text in the binaries), the bundled python-build-standalone interpreter, the PyObjC packages, `uvloop` (Mac only, not installed here) and PyJWT (cloud). They need checking on the Mac build or upstream.

## What ships, and how it was checked

| Artifact | Built from | What's inside (license-relevant) |
|---|---|---|
| **Public Windows installer**: `Miyagi-Windows-Setup.exe`, GitHub release `windows` on adrian-erlikhman/miyagi, uploaded 2026-11-19 17:30 PT | `adrian/windows` (main-era `package.json`: React etc. still in `dependencies`) | Electron 45.3.2 runtime (Chromium, Node, `ffmpeg.dll`, MS/Vulkan DLLs) with `LICENSE.electron.txt` and `LICENSES.chromium.html` next to `miyagi.exe`. `resources/app.asar` holds `out/` (main, preload, renderer bundle, Google Sans Flex woff2, `desktop.png`) and `node_modules/` for ws, react, react-dom, scheduler, zustand, motion, framer-motion, motion-dom, motion-utils, lucide-react and tslib, each with its LICENSE. Also `resources/elevate.exe` and the NSIS stub and plug-ins. **No engine.** I inspected the local build of the same branch from Nov 20 (`wt/windows/app/dist/win-unpacked`), which has the same dependency set. |
| **Public Mac zip**: `Miyagi-Mac.zip`, release `mac`, CI artifact `mac-zip` from `main@0a0af09d` (2026-11-19) | main's `app/` + main's `bundle-engine.mjs` (74-line version) | Same Electron + `app.asar` as Windows. `Resources/engine` holds **engine source + `install.sh` only**. On first launch `install.sh` downloads `uv` from astral.sh, and `uv` downloads CPython and the engine's PyPI packages onto the learner's Mac. Python packages are **not redistributed by miyagi** in this build. main's `server/pyproject.toml` still lists `psycopg[binary]` (LGPL-3.0) as a runtime dependency, so it gets downloaded too. |
| **Next Mac DMG**: `npm run ship:mac` on the integration line (`app/SIZE.md`, measured Nov 20) | `adrian/legal-privacy` = `origin/michael/v2-integration` for every build file; engine from `origin/integration/live` | Electron. `app.asar` = `out/` + `node_modules/ws` only (React and the rest moved to devDependencies and are bundled by Vite). `Resources/engine/python` = **python-build-standalone CPython 3.12.16 (20261026) + 61 packages**, pruned and precompiled. `Resources/engine/src` = server/shared/cli/scripts/demo. `Resources/vscode` = the companion `.vsix` (own code, `"license": "UNLICENSED"`, no npm deps). This **is** redistribution of the Python stack. |
| Windows Store `.appx` | `adrian/windows-store` (unpushed) | Same as the Windows build. Not distributed. |
| **miyagi.study**: GitHub Pages from adrian-erlikhman/miyagi `main` | `miyagi-site` | `index.html`, `fonts/GoogleSansFlex.woff2` + `fonts/OFL.txt`, `live/` (a Nov 14 renderer build: React, motion, lucide, zustand, `desktop.png`, the font), webp screenshots. It also loads `three@0.160.0` and `lenis@1.1.13` from jsDelivr and the YouTube IFrame API at runtime. |
| **Cloud** (`cloud/`, Render) | `origin/claude/eng-proxy-auth` / `integration/live` | Server-side only. Nothing is distributed, so copyleft can only bite through a network-use clause, and there is none. |

Sources read: `app/package.json`, `package-lock.json` (v3, 480 entries, every entry has a `license` field), `electron-builder.yml`, `electron.vite.config.ts`, `scripts/bundle-engine.mjs`, `SIZE.md`, `.github/workflows/ci.yml` (main). Installed copies came from `wt/bug-hunt/app/node_modules`, an exact lock match that resolved 395 of 480 entries. The 85 not installed are other-platform optional binaries. Licenses for those come from the lockfile and are marked as such. For Python I read `*.dist-info/METADATA`, license files and the embedded CycloneDX SBOMs in `wt/michael-demo-lock/.venv` and `wt/engine/.venv` (Windows, CPython 3.12.10). For the Mac I resolved dependency markers for macOS arm64. Versions on disk can differ from the Mac bundle because `pyproject.toml` has only lower bounds and no lock. `PYTHON.json` from a real bundle would give the exact list. Other inputs: the built `win-unpacked` and its `app.asar` (parsed), the electron-builder cache (`%LOCALAPPDATA%\electron-builder\Cache`: NSIS 3.0.4.1 `COPYING`, nsis-resources plug-ins) and the font's `name` table (fontTools).

---

## 1. Counts by license

### (a) Shipped desktop app (Electron shell, all builds)

| Component group | Count by license |
|---|---|
| npm packages in the app (13) | **MIT 11** (electron, ws, react, react-dom, scheduler, zustand, motion, framer-motion, motion-dom, motion-utils, tailwindcss for its CSS preflight and banner) · **ISC 1** (lucide-react, which also carries MIT text for Feather-derived icons) · **0BSD 1** (tslib: copied into `app.asar` by the public builds, not referenced by the bundle) |
| Electron's Chromium credits (`LICENSES.chromium.html`, 500 components) | License-text scan: 224 contain Apache text, 47 Unicode, 25 MPL, 19 LGPL, 30 mention GPL (mostly dual or tri-licensed, or Linux-only parts such as glibc and gtk), 5 CC (data). Electron maintains this file upstream; miyagi's duty is to keep shipping it. |
| Windows installer extras | NSIS 3.0.4.1: **Zlib** (core), **bzip2-1.0.6** (bzip2 module), **CPL-1.0 with linking exception** (LZMA module). Plug-ins StdUtils, UAC, nsProcess, SpiderBanner, WinShell, nsis7z and `elevate.exe`: **UNKNOWN** (see §2). |
| Fonts | **OFL-1.1 1** (Google Sans Flex, subset/instanced woff2) |
| Bundler runtime | Vite modulepreload polyfill and rolldown helpers (MIT, a few lines) |
| Own code | app (`"private": true`, no license field) and VS Code companion (`"license": "UNLICENSED"`): **proprietary/undefined** |

### (b) Engine (bundled inside the next Mac DMG) and cloud

| Scope | Count by license |
|---|---|
| **Engine Python packages**, resolved for macOS arm64 (56 named here; SIZE.md counts 61 in the real bundle, the rest being PyObjC dependencies not resolvable on Windows) | **MIT 23**, **BSD-3-Clause 11**, **Apache-2.0 8** (anthropic, distro, google-auth, google-genai, opentelemetry-api, requests, tenacity, watchdog), **BSD-2-Clause 2** (pyasn1, pyasn1-modules), **PSF-2.0 2** (defusedxml, typing_extensions), **MPL-2.0 1** (certifi), **MIT-0 1** (cffi), **MIT-CMU 1** (pillow), **Apache-2.0 OR BSD-3-Clause 1** (cryptography), **MIT OR Apache-2.0 1** (sniffio), **UNKNOWN (not on disk) 5** (pyobjc-framework-Quartz/Vision/ApplicationServices/ScreenCaptureKit, uvloop) |
| Interpreter | CPython 3.12.16 from python-build-standalone: **PSF-2.0** plus statically linked third-party libraries. **UNVERIFIED** (no Mac bundle on this machine). |
| Native code inside wheels (from on-disk SBOMs and Pillow's LICENSE) | Pillow: FreeType (**FTL**, dual with GPL-2.0), libjpeg-turbo (**IJG + BSD-3**), libpng, libtiff, libwebp, openjpeg, lcms2, harfbuzz, brotli, xz (**0BSD**), zlib-ng (**Zlib**), libavif with dav1d/aom/libyuv (**BSD-2**). cryptography: **OpenSSL 4.0.3 (Apache-2.0)** statically linked + 39 Rust crates. pydantic-core: 101 crates (19 **Unicode-3.0**). jiter: 38 crates. rpds-py: 17. watchfiles: 26 (`notify` is **CC0-1.0**). |
| **Cloud** (`cloud/requirements.txt`, 21 resolved) | **MIT 8**, **BSD-3-Clause 7**, **Apache-2.0 1**, **PSF-2.0 1**, **MIT-0 1**, **MPL-2.0 1** (certifi), **Apache-2.0 OR BSD-3-Clause 1** (cryptography), **UNKNOWN 1** (PyJWT, not installed here). Not distributed, so no notice or source duties. |

### (c) Dev-only (never in a shipped artifact)

| Scope | Count by license |
|---|---|
| npm (467) | **MIT 352**, **ISC 42**, **Apache-2.0 30**, **MPL-2.0 12** (lightningcss + 11 platform binaries), **BSD-3-Clause 10**, **BlueOak-1.0.0 9**, **BSD-2-Clause 5**, **0BSD 1**, **Python-2.0 1** (argparse), **CC-BY-4.0 1** (caniuse-lite), **WTFPL 1** (truncate-utf8-bytes), **WTFPL OR ISC 1** (sanitize-filename), **WTFPL OR MIT 1** (utf8-byte-length), **MIT OR CC0-1.0 1** (type-fest) |
| Python (11) | **MIT 4** (pytest, pluggy, iniconfig, ruff), **Apache-2.0 2** (pytest-asyncio, tzdata), **LGPL-3.0-only 2** (psycopg, psycopg-binary: `tiger` extra on integration), **BSD-2-Clause 1** (Pygments), **BSD-3-Clause 1** (colorama), **Apache-2.0 OR BSD-2-Clause 1** (packaging) |
| Build-machine tools (not shipped, not in the counts above) | NSIS compiler `makensis`, 7-Zip and winCodeSign (electron-builder cache), `uv` |

---

## 2. Flagged items

Risk: **H** = act before the next public release, **M** = fix soon, **L** = note it, keep it as is.

| # | Item | Version | License | Shipped where | Duty it creates | Risk | Recommended action |
|---|---|---|---|---|---|---|---|
| 1 | **miyagi app repo** michae6345-crypto/miyagi (public) and **site/releases repo** adrian-erlikhman/miyagi (public) | main | **No LICENSE** on any branch (GitHub detects none). No CONTRIBUTING, CLA or DCO. | Source is publicly viewable; the releases are hosted on the site repo | No outbound grant: all rights reserved. GitHub's ToS lets users view and fork on GitHub only, so nobody may reuse the code. No inbound terms either: each contributor (two founders, AI-assisted commits) keeps copyright in their own commits, so ownership and the right to relicense or sell are unclear. | **H** (IP and ownership, not OSS compliance) | Founders sign a short IP assignment to the entity or to each other, and check the SanD Hacks/MLH rules on project IP. Then choose: (a) proprietary: add `LICENSE` ("Copyright 2026 …, all rights reserved") and consider making the code repo private, or (b) pick an OSS license on purpose. If outside PRs are possible, add a CONTRIBUTING note with a DCO or inbound=outbound clause. |
| 2 | App (`miyagi-overlay`) and **VS Code companion** (`miyagi.companion`) | 0.1.0 / 0.0.6 | `private`, no license field / **UNLICENSED** | Every build; the `.vsix` ships in the next DMG | Own code. Users get no written license: no EULA in the NSIS installer or DMG, and terms live only at miyagi.study/terms. | M | Point the app's About/Settings at the Terms (sibling note `terms_eula_enforceability.md`). The THIRD_PARTY_NOTICES file should say miyagi's own code is proprietary. |
| 3 | **Electron runtime** (Chromium, Node, V8) | 45.3.2 | MIT + 500 bundled components (LGPL-2.1+, MPL-2.0, Apache-2.0, BSD, Unicode, …) | All desktop builds | Keep `LICENSE.electron.txt` and `LICENSES.chromium.html` with the app. LGPL parts (ffmpeg, Blink's WebKit-derived code) need their source to stay available. Chromium's source is public, and the credits page links it. | L | Done on Windows (both files next to `miyagi.exe`). electron-builder 26.18 moves both into `miyagi.app/Contents/Resources` on Mac (`ElectronFramework.js`). **Verify in the zip and DMG.** In THIRD_PARTY_NOTICES, name the exact Electron tag and link its source. |
| 4 | **ffmpeg** inside Electron (`ffmpeg.dll` 3.1 MB; `libffmpeg.dylib` on Mac) | Chromium's | **LGPL-2.1-or-later** | All desktop builds | LGPL: it must stay a separately replaceable library (it is), with license text (in the Chromium credits) and source availability. The build includes H.264/HEVC code (`h264`, `hevc` strings), which raises **patent** questions (AVC/HEVC pools) that no copyright license covers. | L | Keep it dynamic and keep the credits. Note the patent point in the register. Electron publishes a proprietary-codec-free ffmpeg; swapping it in is a product call, since the YouTube embed may fall back to H.264. |
| 5 | **NSIS** installer stub and LZMA module | 3.0.4.1 | Zlib; bzip2-1.0.6; **CPL-1.0** for the LZMA module, with a special exception (linking does not subject our code; only changes to LZMA files are CPL) | Windows installer | None mandatory. Zlib asks for acknowledgment only. | L | List NSIS in the notices. |
| 6 | **nsis7z.dll** ("7-Zip NSIS Plug-in", © Igor Pavlov, Nik Medved, Marek Mizanin, Stuart Welch) | from nsis-resources 3.4.1 | **UNKNOWN on disk**. Built from 7-Zip code, which is LGPL-2.1+ with the unRAR restriction, so treat it as LGPL until confirmed. | Windows installer. electron-builder calls `Nsis7z::Extract` to unpack the app; it runs from temp at install time. | If LGPL: give notice and license text, point to the source (7-Zip and the plug-in source are public), and allow replacement. | M | Confirm the license from the electron-builder-binaries `nsis-resources` source. Add an LGPL notice and source link to the notices. |
| 7 | **StdUtils.dll** (© 2004-2018 LoRd_MuldeR), **UAC.dll**, **nsProcess.dll**, **SpiderBanner.dll**, **WinShell.dll** | nsis-resources 3.4.1 | **UNKNOWN**: no license string in the DLLs | Windows installer (all are called by electron-builder's NSIS templates) | Unknown until confirmed | M | Confirm each upstream license and add it to the notices. |
| 8 | **elevate.exe** (© 2007 Johannes Passing) | 2019 build | **UNKNOWN**: binary has copyright only | Windows: copied to `resources/elevate.exe` in the installed app | Unknown | M | Confirm the upstream license and add the notice. |
| 9 | **certifi** | 2026.10.23 (on disk) | **MPL-2.0** | Next Mac DMG (engine Python). Also cloud (server-side, no duty), and downloaded by the public zip's first-run installer (not miyagi's redistribution). | File-level copyleft. Ship the license notice and keep the MPL files' source available; the bundle ships unmodified `.py` + `cacert.pem` source, which satisfies this. Any edit to certifi files must be published under MPL. | L | Never patch certifi in the bundle. Keep `dist-info/licenses/LICENSE`. List it in the notices with a source link. |
| 10 | **psycopg / psycopg-binary** | 3.3.9 | **LGPL-3.0-only** (psycopg-binary also bundles libpq and others) | Integration: dev-only (`tiger` extra), and `bundle-engine.mjs` prunes `psycopg_binary` anyway. **main**: runtime dependency, so the public Mac zip's first-run `uv` install downloads it onto learners' Macs (user-side download, not redistribution). | If it is ever bundled: LGPL-3.0 notice and license text, plus the right to replace (pure-Python source is replaceable). | L (M if bundled) | Keep it out of every bundle. Main gets integration's pyproject when merged. Add a bundle check that fails on any LGPL/GPL `dist-info`. |
| 11 | **Google Sans Flex** font (`GoogleSansFlex.woff2`, 36 KB: 349 glyphs, `wght` 400-700, "18pt" instance) | 4.005 | **OFL-1.1** (name table: "Copyright 2015 Google LLC. All Rights Reserved." + `openfontlicense.org`; no license-description entry) | App renderer bundle (all builds), site `/fonts` + `live/`, `web/download` (inlined base64) | OFL §2: every copy carries the copyright notice and the license, as a file or user-viewable metadata. The metadata holds only a URL. The app ships **no** OFL.txt (it lives only in `app/brand/fonts` and the site's `fonts/`). Subsetting makes this a Modified Version: if upstream declares a Reserved Font Name, the subset may not keep the name. | M | Put OFL.txt (Google Sans Flex section) in THIRD_PARTY_NOTICES and next to the inlined font in `web/download`. Check upstream `googlefonts/google-sans-flex` OFL.txt for an RFN. Fix `brand/fonts/OFL.txt`: it names Anybody, Shantell Sans and Syne, which aren't shipped, and its copyright line doesn't match the font's own. |
| 12 | **Site `live/` bundle**: react, react-dom, scheduler, motion/framer-motion, lucide-react, zustand | Nov 14 build (versions not recorded in the file) | MIT / ISC (lucide: also MIT for Feather icons) | miyagi.study/live and the public site repo | MIT/ISC: copyright and permission notice in all copies. The file has **0** license comments (React's and lucide's banners were stripped). | M | Rebuild with Vite `build.license`, or add `live/THIRD_PARTY_NOTICES.txt`. Or delete `live/` if the scroll story replaced it. |
| 13 | **Pillow** wheel native libraries | 13.0.0 | MIT-CMU + bundled: FreeType (FTL or GPL-2.0), libjpeg-turbo (IJG), libavif/dav1d/aom/libyuv, libwebp, … The wheel's SBOM also lists **libimagequant (GPL-3.0+)** and **FriBiDi (LGPL-2.1+)** as *optional build components*. | Next Mac DMG | Choose FTL: "Portions of this software are copyright © <year> The FreeType Project" in documentation. IJG: "acknowledge somewhere in your documentation that you've used the IJG code". The Windows wheel's LICENSE has no libimagequant/FriBiDi section, so they aren't bundled there; FriBiDi only loads at runtime if the OS has it. | L | Put the FreeType and IJG credits in the notices. **Verify the macOS arm64 wheel's LICENSE also lacks libimagequant.** |
| 14 | Rust crates with copyleft *options* | (in wheels) | `self_cell` Apache-2.0 OR GPL-2.0-only (cryptography); `r-efi` MIT OR Apache-2.0 OR LGPL-2.1+ (jiter, pydantic-core); `notify` CC0-1.0 (watchfiles); 19 ICU4X crates Unicode-3.0 (pydantic-core) | Next Mac DMG | Elect the permissive option. Unicode-3.0 needs its notice. | L | Generate notices from the `dist-info/sboms/*.json` files (stdlib-readable CycloneDX). |
| 15 | **OpenSSL** statically linked in `cryptography` | 4.0.3 | Apache-2.0 | Next Mac DMG (cloud: no duty) | Apache-2.0 §4(a): give recipients a copy of the license. The wheel has OpenSSL only in its SBOM, not in its license files. | L | Add an OpenSSL entry to the notices. |
| 16 | **python-build-standalone CPython** | 3.12.16+20261026, `install_only_stripped` | PSF-2.0 + statically linked libraries (OpenSSL, SQLite, libffi, xz, bzip2, zlib, mpdecimal, expat, ncurses/libedit, …) | Next Mac DMG | **UNVERIFIED** (no bundle on this machine). The stripped archive may not carry each library's license text. GPL exposure depends on whether `readline` links GNU readline or libedit, and whether `_gdbm` is present. | M | On the build Mac: `python3 -c "import readline;print(readline.__doc__)"` (libedit vs GNU), look for `_gdbm*`, and copy license texts from the matching PBS release (full archive `PYTHON.json` / `licenses/`) into the notices. |
| 17 | **pyobjc-framework-Quartz / Vision / ApplicationServices / ScreenCaptureKit** (+ pyobjc-core, Cocoa and other dependencies), **uvloop**, **PyJWT** | — | **UNKNOWN** (not on disk; upstream expected MIT / MIT OR Apache-2.0 / MIT) | Mac DMG (PyObjC, uvloop); cloud (PyJWT) | Notice only, if as expected | L | Run the license walker on the Mac bundle's site-packages (see §3). |
| 18 | `desktop.png` (fake macOS desktop with the Apple logo and Dock icons resembling Finder/Safari/VS Code) and `server/screen/fixtures/*.png` (VS Code/Cursor screenshots) | — | Own work; third-party **trademarks/trade dress**, not OSS | `desktop.png` is statically imported by `main.tsx` (browser stage only), so it ships in every renderer bundle and in site `live/`. The fixtures ship in the DMG's engine source (not under `tests/`, so not pruned). | None under OSS licenses | L | Lazy-load the dev stage so production builds drop it. Prune `screen/fixtures` in `bundle-engine.mjs`. |
| 19 | `demo/cache/lessons/raw/*` (AI-built lessons from third-party YouTube tutorials, e.g. `AXXnSzmpyoI`) | — | Content rights, not OSS | Engine source in the Mac builds | See `youtube_copyright_trademark.md` | L | Covered by the YouTube note. |
| 20 | **youtube-transcript-api** | 1.2.5 | MIT (the license is fine) | Engine | No OSS duty beyond the notice, but what it does (calls YouTube's undocumented transcript endpoint) conflicts with YouTube's ToS | (see YouTube note) | Covered by `youtube_copyright_trademark.md` §1. |
| 21 | lightningcss (+ 11 platform binaries) | 1.33.0 | MPL-2.0 | Dev-only (Tailwind/Vite CSS step; none of its code lands in the output) | None | L | None. |
| 22 | caniuse-lite | 1.0.30001826 | CC-BY-4.0 | Dev-only (browserslist data) | None unless redistributed | L | None. |
| 23 | argparse (Python-2.0); 9 BlueOak-1.0.0 (chownr, graceful-fs, isexe ×2, minimatch, minipass, sax, tar, yallist); truncate-utf8-bytes (WTFPL); sanitize-filename (WTFPL OR ISC); utf8-byte-length (WTFPL OR MIT); type-fest (MIT OR CC0-1.0) | see table | as listed | Dev-only (electron-builder, node-gyp, tooling) | None | L | None. |

No package anywhere was found under AGPL, SSPL, BUSL, Commons Clause, EUPL, EPL, CDDL, CC-BY-NC or CC-BY-SA. No npm package is UNLICENSED or custom except miyagi's own two.

---

## 3. Attribution duties for permissive licenses

**What the licenses ask for.** MIT, ISC, BSD-2/3, MIT-CMU (HPND) and PSF-2.0 require the copyright and permission notice in copies or in accompanying documentation. Apache-2.0 requires a copy of the license plus any NOTICE file. FTL and IJG require a credit line in the documentation. OFL requires the license with the font. Unicode-3.0 requires its notice. MPL-2.0 requires the notice plus a source pointer. 0BSD, MIT-0, CC0 and Zlib (for binaries) require nothing.

**NOTICE files that must be reproduced.** Among shipped components only `requests` has one (`dist-info/licenses/NOTICE`: "Requests Copyright 2019 Kenneth Reitz" and the modified ca-bundle note). The Apache-2.0 packages without a NOTICE (anthropic, google-auth, google-genai, opentelemetry-api, tenacity, distro, watchdog, and OpenSSL inside cryptography) need the license text only. On npm, only dev-only packages have NOTICE files: typescript, `@typescript/typescript-win32-x64` and rolldown (`THIRD-PARTY-LICENSE`).

**What ships today.**
- **Electron/Chromium**: covered. Both files sit next to `miyagi.exe`; on Mac, electron-builder 26.18 moves them into `Contents/Resources` (verify).
- **Public builds**: third-party `node_modules` (each with its LICENSE) sit inside `app.asar`. The files are present but nobody can see them.
- **Next build (integration)**: `app.asar` holds only `node_modules/ws/LICENSE`. The renderer bundle keeps React's 5 `@license` banners and lucide's 79, and both point to "the LICENSE file in the root directory", which is no longer shipped. motion, framer-motion and zustand have no notice at all. Tailwind's `/*! tailwindcss v4.3.5 | MIT License */` banner is present.
- **Mac DMG engine**: `bundle-engine.mjs` keeps every `dist-info/licenses/*` and METADATA (it prunes only `RECORD`), so wheel licenses travel. Nothing collects them, and native libraries listed only in SBOMs (OpenSSL, Rust crates) have no license text anywhere.
- **No THIRD_PARTY_NOTICES file and no open-source credits screen.** The Mac About panel (`main/identity.ts`) shows only name, version, engine sha, "© 2026 miyagi" and a tagline. Windows has no About panel. The NSIS installer has no license page. The font's OFL text is not shipped.
- **Site**: OFL.txt is next to the font. `live/` has no notices (#12).

**Recommended build step** (tools named, not installed):
1. **Renderer (and the site's `live/`)**: turn on Vite's built-in **`build.license`**, which Vite 8.3.8 supports (checked in its `index.d.ts`). In `electron.vite.config.ts` → `renderer.build.license = { fileName: 'licenses/renderer.md' }` it emits the license of every dependency actually bundled. Do the same in `vite.web.config.ts`. (Alternative: `rollup-plugin-license`.)
2. **Main process / asar `node_modules`** (only `ws` now): `license-checker-rseidelsohn --production --json` or `@cyclonedx/cyclonedx-npm --omit dev` for an SBOM.
3. **Engine Python** (in `bundle-engine.mjs`, after the uv install and prune): either `pip-licenses --python build/engine/python/bin/python3 --with-license-file --with-notice-file --format=plain-vertical` (run via a throwaway tool env such as `uvx`, never inside the bundle), or a 40-line stdlib walker over `site-packages/*.dist-info/{METADATA,licenses/*,sboms/*.json}`. The scratchpad script `py_inventory.py` already does most of this. Add `cyclonedx-py environment` for a machine-readable SBOM. Append the python-build-standalone license texts from the matching PBS release.
4. **Static, hand-kept section** (`app/build/notices/`): Electron pointer + tag + source link, NSIS `COPYING` + plug-in licenses + elevate, Google Sans Flex OFL.txt, FreeType and IJG credit lines, OpenSSL (Apache-2.0), Unicode-3.0, and a line saying miyagi's own code is proprietary.
5. **Assemble** in a `scripts/notices.mjs` run by `dist:mac`, `ship:mac` and `dist:win` before electron-builder. Write `build/THIRD_PARTY_NOTICES.txt` and add it to `extraResources` for **both** `mac` and `win` (today `extraResources` is mac-only). Add an "Open-source licenses" row in Settings (or the tray menu) that opens it with `shell.openPath`, and mention it in the About panel's `credits`.
6. **Gate in CI**: fail the build on any shipped license outside an allowlist (MIT, ISC, BSD-2/3, Apache-2.0, 0BSD, MIT-0, PSF-2.0, MIT-CMU, Zlib, OFL-1.1, Unicode-3.0; MPL-2.0 for certifi only), using `license-checker-rseidelsohn --onlyAllow`, `pip-licenses --allow-only`, or the walker. Use **ScanCode Toolkit** once, by hand, for a deep scan of the binaries (Electron DLLs, PBS, wheels) before a store submission.

---

## 4. Special cases

- **ffmpeg and other native binaries in Electron.** `ffmpeg.dll` is LGPL-2.1+ with H.264/HEVC code (#4). The Windows build also ships `d3dcompiler_47.dll` (a Microsoft redistributable under Windows SDK terms), `dxcompiler.dll` (DirectX Shader Compiler, listed in the Chromium credits), `vk_swiftshader.dll` and `vulkan-1.dll` (Apache-2.0, in the credits) and `icudtl.dat` (ICU/Unicode). All come with Electron, and its credits file covers them.
- **sharp / libvips**: not used. They appear in neither the integration lock nor main's. There's no other native npm addon in the shipped set; `node-gyp` is dev-only.
- **PyInstaller bootloader**: not used anywhere (searched every branch). The engine reaches users in two ways. (1) **Public Mac zip (main)**: source + `install.sh`. First run installs `uv` from astral.sh, then CPython and the PyPI packages; the learner downloads these from upstream, so miyagi doesn't redistribute them. (2) **Next DMG (integration)**: python-build-standalone 3.12.16 + 61 packages copied in by `extraResources`, which is redistribution (#9, #13-#17). Windows ships no engine.
- **Model weights and datasets**: none ship. Every branch was searched for `.pt/.pth/.onnx/.safetensors/.ckpt/.h5/.pkl/.npz/.npy/.parquet/.gguf/.tflite`, audio and video: nothing. OCR uses macOS Vision (a system framework). LLM calls go to the Anthropic and Gemini APIs (see `vendor_terms_data_handling.md`). The engine source carries `cli/examples/pinn_convection_reference.synthetic.csv` (synthetic, own) and `demo/cache` lesson JSON (#19). Lessons may `pip install` third-party libraries (e.g. torch) into lesson venvs on the learner's machine; that is a user-side download.
- **Sounds and voice**: no audio files on any branch. The `app-sounds` branch synthesizes sound with WebAudio (`features/sound/player.ts`), and voice uses the system `speechSynthesis`.
- **YouTube IFrame API**: loaded at runtime from `https://www.youtube.com/iframe_api` by the app (`renderer/src/features/player/youtube.ts`; the CSP in `main/serve.ts` allows `www.youtube.com` and `s.ytimg.com`) and by the site. It is not redistributed, so there's no OSS duty; it falls under the YouTube API Services Terms and Developer Policies (`youtube_copyright_trademark.md` §2). Thumbnails are hotlinked from `i.ytimg.com`.
- **Site CDN scripts**: `three@0.160.0` and `lenis@1.1.13` (both MIT) load from jsDelivr. jsDelivr serves the files with their banners and miyagi doesn't host copies, so there's no notice duty. The third-party request is a privacy point (`site_cookies_check.md`).
- **Fonts**: only Google Sans Flex (#11). App text uses the OS fonts (SF Pro, Segoe), which aren't redistributed.
- **Icons**: lucide-react (ISC, plus MIT for the Feather-derived icons). The notices must carry both texts from lucide's LICENSE. The bonsai logo, wordmark and app icons are original brand work (BRAND.md).

---

## Gaps and how to close them

- No Mac artifact was on this machine. Before signing off, read on the build Mac: `Contents/Resources/LICENSE.electron.txt`, `LICENSES.chromium.html`, `engine/PYTHON.json` (exact freeze), and site-packages for PyObjC and uvloop.
- NSIS plug-in and `elevate.exe` licenses need an upstream check (electron-builder-binaries).
- Python versions on disk are a proxy (pyproject has lower bounds only). A `uv.lock` or the bundle's `PYTHON.json` would pin the register to exact versions.
- I didn't check upstream Google Sans Flex for an RFN, and I didn't verify the python-build-standalone component list (no network use beyond `gh api`).

Scripts used (read-only), in `<home>\AppData\Local\Temp\claude\899d803577521417\c7201d88-b405-49b2-9fec-e129f6ba2891\scratchpad\licenses\`: `npm_inventory.py`, `py_inventory.py`, `asar_list.py`, `chromium_credits.py`, `make_tables.py`.

---

## Appendix: full per-package tables

"Where it ends up" describes the integration build. Rows marked "public builds also copy it into asar" are in `app.asar/node_modules` in today's public Windows and Mac downloads. "not installed here (lockfile only)" means the license comes from `package-lock.json` and was not cross-checked against an installed copy (other-platform optional binaries). For every installed package, the lockfile license matched the package's own `package.json`.

### npm (app/package-lock.json, 480 entries)

Shipped app (npm): MIT 11, ISC 1, 0BSD 1

Dev-only (npm): MIT 352, ISC 42, Apache-2.0 30, MPL-2.0 12, BSD-3-Clause 10, BlueOak-1.0.0 9, BSD-2-Clause 5, 0BSD 1, Python-2.0 1, CC-BY-4.0 1, WTFPL OR ISC 1, WTFPL 1, (MIT OR CC0-1.0) 1, (WTFPL OR MIT) 1

| Package | Lock path (if nested) | Version | License | Where it ends up | License files on disk | Note |
|---|---|---|---|---|---|---|
| electron |  | 45.3.2 | MIT | app: runtime binary (Electron + Chromium + Node) | LICENSE |  |
| framer-motion |  | 14.14.0 | MIT | app: renderer bundle; public builds also copy it into asar | LICENSE.md |  |
| lucide-react |  | 1.73.0 | ISC | app: renderer bundle; public builds also copy it into asar | LICENSE |  |
| motion |  | 14.14.0 | MIT | app: renderer bundle; public builds also copy it into asar | LICENSE.md |  |
| motion-dom |  | 14.14.0 | MIT | app: renderer bundle; public builds also copy it into asar | LICENSE.md |  |
| motion-utils |  | 14.7.0 | MIT | app: renderer bundle; public builds also copy it into asar | LICENSE.md |  |
| react |  | 19.3.1 | MIT | app: renderer bundle; public builds also copy it into asar | LICENSE |  |
| react-dom |  | 19.3.1 | MIT | app: renderer bundle; public builds also copy it into asar | LICENSE |  |
| scheduler |  | 0.28.0 | MIT | app: renderer bundle; public builds also copy it into asar | LICENSE |  |
| tailwindcss |  | 4.3.5 | MIT | app: generated CSS (preflight + banner) | LICENSE |  |
| tslib |  | 2.9.1 | 0BSD | app: renderer bundle; public builds also copy it into asar | LICENSE.txt |  |
| ws |  | 8.23.0 | MIT | app: asar node_modules (main process) | LICENSE |  |
| zustand |  | 5.1.0 | MIT | app: renderer bundle; public builds also copy it into asar | LICENSE |  |
| @babel/code-frame |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/compat-data |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/core |  | 7.29.13 | MIT | dev-only | LICENSE |  |
| @babel/generator |  | 7.29.14 | MIT | dev-only | LICENSE |  |
| @babel/helper-compilation-targets |  | 7.29.13 | MIT | dev-only | LICENSE |  |
| @babel/helper-globals |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/helper-module-imports |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/helper-module-transforms |  | 7.29.14 | MIT | dev-only | LICENSE |  |
| @babel/helper-plugin-utils |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/helper-string-parser |  | 7.29.14 | MIT | dev-only | LICENSE |  |
| @babel/helper-validator-identifier |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/helper-validator-option |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/helpers |  | 7.29.14 | MIT | dev-only | LICENSE |  |
| @babel/parser |  | 7.29.14 | MIT | dev-only | LICENSE |  |
| @babel/plugin-transform-arrow-functions |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/template |  | 7.29.7 | MIT | dev-only | LICENSE |  |
| @babel/traverse |  | 7.29.14 | MIT | dev-only | LICENSE |  |
| @babel/types |  | 7.29.14 | MIT | dev-only | LICENSE |  |
| @electron-internal/extract-zip |  | 1.0.8 | MIT | dev-only | LICENSE |  |
| @electron/asar |  | 3.4.1 | MIT | dev-only | LICENSE.md |  |
| @electron/fuses |  | 1.8.0 | MIT | dev-only | LICENSE |  |
| @electron/get |  | 5.1.0 | MIT | dev-only | LICENSE |  |
| @electron/get | …/app-builder-lib/…/@electron/get | 3.1.0 | MIT | dev-only | LICENSE |  |
| @electron/notarize |  | 2.5.0 | MIT | dev-only | LICENSE |  |
| @electron/osx-sign |  | 1.3.3 | BSD-2-Clause | dev-only | LICENSE |  |
| @electron/rebuild |  | 4.2.1 | MIT | dev-only | LICENSE |  |
| @electron/universal |  | 2.0.3 | MIT | dev-only | LICENSE |  |
| @electron/windows-sign |  | 1.2.2 | BSD-2-Clause | dev-only | LICENSE | optional/platform |
| @emnapi/core |  | 2.0.0-beta.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @emnapi/core | …/@tailwindcss/oxide-wasm32-wasi/…/@emnapi/core | 1.11.3 | MIT | dev-only | LICENSE | optional/platform |
| @emnapi/runtime |  | 2.0.0-beta.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @emnapi/runtime | …/@tailwindcss/oxide-wasm32-wasi/…/@emnapi/runtime | 1.11.3 | MIT | dev-only | LICENSE | optional/platform |
| @emnapi/wasi-threads |  | 2.2.0 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @emnapi/wasi-threads | …/@tailwindcss/oxide-wasm32-wasi/…/@emnapi/wasi-threads | 1.2.3 | MIT | dev-only | LICENSE | optional/platform |
| @esbuild/aix-ppc64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/android-arm |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/android-arm64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/android-x64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/darwin-arm64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/darwin-x64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/freebsd-arm64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/freebsd-x64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-arm |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-arm64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-ia32 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-loong64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-mips64el |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-ppc64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-riscv64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-s390x |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/linux-x64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/netbsd-arm64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/netbsd-x64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/openbsd-arm64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/openbsd-x64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/openharmony-arm64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/sunos-x64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/win32-arm64 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/win32-ia32 |  | 0.28.2 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @esbuild/win32-x64 |  | 0.28.2 | MIT | dev-only | no license file | optional/platform |
| @isaacs/fs-minipass |  | 4.0.1 | ISC | dev-only | LICENSE |  |
| @jridgewell/gen-mapping |  | 0.3.13 | MIT | dev-only | LICENSE |  |
| @jridgewell/remapping |  | 2.3.5 | MIT | dev-only | LICENSE |  |
| @jridgewell/resolve-uri |  | 3.1.3 | MIT | dev-only | LICENSE |  |
| @jridgewell/sourcemap-codec |  | 1.6.0 | MIT | dev-only | LICENSE |  |
| @jridgewell/trace-mapping |  | 0.3.31 | MIT | dev-only | LICENSE |  |
| @malept/cross-spawn-promise |  | 2.0.0 | Apache-2.0 | dev-only | LICENSE |  |
| @malept/flatpak-bundler |  | 0.4.0 | MIT | dev-only | LICENSE |  |
| @napi-rs/wasm-runtime |  | 1.2.6 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @napi-rs/wasm-runtime | …/@tailwindcss/oxide-wasm32-wasi/…/@napi-rs/wasm-runtime | 1.2.2 | MIT | dev-only | no license file | optional/platform |
| @noble/hashes |  | 1.8.0 | MIT | dev-only | LICENSE |  |
| @oxc-project/types |  | 0.156.0 | MIT | dev-only | LICENSE |  |
| @peculiar/asn1-schema |  | 2.11.1 | MIT | dev-only | LICENSE |  |
| @peculiar/json-schema |  | 1.1.12 | MIT | dev-only | LICENSE |  |
| @peculiar/utils |  | 2.0.3 | MIT | dev-only | LICENSE |  |
| @peculiar/webcrypto |  | 1.7.2 | MIT | dev-only | LICENSE.md |  |
| @rolldown/binding-android-arm-eabi |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-android-arm64 |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-darwin-arm64 |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-darwin-x64 |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-freebsd-x64 |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-linux-arm-gnueabihf |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-linux-arm64-gnu |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-linux-arm64-musl |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-linux-ppc64-gnu |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-linux-s390x-gnu |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-linux-x64-gnu |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-linux-x64-musl |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-openharmony-arm64 |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-wasm32-wasi |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-win32-arm64-msvc |  | 1.2.19 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @rolldown/binding-win32-x64-msvc |  | 1.2.19 | MIT | dev-only | no license file | optional/platform |
| @rolldown/pluginutils |  | 1.1.1 | MIT | dev-only | LICENSE |  |
| @sindresorhus/is |  | 4.6.0 | MIT | dev-only | license |  |
| @szmarczak/http-timer |  | 4.0.6 | MIT | dev-only | LICENSE |  |
| @tailwindcss/node |  | 4.3.5 | MIT | dev-only | LICENSE |  |
| @tailwindcss/oxide |  | 4.3.5 | MIT | dev-only | LICENSE |  |
| @tailwindcss/oxide-android-arm64 |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-darwin-arm64 |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-darwin-x64 |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-freebsd-x64 |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-linux-arm-gnueabihf |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-linux-arm64-gnu |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-linux-arm64-musl |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-linux-x64-gnu |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-linux-x64-musl |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-wasm32-wasi |  | 4.3.5 | MIT | dev-only | no license file | optional/platform |
| @tailwindcss/oxide-win32-arm64-msvc |  | 4.3.5 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @tailwindcss/oxide-win32-x64-msvc |  | 4.3.5 | MIT | dev-only | LICENSE | optional/platform |
| @tailwindcss/vite |  | 4.3.5 | MIT | dev-only | LICENSE |  |
| @tybys/wasm-util | …/@tailwindcss/oxide-wasm32-wasi/…/@tybys/wasm-util | 0.10.3 | MIT | dev-only | no license file | optional/platform |
| @tybys/wasm-util |  | 0.10.4 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| @types/cacheable-request |  | 6.0.3 | MIT | dev-only | LICENSE |  |
| @types/debug |  | 4.1.13 | MIT | dev-only | LICENSE |  |
| @types/fs-extra |  | 9.0.13 | MIT | dev-only | LICENSE |  |
| @types/http-cache-semantics |  | 4.2.0 | MIT | dev-only | LICENSE |  |
| @types/keyv |  | 3.1.4 | MIT | dev-only | LICENSE |  |
| @types/ms |  | 2.1.0 | MIT | dev-only | LICENSE |  |
| @types/node |  | 26.6.6 | MIT | dev-only | LICENSE |  |
| @types/node | …/electron/…/@types/node | 24.19.2 | MIT | dev-only | LICENSE |  |
| @types/react |  | 19.3.0 | MIT | dev-only | LICENSE |  |
| @types/react-dom |  | 19.3.0 | MIT | dev-only | LICENSE |  |
| @types/responselike |  | 1.0.3 | MIT | dev-only | LICENSE |  |
| @types/ws |  | 8.18.2 | MIT | dev-only | LICENSE |  |
| @typescript/typescript-aix-ppc64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-darwin-arm64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-darwin-x64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-freebsd-arm64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-freebsd-x64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-linux-arm |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-linux-arm64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-linux-loong64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-linux-mips64el |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-linux-ppc64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-linux-riscv64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-linux-s390x |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-linux-x64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-netbsd-arm64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-netbsd-x64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-openbsd-arm64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-openbsd-x64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-sunos-x64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-win32-arm64 |  | 7.0.2 | Apache-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| @typescript/typescript-win32-x64 |  | 7.0.2 | Apache-2.0 | dev-only | LICENSE,NOTICE.txt | optional/platform |
| @vitejs/plugin-react |  | 6.3.0 | MIT | dev-only | LICENSE |  |
| @xmldom/xmldom |  | 0.8.15 | MIT | dev-only | LICENSE |  |
| abbrev |  | 4.0.0 | ISC | dev-only | LICENSE |  |
| agent-base |  | 7.1.4 | MIT | dev-only | LICENSE |  |
| ajv |  | 8.20.0 | MIT | dev-only | LICENSE |  |
| ansi-regex |  | 6.6.0 | MIT | dev-only | license |  |
| ansi-regex | …/electron-builder/…/ansi-regex | 5.0.1 | MIT | dev-only | license |  |
| ansi-styles | …/@electron/fuses/…/ansi-styles | 4.3.0 | MIT | dev-only | license |  |
| ansi-styles |  | 6.2.3 | MIT | dev-only | license |  |
| ansi-styles | …/builder-util/…/ansi-styles | 4.3.0 | MIT | dev-only | license |  |
| ansi-styles | …/electron-builder/…/ansi-styles | 4.3.0 | MIT | dev-only | license |  |
| ansi-styles | …/electron-publish/…/ansi-styles | 4.3.0 | MIT | dev-only | license |  |
| app-builder-lib |  | 26.18.0 | MIT | dev-only | no license file |  |
| argparse |  | 2.0.1 | Python-2.0 | dev-only | LICENSE |  |
| asn1js |  | 3.1.0 | BSD-3-Clause | dev-only | LICENSE |  |
| async |  | 3.2.6 | MIT | dev-only | LICENSE |  |
| async-exit-hook |  | 2.0.1 | MIT | dev-only | license |  |
| asynckit |  | 0.4.0 | MIT | dev-only | LICENSE |  |
| at-least-node |  | 1.0.0 | ISC | dev-only | LICENSE |  |
| aws4 |  | 1.13.2 | MIT | dev-only | LICENSE |  |
| balanced-match | …/@electron/asar/…/balanced-match | 1.0.2 | MIT | dev-only | LICENSE.md |  |
| balanced-match | …/@electron/universal/…/balanced-match | 1.0.2 | MIT | dev-only | LICENSE.md |  |
| balanced-match |  | 4.0.4 | MIT | dev-only | LICENSE.md |  |
| balanced-match | …/dir-compare/…/balanced-match | 1.0.2 | MIT | dev-only | LICENSE.md |  |
| balanced-match | …/filelist/…/balanced-match | 1.0.2 | MIT | dev-only | LICENSE.md |  |
| balanced-match | …/glob/…/balanced-match | 1.0.2 | MIT | dev-only | LICENSE.md |  |
| base64-js |  | 1.5.1 | MIT | dev-only | LICENSE |  |
| baseline-browser-mapping |  | 2.11.37 | Apache-2.0 | dev-only | LICENSE.txt |  |
| bluebird |  | 3.7.2 | MIT | dev-only | LICENSE |  |
| boolean |  | 3.2.0 | MIT | dev-only | LICENSE.txt,licenseCheck.json | optional/platform |
| brace-expansion | …/@electron/asar/…/brace-expansion | 1.1.22 | MIT | dev-only | LICENSE |  |
| brace-expansion | …/@electron/universal/…/brace-expansion | 2.1.8 | MIT | dev-only | LICENSE |  |
| brace-expansion |  | 5.0.13 | MIT | dev-only | LICENSE |  |
| brace-expansion | …/dir-compare/…/brace-expansion | 1.1.22 | MIT | dev-only | LICENSE |  |
| brace-expansion | …/filelist/…/brace-expansion | 2.1.8 | MIT | dev-only | LICENSE |  |
| brace-expansion | …/glob/…/brace-expansion | 1.1.22 | MIT | dev-only | LICENSE |  |
| browserslist |  | 4.29.5 | MIT | dev-only | LICENSE |  |
| buffer-from |  | 1.1.2 | MIT | dev-only | LICENSE |  |
| builder-util |  | 26.16.0 | MIT | dev-only | LICENSE |  |
| builder-util-runtime |  | 9.7.0 | MIT | dev-only | LICENSE |  |
| bytestreamjs |  | 2.0.1 | BSD-3-Clause | dev-only | LICENSE |  |
| cac |  | 7.1.0 | MIT | dev-only | LICENSE |  |
| cacheable-lookup |  | 5.0.4 | MIT | dev-only | LICENSE |  |
| cacheable-request |  | 7.0.4 | MIT | dev-only | LICENSE |  |
| call-bind-apply-helpers |  | 1.0.2 | MIT | dev-only | LICENSE |  |
| caniuse-lite |  | 1.0.30001826 | CC-BY-4.0 | dev-only | LICENSE |  |
| chalk | …/@electron/fuses/…/chalk | 4.1.2 | MIT | dev-only | license |  |
| chalk | …/builder-util/…/chalk | 4.1.2 | MIT | dev-only | license |  |
| chalk |  | 5.6.2 | MIT | dev-only | license |  |
| chalk | …/electron-builder/…/chalk | 4.1.2 | MIT | dev-only | license |  |
| chalk | …/electron-publish/…/chalk | 4.1.2 | MIT | dev-only | license |  |
| chownr |  | 3.0.0 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| chromium-pickle-js |  | 0.2.0 | MIT | dev-only | no license file |  |
| ci-info | …/app-builder-lib/…/ci-info | 4.3.1 | MIT | dev-only | LICENSE |  |
| ci-info |  | 4.5.0 | MIT | dev-only | LICENSE |  |
| cliui |  | 9.0.1 | ISC | dev-only | LICENSE.txt |  |
| cliui | …/electron-builder/…/cliui | 8.0.1 | ISC | dev-only | LICENSE.txt |  |
| clone-response |  | 1.0.3 | MIT | dev-only | LICENSE |  |
| color-convert |  | 2.0.1 | MIT | dev-only | LICENSE |  |
| color-name |  | 1.1.4 | MIT | dev-only | LICENSE |  |
| combined-stream |  | 1.0.8 | MIT | dev-only | License |  |
| commander |  | 5.1.0 | MIT | dev-only | LICENSE |  |
| commander | …/postject/…/commander | 9.5.0 | MIT | dev-only | LICENSE | optional/platform |
| compare-version |  | 0.1.2 | MIT | dev-only | no license file |  |
| concat-map |  | 0.0.1 | MIT | dev-only | LICENSE |  |
| concurrently |  | 10.0.7 | MIT | dev-only | LICENSE |  |
| convert-source-map |  | 2.0.0 | MIT | dev-only | LICENSE |  |
| core-util-is |  | 1.0.3 | MIT | dev-only | LICENSE |  |
| cross-dirname |  | 0.1.0 | MIT | dev-only | no license file | optional/platform |
| cross-spawn |  | 7.0.6 | MIT | dev-only | LICENSE |  |
| csstype |  | 3.2.3 | MIT | dev-only | LICENSE |  |
| debug |  | 4.4.3 | MIT | dev-only | LICENSE |  |
| decompress-response |  | 6.0.0 | MIT | dev-only | license |  |
| defer-to-connect |  | 2.0.1 | MIT | dev-only | LICENSE |  |
| define-data-property |  | 1.1.4 | MIT | dev-only | LICENSE | optional/platform |
| define-properties |  | 1.2.1 | MIT | dev-only | LICENSE | optional/platform |
| delayed-stream |  | 1.0.0 | MIT | dev-only | License |  |
| detect-libc |  | 2.1.2 | Apache-2.0 | dev-only | LICENSE |  |
| detect-node |  | 2.1.0 | MIT | dev-only | LICENSE | optional/platform |
| dir-compare |  | 4.2.0 | MIT | dev-only | LICENSE |  |
| dmg-builder |  | 26.18.0 | MIT | dev-only | no license file |  |
| dotenv |  | 16.6.1 | BSD-2-Clause | dev-only | LICENSE |  |
| dotenv-expand |  | 11.0.7 | BSD-2-Clause | dev-only | LICENSE |  |
| dunder-proto |  | 1.0.1 | MIT | dev-only | LICENSE |  |
| duplexer2 |  | 0.1.4 | BSD-3-Clause | dev-only | LICENSE.md |  |
| ejs |  | 3.1.10 | Apache-2.0 | dev-only | LICENSE |  |
| electron-builder |  | 26.18.0 | MIT | dev-only | LICENSE |  |
| electron-builder-squirrel-windows |  | 26.18.0 | MIT | dev-only | LICENSE |  |
| electron-publish |  | 26.18.0 | MIT | dev-only | LICENSE |  |
| electron-to-chromium |  | 1.5.485 | ISC | dev-only | LICENSE |  |
| electron-vite |  | 6.0.0 | MIT | dev-only | LICENSE |  |
| electron-winstaller |  | 5.4.0 | MIT | dev-only | LICENSE |  |
| emoji-regex | …/electron-builder/…/emoji-regex | 8.0.0 | MIT | dev-only | LICENSE-MIT.txt |  |
| emoji-regex |  | 10.6.0 | MIT | dev-only | LICENSE-MIT.txt |  |
| end-of-stream |  | 1.4.5 | MIT | dev-only | LICENSE |  |
| enhanced-resolve |  | 5.27.0 | MIT | dev-only | LICENSE |  |
| env-paths | …/app-builder-lib/…/env-paths | 2.2.1 | MIT | dev-only | license |  |
| env-paths |  | 3.0.0 | MIT | dev-only | license |  |
| env-paths | …/node-gyp/…/env-paths | 2.2.1 | MIT | dev-only | license |  |
| err-code |  | 2.0.3 | MIT | dev-only | no license file |  |
| es-define-property |  | 1.0.1 | MIT | dev-only | LICENSE |  |
| es-errors |  | 1.3.0 | MIT | dev-only | LICENSE |  |
| es-object-atoms |  | 1.1.2 | MIT | dev-only | LICENSE |  |
| es-set-tostringtag |  | 2.1.0 | MIT | dev-only | LICENSE |  |
| es6-error |  | 4.1.1 | MIT | dev-only | LICENSE.md | optional/platform |
| esbuild |  | 0.28.2 | MIT | dev-only | LICENSE.md |  |
| escalade |  | 3.2.0 | MIT | dev-only | license |  |
| escape-string-regexp |  | 4.0.0 | MIT | dev-only | license | optional/platform |
| exponential-backoff |  | 3.1.3 | Apache-2.0 | dev-only | LICENSE |  |
| fast-deep-equal |  | 3.1.3 | MIT | dev-only | LICENSE |  |
| fast-uri |  | 3.1.9 | BSD-3-Clause | dev-only | LICENSE |  |
| fdir |  | 6.5.0 | MIT | dev-only | LICENSE |  |
| filelist |  | 1.0.6 | Apache-2.0 | dev-only | no license file |  |
| form-data |  | 4.0.6 | MIT | dev-only | License |  |
| fs-extra | …/@electron/fuses/…/fs-extra | 9.1.0 | MIT | dev-only | LICENSE |  |
| fs-extra | …/@electron/notarize/…/fs-extra | 9.1.0 | MIT | dev-only | LICENSE |  |
| fs-extra | …/@electron/universal/…/fs-extra | 11.4.1 | MIT | dev-only | LICENSE |  |
| fs-extra | …/@electron/windows-sign/…/fs-extra | 11.4.1 | MIT | dev-only | LICENSE | optional/platform |
| fs-extra | …/@malept/flatpak-bundler/…/fs-extra | 9.1.0 | MIT | dev-only | LICENSE |  |
| fs-extra | …/app-builder-lib/…/@electron/get/…/fs-extra | 8.1.0 | MIT | dev-only | LICENSE |  |
| fs-extra | …/electron-winstaller/…/fs-extra | 7.0.1 | MIT | dev-only | LICENSE |  |
| fs-extra |  | 10.1.0 | MIT | dev-only | LICENSE |  |
| fs-extra | …/unzipper/…/fs-extra | 11.3.1 | MIT | dev-only | LICENSE |  |
| fs.realpath |  | 1.0.0 | ISC | dev-only | LICENSE |  |
| fsevents |  | 2.3.3 | MIT | dev-only | not installed here (lockfile only) | optional/platform |
| function-bind |  | 1.1.2 | MIT | dev-only | LICENSE |  |
| gensync |  | 1.0.0-beta.2 | MIT | dev-only | LICENSE |  |
| get-caller-file |  | 2.0.5 | ISC | dev-only | LICENSE.md |  |
| get-east-asian-width |  | 1.7.0 | MIT | dev-only | license |  |
| get-intrinsic |  | 1.3.0 | MIT | dev-only | LICENSE |  |
| get-proto |  | 1.0.1 | MIT | dev-only | LICENSE |  |
| get-stream |  | 5.2.0 | MIT | dev-only | license |  |
| glob |  | 7.2.3 | ISC | dev-only | LICENSE |  |
| global-agent |  | 3.0.0 | BSD-3-Clause | dev-only | LICENSE | optional/platform |
| globalthis |  | 1.0.4 | MIT | dev-only | LICENSE | optional/platform |
| gopd |  | 1.2.0 | MIT | dev-only | LICENSE |  |
| got |  | 11.8.6 | MIT | dev-only | license |  |
| graceful-fs |  | 4.2.12 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| has-flag |  | 4.0.0 | MIT | dev-only | license |  |
| has-property-descriptors |  | 1.0.2 | MIT | dev-only | LICENSE | optional/platform |
| has-symbols |  | 1.1.0 | MIT | dev-only | LICENSE |  |
| has-tostringtag |  | 1.0.2 | MIT | dev-only | LICENSE |  |
| hasown |  | 2.0.4 | MIT | dev-only | LICENSE |  |
| hosted-git-info |  | 4.1.0 | ISC | dev-only | LICENSE |  |
| http-cache-semantics |  | 4.3.0 | BSD-2-Clause | dev-only | LICENSE |  |
| http-proxy-agent |  | 7.0.2 | MIT | dev-only | LICENSE |  |
| http2-wrapper |  | 1.0.3 | MIT | dev-only | LICENSE |  |
| https-proxy-agent |  | 7.0.6 | MIT | dev-only | LICENSE |  |
| inflight |  | 1.0.6 | ISC | dev-only | LICENSE |  |
| inherits |  | 2.0.4 | ISC | dev-only | LICENSE |  |
| is-fullwidth-code-point |  | 3.0.0 | MIT | dev-only | license |  |
| isarray |  | 1.0.0 | MIT | dev-only | no license file |  |
| isbinaryfile | …/@electron/osx-sign/…/isbinaryfile | 4.0.10 | MIT | dev-only | LICENSE.txt |  |
| isbinaryfile |  | 5.0.7 | MIT | dev-only | LICENSE.txt |  |
| isexe | …/cross-spawn/…/isexe | 2.0.0 | ISC | dev-only | LICENSE |  |
| isexe |  | 3.1.5 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| isexe | …/node-gyp/…/isexe | 4.0.0 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| jake |  | 10.9.4 | Apache-2.0 | dev-only | no license file |  |
| jiti |  | 2.7.0 | MIT | dev-only | LICENSE |  |
| js-tokens |  | 4.0.0 | MIT | dev-only | LICENSE |  |
| js-yaml |  | 4.3.2 | MIT | dev-only | LICENSE |  |
| jsesc |  | 3.1.0 | MIT | dev-only | LICENSE-MIT.txt |  |
| json-buffer |  | 3.0.1 | MIT | dev-only | LICENSE |  |
| json-schema-traverse |  | 1.0.0 | MIT | dev-only | LICENSE |  |
| json-stringify-safe |  | 5.0.1 | ISC | dev-only | LICENSE | optional/platform |
| json5 |  | 2.2.3 | MIT | dev-only | LICENSE.md |  |
| jsonfile | …/app-builder-lib/…/jsonfile | 4.0.0 | MIT | dev-only | LICENSE |  |
| jsonfile | …/electron-winstaller/…/jsonfile | 4.0.0 | MIT | dev-only | LICENSE |  |
| jsonfile |  | 6.2.1 | MIT | dev-only | LICENSE |  |
| keyv |  | 4.5.4 | MIT | dev-only | no license file |  |
| lazy-val |  | 1.0.5 | MIT | dev-only | no license file |  |
| lightningcss |  | 1.33.0 | MPL-2.0 | dev-only | LICENSE |  |
| lightningcss-android-arm64 |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-darwin-arm64 |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-darwin-x64 |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-freebsd-x64 |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-linux-arm-gnueabihf |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-linux-arm64-gnu |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-linux-arm64-musl |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-linux-x64-gnu |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-linux-x64-musl |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-win32-arm64-msvc |  | 1.33.0 | MPL-2.0 | dev-only | not installed here (lockfile only) | optional/platform |
| lightningcss-win32-x64-msvc |  | 1.33.0 | MPL-2.0 | dev-only | LICENSE | optional/platform |
| lodash |  | 4.18.1 | MIT | dev-only | LICENSE |  |
| lowercase-keys |  | 2.0.0 | MIT | dev-only | license |  |
| lru-cache | …/hosted-git-info/…/lru-cache | 6.0.0 | ISC | dev-only | LICENSE |  |
| lru-cache |  | 5.1.1 | ISC | dev-only | LICENSE |  |
| magic-string |  | 1.4.5 | MIT | dev-only | LICENSE |  |
| matcher |  | 3.0.0 | MIT | dev-only | license | optional/platform |
| math-intrinsics |  | 1.1.0 | MIT | dev-only | LICENSE |  |
| mime |  | 2.6.0 | MIT | dev-only | LICENSE |  |
| mime-db |  | 1.52.0 | MIT | dev-only | LICENSE |  |
| mime-types |  | 2.1.35 | MIT | dev-only | LICENSE |  |
| mimic-response | …/decompress-response/…/mimic-response | 3.1.0 | MIT | dev-only | license |  |
| mimic-response |  | 1.0.1 | MIT | dev-only | license |  |
| minimatch | …/@electron/asar/…/minimatch | 3.1.5 | ISC | dev-only | LICENSE |  |
| minimatch | …/@electron/universal/…/minimatch | 9.0.9 | ISC | dev-only | LICENSE |  |
| minimatch | …/dir-compare/…/minimatch | 3.1.5 | ISC | dev-only | LICENSE |  |
| minimatch | …/filelist/…/minimatch | 5.1.9 | ISC | dev-only | LICENSE |  |
| minimatch | …/glob/…/minimatch | 3.1.5 | ISC | dev-only | LICENSE |  |
| minimatch |  | 10.2.6 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| minimist |  | 1.2.8 | MIT | dev-only | LICENSE |  |
| minipass |  | 7.1.3 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| minizlib |  | 3.1.0 | MIT | dev-only | LICENSE |  |
| mkdirp |  | 0.5.6 | MIT | dev-only | LICENSE |  |
| ms |  | 2.1.3 | MIT | dev-only | license.md |  |
| nanoid |  | 3.3.20 | MIT | dev-only | LICENSE |  |
| node-abi |  | 4.40.0 | MIT | dev-only | LICENSE |  |
| node-api-version |  | 0.2.1 | MIT | dev-only | no license file |  |
| node-gyp |  | 12.4.0 | MIT | dev-only | LICENSE |  |
| node-int64 |  | 0.4.0 | MIT | dev-only | LICENSE |  |
| node-releases |  | 2.0.64 | MIT | dev-only | LICENSE |  |
| nopt |  | 9.0.0 | ISC | dev-only | LICENSE |  |
| normalize-url |  | 6.1.0 | MIT | dev-only | license |  |
| object-keys |  | 1.1.1 | MIT | dev-only | LICENSE | optional/platform |
| once |  | 1.4.0 | ISC | dev-only | LICENSE |  |
| p-cancelable |  | 2.1.1 | MIT | dev-only | license |  |
| p-limit |  | 3.1.0 | MIT | dev-only | license |  |
| path-is-absolute |  | 1.0.1 | MIT | dev-only | license |  |
| path-key |  | 3.1.1 | MIT | dev-only | license |  |
| pe-library |  | 0.4.1 | MIT | dev-only | LICENSE |  |
| picocolors |  | 1.1.1 | ISC | dev-only | LICENSE |  |
| picomatch |  | 4.0.7 | MIT | dev-only | LICENSE |  |
| pkijs |  | 3.4.3 | BSD-3-Clause | dev-only | LICENSE |  |
| plist |  | 3.1.0 | MIT | dev-only | LICENSE |  |
| postcss |  | 8.5.33 | MIT | dev-only | LICENSE |  |
| postject |  | 1.0.0-alpha.6 | MIT | dev-only | LICENSE | optional/platform |
| proc-log |  | 6.1.0 | ISC | dev-only | LICENSE |  |
| process-nextick-args |  | 2.0.1 | MIT | dev-only | license.md |  |
| progress |  | 2.0.3 | MIT | dev-only | LICENSE |  |
| promise-retry |  | 2.0.1 | MIT | dev-only | LICENSE |  |
| proper-lockfile |  | 4.1.2 | MIT | dev-only | LICENSE |  |
| pump |  | 3.0.4 | MIT | dev-only | LICENSE |  |
| pvtsutils |  | 1.3.6 | MIT | dev-only | LICENSE |  |
| pvutils |  | 1.2.0 | MIT | dev-only | LICENSE |  |
| quick-lru |  | 5.1.1 | MIT | dev-only | license |  |
| read-binary-file-arch |  | 1.0.6 | MIT | dev-only | no license file |  |
| readable-stream |  | 2.3.8 | MIT | dev-only | LICENSE |  |
| require-directory |  | 2.1.1 | MIT | dev-only | LICENSE |  |
| require-from-string |  | 2.0.2 | MIT | dev-only | license |  |
| resedit |  | 1.7.2 | MIT | dev-only | LICENSE |  |
| resolve-alpn |  | 1.2.1 | MIT | dev-only | LICENSE |  |
| responselike |  | 2.0.1 | MIT | dev-only | LICENSE |  |
| retry |  | 0.12.0 | MIT | dev-only | License |  |
| rimraf |  | 2.6.3 | ISC | dev-only | LICENSE |  |
| roarr |  | 2.15.4 | BSD-3-Clause | dev-only | LICENSE | optional/platform |
| rolldown |  | 1.2.19 | MIT | dev-only | LICENSE,THIRD-PARTY-LICENSE |  |
| rxjs |  | 7.8.2 | Apache-2.0 | dev-only | LICENSE.txt |  |
| safe-buffer |  | 5.1.2 | MIT | dev-only | LICENSE |  |
| sanitize-filename |  | 1.6.5 | WTFPL OR ISC | dev-only | AUTHORS,LICENSE.md |  |
| sax |  | 1.6.1 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| semver | …/@babel/core/…/semver | 6.3.2 | ISC | dev-only | LICENSE |  |
| semver | …/@babel/helper-compilation-targets/…/semver | 6.3.2 | ISC | dev-only | LICENSE |  |
| semver | …/app-builder-lib/…/@electron/get/…/semver | 6.3.2 | ISC | dev-only | LICENSE |  |
| semver | …/app-builder-lib/…/semver | 7.7.4 | ISC | dev-only | LICENSE |  |
| semver |  | 7.8.6 | ISC | dev-only | LICENSE |  |
| semver | …/tiny-async-pool/…/semver | 5.7.3 | ISC | dev-only | LICENSE |  |
| semver-compare |  | 1.0.0 | MIT | dev-only | LICENSE | optional/platform |
| serialize-error |  | 7.0.1 | MIT | dev-only | license | optional/platform |
| shebang-command |  | 2.0.0 | MIT | dev-only | license |  |
| shebang-regex |  | 3.0.0 | MIT | dev-only | license |  |
| shell-quote |  | 1.12.0 | MIT | dev-only | LICENSE |  |
| signal-exit |  | 3.0.7 | ISC | dev-only | LICENSE.txt |  |
| simple-update-notifier |  | 2.0.0 | MIT | dev-only | LICENSE |  |
| source-map |  | 0.6.1 | BSD-3-Clause | dev-only | LICENSE |  |
| source-map-js |  | 1.2.2 | BSD-3-Clause | dev-only | LICENSE |  |
| source-map-support |  | 0.5.21 | MIT | dev-only | LICENSE.md |  |
| sprintf-js |  | 1.1.3 | BSD-3-Clause | dev-only | LICENSE | optional/platform |
| stat-mode |  | 1.0.0 | MIT | dev-only | LICENSE |  |
| string-width | …/electron-builder/…/string-width | 4.2.3 | MIT | dev-only | license |  |
| string-width |  | 7.2.0 | MIT | dev-only | license |  |
| string_decoder |  | 1.1.1 | MIT | dev-only | LICENSE |  |
| strip-ansi | …/electron-builder/…/strip-ansi | 6.0.1 | MIT | dev-only | license |  |
| strip-ansi |  | 7.2.0 | MIT | dev-only | license |  |
| sumchecker |  | 3.0.1 | Apache-2.0 | dev-only | LICENSE |  |
| supports-color | …/@electron/fuses/…/supports-color | 7.2.0 | MIT | dev-only | license |  |
| supports-color | …/builder-util/…/supports-color | 7.2.0 | MIT | dev-only | license |  |
| supports-color | …/electron-builder/…/supports-color | 7.2.0 | MIT | dev-only | license |  |
| supports-color | …/electron-publish/…/supports-color | 7.2.0 | MIT | dev-only | license |  |
| supports-color |  | 10.2.2 | MIT | dev-only | license |  |
| tapable |  | 2.3.4 | MIT | dev-only | LICENSE |  |
| tar |  | 7.5.23 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| temp |  | 0.9.4 | MIT | dev-only | LICENSE |  |
| temp-file |  | 3.4.0 | MIT | dev-only | no license file |  |
| tiny-async-pool |  | 1.3.0 | MIT | dev-only | LICENSE-MIT |  |
| tinyglobby |  | 0.2.17 | MIT | dev-only | LICENSE |  |
| tmp |  | 0.2.7 | MIT | dev-only | LICENSE |  |
| tmp-promise |  | 3.0.3 | MIT | dev-only | no license file |  |
| tree-kill |  | 1.2.2 | MIT | dev-only | LICENSE |  |
| truncate-utf8-bytes |  | 1.0.2 | WTFPL | dev-only | AUTHORS |  |
| tslib | …/@tailwindcss/oxide-wasm32-wasi/…/tslib | 2.8.1 | 0BSD | dev-only | LICENSE.txt | optional/platform |
| tsx |  | 4.23.15 | MIT | dev-only | LICENSE |  |
| type-fest |  | 0.13.1 | (MIT OR CC0-1.0) | dev-only | license | optional/platform |
| typescript |  | 7.0.2 | Apache-2.0 | dev-only | LICENSE,NOTICE.txt |  |
| undici | …/node-gyp/…/undici | 6.29.1 | MIT | dev-only | LICENSE |  |
| undici |  | 7.30.2 | MIT | dev-only | LICENSE | optional/platform |
| undici-types | …/electron/…/undici-types | 7.24.6 | MIT | dev-only | LICENSE |  |
| undici-types |  | 8.9.0 | MIT | dev-only | LICENSE |  |
| universalify | …/app-builder-lib/…/universalify | 0.1.2 | MIT | dev-only | LICENSE |  |
| universalify | …/electron-winstaller/…/universalify | 0.1.2 | MIT | dev-only | LICENSE |  |
| universalify |  | 2.0.1 | MIT | dev-only | LICENSE |  |
| unzipper |  | 0.12.5 | MIT | dev-only | LICENSE |  |
| update-browserslist-db |  | 1.3.4 | MIT | dev-only | LICENSE |  |
| utf8-byte-length |  | 1.0.5 | (WTFPL OR MIT) | dev-only | AUTHORS,LICENSE.MIT.txt,LICENSE.WTFPL.txt |  |
| util-deprecate |  | 1.0.2 | MIT | dev-only | LICENSE |  |
| vite |  | 8.3.8 | MIT | dev-only | LICENSE.md |  |
| webcrypto-core |  | 1.9.2 | MIT | dev-only | LICENSE |  |
| which | …/cross-spawn/…/which | 2.0.2 | ISC | dev-only | LICENSE |  |
| which | …/node-gyp/…/which | 6.0.1 | ISC | dev-only | LICENSE |  |
| which |  | 5.0.0 | ISC | dev-only | LICENSE |  |
| wrap-ansi | …/electron-builder/…/wrap-ansi | 7.0.0 | MIT | dev-only | license |  |
| wrap-ansi |  | 9.0.2 | MIT | dev-only | license |  |
| wrappy |  | 1.0.2 | ISC | dev-only | LICENSE |  |
| xmlbuilder |  | 15.1.1 | MIT | dev-only | LICENSE |  |
| y18n |  | 5.0.8 | ISC | dev-only | LICENSE |  |
| yallist | …/hosted-git-info/…/yallist | 4.0.0 | ISC | dev-only | LICENSE |  |
| yallist | …/tar/…/yallist | 5.0.0 | BlueOak-1.0.0 | dev-only | LICENSE.md |  |
| yallist |  | 3.1.1 | ISC | dev-only | LICENSE |  |
| yargs | …/electron-builder/…/yargs | 17.7.3 | MIT | dev-only | LICENSE |  |
| yargs |  | 18.0.0 | MIT | dev-only | LICENSE |  |
| yargs-parser | …/electron-builder/…/yargs-parser | 21.1.1 | ISC | dev-only | LICENSE.txt |  |
| yargs-parser |  | 22.0.0 | ISC | dev-only | LICENSE.txt |  |
| yocto-queue |  | 0.1.0 | MIT | dev-only | license |  |

### Python

Engine, Mac bundle (resolved for macOS arm64, CPython 3.12): MIT 23, BSD-3-Clause 11, Apache-2.0 8, UNKNOWN (not on disk) 5, PSF-2.0 2, Apache-2.0 OR BSD-3-Clause 1, MIT-CMU 1, BSD-2-Clause 1, MIT OR Apache-2.0 1, MPL-2.0 1, BSD-2-Clause (field says BSD; text is 2-clause) 1, MIT-0 1

Cloud (Render, Linux): MIT 8, BSD-3-Clause 7, Apache-2.0 OR BSD-3-Clause 1, MPL-2.0 1, UNKNOWN (not on disk) 1, PSF-2.0 1, MIT-0 1, Apache-2.0 1

Dev-only: MIT 4, Apache-2.0 2, LGPL-3.0-only 2, BSD-3-Clause (classifier only; text is 3-clause) 1, Apache-2.0 OR BSD-2-Clause 1, BSD-2-Clause 1

| Package | Version on disk | License | Engine (Mac bundle) | Cloud | Dev | License files in dist-info |
|---|---|---|---|---|---|---|
| annotated-doc | 0.0.6 | MIT | yes | yes |  | LICENSE |
| annotated-types | 0.8.0 | MIT | yes | yes |  | LICENSE |
| anthropic | 2.8.0 | Apache-2.0 | yes |  |  | LICENSE, LICENSE-MIT |
| anyio | 4.16.0 | MIT | yes | yes |  | LICENSE |
| attrs | 26.1.0 | MIT | yes |  |  | LICENSE |
| certifi | 2026.10.23 | MPL-2.0 | yes | yes |  | LICENSE |
| cffi | 2.1.1 | MIT-0 | yes | yes |  | LICENSE |
| charset-normalizer | 3.5.2 | MIT | yes |  |  | LICENSE |
| click | 8.5.1 | BSD-3-Clause | yes | yes |  | LICENSE.txt |
| colorama | 0.4.6 | BSD-3-Clause (classifier only; text is 3-clause) |  |  | yes | LICENSE.txt |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | yes | yes |  | LICENSE, LICENSE.APACHE, LICENSE.BSD |
| defusedxml | 0.7.1 | PSF-2.0 | yes |  |  | LICENSE |
| distro | 1.9.0 | Apache-2.0 | yes |  |  | LICENSE |
| docstring_parser | 0.18.0 | MIT | yes |  |  | LICENSE.md |
| fastapi | 0.163.1 | MIT | yes | yes |  | LICENSE |
| google-auth | 2.62.2 | Apache-2.0 | yes |  |  | LICENSE |
| google-genai | 3.3.0 | Apache-2.0 | yes |  |  | LICENSE |
| h11 | 0.16.0 | MIT | yes | yes |  | LICENSE.txt |
| httpcore | 1.0.9 | BSD-3-Clause | yes | yes |  | LICENSE.md |
| httpcore2 | 2.16.0 | BSD-3-Clause | yes |  |  | LICENSE.md |
| httptools | 0.9.0 | MIT | yes |  |  | LICENSE, LICENSE-MIT, LICENSE |
| httpx | 0.28.1 | BSD-3-Clause | yes | yes |  | LICENSE.md |
| httpx2 | 2.16.0 | BSD-3-Clause | yes |  |  | LICENSE.md |
| idna | 3.20 | BSD-3-Clause | yes | yes |  | LICENSE.md |
| iniconfig | 2.3.1 | MIT |  |  | yes | LICENSE |
| jiter | 0.19.0 | MIT | yes |  |  | LICENSE |
| jsonschema | 4.26.0 | MIT | yes |  |  | COPYING |
| jsonschema-specifications | 2025.9.1 | MIT | yes |  |  | COPYING |
| opentelemetry-api | 1.45.2 | Apache-2.0 | yes | yes |  | LICENSE |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |  |  | yes | LICENSE, LICENSE.APACHE, LICENSE.BSD |
| pillow | 13.0.0 | MIT-CMU | yes |  |  | LICENSE |
| pluggy | 1.7.0 | MIT |  |  | yes | LICENSE |
| psycopg | 3.3.9 | LGPL-3.0-only |  |  | yes | LICENSE.txt |
| psycopg-binary | 3.3.9 | LGPL-3.0-only |  |  | yes | LICENSE.txt |
| pyasn1 | 0.6.5 | BSD-2-Clause | yes |  |  | LICENSE.rst |
| pyasn1_modules | 0.4.2 | BSD-2-Clause (field says BSD; text is 2-clause) | yes |  |  | LICENSE.txt |
| pycparser | 3.12 | BSD-3-Clause | yes | yes |  | LICENSE |
| pydantic | 2.14.3 | MIT | yes | yes |  | LICENSE |
| pydantic_core | 2.50.4 | MIT | yes | yes |  | LICENSE |
| Pygments | 2.21.0 | BSD-2-Clause |  |  | yes | AUTHORS, LICENSE |
| pyjwt | — | UNKNOWN: not on disk; upstream expected MIT, unverified |  | yes |  | — |
| pyobjc-framework-applicationservices | — | UNKNOWN: not on disk (macOS-only wheel); upstream expected MIT, unverified | yes |  |  | — |
| pyobjc-framework-quartz | — | UNKNOWN: not on disk; upstream expected MIT, unverified | yes |  |  | — |
| pyobjc-framework-screencapturekit | — | UNKNOWN: not on disk; upstream expected MIT, unverified | yes |  |  | — |
| pyobjc-framework-vision | — | UNKNOWN: not on disk; upstream expected MIT, unverified | yes |  |  | — |
| pytest | 9.2.0 | MIT |  |  | yes | LICENSE |
| pytest-asyncio | 1.5.0 | Apache-2.0 |  |  | yes | LICENSE |
| python-dotenv | 1.2.4 | BSD-3-Clause | yes |  |  | LICENSE |
| PyYAML | 6.0.3 | MIT | yes |  |  | LICENSE |
| RapidFuzz | 3.14.6 | MIT | yes |  |  | LICENSE |
| referencing | 0.37.0 | MIT | yes |  |  | COPYING |
| requests | 2.34.2 | Apache-2.0 | yes |  |  | LICENSE, NOTICE |
| rpds-py | 2026.9.1 | MIT | yes |  |  | LICENSE |
| ruff | 0.17.5 | MIT |  |  | yes | LICENSE |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | yes |  |  | LICENSE, LICENSE.APACHE2, LICENSE.MIT |
| starlette | 1.10.0 | BSD-3-Clause | yes | yes |  | LICENSE.md |
| tenacity | 9.1.4 | Apache-2.0 | yes |  |  | LICENSE |
| truststore | 0.10.5 | MIT | yes |  |  | LICENSE |
| typing_extensions | 4.16.0 | PSF-2.0 | yes | yes |  | LICENSE |
| typing-inspection | 0.4.5 | MIT | yes | yes |  | LICENSE |
| tzdata | 2026.6 | Apache-2.0 |  |  | yes | LICENSE, LICENSE_APACHE |
| urllib3 | 2.8.0 | MIT | yes |  |  | LICENSE.txt |
| uvicorn | 0.54.0 | BSD-3-Clause | yes | yes |  | LICENSE.md |
| uvloop | — | UNKNOWN: not on disk (no Windows wheel); upstream expected MIT OR Apache-2.0, unverified | yes |  |  | — |
| watchdog | 7.1.0 | Apache-2.0 | yes |  |  | AUTHORS, COPYING, LICENSE |
| watchfiles | 1.3.0 | MIT | yes |  |  | LICENSE |
| websockets | 17.4 | BSD-3-Clause | yes |  |  | LICENSE |
| youtube-transcript-api | 1.2.5 | MIT | yes |  |  | LICENSE |

### Binary and non-package components

| Component | Version | License | Where | Verified how |
|---|---|---|---|---|
| Electron | 45.3.2 | MIT | all desktop builds | `LICENSE.electron.txt` in `win-unpacked` |
| Chromium components (500) | Electron 45.3.2 | mixed, see below | all desktop builds | `LICENSES.chromium.html` (5.7 MB) in `win-unpacked` |
| ffmpeg (`ffmpeg.dll` / `libffmpeg.dylib`) | Chromium's | LGPL-2.1-or-later (Chromium credits) | all desktop builds | DLL strings: h264, hevc, opus, vorbis, flac, theora |
| d3dcompiler_47.dll | — | Microsoft redistributable | Windows | file present in `win-unpacked` |
| dxcompiler.dll, vk_swiftshader.dll, vulkan-1.dll, icudtl.dat | — | per Chromium credits (DXC, SwiftShader Apache-2.0, Vulkan loader Apache-2.0, ICU) | Windows | files present |
| NSIS | 3.0.4.1 | Zlib; bzip2-1.0.6; CPL-1.0 + exception (LZMA) | Windows installer | `COPYING` in the electron-builder cache |
| nsis7z.dll | nsis-resources 3.4.1 | UNKNOWN (7-Zip-based; LGPL-2.1+ likely) | Windows installer | DLL version info: "7-Zip NSIS Plug-in", © Igor Pavlov et al. |
| StdUtils.dll | nsis-resources 3.4.1 | UNKNOWN | Windows installer | DLL version info: © 2004-2018 LoRd_MuldeR |
| UAC.dll, nsProcess.dll, SpiderBanner.dll, WinShell.dll | nsis-resources 3.4.1 | UNKNOWN | Windows installer | no license or copyright strings |
| elevate.exe | 2019 build | UNKNOWN | Windows app `resources/` | version info: (c) 2007 Johannes Passing |
| python-build-standalone CPython | 3.12.16 + 20261026 | PSF-2.0 + bundled libraries | next Mac DMG | UNVERIFIED (pinned in `bundle-engine.mjs`; no archive on disk) |
| OpenSSL (static, in cryptography) | 4.0.3 (Windows wheel) | Apache-2.0 | Mac DMG engine; cloud | `cryptography-50.0.2.dist-info/sboms/sbom.json` |
| Pillow bundled libraries | brotli 1.2.0, freetype 2.14.3, harfbuzz 14.5.0, lcms2 2.19.1, libavif 1.4.2 (+dav1d, aom, libyuv), libjpeg-turbo 3.2.0, libpng 1.6.58, libwebp 1.6.0, openjpeg 2.5.4, tiff 4.7.2, xz 5.8.4, zlib-ng 2.3.3 (Windows wheel) | as in Pillow's LICENSE (FTL/GPL-2.0 dual for FreeType; IJG+BSD-3; BSD; MIT; 0BSD; Zlib) | Mac DMG engine | `pillow-13.0.0.dist-info/licenses/LICENSE` (1,629 lines) + SBOM |
| Rust crates in wheels | — | cryptography 39 crates, pydantic-core 101, jiter 38, rpds-py 17, watchfiles 26: all MIT/Apache/BSD/Zlib/Unicode/CC0, or OR-choices with GPL-2.0/LGPL-2.1 options (`self_cell`, `r-efi`) | Mac DMG engine | `*.dist-info/sboms/*.cyclonedx.json` |
| Google Sans Flex (woff2) | 4.005, subset | OFL-1.1 | app renderer, site, web/download | fontTools `name` table; `app/brand/fonts/OFL.txt` |
| three.js, lenis | 0.160.0, 1.1.13 | MIT | site, loaded from jsDelivr (not hosted) | `miyagi-site/index.html` |
| YouTube IFrame API | live | YouTube API Services Terms (proprietary) | app + site, loaded at runtime | `features/player/youtube.ts`, `main/serve.ts` CSP |

### Chromium credits entries whose license text mentions LGPL, GPL, MPL or CC (43 of 500)

Keyword scan of `LICENSES.chromium.html`. Most are dual or tri-licensed (MPL/GPL/LGPL for NSS/NSPR; MIT-or-GPL for JSZip), file-level MPL-2.0 (symphonia, hunspell) or Linux-only (glibc, gtk, libsecret, Speech Dispatcher, v4l-utils, plasma-wayland-protocols). Electron keeps these compliant upstream; miyagi only needs to keep shipping the file.

AXE-CORE Accessibility Audit · Android NDK · Braille Translation Library · DirectX-Shader-Compiler · EasyList (CC) · Eigen · ISimpleDOM COM interfaces · JSZip · Mozilla Personal Security Manager · Mozilla Windows Cert code · NSPR · Node.js · SPIRV-Headers (CC) · ScreenAI Library · Snappy (CC) · Speech Dispatcher · WebKit · **ffmpeg (LGPL)** · glibc · grpc · gtk · hunspell · hunspell dictionaries · hyphenation-patterns · icu · libbrlapi · libsecret · libusbx · plasma-wayland-protocols · symphonia (12 crates) · url_parse · v4l-utils
