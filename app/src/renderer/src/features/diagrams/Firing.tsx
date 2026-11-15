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
import { color, fill, font, glass } from '../../core/theme'
import { WEIGHT_NEG as NEG, WEIGHT_POS as POS } from './NeuralNet'

type Ink = { text: string; label: string; faint: string; ring: string }
const ISLAND: Ink = { text: color.text, label: color.label, faint: color.faint, ring: fill.ring }
const GLASS: Ink = { text: glass.text, label: glass.label, faint: glass.faint, ring: glass.hairline }

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

/** One firing: light a layer (LIGHT_MS), send pulses to the next (TRAVEL_MS), …, then hold. ≈ 1.6 s for 1-4-4-1. */
const FIRE_MS = 1600
const LIGHT_MS = 120
const TRAVEL_MS = 300
/** Train mode: the frames play through in this long, then hold on the last. */
const TRAIN_MS = 6200
const TRAIN_HOLD_MS = 2200
/** A new event's weights tween in from what was on screen. */
const TWEEN_MS = 600

const VW = 380
const VH = 224
const R = 13

export function Firing({ data, compact = false }: { data: Record<string, unknown>; compact?: boolean }): ReactNode {
  const ink = compact ? GLASS : ISLAND
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

  // ---- which frame is on screen ------------------------------------------------------------
  let frame = frames[frames.length - 1]
  let trainP = 1
  if (frame && mode === 'train' && frames.length > 1 && !reduced) {
    const local = t % (TRAIN_MS + TRAIN_HOLD_MS)
    trainP = clamp01(local / TRAIN_MS)
    const at = trainP * (frames.length - 1)
    const i = Math.min(frames.length - 2, Math.floor(at))
    frame = mix(frames[i], frames[i + 1], at - i)
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

  // ---- the firing clock: how far the signal has got, and the pulse on the way ---------------
  let reached = L
  let pulse: { from: number; p: number } | undefined
  if (!reduced) {
    const local = t % FIRE_MS
    reached = -1
    let at = 0
    for (let l = 0; l <= L; l++) {
      if (local < at) break
      reached = l
      at += LIGHT_MS
      if (l === L || local < at) break
      if (local < at + TRAVEL_MS) {
        pulse = { from: l, p: (local - at) / TRAVEL_MS }
        break
      }
      at += TRAVEL_MS
    }
  }

  // ---- geometry: four evenly spaced columns, each layer centered vertically -----------------
  const padX = 46
  const top = 14
  const bottom = VH - 30
  const pos = layers.map((n, l) => {
    const cx = padX + (L ? (l * (VW - 2 * padX)) / L : 0)
    const gap = Math.min(44, (bottom - top) / Math.max(1, n))
    const mid = (top + bottom) / 2
    return Array.from({ length: n }, (_, i) => ({ x: cx, y: mid + (i - (n - 1) / 2) * gap }))
  })
  const maxW = Math.max(1, ...frame.W.flat(2).map(Math.abs))
  const bright = (l: number, i: number): number => (l <= reached ? clamp01(Math.abs(acts[l]?.[i] ?? 0)) : 0)

  const net = (
    <svg viewBox={`0 0 ${VW} ${VH}`} width="100%" className="mx-auto block max-w-full" style={{ fontFamily: font.ui, maxWidth: compact ? undefined : 560 }}>
      {/* Edges */}
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
                strokeOpacity={s < 0.01 ? 0 : 0.12 + 0.78 * s}
                strokeWidth={0.5 + 3 * s}
                strokeLinecap="round"
              />
            )
          })
        )
      )}

      {/* Pulses travelling to the next layer: brightness ∝ |w| · activation */}
      {pulse &&
        frame.W[pulse.from]?.flatMap((row, i) =>
          row.map((w, j) => {
            const a = pos[pulse.from]?.[i]
            const b = pos[pulse.from + 1]?.[j]
            if (!a || !b) return null
            const s = Math.min(1, Math.abs(w) / maxW) * clamp01(Math.abs(acts[pulse.from]?.[i] ?? 0))
            if (s < 0.03) return null
            const p = ease(pulse.p)
            return (
              <circle
                key={`p${i}-${j}`}
                cx={lerp(a.x, b.x, p)}
                cy={lerp(a.y, b.y, p)}
                r={1.8 + 2.6 * s}
                fill={w >= 0 ? POS : NEG}
                opacity={0.3 + 0.7 * s}
              />
            )
          })
        )}

      {/* Neurons: fill brightness = activation, thin outline */}
      {pos.map((col, l) =>
        col.map((p, i) => (
          <circle key={`n${l}-${i}`} cx={p.x} cy={p.y} r={R} fill={ink.text} fillOpacity={0.05 + 0.9 * bright(l, i)} stroke={ink.ring} strokeWidth={1} />
        ))
      )}

      {/* Labels, outside the nodes */}
      {pos[0].map((p, i) => (
        <text key={`in${i}`} x={p.x - R - 7} y={p.y + 4.5} textAnchor="end" fontSize={13} fontStyle="italic" fill={ink.label}>
          {inNames[i] ?? ''}
        </text>
      ))}
      {pos[L].map((p, i) => (
        <text key={`out${i}`} x={p.x + R + 7} y={p.y + 4.5} fontSize={13} fontStyle="italic" fill={ink.label}>
          {outNames[i] ?? ''}
        </text>
      ))}
      {pos.slice(1, L).map((col, h) => (
        <text key={`h${h}`} x={col[0].x} y={VH - 8} textAnchor="middle" fontSize={11} fill={ink.faint}>
          hidden {h + 1}
        </text>
      ))}
    </svg>
  )

  const losses = frames.map((f) => f.loss).filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  const num = { fontVariantNumeric: 'tabular-nums' } as const
  return (
    <div data-part="nn-firing">
      {net}
      {(frame.epoch !== undefined || frame.loss !== undefined) && (
        <div className="mt-[4px] flex items-center gap-[14px] px-[2px] text-[13px] leading-[18px]" style={num}>
          {frame.epoch !== undefined && (
            <span style={{ color: ink.faint }}>
              epoch <span style={{ color: ink.text }}>{frame.epoch.toLocaleString('en-US')}</span>
            </span>
          )}
          {frame.loss !== undefined && (
            <span style={{ color: ink.faint }}>
              loss <span style={{ color: ink.text, fontWeight: 600 }}>{frame.loss < 0.01 ? frame.loss.toExponential(1) : frame.loss.toFixed(3)}</span>
            </span>
          )}
          <span className="flex-1" />
          {losses.length > 1 && <Sparkline values={losses} upTo={mode === 'train' ? trainP : 1} ink={ink} />}
        </div>
      )}
    </div>
  )
}

/** The loss so far, falling (log scale so the long tail still reads). */
function Sparkline({ values, upTo, ink }: { values: number[]; upTo: number; ink: Ink }): ReactNode {
  const w = 96
  const h = 20
  const logs = values.map((v) => Math.log(Math.max(v, 1e-9)))
  const hi = Math.max(...logs)
  const lo = Math.min(...logs)
  const span = hi - lo || 1
  const n = Math.max(2, Math.round(upTo * (values.length - 1)) + 1)
  const pts = logs.slice(0, n).map((v, i) => `${((i / (values.length - 1)) * w).toFixed(1)},${(2 + ((hi - v) / span) * (h - 4)).toFixed(1)}`)
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label="loss" className="shrink-0">
      <polyline points={pts.join(' ')} fill="none" stroke={ink.text} strokeOpacity={0.8} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
