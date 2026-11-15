# Neural-net lesson: handoff and presenter guide

The demo topic: **build a neural network from scratch**: a 1-4-4-1 network (one input x, two hidden layers of 4 tanh
neurons, one linear output y) in NumPy that learns the curve y = sin(x) on [-π, π] from 50 points. It is a curated
lesson: written by hand, served instantly, the same every time (seeded: `np.random.seed(0)`).

| Mode | How it starts | What's live |
|---|---|---|
| **LIVE** (`scripts/miyagi-engine.sh`) | Launcher → any neural-network goal → **Just teach me** | The off-track coach (Claude). Lesson, hints, Explain and the network diagrams come from `demo/cache` (no build, no build cost). |
| **DEMO** (`scripts/miyagi-nn-demo.sh`) | Same | Nothing: DEMO=1 also serves the coach's off-track card from `demo/cache/coach/nn4.json`. |

Checks are the real ones in both: VS Code's exact editor text (companion extension), else `nn.py` on disk; the run steps
on what the run printed (VS Code's terminal via the extension, Run it for me, or the screen). Each typing step checks its
key math, not just that the function exists (t6: step 2 passed with tanh's slope as `1 + h2 ** 2`): step 1 tanh on both
hidden layers and none on the output, step 2 `d_out = 2 * (out - y) / len(X)` and the slope `(1 - h ** 2)` on both
layers, step 3 every weight and bias `-= lr * d…` and the loss as the mean squared error.

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
is in the `.venv`, the run steps still say `python3 nn.py` (the folder's VS Code settings put `.venv/bin` first on
PATH in its terminals, and ▷ runs the `.venv`'s python); only Run it for me types `.venv/bin/python nn.py`. A run of
either counts.

## The six steps (what to do, what appears, what to say)

The right-hand panel of the drawer shows a live network at every step (pushed by the engine; `adrian/shell` PR #94).
Until the learner's first run it is a preview of the lesson's own network (`data.preview`: no epoch, no loss, never a
training run); from the first run on it is their run.

| # | Step | You do | miyagi shows | Say |
|---|---|---|---|---|
| 1 | Build the network | Copy, paste under `# The network`. For the story, **change the three weight lines to zeros**: `W1 = np.zeros((1, 4))`, `W2 = np.zeros((4, 4))`, `W3 = np.zeros((4, 1))`. Save. | Panel: a preview of the network you're building, firing (forward pass). Checks go green. | "This is what we're building: x goes in, y comes out. I'll take a shortcut: zeros instead of random weights. The shapes are right, so it passes." |
| 2 | Backprop | Copy, paste under `# Backprop`, save | Panel: a preview of the error flowing back | "Backprop: the error goes back along the same weights; every weight gets its share of the blame." |
| 3 | Write the training loop | Copy, paste under `# Training`, save | Panel: a preview of the network the loop starts from, standing still (nothing trains before the run) | |
| 4 | Train it | Run it (Run it for me, or the command in VS Code's terminal) | Loss 0.4900 on every line → **off track** (live coach). Panel: **loss stuck**, identical dark hidden neurons (all eight at 0), loss 0.4900. ⌥H twice: "look at how W1, W2 and W3 start" → "start them random". | "Every check passed, but the loss never moved. All eight hidden neurons are the same neuron: each outputs tanh(0) = 0, so the network answers 0 for every x." |
| 4b | | Change the three lines back to `np.random.randn(1, 4)` / `np.random.randn(4, 4)` / `np.random.randn(4, 1) * 0.1`, save, run again (about 0.4 s) | Loss 0.8187 → 0.0009 (epoch 0 → 18000), step passes. Panel: **your run**, weights moving while the loss falls | "Random starts break the tie. Now it learns." |
| 5 | Test it | Copy, paste under `# Test it`, save | Panel: your run again | |
| 6 | See what it learned | Run it | `[-1.0, 0.0, 1.0]` (its answers for -π/2, 0, π/2) and the weights; lesson complete. Panel: your network answering x = -π/2, 0, π/2, drawn from the weights it printed | "From nothing to a network that draws a sine wave, every step checked." |

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
  `activation` `"tanh"` (hidden layers; the output is linear), `samples` (x = -π/2, 0, π/2) / `targets` (sin x), `target` (1), `mode`,
  `frames`, plus the older `inputs` / `output` / `derivatives` / `residual`. A frame is
  `{epoch, loss, input, target, W: [W1 1x4, W2 4x4, W3 4x1], b: [b1[4], b2[4], b3[1]], a: [[x], [4], [4], [y]]}`:
  `W[k][i][j]` is the weight from neuron i of layer k to neuron j of layer k+1 (nested rows, no longer flat), `a` is
  every neuron's activation for that frame's `input` (the app fires the neurons from it; the engine recomputes it from
  the learner's printed weights). `preview` (true, t7): a step's cached picture before the learner's first run;
  its frames have no `epoch` / `loss` and it is never mode `train` (steps 3 and 4 are the start weights, standing
  still; the stuck picture asked for before a stuck run is mode `stuck`, one frame). The learner's runs leave it out
  and carry `epoch` and `loss`; a stuck run is mode `stuck`. Train frames (every 1,000 epochs) all fire x = π/2, so the panel's
  prediction climbs to its target 1.000 (the app shows `data.target` while it tweens train frames); forward frames are
  the trained weights once per sample, π/2 last (t6: x = 3, the worst-fit edge, read "Prediction 0.202 target -0.141").
- Numbers: zeros sit at exactly 0.49 = mean(sin(x)²) over the 50 points (`curated.STUCK_LOSS`); the lesson's run
  prints 0.8187 at epoch 0 and 0.0009 at epoch 18000 (0.00078 after the last epoch). Plain gradient descent, lr 0.1,
  20,000 epochs: over 40 seeds, 39 end below 0.01 and print `[-1.0, 0.0, 1.0]`.
- Typing and running are separate steps (the engine's lesson mode shows a run step's command as its snippet; one step
  for both hid the code).

## If something goes wrong

- **Step 4 never goes off track**: no loss lines were read. With the companion extension the run's own output is used;
  without it the screen must show `epoch 18000  loss 0.4900` in the terminal.
- **`ModuleNotFoundError: numpy`**: install NumPy from the setup card (or `brew install numpy`); a terminal opened
  before that may still find a `python3` without it: open a new one, click ▷, or press Run it for me (it runs
  `.venv/bin/python nn.py`).
- **A different lesson loads on Just teach me**: the goal didn't match (see above), or `MIYAGI_CURATED=0`.
- **No network on the right**: the app is older than `adrian/shell` PR #94 (pushed diagrams then open as a card).

## DEMO setup (Mac, once)

1. NumPy for the `python3` the terminal uses: `python3 -c "import numpy"`, else `pip3 install numpy` (Homebrew Python:
   `brew install numpy`).
2. `scripts/miyagi-nn-demo.sh` (engine on :8787, DEMO=1, `demo/nn-lab/nn.py` reset, its own state dir wiped each take).
3. The app from `adrian/shell`. Launcher: **build a neural network**, then **Just teach me**.
