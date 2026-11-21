# shell

**Status (Nov 21, branch `michael/app-account-sheet`):** sign-in and the account live INSIDE the home window as a sheet (see "Account sheet" below). No `openLogin()` or account-window call is left anywhere the home window can reach. Typecheck green. Checked in the browser stage at 1440x900 and 900x700 (headless frames plus DOM checks). Not verified in Electron.

**Status (Nov 20, branch `michael/app-shell`):** the home window is an app shell with a persistent left sidebar and six pages. Typecheck green. Checked in the browser stage at 1440x900 (headless shots plus DOM checks in the in-app browser). Not verified in Electron.

## Goal
Michael, after trying the app: "It should be like a dashboard on the left. I should be able to click different pages." The home window (route `library`: the Dock click, the tray's "Open miyagi" and setup's Start all open it) is now a real app shell.

## Owns
- `app/src/renderer/src/features/shell/**` (no `index.tsx`: it is not a registered feature, the library window renders it)
  - `store.ts` pages, the page on show, visited pages, the Settings page's section, `openPage(page, section?)`
  - `Shell.tsx` layout, page frames (keep-alive), headers, ⌘1..⌘6, error boundary per page, the preview overlay
  - `Sidebar.tsx` brand, nav with the sliding selection and arrow keys, status, account chip, compact mode
  - `pages/SkillsPage.tsx`, `pages/ProgressPage.tsx`, `pages/SettingsPage.tsx`, `pages/AccountPage.tsx`
  - `sheet.ts` the account sheet's kind (`signin`, `account`, `signout`, `plans`), `openSheet`, `closeSheet`, `openAccountSurface` (sheet when a home window hosts it, else the old window)
  - `AccountSheet.tsx` the sheet host (scrim, sheet, focus trap, Esc), the sheet bodies, `SharedAvatar`
- In `features/library`: `LibraryWindow.tsx` (renders the shell, reads `{id}` and `{page, section}` args), `Library.tsx` (now the Lessons page body plus `LessonSearch`, `greeting`, `openLauncher`; its old sidebar and header moved to the shell), `Detail.tsx` (`back` prop: names the page and drops the traffic-light inset), `Status.tsx` (`plan` prop: the sidebar hides the plan row because the account chip shows it).

## Pages
| Page | What | States |
|---|---|---|
| Home (⌘1) | `features/library` Home, unchanged; header: greeting, date, quiet New lesson | Home's own (loading hero, first run, offline, empty parts) |
| Lessons (⌘2) | Continue, Ready to run with tool chips, paste card; header: search + New lesson (the one primary) | skeletons, offline with nothing cached, empty ("No lessons on this Mac yet."), no match ("Show all") |
| Skills (⌘3) | the full constellation, plus a side panel: the selected skill's card (SkillCard), else each track's headline and share mastered | constellation's loading / "No skills yet"; panel skeleton; offline line |
| Progress (⌘4) | the Progress window's body (`Dashboard`) inline, never the separate window | dashboard's own per part; offline note above it |
| Settings (⌘5) | General, Permissions, Privacy, Your key, Shortcuts (the sheet's section components) under a Segmented | sections' own; `live` only while the page is on show |
| Account (⌘6) | Shipped (LOGIN_ENABLED, see agents/auth.md): signed in, avatar initial, name, email, Sign out (asks first, in the sheet), Use your own key; signed out, "Sign in to sync your progress across Macs" whose Sign in opens the sign-in sheet. v2Cloud (mock): who, plan, help meter, Upgrade (primary, Free only: the plans sheet), Use your own key, Sign out. Login off: "No account needed" | skeleton card until auth:get answers; no answer reads as signed out |

Every page sits in its own error boundary: a crash shows "This page didn't load." with Try again; the other pages keep working.

## Account sheet (Nov 21)
Michael: one polished app, not windows stacked on windows. Sign-in and the account open as a sheet that slides down from the top of the content area; the content dims, the sidebar stays lit.

| Kind | Opened by | What |
|---|---|---|
| `signin` | the sidebar chip (signed out), Account page › Sign in, StatusArea's Account row | the bonsai-free login, re-drawn from features/auth: New user / Returning user (sliding thumb), Google / Apple / GitHub boxes (Google live through `auth:google`, the others "Soon"), Cancel while the browser runs (`auth:cancel`), Not now, Terms and Privacy, the auth note line. A sign-in that lands here turns into "You're signed in" with one Done. |
| `account` | the sidebar chip (signed in), StatusArea's plan row | avatar, name, email; Use your own key (On/Off, goes to Settings › Your key), Sign out. v2Cloud adds the plan chip, the help meter, Upgrade to Pro (primary) or See plans. |
| `signout` | Account page › Sign out, the account sheet's Sign out, "Not you?" | "Sign out of miyagi?" Cancel (back to the account sheet if it came from there) and Sign out (the one primary, `auth:sign-out`, or the mock's in v2Cloud) |
| `plans` | v2Cloud's Upgrade / See plans | features/account `Pricing` on a paper sheet, scrolling inside |

- **Motion.** Open: scrim fades to ~45% black (240 ms); the sheet slides down 16 px on the house spring, its surface fades in fast (80 ms), then the header and rows rise 6 px, 35 ms apart. The avatar is a shared element (`layoutId`): it flies from the sidebar chip into the sheet's header and back on close, and the chip keeps a recessed empty socket meanwhile. Switching kinds (account → sign out, Cancel back, sign-in landing, a sign-in note appearing): the two bodies crossfade at the same time (`AnimatePresence mode="popLayout"`: the old body is lifted out of the flow, inert, and fades in 80 ms; the new one's rows start rising at 20 ms, 35 ms apart). DarkSheet re-renders in the same commit as the body swap (it also subscribes to the auth note), so the surface's `layout` spring has its before snapshot and really springs to the new height (scale transform, radius corrected; measured frame by frame, 192 → 144 px over ~230 ms, no jump). Whole switch under 300 ms. Header lines crossfade with a 4 px rise. Close: lifts 8 px and fades in 120 ms. The avatar flying home is one avatar: `layoutCrossfade={false}` and the leaving sheet's copy is hidden at once (`useIsPresent`), and the chip lifts itself to z 45 (above the scrim at 30 and the sheet at 40) only while the flight runs (`onLayoutAnimationStart/Complete`). Account → Plans: the avatar snaps into the chip (layout transition 0), no flight across the paper sheet. Transform and opacity only; reduced motion = fades (MotionConfig).
- **Closing.** Esc (caught in the capture phase, so a preview, skill card or search behind never sees it), a click on the scrim, a click on the sidebar, the close button, Not now, or ⌘1..⌘6 (closes and still switches; the same chords Shell.tsx takes: 1..PAGES.length, no Alt, no Shift, so ⌘7 or ⌘⇧2 leave it open). Closing while the browser sign-in runs cancels it (`auth:cancel`), like Esc in the login window. Closing also clears a sign-in error note (`say(undefined)`), and so does opening a fresh sign-in sheet, so a reopened sheet never shows the last session's error. A sheet that is leaving takes no clicks and is no longer a dialog.
- **Focus.** The sheet takes focus on open; Tab and Shift+Tab cycle inside it; the sidebar, the pages and a preview behind it are `inert` (pages also `aria-hidden`). Focus goes back to what opened it (usually the chip). A kind switch moves focus into the new body: Cancel on the sign-out confirm (the safe default), Done on "You're signed in", the Sign out row when Cancel comes back to the account; otherwise the sheet itself. Focus never drops to `<body>`.
- **`auth:continue` is not called** from the sheet: main records the learner's choice on a successful sign-in already (`auth.ts` `decide()`), and from the home window continue could open guided setup as a second window.
- Stage: `&sheet=<signin|account|signout|plans>` opens it on load. `&v2Cloud=0` for the shipped login (the stage defaults to the v2Cloud mock), `&auth=signedin` for a signed-in fixture. Port 6011 for this pass.
- Shots: `miyagi-v2/screens/round5/sheet-*.jpg` (frame sequences: `01-open-signin-*`, `03-signed-in-*`, `04-close-*`, `11-open-account-*`, `12-to-signout-*`, `13-signed-out-*`, `42-plans-*`; stills: home signed out / in, over Skills, Account page, v2Cloud, compact).
- Fix round 1 (Nov 21) shots: `round5/sheet-fix1-*` (a: account ⇄ sign out by click and Enter, close; b: sign out to signed out; c: account → plans and close; d: sign-in lands; e: failed sign-in, reopen clean). Sampled every frame: surface height springs, one avatar in flight, focus lands as above, the chip's z-index resets after the flight.
- Checked (DOM): dialog + focus inside on open, sidebar inert, 12 Tabs stay inside, Google → pending → signed in morph, Esc closes and focus returns to the chip, scrim click closes, sidebar click closes and stays on the page, sign out from the confirm flips the chip to signed out, no console errors.

## Behavior
- **Instant switches, state kept.** A visited page stays mounted, hidden with `visibility: hidden` + `inert` + `aria-hidden`, so its scroll, search text, open skill card and key drafts survive. The incoming page rises 6 px and fades in on the house spring (opacity only with reduced motion); the outgoing one hides at once.
- **Sidebar.** The selection is one shape that slides between rows (`layoutId`, house spring). Roving focus: only the selected row is a tab stop; Up / Down / Home / End move and switch. Below 880 px of window width the sidebar is icons only (64 px, labels as tooltips); below 700 px of height the status block hides. The account chip at the foot opens Account.
- **Keys.** ⌘1..⌘6 (Ctrl+1..6 on Windows) pick a page. Esc never closes this window: it closes a lesson preview, a skill card, or clears the search. No keycap is drawn for ⌘1..⌘6 (keycaps only from `platform.keys`, which has none for them); rows carry `aria-keyshortcuts`.
- **Previews.** A lesson's preview opens over the content area (sidebar stays) with "Back to <page>"; switching pages closes it.
- **Deep links.** `openLibrary(id)` = Lessons with that preview. `openLibrary()` again = same page, preview closed. `openPage(page, section?)` (shell/store.ts) = `openWindow('library', {page, section})`. Home's "See all N" lands on Lessons (the shell reads Library's section change).
- **Title** stays "miyagi" (main's window title and index.html; the shell never sets `document.title`).

## Stage
Port 5801 (this pass). `?scenario=home&window=library&size=1440x900&clean` plus `&page=<home|lessons|skills|progress|settings|account>`, `&section=<general|permissions|privacy|account|shortcuts>` for Settings, `&signedout` (Account signed out), `&library=empty`, `?scenario=dashboard` for skills data, `&size=900x700` for the compact sidebar.
Shots: `miyagi-v2/screens/round4/shell-*.jpg` (home, lessons, skills, skills-data, skills-card, progress, progress-data, settings, settings-key, account, account-signedout, preview, compact, lessons-filter, lessons-empty, home-data, offline-cached).

Checked in the stage (DOM): a skill click opens its card in the panel; ⌘2 / ⌘1 / ⌘2 keeps the Lessons scroll; the skill card survives a trip to Lessons; ArrowDown from Skills selects Progress and keeps focus on it; Esc leaves the window open; a lesson card opens the preview with "Back to Lessons", Esc closes it; Settings segment switch; Account › Use your own key lands on Settings › Your key; `openWindow('library', {page})`, `{page:'settings', section:'privacy'}`, `openLibrary(id)` and `openLibrary()` all land right; `setSection('library')` goes to Lessons twice in a row; no console errors.

## Core requests
5. (Nov 21, account sheet) `features/auth/Login.tsx`: export `ModeSwitch` and `ProviderBox` (and the GitHub glyph) so the sheet can render them instead of its faithful copies in `shell/AccountSheet.tsx`. Auth lane.
6. (Nov 21) `auth:continue` from the home window: either a `{from: 'home'}` arg that only records the choice (no guided setup, no window), or leave it uncalled as now. Onboarding / one-window lane.
7. (Nov 21) `core/surfaces.ts` `openLogin()` / `openAccount()` are now unused from the home window; the tray, the first run and other windows still use them. When the one-window flow lands, they could route to `openPage('account')` plus a sheet arg (`{page, sheet}` in LibraryTarget) so nothing opens a second window.
8. (Nov 21) v2Cloud only: Pricing's "Add a key" still calls `openSettings('account')` (the settings window). In the home window it could go to Settings › Your key (`setSettingsSection('account'); setPage('settings')`). Account lane.
1. DONE (`michael/app-login-wire`): `openLibrary({page, section?})` in `core/surfaces.ts`; `openPage` now calls it.
2. DONE (`michael/app-login-wire`), differently: the login has its own `auth` app route, opened with `openLogin()`; the account window's `login` view is gone.
3. Tray / Dock / setup's Start could pass `{page: 'home'}` once (1) exists; today they open the window on whatever page it was left on, Home when new.
4. Settings sheet: `permissions:watch` is one switch in main; the sheet and this page both toggle it while on show. Harmless today (both stop on hide), but a counter in main would be cleaner.

## Exports reused (no new exports needed)
`features/dashboard`: `Constellation`, `useDashView`, `Dashboard`, `SkillCard`, `trackHeadline`, `useDash`. `features/settings`: `sections/*`, `useKeyFlow`, `Sidebar.NAV`. `features/account`: `model`, `store`, `ui` (`Chip`, `MenuRow`, `MeterGroup`, `PersonGlyph`, `Rule`). All were already exported from their modules.

## Not done / next
- Not verified in Electron (traffic lights over the sidebar's top strip, the drag regions, ⌘1..⌘6 against the app menu).
- Skills: no pan / zoom yet (optional in the brief).
