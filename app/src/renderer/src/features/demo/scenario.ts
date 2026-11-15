/**
 * Feature: demo. Builds the scripted engine for the neural-net lesson (mock/scenarios/demo.json) from lesson.ts.
 * Regenerate after editing lesson.ts:  npx tsx scripts/demo-scenario.ts
 *
 * Every message is a real contract message; nothing here is demo-only on the wire. Triggers, per step
 * (`@step_nnK` = while step K is the current one):
 *   learn                         → "Claude is writing your lesson" → lesson.ready → step 1
 *   action:check_step             → the step's checks pass → step.passed → next step
 *                                   (step 5: the run streams a flat loss → off track, level 2)
 *   action:hint (step 5)          → level 3: the exact fix + "Fix it"
 *   action:apply_fix (step 5)     → re-run, loss falls like the tutorial's → back on track → step 6
 *   action:explain / diagram / show_me / ask / hint / skip_step → the step's card, diagram, spotlight, skip
 */
import type { Scenario, ScenarioItem } from '../../../../../mock/engine'
import {
  BUG,
  CURVE_FIXED,
  CURVE_ZEROS,
  EPOCH_EVERY,
  FILE,
  LESSON,
  METRIC_MS,
  RUN,
  STEPS,
  TERM_PROMPT_LINE,
  linesRect,
  termRect,
  type DemoStep
} from './lesson'

const ev = (wait: number, type: string, payload: unknown = {}): ScenarioItem => ({ wait, type, payload })
const go = (wait: number, segment: string): ScenarioItem => ({ wait, goto: segment })

const code = (s: DemoStep): string => FILE.slice(s.from - 1, s.to).join('\n')
const seg = (s: DemoStep): string => `step_${s.id}`
const next = (s: DemoStep): DemoStep | undefined => STEPS[STEPS.indexOf(s) + 1]

/** Where each step says to type (the empty lines its code goes on). */
const CAPTION: Record<string, string> = {
  nn1: 'Create nn.py and type the data here',
  nn2: 'Weights go under the data',
  nn3: 'Add sigmoid and forward here',
  nn4: 'Add backward here',
  nn5: 'The training loop goes here',
  nn6: 'Last line: print the predictions'
}

const EXPLAIN: Record<string, { title: string; body: string }> = {
  nn1: {
    title: 'Why XOR needs a hidden layer',
    body: "The 1s sit on opposite corners of a square. No straight line splits them, so one neuron can't. A hidden layer bends it."
  },
  nn2: {
    title: 'Why the weights start random',
    body: 'Two neurons with the same weights compute the same thing and get the same update. Random starts let each learn its own.'
  },
  nn3: {
    title: 'What forward computes',
    body: 'Each hidden neuron takes a weighted sum of the inputs, squashed into 0..1 by sigmoid. W2 does it again to make one guess.'
  },
  nn4: {
    title: 'The chain rule, in this code',
    body: 'out depends on h, h on W1. Multiply the slopes along that path: d_out is error × σ′, and d_h carries it back through W2.'
  },
  nn5: {
    title: "Why zeros can't learn",
    body: 'All four hidden neurons compute sigmoid(0) = 0.5 and get the same update, so they stay copies. Here nothing moves at all.'
  },
  nn6: {
    title: 'Reading the output',
    body: 'Outputs are between 0 and 1. Above 0.5 counts as 1, so 0.03 0.98 0.97 0.03 reads as 0 1 1 0.'
  }
}

const HINT: Record<string, string> = {
  nn1: 'X has one row per example. y holds the four answers in the same order.',
  nn2: "W1 maps 2 inputs to 4 hidden neurons, so it's 2×4. W2 maps 4 to 1.",
  nn3: 'forward returns h as well: backward needs it.',
  nn4: "Sigmoid's slope is out * (1 - out). Multiply it in at each layer.",
  nn6: 'Compare the outputs with 0.5, then turn True and False into 1 and 0.'
}

/** "Ask anything" mid-step: the question a learner usually asks here. */
const ASK: Record<string, { title: string; body: string }> = {
  nn1: { title: 'Why start with XOR', body: "It's the smallest problem one neuron can't solve, so it proves the hidden layer is doing real work." },
  nn2: { title: 'Why times 0.5', body: "Small starting weights keep sigmoid in its steep middle, where the gradients are big enough to learn fast." },
  nn3: {
    title: 'Sigmoid or ReLU?',
    body: "Both work. Sigmoid keeps outputs in 0..1 like XOR's answers, and its slope σ(1 − σ) keeps backprop to one line."
  },
  nn4: {
    title: 'Why out * (1 - out)',
    body: "It's sigmoid's slope, σ(1 − σ). The chain rule multiplies it in wherever the signal went through a sigmoid."
  },
  nn5: { title: 'Why lr = 1.0', body: 'A tiny network with a smooth loss can take big steps. On real data you would start nearer 0.01.' },
  nn6: { title: 'What next', body: 'Swap XOR for real data: more inputs, a bigger hidden layer, and the same four pieces.' }
}

const NETWORK = {
  kind: 'network',
  caption: 'Two inputs, four hidden neurons, one output. Every line is one weight the loop learns.',
  data: { layers: [2, 4, 1], activation: 'sigmoid', inputs: ['x₁', 'x₂'], output: 'ŷ', derivatives: [], residual: '' }
}

const CHAIN = {
  kind: 'graph',
  caption: 'Forward makes a guess. Backward sends the error back the same way, one layer at a time.',
  data: {
    title: 'Forward, then backward',
    layout: 'flow',
    direction: 'LR',
    grid: { cols: 4, rows: 2 },
    nodes: [
      { id: 'x', label: 'X', detail: '4 examples', shape: 'data', emphasis: false, col: 0, row: 0 },
      { id: 'h', label: 'hidden h', detail: 'σ(X @ W1 + b1)', shape: 'box', emphasis: false, col: 1, row: 0 },
      { id: 'out', label: 'out', detail: 'σ(h @ W2 + b2)', shape: 'box', emphasis: false, col: 2, row: 0 },
      { id: 'loss', label: 'loss', detail: 'mean (out − y)²', shape: 'round', emphasis: true, col: 3, row: 0 },
      { id: 'dout', label: 'd_out', detail: 'error × σ′', shape: 'box', emphasis: true, col: 2, row: 1 },
      { id: 'dh', label: 'd_h', detail: 'd_out @ W2ᵀ × σ′', shape: 'box', emphasis: true, col: 1, row: 1 }
    ],
    edges: [
      { from: 'x', to: 'h', style: 'solid', emphasis: false },
      { from: 'h', to: 'out', style: 'solid', emphasis: false },
      { from: 'out', to: 'loss', style: 'solid', emphasis: false },
      { from: 'loss', to: 'dout', style: 'dashed', emphasis: true, label: 'backward' },
      { from: 'dout', to: 'dh', style: 'dashed', emphasis: true, label: 'through W2' }
    ]
  }
}

const SYMMETRY = {
  kind: 'graph',
  caption: 'With every weight at zero, all four hidden neurons compute 0.5 and get the same update. They stay copies.',
  data: {
    title: 'Four copies of one neuron',
    layout: 'architecture',
    direction: 'LR',
    grid: { cols: 3, rows: 4 },
    nodes: [
      { id: 'x', label: 'x₁, x₂', detail: 'inputs', shape: 'data', emphasis: false, col: 0, row: 1.5 },
      ...[0, 1, 2, 3].map((i) => ({ id: `h${i + 1}`, label: `h${i + 1} = 0.5`, detail: 'same update', shape: 'circle', emphasis: true, col: 1, row: i })),
      { id: 'out', label: 'out = 0.5', detail: 'for every input', shape: 'round', emphasis: false, col: 2, row: 1.5 }
    ],
    edges: [
      ...[1, 2, 3, 4].map((i) => ({ from: 'x', to: `h${i}`, style: 'solid', emphasis: false })),
      ...[1, 2, 3, 4].map((i) => ({ from: `h${i}`, to: 'out', style: 'solid', emphasis: false }))
    ]
  }
}

/** The end of the lesson: what you built today, and where the same ideas lead (Michael's skill map, as a diagram). */
const SKILLS = {
  kind: 'graph',
  caption: 'Solid: what you built today. Dashed: where the same backprop leads next.',
  data: {
    title: 'What you learned, what is next',
    layout: 'flow',
    direction: 'LR',
    grid: { cols: 4, rows: 2 },
    nodes: [
      { id: 'data', label: 'XOR data', detail: 'step 1', shape: 'data', emphasis: false, col: 0, row: 0 },
      { id: 'fwd', label: 'forward pass', detail: 'sigmoid · matmul', shape: 'box', emphasis: false, col: 0, row: 1 },
      { id: 'bp', label: 'backprop', detail: 'chain rule', shape: 'box', emphasis: true, col: 1, row: 0.5 },
      { id: 'gd', label: 'gradient descent', detail: 'random init', shape: 'box', emphasis: true, col: 2, row: 0.5 },
      { id: 'torch', label: 'PyTorch autograd', detail: 'next', shape: 'round', emphasis: false, col: 3, row: 0 },
      { id: 'attn', label: 'attention', detail: 'later', shape: 'round', emphasis: false, col: 3, row: 1 }
    ],
    edges: [
      { from: 'data', to: 'bp', style: 'solid', emphasis: false },
      { from: 'fwd', to: 'bp', style: 'solid', emphasis: false },
      { from: 'bp', to: 'gd', style: 'solid', emphasis: true },
      { from: 'gd', to: 'torch', style: 'dashed', emphasis: false, label: 'next' },
      { from: 'gd', to: 'attn', style: 'dashed', emphasis: false }
    ]
  }
}

const DIAGRAM: Record<string, unknown> = { nn1: NETWORK, nn2: NETWORK, nn3: NETWORK, nn4: CHAIN, nn5: SYMMETRY, nn6: SKILLS }

/** "Watch a video": real, well-known tutorials on this topic (no video ids: nothing here needs the network). */
const SEARCH = [
  {
    id: 'v1',
    kind: 'video',
    title: 'The spelled-out intro to neural networks and backpropagation: building micrograd',
    meta: 'Video · Andrej Karpathy',
    score: 0.93,
    reason: 'Builds backprop by hand',
    style: 'coding'
  },
  {
    id: 'v2',
    kind: 'video',
    title: 'Building a neural network FROM SCRATCH (no Tensorflow/Pytorch, just numpy & math)',
    meta: 'Video · Samson Zhang',
    score: 0.9,
    reason: 'NumPy only, like this lesson',
    style: 'coding'
  },
  { id: 'v3', kind: 'video', title: 'But what is a neural network?', meta: 'Video · 3Blue1Brown', score: 0.84, reason: 'The intuition first', style: 'conceptual' }
]

/** A training run: one `metric` per EPOCH_EVERY epochs, METRIC_MS apart (the fake terminal prints in step). */
const run = (runId: string, curve: number[]): ScenarioItem[] =>
  curve.map((value, i) => ev(i === 0 ? 350 : METRIC_MS, 'metric', { runId, step: i * EPOCH_EVERY, name: 'loss', value }))

/** The tutorial's reference curve, all at once (runId "tutorial": the cards draw it faint under yours). */
const tutorial = (): ScenarioItem[] => CURVE_FIXED.map((value, i) => ev(0, 'metric', { runId: 'tutorial', step: i * EPOCH_EVERY, name: 'loss', value }))

const bugRows = Object.keys(BUG).map(Number)
const bugRect = linesRect(Math.min(...bugRows), Math.max(...bugRows))
const fixed = (n: number): string => FILE[n - 1]

export function buildDemoScenario(): Scenario {
  // "Just teach me" builds the lesson; "Watch a video" finds tutorials first, and building one gives the same lesson.
  const on: Record<string, string> = { 'learn:lesson': 'nn_build', learn: 'nn_search', build_lesson: 'nn_build' }
  const segments: Record<string, ScenarioItem[]> = {}

  segments.nn_search = [
    ev(0, 'status', { state: 'thinking' }),
    ...SEARCH.map((r, i) => ev(i === 0 ? 700 : 180, 'search.result', r)),
    ev(150, 'search.done', { total: SEARCH.length }),
    ev(0, 'status', { state: 'idle' })
  ]

  segments.nn_build = [
    ev(0, 'status', { state: 'thinking' }),
    ev(250, 'lesson.building', { message: 'Reading about neural nets from scratch', progress: 0.15, elapsedS: 0 }),
    ev(1000, 'lesson.building', { message: 'Planning 6 steps', progress: 0.45, elapsedS: 1 }),
    ev(1000, 'lesson.building', { message: 'Claude is writing your lesson', progress: 0.8, elapsedS: 2 }),
    ev(1000, 'lesson.building', { message: 'Claude is writing your lesson', progress: 0.95, elapsedS: 3 }),
    ev(500, 'lesson.ready', {
      lesson: { id: LESSON.id, title: LESSON.title, sources: [], complete: true, builtBy: 'claude', mode: 'lesson', overview: LESSON.overview, primer: LESSON.primer },
      steps: STEPS.map((s, index) => ({ id: s.id, index, title: s.title, kind: s.kind, what: s.what, video: null }))
    }),
    ev(0, 'status', { state: 'watching' }),
    go(300, seg(STEPS[0]))
  ]

  for (const [index, s] of STEPS.entries()) {
    const k = seg(s)
    const after = next(s)
    // Step start: the step, its checks watching, and where to type.
    segments[k] = [
      ev(0, 'step.started', {
        stepId: s.id,
        index,
        title: s.title,
        instructions: s.instructions,
        video: null,
        kind: s.kind,
        what: s.what,
        why: s.why,
        concepts: s.concepts,
        code: code(s)
      }),
      ...s.checks.map((c) => ev(0, 'check.updated', { stepId: s.id, checkId: c.id, label: c.label, status: 'pending' })),
      ev(500, 'spotlight', { rect: linesRect(s.from, s.to), caption: CAPTION[s.id], app: 'Code' })
    ]

    const passAndGo = (wait: number): ScenarioItem[] => [
      ev(0, 'status', { state: 'watching' }),
      ev(wait, 'step.passed', after ? { stepId: s.id, nextStepId: after.id } : { stepId: s.id }),
      ev(0, 'spotlight', { clear: true }),
      ...(after
        ? [go(1700, seg(after))]
        : [
            ev(1500, 'card', {
              stepId: s.id,
              kind: 'answer',
              title: 'You built a neural net from scratch',
              body: 'Six steps, one bug caught by its training curve. It learned XOR with nothing but NumPy.',
              output: '[0 1 1 0]'
            })
          ])
    ]

    // Check: every check passes (step 5's run is the exception: flat loss → off track).
    if (s.id === 'nn5') {
      segments[`${s.id}_check`] = [
        ev(0, 'status', { state: 'thinking' }),
        ev(400, 'check.updated', { stepId: s.id, checkId: 'c1', label: s.checks[0].label, status: 'pass' }),
        ev(250, 'check.updated', { stepId: s.id, checkId: 'c2', label: s.checks[1].label, status: 'pending', detail: `running ${RUN}` }),
        ev(0, 'status', { state: 'watching' }),
        ev(0, 'spotlight', { rect: termRect(TERM_PROMPT_LINE.nn5), caption: 'Watching your training run', app: 'Code' }),
        ...tutorial(),
        ...run('zeros', CURVE_ZEROS),
        ev(200, 'check.updated', { stepId: s.id, checkId: 'c2', label: s.checks[1].label, status: 'pass' }),
        ev(300, 'check.updated', { stepId: s.id, checkId: 'c3', label: s.checks[2].label, status: 'fail', detail: 'yours 0.2500' }),
        ev(0, 'status', { state: 'offtrack' }),
        ev(150, 'offtrack', {
          stepId: s.id,
          severity: 'fail',
          reason: 'loss flat for 5,000 epochs',
          title: 'Loss is stuck at 0.25',
          body: "Your loss hasn't moved in 5,000 epochs. The tutorial's falls below 0.01.",
          guidingQuestion: 'If every hidden neuron starts the same, can they ever become different?',
          actions: ['show_me', 'explain', 'hint'],
          level: 2,
          curve: { label: 'loss', yours: CURVE_ZEROS, tutorial: CURVE_FIXED }
        }),
        ev(450, 'spotlight', { rect: bugRect, caption: 'Every weight starts at zero', app: 'Code', matched: BUG[8] })
      ]
      segments[`${s.id}_hint`] = [
        ev(0, 'status', { state: 'thinking' }),
        ev(700, 'offtrack', {
          stepId: s.id,
          severity: 'fail',
          reason: 'loss flat for 5,000 epochs',
          title: 'Loss is stuck at 0.25',
          body: 'Start W1 and W2 random, like the lesson. Zeros make every hidden neuron identical.',
          diff: { file: 'nn.py', line: 8, expected: fixed(8), yours: BUG[8] },
          actions: ['show_me', 'explain', 'apply_fix'],
          level: 3,
          curve: { label: 'loss', yours: CURVE_ZEROS, tutorial: CURVE_FIXED },
          citation: { label: 'Goodfellow et al. · Deep Learning §8.4', url: 'https://www.deeplearningbook.org/contents/optimization.html' }
        }),
        ev(0, 'status', { state: 'offtrack' }),
        ev(300, 'spotlight', { rect: bugRect, caption: 'Start these random, like the lesson', app: 'Code', matched: BUG[8] })
      ]
      segments[`${s.id}_fix`] = [
        ev(0, 'status', { state: 'thinking' }),
        ev(300, 'spotlight', { rect: bugRect, caption: 'Random starts, like the lesson', app: 'Code', matched: fixed(8) }),
        ev(0, 'check.updated', { stepId: s.id, checkId: 'c3', label: s.checks[2].label, status: 'pending', detail: 'retraining' }),
        ev(900, 'status', { state: 'watching' }),
        ev(0, 'spotlight', { rect: termRect(TERM_PROMPT_LINE.nn5_fix), caption: 'Retraining with random weights', app: 'Code' }),
        ...run('fixed', CURVE_FIXED),
        ev(250, 'check.updated', { stepId: s.id, checkId: 'c3', label: s.checks[2].label, status: 'pass', detail: 'yours 0.0007' }),
        ev(0, 'status', { state: 'passed' }),
        ev(400, 'step.passed', { stepId: s.id, nextStepId: after!.id, summary: 'Loss 0.0007, like the tutorial.' }),
        ev(0, 'spotlight', { clear: true }),
        go(4200, seg(after!))
      ]
      on[`action:hint@${k}`] = `${s.id}_hint`
      on[`action:apply_fix@${k}`] = `${s.id}_fix`
    } else if (s.runs) {
      segments[`${s.id}_check`] = [
        ev(0, 'status', { state: 'thinking' }),
        ev(300, 'check.updated', { stepId: s.id, checkId: 'c1', label: s.checks[0].label, status: 'pending', detail: `running ${RUN}` }),
        ev(0, 'status', { state: 'watching' }),
        ev(0, 'spotlight', { rect: termRect(TERM_PROMPT_LINE.nn6), caption: 'Running your network', app: 'Code' }),
        ...run('final', CURVE_FIXED).map((m, i) => (i === 0 ? m : { ...m, wait: 70 })),
        ev(500, 'check.updated', { stepId: s.id, checkId: 'c1', label: s.checks[0].label, status: 'pass', detail: '[0 1 1 0]' }),
        ...passAndGo(500)
      ]
    } else {
      segments[`${s.id}_check`] = [
        ev(0, 'status', { state: 'thinking' }),
        ...s.checks.map((c, i) => ev(i === 0 ? 350 : 380, 'check.updated', { stepId: s.id, checkId: c.id, label: c.label, status: 'pass' })),
        ...passAndGo(400)
      ]
    }
    on[`action:check_step@${k}`] = `${s.id}_check`

    // Skip: done, never green.
    segments[`${s.id}_skip`] = [
      ev(0, 'spotlight', { clear: true }),
      ev(200, 'step.passed', after ? { stepId: s.id, nextStepId: after.id, skipped: true } : { stepId: s.id, skipped: true }),
      ...(after ? [go(900, seg(after))] : [])
    ]
    on[`action:skip_step@${k}`] = `${s.id}_skip`

    // Understand: explain, diagram, ask (a card or a picture out of the island).
    segments[`${s.id}_explain`] = [
      ev(0, 'status', { state: 'thinking' }),
      ev(650, 'card', { stepId: s.id, kind: 'explain', ...EXPLAIN[s.id] }),
      ev(0, 'status', { state: s.id === 'nn5' ? 'offtrack' : 'watching' })
    ]
    segments[`${s.id}_diagram`] = [
      ev(0, 'status', { state: 'thinking' }),
      ev(700, 'diagram', { ...(DIAGRAM[s.id] as object), stepId: s.id }),
      ev(0, 'status', { state: s.id === 'nn5' ? 'offtrack' : 'watching' })
    ]
    segments[`${s.id}_ask`] = [
      ev(0, 'status', { state: 'thinking' }),
      ev(900, 'card', { stepId: s.id, kind: 'answer', ...ASK[s.id] }),
      ev(0, 'status', { state: s.id === 'nn5' ? 'offtrack' : 'watching' })
    ]
    // Show me: where to type, with the code under the caption.
    segments[`${s.id}_showme`] = [
      ev(
        250,
        'spotlight',
        s.id === 'nn5'
          ? { rect: bugRect, caption: 'Use the random weights from the lesson', app: 'Code', snippet: `${fixed(8)}\n${fixed(9)}\n${fixed(10)}` }
          : { rect: linesRect(s.from, s.to), caption: 'Type this here', app: 'Code', snippet: code(s) }
      )
    ]
    on[`action:explain@${k}`] = `${s.id}_explain`
    on[`action:diagram@${k}`] = `${s.id}_diagram`
    on[`action:ask@${k}`] = `${s.id}_ask`
    on[`action:show_me@${k}`] = `${s.id}_showme`
    if (HINT[s.id]) {
      segments[`${s.id}_hint`] = [
        ev(0, 'status', { state: 'thinking' }),
        ev(600, 'card', { stepId: s.id, kind: 'hint', title: 'Hint', body: HINT[s.id] }),
        ev(0, 'status', { state: 'watching' })
      ]
      on[`action:hint@${k}`] = `${s.id}_hint`
    }
  }

  // Standalone: it answers learn and build_lesson itself, so it must not leak into the merged "full" scenario.
  return { name: 'demo', full: false, on, segments } as Scenario
}
