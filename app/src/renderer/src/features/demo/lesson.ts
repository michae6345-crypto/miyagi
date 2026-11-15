/**
 * Feature: demo. "A neural net from scratch": the one lesson the offline demo teaches.
 *
 * ONE source of truth for both sides of the demo:
 *   - scripts/demo-scenario.ts turns it into mock/scenarios/demo.json (the scripted engine: wire messages only)
 *   - Desktop.tsx draws the fake VS Code from it (the file, line positions, terminal output)
 * Pure data and geometry, no React: the generator imports it with tsx.
 *
 * The code and every number below come from running it (Python 3.12, NumPy 2.5):
 *   W1, W2 = zeros  → loss 0.2500 at every epoch, every output 0.5, predicts [0 0 0 0]
 *   seeded randn    → 0.2691 → 0.0219 → 0.0029 → 0.0014 → 0.0009, predicts [0 1 1 0]
 */

/** The finished nn.py, line 1 first. */
export const FILE: string[] = [
  'import numpy as np',
  '',
  '# XOR: 1 when exactly one input is 1',
  'X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]])',
  'y = np.array([[0], [1], [1], [0]])',
  '',
  'np.random.seed(0)',
  'W1 = np.random.randn(2, 4) * 0.5',
  'b1 = np.zeros((1, 4))',
  'W2 = np.random.randn(4, 1) * 0.5',
  'b2 = np.zeros((1, 1))',
  '',
  'def sigmoid(z):',
  '    return 1 / (1 + np.exp(-z))',
  '',
  'def forward(X):',
  '    h = sigmoid(X @ W1 + b1)',
  '    return h, sigmoid(h @ W2 + b2)',
  '',
  'def backward(X, y, h, out):',
  '    d_out = 2 * (out - y) / len(X) * out * (1 - out)',
  '    d_h = d_out @ W2.T * h * (1 - h)',
  '    return h.T @ d_out, d_out.sum(0), X.T @ d_h, d_h.sum(0)',
  '',
  'lr = 1.0',
  'for epoch in range(5000):',
  '    h, out = forward(X)',
  '    dW2, db2, dW1, db1 = backward(X, y, h, out)',
  '    W2 -= lr * dW2',
  '    b2 -= lr * db2',
  '    W1 -= lr * dW1',
  '    b1 -= lr * db1',
  '    loss = np.mean((out - y) ** 2)',
  '    if epoch % 1000 == 0:',
  '        print(f"epoch {epoch:4d}  loss {loss:.4f}")',
  '',
  'print((forward(X)[1] > 0.5).astype(int).ravel())'
]

export const FILE_NAME = 'nn.py'
export const FOLDER = 'nn-from-scratch'
export const RUN = 'python nn.py'

/** The learner's shortcut in step 2 (the bug the demo catches): zeros instead of random weights. */
export const BUG: Record<number, string> = {
  8: 'W1 = np.zeros((2, 4))',
  10: 'W2 = np.zeros((4, 1))'
}

export type Check = { id: string; label: string }

export type DemoStep = {
  id: string
  title: string
  kind: 'code' | 'run'
  /** The lines of FILE this step adds (1-based, inclusive). */
  from: number
  to: number
  /** What this step builds (<= 12 words): the plan line. */
  what: string
  /** ONE concrete action. */
  instructions: string
  /** What it means (<= 25 words). */
  why: string
  concepts: string[]
  checks: Check[]
  /** The step ends with `python nn.py` in the terminal. */
  runs?: boolean
}

export const STEPS: DemoStep[] = [
  {
    id: 'nn1',
    title: 'The data',
    kind: 'code',
    from: 1,
    to: 5,
    what: 'XOR inputs and targets as NumPy arrays',
    instructions: 'Create nn.py and type the XOR data.',
    why: "XOR is the classic case one straight line can't split, so it needs a hidden layer.",
    concepts: ['xor'],
    checks: [
      { id: 'c1', label: 'nn.py exists' },
      { id: 'c2', label: 'X is 4×2 and y is 4×1' }
    ]
  },
  {
    id: 'nn2',
    title: 'Weights',
    kind: 'code',
    from: 7,
    to: 11,
    what: 'Random starting weights for a 2-4-1 network',
    instructions: 'Add the weights and biases under the data.',
    why: 'Small random weights make each hidden neuron start different, so each can learn its own feature.',
    concepts: ['matmul'],
    checks: [
      { id: 'c1', label: 'W1 is 2×4 and W2 is 4×1' },
      { id: 'c2', label: 'b1 and b2 are defined' }
    ]
  },
  {
    id: 'nn3',
    title: 'Forward pass',
    kind: 'code',
    from: 13,
    to: 18,
    what: 'Sigmoid, and a forward pass from inputs to a guess',
    instructions: 'Add sigmoid and forward.',
    why: 'Each layer is a weighted sum squashed by sigmoid. Two layers turn the inputs into a guess between 0 and 1.',
    concepts: ['sigmoid', 'matmul'],
    checks: [
      { id: 'c1', label: 'sigmoid and forward are defined' },
      { id: 'c2', label: 'forward(X) returns 4 outputs' }
    ]
  },
  {
    id: 'nn4',
    title: 'Backprop',
    kind: 'code',
    from: 20,
    to: 23,
    what: 'A gradient for every weight, with the chain rule',
    instructions: 'Add backward. It returns one gradient per weight.',
    why: 'The chain rule passes the error back one layer at a time, so every weight learns its share of the blame.',
    concepts: ['chain_rule'],
    checks: [
      { id: 'c1', label: 'backward is defined' },
      { id: 'c2', label: 'Gradients match the weight shapes' }
    ]
  },
  {
    id: 'nn5',
    title: 'Train',
    kind: 'code',
    from: 25,
    to: 35,
    what: 'A loop that steps every weight downhill 5,000 times',
    instructions: 'Type the training loop, then run python nn.py.',
    why: 'Gradient descent: move each weight a little against its gradient, and the loss falls.',
    concepts: ['gradient_descent'],
    checks: [
      { id: 'c1', label: 'The loop updates all four weights' },
      { id: 'c2', label: 'nn.py runs without errors' },
      { id: 'c3', label: 'Loss falls below 0.01' }
    ],
    runs: true
  },
  {
    id: 'nn6',
    title: 'Test it',
    kind: 'run',
    from: 37,
    to: 37,
    what: 'Predict XOR and see 0 1 1 0',
    instructions: 'Add the last line and run python nn.py.',
    why: 'Outputs above 0.5 count as 1, so the guesses become answers you can check against XOR.',
    concepts: [],
    checks: [{ id: 'c1', label: 'Predicts 0 1 1 0' }],
    runs: true
  }
]

export const LESSON = {
  id: 'nn-from-scratch',
  title: 'A neural net from scratch',
  overview:
    "We'll build a neural network with nothing but NumPy and teach it XOR. First the data, then random weights, a forward pass that makes a guess, backprop that gives each weight its share of the error, and a loop that trains it. At the end it answers 0 1 1 0 on its own.",
  primer: [
    {
      id: 'xor',
      title: 'XOR',
      body: '1 when exactly one input is 1. No single straight line separates its 1s from its 0s.',
      code: '0 0 → 0\n0 1 → 1\n1 0 → 1\n1 1 → 0'
    },
    {
      id: 'matmul',
      title: 'Matrix multiply',
      body: "X @ W1 computes every hidden neuron's weighted sum, for all four examples at once.",
      code: '(4×2) @ (2×4) → (4×4)'
    },
    {
      id: 'sigmoid',
      title: 'Sigmoid',
      body: 'Squashes any number into 0..1. Its slope is σ(z)·(1 − σ(z)), which backprop reuses.',
      code: '1 / (1 + np.exp(-z))'
    },
    {
      id: 'chain_rule',
      title: 'Chain rule',
      body: 'How a weight moves the loss: multiply the slopes along the path from that weight to the loss.',
      diagramPrompt: 'The chain rule through a 2-4-1 network'
    },
    {
      id: 'gradient_descent',
      title: 'Gradient descent',
      body: 'Step each weight a little against its gradient. Repeat, and the loss falls.',
      code: 'W -= lr * dW'
    }
  ]
}

/** Real loss every 250 epochs (20 points), from running the file. */
export const CURVE_ZEROS: number[] = Array.from({ length: 20 }, () => 0.25)
export const CURVE_FIXED: number[] = [
  0.2691, 0.24696, 0.21131, 0.10564, 0.021908, 0.0091464, 0.005438, 0.0037846, 0.0028712, 0.0022988, 0.0019092, 0.0016282, 0.0014166,
  0.0012519, 0.0011202, 0.0010127, 0.00092341, 0.00084807, 0.00078371, 0.00072813
]
/** What `python nn.py` prints (the epoch lines come from the metric stream: every 4th point). */
export const PREDICT_ZEROS = '[0 0 0 0]'
export const PREDICT_FIXED = '[0 1 1 0]'
export const EPOCH_EVERY = 250
export const PRINT_EVERY = 1000
/** ms between two metric points while a run streams (the terminal prints in step with it). */
export const METRIC_MS = 130

export const epochLine = (epoch: number, loss: number): string => `epoch ${String(epoch).padStart(4)}  loss ${loss.toFixed(4)}`

// ---------------------------------------------------------------------------
// The fake desktop's geometry, in stage points (1600×1000, the mockups' frame). The spotlight rects the
// scripted engine sends are computed from these, so they always land on the right line.
// ---------------------------------------------------------------------------

export const G = {
  menuH: 32,
  titleH: 28,
  activityW: 48,
  explorerW: 184,
  /** Editor column: tabs, breadcrumb, then the code. */
  editorX: 232,
  editorW: 560,
  tabsH: 35,
  crumbsH: 22,
  gutterW: 50,
  /** First code line's top and the line height (13px mono). */
  codeTop: 121,
  lineH: 18,
  /** The terminal panel sits right of the editor ("panel position: right"). */
  termX: 792,
  termTop: 103,
  statusH: 22
} as const

export const codeX = G.editorX + G.gutterW + 8
export const lineTop = (n: number): number => G.codeTop + (n - 1) * G.lineH
export const termLineTop = (n: number): number => G.termTop + (n - 1) * G.lineH

export type Rect = { x: number; y: number; w: number; h: number }

/** The box around lines from..to of nn.py (where to type, or what to look at). */
export function linesRect(from: number, to: number, w = 470): Rect {
  return { x: codeX - 6, y: lineTop(from) - 3, w, h: (to - from + 1) * G.lineH + 6 }
}

/** The box around terminal line n (1-based). */
export function termRect(n: number): Rect {
  return { x: G.termX + 8, y: termLineTop(n) - 3, w: 300, h: G.lineH + 6 }
}

/**
 * The canonical terminal (the walkthrough's order): the prompt is line 1; step 5's run prints the command
 * and 5 epoch lines (prompt on 7); the re-run after the fix ends with the prompt on 13; step 6 adds the
 * prediction line too.
 */
export const TERM_PROMPT_LINE = { nn5: 1, nn5_fix: 7, nn6: 13 } as const
