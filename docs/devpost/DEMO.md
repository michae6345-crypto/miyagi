# Miyagi: live demo script (2 min), fallback (60 s), judge Q&A (3 min)

Hero: Juan Toscano, *Learning Physics Informed Machine Learning Part 1: PINNs* (YouTube `AXXnSzmpyoI`, 24 min, PyTorch,
1D diffusion). Cached lesson: `demo/cache/lessons/aebc6b8fba02dac5.json` (9 steps). Hero failure: `lr = 0.3` → loss stuck around 17
(fails 6/6 seeds) → coach says `1e-3` → green (`demo/pinn-lab/README.md`).

---

## T-15 min: setup (off stage)

1. Network: plug into the **phone hotspot**. The venue Wi-Fi blocks Tiger's port and YouTube rate-limits caption requests from it.
2. Permissions: **System Settings › Privacy & Security › Screen & System Audio Recording** and **Accessibility** both ON for the
   terminal app that runs the engine. Quit and reopen that terminal after granting.
3. Tiger check (optional, quote the number if asked):
   ```bash
   .venv/bin/python -m server.checks.tiger --ping
   ```
4. Engine. Pick **A** (the full flow, with live search) or **B** (lesson already loaded):
   ```bash
   scripts/miyagi-engine.sh
   ```
   ```bash
   scripts/miyagi-demo.sh
   ```
   B autostarts the hero lesson on `demo/pinn-lab` from E2's cache, with no launcher needed. Everything else (screen, checks, coach)
   is still live.
5. App: `cd app && npm run dev` on the `adrian/shell` branch (or the integration build). `ENGINE_URL` defaults to
   `ws://localhost:8787`.
6. **Pre-fill the code so the demo starts at the training step.** In `demo/pinn-lab/pinn_diffusion.py` (local edit, **don't
   commit**), fill sections 1–7 the way the video does. The reference solution with the same sections is
   `server/lesson/fixtures/diffusion_workdir/pinn_diffusion.py`. Keep pinn-lab's `report()` helper, set the Adam line to
   **`lr=0.3`**, and leave the training loop's `report(i, loss, test_loss)` call in. Save the file.
7. Warm the cache: run the stage query once in the launcher, so the search cache and the lesson cache are both hot.
8. Layout: VS Code on the left two-thirds with the integrated terminal open at the bottom. Font size up (⌘+ ×2) so OCR and the
   judges can read it. Close Slack and email notifications (Focus mode ON).
9. Once the lesson is loaded, jump to the training step if you need to: `curl -X POST localhost:8787/debug/goto/7` (s8, "Train the
   network and log loss").

---

## The 2-minute live demo

| Time | Do | Say |
|---|---|---|
| **0:00** | Nothing on screen but VS Code. | "YouTube tutorials can't tell whether you actually got it. Miyagi can. It turns any tutorial into an auto-graded lab." |
| **0:10** | Press **⌥Space**. The launcher grows out of the notch. Type exactly: **`learn physics informed machine learning with PINNs in PyTorch`** and press **↵**. | "I ask Miyagi anything. It searches the live web: Claude with web search, Bright Data's Google SERP, YouTube, GitHub and arXiv." |
| **0:15** | Rows stream in (first one in about 3–4 s). Point at a row's reason and any comment warning. | "Claude scores every result. Gemini actually skims the top videos, and Bright Data pulls the comments, so a video people say is broken gets flagged." |
| **0:25** | **↑/↓** to *Learning Physics Informed Machine Learning Part 1* (Toscano), then **↵**. The panel morphs into the pill: "Building lesson…" | "Gemini watches the whole 24-minute video and turns it into steps, each with checks a machine can grade from my screen. This one's cached; cold, it took 31 seconds." |
| **0:35** | `lesson.ready`. VS Code opens `demo/pinn-lab`. The video plays the step's clip, then pauses. The spotlight dims the screen around the Adam line. | "Each step plays one clip, then waits for me. Miyagi reads my whole screen with Apple Vision on the device, so it knows exactly where I should be working." |
| **0:50** | In the VS Code terminal type **`python pinn_diffusion.py`** and press **↵**. The loss prints and sits around 17. | "I'm training with learning rate 0.3." |
| **1:00** | The run ends. The pill pulses **amber**. The coach card appears (about 3 s): *"Learning rate 0.3 is far too high… Set lr to 1e-3."* The spotlight lands on `lr=0.3`. | "The check reads the loss off my terminal and tests whether it's actually improving, statistically. It isn't. Claude Opus looks at my real screen and code and diagnoses it in about three seconds. Nothing in it is scripted." |
| **1:15** | (Optional) Press **⌥H** for the next hint, or click **Do it for me**: the diff preview shows `lr=0.3` → `lr=1e-3`, then **Confirm**. Otherwise edit it yourself to **`lr=1e-3`** and **⌘S**. | "It gives hints before answers. If I want, it shows the exact diff, applies it only when I confirm, and I can undo it." |
| **1:25** | Run **`python pinn_diffusion.py`** again. The loss drops under 1e-2 (about 15 s; talk over it). | "Every check, every failure and every metric streams into Tiger Data: hypertables plus continuous aggregates. That gives a creator a stuck heatmap over their own video." |
| **1:40** | The step turns **green** and the video **resumes by itself**. | "Green. The video moves on only when my code works." |
| **1:45** | Press **⌥D**. A diagram of the step's network appears. | "Need intuition? Claude draws a diagram for whatever step you're on, for any topic." |
| **1:52** | — | "Miyagi: any tutorial, any topic, graded from your real screen. Built on Claude, Gemini, Bright Data and Tiger Data." |

**If something stalls live:**
- The search is slow or empty: press **Esc**, then restart with `scripts/miyagi-demo.sh` (option B). The lesson is already
  loaded, so skip to 0:35.
- No amber after the run: check that the terminal shows `step N | loss …` lines and is on screen (OCR needs to see them). Press
  **⌥H** to force the hint card.
- The coach is slow (more than 10 s): keep talking. With `DEMO=1` the same card comes from the curated playbook (`lr_too_high`).

---

## 60-second fallback (the network is dead)

Everything below runs with **no internet** except YouTube playback.

```bash
DEMO=1 ORCH_AUTOSTART=1 ORCH_LESSON=demo/cache/lessons/aebc6b8fba02dac5.json TUT_WORKDIR="$PWD/demo/pinn-lab" scripts/miyagi-engine.sh
```
- `DEMO=1` serves `demo/cache/` and the coach's curated playbook card ("Learning rate is too high", citing Smith 2017, from
  `server/coach/playbook.py`). The **checks, screen reader and training run are still real**, because they run on the laptop.
- Recorded training runs can be replayed with `curl -X POST localhost:8787/demo/replay -d '{}' -H 'content-type: application/json'`
  (newest recording in `demo/runs/`). **(unverified)** `demo/cache/runs/` has no committed β/lr take yet. Copy a good one there
  before the freeze.
- If even the engine won't start: `cd app && DEMO=1 npm run dev` plays the scripted lesson **inside Electron with no engine and
  no network** (`app/README.md`, "Demo mode").
- The video can't play offline. Narrate over the step card, or play the **backup screen recording** of the full live run.

**Script (60 s):**
| Time | Do | Say |
|---|---|---|
| 0:00 | Lesson already loaded, pill showing "Step 8 · Train the network". | "Wi-Fi's down, so this is Miyagi offline: same checks, same screen reader, cached lesson." |
| 0:10 | Run `python pinn_diffusion.py` with `lr=0.3`. | "Learning rate 0.3: the loss sits at 17." |
| 0:25 | Amber, then the coach card. | "The plateau check fails. Normally Claude Opus diagnoses this live in about 3 seconds; offline you get the same diagnosis from our curated playbook." |
| 0:35 | Set `lr=1e-3`, save, run again. | "Fix it…" |
| 0:50 | Green. | "…green. The video would resume here. The live version finds the tutorial and builds the lesson itself." |

---

## Judge Q&A cheat sheet (3 min)

**"Is the coach scripted?"** No. On the live path `diagnose` calls `claude-opus-5-5` with the failing checks, the metric series,
your code and a set-of-mark screenshot (`server/coach/diagnose.py`, `llm.py`). Canned cards exist only under `DEMO=1`. Triage
skips the model only on purpose (nothing run yet, or an exact known error signature).

**"How do you know the loss is flat and not just noisy?"** `metric_trend` needs both a Mann-Kendall significance test (|z| ≥
2.576) and a Theil-Sen effect size of at least 5% across the window. On 300 random seeds, flat noisy curves falsely pass ≤ 3 times (it
was 61–136). The threshold check uses the median of the last 5 points (`server/checks/evaluator.py`).

**"How do you read the screen?"** ScreenCaptureKit frames about once a second, re-OCR'd with Apple Vision only when the frame
changed (100–220 ms on device). Our own overlay is excluded from the capture. Rects are in screen points, the same space as the
spotlight. With Accessibility granted we also read VS Code's live buffer and caret (`server/screen/`).

**"Does it work beyond PINNs?"** Yes, measured. React, git, pandas, Rust and FastAPI tutorials all built into schema-valid lessons
scored 8–9/10, with no PINN leakage (`evals/lesson/report.md`). Diagrams work for git graphs, React data flow and pandas groupby
(`server/diagrams/examples/`).

**"What does Gemini do vs Claude?"** Gemini watches YouTube: the full-video lesson pass and the search skim. Claude does
everything that reads text, code or screens: search, scoring, the transcript lesson path, the coach, diagrams and scaffolding.

**"What's Bright Data for?"** The SERP API runs the web search, the Web Scraper API pulls YouTube comments that flag outdated
tutorials, and the Web Unlocker fetches pages Claude reads and the docs the coach cites.

**"What's in Tiger?"** Two hypertables (`training_metrics`, `learning_events`) and five continuous aggregates (live 1 s curves,
time per step, fail rate per check, stuck heatmap per 15 s of video, learner progress). The venue Wi-Fi blocks Tiger's port, so the
writer spools to disk and replays on reconnect: nothing is lost.

**"What if Gemini's out of quota?"** That happened today. The Claude transcript path races Gemini, every lesson draft is cached,
and a failure is a plain-English error in under 6 s, never fake data.

**"Will it edit my files?"** Only after you click Do it for me *and* confirm a diff preview. It refuses while the file has unsaved
edits, writes only patches that compile, keeps a backup for undo, and never runs terminal commands (it copies them to your clipboard).

**"Latency numbers?"** First search result about 3–4 s; lesson from a 24-min video 31 s (Gemini), 29–83 s via the Claude transcript
path; coach card 3.3 s after the run ends; next step starts within 0.4 s of passing.

**"What's next?"** ElevenLabs voice for cards (app side built), a creator dashboard on the Tiger aggregates, and event-driven
capture instead of 1 fps.
