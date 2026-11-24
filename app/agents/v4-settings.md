# v4-settings: the Settings page, v4 (Adrian's ui-next mock, settings / settings-apps / settings-data)

Branch `michael/v4-settings` (from `origin/michael/app-ui-v4`). Stage port 5255.

## Status (Nov 24)
- The home window's Settings page (`features/shell/pages/SettingsPage.tsx`) is the v4 layout: its own list
  (Account; App: General, Shortcuts, Notifications; Learning: Lessons, Apps; Privacy: Permissions, Your data, Your own
  key; About at the foot), a 32 px panel title with a lede, and two columns of groups with flat hairline rows (one
  column under 720 px of panel). The pill-born sheet is unchanged.
- `Flat` (settings/ui.tsx): inside the page, `Group` draws a 15 px section head with a hairline and `Row` drops its
  icon tile and padding, so ptt's Push to talk group and every other panel match without their own code changing.
- General (v4/Panels.tsx `General4`): Appearance (theme, text size, density, compact sidebar, reduce motion, the
  buddy's color), Startup (Open miyagi keycap, launch at login, start page, where miyagi lives: notch place), Sound,
  Push to talk, Help as you learn (tips, setup status, reset tips, tour, setup), Updates, Reset. Language is cut (one
  option, Adrian's trim pass). Appearance folds into General; Editor rows into Lessons.
- Apps (`Apps4`): Code, Sheets and design, 3D and CAD, Games, Everything else, with "Used by N plans." Engine health
  (vscode, jupyter, any id it reports) decides the status; otherwise the typed placeholder in v4/facts.ts.
- Your data (`Data4`): During a lesson (the privacy facts, word for word, and a link to the full list), On this Mac
  (lesson folder, lesson cache with its size), Your progress (export), Help improve miyagi (the share switch), Account
  (signed in as, plan, Delete account, which opens the Privacy panel straight on its two-step confirm).
- Kept working: notch place, launch at login, keys (Your own key), the privacy share switch, the delete flow, search
  still works in the sheet.

See it: `npm run dev:web -- --port 5255`, then
`http://localhost:5255/?scenario=settings&window=library&page=settings&size=1440x900&clean`; click Apps / Your data.

## Remaining differences vs the mock (round 3)
- Frame (shell lane): the mock swaps the app sidebar for the settings list and shows "Settings / General" as a
  breadcrumb; here the list sits beside the app sidebar under the shell's own "Settings" page header, so each column
  is about 340 px, not 492.
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
  `data:open-folder`. Until they land the rows say "Not ready yet." and Electron shows no cache size.
- `apps:connect:<id>` (Blender, FreeCAD, Fusion, Onshape add-ons), or the ui-v4 contract's app list; then
  v4/facts.ts `APPS` is replaced by the contract data (plans count from the catalog).
- Shell lane: on the Settings page, swap the app sidebar for `settings/v4/PageNav` and show a "Settings / <panel>"
  crumb (the panel is `useNav((s) => s.page)` in settings/nav.ts).

## Shots
`agents/shots/v4-settings-r{0..3}-ours-{light,dark}-{general,apps,data}.png`,
`v4-settings-r2-mock-{light,dark}-{general,apps,data}.png`, widths `v4-settings-w1024-*`, `-w1280-*`, `-w1728-*`.
