# v4-settings: the Settings page, v4 (Adrian's ui-next mock, settings / settings-apps / settings-data)

Branch `michael/v4-settings` (from `origin/michael/app-ui-v4`). Stage port 5255.

## Status (Nov 24)
- The home window's Settings page (`features/shell/pages/SettingsPage.tsx`) is the v4 layout: while it shows, the
  shell's sidebar draws Settings' own list instead of the app's pages (`setSidebarList`; Account; App: General,
  Shortcuts, Notifications; Learning: Lessons, Apps; Privacy: Permissions, Your data, Your own key; About at the foot),
  the top bar reads "Settings / <panel>" (`setCrumbs`), and the panel sits in the shell's v4 `PageFrame` (1040 column):
  a 32 px panel title with a lede, and two columns of groups with flat hairline rows (492 each once the pane is 1120
  wide; one column under 720 px). Needs `michael/v4-shell` (merged into this branch). The pill-born sheet is unchanged.
- Segmented controls on the page are the settings feature's own 26 px `Seg` (settings/ui.tsx, inside `Flat`); no
  page-level stylesheet restyles core controls. ptt's chord picker uses core's Segmented directly, so it stays 32 px.
- `Flat` (settings/ui.tsx): inside the page, `Group` draws a 15 px section head with a hairline and `Row` drops its
  icon tile and padding, so ptt's Push to talk group and every other panel match without their own code changing.
- General (v4/Panels.tsx `General4`): Appearance (theme, text size, density, compact sidebar, reduce motion, the
  buddy's color), Startup (Open miyagi keycap, launch at login, start page, where miyagi lives: notch place), Sound,
  Push to talk, Help as you learn (tips, setup status, reset tips, tour, setup), Updates, Reset. Language is cut (one
  option, Adrian's trim pass). Appearance folds into General; Editor rows into Lessons.
- Apps (`Apps4`): Code, Sheets and design, 3D and CAD, Games, Everything else, with "Used by N plans." Connected shows
  only when the engine's health item for that app is ok; with no item the row says "Reads exactly" or "Screen only".
  Connect (add-on apps) is disabled in Electron until main has `apps:connect:<id>`; it works on the stage.
- Your data (`Data4`): During a lesson (the privacy facts, word for word, and a link to the full list), On this Mac
  (lesson folder, lesson cache with its size), Your progress (Download), Help improve miyagi (the share switch), Account
  (signed in as, plan, Delete account, which opens the Privacy panel straight on its two-step confirm).
- Kept working: notch place, launch at login, keys (Your own key), the privacy share switch, the delete flow, search
  still works in the sheet.

See it: `npm run dev:web -- --port 5255`, then
`http://localhost:5255/?scenario=settings&window=library&page=settings&size=1440x900&clean`; click Apps / Your data.

## Remaining differences vs the mock (round 4)
- Shell lane bug: the shell's legacy "Settings" title still shows above the panel title. styles.css hides it with
  `.mg-page-frame:has([data-v4-frame]) > [data-legacy-header] { display: none }`, but that rule is in `@layer base`
  and loses to the header's Tailwind `flex` utility (computed display stays flex). Fix in the shell lane (move the
  rule out of the base layer or `!important`); nothing to change here.
- Brand over mock: Connected is a white tick and the word, not green. Quiet buttons and toggles are core's
  (36 px buttons with a filled track, the core toggle), not the mock's 30 px outline and white knob.
- Sounds is Off / Subtle (the real setting), not a switch. No "Read steps aloud" (voice is off) and no "Update
  automatically" (no such setting yet). Extra rows the app has: Show me around, Set up miyagi, Push to talk, the buddy's color.
- The keycap is one cap from `bridge.platform.keys.launcher` (⌥Space), the mock draws two.
- Your data: copy is the honest privacy facts, not the mock's placeholder lines ("Screenshots: Not kept" is not what
  the engine does). "Clear lesson history" is left out (no handler, destructive). "Kept in your account" is "Your
  progress" (progress lives in ~/miyagi on this Mac).
- No "Plan and usage" row: Account opens the account page, which holds the plan.

## Core requests
- Main handlers for Your data: `data:summary` → `{ folder, cacheBytes, lessons }`, `data:cache-clear`,
  `data:open-folder`. Until they land, Open and Clear are disabled in Electron (they work on the stage) and Electron
  shows no cache size.
- `apps:connect:<id>` (Blender, FreeCAD, Fusion, Onshape add-ons), or the ui-v4 contract's app list; then
  v4/facts.ts `APPS` is replaced by the contract data (plans count from the catalog).
- Shell lane: the legacy-title CSS rule above (base layer loses to `flex`).

## Shots
`agents/shots/v4-settings-r4-ours-{light,dark}-{general,apps,data}.png` (1280x800 stage), one width:
`v4-settings-w1024-light-general.png`. Adrian's mock shots live on `origin/adrian/ui-next` (docs/ui-next/shots).
