# app-ambient: help outside a lesson (explain errors, set up this project, how do I)

Contract: `shared/contracts/AMBIENT-HELP.md` (Nov 24). Branch `michael/app-ambient-help` off `michael/app-ui-v4`.
Stage: `npm run dev:web -- --port 5263` → `http://localhost:5263/?scenario=ambient-help` (port in `agents/ports.json`).

## Status (pass 1)

Works in the browser stage against the `ambient-help` mock, light and dark (`agents/shots/ambient-*.png`):

1. **Error chip.** On `error.seen`, with no lesson running, the notch drops one quiet line: "Error in Terminal · Explain ✕".
   - One chip at a time. A newer error takes the chip.
   - The same id again only updates the chip. An id that already had its turn never comes back.
   - `{id, clear}` fades it. It auto-hides after 20 s, and the pointer resting on it holds it.
   - It never shows during a lesson, with the setting off, or for a muted app.
2. **Explain card** (priority 46, 400 wide). Explain sends `error.explain {id}`, the only moment the error leaves the Mac. The engine redacts the text. Then:
   - The card shows "Reading the error…", then the title, why, fix, `$ command`, and a diff when there is one.
   - One white primary: "Install <tool>" when the fix is an install (it sends `setup.fix`, and `setup.progress` lines show), otherwise "Copy fix".
   - "Show me" (lilac) makes bon point at `target` (or the error's `rect`) through the annotate and buddy stores.
   - "Not in Terminal" mutes that app.
   - ✕ or Esc sends `error.dismiss`.
   - A fail gets a calm line (cap, offline, busy, gone), with "Try again" where a retry makes sense.
3. **Settings > General: "Help outside lessons".** It has the "Offer help with errors" switch (on by default) and the muted apps with Unmute. Both the v4 page (`General4`) and the sheet (`sections/General`) show it.
   - `ambient.set {errors, mutedApps}` goes out on every `engine.hello` that lists it, and on every change.
   - Only the overlay window (or the stage) sends it.
4. **Launcher "Set up this project".** It matches "set up this project", "install dependencies", "check my environment"… but not a topic like "set up a React app". It sends `setup.scan`.
   - The setup card (priority 47) lists rows, missing first, with Fix (`setup.fix {tool, root}`) or "Get it" for a licensed app's page. A licensed app is never installed.
   - The card has "Fix all N" (one by one), the progress line under the running row, `+N more`, and the env line.
   - A closed card stays closed for that scan's later reports.
5. **Launcher "How do I…".** Typed outside a lesson, the row reads "Show me in <App>", where the app is main's front-app reading. It sends `help.ask {text, app, source: typed}`.
   - The notch line reads "Looking at Blender", then "1 of 4 · Click File in the top bar  Back  Next ✕", and bon points at each step's target.
   - Next, Back and ✕ send `help.nav`. `done` closes the line after 2.5 s. A late re-send never reopens a help the learner closed.

Every command is gated on `engine.hello.capabilities`. Model calls happen only on a click (Explain, a sent help.ask), and the app never sends a screenshot.

## How to see it

Open `?scenario=ambient-help`.
- The chip comes about 1.5 s after connect. Click Explain, then Show me, then Install pandas.
- Ctrl+K and type `set up this project`, then Enter, then Fix or Fix all.
- Ctrl+K and type `how do I export this as an STL?`, then Enter, then Next.
- For the settings: Ctrl+K, type `settings`, then General.

Playwright scripts: `~/miyagi/tools/playwright/ambient-shots.mjs <port> <outdir>` and `ambient-settings.mjs`. Unit tests: `test/ambient.test.ts` (30).

## Files

- `features/ambient/`: `model.ts` (pure rules), `store.ts`, `prefs.ts`, `point.ts`, `Lines.tsx` (chip, help line), `Cards.tsx` (explain, setup), `Settings.tsx`, `commands.ts`, and `index.tsx` (island modes: chip 22, help 23, explain 46, setup 47).
- Outside the folder (registration only):
  - `launcher/Launcher.tsx`: the command row, the same slot as the Settings row.
  - `launcher/Rows.tsx`: `SettingsRow` takes a title, meta, icon and data attribute.
  - `settings/v4/Panels.tsx` and `settings/sections/General.tsx`: `<AmbientSettings />`.

## Notes

- The chip and the help line are pill-sized modes at priorities 22 and 23, above the notch hover home (21). Otherwise, moving the pointer onto Explain opens the home panel over it.
- The mock's `setup.fix` always installs pandas, so in the stage "Fix all" on other rows waits forever. A fresh report that shows a running row as ok also ends that install.

## Core requests

1. **Prefs.** Add `ambient: { errors: boolean; mutedApps: string[] }` to `common/prefs.ts` so main keeps it in prefs.json. Until then it lives in localStorage (`miyagi.ambient`), shared across windows through the `storage` event.
2. **Launcher command registry.** A registry would let features add command rows without touching `Launcher.tsx`. Today ambient adds two small edits there.
