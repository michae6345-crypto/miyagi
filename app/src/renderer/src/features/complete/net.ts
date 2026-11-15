/**
 * The lesson's own network, read from the `network` diagrams the engine pushed (data.frames with real weights), for
 * mockup 12's header thumbnail, loss chart and fit chart. Pure: no React. Nothing here is made up: a piece that the
 * data can't back (no frames, one epoch, no samples / targets, a forward pass that doesn't reproduce the engine's
 * own activations) comes back undefined and the panel leaves it out.
 */

type Raw = Record<string, unknown>
export type NetFrame = { epoch?: number; loss?: number; input?: unknown; W: number[][][]; b?: number[][]; a?: number[][] }
export type Net = { layers: number[]; frames: NetFrame[]; activation?: string; samples?: number[]; targets?: number[] }

const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)

/** Nested W (W[k][i][j]) or flat row-major W[k][i*n+j] (older frames) when the layer sizes are known. */
function nestW(W: unknown, layers?: number[]): number[][][] | undefined {
  if (!Array.isArray(W) || !W.length) return undefined
  if (W.every((m) => Array.isArray(m) && m.every((r) => Array.isArray(r)))) return W as number[][][]
  if (!layers) return undefined
  return (W as number[][]).map((flat, k) => {
    const n = layers[k + 1] ?? 1
    return Array.from({ length: layers[k] ?? 0 }, (_, i) => Array.from({ length: n }, (_, j) => Number(flat?.[i * n + j] ?? 0)))
  })
}

/** A `network` diagram's data as a Net, or undefined when it has no usable weights. */
export function readNet(data: unknown): Net | undefined {
  const d = (data ?? {}) as Raw
  const rawFrames = Array.isArray(d.frames) ? (d.frames as Raw[]) : []
  if (!rawFrames.length) return undefined
  const given = Array.isArray(d.layers) && d.layers.every((x) => typeof x === 'number') ? (d.layers as number[]) : undefined
  const frames: NetFrame[] = []
  for (const f of rawFrames) {
    const W = nestW(f.W, given)
    if (!W) continue
    frames.push({ epoch: num(f.epoch), loss: num(f.loss), input: f.input, W, b: f.b as number[][] | undefined, a: f.a as number[][] | undefined })
  }
  if (!frames.length) return undefined
  const W = frames[frames.length - 1].W
  const layers = given ?? [W[0].length, ...W.map((m) => m[0]?.length ?? 0)]
  const samples = Array.isArray(d.samples) ? (d.samples as unknown[]).map((s) => num(Array.isArray(s) ? s[0] : s)) : undefined
  const targets = Array.isArray(d.targets) ? (d.targets as unknown[]).map((t) => num(Array.isArray(t) ? t[0] : t)) : undefined
  const ok = samples && targets && samples.length === targets.length && samples.length > 1 && samples.every((x) => x !== undefined) && targets.every((x) => x !== undefined)
  return {
    layers,
    frames,
    activation: typeof d.activation === 'string' ? d.activation : undefined,
    ...(ok ? { samples: samples as number[], targets: targets as number[] } : {})
  }
}

/** The loss over training, one point per epoch (needs at least two epochs). */
export function lossSeries(net: Net | undefined): Array<{ epoch: number; loss: number }> | undefined {
  if (!net) return undefined
  const by = new Map<number, number>()
  for (const f of net.frames) if (f.epoch !== undefined && f.loss !== undefined && f.loss > 0) by.set(f.epoch, f.loss)
  const pts = [...by.entries()].sort((a, b) => a[0] - b[0]).map(([epoch, loss]) => ({ epoch, loss }))
  return pts.length >= 2 ? pts : undefined
}

const SQUASH: Record<string, (z: number) => number> = {
  sigmoid: (z) => 1 / (1 + Math.exp(-z)),
  tanh: (z) => Math.tanh(z),
  relu: (z) => Math.max(0, z),
  linear: (z) => z
}

/** One input through the network: hidden layers use `act`, the output `out`. Every layer's activations. */
function forward(f: NetFrame, x: number[], act: (z: number) => number, out: (z: number) => number): number[][] {
  const as = [x]
  let h = x
  f.W.forEach((m, k) => {
    const last = k === f.W.length - 1
    const n = m[0]?.length ?? 0
    h = Array.from({ length: n }, (_, j) => {
      let z = Number(f.b?.[k]?.[j] ?? 0)
      for (let i = 0; i < m.length; i++) z += (h[i] ?? 0) * (m[i]?.[j] ?? 0)
      return (last ? out : act)(z)
    })
    as.push(h)
  })
  return as
}

/**
 * The trained network's curve against the lesson's targets (one input, one output). The output squash is checked
 * against the engine's own activations in the frame (`a`): linear first, then the hidden one; no match, no chart.
 */
export function fitCurve(net: Net | undefined, steps = 64): { xs: number[]; ys: number[]; samples: number[]; targets: number[]; maxError: number } | undefined {
  if (!net?.samples || !net.targets || net.layers[0] !== 1 || net.layers[net.layers.length - 1] !== 1) return undefined
  const f = net.frames[net.frames.length - 1]
  const act = SQUASH[net.activation ?? ''] ?? undefined
  if (!act || !f.a?.length) return undefined
  const x0 = Number(f.a[0]?.[0])
  const want = Number(f.a[f.a.length - 1]?.[0])
  if (!Number.isFinite(x0) || !Number.isFinite(want)) return undefined
  const outFn = [SQUASH.linear, act].find((o) => Math.abs(forward(f, [x0], act, o).at(-1)![0] - want) <= 0.02 + 0.02 * Math.abs(want))
  if (!outFn) return undefined
  const y = (x: number): number => forward(f, [x], act, outFn).at(-1)![0]
  const lo = Math.min(...net.samples)
  const hi = Math.max(...net.samples)
  const xs = Array.from({ length: steps }, (_, i) => lo + ((hi - lo) * i) / (steps - 1))
  const maxError = Math.max(...net.samples.map((x, i) => Math.abs(y(x) - net.targets![i])))
  return { xs, ys: xs.map(y), samples: net.samples, targets: net.targets, maxError }
}

/** "0.0019" / "0.82" / "7.8e-4": short, honest. */
export function short(v: number): string {
  const a = Math.abs(v)
  if (a === 0) return '0'
  if (a >= 100) return Math.round(v).toLocaleString('en-US')
  if (a >= 1) return v.toFixed(2).replace(/\.?0+$/, '')
  if (a >= 0.001) return v.toPrecision(2).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
  return v.toExponential(1)
}
