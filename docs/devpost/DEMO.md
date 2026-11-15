# Miyagi: 2-minute demo (both ways to learn), 60-second fallback, judge Q&A

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
3. **Engine** (`.env` already has `LESSON_ENGINE=claude-first`):
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
   - The reference solution is `server/lesson/fixtures/diffusion_workdir/pinn_diffusion.py`. The rehearsal PR's
     `scripts/rehearse.py --prefill demo/pinn-lab` does it automatically once that PR is merged.
   - **Don't add files to `demo/pinn-lab`.** The lesson cache key includes the folder's file names, and a miss means a live build.
7. **Warm both caches:**
   - Run the path 1 query once and pick Toscano.
   - Then ⌥Space, type `build a calculator`, ⌘↵, and let it finish. Text lessons are cached by goal + folder, so on stage it
     comes back from the cache.
   - End both lessons afterwards (bottom bar › End lesson).
8. **Layout:** VS Code, terminal open, font ⌘+ twice, Focus mode on. A second terminal tab has
   `curl -X POST localhost:8787/debug/goto/7` typed in but **not run**.
9. Optional: a browser tab on `http://localhost:8787/stats` (the Tiger stats page) for Q&A.

---

## The 2-minute script

| Time | Do | Say |
|---|---|---|
| **0:00** | VS Code on screen, the island pill under the notch. | "YouTube tutorials can't tell whether you actually got it. Miyagi can. It turns any tutorial into an auto-graded lab, and there are two ways in." |
| **0:07** | **⌥Space**. The launcher grows out of the island. Type **`learn physics informed machine learning with PINNs in PyTorch`**, then press **↵** (Watch a video). | "First way: watch a video. Claude searches YouTube with Bright Data's Google results, and Bright Data reads each video's comments, so a broken tutorial gets flagged." |
| **0:14** | **↑/↓** to *Learning Physics Informed Machine Learning Part 1* (Toscano), then **↵**. The **preflight card** shows within 5 s. Click **Build**. | "Before building anything, Miyagi tells me what this video is and what I'm missing. Then Claude builds the lesson from the transcript; Gemini watches the video only when there's no transcript." |
| **0:22** | The lesson loads (cached) and VS Code opens `demo/pinn-lab`. Switch to the second tab and press **↵** on `debug/goto/7`: the step's clip plays, then pauses. The screen dims to a **white box** on the code. | "Each step plays one clip and waits. Miyagi reads my whole screen on the device and boxes exactly where I work. Let's skip to training." |
| **0:30** | In the VS Code terminal: **`tut run python pinn_diffusion.py`** ↵. The loss sits around 17. | "Learning rate 0.3." |
| **0:47** | The pill pulses **amber** 16.5–18.8 s after ↵. | "The check reads my loss and tests whether it's improving, statistically. It isn't." |
| **0:53** | The coach card arrives 5–7 s after amber: *"Learning rate 0.3 is far too high… Set lr to 1e-3."* | "Claude Opus reads my real screen and code. No script." |
| **0:58** | **⌘S** once. Within 1 s **Do it for me** appears. Click it, review the `lr=0.3 → lr=1e-3` preview, click **Confirm**. | "Hints before answers. The fix is a diff I approve, and I can undo it." |
| **1:02** | **`tut run python pinn_diffusion.py`** again. Green arrives 11.6–15.9 s later and the video resumes 0.4 s after that. | "Every check and every metric streams into Tiger Data. That's what lets a creator see where learners get stuck." |
| **1:18** | Bottom bar › **End lesson**. Then **⌥Space**, type **`build a calculator`**, press **⌘↵** (Just teach me). | "Second way: no video at all. Just teach me." |
| **1:24** | The pill shows the build. VS Code opens **full screen**. Step 1 appears and the white box sits on the exact line, with the code to type under the caption. | "Claude researched the official docs with web search and wrote the lesson, and Miyagi boxes exactly where to type." |
| **1:34** | Type the boxed line, **⌘S**, then bottom bar › **Check**. The step goes green and the box moves to the next line. | "Check runs the step's checks on my screen, then a Claude judge. Green." |
| **1:48** | — | "Two ways to learn, both graded from your real screen, and it survives a restart. Built on Claude, Bright Data, Tiger Data and Gemini." |

**If something stalls:**
- **Search is slow:** press Esc and run `ORCH_LADDER_MIN_S=0 COACH_OFFLINE_FALLBACK=1 scripts/miyagi-demo.sh`, which autostarts
  the hero lesson. Skip to 0:22.
- **No amber:** you ran plain `python`. Use `tut run`. Press ⌥H to force the hint card.
- **Network dies:** with `COACH_OFFLINE_FALLBACK=1` the live engine still shows the "Learning rate is too high" playbook card
  (0.9 s after amber, verified offline in rehearsal). There's no "Do it for me" offline, so type `lr = 1e-3` by hand. Path 2's
  first build needs the network, so it only works offline if the cache was warmed in step 7.
- **The engine crashed:** restart it. The resume card ("<title> · step N of M") brings the lesson back at the same step.
- **Path 2 misbehaves:** skip it and press **⌥D** on the hero step instead (a Claude-built diagram of the network).

---

## 60-second fallback (no network at all)

```bash
DEMO=1 ORCH_AUTOSTART=1 ORCH_LESSON=demo/cache/lessons/aebc6b8fba02dac5.json TUT_WORKDIR="$PWD/demo/pinn-lab" scripts/miyagi-engine.sh
```
- The checks, screen reader, `tut run` and Tiger spool all run on the laptop.
- **Watch the coach card:** under plain `DEMO=1` the rehearsal saw the orchestrator's β-curriculum stub card instead of the
  `lr_too_high` one. The rehearsal PR's `scripts/miyagi-offline.sh` + `demo/cache/coach/s8.json` fix that, but they **aren't
  merged**. Until they are, prefer the live engine with `COACH_OFFLINE_FALLBACK=1` (above).
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
| 0:10 | Type `def add(a, b):` / `return a + b`, then `print(add(2, 3))`. ⌘S, press **Check**. | "I type, I ask: can I move on?" |
| 0:25 | Step 2, "Run your first output". **Known bug:** it says "type print(add(2, 3))" and boxes that line instead of the terminal. Ignore the box and run `python3 calculator.py` in the VS Code terminal (`python` doesn't exist on this Mac). | "Now run it." |
| 0:35 | Prints `5`, step goes green (0.4–0.5 s after the run). | "Green: it checked my real run, not a quiz." |
| 0:45 | Stop here. Steps 3–7 box line 1 (a regex bug), and their captions contradict the step. | "Each step is a real piece of the program, graded the same way." |

---

## Judge Q&A cheat sheet (3 min)

**"Two ways to learn: what's the difference?"** Watch a video builds the lesson from a real YouTube tutorial: Claude reads its
transcript, and Gemini watches the video only when there's no transcript. The video is gated step by step. Just teach me has no
video: Claude plans the steps, researches the official docs with web search and fetch, and writes the exact code for each step.
Both are graded the same way, from your screen.

**"Is the coach scripted?"** No. Live diagnoses come from `claude-opus-5-5` with the failing checks, your metrics, your code and
a marked-up screenshot (`server/coach/`). Canned cards exist only under `DEMO=1` or the opt-in offline fallback, which is marked
`offline: true`.

**"How does it know where to box?"** It uses macOS Accessibility for the exact editor line rect, VS Code's terminal and editor
regions from the screen reader, and Apple Vision OCR as the fallback. The overlay dims the rest of the screen to 55%.

**"How do you read the screen?"** ScreenCaptureKit first, then Apple's `screencapture` when ScreenCaptureKit stalls (macOS 26
does that), then CoreGraphics. OCR runs on the device in 100–220 ms per changed frame, and our own overlay is excluded.

**"How do you know the loss is flat, not noisy?"** A Mann-Kendall significance test plus a Theil-Sen effect size of at least 5%.
Flat noisy curves pass ≤ 3/300 times (it was 61–136).

**"What's Bright Data for?"** The SERP API supplies Google's video results for search, the YouTube comments dataset flags
tutorials that no longer work (up to 36 comments read per video in our recorded live searches), and the Web Unlocker is the
fallback route for captions.

**"What's in Tiger?"** `learning_events` and `training_metrics` hypertables plus five continuous aggregates: the live 1 s curve,
time per step, fail rate per check, a stuck heatmap per 15 s of video, and learner progress. You can see them live at
`localhost:8787/stats`. When the venue Wi-Fi blocks the port, writes spool to disk and replay later.

**"Where's Gemini?"** It's the video-watching fallback in the lesson builder, used when there's no transcript or Claude's draft
fails. It's capped per day and its token use is logged in `build.cost`.

**"What did it cost / how do you control spend?"** An unsupervised test sweep drained our prepaid Gemini credit (about $20, team
figure). Since then: a billing fast-fail, a daily Gemini cap, skims off, Claude tiers (Haiku/Sonnet, Opus only on failure) and
per-model token logging.

**"What if it crashes?"** Every lesson is saved as it's built. A restart offers to resume at the same step with no rebuild.

**"Will it edit my files?"** Only after you click Do it for me and confirm a diff preview. It refuses while the file has unsaved
changes, writes only code that compiles, can be undone, and never runs terminal commands.
