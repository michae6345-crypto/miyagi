"""Builds the offline "neural net from scratch" demo for the real engine (DEMO=1), with zero API calls.

    python scripts/make_nn_demo.py          # needs numpy; rewrites every file below
    scripts/miyagi-nn-demo.sh               # then run the engine on it

What it writes (all data, no engine code):
  demo/nn-lab/nn.py, demo/nn-start.py       the learner's file and its clean copy (step anchors only)
  demo/cache/lessons/text-nn-from-scratch.json
                                            the 4-step "Just teach me" lesson (mode "lesson"); under DEMO=1
                                            "Just teach me" picks the newest lesson-mode cache, and the launch
                                            script touches this one so it wins
  demo/cache/coach/nn3.json                 the off-track card when training stays flat (zero weights)
  demo/cache/cards/nn<k>-explain|answer|hint<n>.json
                                            Explain / Ask / Hint for each step
  demo/cache/diagrams/nn<k>-network.json, nn3-gradients.json
                                            live networks (the app's NeuralNet view): neurons lit by activation,
                                            weights blue/brown, signals firing. Needs the 3-line per-step lookup in
                                            modules.diagram (same branch); without it DEMO falls back to its stubs.

The story: step 1 builds the network, and the learner takes a shortcut, W1 and W2 = zeros. Every check passes.
Step 3 trains: the loss sits at exactly 0.2500 for all 5,000 epochs, because every hidden neuron computes the
same thing and gets the same update. miyagi goes off track, the diagram shows four identical neurons, the hint
ladder says start them random; the learner fixes it by hand, reruns, and the loss falls to 0.0009.
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
# The code, step by step (what the drawer shows and Copy copies). The learner types/pastes it under each anchor.
# ---------------------------------------------------------------------------------------------------------------

STARTER = """# A neural net from scratch: 2 inputs, 4 hidden neurons, 1 output. It learns XOR.
import numpy as np

# Step 1: the network


# Step 2: backprop


# Step 3: train


# Step 4: test it
"""

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
    "nn4": """print((forward(X)[1] > 0.5).astype(int).ravel())""",
}

# ---------------------------------------------------------------------------------------------------------------
# Real runs: the weights every 250 epochs (the live diagrams), for the shortcut (zeros) and the fixed file.
# ---------------------------------------------------------------------------------------------------------------

X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]])
Y = np.array([[0], [1], [1], [0]])


def train(zero: bool) -> tuple[list[dict], list[float]]:
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
    return frames, printed


ZEROS, ZERO_PRINTS = train(zero=True)
FIXED, FIXED_PRINTS = train(zero=False)
assert all(abs(v - 0.25) < 1e-9 for v in ZERO_PRINTS), ZERO_PRINTS
assert FIXED_PRINTS[-1] < 0.01, FIXED_PRINTS


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


DIAGRAMS = {
    "nn1-network": net("forward", FIXED[-1:],
                       "What you're building. Brightness is a neuron's activation; blue weights push up, brown push down."),
    "nn2-network": net("backward", FIXED[:1],
                       "Backprop: the output's error flows back along the same weights, and each weight gets its share."),
    "nn3-network": net("train", FIXED,
                       "Training: every weight takes a small step downhill 5,000 times, and ŷ settles on 0 1 1 0."),
    "nn3-gradients": net("train", ZEROS,
                         "Your run: all four hidden neurons are the same neuron. Same start, same update, so nothing moves."),
    "nn4-network": net("train", FIXED,
                       "After the fix: random starts make each neuron different. Watch them learn 0 1 1 0."),
}

# ---------------------------------------------------------------------------------------------------------------
# The lesson (the engine's step-graph format, same as demo/cache/lessons/text-43e26ca1d86c37ed.json).
# ---------------------------------------------------------------------------------------------------------------

METRIC = r"epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>[0-9.eE+-]+)"


def step(sid: str, index: int, **kw) -> dict:
    s = {"id": sid, "index": index, "file": "nn.py", "code": CODE[sid], "explanations": []}
    s.update(kw)
    return s


STEPS = [
    step(
        "nn1", 1,
        title="Build the network",
        kind="code",
        what="The data, random weights and a forward pass",
        why="Every guess the network makes is this forward pass: weighted sums squished by sigmoid, one layer at a time.",
        concepts=["p1", "p2", "p3"],
        action="In nn.py, paste the network under # Step 1",
        instructions="Under # Step 1, add the XOR data, the weights and the forward pass.",
        checks=[
            {"id": "nn1c1", "type": "screen_contains", "label": "The XOR data is in nn.py", "app": "Code", "pattern": r"y\s*=\s*np\.array\(\[\[0\],\s*\[1\]"},
            {"id": "nn1c2", "type": "screen_contains", "label": "W1 and W2 are created", "app": "Code", "pattern": r"W2\s*=\s*np\."},
            {"id": "nn1c3", "type": "screen_contains", "label": "forward is defined", "app": "Code", "pattern": r"def\s+forward\(X\)"},
        ],
        precision_checks=[
            {"id": "nn1p1", "type": "file_contains", "label": "nn.py defines forward", "file": "nn.py", "pattern": r"def forward\(X\):"},
            {"id": "nn1p2", "type": "file_contains", "label": "nn.py has sigmoid", "file": "nn.py", "pattern": r"1 / \(1 \+ np\.exp\(-z\)\)"},
        ],
        targets=[{"app": "Code", "file": "nn.py", "match": "# Step 1: the network", "caption": "Paste the network under this line"}],
        hints=[
            "Use the drawer's Copy button, then paste under # Step 1.",
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
        action="In nn.py, add backward under # Step 2",
        instructions="Under # Step 2, add backward. It returns one gradient per weight.",
        checks=[
            {"id": "nn2c1", "type": "screen_contains", "label": "backward is defined", "app": "Code", "pattern": r"def\s+backward\("},
            {"id": "nn2c2", "type": "screen_contains", "label": "The error flows back through W2", "app": "Code", "pattern": r"d_h\s*=\s*d_out\s*@\s*W2\.T"},
        ],
        precision_checks=[
            {"id": "nn2p1", "type": "file_contains", "label": "nn.py defines backward", "file": "nn.py", "pattern": r"def backward\(X, y, h, out\):"},
        ],
        targets=[{"app": "Code", "file": "nn.py", "match": "# Step 2: backprop", "caption": "Add backward under this line"}],
        hints=[
            "Start at the output: d_out is the error times sigmoid's slope, out * (1 - out).",
            "d_h sends d_out back through W2, then multiplies by the hidden layer's slope.",
        ],
        common_mistakes=["Writing W2 instead of W2.T, so the shapes don't line up.", "Forgetting the hidden slope h * (1 - h)."],
        estMinutes=3,
    ),
    step(
        "nn3", 3,
        title="Train",
        kind="code",
        what="A loop that steps every weight downhill 5,000 times",
        why="Each step lowers the loss a little. If the loss stops falling, the network has stopped learning.",
        concepts=["p4"],
        action="Add the training loop under # Step 3, then run python3 nn.py",
        instructions="Under # Step 3, add the training loop, then run python3 nn.py in the terminal.",
        run_command=RUN,
        checks=[
            {"id": "nn3c1", "type": "screen_contains", "label": "The loop updates the weights", "app": "Code", "pattern": r"W1\s*-=\s*lr\s*\*\s*dW1"},
            {"id": "nn3c2", "type": "screen_absent", "label": "Training runs without errors", "app": "Terminal", "pattern": "Traceback|Error"},
            {"id": "nn3c3", "type": "metric_threshold", "label": "Loss falls below 0.01", "metric": "loss", "op": "<", "value": 0.01,
             "metric_pattern": METRIC, "by_step": 4000},
        ],
        precision_checks=[
            {"id": "nn3p1", "type": "file_contains", "label": "nn.py has the training loop", "file": "nn.py", "pattern": r"for epoch in range\(5000\):"},
            {"id": "nn3p2", "type": "metric_threshold", "label": "Loss falls below 0.01", "metric": "loss", "op": "<", "value": 0.01,
             "metric_pattern": METRIC, "by_step": 4000},
        ],
        targets=[
            {"app": "Code", "file": "nn.py", "match": "# Step 3: train", "caption": "Add the training loop under this line"},
            {"app": "Terminal", "file": "nn.py", "match": RUN, "caption": f"Run {RUN} and watch the loss"},
        ],
        hints=[
            "Look at how W1 and W2 start. What does every hidden neuron compute when all its weights are 0?",
            "Start them random, like the lesson: np.random.randn(2, 4) * 0.5 and np.random.randn(4, 1) * 0.5. Then run again.",
        ],
        common_mistakes=["Starting W1 and W2 at zero: every hidden neuron stays identical and the loss never moves.",
                         "Running before saving, so the old file runs."],
        estMinutes=3,
    ),
    step(
        "nn4", 4,
        title="Test it",
        kind="code",
        what="Print what it predicts for all four inputs",
        why="Outputs above 0.5 count as 1, so you can check its answers against XOR.",
        concepts=["p1"],
        action="Add the print under # Step 4, then run python3 nn.py",
        instructions="Under # Step 4, print the predictions, then run python3 nn.py.",
        run_command=RUN,
        expected_output="[0 1 1 0]",
        checks=[
            {"id": "nn4c1", "type": "screen_contains", "label": "It predicts 0 1 1 0", "app": "Terminal", "pattern": r"\[0 1 1 0\]"},
        ],
        precision_checks=[
            {"id": "nn4p1", "type": "file_contains", "label": "nn.py prints the predictions", "file": "nn.py", "pattern": r"> 0\.5\)\.astype\(int\)"},
            {"id": "nn4p2", "type": "output_contains", "label": "The output is [0 1 1 0]", "pattern": r"\[0 1 1 0\]"},
        ],
        targets=[{"app": "Code", "file": "nn.py", "match": "# Step 4: test it", "caption": "Print the predictions under this line"}],
        hints=["forward(X)[1] is the output for all four inputs.", "Compare with 0.5 and turn True/False into 1/0 with .astype(int)."],
        common_mistakes=["Printing forward(X) instead of forward(X)[1], which prints h too."],
        estMinutes=2,
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
    "build": {"mode": "lesson", "note": "Written by hand for the offline demo (scripts/make_nn_demo.py), no model call."},
}

# ---------------------------------------------------------------------------------------------------------------
# Coaching (cached, so it's instant and needs no network): the off-track card, Explain, Ask, Hint.
# ---------------------------------------------------------------------------------------------------------------

COACH = {
    "nn3": {
        "stepId": "nn3",
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
    "nn3": ("Why zeros can't learn", "All four hidden neurons compute sigmoid(0) = 0.5 and get the same update, so they stay copies. Here the gradient is exactly zero."),
    "nn4": ("Reading the output", "Outputs are between 0 and 1. Above 0.5 counts as 1, so 0.03 0.98 0.97 0.03 reads as 0 1 1 0."),
}

ASK = {
    "nn1": ("Sigmoid or ReLU?", "Both work. Sigmoid keeps outputs in 0..1 like XOR's answers, and its slope σ(1 − σ) keeps backprop to one line."),
    "nn2": ("Why out * (1 - out)?", "It's sigmoid's slope. The chain rule multiplies it in wherever the signal went through a sigmoid."),
    "nn3": ("Why lr = 1.0?", "A tiny network with a smooth loss can take big steps. On real data you'd start nearer 0.01."),
    "nn4": ("What next?", "Swap XOR for real data: more inputs, a bigger hidden layer, and the same four pieces."),
}


def write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    LAB.mkdir(parents=True, exist_ok=True)
    (ROOT / "demo" / "nn-start.py").write_text(STARTER, encoding="utf-8")
    (LAB / "nn.py").write_text(STARTER, encoding="utf-8")
    write(CACHE / "lessons" / "text-nn-from-scratch.json", LESSON)
    for sid, card in COACH.items():
        write(CACHE / "coach" / f"{sid}.json", card)
    for s in STEPS:
        sid = s["id"]
        title, body = EXPLAIN[sid]
        write(CACHE / "cards" / f"{sid}-explain.json", {"stepId": sid, "kind": "explain", "title": title, "body": body})
        title, body = ASK[sid]
        write(CACHE / "cards" / f"{sid}-answer.json", {"stepId": sid, "kind": "answer", "title": title, "body": body})
        for level, text in enumerate(s["hints"]):
            write(CACHE / "cards" / f"{sid}-hint{level}.json",
                  {"stepId": sid, "kind": "hint", "title": f"Hint {level + 1} of {len(s['hints'])}", "body": text})
    for name, d in DIAGRAMS.items():
        write(CACHE / "diagrams" / f"{name}.json", d)
    print(f"zeros: loss {ZERO_PRINTS} · fixed: loss {[round(v, 4) for v in FIXED_PRINTS]}")
    print(f"wrote {LAB.relative_to(ROOT)}/ and demo/cache/(lessons|coach|cards|diagrams) for {len(STEPS)} steps")


if __name__ == "__main__":
    main()
