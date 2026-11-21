# account

**Status:** pass 1 done, stage-verified (Electron side typechecked, not run) · **Plan:** A9 · **Port:** 5194 · **Branch:** `michael/app-account` · **Flag:** `v2Cloud` · **PR:** draft into `adrian/shell`

## Goal
The account surfaces from the miyagi v2 mockups, shipped as UI on mock data behind `v2Cloud` (off in a normal build): the account menu, the Upgrade sheet, Sign in, and Pricing on the paper tokens. No network, no auth, no billing, no quota that blocks a lesson.

## Owns
- `app/src/renderer/src/features/account/**`: `index.tsx` (feature, `enabled: v2Cloud`, app window route `account`), `model.ts` (flag, types, IPC cleaning), `store.ts`, `AccountWindow.tsx`, `Menu.tsx`, `Upgrade.tsx`, `SignIn.tsx`, `Pricing.tsx`, `ui.tsx`, `web.ts` (stage stand-ins + fixture)
- `app/src/main/features/account.ts` (fixed links only, no tokens, no protocol handler)
- `app/mock/scenarios/account.json` (a lesson on step 3 of 6 behind the window, so the stage shows the lesson is not blocked)
- `app/agents/account.md`

## What works (stage)
`npm run dev:web -- --port 5194`, then `http://localhost:5194/?scenario=account&account=<view>&size=1440x900&clean` with `<view>` = `menu | upgrade | signin | pricing`. Extras: `&plan=pro` (Pro account: no Upgrade button, Pro is the current plan), `&signedout` (account:get answers null, so the window opens on Sign in).

- **One app window, four views** (decision 4: an app window, not born from the island). `openAccount(view)` picks the view; inside, Upgrade to Pro → Pricing, Sign out → Sign in. **Esc** goes back one view, or closes the window on the first one.
- **Menu** (Plan-AccountMenu): avatar, name, email, plan chip (neutral outline), "Help this month" meter (white bar on the dark track), Resets on <day>, **Upgrade to Pro** (the one primary, Free only), My lessons → `openLibrary()`, Settings with the `settings` keycap from `bridge.platform.keys` → `openSettings()`, **Use your own key → `openSettings('account')`** with On/Off read from `settings:get` (`{set}` only, never a key), Sign out.
- **Upgrade** (Plan-Upgrade): "You've used this month's free help." / "Your lesson stays open. Checks keep working." Full meter, "Upgrade to Pro, <price> a month" (price only when the catalog has one) → Pricing; Use my own key → `openSettings('account')`; Not now with the `dismiss` keycap closes the window. Verified: closing it leaves the lesson running.
- **Sign in** (Plan-SignIn): Apple / Google / email link are UI only. Each says "Sign in is not live yet. Nothing was sent." The email lives in component state only and is cleared on submit (checked: field empty, nothing in localStorage or the URL). Terms and Privacy go through `account:open`.
- **Pricing** (Plan-Pricing) on `theme.paper`: ink text, ink primary (Upgrade to Pro), ink meter, ink checks, no hue. Monthly / Yearly segmented (paper). Free, Pro (Recommended, ink outline), Teams, Bring your own key (dashed; Add a key → `openSettings('account')`). Paid prices come from the account's catalog; with none the card says "Price coming soon" (no invented number). Footer meter with the reset day and "Checks on your work never count. Cancel anytime." Four columns from 1100 px wide, two below (the account window is 720 wide, see Core requests 2), scrolling.
- **Main** (`account.ts`): `account:get` → null (no backend in this push); `account:open(link)` maps a link name to a fixed `https://miyagi.study/...` page through `safeOpenExternal` (the renderer never passes a URL, nothing is appended); `account:sign-out` → nothing stored to forget. Every handler answers false/null unless `MIYAGI_V2_CLOUD=1`.
- **Flag:** the renderer feature mounts only when `v2Cloud` is on: always in the browser stage (mock data), in Electron only for a build with `VITE_MIYAGI_V2_CLOUD=1`.

Checks: `npm run typecheck` green. Brand grep on the package files: no hex, no typed keycaps, no Cursor, no `dangerouslySetInnerHTML`, no `console.log`, no `openExternal` outside `safeOpen`, no em dashes, no localStorage.

## Deviations from the mockups (brand or plan rules)
- The menu does not drop from an avatar in the pill: the pill is A2's, and decision 4 makes the account surfaces an app window. The window centers the card on `surface.sheet` (the Plan-SignIn backdrop).
- The Sign in and Pricing marks are the color bonsai (BRAND.md), not the mockup's white/ink trunk. "Sign in to miyagi" is plain text (`copy.name`), not a retyped wordmark; Pricing uses `MiyagiWordmark`.
- Keycaps: `⌘,` and `Esc` come from `platform.keys.settings` / `dismiss`.
- Placeholders ([NAME], [PRICE], [N], [DATE]) are a stage fixture in `web.ts` (Sam Rivera, $12 / $10, $8 / $7, 20 and 300 help requests, December 1, save 17%). They are mock data, not a pricing decision.
- Mac-only copy switches on `platform.os` ("on every Mac" / "on every computer", "Key kept in your Mac's Keychain" / "secure storage").

## Not verified
Electron (`npm run dev`): the app window, the `account:*` handlers, `safeOpenExternal` of the miyagi.study pages. The four-column Pricing layout (the window never gets 1100 wide until Core request 2). No shots saved in `shots/`: the browser pane can't write PNG files here and there is no headless Chrome in this worktree; the states were checked by screenshot and DOM in the pane.

## Core requests
1. **One shared `v2Cloud` flag** (e.g. `core/flags.ts` plus the same value in main): today the renderer reads the build-time `VITE_MIYAGI_V2_CLOUD` and main reads the runtime `MIYAGI_V2_CLOUD`. A7's limit card (priority 58) needs the same switch.
2. **Pricing window size** (`main/appWindows.ts`, `dev/Stage.tsx`): open `account` with `{view:'pricing'}` at `windowSize.pricing` (1200x760), or add a `pricing` route. Until then Pricing reflows to two columns at 720x560.
3. **Refuse the `account` route when `v2Cloud` is off** (`main/appWindows.ts`): with the feature unmounted, a stray `openAccount()` would show main.tsx's "No feature window" line.
4. **Entry points (other lanes, only with `v2Cloud`):** A2 an avatar in the pill → `openAccount('menu')`; A7's limit card → `openAccount('upgrade')`; A4 `settings:open` honoring `{section:'account'}` (already in core-v2 notes).
5. **Site pages:** `miyagi.study/pricing`, `/teams`, `/terms`, `/privacy`, `/account` must exist before `v2Cloud` ships (the host is already on the `safeOpen` allowlist).
6. **Real account data** later comes from the proxy's `GET /v1/me` (DISTRIBUTION-PLAN) into `account:get`, in the shape of `Account` in `model.ts` (`cleanAccount` already bounds it).
