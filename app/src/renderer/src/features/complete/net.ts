/**
 * The lesson's own network, read from the `network` diagrams the engine pushed (data.frames with real weights), for
 * the complete panel's network and its loss. Pure: no React. Nothing here is made up: a piece that the data can't
 * back (no frames, no loss) comes back undefined and the panel leaves it out.
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

/** "0.0019" / "0.82" / "7.8e-4": short, honest. */
export function short(v: number): string {
  const a = Math.abs(v)
  if (a === 0) return '0'
  if (a >= 100) return Math.round(v).toLocaleString('en-US')
  if (a >= 1) return v.toFixed(2).replace(/\.?0+$/, '')
  if (a >= 0.001) return v.toPrecision(2).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
  return v.toExponential(1)
}

/** A loss for the big numbers: plain decimals ("0.82", "0.00078"), never exponent form unless it's tiny. */
export function plain(v: number): string {
  const a = Math.abs(v)
  if (a === 0) return '0'
  if (a >= 100 || a < 1e-6) return short(v)
  return String(Number(v.toPrecision(2)))
}

/** The loss at the first and last frame that carry one, and the epochs between them (only what the frames hold). */
export function lossStat(frames: NetFrame[]): { from?: number; to: number; epochs?: number } | undefined {
  const at = frames.filter((f) => f.loss !== undefined && Number.isFinite(f.loss))
  if (!at.length) return undefined
  const a = at[0]
  const b = at[at.length - 1]
  const epochs = a.epoch !== undefined && b.epoch !== undefined && b.epoch > a.epoch ? b.epoch - a.epoch : undefined
  return { ...(at.length > 1 && a.loss !== b.loss ? { from: a.loss } : {}), to: b.loss!, ...(epochs ? { epochs } : {}) }
}
