# onboarding (A3)

**Status:** one-window first run (lane oneflow, Nov 21: the flow layer in the home window, see below); before that, intro + guided setup pass done (lane intro-setup): typecheck green, brand lint clean, stage flows walked end to end headless (intro, skip, reduced motion, steps 1-4 with auto-advance, Back, Review setup, Walk me through it, You're ready, Start). Electron not run (cost freeze) · **Priority:** P0 (first run) · **Port:** 5402 (this lane; 5188 before) · **Branch:** `michael/app-intro-setup` (from `michael/v2-integration`; earlier `michael/app-onboarding`, draft #171) · **PR:** draft into `adrian/shell`

## One window from start to finish (lane oneflow, Nov 21, branch `michael/app-one-flow`)
Michael: it must feel like ONE app; a login window floating over home ("two separate pages") is out. The first run now
happens inside the home window (route `library`, the app shell): a full-window **flow layer**
(`features/shell/flow/`) covers it, sidebar included, and hands the window to home at the end.

| Phase | What shows |
|---|---|
| intro | the branded intro (Intro.tsx), the first time only; any key or click skips |
| login | "Sign in to miyagi" (features/auth Login.tsx): one big white Continue with Google, a quiet "Apple · GitHub · coming soon", "Continue without an account" under it. Only while main says the login is needed. |
| setup | guided setup (Guided.tsx, `chrome="flow"`: no header of its own): Screen Recording, Accessibility, VS Code companion, Getting miyagi ready (engine + cloud access, with a soft progress line; Retry and Copy details on a real failure: `engine-local:restart` / `engine-local:details`) |
| ready | You're ready (Ready.tsx, `onStart`), or Review setup when something the learner can fix is left |
| leaving | the hand-off: the layer fades, the sidebar slides in from the left over it, the bonsai lands in the sidebar's logo, Home rises in |

- **Strip** (Strip.tsx): `[bonsai] Sign in · Screen · Accessibility · VS Code · Ready` at the top. Current step white on a
  raised pill that slides between steps; done steps get the green tick (green = done only), the rest are faint.
  "Ready" covers Getting miyagi ready and You're ready. "Set up later" (top right, setup only) hands over to home
  without finishing setup (`onboarding:later`: home on launch from then on; home's Finish setup opens the setup window).
- **Main** (`main/features/onboarding.ts`, `launch.ts`): a first launch opens ONLY the home window; no login window,
  no setup window, nothing behind them. `onboarding:get` answers `{done, introSeen, flow, login, step}`; the guided step
  on screen is saved (`onboarding:step`) so a relaunch for Screen Recording returns to it (shown Done for a moment
  when it is green by now, then the walk moves on). The Dock click, the tray's Open miyagi and a second launch bring
  the same window forward as it is (no new args). `auth:continue` in the flow opens nothing (`onLoginDone` returns
  nothing while no login window is open).
- **Fallbacks kept**: the standalone setup window (`openOnboarding()`: Settings' Open setup, home's Finish setup, the
  sidebar's Setup row) and the standalone login window (`openLogin()`: the Account page's Sign in). The login window
  now shows the same lighter login.

### One window: motion spec
All moves use the house spring `{stiffness 420, damping 34, mass 0.9}`; fades are tweens on `ease.out`
`cubic-bezier(0.23, 1, 0.32, 1)`. Transform and opacity only; the window never resizes. Constants:
`features/shell/flow/motion.ts`.

**Shared elements** (motion `layoutId`, one `LayoutGroup id="shell"` around the shell):
| layoutId | Where it lives, in order |
|---|---|
| `onb-mark` (MARK_ID) | Intro, 148 px, center → Login header, 56 px → the strip's step indicator, 18 px (setup and ready) → the sidebar's top-left logo, 20 px (`FlowMark`, Sidebar.tsx). Only one is mounted at a time; motion glides the new one from the last one's box. |
| `flow-strip-current` | the strip's current-step pill, from step to step |
| `shell-nav-selection` | (the sidebar's own, unchanged) |

**Timeline**
| Transition | Motion |
|---|---|
| intro | as before: tree grows 0 to 1.05 s, wordmark 0.95 s, line 1.3 s, ends 2.5 s |
| intro → login | intro fades 200 ms; the tree glides and shrinks into the login header (spring); the login fades in 240 ms, 80 ms late; the strip fades in (opacity 240 ms, y -4 → 0 on the spring) |
| login → setup | login fades 120 ms with a 6 px lift; the tree glides up into the strip; the pill slides Sign in → Screen and Sign in gets its tick (scale .6 → 1, spring); the step slides in 24 px, 160 ms late, its parts rising 35 ms apart |
| step → step | Done for 1.1 s (a green hairline fills under the status, linear), then the step slides 24 px (spring) with a 180 ms fade; exit 16 px / 120 ms; the pill slides along |
| Getting miyagi ready | a soft progress line: one 28 % neutral segment crossing the status's bottom edge, 1.6 s `ease.inOut`, 0.2 s rest, looping, transform only |
| setup → ready | the step fades 120 ms; Ready's rows rise 35 ms apart |
| ready → home | the strip drops the tree; the layer fades 220 ms; the sidebar slides in from x = -its width (spring, 40 ms late) over the fading layer; the tree glides into the sidebar logo; home fades in 240 ms and rises 8 px (spring), 120 ms late, then its cards rise one after another (library/motion.tsx); the layer is gone after 900 ms |
| login: waiting | the button's glyph swaps to the spinner (scale .7 → 1, spring), the label slides 6 px up into "Waiting for Google…" (spring + 180 ms fade); one faint ink band (`tint.hoverOnLight`, no gradient) crosses the button, 1.8 s `ease.inOut`, 0.4 s rest; "Finish in your browser · Cancel" fades in under it |
| login: failed | the reason fades in under the button (240 ms), with Try again. No shake, no hue. |

**Reduced motion** (`MotionConfig reducedMotion="user"`, main.tsx): every transform and layout move is dropped and the
fades stay, so each hand-off is a crossfade: the tree appears in its new place as the views crossfade; the sidebar
fades in (opacity, no slide); the progress line and the shimmer breathe in place (opacity loops, never frozen); the
intro is one static frame (as before).

**Stage**: `npm run dev:web -- --port 6111` →
`http://localhost:6111/?scenario=onboarding&flow=1&size=1440x900&clean&step=intro|login|screen|access|vscode|engine|ready|done`
(`done`: You're ready, then Start by itself, so the hand-off plays; `&auth=fail` for the failure line). Frame sequences
(headless, 1440x900): `miyagi-v2/screens/round5/oneflow-*.jpg` (sheets: `oneflow-sheet-a-intro-to-login`,
`-b-login-to-setup`, `-c-google-wait-fail`, `-d-engine-to-ready`, `-e-ready-to-home`, `-f-reduced-motion-handoff`,
`-g-screen-to-accessibility`).
Not verified in Electron (no live run in this lane): the first launch opening only home, the Dock / tray / second
launch bringing it forward, the relaunch landing back on the step, the traffic lights over the strip.

## Goal (intro-setup lane, Nov 20)
First launch = a branded intro, then guided setup, one step per screen (Michael's choice; replaces the all-in-one
checklist as the primary flow). The checklist stays as **Review setup**. The window, the app and the menu say miyagi.

| Piece | How |
|---|---|
| Intro (`Intro.tsx`) | ~2.5 s in the setup window: the colored bonsai (full cut, brand file) scales up from its pot while a cover in the window's color slides up off it (pot, trunk, then pads), the wordmark (brand file) fades up at 0.95 s, "Learn by doing, in the apps you already use." at 1.3 s, then the tree travels into the setup header (shared `layoutId`). Any key (not a lone modifier) or click skips. Transform and opacity only. Reduced motion: one static frame for 1.6 s. Plays once per Mac (`introSeen` in onboarding.json), so a relaunch for Screen Recording lands back in the walk. |
| Guided setup (`Guided.tsx`, `steps.ts`, `Illustration.tsx`) | Header: tree + wordmark, "N of 4" and four bars (green done, white current, track next; done/earlier bars jump back). Body: icon tile, a 28 px title, one line of why, the live status (glyph + word + sentence) and a picture of what the learner will see that mirrors the live state (the System Settings list with miyagi's switch, VS Code's extension row, the engine + cloud access lines). Footer: Back, an optional quiet action (Skip for now when VS Code isn't on this Mac; Open System Settings again after Allow), the ONE primary (Allow, Open System Settings, Install in VS Code, Relaunch miyagi, Continue; busy and disabled while installing or setting up). Enter presses the primary. |
| Moving | A step that turns green while shown says Done, a green hairline fills under the status for 1.1 s, then the walk moves to the next step not done (wrapping to one left open). Steps already done are skipped when the walk starts (permissions known first, so a done step never flashes). Continue on a Not sure yet step counts it as passed for the walk. The engine step has nothing to click and advances by itself. Steps slide 24 px on the house spring with a fade; parts rise in with a 35 ms stagger. |
| You're ready (`Ready.tsx`) | Rows rise in, the first-lesson card only when the engine offers one, "Open miyagi anytime" + the launcher keycap (platform.keys), **Start** → `startLearning()` (library.start for the suggestion, else `openLibrary()` = home). Shown only when nothing fixable is left; otherwise the checklist. |
| Review setup (`Checklist.tsx`) | Every row on one sheet with its own button, rows rise in, "Walk me through it" goes back to guided setup. `openOnboarding()` with no args after setup is done lands here (Settings > General "Open setup"). |
| Views | window args `view`: `intro` (first launch), `setup`, `checklist`, legacy `welcome` (= intro, or setup once seen); none → Review setup when done, else setup (intro the first time). Main opens `{view: introSeen ? 'setup' : 'intro'}` and pins the window title to "miyagi" (`page-title-updated` prevented). |

Earlier pass (A3), still true below:  the four things miyagi needs (Screen Recording, Accessibility, the VS Code companion, the engine
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
`npm run dev:web -- --port 5402` → `http://localhost:5402/?scenario=onboarding&onb=<variant>&size=1440x900&clean`
- `intro`: the intro, held on its last frame (key or click moves on). `full`: the real first launch (intro, then step 1, nothing granted). `step1`..`step4`: guided setup opened on that step. `mixed`: Review setup. `ready`: You're ready. `recovery`: the island card.
- Stage fakes: Allow / Open System Settings switch the grant on 2.5 s later; Install in VS Code goes Installing then Connected (mock `action:install`); cloud access is "Setting up" until the engine step has been up 2.5 s, then the walk finishes on its own.
- Shots (headless Chromium over CDP, 1440x900): `/Users/tripi/sand hacks/miyagi-v2/screens/round3/intro-*.jpg` (intro-a2-grow, intro-b-wordmark, intro-reduced-motion, intro-step1-screen, -step1-watching, -step2-accessibility, -step3-vscode, -step3-installing, -step3-done, -step4-engine, -ready, -review-setup, -back-to-done).

Earlier (A3) test notes: `npm run dev:web -- --port 5188` → `http://localhost:5188/?scenario=onboarding&onb=full|mixed|ready|recovery&size=1440x900&clean`
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
0. **Intro-setup lane (Nov 20):**
   - **home (library/dashboard lane):** a "Review setup" entry on home that calls `openOnboarding()` (it opens the checklist once setup is done). Settings > General's button says "Open setup"; "Review setup" would match the window's title (settings lane).
   - **core/ui/motion.ts:** `rise` / `stagger` live in `features/onboarding/parts.tsx` until the polish lane's shared motion helpers land; swap then.
   - **styles.css:** a global `:focus-visible` ring (UI-POLISH-SPEC 3) so the step bars, Back and the primary show keyboard focus; nothing is styled here locally.
   - **core/ui/Mark.tsx:** `MiyagiWordmark` sets `height` as an attribute, which Tailwind's preflight (`img { height: auto }`) overrides, so the wordmark renders at its natural 549 px. Callers here pass `className="h-[..px] w-auto"`; setting `style.height` in the atom would fix it everywhere.
   - **appWindows / theme:** a per-view window size (`windowSize.onboardingFirstRun` 944x640) instead of main resizing after `openWindow` (as before).
1. **bridge.ts / mock/engine.ts (integrator):** the inline mock's default `engine.hello` (W0 fix round 3) is emitted in `start()` inside `createWebBridge`, before `main.tsx` subscribes to `engine:event`, so it is lost in the stage: `canSend()` stays false in every scenario that doesn't script its own hello (`?scenario=full` included: no `health.get`, `library.list`, `panel.state` go out). `onboarding.json` scripts its own hello in `connect` as a workaround. Fix: replay the bridge's `log` on `ready()`, or start the mock after the first `onEvent` subscriber.
2. **core/theme.ts `windowSize.onboarding` + main/appWindows.ts:** the first run is the 944×640 two-pane dialog; today main/features/onboarding.ts resizes the window right after `ctx.openWindow`. A per-view size (e.g. `windowSize.onboardingFirstRun`) or an `openWindow(route, args, size?)` would remove that.
3. **contract (Michael):** an explicit "suggested first lesson" signal. Ready reads `LibraryItem.suggested` loosely (not in the contract) and falls back to the first ready, unstarted cached lesson. Add `suggested?: boolean` to `LibraryItem` (or a `health` field) so the card shows only on the engine's word.
4. **engine (E3/E2):** send `lesson.paused {reason:"permission"}` (and `lesson.resumed`) when Accessibility or Screen Recording calls start failing mid-lesson; main polls permissions only while a window watches, so mid-lesson drops reach the app through the engine. A field naming the grant (`kind`) on that pause would replace the app's guess. Also: a way to go on "without pointing" (today the card only closes locally; the engine's pause stays until it resumes).
5. **engine (E1/E2):** `health` items `companion` and `vscode` (probe: VS Code app present, `code --list-extensions` lists the companion, the engine reaches it on 8791-8799), with `fix: "install"` on a missing companion. Without a `companion` item the row stays hidden.
6. **bundle (claude/eng-bundle):** ship the companion as `Resources/vscode/miyagi*.vsix` so the main-process install path (VS Code CLI) is used instead of the engine fallback.

## Notes
- No email to Adrian was sent from this session (the lane is claimed by the draft PR); the coordination email is left to Michael.
