# Neural-net demo: handoff and presenter guide

The in-person demo: **build a neural net from scratch** in the real miyagi, on the real engine in DEMO mode.
No API calls and no network: the lesson, the coach's off-track card, hints, Explain / Ask cards and the live
network diagrams all come from `demo/cache`. Checks are the real ones (screen + file + run output).

Two branches, both needed:

| Branch | Base | What |
|---|---|---|
| `adrian/nn-demo-engine` (this one) | integration/live | the lesson as cache files, `scripts/make_nn_demo.py`, `scripts/miyagi-nn-demo.sh`, 3-line DEMO diagram lookup in `server/orchestrator/modules.py` |
| `adrian/nn-demo-app` | adrian/shell | `features/diagrams/NeuralNet.tsx`: network diagrams with real weights draw a live network. Without it the diagrams fall back to the old static view. Plus a drawer fix (long check details wrap). |

## Setup (Mac, once)

1. Check out both branches (worktrees are easiest). Your Mac auto-pulls `adrian/shell`, which does **not** have
   the app side yet: run the app from `adrian/nn-demo-app`, or merge it into shell.
2. NumPy for the `python3` the terminal uses: `python3 -c "import numpy"`. If that fails: `pip3 install numpy`.
   If pip refuses ("externally-managed-environment", Homebrew Python): `brew install numpy`.
3. Dry run once, start to finish (about 4 minutes).

## Start a take

```bash
scripts/miyagi-nn-demo.sh          # engine on :8787, DEMO=1; resets demo/nn-lab/nn.py and its own state dir
```
Every take starts clean: `nn.py` goes back to the four `# Step N` anchors, and progress is wiped, so there is no
"Continue where you left off?" card. The engine opens VS Code on `demo/nn-lab`.

Then the app (from `adrian/nn-demo-app`): open the launcher, type **build a neural net from scratch**, pick
**Just teach me** (Tab, then Enter, or ⌘↵). The pill builds the lesson; the drawer opens on step 1 of 4.

## The four steps (what to do, what appears, what to say)

| # | You do | miyagi shows | Say |
|---|---|---|---|
| 0 | Launcher → "build a neural net from scratch" → Just teach me | The lesson: what we're building, "Before you start" (4 ideas), the plan, step 1's code with Copy | "Tell it what you want to learn. Claude writes a lesson, then miyagi watches you do it." |
| 1 | **⌥D** first: the network firing. Esc. Then Copy step 1, paste under `# Step 1`, **change the two weight lines to zeros**: `W1 = np.zeros((2, 4))`, `W2 = np.zeros((4, 1))`. Save. | Diagram: circles light up by activation, blue/brown weights, signals firing, want vs gets for 00 01 10 11. Then the checks go green: "Good. Now the next one." | "This is what we're building. I'll take a shortcut: zeros instead of random weights. The shapes are right, so it passes." |
| 2 | Copy backward, paste under `# Step 2`, save. **⌥D**: the error flowing back. | Checks green | "Backprop: the error goes back along the same weights; every weight gets its share of the blame." |
| 3 | Copy the loop, paste under `# Step 3`, save, run `python3 nn.py` in the VS Code terminal | Loss 0.2500 on every line → **off track**: "Loss is stuck at 0.25", guiding question, yours vs expected. **⌥D**: four identical neurons, all 0.50. **⌥H** twice: the hint ladder ends at "start them random". | "Every check passed, but the loss never moved. miyagi caught it from the curve and asks a question first. All four neurons are the same neuron." |
| 3b | Change the two lines back to `np.random.randn(2, 4) * 0.5` / `np.random.randn(4, 1) * 0.5`, save, run again | Loss 0.2691 → 0.0009 → back on track, step passes | "Random starts break the tie. Now it learns." |
| 4 | **⌥D** first: watch it learn. Esc. Copy the print, paste under `# Step 4`, save, run | Weights grow, outputs settle on 0 1 1 0; then `[0 1 1 0]`, lesson complete | "From nothing to a working neural net, every step checked." |

Screenshots from the test run (browser stage on Windows, the desktop behind it is the stage's placeholder image):
`docs/nn-demo/1-lesson-step1.jpg`, `2-network-firing.png`, `3-off-track.jpg`, `4-four-identical-neurons.jpg`.

## What was tested, what wasn't

Tested on Adrian's Windows laptop: this branch's engine (DEMO=1, `ORCH_SCREEN=0` because screen reading is
macOS-only) with the app's browser stage connected. Lesson load, steps 1-2 passing on file checks, the real
run's output (posted to `/ingest`) going off track at 0.25 with the cached coach card, hints and diagrams,
the fix passing step 3, `[0 1 1 0]` passing step 4.

**Not tested** (needs your Mac): the screen checks (VS Code regexes, Terminal), reading the loss off the
Terminal with `metric_pattern` (`epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>…)`), Electron, VS Code auto-open.

## If something goes wrong

- **Step 3 never goes off track**: the loss lines weren't read. Check the Terminal shows `epoch 4000  loss 0.2500`
  and isn't covered; the check needs the line for epoch 4000.
- **A "Continue where you left off?" card**: the take didn't start from the script. Restart it with the script.
- **A different lesson loads on Just teach me**: another lesson-mode file in `demo/cache/lessons` is newer. The
  script touches this one; run the script again.
- **Diagrams look static (old network view)**: the app isn't on `adrian/nn-demo-app`.

## Changing the lesson

Edit `scripts/make_nn_demo.py` (code per step, checks, cards, captions) and run `python3 scripts/make_nn_demo.py`.
It retrains the network with NumPy and rewrites every cache file, so the numbers on screen stay real.
