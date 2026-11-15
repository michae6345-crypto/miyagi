# Miyagi: Devpost submission (final)

Paste-ready Devpost fields. The claims are limited to what is merged in `integration/live` (`ff8fdd1`) and the app branch
`adrian/shell` (`10ea9a8`). Every number names the file or commit it comes from. **(unverified)** marks anything the repo can't
show; **(team-reported)** marks something the team told us that isn't in the repo. The checklist at the bottom lists what to
confirm before pressing Submit.

---

## Name
**Miyagi**

## Tagline (42 chars)
**Turn any tutorial into an auto-graded lab.**

## Elevator pitch (for the short-description field)
Ask Miyagi anything. It finds a real tutorial, or writes one from the web, then watches your screen and won't move on until your
own code actually works.

---

## Inspiration

YouTube tutorials can't tell whether you actually got it. You follow along, your loss curve is flat, and the video has already
moved on. The fix is usually one line ("your learning rate is 300x too high"), but nobody is watching your screen to say so. We
wanted the patient teacher from *The Karate Kid*, someone who makes you do each step yourself and doesn't let you move on until
it really works.

## What it does

### The overlay
- **Position 1, the island.** A small pill sits just under the MacBook notch for the whole lesson. Its ring shows progress and its
  dot shows state: gray while watching, amber when you're off track, green when a step passes.
- **Position 2, the launcher.** Press **⌥Space** and a launcher grows out of the island. Type what you want to learn, then choose
  how to learn it:
  - **Watch a video** (↵)
  - **Just teach me** (**⌘↵**)

  (`app/src/renderer/src/features/launcher/Launcher.tsx` on `adrian/shell`.)
- **Spotlight.** While you work, Miyagi dims the rest of the screen to 55% and draws one **white hairline box** around the exact
  place to work:
  - the line of code to type, using an exact line rect from macOS Accessibility (`server/workspace/editor.py`,
    `editor_line_rect`) with OCR as the fallback;
  - or **VS Code's integrated terminal** for steps that run something (`server/screen` `locate_region("terminal")`, commits
    `0f7b9f8` and `eff2cfd`).

  In "Just teach me" the spotlight also shows the code to type under its caption (`spotlight.snippet` in
  `shared/contracts/events.ts`). The app side is `app/src/renderer/src/features/spotlight/Spotlight.tsx`.
- **Bottom bar.** It has **Check**, **Skip step** and **End lesson**, next to Back, Explain, Diagram, Show me, Hint and Voice
  (`app/src/renderer/src/features/shortcut-bar/ShortcutBar.tsx` on `adrian/shell`). **Check** runs the step's deterministic
  checks on a fresh screen frame first, then a Claude step judge. If the step isn't done you get one short "Not yet" with the
  spot to fix (commit `71abc6f`).

### Two ways to learn

**1. Watch a video**
1. **Find.** The launcher search shows **YouTube videos only**. Claude (with the web-search tool) looks for videos, one Bright
   Data SERP query adds Google's video results, and Claude scores every candidate. Rows under 40/100 are never shown
   (`FINDER_KINDS=video`, `FINDER_MIN_SCORE=40`, commit `b27d68d`). Bright Data also reads the **YouTube comments** of the top
   videos, so a tutorial people say "doesn't work anymore" gets a warning.
2. **Preflight.** Within 5 s of your pick, a card says what the video really is: its style, length and chapters, whether it fits
   your goal, and which tools you're missing. It has two buttons, **Build** or **Pick another** (`server/preflight/`).
3. **Build: Gemini watches, Claude reads, in parallel** (`LESSON_ENGINE=auto`, the default; `server/lesson/builder.py`).
   - **Gemini watches the YouTube video itself** at 0.5 fps, with the title, description and chapters as text. It returns the
     steps with timestamps, the code typed on screen, draft checks and a hint ladder (`server/lesson/gemini.py`).
   - At the same time **Claude builds the same lesson from the video's timestamped transcript** (fetched through Bright Data's
     Web Unlocker). Gemini's draft is used if it arrives within 75 s; if Gemini fails or runs late, Claude's is used.
   - Claude then adapts the checks to your folder: your file names and the metric names your script prints.
   - Each step gets a video clip and checks that can be graded from your screen: regexes over the editor and terminal, plus
     loss/accuracy thresholds and trends read off the terminal.
   - Videos over 30 min are built part by part (`server/lesson/progressive.py`).
4. **Set up.** It makes a folder per lesson (`~/miyagi/lessons/<slug>`) with starter files that never pass a step on their own,
   and opens VS Code (`server/workspace/`).
5. **Follow along.** The video plays one step's clip and pauses. When your screen shows the step really works, the step turns
   green and the video moves on by itself.

**2. Just teach me** (no video, **Claude only**)

You type a goal like *"build a calculator"* and press ⌘↵ (`learn {mode: "lesson"}`).
- `build_text_lesson` (`server/lesson/textlesson.py`) plans 3–8 steps with Sonnet.
- It researches the topic with Claude's **web search and web fetch** tools, so the official docs are the source. Sources are only
  URLs those tools returned.
- Haiku writes each step: the exact code to type, where it goes, the screen checks and hints. Sonnet steps in only when a check on
  that output fails.
- The lesson opens with an **overview** ("What we're building"), a **"Before you start"** primer and the **plan**; every step
  says **what** you build and **why**, and gives the **complete code to type**, never truncated (`explain_step` in
  `textlesson.py`, fields in `shared/contracts/events.ts`). The drawer that shows them is app PR #68 (open).
- Step 1 is ready before the research finishes.
- VS Code opens full screen, and each step boxes exactly where to type (commits `f438b88`, `12c1b26`, `716dafe`).

### In both modes
- **Get unstuck.** When a check fails (for example, the loss sits around 17), the step turns amber. A **Claude Sonnet** coach reads
  your actual screen and code and gives one short card: a hint ladder from a question, to the moment in the video or the source,
  to the exact fix. **Do it for me** shows a diff preview, applies it only after you confirm, writes only code that compiles, and
  can be undone (`server/coach/`, `server/orchestrator/session.py`).
- **Lessons survive restarts.** Every lesson, video or not, is saved as it's built. After an engine restart Miyagi offers
  "<title> · step N of M · X min ago" and resumes at that step with no rebuild. A save made before the restart is never
  overwritten before you answer (`server/sessions/`, commits `b80996d` and `1bebab8`).
- **Diagrams.** **⌥D** draws a Claude-built diagram of the current step for any topic: React data flow, a git commit graph, a
  pandas groupby, a neural net (`server/diagrams/`).
- **Everything is recorded.** Every learning event and metric goes to **Tiger Data**, and the engine serves a live stats page at
  `localhost:8787/stats`.

## How we built it

Two people and many parallel Claude Code sessions, each in its own git worktree and folder. The boundary between them is the
contracts in `shared/contracts/`: WebSocket events, the step-graph and check schemas, the metric line protocol and the Tiger
schema.

```
Electron overlay (app/: island, launcher, spotlight, bottom bar, player)
        │  WebSocket :8787 · shared/contracts/events.ts
        ▼
engine: server/orchestrator (FastAPI hub, lesson state machine, don't-nag gate, hint ladder)
  ├─ finder     Claude web search + scoring · Bright Data SERP (Google video results) + YouTube comments
  ├─ preflight  ≤ 5 s card before any build
  ├─ lesson     Watch a video: Gemini watches the video ∥ Claude drafts from the transcript; Claude adapts the checks
  │             Just teach me: Claude plans, researches (web search/fetch) and writes the steps
  ├─ workspace  per-lesson folder, starter files, VS Code (full screen in Just teach me), Accessibility line rects
  ├─ screen     ScreenCaptureKit → screencapture → CoreGraphics; Apple Vision OCR; Accessibility; terminal/editor regions
  ├─ checks     pure evaluator: screen regex, metric threshold, metric trend (Mann-Kendall + Theil-Sen)
  ├─ coach      Claude Sonnet diagnosis, step judge, hint ladder, Do it for me
  ├─ diagrams   Claude-built diagram for the current step
  ├─ sessions   restart-safe lesson saves + resume
  └─ Tiger Data learning_events + training_metrics hypertables, 5 continuous aggregates, GET /stats
```

**Model rule:** Claude searches, scores and reads screens, code and transcripts. Gemini only ever watches YouTube videos.
Inside Claude we use tiers: Sonnet builds lessons and writes the coach's diagnosis; Haiku does the routine work (search
scoring, preflight, triage, explaining, the Check judge, locating, the set-of-marks box targeter); Sonnet also takes over when a
quality check on cheaper output fails (commits `d500d03`, `c7f962b`). Opus is never used by default; it needs `LESSON_ALLOW_OPUS=1`.

**Screen reading.**
- Capture order: ScreenCaptureKit first, Apple's `/usr/sbin/screencapture` when ScreenCaptureKit stalls (as it does on
  macOS 26), then CoreGraphics (commit `e23a751`).
- OCR runs on the device with Apple Vision. On an M5 Pro, capture takes about 17 ms and OCR 100–220 ms per changed frame
  (`server/screen/README.md`).
- macOS Accessibility gives exact editor line rects.
- Our own overlay is left out of the captured frames.
- The VS Code companion extension (`vscode-ext/`) is an optional precision boost (exact file, unsaved edits, the terminal's last
  command and exit code). Without it every call returns nothing and the engine reads the screen (`server/workspace/vscode_ext.py`).

Measured numbers:

| What | Measured | Source |
|---|---|---|
| Search with Claude + Bright Data live (4 queries, all result kinds) | first row **3.6–5.8 s**, done 12.7–18.0 s; up to 36 YouTube comments read per video | `timings` / `comments` in `demo/cache/search/*.json` (re-recorded 15:16–15:18) |
| Hero lesson build (24-min Toscano PINN video, Gemini watched it) | **31.1 s** | `build` in `demo/cache/lessons/aebc6b8fba02dac5.json` |
| Lesson builder on 5 non-PINN tutorials (React, git, pandas, Rust, FastAPI) | Gemini path 41–50 s; Claude transcript path **29–83 s** after fixes; all schema-valid; 43/43 step titles match the transcript; manual score **8–9/10** | `evals/lesson/report.md` |
| Coach card after a failed run | 2–4 s after the run ends; 3.1–4.0 s per diagnosis call (3 rehearsal takes, measured when the coach ran on Opus; it runs on Sonnet now) | `docs/REHEARSAL.md`; commit `eb08267` (3.3 s) |
| Screen reader | capture ~17 ms; OCR 100–220 ms per changed frame | `server/screen/README.md` |
| Plateau detector | flat noisy curves wrongly graded "improving": 61–136/300 seeds → **≤ 3/300** | `server/checks/README.md` |
| Hero failure is real | `lr = 0.3`: loss stuck around 17, fails **6/6** seeds; `lr = 1e-3` passes 3/3 in ~15 s on CPU | `demo/pinn-lab/README.md` |
| Diagrams | 2.1–4.4 s per live Claude call | `server/diagrams/examples/RESULTS.md` |

Stack: Python 3.12 (FastAPI, pyobjc for ScreenCaptureKit/Vision/Accessibility, psycopg, httpx, rapidfuzz, watchdog); Electron +
React + TypeScript + Tailwind + Motion; PyTorch for the hero lesson.

## Challenges we ran into

- **Free-tier quotas.** Our Gemini key had per-model daily caps (`gemini-3.8-flash`: 20/day), and by mid-afternoon every video
  model returned `429`. In response we:
  - raced a Claude transcript path against Gemini, so a lesson still gets built when Gemini is out of quota or slow;
  - added hedged fallbacks and turned off the SDK's silent retries;
  - cached every lesson draft;
  - added a daily Gemini cap (`LESSON_GEMINI_DAILY_CAP`, 25 video calls, commit `6eb9aab`).
- **Cost.** A test sweep left running unsupervised used up our prepaid Gemini credit (about $20, **team-reported**). After that,
  every call returned `402 "prepayment credits are depleted"` (commit `15f0efe`). We added:
  - a 402 fast-fail with a 5-minute breaker and a plain-English error;
  - Gemini skims off in the finder (`b4f3bd2`);
  - Haiku/Sonnet tiers, and Opus off unless explicitly allowed;
  - `build.cost` token accounting on every lesson (`d500d03`);
  - opt-in prebuild;
  - paid keys blanked in tests.
- **YouTube rate limits on the venue Wi-Fi.** YouTube answered caption requests from the venue network with `429`. The Bright
  Data Web Unlocker is the alternate route for watch pages and captions (`server/lesson/transcript.py`). Every build failure ends
  in seconds with a plain sentence instead of a hang.
- **The venue Wi-Fi blocked Tiger Data.** Our Tiger Cloud service listens on a high port (37145) that the venue network drops.
  Writes spool to `~/.miyagi/tiger-spool/` and upload on reconnect, and `python -m server.checks.tiger --ping` tests the
  connection from any network (`server/checks/tiger.py`).
- **Screen capture on macOS 26.** `replayd` kept dropping our ScreenCaptureKit connection (thousands of
  `XPC_ERROR_CONNECTION_INTERRUPTED` a second), and `CGDisplayCreateImage` blocked for 5 s and returned nothing. We added the
  `screencapture` fallback: a temp PNG with mode 0600, deleted right away, with backoff (`e23a751`). The app is also told when the
  screen reader is down (`27c1804`).
- **Permissions.** Screen Recording and Accessibility belong to the app that *runs the engine*, not to Miyagi.
  `scripts/miyagi-engine.sh` detects a denied grant and prints where to turn it on.
- **Pointing at the right place.** OCR heuristics kept landing the box on VS Code's breadcrumb or jittering. We switched to stable
  editor and terminal regions (`0f7b9f8`) and Accessibility line rects (`12c1b26`).
- **A demo that hid a general bug.** Running 4 non-PINN topics stage by stage showed every lesson being adapted to the PINN demo
  folder. The fix was one folder per lesson (`server/workspace`).

## Accomplishments that we're proud of
- The hero loop is real end to end: a real training run, real OCR of the terminal, a statistically tested plateau check and a
  live Claude diagnosis. It finds `lr = 0.3` by itself, then the step goes green and the video resumes.
- There are two ways to learn, and both are graded the same way, from your real screen.
- No fake data on the live path. A failing module reports why, and a search row that wasn't watched or read says so. Canned data
  exists only behind `DEMO=1`.
- It generalizes: 5 tutorials in very different stacks became lessons scored 8–9/10 (`evals/lesson/report.md`).
- "Do it for me" is safe: preview, confirm, apply, undo. It refuses while the file has unsaved changes, and terminal fixes are
  copied, never run.

## What we learned
- Grading from the **screen** generalizes better than plugging into one editor. It works in VS Code, the terminal or a notebook
  with no extension; our optional VS Code companion only adds precision.
- Watching the video gets step boundaries as good or better than reading the transcript (median 1 s from the chapter marks,
  against up to 15 s for the transcript path, `evals/lesson/report.md`), and running both in parallel keeps every build working.
- Noisy loss curves fool slope checks; rank-based trend tests don't.
- Spending needs guardrails from the very first test sweep.

## What's next
- A creator dashboard on the Tiger aggregates: where learners get stuck in *your* video.
- Community warnings pinned to timestamps ("breaks at 12:40 on pandas 2.x").
- Windows support (platform differences are already isolated in `app/src/main/platform.ts`).

## Built with
`python` · `fastapi` · `pyobjc` · `apple-vision` · `screencapturekit` · `macos-accessibility` · `electron` · `react` · `typescript`
· `tailwindcss` · `framer-motion` · `pytorch` · `claude` (Sonnet 5.5, Haiku 5.5) · `anthropic-api` · `gemini` ·
`bright-data` · `tiger-data` · `timescaledb` · `postgresql` · `youtube-iframe-api` · `vs-code` · `godaddy`

---

## Sponsor tracks

### Bright Data: live
Bright Data is Miyagi's live-web layer, and its "good" is steering learners away from tutorials that no longer work.
- **SERP API:** Google's video results for every search. It resolves `google.com/goto` links and falls back to DuckDuckGo on a
  target failure (`server/finder/brightdata.py`, `server/finder/sources.py`).
- **YouTube data (Web Scraper API comments dataset):** comments of the top videos, read in parallel under a 10 s cap.
  "Outdated" and "doesn't work" comments become row `warnings`.
  - Live evidence: "36 comments read via Bright Data" in `demo/cache/search/learn-physics-informed-machine-learning-with-pin-*.json`
    (re-recorded with Bright Data live at 15:17).
- **Web Unlocker:** the first route for YouTube captions and the backup for watch pages when YouTube blocks the plain fetch
  (`server/lesson/transcript.py`), and, with the SERP API, the docs/community pages the coach cites (`server/coach/web.py`).

### Tiger Data
Tiger Data is the time-series memory of every session.
- **Schema** (`shared/contracts/tiger-schema.sql` + `cli/sql/tiger-extras.sql`):
  - hypertables **`learning_events`** (step_started, check_pass, check_fail, offtrack, fix_applied, question, step_passed, each
    with the video timestamp) and **`training_metrics`**;
  - **continuous aggregates** `metrics_1s`, `time_per_step`, `check_fail_rate`, `stuck_heatmap` (per 15 s of video) and
    `learner_progress`, set to real-time with refresh policies.
- **Writers:** `server/checks/tiger.py` batches `COPY` every 0.5 s and keeps an offline spool. The orchestrator records every
  learning event (commit `79bd343`).
- **Stats page:** `GET localhost:8787/stats` (`server/checks/stats_web.py`, polling `/stats/data` every 2 s) shows:
  - the live curve from `metrics_1s` with the tutorial's reference curve;
  - time per step and fail rate per check;
  - the stuck heatmap;
  - ingest rows/s and each panel's measured query latency.

  When Tiger is unreachable it says so instead of showing stale numbers. The app's overview links to it (commit `27879d2`).
- **Status:** the schema was applied to our Tiger Cloud service tonight (**team-reported**). Paste the
  `python -m server.checks.tiger --ping` output from the demo network before submitting.

### Gemini
Gemini is how Miyagi **watches** a tutorial (`LESSON_ENGINE=auto`, the default).
- The lesson builder sends the public YouTube URL to Gemini as `file_data` at 0.5 fps, with the video's title, description and
  chapters as text, so it also sees the repo and data links.
- It returns structured JSON: steps with MM:SS bounds, titles and instructions, the code typed on screen, draft checks, targets,
  and a hint ladder with common mistakes (`server/lesson/gemini.py`).
- Claude builds the same lesson from the transcript in parallel. Gemini's draft is used if it arrives within 75 s; Claude's is
  used if Gemini fails or runs late (`server/lesson/builder.py`). Claude then adapts the checks to the learner's folder.
- Videos over 30 min are watched part by part (`server/lesson/progressive.py`). Usage is capped per day
  (`LESSON_GEMINI_DAILY_CAP`) and logged in `build.cost`.
- Gemini only watches videos. Just teach me, search, scoring, the coach, the judge, screen reading and box picking are Claude.
The cached hero lesson was built by `gemini-4-hydrogen` watching the 24-minute video (31.1 s, `build.model` in
`demo/cache/lessons/aebc6b8fba02dac5.json`).

### GoDaddy
Our domain is **miyagi.study**. The packaged app sends `https://miyagi.study/` as the Referer for YouTube embeds
(`youtubeReferer()` in `app/src/main/index.ts`). **(unverified)** Nothing in the repo shows the registration or what the domain
serves. Confirm both.

### Pending Michael's decision: ElevenLabs, xAI, Vultr
- **ElevenLabs:** the code is merged. `server/coach/voice.py` calls ElevenLabs streaming TTS (`eleven_flash_v2_5`) for short
  lines (the step title, the card title, "Nice, step passed.") and serves them at `/tts/<hash>.mp3`. It's wired in
  `server/orchestrator/modules.py:544`, and the app plays `speak` audio when Voice is on. **(unverified live)** Enter the track only
  if Michael decides to and it has been heard working.
- **xAI:** nothing in the repo uses xAI. Don't list it unless something lands.
- **Vultr:** nothing in the repo deploys to Vultr. The engine runs locally on the Mac. Don't list it unless something lands.

---

## Before you submit
- [ ] Repo public: https://github.com/michae6345-crypto/miyagi (moved from `sandhacks-tutor`; private right now)
- [ ] The app on `integration/live` matches `adrian/shell` (the launcher's two ways to learn and the bottom bar are on `adrian/shell` `10ea9a8`).
- [ ] Tiger: `python -m server.checks.tiger --ping` on the demo network; paste the numbers in place of "(team-reported)".
- [ ] GoDaddy: confirm `miyagi.study` is registered and what it serves.
- [ ] Michael: ElevenLabs / xAI / Vultr: in or out.
- [x] Rehearsal PR merged (#43: `scripts/miyagi-offline.sh`, `scripts/rehearse.py`, `docs/REHEARSAL.md`).
- [ ] App PR #68 (drawer: overview, plan, why, full code) merged into `adrian/shell`, or drop that sentence.
- [ ] Backup screen recording of both demo paths.
- [ ] No `.env`, keys or connection strings in screenshots or the video.
