# Neural-net lesson: handoff and presenter guide

The demo topic: **build a neural network from scratch**: a 1-4-4-1 network (one input x, two hidden layers of 4 tanh
neurons, one linear output y) in NumPy that learns the curve y = sin(x) on [-π, π] from 50 points. It is a curated
lesson: written by hand, served instantly, the same every time (seeded: `np.random.seed(0)`).

| Mode | How it starts | What's live |
|---|---|---|
| **LIVE** (`scripts/miyagi-engine.sh`) | Launcher → any neural-network goal → **Just teach me** | The off-track coach (Claude). Lesson, hints, Explain and the network diagrams come from `demo/cache` (no build, no build cost). |
| **DEMO** (`scripts/miyagi-nn-demo.sh`) | Same | Nothing: DEMO=1 also serves the coach's off-track card from `demo/cache/coach/nn4.json`. |

Checks are the real ones in both: VS Code's exact editor text (companion extension), else `nn.py` on disk; the run steps
on what the run printed (VS Code's terminal via the extension, Run it for me, or the screen).

## Which goals get it

`server/orchestrator/curated.py` `matches(goal)`: the goal names a neural network ("neural network", "neural net",
"nn", "multilayer perceptron", "MLP") and nothing more specific (LLM / GPT / transformer, fine-tuning, CNN / RNN / GAN,
PyTorch / TensorFlow / Keras, images / MNIST / text / prices, XOR (another task), another language such as JavaScript
or C++).
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
| 1 | Build the network | Copy, paste under `# The network`. For the story, **change the three weight lines to zeros**: `W1 = np.zeros((1, 4))`, `W2 = np.zeros((4, 4))`, `W3 = np.zeros((4, 1))`. Save. | Panel: the network firing (forward pass, x = -3 … 3). Checks go green. | "This is what we're building: x goes in, y comes out. I'll take a shortcut: zeros instead of random weights. The shapes are right, so it passes." |
| 2 | Backprop | Copy, paste under `# Backprop`, save | Panel: the error flowing back | "Backprop: the error goes back along the same weights; every weight gets its share of the blame." |
| 3 | Write the training loop | Copy, paste under `# Training`, save | Panel: what training will do | |
| 4 | Train it | Run it (Run it for me, or the command in VS Code's terminal) | Loss 0.4900 on every line → **off track** (live coach). Panel: **identical hidden neurons** (all eight at 0). ⌥H twice: "look at how W1, W2 and W3 start" → "start them random". | "Every check passed, but the loss never moved. All eight hidden neurons are the same neuron: each outputs tanh(0) = 0, so the network answers 0 for every x." |
| 4b | | Change the three lines back to `np.random.randn(1, 4)` / `np.random.randn(4, 4)` / `np.random.randn(4, 1) * 0.1`, save, run again (about 0.4 s) | Loss 0.8187 → 0.0009 (epoch 0 → 18000), step passes. Panel: **your run**, weights moving while the loss falls | "Random starts break the tie. Now it learns." |
| 5 | Test it | Copy, paste under `# Test it`, save | Panel: your run again | |
| 6 | See what it learned | Run it | `[-1.0, 0.0, 1.0]` (its answers for -π/2, 0, π/2) and the weights; lesson complete. Panel: your network answering x = -3 … 3, drawn from the weights it printed | "From nothing to a network that draws a sine wave, every step checked." |

⌥D on any step opens the panel's network full size (no engine round trip when the panel has one).

## Under the hood

- Lesson and data: `scripts/make_nn_demo.py` (retrains with NumPy and rewrites every file, so every number on screen is
  real): `demo/cache/lessons/text-nn-from-scratch.json`, `cards/nn<k>-*.json` (+ `nn4-stuck-*`), `diagrams/nn<k>-network.json`
  + `nn4-gradients.json`, `coach/nn4.json` (DEMO only), `demo/nn-start.py`.
- Engine: `server/orchestrator/curated.py`. Pushed diagrams are ordinary `diagram` events (kind `network`, `data.frames`,
  `stepId` = the current step). After a run, the frames are redrawn from the learner's run: their printed losses, and
  their weights once `nn.py` prints them (step 5's code does). A run that matches the lesson's own run (seed 0) uses its
  exact weights for every frame.
- Payload (`data`): `layers` `[1, 4, 4, 1]`, `labels` `{input: ["x"], output: ["y"]}`, `placement` `"drawer"`,
  `activation` `"tanh"` (hidden layers; the output is linear), `samples` (x = -3 … 3) / `targets` (sin x), `mode`,
  `frames`, plus the older `inputs` / `output` / `derivatives` / `residual`. A frame is
  `{epoch, loss, input, W: [W1 1x4, W2 4x4, W3 4x1], b: [b1[4], b2[4], b3[1]], a: [[x], [4], [4], [y]]}`:
  `W[k][i][j]` is the weight from neuron i of layer k to neuron j of layer k+1 (nested rows, no longer flat), `a` is
  every neuron's activation for that frame's `input` (the app fires the neurons from it; the engine recomputes it from
  the learner's printed weights). Train frames (every 1,000 epochs) cycle `input` through the samples; forward frames are
  the trained weights once per sample.
- Numbers: zeros sit at exactly 0.49 = mean(sin(x)²) over the 50 points (`curated.STUCK_LOSS`); the lesson's run
  prints 0.8187 at epoch 0 and 0.0009 at epoch 18000 (0.00078 after the last epoch). Plain gradient descent, lr 0.1,
  20,000 epochs: over 40 seeds, 39 end below 0.01 and print `[-1.0, 0.0, 1.0]`.
- Typing and running are separate steps (the engine's lesson mode shows a run step's command as its snippet; one step
  for both hid the code).

## If something goes wrong

- **Step 4 never goes off track**: no loss lines were read. With the companion extension the run's own output is used;
  without it the screen must show `epoch 18000  loss 0.4900` in the terminal.
- **`ModuleNotFoundError: numpy`**: install NumPy from the setup card (or `brew install numpy`); the run steps then use
  `.venv/bin/python nn.py`.
- **A different lesson loads on Just teach me**: the goal didn't match (see above), or `MIYAGI_CURATED=0`.
- **No network on the right**: the app is older than `adrian/shell` PR #94 (pushed diagrams then open as a card).

## DEMO setup (Mac, once)

1. NumPy for the `python3` the terminal uses: `python3 -c "import numpy"`, else `pip3 install numpy` (Homebrew Python:
   `brew install numpy`).
2. `scripts/miyagi-nn-demo.sh` (engine on :8787, DEMO=1, `demo/nn-lab/nn.py` reset, its own state dir wiped each take).
3. The app from `adrian/shell`. Launcher: **build a neural network**, then **Just teach me**.
