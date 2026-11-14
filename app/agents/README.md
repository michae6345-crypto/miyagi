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
| 12 | **theme** | Adrian's colors and type, applied to every token | `core/theme.ts` + `styles.css` | P2 | new | 5185 |
| – | **core / shell** | Windows, click-through, shortcuts, engine link, registry, Mac behavior | integrator (this repo's core) | – | built, Mac-unverified | 5173 |

P0 = needed for the 6 PM checkpoint (the happy path end to end) and "never cut" (launcher, pill status, off-track card, video gating). P1 = by 9 PM. P2 = overnight.

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
