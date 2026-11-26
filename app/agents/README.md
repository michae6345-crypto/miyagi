# Frontend build outline: one agent per feature

Everything Adrian's side has to ship, split so each piece is one Claude session on its own branch and worktree, editing only its own folder. Rules every agent follows: `app/CLAUDE.md`.

## The pieces

| # | Feature | What it is | Plugs in as | Pri | Status | Port |
|---|---|---|---|---|---|---|
| 1 | **player** | Video player window + **gating**: plays a step's clip, pauses at its end until the checks pass, resumes, reports `video.state` | window `player` + main feature | **P0** | new | 5182 |
| 2 | **launcher** | ⌥Space search, paste a YouTube link, results, Build lesson → shrinks into the pill, **ask mode** during a lesson | window `launcher` | **P0** | v1 built | 5176 |
| 3 | **pill** | The pill's own states (idle / building / step) + the **step-pass moment** | island modes 0–9 | **P0** | v1 built | 5174 |
| 4 | **cards** | Off-track (amber), back-on-track (green), explain / hint / answer cards; **live loss curve** from `metric` | island modes 50–70 | **P0** | v1 built | 5177 |
| 5 | **spotlight** | Screen-first dim + glowing cut-out at the engine's rect + caption | overlay layer z 10 | **P0** | v1 built | 5178 |
| 6 | **overview** | Hover the pill → step card (thumbnail, progress, live checks) | island mode 20 | P1 | v1 built | 5175 |
| 7 | **shortcut-bar** | Bottom bar: Ask anything · Back · Explain · Diagram · Show me · Hint · Voice | overlay layer z 60 | P1 | v1 built | 5179 |
| 8 | **settings** | Bring-your-own-keys sheet, keys encrypted with `safeStorage`, `config.keys` / `config.status` | window `settings` + main feature | P1 | new | 5183 |
| 9 | **diagrams** | Intuition diagrams out of the pill: network · gradient flow · **heatmap** | island mode 80 | P1 | v1 (no heatmap) | 5180 |
| 10 | **voice** | `speak` audio (ElevenLabs) on/off, equalizer; optional mic to ask | overlay layer (no UI) | P2 | v1 built | 5181 |
| 11 | **drawer** | Right-edge tab → lesson drawer: all steps with status, sources | overlay layer z 40 | P2 | new | 5184 |
| 12 | **theme** | Miyagi brand kit (`app/brand/`): tokens in `core/theme.ts`, logo `core/ui/Mark.tsx`, app icon, system font. Each feature applies `BRAND.md` in its own folder | `core/theme.ts` + `styles.css` | P0 | core done; features applying | 5185 |
| – | **core / shell** | Windows, click-through, shortcuts, engine link, registry, Mac behavior | integrator (this repo's core) | – | built, Mac-unverified | 5173 |

P0 = needed for the 6 PM checkpoint (the happy path end to end) and "never cut" (launcher, pill status, off-track card, video gating). P1 = by 9 PM. P2 = overnight.

## v2 lanes (miyagi-v2 BUILD-PLAN, wave 1)

Wave 0 (`michael/app-core-v2`, brief `core-v2.md`) lands first: contract sync, theme tokens, shared atoms (`core/ui/*`), app windows (`core/surfaces.ts`, `main/appWindows.ts`), shell services (`core/geometry.ts`, `core/dock.ts`, lesson hooks, prefs, `main/permissions.ts`, engine token, cloud token) and the security core. Every wave 1 lane branches from its merge. Each lane edits only the files its plan entry lists; a core change goes under **Core requests** in its brief.

| Plan | Lane (brief) | Branch | Mockups | Port |
|---|---|---|---|---|
| W0 | **core-v2** (`core-v2.md`) | `michael/app-core-v2` | tokens and atoms for all | 5173 |
| A1 | **lesson-panel** (`drawer.md`) | `michael/app-lesson-panel` | Les-Anatomy, Working, Checking, NotYet, Hint, Passed | 5186 |
| A2 | **pill-cards** (`pill.md`, `cards.md`) | `michael/app-pill-cards` | Les-Mini, pill lines, Err-KernelInContext footer, Err-VSCodeSetup | 5187 |
| A3 | **onboarding** (`onboarding.md`) | `michael/app-onboarding` | Onb-Setup-Full, Checklist-Mixed, Setup-Ready, Permission-Recovery | 5188 |
| A4 | **settings-v2** (`settings.md`) | `michael/app-settings` | Set-General, Permissions, Privacy, Account, Shortcuts, Plan-OwnKey | 5189 |
| A5 | **home** (`launcher.md`, `building.md`) | `michael/app-launcher` | Home-Launcher, LauncherInContext, Home-Building | 5190 |
| A6 | **library** (`library.md`) | `michael/app-library` | Home-Library, Home-LessonDetail | 5191 |
| A7 | **errors** (`errors.md`) | `michael/app-errors` | Err-EngineReconnect, OfflineAndLimits, LessonBuildFailed, VSCodeClosed, KernelInContext, CrashConsent | 5192 |
| A8 | **progress** (`progress.md`) | `michael/app-progress` | Prog-Step-Passed, Completion, Review-Reminder, Progress-Window | 5193 |
| A9 | **account** (`account.md`, flag `v2Cloud`) | `michael/app-account` | Plan-AccountMenu, Upgrade, SignIn, Pricing | 5194 |
| A10 | **dmg-art** | `michael/app-dmg-art` | Onb-Install-Dmg | 5195 |
| A11 | **studio** (wave 2 optional, stage only) | `michael/app-studio` | Biz-Import, Building, StepEditor | 5196 |

Stage: `npm run dev:web -- --port <port>` then `?scenario=<name>&size=1440x900&clean` (v2 mockups are 1440×900); app windows open with `&window=<route>` (onboarding, library, progress, account). `?scenario=core-v2` plays the v2 events (engine.hello, health, building phases, blocker, library, progress) and a fake reconnect (`_link`).

## Island priority table (v2)

Higher wins. Ranges: 0–9 pill-sized · 20 hover · 40–79 cards · 80+ modal. Reviewers check new modes against this table; a lane that needs a new number adds it here in its PR.

| Priority | Mode (feature) | Status |
|---|---|---|
| 0 | idle (pill) | built |
| 2 | compact (pill): the step pill, "N of M" in v2 | built (A2 restyles) |
| 3 | building (pill) | built |
| 4 | saved (pill) | built |
| 5 | notice (pill): notify() lines | built |
| 6 | net-offline, busy (errors) | A7 |
| 7 | reconnecting, blocker pill line (errors) | A7 |
| 9 | Mini lesson pill (pill-cards, while the panel is collapsed) | A2 |
| 20 | overview (hover) | built |
| 45 | build card (building) | A5 |
| 50 | card (cards) | built |
| 55 | step passed card (progress; Mini only, never on the last step or with the panel open) | A8 |
| 56 | cap-line (signincard: a 429 cap on a shared lesson build, `cloud.notice`) | built |
| 57 | signin-card (signincard: 401 `signin_required` on a shared lesson build, `cloud.notice`) | built |
| 58 | limit (errors, `v2Cloud`, flagged) | A7 |
| 60 | success (cards) | built |
| 62 | build failed (errors) | A7 |
| 64 | complete (complete) | built (A8 restyles) |
| 65 | before-start (before-start) | built |
| 66 | editor closed (errors) | A7 |
| 70 | offtrack (cards) | built |
| 72 | engine offline (errors) | A7 |
| 75 | permission recovery (onboarding) | A3 |
| 90 | crash consent (errors; at launch only, never mid-lesson) | A7 |

The lesson panel (A1) is an overlay layer docked right (`core/dock.ts`, z 40), not an island mode; app windows (Onboarding, Library, Progress, Account) are their own windows (decision 4). Panel-routed cards (A1 `isPanelRouted`) render inside the panel while it's open, so the island skips them (A2).

## Order of work
1. **Now:** player, launcher, pill, cards, spotlight in parallel (5 agents).
2. **After the 4:30 sync:** overview, shortcut-bar, settings, diagrams.
3. **Overnight:** voice, drawer, then **theme last** (it touches color values in every feature, so run it alone once the others are merged).

## Cross-feature hand-offs (who touches what)
- **Every surface is born from the notch island** (launcher, cards, diagrams, settings): the launcher and settings are focusable windows that start from the island's exact size (`launcher:open {from}`) and collapse back into it. Nothing pops up mid-screen.
- The gear that opens **settings** lives in the **overview** card: settings exports `openSettings()`; the overview agent adds the button.
- **cards**' video jump and **player** share `core/lesson.video` (the engine's intent). The player follows it; nobody else drives the player directly.
- **shortcut-bar** shows Diagram / Voice as lit using the diagrams and voice stores (read-only).
- **launcher** ask mode answers come back as a `card {kind:"answer"}` rendered by **cards**.

## Launch an agent
```bash
cd app
npm run feature -- new <feature>          # → ../tut-<feature> on adrian/<feature>, scaffolded, npm ci
```
Open a Claude Code session in `tut-<feature>` and paste:
> Read app/CLAUDE.md and app/agents/<feature>.md, then build it. Stage: `npm run dev:web -- --port <port>` → `http://localhost:<port>/?scenario=<feature>`

Until PR #6 is merged into `main`, the script branches from `origin/adrian/shell` (it checks for itself).
