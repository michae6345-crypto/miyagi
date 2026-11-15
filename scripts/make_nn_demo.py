"""Builds the curated "build a neural network" lesson (LIVE and DEMO=1), with zero API calls.

    python scripts/make_nn_demo.py          # needs numpy; rewrites every file below
    scripts/miyagi-nn-demo.sh               # DEMO=1 engine on it (offline coach); LIVE needs nothing (see below)

LIVE: "Just teach me" with a neural-network goal ("build a neural network", "neural net from scratch", ...) serves this
lesson instantly instead of building one (server/orchestrator/curated.py; MIYAGI_CURATED=0 turns that off). The coach
stays live; hints, the Explain button and every network diagram come from the files below.

What it writes (all data, no engine code):
  demo/nn-lab/nn.py, demo/nn-start.py       the learner's file and its clean copy (four section comments)
  demo/cache/lessons/text-nn-from-scratch.json
                                            the 6-step lesson (mode "lesson"): typing steps and run steps alternate,
                                            the way the engine's lesson mode expects (a run step's snippet is its command)
  demo/cache/coach/nn4.json                 DEMO only: the off-track card when training stays flat (zero weights)
  demo/cache/cards/nn<k>-explain|answer|hint<n>.json, nn4-stuck-explain|hint<n>.json
                                            Explain / Ask (DEMO) / Hint for each step; nn4-stuck-*: the ladder once the
                                            loss is stuck at 0.25
  demo/cache/diagrams/nn<k>-network.json, nn4-gradients.json
                                            live networks (the app's NeuralNet view): neurons lit by activation,
                                            weights blue/brown, signals firing. The engine pushes them to the drawer's
                                            right-hand panel and redraws the training ones from the learner's own run.

The story (DEMO's presenter, or any learner who takes the shortcut): step 1 builds the network with W1 and W2 = zeros.
Every check passes. Step 4 trains: the loss sits at exactly 0.2500 for all 5,000 epochs, because every hidden neuron
computes the same thing and gets the same update. miyagi goes off track, the diagram shows four identical neurons, the
hint ladder says start them random; the learner fixes it, reruns, and the loss falls to 0.0009.
Every number comes from running the code below.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "demo" / "nn-lab"
CACHE = ROOT / "demo" / "cache"
RUN = "python3 nn.py"

# ---------------------------------------------------------------------------------------------------------------
# The code, step by step (what the drawer shows and Copy copies). The learner pastes it under each section comment.
# The comments carry no numbers: the lesson has 6 steps (4 to type, 2 to run) but the file has 4 sections.
# ---------------------------------------------------------------------------------------------------------------

STARTER = """# A neural net from scratch: 2 inputs, 4 hidden neurons, 1 output. It learns XOR.
import numpy as np

# The network


# Backprop


# Training


# Test it
"""

ANCHOR = {"nn1": "# The network", "nn2": "# Backprop", "nn3": "# Training", "nn5": "# Test it"}

CODE = {
    "nn1": """X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]])
y = np.array([[0], [1], [1], [0]])

np.random.seed(0)
W1 = np.random.randn(2, 4) * 0.5
b1 = np.zeros((1, 4))
W2 = np.random.randn(4, 1) * 0.5
b2 = np.zeros((1, 1))

def sigmoid(z):
    return 1 / (1 + np.exp(-z))

def forward(X):
    h = sigmoid(X @ W1 + b1)
    return h, sigmoid(h @ W2 + b2)""",
    "nn2": """def backward(X, y, h, out):
    d_out = 2 * (out - y) / len(X) * out * (1 - out)
    d_h = d_out @ W2.T * h * (1 - h)
    return h.T @ d_out, d_out.sum(0), X.T @ d_h, d_h.sum(0)""",
    "nn3": """lr = 1.0
for epoch in range(5000):
    h, out = forward(X)
    dW2, db2, dW1, db1 = backward(X, y, h, out)
    W2 -= lr * dW2
    b2 -= lr * db2
    W1 -= lr * dW1
    b1 -= lr * db1
    loss = np.mean((out - y) ** 2)
    if epoch % 1000 == 0:
        print(f"epoch {epoch:4d}  loss {loss:.4f}")""",
    "nn4": RUN,
    "nn5": """h, out = forward(X)
print((out > 0.5).astype(int).ravel())
for name, w in (("W1", W1), ("b1", b1), ("W2", W2), ("b2", b2)):
    print(name, np.round(w, 3).tolist())""",
    "nn6": RUN,
}

# ---------------------------------------------------------------------------------------------------------------
# Real runs: the weights every 250 epochs (the live diagrams), for the shortcut (zeros) and the lesson's code.
# ---------------------------------------------------------------------------------------------------------------

X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]])
Y = np.array([[0], [1], [1], [0]])


def train(zero: bool) -> tuple[list[dict], list[float], dict]:
    np.random.seed(0)
    W1 = np.zeros((2, 4)) if zero else np.random.randn(2, 4) * 0.5
    b1 = np.zeros((1, 4))
    W2 = np.zeros((4, 1)) if zero else np.random.randn(4, 1) * 0.5
    b2 = np.zeros((1, 1))
    sig = lambda z: 1 / (1 + np.exp(-z))  # noqa: E731
    frames: list[dict] = []

    def snap(epoch: int, loss: float) -> None:
        r = lambda a: [round(float(v), 4) for v in np.asarray(a).ravel()]  # noqa: E731
        frames.append({"epoch": epoch, "loss": round(float(loss), 5), "W": [r(W1), r(W2)], "b": [r(b1), r(b2)]})

    printed = []
    for epoch in range(5000):
        h = sig(X @ W1 + b1)
        out = sig(h @ W2 + b2)
        d_out = 2 * (out - Y) / len(X) * out * (1 - out)
        d_h = d_out @ W2.T * h * (1 - h)
        W2 -= h.T @ d_out
        b2 -= d_out.sum(0)
        W1 -= X.T @ d_h
        b1 -= d_h.sum(0)
        loss = np.mean((out - Y) ** 2)
        if epoch % 250 == 0:
            snap(epoch, loss)
        if epoch % 1000 == 0:
            printed.append(float(loss))
    out = sig(sig(X @ W1 + b1) @ W2 + b2)
    snap(5000, np.mean((out - Y) ** 2))
    preds = (out > 0.5).astype(int).ravel().tolist()
    return frames, printed, {"predictions": preds}


ZEROS, ZERO_PRINTS, _ = train(zero=True)
FIXED, FIXED_PRINTS, FIXED_END = train(zero=False)
assert all(abs(v - 0.25) < 1e-9 for v in ZERO_PRINTS), ZERO_PRINTS
assert FIXED_PRINTS[-1] < 0.01, FIXED_PRINTS
assert FIXED_END["predictions"] == [0, 1, 1, 0], FIXED_END


def net(mode: str, frames: list[dict], caption: str) -> dict:
    return {
        "kind": "network",
        "caption": caption,
        "data": {
            "layers": [2, 4, 1], "activation": "sigmoid", "inputs": ["x₁", "x₂"], "output": "ŷ",
            "derivatives": [], "residual": "",  # the contract's network fields (the classic view ignores them here)
            "mode": mode, "frames": frames, "samples": X.tolist(), "targets": Y.ravel().tolist(),
        },
    }


# Per step: what the drawer's right-hand panel shows when the step starts (the engine redraws the training ones from
# the learner's own run: server/orchestrator/curated.py). nn4-gradients is the stuck-loss picture.
DIAGRAMS = {
    "nn1-network": net("forward", FIXED[-1:],
                       "What you're building. Brightness is a neuron's activation; blue weights push up, brown push down."),
    "nn2-network": net("backward", FIXED[:1],
                       "Backprop: the output's error flows back along the same weights, and each weight gets its share."),
    "nn3-network": net("train", FIXED,
                       "What your loop will do: every weight takes a small step downhill 5,000 times, and ŷ settles on 0 1 1 0."),
    "nn4-network": net("train", FIXED,
                       "Run it and the weights move while the loss falls. This redraws from your run."),
    "nn4-gradients": net("train", ZEROS,
                         "Your run: all four hidden neurons are the same neuron. Same start, same update, so nothing moves."),
    "nn5-network": net("train", FIXED,
                       "Your network training: the weights move while the loss falls, and ŷ settles on 0 1 1 0."),
    "nn6-network": net("forward", FIXED[-1:],
                       "Your trained network answering 00, 01, 10 and 11."),
}

# ---------------------------------------------------------------------------------------------------------------
# The lesson (the engine's step-graph format, same as demo/cache/lessons/text-43e26ca1d86c37ed.json).
# Checks: VS Code checks are graded on the editor's exact text (companion extension), else nn.py on disk; run steps
# pass on the run's real output (VS Code's terminal via the extension, Run it for me, or the screen).
# ---------------------------------------------------------------------------------------------------------------

METRIC = r"epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>[0-9Oo.eE+-]+)"  # O: OCR reads 0.0009 as O.0009 at times
XOR_OUT = r"\[\s*0\s*,?\s*1\s*,?\s*1\s*,?\s*0\s*\]"  # [0 1 1 0], tolerant of OCR spacing ("[0 11 0]") and a list


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
        what="The XOR data, random weights and a forward pass",
        why="Every guess the network makes is this forward pass: weighted sums squished by sigmoid, one layer at a time.",
        concepts=["p1", "p2", "p3"],
        action="In nn.py, paste this under # The network",
        instructions="Under # The network, add the XOR data, the weights and the forward pass.",
        checks=[
            {"id": "nn1c1", "type": "screen_contains", "label": "The XOR data is in nn.py", "app": "Code",
             "pattern": r"y\s*=\s*np\.array\(\s*\[\s*\[\s*0\s*\]\s*,\s*\[\s*1\s*\]"},
            {"id": "nn1c2", "type": "screen_contains", "label": "W1 and W2 are created", "app": "Code",
             "pattern": r"W1\s*=\s*np\.[\s\S]*W2\s*=\s*np\."},
            {"id": "nn1c3", "type": "screen_contains", "label": "forward() is defined", "app": "Code",
             "pattern": r"def\s+forward\s*\(\s*X\s*\)"},
        ],
        precision_checks=[
            {"id": "nn1p1", "type": "file_contains", "label": "nn.py has the XOR data", "file": "nn.py",
             "pattern": r"y\s*=\s*np\.array\(\s*\[\s*\[\s*0\s*\]\s*,\s*\[\s*1\s*\]"},
            {"id": "nn1p2", "type": "file_contains", "label": "nn.py creates W1 and W2", "file": "nn.py",
             "pattern": r"W1\s*=\s*np\.[\s\S]*W2\s*=\s*np\."},
            {"id": "nn1p3", "type": "file_contains", "label": "nn.py defines sigmoid and forward", "file": "nn.py",
             "pattern": r"1\s*/\s*\(\s*1\s*\+\s*np\.exp\(\s*-\s*z\s*\)\s*\)[\s\S]*def\s+forward\s*\(\s*X\s*\)\s*:"},
        ],
        targets=code_target("nn1", "Paste the network under this line"),
        hints=[
            "Copy the code from the drawer and paste it under # The network.",
            "forward returns two things: the hidden layer h and the output.",
        ],
        common_mistakes=["Pasting above import numpy as np, so np isn't defined yet.", "Losing the indentation inside def forward."],
        estMinutes=4,
    ),
    step(
        "nn2", 2,
        title="Backprop",
        kind="code",
        what="A gradient for every weight, with the chain rule",
        why="The chain rule sends the output's error back one layer at a time, so each weight learns its share of the blame.",
        concepts=["p4"],
        action="In nn.py, paste backward under # Backprop",
        instructions="Under # Backprop, add backward. It returns one gradient per weight.",
        checks=[
            {"id": "nn2c1", "type": "screen_contains", "label": "backward() is defined", "app": "Code",
             "pattern": r"def\s+backward\s*\("},
            {"id": "nn2c2", "type": "screen_contains", "label": "The error flows back through W2", "app": "Code",
             "pattern": r"d_h\s*=\s*d_out\s*@\s*W2\.T"},
        ],
        precision_checks=[
            {"id": "nn2p1", "type": "file_contains", "label": "nn.py defines backward", "file": "nn.py",
             "pattern": r"def\s+backward\s*\(\s*X\s*,\s*y\s*,\s*h\s*,\s*out\s*\)\s*:"},
            {"id": "nn2p2", "type": "file_contains", "label": "nn.py sends the error back through W2", "file": "nn.py",
             "pattern": r"d_h\s*=\s*d_out\s*@\s*W2\.T"},
        ],
        targets=code_target("nn2", "Paste backward under this line"),
        hints=[
            "Start at the output: d_out is the error times sigmoid's slope, out * (1 - out).",
            "d_h sends d_out back through W2, then multiplies by the hidden layer's slope.",
        ],
        common_mistakes=["Writing W2 instead of W2.T, so the shapes don't line up.", "Forgetting the hidden slope h * (1 - h)."],
        estMinutes=3,
    ),
    step(
        "nn3", 3,
        title="Write the training loop",
        kind="code",
        what="A loop that steps every weight downhill 5,000 times",
        why="Each step lowers the loss a little. The loop prints the loss every 1,000 epochs so you can watch it fall.",
        concepts=["p4"],
        action="In nn.py, paste the loop under # Training",
        instructions="Under # Training, add the training loop. It prints the loss every 1,000 epochs.",
        checks=[
            {"id": "nn3c1", "type": "screen_contains", "label": "The loop runs 5,000 epochs", "app": "Code",
             "pattern": r"for\s+epoch\s+in\s+range\(\s*5000\s*\)"},
            {"id": "nn3c2", "type": "screen_contains", "label": "Every weight steps downhill", "app": "Code",
             "pattern": r"W2\s*-=\s*lr\s*\*\s*dW2[\s\S]*W1\s*-=\s*lr\s*\*\s*dW1"},
            {"id": "nn3c3", "type": "screen_contains", "label": "It prints the loss", "app": "Code",
             "pattern": r"print\(\s*f[\"']epoch"},
        ],
        precision_checks=[
            {"id": "nn3p1", "type": "file_contains", "label": "nn.py has the training loop", "file": "nn.py",
             "pattern": r"for\s+epoch\s+in\s+range\(\s*5000\s*\)"},
            {"id": "nn3p2", "type": "file_contains", "label": "nn.py updates W1 and W2", "file": "nn.py",
             "pattern": r"W2\s*-=\s*lr\s*\*\s*dW2[\s\S]*W1\s*-=\s*lr\s*\*\s*dW1"},
            {"id": "nn3p3", "type": "file_contains", "label": "nn.py prints the loss", "file": "nn.py",
             "pattern": r"print\(\s*f[\"']epoch"},
        ],
        targets=code_target("nn3", "Paste the loop under this line"),
        hints=[
            "Copy the loop from the drawer and paste it under # Training, with its indentation.",
            "Inside the loop: forward, backward, then W -= lr * dW for all four weights.",
        ],
        common_mistakes=["Losing the indentation under for epoch.", "Updating only W1 and W2, not the biases."],
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
            {"id": "nn4c1", "type": "metric_threshold", "label": "Loss falls below 0.01", "metric": "loss",
             "op": "<", "value": 0.01, "metric_pattern": METRIC, "by_step": 4000},
        ],
        precision_checks=[
            {"id": "nn4p1", "type": "file_contains", "label": "The saved nn.py runs 5,000 epochs", "file": "nn.py",
             "pattern": r"for\s+epoch\s+in\s+range\(\s*5000\s*\)"},
            {"id": "nn4p2", "type": "metric_threshold", "label": "Your run's loss falls below 0.01", "metric": "loss",
             "op": "<", "value": 0.01, "metric_pattern": METRIC, "by_step": 4000},
        ],
        targets=RUN_TARGET,
        hints=[
            "Press Run it for me, or run the command in VS Code's terminal (Terminal > New Terminal).",
            "Watch the epoch lines: the loss should fall below 0.01 by epoch 4000.",
        ],
        common_mistakes=["Starting W1 and W2 at zero: every hidden neuron stays identical and the loss never moves.",
                         "Running before saving, so the old file runs."],
        estMinutes=1,
    ),
    step(
        "nn5", 5,
        title="Test it",
        kind="code",
        what="Print its answers and the weights it learned",
        why="Outputs above 0.5 count as 1, so you can check its answers against XOR. The weights are what it learned.",
        concepts=["p1"],
        action="In nn.py, paste this under # Test it",
        instructions="Under # Test it, print the predictions and the weights.",
        checks=[
            {"id": "nn5c1", "type": "screen_contains", "label": "It prints the predictions", "app": "Code",
             "pattern": r"\(\s*out\s*>\s*0\.5\s*\)\.astype\(\s*int\s*\)"},
            {"id": "nn5c2", "type": "screen_contains", "label": "It prints W1, b1, W2 and b2", "app": "Code",
             "pattern": r"\(\s*[\"']W1[\"']\s*,\s*W1\s*\)"},
        ],
        precision_checks=[
            {"id": "nn5p1", "type": "file_contains", "label": "nn.py prints the predictions", "file": "nn.py",
             "pattern": r"\(\s*out\s*>\s*0\.5\s*\)\.astype\(\s*int\s*\)"},
            {"id": "nn5p2", "type": "file_contains", "label": "nn.py prints the weights", "file": "nn.py",
             "pattern": r"\(\s*[\"']W1[\"']\s*,\s*W1\s*\)"},
        ],
        targets=code_target("nn5", "Paste the test under this line"),
        hints=["forward(X) gives h and out; out holds the four answers.",
               "Compare with 0.5 and turn True/False into 1/0 with .astype(int)."],
        common_mistakes=["Printing h instead of out."],
        estMinutes=2,
    ),
    step(
        "nn6", 6,
        title="See what it learned",
        kind="run",
        what="Run it: it answers 0 1 1 0",
        why="Your network learned XOR from four examples. The panel on the right is drawn from the weights it printed.",
        concepts=["p1"],
        instructions="Run nn.py again and read its answers.",
        run_command=RUN,
        expected_output="[0 1 1 0]",
        checks=[
            {"id": "nn6c1", "type": "screen_contains", "label": "It answers 0 1 1 0", "app": "Terminal", "pattern": XOR_OUT},
        ],
        precision_checks=[
            {"id": "nn6p1", "type": "file_contains", "label": "The saved nn.py prints its answers", "file": "nn.py",
             "pattern": r"\(\s*out\s*>\s*0\.5\s*\)\.astype\(\s*int\s*\)"},
            {"id": "nn6p2", "type": "output_contains", "label": "Your run prints [0 1 1 0]", "pattern": XOR_OUT},
        ],
        targets=RUN_TARGET,
        hints=["Press Run it for me, or run the command again in VS Code's terminal.",
               "The first line after the losses is its answer for 00, 01, 10 and 11."],
        common_mistakes=["Reading the loss lines instead of the [0 1 1 0] line under them."],
        estMinutes=1,
    ),
]

LESSON = {
    "lesson": {
        "id": "lesson-nn-from-scratch",
        "title": "A neural net from scratch",
        "goal": "build a neural net from scratch",
        "workdir": "demo/nn-lab",
        "libraries": {"numpy": "2.x"},
        "mode": "lesson",
        "complete": True,
        "builtBy": "claude",
        "curated": "nn-from-scratch",
        "overview": ("We'll build a neural network with nothing but NumPy and teach it XOR: output 1 when exactly one input "
                     "is 1. First the network and its forward pass, then backprop, then a training loop, and last a test "
                     "that prints 0 1 1 0."),
        "primer": [
            {"id": "p1", "title": "A neuron holds a number",
             "body": "Each neuron holds a number between 0 and 1, its activation. The inputs are the data; every other "
                     "neuron computes its number from the layer before it."},
            {"id": "p2", "title": "Weights and a bias",
             "body": "Each connection multiplies the signal by a weight: positive pushes the next neuron up, negative "
                     "pushes it down. The bias shifts how easily the neuron lights up.",
             "code": "z = x1 * w1 + x2 * w2 + b"},
            {"id": "p3", "title": "Sigmoid squishes",
             "body": "Sigmoid turns any total into a number between 0 and 1, so a neuron's output reads like how active it is.",
             "code": "1 / (1 + np.exp(-z))"},
            {"id": "p4", "title": "Learning goes downhill",
             "body": "The loss says how wrong the outputs are. Backprop finds which way each weight should move to "
                     "lower it, and each training step moves it a little that way.",
             "code": "W -= lr * dW"},
        ],
        "build": {"summary": "A 2-4-1 neural network in NumPy that learns XOR.",
                  "outcome": "Run it and the loss falls below 0.001; it prints [0 1 1 0] for the four inputs.",
                  "estMinutes": sum(s["estMinutes"] for s in STEPS)},
        "flow": [
            {"label": "Inputs", "detail": "x₁, x₂", "stepIndex": 1},
            {"label": "Hidden layer", "detail": "σ(X·W1 + b1)", "stepIndex": 1},
            {"label": "Output", "detail": "σ(h·W2 + b2)", "stepIndex": 1},
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
    "Look at how W1 and W2 start. What does every hidden neuron compute when all its weights are 0?",
    "Start them random, like the lesson: np.random.randn(2, 4) * 0.5 and np.random.randn(4, 1) * 0.5. Save, then run again.",
]

COACH = {
    "nn4": {
        "stepId": "nn4",
        "severity": "fail",
        "title": "Loss is stuck at 0.25",
        "body": "All four hidden neurons start with the same weights, so they get the same update and stay copies. "
                "With zeros nothing moves at all. Start W1 and W2 random.",
        "guidingQuestion": "If every hidden neuron starts the same, can they ever become different?",
        "citation": {"label": "Goodfellow et al., Deep Learning §8.4 (breaking symmetry)",
                     "url": "https://www.deeplearningbook.org/contents/optimization.html"},
        "actions": ["explain", "hint", "show_me"],
    }
}

EXPLAIN = {
    "nn1": ("What a neuron does", "It adds its inputs, each times a weight, plus a bias, then sigmoid squishes the total into 0..1. That number is how lit up it is."),
    "nn2": ("How backprop assigns blame", "Start at the output: how wrong was it? Each weight into it is blamed by how much it contributed. Then do the same one layer back."),
    "nn3": ("One pass of the loop", "forward makes a guess, backward says which way each weight should move, and each weight moves a little that way (lr sets how far). 5,000 times."),
    "nn4": ("Reading the loss", "The loss is the mean squared error over the four inputs. Answering 0.5 for everything scores 0.25; a network that has learned XOR goes below 0.01."),
    "nn4-stuck": ("Why zeros can't learn", "All four hidden neurons compute sigmoid(0) = 0.5 and get the same update, so they stay copies. Here the gradient is exactly zero."),
    "nn5": ("Reading the output", "Outputs are between 0 and 1. Above 0.5 counts as 1, so 0.03 0.98 0.97 0.03 reads as 0 1 1 0."),
    "nn6": ("What the weights mean", "Hidden neuron 1 turns on when either input is 1 (OR); neuron 3 only when both are (AND). The output adds the first and subtracts the third: OR minus AND is XOR."),
}

ASK = {
    "nn1": ("Sigmoid or ReLU?", "Both work. Sigmoid keeps outputs in 0..1 like XOR's answers, and its slope σ(1 − σ) keeps backprop to one line."),
    "nn2": ("Why out * (1 - out)?", "It's sigmoid's slope. The chain rule multiplies it in wherever the signal went through a sigmoid."),
    "nn3": ("Why lr = 1.0?", "A tiny network with a smooth loss can take big steps. On real data you'd start nearer 0.01."),
    "nn4": ("Why 5,000 epochs?", "XOR needs a few thousand small steps from this start; by epoch 4000 the loss is under 0.001."),
    "nn5": ("Why round the weights?", "Three decimals are enough to read them, and the drawing on the right uses the same numbers."),
    "nn6": ("What next?", "Swap XOR for real data: more inputs, a bigger hidden layer, and the same four pieces."),
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
    print(f"zeros: loss {ZERO_PRINTS} · lesson code: loss {[round(v, 4) for v in FIXED_PRINTS]}")
    print(f"wrote {LAB.relative_to(ROOT)}/ and demo/cache/(lessons|coach|cards|diagrams) for {len(STEPS)} steps")


if __name__ == "__main__":
    main()
