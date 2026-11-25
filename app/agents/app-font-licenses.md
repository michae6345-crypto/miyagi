# app-font-licenses: font and license hygiene (Nov 24)

Branch `michael/app-font-licenses` (from `michael/app-ui-v4`). Asked: "are we using Google hosted fonts? make sure we can't get sued over that".

## Facts
- No font loads from Google's servers. Both fonts are bundled woff2 files served from the app itself:
  - Bricolage Grotesque (`src/renderer/src/assets/fonts/*.woff2`, the app font; also inlined in the splash).
  - Google Sans Flex (`brand/fonts/GoogleSansFlex.woff2`, `@font-face` in styles.css, no token uses it since Nov 24).
- Both are SIL Open Font License 1.1: free to bundle and ship in a paid app. Condition 2 is the one we were missing:
  the copyright notice and the license must travel with every copy of the font.
- The built app's CSP already allows fonts only from the app (`font-src 'self' data:`, main/serve.ts).

## What changed
- **Shipped with the app**: top-level `extraResources` in `electron-builder.yml` copies into `Contents/Resources/licenses/`
  (`resources\licenses` on Windows; electron-builder merges it with the mac: and win: lists):
  - `fonts/BricolageGrotesque-OFL.txt`, `fonts/GoogleSansFlex-OFL.txt`
  - `THIRD-PARTY-NOTICES.txt`: the npm packages bundled into the app (react, react-dom, scheduler, motion and its
    parts, lucide-react, zustand, ws, tslib), each with its full license text (MIT / ISC / 0BSD want the notice kept).
    `node scripts/third-party-notices.mjs` writes it; `--check` says what is missing.
  - Electron and Chromium already ship theirs (`Resources/LICENSE.electron.txt`, `LICENSES.chromium.html`; electron-builder
    moves them into the .app on a Mac). The notices file points at them.
  - Checked against electron-builder's own `getFileMatchers` with this yml: the three files land in `licenses/` on mac and
    win. The renderer bundle (app.asar) also carries the OFL text, through the view below.
- **Settings > About > Open-source licenses** is live (was in Coming soon). "View" opens it in place of About's rows,
  "‹ About" goes back, leaving the panel closes it. It lists both fonts with copyright and license, a Source button
  to each project's GitHub page (`open:external`, github.com is on safeOpen's allowlist), the line "Other open-source
  parts are listed in the app's licenses folder.", and the OFL 1.1 in full in a 320 px scrolling block (the text is
  the bundled `BricolageGrotesque-OFL.txt?raw`, cut at the license banner, with both copyright lines on top).
  Files: `features/settings/licenses.ts` (data, store, `licenseText`), `LicensesView.tsx`, a row change in `rows.tsx`,
  the header and the About case in `Content.tsx`.
- **Guard test** `test/fontLicenses.test.ts`: fails on any `fonts.googleapis.com` / `fonts.gstatic.com`, remote font
  file, remote `@font-face` url, remote `@import` or remote `new FontFace` in `src/` or `brand/` code; on a CSP font-src
  that is more than `'self' data:`; on a .woff2/.woff/.ttf/.otf under `src/` or `brand/` with no license .txt beside it;
  on a bundled `@font-face` family missing from the About list; on electron-builder no longer copying a license; and on
  a shipped npm package missing from THIRD-PARTY-NOTICES.txt. A self-test proves the remote-font check can fail.

## Shots
`agents/shots/licenses-light.png`, `licenses-dark.png` (the view), `licenses-about-light.png`, `licenses-about-dark.png`
(About with the live row). Headless Playwright on dev:web 5813: no request left localhost, no console errors.

## Not done
- `brand/fonts/OFL.txt` also names Anybody, Shantell Sans and Syne, which are no longer in the repo. It ships as
  `GoogleSansFlex-OFL.txt` as is (it holds the Google Sans Flex copyright and the same OFL); trimming it is a brand-kit call.
- Google Sans Flex is still loaded by styles.css though nothing uses it (~size only, not a legal issue).
- Not packaged end to end here (no `dist:mac` run); the next signed build should show `Contents/Resources/licenses/`.
