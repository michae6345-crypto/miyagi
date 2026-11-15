"""Builds the curated "build a neural network" lesson (LIVE and DEMO=1), with zero API calls.

    python scripts/make_nn_demo.py          # needs numpy; rewrites every file below
    scripts/miyagi-nn-demo.sh               # DEMO=1 engine on it (offline coach); LIVE needs nothing (see below)

LIVE: "Just teach me" with a neural-network goal ("build a neural network", "neural net from scratch", ...) serves this
lesson instantly instead of building one (server/orchestrator/curated.py; MIYAGI_CURATED=0 turns that off). The coach
stays live; hints, the Explain button and every network diagram come from the files below.

The network: 1-4-4-1 (one input x, two hidden layers of 4 tanh neurons, one linear output y), NumPy only, trained with
plain gradient descent on MSE to draw the curve y = sin(x) for 50 points on [-pi, pi]. Seeded (np.random.seed(0)), so
the lesson's run is the same every time.

What it writes (all data, no engine code):
  demo/nn-lab/nn.py, demo/nn-start.py       the learner's file and its clean copy (four section comments)
  demo/cache/lessons/text-nn-from-scratch.json
                                            the 6-step lesson (mode "lesson"): typing steps and run steps alternate,
                                            the way the engine's lesson mode expects (a run step's snippet is its command)
  demo/cache/coach/nn4.json                 DEMO only: the off-track card when training stays flat (zero weights)
  demo/cache/cards/nn<k>-explain|answer|hint<n>.json, nn4-stuck-explain|hint<n>.json
                                            Explain / Ask (DEMO) / Hint for each step; nn4-stuck-*: the ladder once the
                                            loss is stuck at 0.4900
  demo/cache/diagrams/nn<k>-network.json, nn4-gradients.json
                                            live networks (the app's NeuralNet view): neurons lit by activation,
                                            weights blue/brown, signals firing. The engine pushes them to the drawer's
                                            right-hand panel and redraws the training ones from the learner's own run.

Diagram payload (kind "network"): data.layers [1, 4, 4, 1], labels {input: ["x"], output: ["y"]}, placement "drawer",
activation "tanh" (hidden; the output is linear), samples [[x]] for x = -π/2, 0, π/2, targets sin(x), target sin(π/2),
mode, frames. A frame:
    {epoch, loss, input: x, target: sin(x), W: [W1 1x4, W2 4x4, W3 4x1], b: [b1[4], b2[4], b3[1]], a: [[x], [4], [4], [y]]}
W[k][i][j] is the weight from neuron i of layer k to neuron j of layer k+1; `a` is every neuron's activation for the
frame's input. Train frames (one per SNAP epochs) all fire x = π/2, so the panel's prediction climbs to its target 1;
forward frames are the trained weights once per sample (π/2 last: the frame that stays up).

The story (DEMO's presenter, or any learner who takes the shortcut): step 1 builds the network with W1, W2 and W3 =
zeros. Every check passes. Step 4 trains: the loss sits at exactly 0.4900 on every line, because every hidden neuron
outputs tanh(0) = 0 and gets the same (zero) update, so the network answers 0 for every x. miyagi goes off track, the
diagram shows identical neurons, the hint ladder says start them random; the learner fixes it, reruns, and the loss
falls. Every number comes from running the code below.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "demo" / "nn-lab"
CACHE = ROOT / "demo" / "cache"
RUN = "python3 nn.py"

# The run (every number in the lesson's code; the checks and cards below quote them)
N_POINTS = 50  # x = linspace(-pi, pi, 50): zeros answer 0 everywhere -> MSE = mean(sin^2) = 49/100 exactly
LR = 0.1
EPOCHS = 20000  # about 0.3 s; plain gradient descent, so the loss keeps creeping down the whole run
PRINT_EVERY = 2000  # the loss lines the loop prints (10 of them: the run check takes the median of the last 5)
SNAP = 1000  # a diagram frame every SNAP epochs (every printed epoch has one: curated.live_frames matches on them)
# np.random.randn(...) * scale (1.0: no factor in the code). W3 starts small, so the first guesses are near 0.
# Picked over 40 seeds: 39 end below 0.01 and print [-1.0, 0.0, 1.0]; seed 0 (the lesson's) is one of them.
SCALE = {"W1": 1.0, "W2": 1.0, "W3": 0.1}
STUCK_LOSS = (N_POINTS - 1) / (2 * N_POINTS)  # 0.49: what curated.py's STUCK_LOSS must be
LOSS_TARGET = 0.01  # the run step passes once the loss is below this by BY_EPOCH
BY_EPOCH = EPOCHS - PRINT_EVERY  # the last printed epoch

# ---------------------------------------------------------------------------------------------------------------
# The code, step by step (what the drawer shows and Copy copies). The learner pastes it under each section comment.
# The comments carry no numbers: the lesson has 6 steps (4 to type, 2 to run) but the file has 4 sections.
# ---------------------------------------------------------------------------------------------------------------

STARTER = """# A neural net from scratch: 1 input, two hidden layers of 4 neurons, 1 output. It learns the curve y = sin(x).
import numpy as np

# The network


# Backprop


# Training


# Test it
"""

ANCHOR = {"nn1": "# The network", "nn2": "# Backprop", "nn3": "# Training", "nn5": "# Test it"}


def _init(name: str, shape: str) -> str:
    s = SCALE[name]
    return f"np.random.randn({shape})" + ("" if s == 1.0 else f" * {s:g}")


INIT = {"W1": _init("W1", "1, 4"), "W2": _init("W2", "4, 4"), "W3": _init("W3", "4, 1")}
EPOCH_W = len(str(EPOCHS - 1))

CODE = {
    "nn1": f"""X = np.linspace(-np.pi, np.pi, {N_POINTS}).reshape(-1, 1)
y = np.sin(X)

np.random.seed(0)
W1 = {INIT["W1"]}
b1 = np.zeros((1, 4))
W2 = {INIT["W2"]}
b2 = np.zeros((1, 4))
W3 = {INIT["W3"]}
b3 = np.zeros((1, 1))

def forward(X):
    h1 = np.tanh(X @ W1 + b1)
    h2 = np.tanh(h1 @ W2 + b2)
    return h1, h2, h2 @ W3 + b3""",
    "nn2": """def backward(X, y, h1, h2, out):
    d_out = 2 * (out - y) / len(X)
    d_h2 = d_out @ W3.T * (1 - h2 ** 2)
    d_h1 = d_h2 @ W2.T * (1 - h1 ** 2)
    return h2.T @ d_out, d_out.sum(0), h1.T @ d_h2, d_h2.sum(0), X.T @ d_h1, d_h1.sum(0)""",
    "nn3": f"""lr = {LR:g}
for epoch in range({EPOCHS}):
    h1, h2, out = forward(X)
    dW3, db3, dW2, db2, dW1, db1 = backward(X, y, h1, h2, out)
    W3 -= lr * dW3
    b3 -= lr * db3
    W2 -= lr * dW2
    b2 -= lr * db2
    W1 -= lr * dW1
    b1 -= lr * db1
    loss = np.mean((out - y) ** 2)
    if epoch % {PRINT_EVERY} == 0:
        print(f"epoch {{epoch:{EPOCH_W}d}}  loss {{loss:.4f}}")""",
    "nn4": RUN,
    "nn5": """h1, h2, out = forward(np.array([[-np.pi / 2], [0.0], [np.pi / 2]]))
print(np.round(out, 1).ravel().tolist())
for name, w in (("W1", W1), ("b1", b1), ("W2", W2), ("b2", b2), ("W3", W3), ("b3", b3)):
    print(name, np.round(w, 3).tolist())""",
    "nn6": RUN,
}

# ---------------------------------------------------------------------------------------------------------------
# Real runs: the weights every SNAP epochs (the live diagrams), for the shortcut (zeros) and the lesson's code.
# ---------------------------------------------------------------------------------------------------------------

X = np.linspace(-np.pi, np.pi, N_POINTS).reshape(-1, 1)
Y = np.sin(X)
TEST_X = [-math.pi / 2, 0.0, math.pi / 2]  # step 5 prints the network's answers here: sin = -1, 0, 1
# What the panel shows: the network's prediction for one x, next to its target sin(x). t6: the train frames cycled
# x = -3..3 and ended on x = 3 (the edge of [-pi, pi], the trained net's worst point: 0.202 for sin(3) = 0.141), and the
# app, which shows data.target / targets[0] while it tweens frames, said "Prediction 0.202 target -0.141" (sin(-3)).
# Now every frame carries its own target, the samples are the test step's three points (the trained net is within
# 0.012 of sin there), and every training frame fires x = pi/2: the replay's prediction climbs to 1.01, target 1.000.
SAMPLES = [[round(x, 4)] for x in TEST_X]
TARGETS = [round(math.sin(s[0]), 4) for s in SAMPLES]
REST_X = SAMPLES[-1][0]  # pi/2: every training frame's input, and the forward frame that stays up (the last)


def r4(a) -> list:
    """An array as (nested) lists rounded to 4 places, with -0.0 as 0.0."""
    return (np.round(np.asarray(a, dtype=float), 4) + 0.0).tolist()


def fire(W: list[np.ndarray], b: list[np.ndarray], x: float) -> list[list[float]]:
    """Every neuron's activation for input x: [[x], tanh layer 1, tanh layer 2, linear output]."""
    h1 = np.tanh(np.array([[x]]) @ W[0] + b[0])
    h2 = np.tanh(h1 @ W[1] + b[1])
    return [[round(float(x), 4)], r4(h1.ravel()), r4(h2.ravel()), r4((h2 @ W[2] + b[2]).ravel())]


def frame(epoch: int, loss: float, x: float, W: list[np.ndarray], b: list[np.ndarray]) -> dict:
    return {"epoch": epoch, "loss": round(float(loss), 5), "input": round(float(x), 4), "target": round(math.sin(x), 4),
            "W": [r4(w) for w in W], "b": [r4(v.ravel()) for v in b], "a": fire(W, b, x)}


def train(zero: bool) -> tuple[list[dict], list[tuple[int, float]], dict]:
    """The lesson's code, run for real (zero=True: the shortcut, every weight starts at 0)."""
    np.random.seed(0)
    shapes = {"W1": (1, 4), "W2": (4, 4), "W3": (4, 1)}
    W = [np.zeros(shapes[k]) if zero else np.random.randn(*shapes[k]) * SCALE[k] for k in ("W1", "W2", "W3")]
    b = [np.zeros((1, 4)), np.zeros((1, 4)), np.zeros((1, 1))]
    frames: list[dict] = []
    printed: list[tuple[int, float]] = []
    for epoch in range(EPOCHS):
        h1 = np.tanh(X @ W[0] + b[0])
        h2 = np.tanh(h1 @ W[1] + b[1])
        out = h2 @ W[2] + b[2]
        loss = np.mean((out - Y) ** 2)
        if epoch % SNAP == 0:  # the weights that made this epoch's loss
            frames.append(frame(epoch, loss, REST_X, W, b))
        if epoch % PRINT_EVERY == 0:
            printed.append((epoch, round(float(loss), 4)))  # what nn.py prints (loss {loss:.4f})
        d_out = 2 * (out - Y) / len(X)
        d_h2 = d_out @ W[2].T * (1 - h2 ** 2)
        d_h1 = d_h2 @ W[1].T * (1 - h1 ** 2)
        grads = [(X.T @ d_h1, d_h1.sum(0)), (h1.T @ d_h2, d_h2.sum(0)), (h2.T @ d_out, d_out.sum(0))]
        for k, (dW, db) in enumerate(grads):
            W[k] -= LR * dW
            b[k] -= LR * db
    out = np.tanh(np.tanh(X @ W[0] + b[0]) @ W[1] + b[1]) @ W[2] + b[2]
    frames.append(frame(EPOCHS, np.mean((out - Y) ** 2), REST_X, W, b))
    t = np.array(TEST_X).reshape(-1, 1)
    answers = (np.round(np.tanh(np.tanh(t @ W[0] + b[0]) @ W[1] + b[1]) @ W[2] + b[2], 1) + 0.0).ravel().tolist()
    return frames, printed, {"answers": answers, "loss": float(np.mean((out - Y) ** 2)),
                             "max_error": float(np.abs(out - Y).max())}


ZEROS, ZERO_PRINTS, _ = train(zero=True)
FIXED, FIXED_PRINTS, FIXED_END = train(zero=False)
assert abs(STUCK_LOSS - 0.49) < 1e-12, STUCK_LOSS
assert all(abs(v - STUCK_LOSS) < 1e-9 for _, v in ZERO_PRINTS), ZERO_PRINTS
assert all(f["a"][1] == [0.0] * 4 and f["a"][2] == [0.0] * 4 for f in ZEROS), "zeros: every hidden neuron is 0"
assert sorted(FIXED_PRINTS[-5:])[2][1] < LOSS_TARGET, FIXED_PRINTS  # the run check: median of the last 5 printed
assert FIXED_END["answers"] == [-1.0, 0.0, 1.0], FIXED_END


def forward_frames(f: dict) -> list[dict]:
    """The trained network answering every sample: f's weights, once per x."""
    W = [np.array(w) for w in f["W"]]
    b = [np.array(v) for v in f["b"]]
    return [{**f, "input": s[0], "target": round(math.sin(s[0]), 4), "a": fire(W, b, s[0])} for s in SAMPLES]


def net(mode: str, frames: list[dict], caption: str) -> dict:
    return {
        "kind": "network",
        "caption": caption,
        "data": {
            "layers": [1, 4, 4, 1], "activation": "tanh", "inputs": ["x"], "output": "ŷ",
            "labels": {"input": ["x"], "output": ["y"]}, "placement": "drawer",
            "derivatives": [], "residual": "",  # the contract's network fields (the classic view ignores them here)
            "mode": mode, "frames": frames, "samples": SAMPLES, "targets": TARGETS,
            "target": round(math.sin(REST_X), 4),  # the app's target while it tweens frames (it drops theirs)
        },
    }


# Per step: what the drawer's right-hand panel shows when the step starts (the engine redraws the training ones from
# the learner's own run: server/orchestrator/curated.py). nn4-gradients is the stuck-loss picture.
DIAGRAMS = {
    "nn1-network": net("forward", forward_frames(FIXED[-1]),
                       "What you're building: x goes in, y comes out. Brightness is a neuron's activation; blue weights "
                       "push up, brown push down."),
    "nn2-network": net("backward", FIXED[:1],
                       "Backprop: the output's error flows back along the same weights, and each weight gets its share."),
    "nn3-network": net("train", FIXED,
                       f"What your loop will do: every weight takes a small step downhill {EPOCHS:,} times, and y "
                       "settles on sin(x)."),
    "nn4-network": net("train", FIXED,
                       "Run it and the weights move while the loss falls. This redraws from your run."),
    "nn4-gradients": net("train", ZEROS,
                         "Your run: all eight hidden neurons are the same neuron. Same start, same update, so nothing "
                         "moves."),
    "nn5-network": net("train", FIXED,
                       "Your network training: the weights move while the loss falls, and y settles on sin(x)."),
    "nn6-network": net("forward", forward_frames(FIXED[-1]),
                       "Your trained network: x goes in, sin(x) comes out."),
}

# ---------------------------------------------------------------------------------------------------------------
# The lesson (the engine's step-graph format, same as demo/cache/lessons/text-43e26ca1d86c37ed.json).
# Checks: VS Code checks are graded on the editor's exact text (companion extension), else nn.py on disk; run steps
# pass on the run's real output (VS Code's terminal via the extension, Run it for me, or the screen).
# ---------------------------------------------------------------------------------------------------------------

METRIC = r"epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>[0-9Oo.eE+-]+)"  # O: OCR reads 0.0009 as O.0009 at times
# [-1.0, 0.0, 1.0] (or -0.0), tolerant of OCR spacing, a missing comma and an O read for a 0
SIN_OUT = r"\[\s*-\s*1\.[0O]\s*,?\s*-?\s*[0O]\.[0O]\s*,?\s*1\.[0O]\s*\]"
INIT_RX = r"W1\s*=\s*np\.[\s\S]*W2\s*=\s*np\.[\s\S]*W3\s*=\s*np\."
LOOP_RX = rf"for\s+epoch\s+in\s+range\(\s*{EPOCHS}\s*\)"
# The key math of each step, checked exactly (t6: step 2 passed with tanh's slope written 1 + h2 ** 2; the training run
# then stalled at loss 0.05 and the learner found out two steps later). Spacing-tolerant, in the forms the drawer's code
# uses (the learner pastes it): a @ W or a.dot(W); h ** 2, h * h or np.square(h).


def _mm(a: str, w: str) -> str:
    return rf"{a}\s*(?:@\s*{w}|\.dot\(\s*{w}\s*\))"


def _slope(h: str) -> str:
    """(1 - h ** 2): tanh's slope at h, with its parentheses (d_h2 @ W2.T * 1 - h1 ** 2 is another number)."""
    return rf"\(\s*1(?:\.0*)?\s*-\s*(?:{h}\s*\*\*\s*2(?:\.0*)?|{h}\s*\*\s*{h}|np\.square\(\s*{h}\s*\))\s*\)"


def _downhill(*names: str) -> str:
    """Every one of `names` steps downhill (p -= lr * dp, or p = p - lr * dp), in any order. Never += (uphill)."""
    return r"\A" + "".join(rf"(?=[\s\S]*\b{p}\s*(?:-=|=\s*{p}\s*-)\s*lr\s*\*\s*d{p}\b)" for p in names)


# forward: tanh on both hidden layers, a plain sum on the output (no tanh there, so it can answer any number)
FORWARD_RX = (rf"h1\s*=\s*np\.tanh\(\s*{_mm('X', 'W1')}\s*\+\s*b1\s*\)[\s\S]*"
              rf"h2\s*=\s*np\.tanh\(\s*{_mm('h1', 'W2')}\s*\+\s*b2\s*\)[\s\S]*"
              rf"return\s+h1\s*,\s*h2\s*,\s*{_mm('h2', 'W3')}\s*\+\s*b3\b")
# backward: the output's error (the slope of the mean squared error), then tanh's slope on each hidden layer
D_OUT_RX = r"d_out\s*=\s*2(?:\.0*)?\s*\*\s*\(\s*out\s*-\s*y\s*\)\s*/\s*(?:len\(\s*X\s*\)|X\.shape\[\s*0\s*\])"
SLOPE_RX = (rf"d_h2\s*=\s*{_mm('d_out', r'W3\.T')}\s*\*\s*{_slope('h2')}[\s\S]*"
            rf"d_h1\s*=\s*{_mm('d_h2', r'W2\.T')}\s*\*\s*{_slope('h1')}")
# the loop: every weight and bias downhill, and the printed loss is the mean squared error
UPDATE_RX = _downhill("W1", "b1", "W2", "b2", "W3", "b3")
MSE_RX = r"loss\s*=\s*np\.mean\(\s*\(\s*(?:out\s*-\s*y|y\s*-\s*out)\s*\)\s*\*\*\s*2\s*\)"
ANSWERS_RX = r"np\.round\(\s*out\s*,\s*1\s*\)"
WEIGHTS_RX = r"\(\s*[\"']W1[\"']\s*,\s*W1\s*\)[\s\S]*\(\s*[\"']W3[\"']\s*,\s*W3\s*\)"


def step(sid: str, index: int, **kw) -> dict:
    s = {"id": sid, "index": index, "file": "nn.py", "code": CODE[sid], "explanations": []}
    s.update(kw)
    return s


def code_target(sid: str, caption: str) -> list[dict]:
    return [{"app": "Code", "file": "nn.py", "match": ANCHOR[sid], "caption": caption}]


RUN_TARGET = [{"app": "Terminal", "file": "nn.py", "match": RUN, "caption": "Run it here"}]

STEPS = [
    step(
        "nn1", 1,
        title="Build the network",
        kind="code",
        what="The sine data, random weights and a forward pass",
        why="Every guess the network makes is this forward pass: x goes through two layers of tanh neurons, and the "
            "output neuron adds them up into y.",
        concepts=["p1", "p2", "p3"],
        action="In nn.py, paste this under # The network",
        instructions="Under # The network, add the data (y = sin(x)), the weights and the forward pass.",
        checks=[
            {"id": "nn1c1", "type": "screen_contains", "label": "The sine data is in nn.py", "app": "Code",
             "pattern": r"y\s*=\s*np\.sin\(\s*X\s*\)"},
            {"id": "nn1c2", "type": "screen_contains", "label": "W1, W2 and W3 are created", "app": "Code",
             "pattern": INIT_RX},
            {"id": "nn1c3", "type": "screen_contains", "label": "forward() is defined", "app": "Code",
             "pattern": r"def\s+forward\s*\(\s*X\s*\)"},
            {"id": "nn1c4", "type": "screen_contains", "label": "Hidden layers use tanh, the output doesn't",
             "app": "Code", "pattern": FORWARD_RX},
        ],
        precision_checks=[
            {"id": "nn1p1", "type": "file_contains", "label": "nn.py has the sine data", "file": "nn.py",
             "pattern": r"X\s*=\s*np\.linspace\([\s\S]*y\s*=\s*np\.sin\(\s*X\s*\)"},
            {"id": "nn1p2", "type": "file_contains", "label": "nn.py creates W1, W2 and W3", "file": "nn.py",
             "pattern": INIT_RX},
            {"id": "nn1p3", "type": "file_contains", "label": "nn.py defines forward with two tanh layers",
             "file": "nn.py",
             "pattern": r"def\s+forward\s*\(\s*X\s*\)\s*:[\s\S]*np\.tanh\([\s\S]*np\.tanh\([\s\S]*@\s*W3"},
            {"id": "nn1p4", "type": "file_contains", "label": "nn.py's hidden layers use tanh, its output doesn't",
             "file": "nn.py", "pattern": FORWARD_RX},
        ],
        targets=code_target("nn1", "Paste the network under this line"),
        hints=[
            "Copy the code from the drawer and paste it under # The network.",
            "forward returns three things: the two hidden layers h1 and h2, and the output.",
        ],
        common_mistakes=["Pasting above import numpy as np, so np isn't defined yet.",
                         "Losing the indentation inside def forward."],
        estMinutes=4,
    ),
    step(
        "nn2", 2,
        title="Backprop",
        kind="code",
        what="A gradient for every weight, with the chain rule",
        why="The chain rule sends the output's error back one layer at a time, so each weight learns its share of the "
            "blame.",
        concepts=["p4"],
        action="In nn.py, paste backward under # Backprop",
        instructions="Under # Backprop, add backward. It returns one gradient per weight and bias.",
        checks=[
            {"id": "nn2c1", "type": "screen_contains", "label": "backward() is defined", "app": "Code",
             "pattern": r"def\s+backward\s*\("},
            {"id": "nn2c2", "type": "screen_contains", "label": "The error flows back through W3 and W2", "app": "Code",
             "pattern": r"d_h2\s*=\s*d_out\s*@\s*W3\.T[\s\S]*d_h1\s*=\s*d_h2\s*@\s*W2\.T"},
            {"id": "nn2c3", "type": "screen_contains", "label": "The error starts as 2 * (out - y) / len(X)",
             "app": "Code", "pattern": D_OUT_RX},
            {"id": "nn2c4", "type": "screen_contains", "label": "Uses the tanh slope 1 - h² on both layers",
             "app": "Code", "pattern": SLOPE_RX},
        ],
        precision_checks=[
            {"id": "nn2p1", "type": "file_contains", "label": "nn.py defines backward", "file": "nn.py",
             "pattern": r"def\s+backward\s*\(\s*X\s*,\s*y\s*,\s*h1\s*,\s*h2\s*,\s*out\s*\)\s*:"},
            {"id": "nn2p2", "type": "file_contains", "label": "nn.py sends the error back through W3 and W2",
             "file": "nn.py", "pattern": r"d_h2\s*=\s*d_out\s*@\s*W3\.T[\s\S]*d_h1\s*=\s*d_h2\s*@\s*W2\.T"},
            {"id": "nn2p3", "type": "file_contains", "label": "nn.py's error starts as 2 * (out - y) / len(X)",
             "file": "nn.py", "pattern": D_OUT_RX},
            {"id": "nn2p4", "type": "file_contains", "label": "nn.py uses the tanh slope 1 - h² on both layers",
             "file": "nn.py", "pattern": SLOPE_RX},
        ],
        targets=code_target("nn2", "Paste backward under this line"),
        hints=[
            "Start at the output: d_out is how wrong it was. The output has no tanh, so there is no slope to multiply.",
            "d_h2 sends d_out back through W3, then multiplies by tanh's slope, 1 - h2 ** 2. d_h1 does the same "
            "through W2.",
        ],
        common_mistakes=["Writing W3 instead of W3.T, so the shapes don't line up.",
                         "Forgetting tanh's slope (1 - h ** 2) on a hidden layer."],
        estMinutes=3,
    ),
    step(
        "nn3", 3,
        title="Write the training loop",
        kind="code",
        what=f"A loop that steps every weight downhill {EPOCHS:,} times",
        why=f"Each step lowers the loss a little. The loop prints the loss every {PRINT_EVERY:,} epochs so you can "
            "watch it fall.",
        concepts=["p4"],
        action="In nn.py, paste the loop under # Training",
        instructions=f"Under # Training, add the training loop. It prints the loss every {PRINT_EVERY:,} epochs.",
        checks=[
            {"id": "nn3c1", "type": "screen_contains", "label": f"The loop runs {EPOCHS:,} epochs", "app": "Code",
             "pattern": LOOP_RX},
            {"id": "nn3c2", "type": "screen_contains", "label": "Every weight and bias steps downhill", "app": "Code",
             "pattern": UPDATE_RX},
            {"id": "nn3c4", "type": "screen_contains", "label": "The loss is the mean squared error", "app": "Code",
             "pattern": MSE_RX},
            {"id": "nn3c3", "type": "screen_contains", "label": "It prints the loss", "app": "Code",
             "pattern": r"print\(\s*f[\"']epoch"},
        ],
        precision_checks=[
            {"id": "nn3p1", "type": "file_contains", "label": "nn.py has the training loop", "file": "nn.py",
             "pattern": LOOP_RX},
            {"id": "nn3p2", "type": "file_contains", "label": "nn.py moves every weight and bias downhill",
             "file": "nn.py", "pattern": UPDATE_RX},
            {"id": "nn3p4", "type": "file_contains", "label": "nn.py's loss is the mean squared error", "file": "nn.py",
             "pattern": MSE_RX},
            {"id": "nn3p3", "type": "file_contains", "label": "nn.py prints the loss", "file": "nn.py",
             "pattern": r"print\(\s*f[\"']epoch"},
        ],
        targets=code_target("nn3", "Paste the loop under this line"),
        hints=[
            "Copy the loop from the drawer and paste it under # Training, with its indentation.",
            "Inside the loop: forward, backward, then W -= lr * dW for all three weights and all three biases.",
        ],
        common_mistakes=["Losing the indentation under for epoch.", "Updating only the weights, not the biases."],
        estMinutes=3,
    ),
    step(
        "nn4", 4,
        title="Train it",
        kind="run",
        what="Run it and watch the loss fall",
        why="Each printed line is one checkpoint. If the loss stops falling, the network has stopped learning.",
        concepts=["p4"],
        instructions="Run nn.py in VS Code's terminal and watch the loss.",
        run_command=RUN,
        checks=[
            {"id": "nn4c1", "type": "metric_threshold", "label": f"Loss falls below {LOSS_TARGET:g}", "metric": "loss",
             "op": "<", "value": LOSS_TARGET, "metric_pattern": METRIC, "by_step": BY_EPOCH},
        ],
        precision_checks=[
            {"id": "nn4p1", "type": "file_contains", "label": f"The saved nn.py runs {EPOCHS:,} epochs",
             "file": "nn.py", "pattern": LOOP_RX},
            {"id": "nn4p2", "type": "metric_threshold", "label": f"Your run's loss falls below {LOSS_TARGET:g}",
             "metric": "loss", "op": "<", "value": LOSS_TARGET, "metric_pattern": METRIC, "by_step": BY_EPOCH},
        ],
        targets=RUN_TARGET,
        hints=[
            "Press Run it for me, or run the command in VS Code's terminal (Terminal > New Terminal).",
            f"Watch the epoch lines: the loss should fall below {LOSS_TARGET:g} by epoch {BY_EPOCH}.",
        ],
        common_mistakes=["Starting W1, W2 and W3 at zero: every hidden neuron stays identical and the loss never "
                         "moves.",
                         "Running before saving, so the old file runs."],
        estMinutes=1,
    ),
    step(
        "nn5", 5,
        title="Test it",
        kind="code",
        what="Print its answers and the weights it learned",
        why="sin(-π/2) = -1, sin(0) = 0 and sin(π/2) = 1, so you can check its answers. The weights are what it learned.",
        concepts=["p1"],
        action="In nn.py, paste this under # Test it",
        instructions="Under # Test it, print its answers for -π/2, 0 and π/2, and the weights.",
        checks=[
            {"id": "nn5c1", "type": "screen_contains", "label": "It prints its answers", "app": "Code",
             "pattern": ANSWERS_RX},
            {"id": "nn5c2", "type": "screen_contains", "label": "It prints W1 to b3", "app": "Code",
             "pattern": WEIGHTS_RX},
        ],
        precision_checks=[
            {"id": "nn5p1", "type": "file_contains", "label": "nn.py prints its answers", "file": "nn.py",
             "pattern": ANSWERS_RX},
            {"id": "nn5p2", "type": "file_contains", "label": "nn.py prints the weights", "file": "nn.py",
             "pattern": WEIGHTS_RX},
        ],
        targets=code_target("nn5", "Paste the test under this line"),
        hints=["forward gives h1, h2 and out; out holds its three answers.",
               "np.round(out, 1) rounds them to one decimal, so a good network prints -1.0, 0.0 and 1.0."],
        common_mistakes=["Printing h2 instead of out."],
        estMinutes=2,
    ),
    step(
        "nn6", 6,
        title="See what it learned",
        kind="run",
        what="Run it: it answers -1, 0, 1",
        why="Your network learned the sine curve from 50 examples. The panel on the right is drawn from the weights it "
            "printed.",
        concepts=["p1"],
        instructions="Run nn.py again and read its answers.",
        run_command=RUN,
        expected_output="[-1.0, 0.0, 1.0]",
        checks=[
            {"id": "nn6c1", "type": "screen_contains", "label": "It answers -1, 0, 1", "app": "Terminal",
             "pattern": SIN_OUT},
        ],
        precision_checks=[
            {"id": "nn6p1", "type": "file_contains", "label": "The saved nn.py prints its answers", "file": "nn.py",
             "pattern": ANSWERS_RX},
            {"id": "nn6p2", "type": "output_contains", "label": "Your run prints [-1.0, 0.0, 1.0]", "pattern": SIN_OUT},
        ],
        targets=RUN_TARGET,
        hints=["Press Run it for me, or run the command again in VS Code's terminal.",
               "The first line after the losses is its answer for -π/2, 0 and π/2."],
        common_mistakes=["Reading the loss lines instead of the [-1.0, 0.0, 1.0] line under them."],
        estMinutes=1,
    ),
]

LESSON = {
    "lesson": {
        "id": "lesson-nn-from-scratch",
        "title": "A neural net from scratch",
        "goal": "build a neural network from scratch",  # the completion title: "You built a neural network"
        "workdir": "demo/nn-lab",
        "libraries": {"numpy": "2.x"},
        "mode": "lesson",
        "complete": True,
        "builtBy": "claude",
        "curated": "nn-from-scratch",
        "overview": ("We'll build a neural network with nothing but NumPy and teach it to draw a curve: y = sin(x) for x "
                     "from -π to π. One input (x), two hidden layers of 4 neurons, one output (y). First the network "
                     "and its forward pass, then backprop, then a training loop, and last a test that prints -1, 0, 1 "
                     "for -π/2, 0, π/2."),
        "primer": [
            {"id": "p1", "title": "A neuron holds a number",
             "body": "The input neuron holds x. Each hidden neuron holds a number between -1 and 1, its activation, "
                     "computed from the layer before it. The output neuron holds the network's answer, y."},
            {"id": "p2", "title": "Weights and a bias",
             "body": "Each connection multiplies the signal by a weight: positive pushes the next neuron up, negative "
                     "pushes it down. The bias shifts where the neuron switches on.",
             "code": "z = h1 * w1 + h2 * w2 + h3 * w3 + h4 * w4 + b"},
            {"id": "p3", "title": "tanh bends",
             "body": "tanh squishes any total into -1..1. Stacking these bends is what lets the network draw a curve; "
                     "the output skips tanh, so it can answer any number.",
             "code": "np.tanh(z)"},
            {"id": "p4", "title": "Learning goes downhill",
             "body": "The loss says how wrong the outputs are. Backprop finds which way each weight should move to "
                     "lower it, and each training step moves it a little that way.",
             "code": "W -= lr * dW"},
        ],
        "build": {"summary": "A 1-4-4-1 neural network in NumPy that learns y = sin(x).",
                  "outcome": f"Run it and the loss falls below {LOSS_TARGET:g}; it prints [-1.0, 0.0, 1.0] for "
                             "x = -π/2, 0, π/2.",
                  "estMinutes": sum(s["estMinutes"] for s in STEPS)},
        "flow": [
            {"label": "Input", "detail": "x", "stepIndex": 1},
            {"label": "Hidden layer 1", "detail": "tanh(X·W1 + b1)", "stepIndex": 1},
            {"label": "Hidden layer 2", "detail": "tanh(h1·W2 + b2)", "stepIndex": 1},
            {"label": "Output", "detail": "h2·W3 + b3", "stepIndex": 1},
            {"label": "Backprop", "detail": "chain rule", "stepIndex": 2},
            {"label": "Gradient step", "detail": "W -= lr·dW", "stepIndex": 3},
        ],
        "prerequisites": [
            {"id": "numpy-arrays", "title": "NumPy arrays", "why": "X, y and every weight are arrays.", "status": "unknown"},
            {"id": "matrix-multiply", "title": "Matrix multiply", "why": "X @ W1 runs every hidden neuron at once.", "status": "unknown"},
            {"id": "derivatives", "title": "Derivatives", "why": "Backprop multiplies slopes along the network.", "status": "unknown"},
        ],
        "learnFirst": [
            {"title": "NumPy arrays", "minutes": 5, "kind": "read", "covers": "numpy-arrays"},
            {"title": "Matrix multiplication", "minutes": 6, "kind": "interactive", "covers": "matrix-multiply"},
        ],
    },
    "sources": [],
    "steps": STEPS,
    "build": {"mode": "lesson", "note": "Written by hand (scripts/make_nn_demo.py), no model call. Served instantly for "
                                         "neural-network goals by server/orchestrator/curated.py."},
}

# ---------------------------------------------------------------------------------------------------------------
# Coaching cards (instant, no network). LIVE uses the hints and Explain; the off-track coach stays live Claude.
# DEMO also serves the coach card and the Ask answers from here.
# ---------------------------------------------------------------------------------------------------------------

STUCK_HINTS = [
    "Look at how W1, W2 and W3 start. What does every hidden neuron compute when all its weights are 0?",
    f"Start them random, like the lesson: W1 = {INIT['W1']}, W2 = {INIT['W2']}, W3 = {INIT['W3']}. "
    "Save, then run again.",
]

COACH = {
    "nn4": {
        "stepId": "nn4",
        "severity": "fail",
        "title": f"Loss is stuck at {STUCK_LOSS:.2f}",
        "body": "All eight hidden neurons start with the same weights, so they get the same update and stay copies. "
                "With zeros nothing moves at all: the network answers 0 for every x. Start W1, W2 and W3 random.",
        "guidingQuestion": "If every hidden neuron starts the same, can they ever become different?",
        "citation": {"label": "Goodfellow et al. 2016, §8.4",
                     "url": "https://www.deeplearningbook.org/contents/optimization.html"},
        "actions": ["explain", "hint", "show_me"],
    }
}

FIRST, LAST = FIXED_PRINTS[0][1], FIXED_PRINTS[-1][1]

EXPLAIN = {
    "nn1": ("What a neuron does", "It adds its inputs, each times a weight, plus a bias, then tanh squishes the total "
                                  "into -1..1. That number is how lit up it is. The output neuron skips tanh, so it can "
                                  "answer any number."),
    "nn2": ("How backprop assigns blame", "Start at the output: how wrong was it? Each weight into it is blamed by how "
                                          "much it contributed. Then do the same one layer back, and once more."),
    "nn3": ("One pass of the loop", f"forward makes a guess for all {N_POINTS} points, backward says which way each "
                                    f"weight should move, and each weight moves a little that way (lr sets how far). "
                                    f"{EPOCHS:,} times."),
    "nn4": ("Reading the loss", f"The loss is the mean squared error over the {N_POINTS} points. Answering 0 for every "
                                f"x scores {STUCK_LOSS:.2f}; a network that has learned the curve goes below "
                                f"{LOSS_TARGET:g}."),
    "nn4-stuck": ("Why zeros can't learn", "With every weight at 0, all eight hidden neurons output tanh(0) = 0, so the "
                                           "network answers 0 for every x. Every weight's gradient is exactly zero, "
                                           "so they stay copies and nothing moves."),
    "nn5": ("Reading the output", "sin(-π/2) = -1, sin(0) = 0 and sin(π/2) = 1. Rounded to one decimal, a network that "
                                  "learned the curve prints exactly those."),
    "nn6": ("What the weights mean", "Each first-layer neuron is tanh(w·x), an S-curve through 0: steep when its "
                                     "weight is big, gentle when it's small. The second layer mixes those S-curves, "
                                     "and the output adds them up into the sine wave. The biases stay at 0: sin is "
                                     "symmetric (sin(-x) = -sin(x)), and so is a network with no biases."),
}

ASK = {
    "nn1": ("Why no tanh on the output?", "tanh keeps a neuron between -1 and 1. The hidden layers need that bend; the "
                                          "output just adds them up, so it can reach any value. Its weights start "
                                          "small (* 0.1), so its first guesses are near 0."),
    "nn2": ("Why 1 - h2 ** 2?", "It's tanh's slope. The chain rule multiplies it in wherever the signal went through "
                                "a tanh."),
    "nn3": (f"Why lr = {LR:g}?", "Small enough that each step doesn't overshoot, big enough to finish in a second. "
                                 "Real networks tune it the same way: try a few and watch the loss."),
    "nn4": (f"Why {EPOCHS:,} epochs?", f"Plain gradient descent takes small steps. From this start the loss goes from "
                                       f"{FIRST:.4f} to {LAST:.4f} by epoch {FIXED_PRINTS[-1][0]:,}, in about a second."),
    "nn5": ("Why round the weights?", "Three decimals are enough to read them, and the drawing on the right uses the "
                                      "same numbers."),
    "nn6": ("What next?", "Swap np.sin for another curve, like np.cos, and train again: the same network and the same "
                          "four pieces learn it."),
}


def write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def card(sid: str, kind: str, title: str, body: str) -> dict:
    return {"stepId": sid, "kind": kind, "title": title, "body": body}


def main() -> None:
    for sub in ("cards", "diagrams", "coach"):  # no stale files from an earlier step layout
        for old in (CACHE / sub).glob("nn[0-9]*.json"):
            old.unlink()
    LAB.mkdir(parents=True, exist_ok=True)
    (ROOT / "demo" / "nn-start.py").write_text(STARTER, encoding="utf-8")
    (LAB / "nn.py").write_text(STARTER, encoding="utf-8")
    write(CACHE / "lessons" / "text-nn-from-scratch.json", LESSON)
    for sid, c in COACH.items():
        write(CACHE / "coach" / f"{sid}.json", c)
    for s in STEPS:
        sid = s["id"]
        write(CACHE / "cards" / f"{sid}-explain.json", card(sid, "explain", *EXPLAIN[sid]))
        write(CACHE / "cards" / f"{sid}-answer.json", card(sid, "answer", *ASK[sid]))
        for level, text in enumerate(s["hints"]):
            write(CACHE / "cards" / f"{sid}-hint{level}.json", card(sid, "hint", f"Hint {level + 1} of {len(s['hints'])}", text))
    write(CACHE / "cards" / "nn4-stuck-explain.json", card("nn4", "explain", *EXPLAIN["nn4-stuck"]))
    for level, text in enumerate(STUCK_HINTS):
        write(CACHE / "cards" / f"nn4-stuck-hint{level}.json", card("nn4", "hint", f"Hint {level + 1} of {len(STUCK_HINTS)}", text))
    for name, d in DIAGRAMS.items():
        write(CACHE / "diagrams" / f"{name}.json", d)
    print(f"zeros: loss {[v for _, v in ZERO_PRINTS]} · lesson code: loss {[v for _, v in FIXED_PRINTS]}")
    print(f"lesson code: final loss {FIXED_END['loss']:.6f}, max error {FIXED_END['max_error']:.3f}, "
          f"answers {FIXED_END['answers']}")
    print(f"wrote {LAB.relative_to(ROOT)}/ and demo/cache/(lessons|coach|cards|diagrams) for {len(STEPS)} steps")


if __name__ == "__main__":
    main()
