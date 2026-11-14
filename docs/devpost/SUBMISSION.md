# Miyagi: Devpost submission

Every number below comes from a file, commit or measured run in this repo, and the source is named next to it.
Anything we have not verified is marked **(unverified)**. Checklist before submitting: the
"Before you submit" section at the bottom.

---

## Name
**Miyagi**

## Tagline (42 chars)
**Turn any tutorial into an auto-graded lab.**

Alternates: "Ask Miyagi anything. It won't move on until you do." (52) · "The tutorial waits until your code works." (41)

---

## Inspiration

YouTube tutorials can't tell whether you actually got it. You follow along, the video keeps going, your loss curve is flat, and the
video has already moved on to the next step. The fix is usually one line ("your learning rate is 300x too high"), but no one is
watching your screen to tell you. We wanted the patient teacher from *The Karate Kid*, someone who makes you do each step
yourself and doesn't let you move on until it really works. Miyagi does that for any tutorial.

## What it does

Miyagi has **two ways to learn**:
- **Watch a video** (shipped, below): Miyagi finds a real tutorial, checks it in a preflight card, builds a lesson from the video,
  and gates the video step by step.
- **Just teach me** (**in progress**, not merged yet): no video. Claude researches the topic with web search and the official docs
  and writes the lesson itself. The editor opens full screen and Miyagi boxes exactly where to type. Details below.

**Watch a video:**

1. **Ask.** Press **⌥Space**. A launcher grows out of the MacBook notch. Type what you want to learn, e.g. *"learn physics informed
   machine learning with PINNs in PyTorch"*.
2. **Find.** Miyagi searches the live web for real tutorials (YouTube, blogs, notebooks, repos, papers): Claude with web search
   plus the Bright Data SERP API. Claude scores every candidate, and Bright Data pulls the comments of the top 3 videos so videos
   people say "don't work anymore" get flagged. Every row shows its style (coding / no-code / conceptual) and length. The first
   result shows up in about 3–4 s.
3. **Preflight.** Within 5 s of your pick, a card says what the video actually is: its style, length and chapters, whether it fits
   your goal, and which tools it needs ("VS Code ✓ Python 3 ✓ torch ✗"). It has two buttons, **Build** or **Pick another**.
   Nothing is built until you say so. (`server/preflight/`)
4. **Build a lesson.** Miyagi turns the chosen video into a step-by-step lesson. Each step has a video clip and checks a machine can
   grade: regexes over what is on your screen, plus loss/accuracy thresholds and trends read off your terminal. Gemini watches the
   YouTube video directly, and a Claude path that reads the transcript races it. Videos over 30 minutes are built progressively,
   part by part, so the first part is ready while the rest builds. (`server/lesson/progressive.py`)
5. **Set up.** It creates a project folder with starter files and opens VS Code. The starter files are guarded so that none of them
   already passes a step.
6. **Follow along.** The video plays one step and then pauses. Miyagi watches your **whole screen** (Apple Vision OCR on the
   device, plus macOS Accessibility) and spotlights where you should work. When the step's checks pass on your real screen, the
   step turns green and the video resumes on its own.
7. **Get unstuck.** If a check fails (say, the loss is stuck around 17), the step goes amber and a Claude Opus coach diagnoses the
   problem from your actual screen and code, with the card landing 2–4 s after the run ends. It gives one short card with a hint ladder: a guiding question, then the moment in
   the video, then the source, then the exact fix. **"Do it for me"** shows a diff preview, applies it only after you confirm, and
   can be undone.
8. **See it.** **⌥D** draws a diagram for the current step, built by Claude for any topic: React data flow, a git commit graph,
   a pandas groupby, a neural net.
9. **Remember everything.** Every learning event and metric streams into Tiger Data (TimescaleDB hypertables + continuous
   aggregates): time per step, fail rate per check, and a "stuck heatmap" over the video's timeline.

**Just teach me (in progress):**
- `build_text_lesson(goal, workdir)` (commit `f438b88`, branch `claude/michael-lesson-135f28`) is **Claude only, no Gemini**:
  - Sonnet plans 3–8 steps from your starter files.
  - Sonnet with web search and web fetch researches the later steps in parallel. Sources are only URLs the tools returned.
  - Haiku writes each step: the exact code to type, the target (file + anchor), screen checks and hints. Opus takes over only when
    a check on its output fails.
  - Step 1 goes out without waiting for the research.
- Full-screen editor and `editor_line_rect()` (an exact line rect from macOS Accessibility, for boxing where to type): commit
  `12c1b26`, branch `claude/workspace-pycheck`.
- Status: both have **offline tests only**: a Python calculator, a React todo list and a file-renaming CLI, all with faked
  models. They're **not merged into `integration/live`**, and the launcher and engine don't call them yet.

Nothing in it is PINN-specific. We evaluated the lesson builder on React, git, pandas, Rust and FastAPI tutorials (numbers below).

## How we built it

Two people and many parallel Claude Code sessions, each in its own git worktree and folder. The contracts in
`shared/contracts/` (WebSocket events, step-graph schema, check schema, metric line protocol, Tiger schema) are the boundary
between all of them.

```
Electron overlay (app/) ──WebSocket :8787, shared/contracts/events.ts──▶ engine (server/orchestrator, FastAPI)
                                                                           ├─ finder     Claude web search + Bright Data SERP/Unlocker/YouTube comments (Gemini skim: off by default)
                                                                           ├─ preflight  ≤ 5 s card before any build: style, length, goal fit, tools needed
                                                                           ├─ lesson     Gemini watches the YouTube video ∥ Claude reads the transcript → step graph (long videos: part by part)
                                                                           ├─ workspace  Claude scaffolds ~/miyagi/lessons/<slug>, opens VS Code
                                                                           ├─ screen     ScreenCaptureKit + Apple Vision OCR + Accessibility, on-device
                                                                           ├─ checks     pure evaluator: screen regex, metric threshold/trend (Mann-Kendall + Theil-Sen)
                                                                           ├─ coach      Claude Opus diagnosis, hint ladder, Do it for me; Bright Data docs grounding
                                                                           ├─ diagrams   Claude-built diagram for the current step
                                                                           └─ Tiger Data training_metrics + learning_events hypertables, 5 continuous aggregates
tut run (cli/) ── POST /ingest ──▶ engine        (optional "precision mode": parses ::metric:: lines from your training script)
```

**Model rule:** Claude reads screens and code. Gemini only watches YouTube videos, and only for the lesson builder: the finder's
Gemini skim and its Gemini scoring fallback are **off by default** (`FINDER_SKIM_TOP=0`, `FINDER_GEMINI_FALLBACK=0`, commit
`b4f3bd2`). One exception remains: `server/screen/describe.py` on `integration/live` still has a Gemini path (the Claude-only
version is in PR #9), but it isn't used in the hero flow.

**Claude tiers** (commit `d500d03`): in the lesson builder, Sonnet 5.5 segments the video and Haiku 5.5 does per-step detail, check
adaptation and goal judging. Opus 5.5 runs only when a quality check fails: bad output, wrong step count, a step without checks,
or a lint-feedback round. The coach's diagnosis stays on Opus.

Real numbers, with where each one comes from:

| What | Measured | Source |
|---|---|---|
| Preflight card after the pick | cold **3.4–5.0 s** (hard cap 5 s; a late tool list re-sends the card at 5.3–7.0 s) | `docs/PIPELINE.md` |
| Search, first result on screen | **2.8–3.7 s**; whole search done in 4.1–14.3 s (4 PINN queries); 2.4–7.2 s to the first row on 4 non-PINN topics | `timings` in `demo/cache/search/*.json`; `docs/STAGES.md` (PR #13) |
| Claude web search (Haiku 5.5 + `web_search` tool) | 5–8 s for 17–26 results (Sonnet took 13.8 s on the same query) | `server/finder/README.md` |
| Lesson build, hero (24-min Toscano PINN video, Gemini watched it) | **31.1 s** | `build.seconds` in `demo/cache/lessons/aebc6b8fba02dac5.json` |
| Lesson build, 5 non-PINN tutorials (React, git, pandas, Rust, FastAPI) | Gemini path **41–50 s**; Claude transcript path 170–179 s on the first run → **29–83 s** after four rounds of fixes | `evals/lesson/report.md` (PR #10) |
| Lesson quality on those 5 | All schema-valid and lint-clean; 43/43 step titles match the transcript at that time; manual score **8–9/10** on the latest run; no PINN vocabulary leaked | `evals/lesson/report.md` |
| Coach card after a failed training run | **2–4 s** after the run ends; Opus itself takes 3.1–4.0 s, starting once the check fails (3 rehearsal takes); 3.3 s in an earlier warm-cache run | `docs/REHEARSAL.md` (rehearsal PR, `claude/demo-rehearsal-06521d`); commit `eb08267` |
| Hero rehearsal, end to end | 3/3 takes passed: amber 16.5–18.8 s after ↵, green 11.6–15.9 s after the fix, video resumes 0.4 s after green | `docs/REHEARSAL.md` |
| Coach streaming | first text 1.5 s after `warm()`; spotlight targets at 2.9 s of a 4.65 s reply; 4,505 cached prompt tokens read | `server/coach/README.md` |
| Screen reader (M5 Pro, 3456×2234) | capture ~17 ms; Apple Vision OCR 100–220 ms per frame warm; static screens aren't re-OCR'd | `server/screen/README.md` |
| Step gate | check passes → next step started within 0.4 s | `docs/STAGES.md` |
| Diagrams | 2.1–4.4 s per live Claude call | `server/diagrams/examples/RESULTS.md` |
| Plateau detector | flat-but-noisy curves falsely graded "improving": 61–136 of 300 seeds before → **≤ 3 of 300** after adding a Mann-Kendall + Theil-Sen gate | `server/checks/README.md` |
| Hero failure is real | `lr = 0.3`: loss diverges and sits flat around 17, check fails **6/6** seeds; `lr = 1e-3` passes 3/3, under 1e-2 by step 836–1078 (~15 s on CPU) | `demo/pinn-lab/README.md` |

Stack: Python 3.12 (FastAPI, pyobjc for Quartz/ScreenCaptureKit/Vision/Accessibility, psycopg, httpx, rapidfuzz, watchdog),
Electron + React + TypeScript + Tailwind + Motion for the overlay, PyTorch for the demo lesson.

## Challenges we ran into

- **Free-tier Gemini quotas.** The shared key had per-model daily caps (`gemini-3.8-flash`: 20 requests/day). By about 2 PM all
  four video models returned `429 RESOURCE_EXHAUSTED` and Google Search grounding returned 429 on every model. We added hedged
  model fallbacks, turned off the SDK's silent retries (they swallowed our timeouts), raced a Claude transcript path against Gemini,
  and cached every lesson draft so a cached video never spends quota. (`E7` quota note; `docs/STAGES.md` F2/F6.)
- **Cost: an unsupervised test sweep drained our Gemini credit.** A test sweep left running on its own used up the prepaid Gemini
  credit (about **$20**, a team-reported figure; it isn't in the repo). After that every call returned
  `402 "prepayment credits are depleted"`, and our code retried it as a transient error until the 75 s cap (commit `15f0efe`).
  What we added:
  - A **402 fast-fail**: billing errors mark Gemini down for 5 min, with no retries or fallbacks, so the race takes Claude's draft at
    once. The learner sees a plain sentence: "Gemini credits are used up…" (`15f0efe`).
  - **Gemini skims off** in the finder by default (`b4f3bd2`, `c0a3baa`).
  - **Model tiering**: Haiku/Sonnet first, Opus only when a check on the output fails (`d500d03`).
  - **`build.cost`** on every lesson: model calls and input/output tokens per model, Claude usage plus Gemini `usage_metadata`
    including thinking (`d500d03`). These are token counts, not dollars.
  - Speculative **prebuild is opt-in** (`ORCH_PREBUILD=1`), and the tests blank paid keys (`d500d03`, `bb8feb2`).
  - A **daily Gemini cap**: `LESSON_GEMINI_DAILY_CAP`, 25 video calls/day by default, persisted in
    `~/miyagi/state/gemini_usage.json`; when it's used up the Claude transcript path takes over. Long videos also build later
    parts only on demand. Both are in commit `6eb9aab`, which is **not merged into `integration/live` yet**.
- **YouTube rate limits.** From the venue network, YouTube returned `429 Too Many Requests` on caption (`timedtext`) requests, so
  with Gemini also out of quota no new lesson could be built. Every failure now ends in under 6 s with a plain-English
  error instead of a hang. (`docs/STAGES.md` re-run.)
- **Venue Wi-Fi blocked Tiger Data.** Our Tiger Cloud service listens on a high port (37145), and the venue Wi-Fi drops outbound
  TCP to it (`nc` fails on it while :443 works). We wrote an offline spool: writes go to `~/.miyagi/tiger-spool/*.jsonl`, it retries
  every 30 s, uploads everything after reconnecting, and nothing is lost. `python -m server.checks.tiger --ping` checks the
  connection from any network. (`server/checks/README.md`.)
- **macOS permissions.** The screen reader needs Screen Recording, and the Accessibility tree needs Accessibility, for the app
  that *runs the engine*, not for Miyagi itself. `scripts/miyagi-engine.sh` detects a denied grant and prints exactly where to
  turn it on. We also learned that ScreenCaptureKit leaves our own overlay out of the frames we capture, and that Vision splits
  one terminal row into 3 blocks: per-line regrouping took the parsed loss points from 0 to 42 on our fixtures.
- **Bright Data setup.** At first the account was inactive and the SERP/Unlocker zones didn't exist. Once they were live, the
  SERP API returned `google.com/goto` redirects, and YouTube watch pages hung in the Unlocker. We now resolve redirects and never
  send YouTube through the Unlocker.
- **One demo hiding a general bug.** A stage-by-stage runner (`scripts/stage.py`) on 4 non-PINN topics found that every lesson
  was being adapted to the PINN demo folder: React steps came back as "sample collocation points". The fix was a fresh folder per
  lesson (`server/workspace`). (`docs/STAGES.md` F1.)

## Accomplishments that we're proud of

- The hero loop is real end to end: an actual training run, real OCR of the terminal, a statistically tested plateau check, a
  live Opus diagnosis that lands 2–4 s after the run ends and finds `lr = 0.3` by itself, then green, and the video resumes.
- No fake data on the live path. A module that fails sends an `error` event with the reason, a search row Gemini didn't watch says
  "not watched: Gemini quota", and Claude can't cite a paper that isn't on a whitelist. Canned data exists only behind `DEMO=1`.
- It generalizes: 5 tutorials in very different stacks became playable lessons scored 8–9/10, with checks that fit each stack
  (`error\[E\d+\]` for Rust, uvicorn access-log lines for FastAPI, `RangeIndex: N entries` for pandas).
- "Do it for me" is safe: a preview diff, then confirm, then apply, then undo. It refuses while the file has unsaved edits and
  writes only patches that compile. Terminal fixes are copied to the clipboard and never run.

## What we learned

- Grading a learner from their **screen** generalizes far better than wiring into one editor. It works in VS Code, Terminal, a
  browser or a notebook, with no extension.
- Fast models do the cheap parts and Opus does the one hard part. Rules handle triage, Haiku points at the screen, Sonnet draws
  diagrams and scaffolds, and Opus writes only the diagnosis. Prompt caching plus a warm-up call is what lets the card land 2–4 s after the run ends.
- A noisy loss curve fools naive slope checks about a third of the time. Rank-based trend tests fixed it.
- Run every stage against topics you didn't design for. Our worst bug only showed up outside the demo.

## What's next

- Land **Just teach me** (no-video lessons) in the launcher and the engine, and merge the daily Gemini cap.
- Voice: ElevenLabs narration of cards (the app side is built; the engine side is in progress).
- Video-ID–level community warnings at specific timestamps ("this breaks at 12:40 with pandas 2.x").
- A creator dashboard on the Tiger aggregates: where learners get stuck in *your* video, and which steps take the longest.
- Event-driven capture (typing pauses, clicks, app switches) instead of a 1 fps loop, and exact line rects from the
  Accessibility tree for every editor.
- Windows support (the overlay already isolates platform differences in `app/src/main/platform.ts`).

## Built with

`python` · `fastapi` · `websockets` · `pyobjc` · `apple-vision` · `screencapturekit` · `macos-accessibility` · `electron` · `react`
· `typescript` · `tailwindcss` · `framer-motion` · `pytorch` · `claude` (Opus 5.5, Sonnet 5.5, Haiku 5.5) · `anthropic-api` ·
`gemini` (google-genai) · `bright-data` (SERP API, Web Unlocker, Web Scraper API) · `tiger-data` · `timescaledb` · `postgresql` ·
`youtube-iframe-api` · `vs-code` · `elevenlabs` (in progress) · `godaddy` (domain)

---

## Sponsor tracks: what each product does in Miyagi (with file paths)

### Gemini (MLH: Best use of Gemini API)
Gemini is the part of Miyagi that **watches YouTube**. `server/lesson/gemini.py` (`watch_video`) sends the public YouTube URL
straight to Gemini as `file_data`, with structured JSON output. It gets back the steps with MM:SS bounds, the code written in each
step, draft checks, on-screen targets, explanation timestamps, a hint ladder, common mistakes and library versions. An optional
`step_detail` pass re-sends each step clipped with `start_offset`/`end_offset` at 2 fps so code on screen is readable.
Videos over 30 minutes are built progressively, window by window (`server/lesson/progressive.py`). `server/finder/gemini.py` can also do a
low-fps skim (0.05 fps) of the top 3 search results, but it has been **off by default** since our cost freeze (`FINDER_SKIM_TOP=0`):
Gemini is spent only on the lesson the learner picked. The hero lesson was built by `gemini-4-hydrogen` watching the 24-minute video in 31.1 s, recorded in
`build.model` of `demo/cache/lessons/aebc6b8fba02dac5.json`. That cached lesson's adapt pass was also done by Gemini
(`gemini-3.6-flash`), before we moved adapt to Claude. Model chains, hedged fallbacks and quota handling: `server/lesson/README.md`,
`server/finder/README.md`.

### Bright Data (Data for Good)
Bright Data is Miyagi's **live-web layer**, and the "good" it does is keeping learners away from tutorials that no longer work.
- **SERP API** (Google) runs the web searches for written tutorials and notebooks, keeps Google's video results, and resolves
  `google.com/goto` links. `server/finder/brightdata.py`, `server/finder/sources.py`.
- **Web Scraper API, YouTube comments dataset:** the comments of the top 3 videos are pulled within a 10 s cap.
  Comments like "outdated" or "doesn't work" become row `warnings`. `server/finder/brightdata.py`
  (`BRIGHTDATA_YT_COMMENTS_DATASET`).
- **Web Unlocker** fetches the pages Claude reads and re-checks bot-blocked URLs (`server/finder/verify.py`). For the lesson
  builder it fetches YouTube watch pages and captions when the direct route is rate-limited (`server/lesson/transcript.py`).
- **Coach grounding:** when a library error shows up on screen, `server/coach/web.py` (`docs_for`, `community_signals`) searches
  the official docs and changelog plus Stack Overflow, GitHub and Reddit through SERP + Unlocker. The card cites the URL it used.

Status: SERP results were seen live in all 4 stage-runner searches (`docs/STAGES.md` re-run, finding A5). Commit `99a2c4c` made
SERP, Unlocker and comments live. The 20 offline tests replay recorded responses. **(unverified)** A live run showing "N comments
read via Bright Data" on the stage query hasn't been logged yet. The committed cache for the stage query was created before the
zones existed, so it shows Bright Data failing and the DuckDuckGo fallback.

### Tiger Data
Tiger Data is **the time-series memory of every learning session**. Schema: `shared/contracts/tiger-schema.sql`.
- Hypertables `training_metrics` (any numeric signal: loss, tests passing, build time…) and `learning_events` (every state
  transition: `step_started`, `check_pass`, `check_fail`, `offtrack`, `fix_applied`, `question`, `step_passed`, with the video
  timestamp).
- Continuous aggregates `metrics_1s` (live curves), `time_per_step`, `check_fail_rate`, `stuck_heatmap` (fails + offtracks per
  15 s of video) and `learner_progress`, set to real-time with refresh policies in `cli/sql/tiger-extras.sql`.
- Writers: `server/checks/tiger.py` (`record_event`, `record_metric`: non-blocking batched `COPY` every 0.5 s, offline spool),
  `server/screen/` (loss read off the screen → `training_metrics`, `run_id = screen-<lesson>`), `cli/tut` (`tut run` → `runs` +
  `training_metrics`).
- Reads: `tut db compare` / `server/checks/curves.py` + `server/checks/sql/compare_curves.sql` line up your curve against the
  tutorial's reference curve on `metrics_1s` by training step. `tut stats --watch` prints ingest rows/s and query ms.

Status: the venue Wi-Fi blocks Tiger's port, so live writes from the venue are **(unverified)**. They spool locally and upload on
reconnect. Before judging, run `python -m server.checks.tiger --ping` on a phone hotspot and quote its numbers.

### ElevenLabs
**In progress. Don't claim it as shipped.** What exists: the contract event `speak {audioUrl, text}`
(`shared/contracts/events.ts:60`) and the `voice_toggle` action; the overlay's voice feature, which plays `speak` audio while Voice
is on (⌥V) and shows an equalizer (`app/src/renderer/src/features/voice/` on branch `adrian/shell`, PR #6, marked "untested with
real ElevenLabs audio" in `app/README.md`); and key plumbing (`ELEVENLABS_API_KEY` in `.env.example`, `server/config.py:21`, the
app's Settings sheet). The engine only flips a flag on `voice_toggle` (`server/orchestrator/session.py:1055`). **No ElevenLabs API call
is in the repo yet.** If it lands before the deadline, link the file here. Otherwise say "planned" in the pitch.

### GoDaddy (domain)
The product's domain is **miyagi.study**. **(unverified)** Nothing in the repo shows the registration, and no landing page is
deployed from this repo. Confirm the domain is registered (MLH code) and what it points to (e.g. a redirect to the GitHub repo or
the demo video) before listing this track.

---

## Before you submit (checklist)

- [ ] Repo is public (Devpost needs the link): https://github.com/michae6345-crypto/sandhacks-tutor
- [ ] App source is merged or linked: the overlay lives on `adrian/shell` (PR #6); `integration/live` has only the engine.
- [ ] `python -m server.checks.tiger --ping` on the demo network: paste the ms numbers into the Tiger paragraph, or keep "(unverified)".
- [ ] One live finder run with Bright Data comments: `python -m server.finder "learn physics informed machine learning with PINNs in PyTorch" --refresh -v`. Quote its `comments` line.
- [ ] ElevenLabs: link the engine file that calls it, or keep it "in progress".
- [ ] GoDaddy: confirm miyagi.study is registered and where it points.
- [ ] Rehearsal PR (`claude/demo-rehearsal-06521d`: `scripts/miyagi-offline.sh`, `scripts/rehearse.py`, `demo/cache/coach/s8.json`, `docs/REHEARSAL.md`) merged, since DEMO.md and the numbers table point to it.
- [ ] Backup demo video recorded (see `docs/devpost/DEMO.md`).
- [ ] No `.env`, API keys or connection strings in screenshots or the video.
