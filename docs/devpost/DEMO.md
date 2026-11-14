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
4. Engine. Start it with **`ORCH_LADDER_MIN_S=0`**. Otherwise the "Do it for me" card can't appear until 20 s after the first
   card (`server/orchestrator/config.py:117`). Pick **A** (the full flow, with live search) or **B** (lesson already loaded):
   ```bash
   ORCH_LADDER_MIN_S=0 scripts/miyagi-engine.sh
   ```
   ```bash
   ORCH_LADDER_MIN_S=0 scripts/miyagi-demo.sh
   ```
   B autostarts the hero lesson on `demo/pinn-lab` from E2's cache, with no launcher needed. Everything else (screen, checks, coach)
   is still live.
5. App: `cd app && npm run dev` on the `adrian/shell` branch (or the integration build). `ENGINE_URL` defaults to
   `ws://localhost:8787`.
6. **Python for the training run.** On the demo Mac, plain `python` doesn't exist and the system `python3` has no torch. In the
   VS Code terminal:
   ```bash
   source .venv/bin/activate && python -c "import torch; from pydoe import lhs"
   ```
   The rehearsed command is `tut run python pinn_diffusion.py`. It sends exact `::metric::` values. Plain `python …` relies on OCR
   of the terminal, which the rehearsal didn't cover.
7. **Pre-fill the code so the demo starts at the training step** (local edit, **don't commit**). Run
   `.venv/bin/python scripts/rehearse.py --prefill demo/pinn-lab`. It writes sections 1–7 the way the video does, with `lr = 0.3`
   and `steps = 2500` (runs take about 17–20 s). `rehearse.py` comes from the rehearsal PR "demo: rehearsal script + offline
   fallback" (`claude/demo-rehearsal-06521d`). Without it, fill the sections by hand from
   `server/lesson/fixtures/diffusion_workdir/pinn_diffusion.py`. **Don't add files to `demo/pinn-lab`** (`results.png` etc.):
   E2's cache key includes the folder's file names, and a cache miss means a live Gemini build.
8. Warm the cache: run the stage query once in the launcher, so the search cache and the lesson cache are both hot.
9. Layout: VS Code on the left two-thirds with the integrated terminal open at the bottom. Font size up (⌘+ ×2) so OCR and the
   judges can read it. Close Slack and email notifications (Focus mode ON).
10. A **second terminal tab**, with this typed in but **not run**: `curl -X POST localhost:8787/debug/goto/7`. The lesson starts
    at s1, and this jumps to s8, "Train the network and log loss".

---

## The 2-minute live demo

| Time | Do | Say |
|---|---|---|
| **0:00** | Nothing on screen but VS Code. | "YouTube tutorials can't tell whether you actually got it. Miyagi can. It turns any tutorial into an auto-graded lab." |
| **0:10** | Press **⌥Space**. The launcher grows out of the notch. Type exactly: **`learn physics informed machine learning with PINNs in PyTorch`** and press **↵**. | "I ask Miyagi anything. It searches the live web: Claude with web search, Bright Data's Google SERP, YouTube, GitHub and arXiv." |
| **0:15** | Rows stream in (first one in about 3–4 s). Point at a row's reason and any comment warning. | "Claude scores every result. Gemini actually skims the top videos, and Bright Data pulls the comments, so a video people say is broken gets flagged." |
| **0:25** | **↑/↓** to *Learning Physics Informed Machine Learning Part 1* (Toscano), then **↵**. The panel morphs into the pill: "Building lesson…" | "Gemini watches the whole 24-minute video and turns it into steps, each with checks a machine can grade from my screen. This one's cached; cold, it took 31 seconds." |
| **0:35** | `lesson.ready` (0.02 s from the cache). VS Code opens `demo/pinn-lab`. The lesson starts at s1. Switch to the second terminal tab and press **↵** on the `debug/goto/7` line: the video jumps to s8's clip, plays it, then pauses. The spotlight dims the screen around the training code. | "Each step plays one clip, then waits for me. Miyagi reads my whole screen with Apple Vision on the device, so it knows exactly where I should be working. Let's skip ahead to training." |
| **0:50** | In the VS Code terminal type **`tut run python pinn_diffusion.py`** and press **↵**. The loss prints and sits around 17. | "I'm training with learning rate 0.3." |
| **1:07** | Pill pulses **amber** (16.5–18.8 s after ↵). The check fails at step 2000, about 3 s before the run ends. | "The check reads my loss and tests whether it's actually improving, statistically. It isn't." |
| **1:13** | The coach card appears 5–7 s after amber (2–4 s after the run ends): *"Learning rate 0.3 is far too high… Set lr to 1e-3."* The spotlight lands on `lr=0.3`. This first card is a level-2 hint (Explain / Show me / Hint), **no fix button yet**. | "Claude Opus looks at my real screen and code and diagnoses it: about 3–4 seconds of model time. Nothing in it is scripted." |
| **1:20** | Press **⌘S** once. Within 1 s the level-3 card adds **Do it for me**. Click it: the preview shows `lr=0.3` → `lr=1e-3`. Click **Confirm**. (Or just type **`lr = 1e-3`** and **⌘S**.) | "Hints come before answers. If I want, it shows the exact diff, applies it only when I confirm, and I can undo it." |
| **1:25** | Run **`tut run python pinn_diffusion.py`** again. The loss drops under 1e-2 by step 1000 (green in 12–16 s; talk over it). | "Every check, every failure and every metric streams into Tiger Data: hypertables plus continuous aggregates. That gives a creator a stuck heatmap over their own video." |
| **1:40** | The step turns **green**. The video **resumes by itself** 0.4 s later. | "Green. The video moves on only when my code works." |
| **1:45** | Press **⌥D**. A diagram of the step's network appears. | "Need intuition? Claude draws a diagram for whatever step you're on, for any topic." |
| **1:52** | — | "Miyagi: any tutorial, any topic, graded from your real screen. Built on Claude, Gemini, Bright Data and Tiger Data." |

**If something stalls live:**
- The search is slow or empty: press **Esc**, then restart with `scripts/miyagi-demo.sh` (option B). The lesson is already
  loaded, so skip to 0:35.
- No amber after the run: you probably ran plain `python`. Use `tut run python …` so the metrics are exact. Press **⌥H** to force
  the hint card.
- The network is dead: the LIVE engine shows **no** coach card (`CoachUnavailable`, plus an error toast about once a second). Don't
  wait. Stop the engine and switch to `scripts/miyagi-offline.sh` (below).

---

## 60-second fallback (the network is dead)

Everything below runs with **no internet** except YouTube playback.

```bash
scripts/miyagi-offline.sh
```
- This script comes from the rehearsal PR "demo: rehearsal script + offline fallback" (`claude/demo-rehearsal-06521d`). Make sure
  it's merged before the freeze. It runs `DEMO=1` with autostart, **pins the hero lesson** (plain `DEMO=1` loads the newest
  cached lesson), and ships `demo/cache/coach/s8.json`: E5's `lr_too_high` playbook card from `server/coach/playbook.py`, word
  for word.
- **Don't use plain `DEMO=1`.** As shipped, it shows the orchestrator's stub card ("Loss plateaued at large β … β curriculum"),
  which is the wrong card for this failure.
- What the rehearsal verified offline: search, lesson, checks, `tut run` and the Tiger spool all work. The checks and the training
  run are real, because they run on the laptop.
- Offline there's **no "Do it for me"** (the card has no diff), and under `DEMO=1` `apply_fix` writes without a preview. Fix the
  learning rate **by hand**.
- If even the engine won't start: `cd app && DEMO=1 npm run dev` plays the scripted lesson **inside Electron with no engine and
  no network** (`app/README.md`, "Demo mode").
- The video can't play offline. Narrate over the step card, or play the **backup screen recording** of the full live run.

**Script (60 s):**
| Time | Do | Say |
|---|---|---|
| 0:00 | Lesson already loaded, pill showing "Step 8 · Train the network". | "Wi-Fi's down, so this is Miyagi offline: same checks, same screen reader, cached lesson." |
| 0:10 | Run `tut run python pinn_diffusion.py` with `lr=0.3`. | "Learning rate 0.3: the loss sits at 17." |
| 0:28 | Amber, then the coach card. | "The plateau check fails. Normally Claude Opus diagnoses this live from my screen; offline you get the same diagnosis from our curated playbook." |
| 0:35 | Type `lr = 1e-3`, save, run again. | "Fix it…" |
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

**"Will it edit my files?"** On the live path, only after you click Do it for me *and* confirm a diff preview. It refuses while the file has unsaved
edits, writes only patches that compile, keeps a backup for undo, and never runs terminal commands (it copies them to your clipboard).

**"Latency numbers?"** First search result about 3–4 s live (under 0.1 s from the cache); lesson from a 24-min video 31 s (Gemini),
29–83 s via the Claude transcript path; coach card 2–4 s after the run ends, of which 3–4 s is Opus (it starts before the run
ends); video resumes 0.4 s after green. Three rehearsal takes of the hero: all passed, 44–50 s of machine time each.

**"What's next?"** ElevenLabs voice for cards (app side built), a creator dashboard on the Tiger aggregates, and event-driven
capture instead of 1 fps.
