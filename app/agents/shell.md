# shell

**Status (Nov 20, branch `michael/app-shell`):** the home window is an app shell with a persistent left sidebar and six pages. Typecheck green. Checked in the browser stage at 1440x900 (headless shots plus DOM checks in the in-app browser). Not verified in Electron.

## First run in this window (lane oneflow, Nov 21)
`flow/` (FlowLayer, Strip, FlowMark, SidebarBrand, store, motion, web): until setup is over, a full-window flow layer
covers the shell, sidebar included (intro, Sign in, guided setup, You're ready), then hands over: its screen fades,
then its paper while the sidebar slides in from the left, the bonsai lands in the sidebar's logo (`FlowMark`, layoutId
shared with the flow) and the wordmark writes in after it, Home rises in. Shell.tsx mounts nothing of home under a first
run, wraps everything in one `LayoutGroup`, and ignores ⌘1..⌘6 during the flow. Setup again (Finish setup, Settings'
Open setup: `openSetup`) runs the flow over home, which stays mounted and inert under it. Spec and timeline:
agents/onboarding.md "One window". Sidebar.tsx: only the logo row changed (`SidebarBrand` in place of the mark and
wordmark).

## Goal
Michael, after trying the app: "It should be like a dashboard on the left. I should be able to click different pages." The home window (route `library`: the Dock click, the tray's "Open miyagi" and setup's Start all open it) is now a real app shell.

## Owns
- `app/src/renderer/src/features/shell/**` (no `index.tsx`: it is not a registered feature, the library window renders it)
  - `store.ts` pages, the page on show, visited pages, the Settings page's section, `openPage(page, section?)`
  - `Shell.tsx` layout, page frames (keep-alive), headers, ⌘1..⌘6, error boundary per page, the preview overlay
  - `Sidebar.tsx` brand, nav with the sliding selection and arrow keys, status, account chip, compact mode
  - `pages/SkillsPage.tsx`, `pages/ProgressPage.tsx`, `pages/SettingsPage.tsx`, `pages/AccountPage.tsx`
- In `features/library`: `LibraryWindow.tsx` (renders the shell, reads `{id}` and `{page, section}` args), `Library.tsx` (now the Lessons page body plus `LessonSearch`, `greeting`, `openLauncher`; its old sidebar and header moved to the shell), `Detail.tsx` (`back` prop: names the page and drops the traffic-light inset), `Status.tsx` (`plan` prop: the sidebar hides the plan row because the account chip shows it).

## Pages
| Page | What | States |
|---|---|---|
| Home (⌘1) | `features/library` Home, unchanged; header: greeting, date, quiet New lesson | Home's own (loading hero, first run, offline, empty parts) |
| Lessons (⌘2) | Continue, Ready to run with tool chips, paste card; header: search + New lesson (the one primary) | skeletons, offline with nothing cached, empty ("No lessons on this Mac yet."), no match ("Show all") |
| Skills (⌘3) | the full constellation, plus a side panel: the selected skill's card (SkillCard), else each track's headline and share mastered | constellation's loading / "No skills yet"; panel skeleton; offline line |
| Progress (⌘4) | the Progress window's body (`Dashboard`) inline, never the separate window | dashboard's own per part; offline note above it |
| Settings (⌘5) | General, Permissions, Privacy, Your key, Shortcuts (the sheet's section components) under a Segmented | sections' own; `live` only while the page is on show |
| Account (⌘6) | Shipped (LOGIN_ENABLED, see agents/auth.md): signed in, avatar initial, name, email, Sign out, Use your own key; signed out, "Sign in to sync your progress across Macs" whose Sign in opens the login window (`openLogin()`). v2Cloud (mock): who, plan, help meter, Upgrade (primary, Free only), Use your own key, Sign out. Login off: "No account needed" | skeleton card until auth:get answers; no answer reads as signed out |

Every page sits in its own error boundary: a crash shows "This page didn't load." with Try again; the other pages keep working.

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
1. DONE (`michael/app-login-wire`): `openLibrary({page, section?})` in `core/surfaces.ts`; `openPage` now calls it.
2. DONE (`michael/app-login-wire`), differently: the login has its own `auth` app route, opened with `openLogin()`; the account window's `login` view is gone.
3. Tray / Dock / setup's Start could pass `{page: 'home'}` once (1) exists; today they open the window on whatever page it was left on, Home when new.
4. Settings sheet: `permissions:watch` is one switch in main; the sheet and this page both toggle it while on show. Harmless today (both stop on hide), but a counter in main would be cleaner.

## Exports reused (no new exports needed)
`features/dashboard`: `Constellation`, `useDashView`, `Dashboard`, `SkillCard`, `trackHeadline`, `useDash`. `features/settings`: `sections/*`, `useKeyFlow`, `Sidebar.NAV`. `features/account`: `model`, `store`, `ui` (`Chip`, `MenuRow`, `MeterGroup`, `PersonGlyph`, `Rule`). All were already exported from their modules.

## Not done / next
- Not verified in Electron (traffic lights over the sidebar's top strip, the drag regions, ⌘1..⌘6 against the app menu).
- Skills: no pan / zoom yet (optional in the brief).
