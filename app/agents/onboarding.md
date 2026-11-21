# onboarding (A3)

**Status:** pass 1 done: typecheck green, brand lint clean, four stage shots, stage flows driven end to end. Electron not run (cost freeze; Michael checks the TCC prompts on his Mac) · **Priority:** P0 (first run) · **Port:** 5188 · **Branch:** `michael/app-onboarding` · **PR:** draft #171 into `adrian/shell`

## Goal
First run, one window: the four things miyagi needs (Screen Recording, Accessibility, the VS Code companion, the engine
with its cloud access) as rows that update on their own, then "You're all set" and Start learning. Mid-lesson, when a
permission goes away, a recovery card grows out of the pill, keeps the learner's place, and goes away once it is back.

## Owns (BUILD-PLAN A3)
- `app/src/renderer/src/features/onboarding/**`: `index.tsx`, `store.ts`, `rows.ts`, `Onboarding.tsx`, `Welcome.tsx`, `SetupList.tsx`, `Checklist.tsx`, `Ready.tsx`, `Recovery.tsx`, `Row.tsx`, `web.ts`
- `app/src/main/features/onboarding.ts`
- `app/mock/scenarios/onboarding.json`
- `app/agents/onboarding.md`, `app/agents/shots/onboarding-*.png`

## Mockups
Onb-Setup-Full, Onb-Checklist-Mixed, Onb-Setup-Ready, Onb-Permission-Recovery.

## What it does
| Piece | How |
|---|---|
| Window `onboarding` (kind `app`) | `welcome` = Onb-Setup-Full (two panes, 944×640), `checklist` = Onb-Checklist-Mixed (720×560), `ready` = Onb-Setup-Ready once every row is green. Two panes only when the window is at least 880 wide (it is resizable). |
| First run | `main/features/onboarding.ts`: no `userData/onboarding.json` done flag → opens the window with `{view:'welcome'}` once the overlay has loaded and sets 944×640 before it shows (no animation, no jump). `MIYAGI_SKIP_ONBOARDING=1` skips it. Done is written when every row is green (and `prefs.onboarded`). Later runs: `openOnboarding()` (A4's "Set up miyagi") opens the checklist. |
| Rows (`rows.ts`, pure) | Screen Recording and Accessibility from `main/permissions.ts`; VS Code companion from the engine's `health` (hidden when health has no `companion` item, i.e. no probe); miyagi engine from the link, `main/localEngine.ts` and the cloud install token. `unknown` (engine started in Terminal, no probe) is the gray ring, "Not sure yet", and never blocks Start learning. Watching = the learner clicked the row's button and miyagi waits for the switch. |
| Engine row + cloud token (DISTRIBUTION-PLAN 4) | Connected + `cloud:get` phase + `config.status.cloud`: minting → "Setting up access for this Mac" (spinner), mint failed → "Couldn't set up access" + Try again (`cloud:retry`), paused / quota / unauthorized / offline → plain text, engine failed or missing → Try again (`engine-local:restart`), external and down → "Start the engine in Terminal". Cloud off (no proxy configured) = nothing to show. |
| Live, never prompting | `permissions:watch` only while the onboarding window is focused or a recovery card is open; `health.get` on open and every 4 s while focused, only when `engine.hello` lists it. |
| Prompts and panes | Only in click handlers: `onboarding:prompt(kind)` (main: one 1×1 capture for Screen Recording, `isTrustedAccessibilityClient(true)` for Accessibility), then core `permissions:open(kind)`. `permission.open {kind}` goes to the engine when it lists it. Screen Recording's row offers Relaunch after the click (`app.relaunch()`). |
| Companion install | `onboarding:install-companion`: VS Code's CLI at its fixed bundle path, `execFile` (no shell, minimal env), the bundled `Resources/vscode/miyagi*.vsix` + Python and Jupyter extensions. Nothing bundled (today) → falls back to the engine's own fix (`health` item `fix: "install"` → `sendAction('install', 'companion')`). Get VS Code → `open:external` (code.visualstudio.com is on the allowlist). |
| Ready | Lesson card only when the engine offers one: `library.list` (capability) answer, an item flagged `suggested` or the first ready one not started. Start learning → `library.start {id}` (zero model calls), else opens the launcher; the window closes. |
| Recovery card | Island mode `onboarding-recovery`, priority 75, 368 wide. Opens on `lesson.paused {reason:"permission"}` (kind = whichever grant is off, Screen Recording first), or when a watched grant drops mid-lesson. "Your place is saved · Step N of M · title" from `useCurrentStep`. Open System Settings (the one primary), Keep going without pointing (Accessibility only; Esc does the same), Relaunch miyagi (Screen Recording, after the click). Closes when the grant is back (notice "Accessibility is back on.") or on `lesson.resumed` / `lesson.ended`. Emits `surface {id:'recovery'}`. |

## Test
`npm run dev:web -- --port 5188` → `http://localhost:5188/?scenario=onboarding&onb=full|mixed|ready|recovery&size=1440x900&clean`
- full / mixed: Screen on, Accessibility Watching, VS Code companion Not yet, engine Running, "Turn on Accessibility and VS Code to start.", Start learning off. Click Install in VS Code (Checking, then Connected via the mock's `action:install`), then Open System Settings (the stage switches it on 2.5 s later) → Ready with the lesson card → Start learning closes the window and starts the lesson.
- ready: all four green, the first-lesson card, Start learning on.
- recovery: a lesson at step 3 of 6 pauses for Accessibility; the card shows the saved place and the rows. Open System Settings → the card closes and the pill says "Accessibility is back on."; Keep going closes it at once.
Shots: `agents/shots/onboarding-full.png`, `-mixed.png`, `-ready.png`, `-recovery.png` (taken headless over CDP, real time, 1440×900). The flows above were driven by script in the same headless page (rows' `data-state` checked at each step).
Not verified: Electron (`npm run dev`), real TCC prompts, the relaunch, the VS Code CLI install, the first-run window size on a real display.

## Deviations (and why)
- Recovery card is centered under the pill (island-born rule), not at the mockup's right edge; the mockup's "Paused · Accessibility is off" pill line is the pill's (A2/A7), the card replaces the pill while it is open.
- Watching glyph is the dashed gray ring (decision 5), not the mockup's arc. Keycaps are `platform.keys.launcher` (⌥Space), not the mockup's ⌘K. Welcome title is 28 px (type2.xxl), not 32, so "Welcome to miyagi" fits one line in the 352 pane.
- The mockup's legend under the dialog ("Green means done...") is canvas annotation, not shipped.
- Row buttons are QuietButton md (36 high) rather than the mockup's 32; disabled Start learning is the white primary at 40% (the atom), not a gray fill.
- Stage only: `FeatureWindow.size` is a getter (944×640 for `onb=full`, else theme 720×560) because dev/Stage.tsx sizes app windows from it; Electron ignores it.
- Stage only: `web.ts` selects the variant by sending `library.get {id:"onb_<variant>"}`, which the scenario maps to a `step_onb_*` segment so every later trigger is scoped to it (`health.get@step_onb_*`, `library.list@...`, `action:install@...`, `permission.open@...`). No unscoped trigger in `onboarding.json` except `connect` (blank in `full`), so `?scenario=full` is unchanged for other lanes.

## Core requests
1. **bridge.ts / mock/engine.ts (integrator):** the inline mock's default `engine.hello` (W0 fix round 3) is emitted in `start()` inside `createWebBridge`, before `main.tsx` subscribes to `engine:event`, so it is lost in the stage: `canSend()` stays false in every scenario that doesn't script its own hello (`?scenario=full` included: no `health.get`, `library.list`, `panel.state` go out). `onboarding.json` scripts its own hello in `connect` as a workaround. Fix: replay the bridge's `log` on `ready()`, or start the mock after the first `onEvent` subscriber.
2. **core/theme.ts `windowSize.onboarding` + main/appWindows.ts:** the first run is the 944×640 two-pane dialog; today main/features/onboarding.ts resizes the window right after `ctx.openWindow`. A per-view size (e.g. `windowSize.onboardingFirstRun`) or an `openWindow(route, args, size?)` would remove that.
3. **contract (Michael):** an explicit "suggested first lesson" signal. Ready reads `LibraryItem.suggested` loosely (not in the contract) and falls back to the first ready, unstarted cached lesson. Add `suggested?: boolean` to `LibraryItem` (or a `health` field) so the card shows only on the engine's word.
4. **engine (E3/E2):** send `lesson.paused {reason:"permission"}` (and `lesson.resumed`) when Accessibility or Screen Recording calls start failing mid-lesson; main polls permissions only while a window watches, so mid-lesson drops reach the app through the engine. A field naming the grant (`kind`) on that pause would replace the app's guess. Also: a way to go on "without pointing" (today the card only closes locally; the engine's pause stays until it resumes).
5. **engine (E1/E2):** `health` items `companion` and `vscode` (probe: VS Code app present, `code --list-extensions` lists the companion, the engine reaches it on 8791-8799), with `fix: "install"` on a missing companion. Without a `companion` item the row stays hidden.
6. **bundle (claude/eng-bundle):** ship the companion as `Resources/vscode/miyagi*.vsix` so the main-process install path (VS Code CLI) is used instead of the engine fallback.

## Notes
- No email to Adrian was sent from this session (the lane is claimed by the draft PR); the coordination email is left to Michael.
