# Miyagi: 2-minute demo (both ways to learn), 60-second fallback, judge Q&A

The live judging run is the neural-net lesson from the launcher's **Demo** chip, with the presenter keys ⌃⌥⌘→ (pass
the step), ⌃⌥⌘← (back a step) and ⌃⌥⌘R (a fresh take from step 1, with a clean `nn.py` in VS Code too). Its run of show
and offline runbook are in [`docs/DEMO.md`](../DEMO.md). This page covers the other two ways to learn, Watch a video and
Just teach me, and the judge Q&A.

Learners never have to press ⌘S to be graded. Miyagi grades the unsaved code in VS Code and saves the file itself
before a run. The VS Code
companion is 0.0.6 (`curl -s 127.0.0.1:8791/health`).

- **Path 1, Watch a video:** Juan Toscano, *Learning Physics Informed Machine Learning Part 1: PINNs* (YouTube `AXXnSzmpyoI`,
  24 min). Cached lesson: `demo/cache/lessons/aebc6b8fba02dac5.json` (9 steps). The failure: `lr = 0.3` keeps the loss stuck
  around 17 (fails 6/6 seeds), the coach says `1e-3`, and the step goes green (`demo/pinn-lab/README.md`).
- **Path 2, Just teach me:** "build a calculator", the goal Michael ran live (commit `b37a767`). No video, Claude only.

The timings for path 1 come from 3 rehearsal takes, all passing. **Path 2 has no measured timings in the repo yet: rehearse it and
write the real numbers in.**

---

## T-15 min: setup (off stage)

1. **Network:** the phone hotspot. The venue Wi-Fi blocks Tiger's port, and YouTube rate-limits caption requests from it.
2. **Permissions:** turn on **Screen & System Audio Recording** and **Accessibility** for the terminal app that runs the engine,
   under System Settings › Privacy & Security. Quit and reopen that terminal after granting.
3. **Engine** (`.env` has `LESSON_ENGINE=auto`, `GEMINI_API_KEY` set, and `MIYAGI_EDITOR=vscode`):
   ```bash
   ORCH_LADDER_MIN_S=0 COACH_OFFLINE_FALLBACK=1 scripts/miyagi-engine.sh
   ```
   - `ORCH_LADDER_MIN_S=0`: "Do it for me" appears after one more save instead of 20 s later.
   - `COACH_OFFLINE_FALLBACK=1`: if the network dies, the coach still shows the matching playbook card, marked offline.
4. **App:** from the **`adrian/shell`** branch (the launcher's two ways to learn and the bottom bar are there), run
   `cd app && npm run dev`.
5. **Python for the training run:**
   ```bash
   source .venv/bin/activate && python -c "import torch; from pydoe import lhs"
   ```
6. **Pre-fill the hero code** in `demo/pinn-lab/pinn_diffusion.py`. This is a local edit: **don't commit it**.
   - Fill sections 1–7 the way the video does: `lr = 0.3`, `steps = 2500`, and keep `report(i, loss, test_loss)`.
   - The reference solution is `server/lesson/fixtures/diffusion_workdir/pinn_diffusion.py`. Or run
     `.venv/bin/python scripts/rehearse.py --prefill demo/pinn-lab`, which does it automatically (merged in #43).
   - **Don't add files to `demo/pinn-lab`.** The lesson cache key includes the folder's file names, and a miss means a live build.
7. **Warm both caches:**
   - Run the path 1 query once and pick Toscano.
   - Then ⌥Space, type `build a calculator`, ⌘↵, and let it finish. Text lessons are cached by goal + folder, so on stage it
     comes back from the cache.
   - End both lessons afterwards (bottom bar › End lesson: one tap on a finished lesson, two mid-lesson, where the
     first tap reads "Tap to end").
8. **Layout:** VS Code, terminal open, font ⌘+ twice, Focus mode on. A second terminal tab has
   `curl -X POST localhost:8787/debug/goto/7` typed in but **not run**.
9. Optional: a browser tab on `http://localhost:8787/stats` (the Tiger stats page) for Q&A.

---

## The 2-minute script

| Time | Do | Say |
|---|---|---|
| **0:00** | VS Code on screen, the island pill under the notch. | "YouTube tutorials can't tell whether you actually got it. Miyagi can. It turns any tutorial into an auto-graded lab, and there are two ways in." |
| **0:07** | **⌥Space**. The launcher grows out of the island. Type **`learn physics informed machine learning with PINNs in PyTorch`**, then press **↵** (Watch a video). | "First way: watch a video. Claude searches YouTube with Bright Data's Google results, and Bright Data reads each video's comments, so a broken tutorial gets flagged." |
| **0:14** | **↑/↓** to *Learning Physics Informed Machine Learning Part 1* (Toscano), then **↵**. The **preflight card** shows within 5 s. Click **Build**. | "Before building anything, Miyagi tells me what this video is and what I'm missing. Then Gemini watches the video and builds the lesson, with Claude reading the transcript as backup." |
| **0:22** | The lesson loads (cached) and VS Code opens `demo/pinn-lab`. Switch to the second tab and press **↵** on `debug/goto/7`: the step's clip plays, then pauses. The screen dims to a **white box** on the code. | "Each step plays one clip and waits. Miyagi reads my whole screen on the device and boxes exactly where I work. Let's skip to training." |
| **0:30** | In the VS Code terminal: **`tut run python pinn_diffusion.py`** ↵. The loss sits around 17. | "Learning rate 0.3." |
| **0:47** | The pill pulses **amber** 16.5–18.8 s after ↵. | "The check reads my loss and tests whether it's improving, statistically. It isn't." |
| **0:53** | The coach card arrives 5–7 s after amber: *"Learning rate 0.3 is far too high… Set lr to 1e-3."* | "Claude reads my real screen and code. No script." |
| **0:58** | **⌘S** once. On a video lesson, saving the same failing code again is what asks for the exact fix, so within 1 s **Do it for me** appears. Click it, review the `lr=0.3 → lr=1e-3` preview, click **Confirm**. | "Hints before answers. The fix is a diff I approve, and I can undo it." |
| **1:02** | **`tut run python pinn_diffusion.py`** again. Green arrives 11.6–15.9 s later and the video resumes 0.4 s after that. | "Every check and every metric streams into Tiger Data. That's what lets a creator see where learners get stuck." |
| **1:18** | Bottom bar › **End lesson**, two taps (the first reads "Tap to end"). Then **⌥Space**, type **`build a calculator`**, press **⌘↵** (Just teach me). | "Second way: no video at all. Just teach me." |
| **1:24** | The pill shows the build. VS Code opens **full screen**. Step 1 appears and the white box sits on the exact line, with the code to type under the caption. | "Claude researched the official docs with web search and wrote the lesson, and Miyagi boxes exactly where to type." |
| **1:34** | Type the boxed line, then press **Check my work** (drawer or bar). No ⌘S: it grades the unsaved code. The step goes green and the box moves to the next line. | "Check runs the step's checks on my screen, then a Claude judge. Green." |
| **1:48** | — | "Two ways to learn, both graded from your real screen, and it survives a restart. Built on Claude, Gemini, Bright Data and Tiger Data." |

**If something stalls:**
- **Search is slow:** press Esc and run `ORCH_LADDER_MIN_S=0 COACH_OFFLINE_FALLBACK=1 scripts/miyagi-demo.sh`, which autostarts
  the hero lesson. Skip to 0:22.
- **No amber:** you ran plain `python`. Use `tut run`. Press Hint (⌃⌥H) to force the hint card.
- **Network dies:** with `COACH_OFFLINE_FALLBACK=1` the live engine still shows the "Learning rate is too high" playbook card
  (0.9 s after amber, verified offline in rehearsal). There's no "Do it for me" offline, so type `lr = 1e-3` by hand. Path 2's
  first build needs the network, so it only works offline if the cache was warmed in step 7.
- **The engine crashed:** restart it. The resume card ("<title> · step N of M") brings the lesson back at the same step.
- **Path 2 misbehaves:** skip it and press **Diagram** (⌃⌥D) on the hero step instead (a Claude-built diagram of the network).

---

## 60-second fallback (no network at all)

First choice: turn Wi-Fi fully off (better than flaky Wi-Fi), start `scripts/miyagi-nn-demo.sh`, and run the neural-net
lesson from the **Demo** chip. It needs no network. See "No network at the venue" in [`docs/DEMO.md`](../DEMO.md).

The older PINN fallback:

```bash
scripts/miyagi-offline.sh
```
- The checks, screen reader, `tut run` and Tiger spool all run on the laptop.
- **Watch the coach card:** under plain `DEMO=1` the rehearsal saw the orchestrator's β-curriculum stub card instead of the
  `lr_too_high` one. `scripts/miyagi-offline.sh` (above) pins the hero lesson, and `demo/cache/coach/s8.json` serves the right card
  (both merged in #43).
- If even the engine won't start, run `cd app && DEMO=1 npm run dev`. It plays a scripted lesson inside Electron, with no engine
  and no network.
- The video can't play offline. Narrate, or play the backup screen recording.

| Time | Do | Say |
|---|---|---|
| 0:00 | Hero lesson loaded, at step 8. | "No Wi-Fi, so this is Miyagi offline: same checks, same screen reader, cached lesson." |
| 0:10 | `tut run python pinn_diffusion.py` with `lr = 0.3`. | "The loss sits at 17." |
| 0:28 | Amber, then the card. | "The plateau check fails, and offline you get the curated diagnosis." |
| 0:35 | Type `lr = 1e-3`, save, run again. | "Fix it…" |
| 0:50 | Green. | "…green. Online, Claude finds the tutorial or writes the lesson itself." |

---

## Second path: "Just teach me" (no video), about 60 s

Rehearsed on integration/live ff8fdd1 with DEMO=1, offline, without the screen reader (`docs/REHEARSAL.md` §7). **On ff8fdd1
only steps 1–2 are stage-safe, and step 2 needs the workaround below.** The bugs are with E4.

**Setup (adds to T-15):**
- Cached lesson `demo/cache/lessons/text-43e26ca1d86c37ed.json` ("Build a Python Calculator", 8 steps, Michael's live run;
  added by the rehearsal PR). `DEMO=1` serves the newest cached lesson in "lesson" mode.
- Seed the lesson folder with the live run's starter. S2 names the folder from the goal, so type the goal exactly as below.
  Reset it before every take.
  ```bash
  D=~/miyagi/lessons/build-a-calculator-in-python-b38f75; rm -rf "$D" && mkdir -p "$D" && printf '"""A simple Python calculator."""\n\n# Step 1: Start building your calculator here\n' > "$D/calculator.py"
  ```
- `DEMO=1` isn't free online on this path: S2 calls Claude once to scaffold the folder, and every **Check** press asks E5's
  judge (Claude). Both are small, but they are real calls.
- VS Code goes full screen only if the terminal that runs the engine has **Accessibility**; otherwise press ⌃⌘F.

| Time | Do | Say |
|---|---|---|
| 0:00 | ⌥Space, type **`build a calculator in python`**, press **Just teach me** (or the "Build a lesson from the internet" row). | "No video this time: just teach me." |
| 0:03 | The lesson is ready in ~2 s (cached). VS Code opens on `calculator.py`; the box sits on `# Step 1: …`, captioned "Type the add function on the lines below this comment". | "It writes the lesson, opens my editor and shows me exactly where to type." |
| 0:10 | Type `def add(a, b):` / `return a + b`, then `print(add(2, 3))`. Press **Check my work** (no ⌘S). | "I type, I ask: can I move on?" |
| 0:25 | Step 2, "Run your first output". **Known bug:** it says "type print(add(2, 3))" and boxes that line instead of the terminal. Ignore the box and run `python3 calculator.py` in the VS Code terminal (`python` doesn't exist on this Mac). | "Now run it." |
| 0:35 | Prints `5`, step goes green (0.4–0.5 s after the run). | "Green: it checked my real run, not a quiz." |
| 0:45 | Stop here. Steps 3–7 box line 1 (a regex bug), and their captions contradict the step. | "Each step is a real piece of the program, graded the same way." |

---

## Judge Q&A cheat sheet (3 min)

**"Two ways to learn: what's the difference?"** Watch a video builds the lesson from a real YouTube tutorial: Gemini watches the
video while Claude reads its transcript as a backup. The video is gated step by step. Just teach me has no
video: Claude writes an overview and a step plan, researches the official docs with web search and fetch, and for each step says
what you build and why, with the complete code to type.
Both are graded the same way, from your screen.

**"Is the coach scripted?"** No. Live diagnoses come from `claude-sonnet-5-5` with the failing checks, your metrics, your code and
a marked-up screenshot (`server/coach/`). Canned cards exist only under `DEMO=1` or the opt-in offline fallback, which is marked
`offline: true`.

**"How does it know where to box?"** It uses macOS Accessibility for the exact editor line rect, VS Code's terminal and editor
regions from the screen reader, and Apple Vision OCR as the fallback. The overlay dims the rest of the screen to 55%.

**"How do you read the screen?"** ScreenCaptureKit first, then Apple's `screencapture` when ScreenCaptureKit stalls (macOS 26
does that), then CoreGraphics. OCR runs on the device in 100–220 ms per changed frame, and our own overlay is excluded. macOS Accessibility adds VS Code's
live buffer and caret. The VS Code companion extension is an optional precision boost; without it, Miyagi reads the screen.

**"How do you know the loss is flat, not noisy?"** A Mann-Kendall significance test plus a Theil-Sen effect size of at least 5%.
Flat noisy curves pass ≤ 3/300 times (it was 61–136).

**"What's Bright Data for?"** The SERP API supplies Google's video results for search, the YouTube comments dataset flags
tutorials that no longer work (up to 36 comments read per video in our recorded live searches), the Web Unlocker is the first
route for captions (and the backup for watch pages), and the coach looks up docs through SERP + Unlocker (`server/coach/web.py`).

**"What's in Tiger?"** `learning_events` and `training_metrics` hypertables plus five continuous aggregates: the live 1 s curve,
time per step, fail rate per check, a stuck heatmap per 15 s of video, and learner progress. You can see them live at
`localhost:8787/stats`. When the venue Wi-Fi blocks the port, writes spool to disk and replay later.

**"Where's Gemini?"** Gemini watches the video. It gets the YouTube URL at 0.5 fps plus the title, description and chapters, and
returns the steps with timestamps, the code typed on screen, draft checks and the hint ladder. Claude builds the same lesson from
the transcript in parallel and is used if Gemini fails or takes over 75 s. The cached hero lesson was built by Gemini. Gemini is
capped per day and logged in `build.cost`; everything else (Just teach me, search, the coach, the judge, screen reading) is Claude.

**"What did it cost / how do you control spend?"** An unsupervised test sweep drained our prepaid Gemini credit (about $20, team
figure). Since then: a billing fast-fail, a daily Gemini cap, skims off, Claude tiers (Haiku/Sonnet; Opus off), Claude's
transcript draft as the fallback when Gemini is out of credit, and per-model token logging.

**"What if it crashes?"** Every lesson is saved as it's built. A restart offers to resume at the same step with no rebuild.

**"Will it edit my files?"** Only after you click Do it for me and confirm a diff preview. It refuses while the file has unsaved
changes, writes only code that compiles, and can be undone. A fix that's a terminal command is copied to your clipboard, never
run. The one command Miyagi runs is a run step's own command, when you press Run it for me.
