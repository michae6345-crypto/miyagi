/**
 * Feature: diagrams. The demo network, drawn like 3Blue1Brown's (Michael, Sun 2:32 AM): a symmetrical 1-4-4-1, four
 * evenly spaced columns, each layer centered; neurons are circles whose fill brightness is their activation; every
 * edge between adjacent layers is blue (positive) or brown (negative), width and opacity ∝ |w|. About every 1.6 s the
 * network fires: the input lights, pulses travel along the edges (brightness ∝ |w|·activation), each layer lights as
 * they arrive, then the output. Under it: epoch, loss and a small loss sparkline.
 *
 * Payload (the `network` diagram, additive):
 *   layers  : [1,4,4,1] (inferred from W when missing)
 *   labels  : { input: ["x"], output: ["y"] }   drawn OUTSIDE the nodes; "hidden 1" / "hidden 2" under the columns
 *   mode    : forward | train | stuck
 *   frames  : [{ epoch, loss, input, W: [W1 1x4, W2 4x4, W3 4x1], b, a: [[x],[4],[4],[y]] }]
 *             W[k][i][j] is the weight from neuron i of layer k to neuron j of layer k+1; `a` is every activation.
 * In train mode the frames play through (weights and activations interpolated); a new event's weights tween in from
 * what was on screen. Reduced motion: no pulses, no tweens, everything lit.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'
import { color, font } from '../../core/theme'

/**
 * Mockup 11 (Michael, Sun 2:58 AM): the network sits on its own black card in both appearances (the island color), so
 * the inks are the island's. The weight-sign blue / brown are diagram-only, like NeuralNet's; status colors never
 * appear here. Neuron rings at 55% white and card rules at 7-8% white come from the mockup.
 */
const POS = '#5CB0F0'
const NEG = '#D68442'
const INK = { text: color.text, label: color.label, faint: color.faint, ring: 'rgba(255,255,255,.55)', rule: 'rgba(255,255,255,.07)', edge: 'rgba(255,255,255,.08)' }

export type FiringFrame = { epoch?: number; loss?: number; input?: number[]; W: number[][][]; b?: number[][]; a?: number[][] }
type RawFrame = { epoch?: number; loss?: number; input?: number[]; W?: unknown; b?: number[][]; a?: number[][] }

/** Nested W (W[k][i][j]), or flat row-major W[k][i*n+j] (the older 2-4-1 frames) when the layer sizes are known. */
function nestW(W: unknown, layers: number[] | undefined): number[][][] | undefined {
  if (!Array.isArray(W)) return undefined
  if (W.every((m) => Array.isArray(m) && m.every((r) => Array.isArray(r)))) return W as number[][][]
  if (!layers) return undefined
  return (W as number[][]).map((flat, k) => {
    const n = layers[k + 1] ?? 1
    return Array.from({ length: layers[k] ?? 0 }, (_, i) => Array.from({ length: n }, (_, j) => Number(flat?.[i * n + j] ?? 0)))
  })
}

/** Layer sizes from the nested weights: rows of W[0], then the columns of each W[k]. */
export function inferLayers(W: number[][][]): number[] {
  if (!W.length) return []
  return [W[0].length, ...W.map((m) => m[0]?.length ?? 0)]
}

/** Does this `network` payload use the 1-4-4-1 shape (nested W, per-frame activations or no samples)? */
export function isFiringNetwork(data: Record<string, unknown>): boolean {
  const frames = data.frames as RawFrame[] | undefined
  if (!Array.isArray(frames) || !frames.length) return false
  const f = frames[0]
  if (Array.isArray(f.a)) return true
  if (Array.isArray((f.W as unknown[] | undefined)?.[0]) && Array.isArray((f.W as unknown[][])[0]?.[0])) return true
  return !Array.isArray(data.samples)
}

const squash: Record<string, (z: number) => number> = {
  sigmoid: (z) => 1 / (1 + Math.exp(-z)),
  tanh: (z) => Math.tanh(z),
  relu: (z) => Math.max(0, z),
  linear: (z) => z
}

/** Activations for one input when the frame doesn't carry them (last layer linear, like a regression head). */
function forward(f: FiringFrame, layers: number[], x: number[], act: (z: number) => number): number[][] {
  const out = [x]
  for (let k = 0; k < layers.length - 1; k++) {
    const prev = out[k]
    const last = k === layers.length - 2
    out.push(
      Array.from({ length: layers[k + 1] }, (_, j) => {
        let z = f.b?.[k]?.[j] ?? 0
        for (let i = 0; i < layers[k]; i++) z += (prev[i] ?? 0) * (f.W[k]?.[i]?.[j] ?? 0)
        return last ? z : act(z)
      })
    )
  }
  return out
}

const lerp = (a: number, b: number, t: number): number => a + (b - a) * t
/** A loss the way a training script prints it (0.0009, not 9.0e-4); scientific only below 0.0001. */
export const printedLoss = (v: number): string => (v !== 0 && Math.abs(v) < 1e-4 ? v.toExponential(1) : v.toFixed(4))
const clamp01 = (v: number): number => Math.min(1, Math.max(0, v))
const ease = (v: number): number => {
  const c = clamp01(v)
  return c * c * (3 - 2 * c)
}
const mixGrid = (a: number[][] | undefined, b: number[][] | undefined, t: number): number[][] | undefined =>
  a && b ? a.map((row, i) => row.map((v, j) => lerp(v, b[i]?.[j] ?? v, t))) : b ?? a
function mix(a: FiringFrame, b: FiringFrame, t: number): FiringFrame {
  return {
    epoch: a.epoch !== undefined && b.epoch !== undefined ? Math.round(lerp(a.epoch, b.epoch, t)) : b.epoch,
    loss: a.loss !== undefined && b.loss !== undefined ? Math.exp(lerp(Math.log(Math.max(a.loss, 1e-9)), Math.log(Math.max(b.loss, 1e-9)), t)) : b.loss,
    input: b.input,
    W: a.W.map((m, k) => m.map((row, i) => row.map((v, j) => lerp(v, b.W[k]?.[i]?.[j] ?? v, t)))),
    b: mixGrid(a.b, b.b, t),
    a: mixGrid(a.a, b.a, t)
  }
}

/** Milliseconds since mount, every animation frame (off with reduced motion). */
function useClock(run: boolean): number {
  const [t, setT] = useState(0)
  useEffect(() => {
    if (!run) return
    let id = 0
    const start = performance.now()
    const tick = (now: number): void => {
      setT(Math.max(0, now - start))
      id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [run])
  return t
}

/**
 * One firing, 1.6 s (mockup 11): layer l lights at LAYER_AT[l] (LIGHT_MS ease-in, then a FLASH_MS ring), pulses leave
 * layer l at PULSE_AT[l] and take TRAVEL_MS, and from REST_AT the neurons fade back to 14% for the next pass.
 */
const FIRE_MS = 1600
const LAYER_AT = [0, 380, 720, 1060]
const PULSE_AT = [100, 440, 780]
const LIGHT_MS = 140
const FLASH_MS = 480
const TRAVEL_MS = 320
const REST_AT = 1250
const REST_LEVEL = 0.14
/** Train mode: the frames play through once in this long, then hold on the last. Reduced motion: one frame every 2 s. */
const TRAIN_MS = 6200
const STILL_STEP_MS = 2000
/** A new event's weights tween in from what was on screen. */
const TWEEN_MS = 600

const COL = 146
const ROW = 54
const R = 17
const VH = 236
/** The comet tail, as a share of the edge. */
const TAIL = 0.42

/** Activation → neuron fill, grey 14 → 244 by |a|^0.8. */
const greyOf = (v: number): string => {
  const g = Math.round(14 + 230 * Math.pow(clamp01(Math.abs(v)), 0.8))
  return `rgb(${g},${g},${g})`
}

/** Reduced motion: a counter that ticks every STILL_STEP_MS (train frames swap instead of tweening). */
function useStep(run: boolean): number {
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!run) return
    const id = setInterval(() => setN((v) => v + 1), STILL_STEP_MS)
    return () => clearInterval(id)
  }, [run])
  return n
}

/** Mockup beats for 1-4-4-1; other depths spread the last beat evenly. */
const beat = (arr: number[], l: number, n: number): number => (n <= arr.length ? arr[l] : (arr[arr.length - 1] * l) / Math.max(1, n - 1))

export function Firing({ data }: { data: Record<string, unknown>; compact?: boolean }): ReactNode {
  const ink = INK
  const raw = (data.frames as RawFrame[]) ?? []
  const given = Array.isArray(data.layers) ? (data.layers as number[]) : undefined
  const frames: FiringFrame[] = raw.flatMap((f) => {
    const W = nestW(f.W, given)
    return W ? [{ ...f, W } as FiringFrame] : []
  })
  const layers = given ?? (frames[0] ? inferLayers(frames[0].W) : [])
  const mode = (data.mode as string) ?? 'forward'
  const labels = (data.labels as { input?: string[]; output?: string[] } | undefined) ?? {}
  const inNames = labels.input ?? (data.inputs as string[] | undefined) ?? []
  const outNames = labels.output ?? (data.output ? [data.output as string] : [])
  const act = squash[(data.activation as string) ?? 'tanh'] ?? squash.tanh
  const reduced = !!useReducedMotion()
  const t = useClock(!reduced && frames.length > 0)
  const still = useStep(reduced && mode === 'train' && frames.length > 1)

  // ---- which frame is on screen ------------------------------------------------------------
  let frame = frames[frames.length - 1]
  let trainP = 1
  if (frame && mode === 'train' && frames.length > 1) {
    if (reduced) {
      const i = Math.min(still, frames.length - 1)
      frame = frames[i]
      trainP = i / (frames.length - 1)
    } else {
      // Play once and stop on the run's last real row (Michael's test 8: looping replayed numbers the terminal never
      // printed). The weights tween between rows; epoch and loss always show the last real row reached.
      trainP = clamp01(t / TRAIN_MS)
      const at = trainP * (frames.length - 1)
      const i = Math.min(frames.length - 2, Math.floor(at))
      const real = frames[trainP >= 1 ? frames.length - 1 : i]
      frame = { ...mix(frames[i], frames[i + 1], at - i), epoch: real.epoch, loss: real.loss }
    }
  }
  // A new event: tween from the last frame drawn to the new one.
  const shown = useRef<FiringFrame | undefined>(undefined)
  const tween = useRef<{ from: FiringFrame; at: number; key: unknown } | undefined>(undefined)
  if (frame && !reduced && tween.current?.key !== data.frames) {
    const from = shown.current
    tween.current = from && from.W.length === frame.W.length ? { from, at: performance.now(), key: data.frames } : { from: frame, at: 0, key: data.frames }
  }
  if (frame && !reduced && tween.current?.at) {
    const p = (performance.now() - tween.current.at) / TWEEN_MS
    if (p < 1) frame = mix(tween.current.from, frame, ease(p))
  }
  shown.current = frame

  if (!frame || layers.length < 2) return null
  const L = layers.length - 1
  const x = frame.input ?? frame.a?.[0] ?? [0]
  const acts = frame.a && frame.a.length === layers.length ? frame.a : forward(frame, layers, x, act)

  // ---- the firing clock --------------------------------------------------------------------
  const local = reduced ? 0 : t % FIRE_MS
  const rest = reduced ? 1 : 1 - ease((local - REST_AT) / (FIRE_MS - REST_AT)) * (1 - REST_LEVEL)
  const lit = (l: number): number => (reduced ? 1 : Math.pow(clamp01((local - beat(LAYER_AT, l, L + 1)) / LIGHT_MS), 2) * rest)
  const flash = (l: number): number => (reduced ? -1 : (local - beat(LAYER_AT, l, L + 1)) / FLASH_MS)
  const level = (l: number, i: number): number => clamp01(Math.abs(acts[l]?.[i] ?? 0)) * lit(l)

  // ---- geometry: columns COL apart, rows ROW apart, every layer centered --------------------
  const nameW = (names: unknown[]): number => Math.max(0, ...names.map((v) => String(v ?? '').length)) * 7.4 + R + 10
  const padL = Math.max(R + 4, Math.ceil(nameW(inNames)))
  const padR = Math.max(R + 4, Math.ceil(nameW(outNames)))
  const VW = padL + COL * L + padR
  const mid = VH / 2 - 6
  const pos = layers.map((n, l) => {
    const cx = padL + l * COL
    const gap = Math.min(ROW, (VH - 40) / Math.max(1, n))
    return Array.from({ length: n }, (_, i) => ({ x: cx, y: mid + (i - (n - 1) / 2) * gap }))
  })
  const maxW = Math.max(1e-6, ...frame.W.flat(2).map(Math.abs))

  // Comet pulses: a dim tail (~42% of the edge) and a bright nose, brightness 0.28 + 0.72·(|w|·a)^0.8. No halo.
  const pulses: ReactNode[] = []
  if (!reduced) {
    for (let k = 0; k < L; k++) {
      const p = (local - beat(PULSE_AT, k, L)) / TRAVEL_MS
      if (p <= 0 || p >= 1 + TAIL) continue
      frame.W[k]?.forEach((row, i) =>
        row.forEach((w, j) => {
          const a = pos[k]?.[i]
          const b = pos[k + 1]?.[j]
          if (!a || !b) return
          const s = Math.pow(Math.min(1, (Math.abs(w) / maxW) * clamp01(Math.abs(acts[k]?.[i] ?? 0))), 0.8)
          if (s < 0.04) return
          const head = ease(Math.min(1, p))
          const tail = Math.max(0, (p > 1 ? 1 : head) - TAIL + Math.max(0, p - 1))
          if (tail >= head) return
          const at = (f: number): { x: number; y: number } => ({ x: lerp(a.x, b.x, f), y: lerp(a.y, b.y, f) })
          const h = at(head)
          const tl = at(tail)
          const nose = at(Math.max(tail, head - 0.1))
          const bright = 0.28 + 0.72 * s
          const stroke = w >= 0 ? POS : NEG
          const width = 1.2 + 2.2 * s
          pulses.push(
            <g key={`p${k}-${i}-${j}`}>
              <line x1={tl.x} y1={tl.y} x2={h.x} y2={h.y} stroke={stroke} strokeOpacity={bright * 0.45} strokeWidth={width} strokeLinecap="round" />
              <line x1={nose.x} y1={nose.y} x2={h.x} y2={h.y} stroke={stroke} strokeOpacity={bright} strokeWidth={width + 0.6} strokeLinecap="round" />
            </g>
          )
        })
      )
    }
  }

  const net = (
    <svg
      viewBox={`0 0 ${VW} ${VH}`}
      width="100%"
      className="mx-auto block max-w-full"
      style={{ fontFamily: font.ui, maxWidth: 588 }}
      role="img"
      aria-label={`A ${layers.join('-')} neural network firing layer by layer`}
    >
      {frame.W.map((m, k) =>
        m.flatMap((row, i) =>
          row.map((w, j) => {
            const a = pos[k]?.[i]
            const b = pos[k + 1]?.[j]
            if (!a || !b) return null
            const s = Math.min(1, Math.abs(w) / maxW)
            return (
              <line
                key={`e${k}-${i}-${j}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={w >= 0 ? POS : NEG}
                strokeOpacity={0.1 + 0.62 * s}
                strokeWidth={0.6 + 3.4 * s}
                strokeLinecap="round"
              />
            )
          })
        )
      )}
      {pulses}
      {pos.map((col, l) =>
        col.map((p, i) => {
          const f = flash(l)
          const strength = clamp01(Math.abs(acts[l]?.[i] ?? 0))
          return (
            <g key={`n${l}-${i}`}>
              {f > 0 && f < 1 && strength > 0.05 && (
                <circle cx={p.x} cy={p.y} r={R + 2 + 7 * ease(f)} fill="none" stroke={ink.text} strokeOpacity={0.45 * (1 - f) * strength} strokeWidth={1.25} />
              )}
              <circle cx={p.x} cy={p.y} r={R} fill={greyOf(level(l, i))} stroke={ink.ring} strokeWidth={1.25} />
            </g>
          )
        })
      )}
      {pos[0].map((p, i) => (
        <text key={`in${i}`} x={p.x - R - 8} y={p.y + 4.5} textAnchor="end" fontSize={13} fontStyle="italic" fill={ink.label}>
          {inNames[i] ?? ''}
        </text>
      ))}
      {pos[L].map((p, i) => (
        <text key={`out${i}`} x={p.x + R + 8} y={p.y + 4.5} fontSize={13} fontStyle="italic" fill={ink.label}>
          {outNames[i] ?? ''}
        </text>
      ))}
      {pos.slice(1, L).map((col, h) => (
        <text key={`h${h}`} x={col[0].x} y={VH - 6} textAnchor="middle" fontSize={11} fill={ink.faint}>
          hidden {h + 1}
        </text>
      ))}
    </svg>
  )

  const losses = frames.map((f) => f.loss).filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  const total = typeof data.epochs === 'number' ? data.epochs : undefined
  // A preview (data.preview, before any code exists) shows no prediction: those numbers aren't the learner's yet.
  const yhat = data.preview === true ? undefined : acts[L]?.[0]
  const rawTarget = (frame as { target?: unknown }).target ?? data.target ?? (data.targets as unknown[] | undefined)?.[0]
  const target = typeof rawTarget === 'number' ? rawTarget : Array.isArray(rawTarget) && typeof rawTarget[0] === 'number' ? (rawTarget[0] as number) : undefined
  const num = { fontVariantNumeric: 'tabular-nums' } as const
  const key = 'text-[11px] font-semibold uppercase tracking-[.06em]'
  const val = 'text-[19px] font-semibold leading-[24px] tracking-[-.01em]'
  const cell = 'mr-[14px] flex flex-col gap-[2px] border-r pr-[14px]'
  const small = 'ml-[4px] text-[13px] font-medium tracking-normal'
  return (
    <div data-part="nn-firing" className="rounded-[16px] border px-[16px] py-[14px]" style={{ background: color.island, borderColor: ink.edge, color: ink.text }}>
      {net}
      {(frame.epoch !== undefined || frame.loss !== undefined || yhat !== undefined) && (
        <div className="mt-[6px] flex flex-wrap items-stretch gap-y-[8px] border-t pt-[12px]" style={{ ...num, borderColor: ink.rule }}>
          {frame.epoch !== undefined && (
            <div className={cell} style={{ borderColor: ink.rule }}>
              <span className={key} style={{ color: ink.faint }}>
                Epoch
              </span>
              <span className={val}>
                {frame.epoch.toLocaleString('en-US')}
                {total !== undefined && (
                  <small className={small} style={{ color: ink.faint }}>
                    / {total.toLocaleString('en-US')}
                  </small>
                )}
              </span>
            </div>
          )}
          {frame.loss !== undefined && (
            <div className={cell} style={{ borderColor: ink.rule }}>
              <span className={key} style={{ color: ink.faint }}>
                Loss
              </span>
              <span className={val}>{printedLoss(frame.loss)}</span>
            </div>
          )}
          {losses.length > 1 && (
            <div className="flex min-w-[96px] flex-1 flex-col gap-[2px]">
              <span className={key} style={{ color: ink.faint }}>
                Loss over training
              </span>
              <Sparkline values={losses} upTo={mode === 'train' ? trainP : 1} />
            </div>
          )}
          {yhat !== undefined && Number.isFinite(yhat) && (
            <div className="ml-auto flex flex-col items-end gap-[2px] pl-[14px]">
              <span className={key} style={{ color: ink.faint }}>
                Prediction
              </span>
              <span className={val}>
                {yhat.toFixed(3)}
                {target !== undefined && (
                  <small className={small} style={{ color: ink.faint }}>
                    target {target.toFixed(3)}
                  </small>
                )}
              </span>
            </div>
          )}
        </div>
      )}
      <div className="mt-[12px] flex flex-wrap items-center gap-x-[14px] gap-y-[4px] text-[12.5px] leading-[1.4]" style={{ color: ink.label }}>
        <span>
          <Swatch c={POS} />
          positive weight
        </span>
        <span>
          <Swatch c={NEG} />
          negative weight
        </span>
        <span>thicker = stronger, brighter = more active</span>
      </div>
    </div>
  )
}

function Swatch({ c }: { c: string }): ReactNode {
  return <span className="mr-[5px] inline-block h-[3px] w-[14px] rounded-[2px] align-[3px]" style={{ background: c }} />
}

/** The loss so far, falling (log scale so the long tail still reads). */
function Sparkline({ values, upTo }: { values: number[]; upTo: number }): ReactNode {
  const w = 170
  const h = 32
  const logs = values.map((v) => Math.log(Math.max(v, 1e-9)))
  const hi = Math.max(...logs)
  const lo = Math.min(...logs)
  const span = hi - lo || 1
  const n = Math.max(2, Math.round(upTo * (values.length - 1)) + 1)
  const pts = logs.slice(0, n).map((v, i) => `${((i / (values.length - 1)) * w).toFixed(1)},${(3 + ((hi - v) / span) * (h - 6)).toFixed(1)}`)
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-label="loss over training" className="block max-w-[170px]">
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={INK.text}
        strokeOpacity={0.8}
        strokeWidth={1.4}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
