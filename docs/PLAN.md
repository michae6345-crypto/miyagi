# Build plan: the tutorial-to-graded-lab overlay (working name TBD)

**One-liner:** Turn any tutorial into an auto-graded lab that runs beside your code. Ask what you want to learn → it finds the best tutorial → breaks it into steps → the video pauses at each step until **your own code / terminal / training run passes that step's check** → it spotlights where to work, explains, and draws intuition diagrams.

**Hero demo:** train a PINN on the convection equation. Loss plateaus at β=30 → step goes red → it diagnoses the known failure mode (Krishnapriyan et al., NeurIPS 2021) → you add a β curriculum → loss drops → step goes green → video resumes by itself.

**Not Clicky:** Clicky answers "what's on my screen". We verify your work against a real lesson. Lead the demo with the red→green checkpoint, not the overlay.

**Name:** pick by 1:00 PM ("Shadow" is taken on Product Hunt). Shortlist: Greenlight · Checkpoint · Labwork · Followthru.

---

## Team: 3 humans, ~9 Claude Code sessions

Each person is a **lead** who runs 2–3 Claude Code sessions in parallel, each in its **own git worktree / branch**, each owning one folder. Leads review and merge; Claudes write code.

| Lead | Claude sessions (folder they own) |
|---|---|
| **A — Engine (you)** | **A1 Lesson Builder** (`server/lesson/`): YouTube URL → Gemini → step graph + machine-checkable checks. **A2 Runner & Checks** (`cli/` + `server/checks/`): `tut run <cmd>` wrapper, metric parser, check evaluator, Tiger ingest. **A3 Coach** (`server/coach/`): Claude Opus diagnosis, hint ladder, outdated-code fixer via DuckDuckGo search. |
| **B — Overlay (Apple UI): Adrian, see FRONTEND-HANDOFF.md** | **B1 Shell** (`app/`): Electron, top-center pill (Dynamic-Island style), Spotlight launcher, lesson drawer, shortcut bar, native vibrancy. **B2 Spotlight** (`app/spotlight/` + `vscode-ext/`): dim overlay with cut-out, VS Code extension that reports exact line rects. **B3 Video + Voice** (`app/player/`): YouTube IFrame player with gating (pause / seek / resume on step pass), ElevenLabs TTS toggle. |
| **C — Finder, Diagrams, Demo (third teammate)** | **C1 Finder** (`server/finder/`): search (YouTube + DuckDuckGo web + papers) + Gemini triage → ranked candidates. **C2 Diagrams** (`server/diagrams/` + `app/diagrams/`): 3 templates from real run data (network graph, per-layer gradient flow, solution heatmap) + Claude one-line intuition. **C3 Demo content** (`demo/`): the PINN repo, chosen tutorial, cached search results + step graph, demo-mode switch, backup video, Devpost. |

**Background agents** (fire-and-forget, any lead can launch): pick & verify the real public PINN YouTube tutorial · write seed/demo data · README + architecture diagram · Devpost draft · test scripts · landing page on the GoDaddy domain.

---

## Hour 0–1 (12:30–1:30 PM): contracts first, all three together

Put these in `shared/contracts/` and don't change them without telling the other leads:

1. **Step graph JSON**: `{lesson, sources[], steps[{id, title, video:{start,end}, instructions, checks[], targets[], hints[]}]}`
2. **Check spec**: `type: file_contains | command_exit_ok | metric_threshold | file_exists | visual`, e.g. `{type:"metric_threshold", name:"loss", op:"<", value:1e-3, by_step:2000}`
3. **Metric line protocol** (stdout from the user's run): `::metric:: {"step":1200,"name":"loss","value":0.25}`
4. **App ↔ server WebSocket events**: `step.started`, `check.updated`, `step.passed`, `offtrack {reason, card}`, `spotlight {file, lines}`, `video.seek {t}`, `diagram {kind, data, caption}`
5. **Tiger schema**: `training_metrics` + `learning_events` hypertables, `runs`, `lessons`, `steps`; continuous aggregate `metrics_1s`
6. Repo skeleton, `.env.example`, and all API keys working: Gemini, Anthropic, Tiger Data, ElevenLabs (+ Vultr box).

**Also in hour 1 (C3 + a background agent):** choose the actual YouTube tutorial and confirm the PINN code trains in about 60 s on a laptop. The whole demo depends on this.

---

## Timeline (now → Sun 12:00 noon)

| When | Goal |
|---|---|
| **1:30–6:00 PM** | Everyone builds against mocks. Engine and overlay run independently. |
| **6:00 PM · Checkpoint 1** | **Happy path end to end:** launcher → (cached) lesson → steps 1–4 gate on code checks → video pauses and resumes automatically. |
| 6:00–9:00 PM | Off-track loop: metric check fails on the flat loss → coach card → spotlight → fix → green → resume. (Dinner 7:30.) |
| **9:00 PM · Checkpoint 2** | **The hero moment works end to end.** Room closes; keep going offsite. |
| 9 PM–2 AM | Live Finder, diagrams, voice, Apple polish, deploy the backend to Vultr. |
| 2–7 AM | Sleep in shifts (2 people × 3h). Agents do low-risk work: tests, README, Devpost draft. |
| **9:00 AM · Feature freeze** | Rehearse the demo 5 times. Demo-mode switch with cached results. |
| **10:00 AM** | Backup demo video recorded. |
| **11:00 AM** | Placeholder Devpost submission (required). |
| **12:00 PM** | Final submission. Judging 12:30–2:30, whole team at the table. |

**Decision gates (no debating, just cut):**
- Miss Checkpoint 1 → drop live search (pasted YouTube link only) and lesson stitching.
- Miss Checkpoint 2 → drop the dim-screen spotlight (lesson card only) and cut to 1 diagram template.

---

## Must-have vs. stretch

**Must work live:** launcher → lesson from a YouTube link → video gated by code checks → flat-loss metric check fails → coach diagnosis card → fix → green → resume.

**Stretch, in order:**
1. Live tutorial search
2. Spotlight dimming
3. Gradient-flow diagram
4. Voice
5. "Explain more" / "Go deeper"
6. Outdated-API fixer
7. Multi-source stitching
8. Learner "stuck heatmap" for creators

---

## Money and accounts (do this in hour 1; you likely pay $0)
| Service | Cost | Action now |
|---|---|---|
| Claude API | Your $200 credits; about $2–6 per session-hour | Set a spend limit in the Console; share one key via `.env` (never commit it) |
| Gemini API | Free AI Studio key; YouTube input is free in preview (8h of video/day on the free tier) | Get the key now. Turn on billing only if you hit rate limits (cents) |
| Tiger Data | Free cloud service | Create the service; save the connection string |
| ElevenLabs | Creator credits for everyone | Redeem; pick 1 voice |
| Vultr | Check MLH's prize/credit page; otherwise about $6/mo VM, or run the backend locally | Only needed for the Vultr track |
| GoDaddy domain | Free via the MLH code | Register the name once it's picked |
| Apple developer, GitHub, Figma | Free / not needed | Nothing |

**Install on every laptop:** Node 22+, Python 3.11 + PyTorch, VS Code, Git + `gh`, Claude Code. Grant your terminal **Accessibility** permission on macOS.

## Workflow between the three of you
- **The contracts in `shared/contracts/` are the boundary.** Changes go through a PR + a ping in the group chat.
- **Frontend builds against a mock replay; engine emits the same events.** Integrate by flipping `ENGINE_URL` at 6 PM.
- **Each Claude session works on its own branch/worktree.** Leads merge to `main` at checkpoints; `main` must always start the app and the engine.
- **Syncs:** 2:30, 4:30, 6:00 and 9:00 PM, and 8:00 AM. 5 minutes each: done / contract changes / blockers, plus a screen recording of the UI.

## Sponsor map (say these words in the pitch)
- **Gemini:** watches the YouTube video → step graph with timestamps; triages candidate tutorials.
- **Web search:** the finder ranks tutorials across YouTube, blogs, notebooks, papers; the coach pulls current docs (DuckDuckGo) for outdated code.
- **Tiger Data:** every training metric streams into hypertables; continuous aggregates power the live curve comparison and the check that grades your step.
- **ElevenLabs:** optional voice explanations.
- **Vultr:** backend hosting. **GoDaddy:** domain. **Claude:** coach and diagnosis.

## 3-minute demo
1. **Hook (15s):** "YouTube tutorials don't know if you actually got it. Ours do."
2. **Launcher (25s):** ⌥Space → "train a PINN on the convection equation" → best tutorial found → lesson built.
3. **Gating (40s):** the video plays step 4 and pauses; the screen dims onto `pde_residual`; you type; checks tick; the step goes green and the video resumes.
4. **Hero (60s):** training at β=30, loss flat → step red → card: known PINN failure mode + paper → gradient-flow diagram shows why → add the β curriculum → loss drops → green → video resumes.
5. **Close (20s):** "Any tutorial becomes an auto-graded lab. Built on Gemini, Tiger Data, ElevenLabs."

## Kickoff prompt for each Claude session
> We're building [NAME] at a 24h hackathon. Read `PLAN.md` and everything in `shared/contracts/`. You own `<folder>` only; build against the contracts exactly and mock what other sessions own. Get a runnable slice in 90 minutes, then deepen. Secrets in `.env` only. Commit to your branch often with clear messages; don't touch other folders.
