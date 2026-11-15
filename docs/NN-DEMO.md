# Neural-net lesson: handoff and presenter guide

The demo topic: **build a neural network from scratch** (2 inputs, 4 hidden neurons, 1 output, NumPy, learns XOR).
It is a curated lesson: written by hand, served instantly, the same every time.

| Mode | How it starts | What's live |
|---|---|---|
| **LIVE** (`scripts/miyagi-engine.sh`) | Launcher → any neural-network goal → **Just teach me** | The off-track coach (Claude). Lesson, hints, Explain and the network diagrams come from `demo/cache` (no build, no build cost). |
| **DEMO** (`scripts/miyagi-nn-demo.sh`) | Same | Nothing: DEMO=1 also serves the coach's off-track card from `demo/cache/coach/nn4.json`. |

Checks are the real ones in both: VS Code's exact editor text (companion extension), else `nn.py` on disk; the run steps
on what the run printed (VS Code's terminal via the extension, Run it for me, or the screen).

## Which goals get it

`server/orchestrator/curated.py` `matches(goal)`: the goal names a neural network ("neural network", "neural net",
"nn", "multilayer perceptron", "MLP") and nothing more specific (LLM / GPT / transformer, fine-tuning, CNN / RNN / GAN,
PyTorch / TensorFlow / Keras, images / MNIST / text / prices, another language such as JavaScript or C++).
"build a neural network", "neural net from scratch", "teach me how to create a neural network", "train a tiny neural
network", "build a nn": yes. "build an LLM", "fine-tune a neural network", "neural network in pytorch": no, those build
a lesson as before. `MIYAGI_CURATED=0` turns curated lessons off.

The folder is `~/miyagi/lessons/a-neural-net-from-scratch-<hash>/` (the same every time, so a NumPy installed into its
`.venv` stays). A fresh start puts the clean `nn.py` back; the previous attempt is kept in
`~/miyagi/lessons/.miyagi-state/attempts/`. Typing the goal again always starts at step 1, also after an engine restart
mid-lesson (that lesson's save is dropped); the resume card's Continue is how to go back to the saved step with your
`nn.py`. NumPy: the setup card offers to install it into the lesson's `.venv` when `python3` doesn't have it; once NumPy
is in the `.venv`, the run steps say `.venv/bin/python nn.py` (VS Code's terminal doesn't activate the venv).

## The six steps (what to do, what appears, what to say)

The right-hand panel of the drawer shows a live network at every step (pushed by the engine; `adrian/shell` PR #94).

| # | Step | You do | miyagi shows | Say |
|---|---|---|---|---|
| 1 | Build the network | Copy, paste under `# The network`. For the story, **change the two weight lines to zeros**: `W1 = np.zeros((2, 4))`, `W2 = np.zeros((4, 1))`. Save. | Panel: the network firing (forward pass). Checks go green. | "This is what we're building. I'll take a shortcut: zeros instead of random weights. The shapes are right, so it passes." |
| 2 | Backprop | Copy, paste under `# Backprop`, save | Panel: the error flowing back | "Backprop: the error goes back along the same weights; every weight gets its share of the blame." |
| 3 | Write the training loop | Copy, paste under `# Training`, save | Panel: what training will do | |
| 4 | Train it | Run it (Run it for me, or the command in VS Code's terminal) | Loss 0.2500 on every line → **off track** (live coach). Panel: **four identical neurons**. ⌥H twice: "look at how W1 and W2 start" → "start them random". | "Every check passed, but the loss never moved. All four hidden neurons are the same neuron." |
| 4b | | Change the two lines back to `np.random.randn(2, 4) * 0.5` / `np.random.randn(4, 1) * 0.5`, save, run again | Loss 0.2691 → 0.0009, step passes. Panel: **your run**, weights moving while the loss falls | "Random starts break the tie. Now it learns." |
| 5 | Test it | Copy, paste under `# Test it`, save | Panel: your run again | |
| 6 | See what it learned | Run it | `[0 1 1 0]` and the weights; lesson complete. Panel: your network answering 00 01 10 11, drawn from the weights it printed | "From nothing to a working neural net, every step checked." |

⌥D on any step opens the panel's network full size (no engine round trip when the panel has one).

## Under the hood

- Lesson and data: `scripts/make_nn_demo.py` (retrains with NumPy and rewrites every file, so every number on screen is
  real): `demo/cache/lessons/text-nn-from-scratch.json`, `cards/nn<k>-*.json` (+ `nn4-stuck-*`), `diagrams/nn<k>-network.json`
  + `nn4-gradients.json`, `coach/nn4.json` (DEMO only), `demo/nn-start.py`.
- Engine: `server/orchestrator/curated.py`. Pushed diagrams are ordinary `diagram` events (kind `network`, `data.frames`,
  `stepId` = the current step). After a run, the frames are redrawn from the learner's run: their printed losses, and
  their weights once `nn.py` prints them (step 5's code does). A run that matches the lesson's own run (seed 0) uses its
  exact weights for every frame.
- Typing and running are separate steps (the engine's lesson mode shows a run step's command as its snippet; one step
  for both hid the code).

## If something goes wrong

- **Step 4 never goes off track**: no loss lines were read. With the companion extension the run's own output is used;
  without it the screen must show `epoch 4000  loss 0.2500` in the terminal.
- **`ModuleNotFoundError: numpy`**: install NumPy from the setup card (or `brew install numpy`); the run steps then use
  `.venv/bin/python nn.py`.
- **A different lesson loads on Just teach me**: the goal didn't match (see above), or `MIYAGI_CURATED=0`.
- **No network on the right**: the app is older than `adrian/shell` PR #94 (pushed diagrams then open as a card).

## DEMO setup (Mac, once)

1. NumPy for the `python3` the terminal uses: `python3 -c "import numpy"`, else `pip3 install numpy` (Homebrew Python:
   `brew install numpy`).
2. `scripts/miyagi-nn-demo.sh` (engine on :8787, DEMO=1, `demo/nn-lab/nn.py` reset, its own state dir wiped each take).
3. The app from `adrian/shell`. Launcher: **build a neural network**, then **Just teach me**.
