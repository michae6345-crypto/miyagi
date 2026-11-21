# Miyagi: Devpost submission (final)

Paste-ready Devpost fields. The claims are limited to what is merged in `integration/live` (the engine) and `adrian/shell`
(the app) on Nov 15, 2026. Numbers name the file or commit they come from. **[CHECK]** marks anything the repo can't show:
Michael confirms or removes each one before pressing Submit. The checklist at the bottom lists them all.

---

## Name
**Miyagi**

## Tagline (42 chars)
**Turn any tutorial into an auto-graded lab.**

## Elevator pitch (for the short-description field)
Tell Miyagi what you want to learn. It finds a YouTube tutorial or writes the lesson, opens it in your own VS Code, checks
every step from your code and your screen, and won't move on until your code works.

---

## Inspiration

YouTube tutorials can't tell whether you got it. You follow along, your loss curve is flat, and the video has already moved
on. The fix is often one line (every weight starts at zero, or the learning rate is far too high), but nobody is watching
your screen to say so. We wanted the patient teacher from *The Karate Kid*: someone who makes you do each step yourself and
doesn't let you move on until it works.

## What it does

Miyagi is a macOS overlay that sits under the MacBook notch. Press **⌥Space**, type what you want to learn, and pick one of
three ways in:

- **Watch a video** (↵): Miyagi finds a YouTube tutorial and turns it into a lesson that pauses at every step.
- **Just teach me** (⌘↵): no video. Claude writes the lesson from the web and the official docs. A plain neural-network goal
  gets our hand-written lesson instead.
- **Demo** (the third chip): the neural-network lesson, staged so nothing can break in front of an audience.

In every lesson you work in your own VS Code, in a folder Miyagi sets up for that lesson (`~/miyagi/lessons/<lesson>`).

### Build a neural network (the lesson we demo)

A hand-written lesson served at once, with no build step and no model call to write it
(`server/orchestrator/curated.py`, `demo/cache/lessons/text-nn-from-scratch.json`). You build a 1-4-4-1 network in NumPy
(one input x, two hidden layers of 4 tanh neurons, one linear output y) and train it to learn y = sin(x) on [-π, π]:

| Step | What you do | What it checks |
|---|---|---|
| `nn1` Build the network | the sine data, W1 to W3 and `forward()` | tanh on both hidden layers and none on the output |
| `nn2` Backprop | `backward()` | `d_out = 2 * (out - y) / len(X)` and the tanh slope `1 - h²` on both layers |
| `nn3` Write the training loop | 20,000 epochs of gradient steps | every weight and bias steps downhill, the loss is the mean squared error |
| `nn4` Train it | run `python3 nn.py` | the loss falls below 0.01 |
| `nn5` Test it | print its answers and the weights | both prints are there |
| `nn6` See what it learned | run it again | it answers `[-1.0, 0.0, 1.0]` for x = -π/2, 0, π/2 |

- A "Before you start" sheet shows the plan (input → hidden layer 1 → hidden layer 2 → output → backprop → gradient step) and
  what to know first (NumPy arrays, matrix multiply, derivatives).
- Miyagi draws the network live. Until your first run it shows a preview of the lesson's own network. After
  each run that prints losses it shows **your** run: your weights on the edges, the neurons firing, the prediction for
  x = π/2 climbing to its target 1.
- The planned "Not yet": start every weight at zero and every hidden neuron gets the same update, so the network answers 0 for
  every x. The loss sits at 0.49 (the mean of sin²(x) over the lesson's 50 points), the panel shows eight identical dark
  neurons, and the card reads **Loss is stuck at 0.49** (in Just teach me, **All weights start at zero**), with a two-step
  hint ladder. Start the weights random and the
  lesson's own code goes from loss 0.8187 to 0.0009 by epoch 18,000 (`demo/cache/stage/nn-runs.json`, real NumPy output).
- The finished lesson ends on a completion panel with the lesson's skill map.

### Demo mode

The third launcher chip sends `learn` with `mode: "demo"` (`server/orchestrator/stage.py`). It loads the same neural-network
lesson, with the same folder, cards, hints and network panel, and stages it:

- A typing step passes by itself about a second after its code is pasted into `nn.py`, unsaved. **Check my work**, a save
  or the presenter's key also pass it, but only once that step's code is there (the key always does).
- A run step never runs anything. **Run it for me** shows a recorded run of the lesson's own code, and its loss lines feed the
  live curve and the network panel. The first Train it run is the stuck one when `nn.py` starts any weight at zero.
- No grading, screen reading or coach calls happen on stage. A typed question that can't reach Claude gets the step's own
  explanation (commit `65024d6`: with Wi-Fi off, 51 "Couldn't reach Claude" cards went to 0).
- Presenter keys, bound only while a Demo runs: ⌃⌥⌘→ passes the step, ⌃⌥⌘← goes back, ⌃⌥⌘R starts again at step 1 with a
  clean `nn.py` on disk and in VS Code's open tab (`POST /stage/next`, `/stage/back`, `/stage/restart`;
  `app/src/main/features/presenter.ts` on `adrian/shell`).
- Every Demo start is a fresh take: step 1 and a clean `nn.py`, never a saved step (commit `a2ff530`).
- A headless rehearsal plays the whole run of show against a private engine with no paid keys, as a regression gate
  (`scripts/rehearse_demo.py`, `server/tests/demo_rehearsal.py`).

### Watch a video

1. **Find.** The launcher shows YouTube videos only. Claude (with its web-search tool) and YouTube's own results page look for videos, and Claude scores every candidate. Rows under 40/100 are never shown
   (`FINDER_KINDS=video`, `FINDER_MIN_SCORE=40`, `server/finder/`).
2. **Preflight.** Within about 5 s of your pick, a card says what the video is: its style, length and chapters, whether it
   fits your goal, and which tools you're missing. Nothing is built until you say so (`server/preflight/`).
3. **Build.** Gemini watches the YouTube video at 0.5 fps, with its title, description and chapters as text, and returns the
   steps with timestamps, the code typed on screen, draft checks and a hint ladder (`server/lesson/gemini.py`). That draft is
   cached per video and goal (`demo/cache/lessons/raw/`), so Gemini watches each video once. Claude drafts the same lesson
   from the transcript in parallel and is used if Gemini fails or takes over 75 s (`server/lesson/builder.py`). Videos over
   30 minutes are built part by part (`server/lesson/progressive.py`).
4. **Adapt to your machine.** Claude rewrites the checks for your folder: your file names and the metric names your script
   prints. Claude also lists the tools the lesson needs, and the engine checks each one on your Mac. A setup card offers a
   one-press Install for what's missing (`server/workspace/setup.py`).
5. **Follow along.** The player plays one step's clip and pauses at the step's end ("Waiting for your checks") until your work
   passes. Then it resumes by itself (`app/src/renderer/src/features/player/store.ts` on `adrian/shell`).

### Just teach me, for any other topic

You type a goal like *"build a calculator"* (`server/lesson/textlesson.py`). Claude plans the steps, researches the topic with
its web-search and web-fetch tools (sources are only URLs those tools returned), and writes each step: what you build and
why, and the complete code to type. Step 1 is ready before the research finishes.

### Live checks, from your code and your screen

- **Your code.** The VS Code companion hands the engine the exact text in your editor, unsaved edits included. Without it the
  engine reads the file on disk, and OCR is the last resort (`server/orchestrator/editor_text.py`). You never press ⌘S: an
  edit is re-graded within about a second, and when a step needs the file on disk (before a run), the companion saves it
  for you (`server/orchestrator/quiet_save.py`, commit `f690f54`).
- **Your screen.** On-device Apple Vision OCR reads the terminal: the output, and the loss values off each printed line.
  Metric checks test thresholds and trends; the trend test is Mann-Kendall with a Theil-Sen slope, so a noisy flat curve
  doesn't count as falling (`server/checks/`).
- **Pointing.** The spotlight dims the screen and draws one white box: on the line to type, or on the real VS Code control to
  use next (the Run ▷ button, the terminal, the file's tab), found through macOS Accessibility (commit `34d525b`). The type
  box follows when VS Code scrolls (since companion 0.0.5, commit `84042f5`).

### The coach: "Not yet" cards and hints

- **Check my work** runs the step's checks on a fresh screen frame, then a Claude step judge reads the screen and the code.
- If the step isn't done, a **Not yet** card says what's left, from the rows that failed ("Still to do: ..."). A metric row
  shows your value next to the expected one (`server/orchestrator/code_gate.py`, commit `7863fa6`).
- **Hint** climbs a ladder: a guiding question first, then the moment in the video or the source, then the exact fix
  (`server/coach/hints.py`). When a check fails on its own, a Claude Sonnet coach reads your screen and code and writes one
  short card about what's wrong (`server/coach/diagnose.py`).
- The neural-net lesson's two planted bugs get their **Not yet** card at once, from the lesson's files with no model call:
  nn2's tanh slope written `1 + h ** 2` ("Wrong sign in the d_h2 tanh slope") and nn4's zero weights ("All weights start
  at zero") (commits `7cad4ff`, `085271e`). Any other failure goes to the coach.
- **Do it for me** shows a preview, applies only after you confirm, and can be undone.
- A run that stops on a missing package offers a one-press Install (commit `01bf965`). Terminal typos get a card without a
  model call (commit `2f20461`).

### Lessons survive restarts

Every lesson is saved as you go. After an engine restart, the first app connection continues the lesson at the exact step
(`server/sessions/`, `auto_resume` in `server/orchestrator/main.py`). `POST /end` ends a lesson and keeps your place;
`POST /end?forget=1` forgets it.

## How we built it

Two people and many parallel Claude Code sessions, each in its own git worktree. The boundary between them is the contracts
in `shared/contracts/`: WebSocket events, the step-graph and check schemas, the metric line protocol and the Tiger schema.

```
Electron overlay (app/: pill, launcher, drawer + network panel, spotlight, cards, bottom bar, video player)
        │  WebSocket :8787 · shared/contracts/events.ts
        ▼
engine: server/orchestrator (FastAPI hub, lesson state machine, curated NN lesson, Demo staging, quiet save)
  ├─ finder     Claude web search + scoring · YouTube results page + DuckDuckGo
  ├─ preflight  ≤ 5 s card before any build
  ├─ lesson     Watch a video: Gemini watches the video ∥ Claude drafts from the transcript; Claude adapts the checks
  │             Just teach me: Claude plans, researches (web search/fetch) and writes the steps
  ├─ workspace  per-lesson folder, the lesson's tools checked on this Mac, VS Code, Accessibility rects
  ├─ screen     ScreenCaptureKit → screencapture → CoreGraphics; Apple Vision OCR; Accessibility
  ├─ checks     pure evaluator: screen regex, metric threshold, metric trend (Mann-Kendall + Theil-Sen)
  ├─ coach      Claude step judge, Sonnet diagnosis, hint ladder, Do it for me
  ├─ sessions   restart-safe lesson saves + resume
  └─ Tiger Data learning_events + training_metrics hypertables, continuous aggregates, GET /stats
VS Code companion (vscode-ext/, 0.0.6): exact editor text, saves, terminal output and exit codes, scrolls
```

**Model rule.** Claude searches, scores, writes lessons and reads screens, code and transcripts. Gemini only watches YouTube
videos. Inside Claude we use tiers: Sonnet writes lessons and the coach's diagnosis; Haiku does the routine work (search
scoring, preflight, the Check judge, explaining, locating). Opus is never used by default (`server/coach/llm.py`,
`server/lesson/claude.py`).

**Screen reading.** Capture tries ScreenCaptureKit first, then Apple's `/usr/sbin/screencapture` when ScreenCaptureKit stalls
(as it does on macOS 26), then CoreGraphics. OCR runs on the device with Apple Vision. Our own overlay is left out of the
captured frames.

**VS Code companion** (`vscode-ext/`, version 0.0.6). Plain JavaScript with no build step, serving HTTP on 127.0.0.1 only
(port 8791). It gives the engine the open file, unsaved edits, the caret position, what's scrolled into view, and the terminal's last
command with its output and exit code. It can open a file at a line, run a command in a terminal named "Miyagi", save, and
apply a fix. It draws nothing in VS Code. It adds one command, **Miyagi: Explain this** (Ctrl+Cmd+E), answered in Miyagi's
overlay. Without it, the engine falls back to the screen and the disk.

**Electron overlay** (`app/`). Electron, React 19, TypeScript, Tailwind CSS 4, Motion and Zustand. The pill under the notch
shows progress and state, the launcher grows out of it, the drawer holds the steps, their live checks and the network panel,
and the YouTube player is docked to the right.

Measured numbers:

| What | Measured | Source |
|---|---|---|
| The NN lesson's own training run (seeded) | loss 0.8187 at epoch 0 → 0.0009 at epoch 18,000; with zero weights, 0.4900 on every line | `demo/cache/stage/nn-runs.json` |
| Demo with Wi-Fi off | "Couldn't reach Claude" cards: 51 → 0 | commit `65024d6` |
| Lesson builder on 5 tutorials (React, git, pandas, Rust, FastAPI) | Gemini's step starts a median 1 s from the chapter marks, against up to 15 s for the transcript path; React, Rust and FastAPI score 8–9/10 on Gemini; 43/43 step titles match the transcript | `evals/lesson/report.md` |
| A 24-minute video watched by Gemini | lesson built in 31.1 s | `build` in `demo/cache/lessons/aebc6b8fba02dac5.json` |
| Screen reader | capture ~17 ms; OCR ~100–220 ms per frame | `server/screen/README.md` |
| Plateau detector | flat noisy curves wrongly graded "improving": ≤ 3/300 seeds | `server/checks/README.md` |

Stack: Python 3.12 (FastAPI, PyObjC for ScreenCaptureKit, Vision and Accessibility, psycopg 3, httpx, watchdog); Electron,
React, TypeScript, Tailwind CSS, Motion; NumPy for the neural-network lesson.

## Challenges we ran into

- **Free-tier quotas.** Our Gemini key had per-model daily caps, and by mid-afternoon every video model returned `429`. So
  Claude's transcript path races Gemini, every lesson draft is cached, and Gemini has a daily cap
  (`LESSON_GEMINI_DAILY_CAP`, commit `6eb9aab`).
- **Cost.** A test sweep left running used up our prepaid Gemini credit, and every call returned
  `402 "prepayment credits are depleted"` (commit `15f0efe`). We added a 402 fast-fail with a 5-minute breaker, Haiku and
  Sonnet tiers with Opus off by default, token accounting in every lesson's `build.cost` (commit `d500d03`), and paid keys
  blanked in tests.
- **The venue Wi-Fi.** YouTube answered caption requests with `429`, so the transcript path falls back from the captions endpoint to the watch page and `youtube-transcript-api` (`server/lesson/transcript.py`). The network also blocked our Tiger Cloud port, so writes go to an
  offline spool (`~/.miyagi/tiger-spool/`) and upload on reconnect. For the stage, Demo mode makes no Claude call that can
  fail.
- **Screen capture on macOS 26.** `replayd` kept dropping our ScreenCaptureKit connection and `CGDisplayCreateImage` blocked
  for 5 s and returned nothing. We added the `screencapture` fallback (a temp PNG with mode 0600, deleted right away, with
  backoff; commit `e23a751`).
- **Pointing at the right place.** OCR guesses kept landing the box on VS Code's breadcrumb or jittering. We moved to exact
  editor line rects and VS Code's own controls through Accessibility, and the companion's scroll events keep the box on its
  line.
- **Human details from desktop tests.** Testers had to press ⌘S before every check and still watched checks lag, so grading
  moved to the live editor buffer and the companion saves for you. Engine deploys sent a lesson back to the start sheet, so `POST /end` now keeps your place
  and the next connection resumes the exact step (commit `f690f54`).

## Accomplishments that we're proud of

- The neural-network lesson works end to end in the learner's own editor: real code, real runs, a network panel drawn from
  their own weights, and a "Not yet" that teaches why zero weights never learn.
- Checks come from the learner's own code and screen, and they re-grade within about a second of an edit.
- A video lesson pauses at each step until the learner's work passes, and Gemini watches each video only once.
- No fake data on the live path. A failing module reports why. Canned data exists only behind `DEMO=1` and the Demo chip,
  and Demo recordings are tagged `demo` in Tiger.
- "Do it for me" is safe: preview, confirm, apply, undo.

## What we learned

- Reading the screen works with no plugin at all, but OCR misreads code ("import numey as np"). The companion's exact editor
  text fixed that (`server/orchestrator/editor_text.py`).
- Watching the video gets step boundaries as good or better than reading the transcript (median 1 s from the chapter marks,
  against up to 15 s, `evals/lesson/report.md`), and racing both keeps every build working.
- Noisy loss curves fool slope checks; rank-based trend tests don't.
- Spending needs guardrails from the very first test sweep.
- Small chores (a forgotten ⌘S, a box one line off) are what make a real learner give up.

## What's next

- A creator dashboard on the Tiger aggregates: where learners get stuck in *your* video.
- Community warnings pinned to timestamps ("breaks at 12:40 on pandas 2.x").
- More hand-written lessons like the neural network one.
- Windows support (platform differences are already isolated in `app/src/main/platform.ts`).

## Built with
`python` · `fastapi` · `pyobjc` · `apple-vision` · `screencapturekit` · `macos-accessibility` · `electron` · `react` ·
`typescript` · `tailwindcss` · `motion` · `numpy` · `claude` (Sonnet 5.5, Haiku 5.5) · `anthropic-api` · `gemini` ·
`bright-data` · `tiger-data` · `timescaledb` · `postgresql` · `youtube-iframe-api` · `vs-code` · `godaddy`

---

## Sponsor tracks

### Tiger Data
Tiger Data is the time-series record of every session.
- **Schema** (`shared/contracts/tiger-schema.sql`, `cli/sql/tiger-extras.sql`): hypertables `learning_events` (step started,
  check pass and fail, off track, fix applied, question, step passed) and `training_metrics`, with continuous aggregates
  `metrics_1s`, `time_per_step`, `check_fail_rate`, `stuck_heatmap` and `learner_progress`.
- **Training metrics:** every run the engine sees end (VS Code's ▷, a command typed in its terminal, Run it for me) sends its
  loss values to `training_metrics`. Demo recordings are written with source `demo`, and `/stats` labels them "Demo
  recording, not a live run" (`server/orchestrator/tiger_runs.py`, commit `b5cfcc1`).
- **Offline spool:** the writer batches `COPY` in the background. When Tiger can't be reached, rows wait in
  `~/.miyagi/tiger-spool/` and upload as soon as it answers (`server/checks/tiger.py`).
- **Stats page:** `localhost:8787/stats` shows the live loss curve with the tutorial's reference curve, time per step, fail
  rate per check and the stuck heatmap (`server/checks/stats_web.py`).
- **[CHECK]** Rows from today's runs are in the local spool because the venue network blocks Tiger's port. Say whether they
  reached Tiger Cloud (run `python -m server.checks.tiger --ping` and `--flush-spool` on a network that allows it), or keep
  this track's wording to "spooled offline".

### Gemini
Gemini is how Miyagi **watches** a tutorial (`LESSON_ENGINE=auto`, the default).
- The lesson builder sends the public YouTube URL to Gemini as `file_data` at 0.5 fps, with the title, description and
  chapters as text (`server/lesson/gemini.py`).
- It returns structured JSON: steps with MM:SS bounds, titles and instructions, the code typed on screen, draft checks,
  targets and a hint ladder.
- The draft is cached per video and goal, so each video is watched once. Claude then adapts the checks to the learner's
  folder.
- Claude's transcript draft runs in parallel and is used only if Gemini fails or takes over 75 s. Usage is capped per day
  (`LESSON_GEMINI_DAILY_CAP`) and logged in `build.cost`.
- Example: the cached PINN lesson was built by `gemini-4-hydrogen` watching a 24-minute video in 31.1 s (`build.model` in
  `demo/cache/lessons/aebc6b8fba02dac5.json`).
- **[CHECK]** Say whether a Gemini-built video lesson is shown in the demo video, or only described.

### GoDaddy
Our domain is **miyagi.study**. The app sends `https://miyagi.study/` as the Referer for YouTube embeds (`app/src/main/index.ts`).
**[CHECK]** Nothing in the repo shows the registration or what the domain serves. Confirm both, or drop this track.

### Not entered: ElevenLabs, xAI, Vultr
**[CHECK]** Michael dropped ElevenLabs and Vultr on Nov 15. `server/coach/voice.py` (ElevenLabs text to speech) is still in the
repo and speaks only with an ElevenLabs key. Nothing in the repo uses xAI or deploys to Vultr. Confirm none of these go on the form.

---

## Gallery images
In `docs/devpost/screenshots/`, 3200×2000. Taken on Nov 15 in the browser stage (`npm run dev:web`, mock scenarios
nndemo, happy, cards and complete) from `adrian/shell` with #129 (drawer side) and #141 (diagram flyout) merged. The mock
data was patched in two places only: "Cursor" reads "VS Code" with a second package in the setup card, and the completion
card uses the real engine's "Neural networks" track with 8 skills.
- `01-launcher.png`: "build a neural network" typed, with the Watch a video / Just teach me / Demo chips.
- `01b-lesson-sheet.png`: the "Your lesson" sheet (what you'll build, how it works, you'll need) beside the drawer.
- `02-box.png`: step 4, the box on the residual lines in the editor, with the video paused at "Waiting for your checks".
- `03-not-yet.png`: "Not yet. Loss is stuck at 0.49", yours 0.4900 against < 0.01, with Explain / Show me / Hint.
- `05-diagram-flyout.png`: the Diagram flyout out of the drawer's edge: the trained network, epoch 20,000, loss 0.0008.
- `06-skill-map.png`: the lesson-complete panel, "Neural networks · 8 skills mastered", loss 0.82 → 0.0009.
- `07-search.png`: Watch a video results for "physics-informed neural networks" (mock results, not a live search).
- `07b-video-checkpoint.png`: the video panel paused at the 9:48 checkpoint, "Waiting for your checks", 0 of 2 pass.
- `08-stats.png`: "Step 4 done · Loss 0.82 to 9.0e-4" (now vs before the fix) and the plan at 4 of 6 done.
- `09-setup-install-all.png`: "Set up this lesson" with VS Code and Python found, two packages and Install all.

## Before you submit
- [ ] **[CHECK]** The repo is public at https://github.com/michae6345-crypto/miyagi.
- [ ] **[CHECK]** The app judges run is `adrian/shell` (the Demo chip, presenter keys and network panel are there, not yet in
      `integration/live`'s `app/`).
- [ ] **[CHECK]** The presenter keys (⌃⌥⌘→ / ⌃⌥⌘← / ⌃⌥⌘R) were tried on the Mac: `presenter.ts` still marks them untested in
      Electron.
- [ ] **[CHECK]** Tiger: spooled rows uploaded, or the track says "spooled offline".
- [ ] **[CHECK]** Gemini: a video lesson in the demo video, or described only.
- [ ] **[CHECK]** GoDaddy: `miyagi.study` registered, and what it serves.
- [ ] **[CHECK]** ElevenLabs, xAI, Vultr: not entered.
- [ ] Backup screen recording of the Demo run of show (`docs/DEMO.md`).
- [ ] No `.env`, keys or connection strings in screenshots or the video.
