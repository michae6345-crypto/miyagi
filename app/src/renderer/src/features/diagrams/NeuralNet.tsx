/**
 * Feature: diagrams. A live neural network, drawn the way people first understand one: every neuron a circle lit by its
 * activation (0 dark → 1 white, its value inside), every weight a line (blue pushes the next neuron up, brown pushes it
 * down; thicker = stronger), and signals firing through it.
 *
 * Used when a `network` diagram carries real weights (extra fields, the contract allows adding them):
 *   frames  : [{ epoch, loss, W: number[][], b: number[][] }]  W[l] is layer l → l+1, row-major (from i, to j at i*n+j)
 *   samples : the inputs to cycle through (e.g. the 4 XOR rows) · targets: what each should give
 *   mode    : 'forward'  signals fire left → right for each sample, with the last frame's weights
 *             'backward' the output's error flows right → left along the same weights
 *             'train'    the weights move through the frames (epoch, loss) while ŷ for every sample settles
 * Everything (labels, sizes, values) comes from the data; nothing here knows the lesson.
 *
 * Colors: Adrian asked for the classic look (Sat Nov 14): blue / brown for weight sign, white for activation. They
 * live here only, for weights; status colors keep their meaning (green is never used here).
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'
import { color, fill, font, glass } from '../../core/theme'

const POS = '#58C4DD'
const NEG = '#C08552'
/** The weight-sign colors, shared with the static network diagram (Diagram.tsx). */
export const WEIGHT_POS = POS
export const WEIGHT_NEG = NEG

/** Island (black HUD) or glass (the drawer: flips with Settings → Appearance). Status colors never appear here. */
type Ink = { text: string; label: string; faint: string; ring: string; lit: string; highlight: string; track: string }
const ISLAND: Ink = { text: color.text, label: color.label, faint: color.faint, ring: fill.ring, lit: color.onAccent, highlight: fill.highlight, track: fill.track }
const GLASS: Ink = { text: glass.text, label: glass.label, faint: glass.faint, ring: glass.hairline, lit: glass.buttonText, highlight: glass.field, track: glass.track }

type Frame = { epoch: number; loss: number; W: number[][]; b: number[][] }
type Mode = 'forward' | 'backward' | 'train'

const W = 600
const H = 262
const NET_W = 380
const R = 19

const squash: Record<string, (z: number) => number> = {
  sigmoid: (z) => 1 / (1 + Math.exp(-z)),
  tanh: (z) => (Math.tanh(z) + 1) / 2,
  relu: (z) => Math.min(1, Math.max(0, z))
}

/** Every layer's activations for one input. */
function forward(f: Frame, layers: number[], x: number[], act: (z: number) => number): number[][] {
  const out = [x ?? []]
  for (let l = 0; l < layers.length - 1; l++) {
    const prev = out[l]
    const next: number[] = []
    for (let j = 0; j < layers[l + 1]; j++) {
      // A frame may carry only epoch / loss (a live run line without weights): missing weights count as 0, never throw.
      let z = f.b?.[l]?.[j] ?? 0
      for (let i = 0; i < layers[l]; i++) z += (prev?.[i] ?? 0) * (f.W?.[l]?.[i * layers[l + 1] + j] ?? 0)
      next.push(act(z))
    }
    out.push(next)
  }
  return out
}

const lerp = (a: number, b: number, t: number): number => a + (b - a) * t
function mix(a: Frame, b: Frame, t: number): Frame {
  return {
    epoch: Math.round(lerp(a.epoch, b.epoch, t)),
    loss: Math.exp(lerp(Math.log(Math.max(a.loss, 1e-9)), Math.log(Math.max(b.loss, 1e-9)), t)),
    W: (a.W ?? b.W ?? []).map((row, l) => row.map((v, k) => lerp(v, b.W?.[l]?.[k] ?? v, t))),
    b: (a.b ?? b.b ?? []).map((row, l) => row.map((v, k) => lerp(v, b.b?.[l]?.[k] ?? v, t)))
  }
}

/** Milliseconds since mount, every frame (stops when reduced motion is on). */
function useTime(run: boolean): number {
  const [t, setT] = useState(0)
  const start = useRef(0)
  useEffect(() => {
    if (!run) return
    let id = 0
    start.current = performance.now()
    const tick = (now: number): void => {
      setT(Math.max(0, now - start.current))  // a rAF timestamp can precede the effect's performance.now()
      id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [run])
  return t
}

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v))
const ease = (v: number): number => {
  const c = clamp01(v)
  return c * c * (3 - 2 * c)
}

/** One sample's forward pass: inputs, then each layer's signals and fill, then a hold. */
const STAGE_MS = 520
const FILL_MS = 260
const HOLD_MS = 900
const TRAIN_MS = 6200
const TRAIN_HOLD_MS = 2600
const TRAIN_SAMPLE_MS = 760

/**
 * compact: the drawer's right-hand panel (Michael, Sun 1:55 AM). Just the network at the panel's width, with the
 * epoch / loss and a one-line want / gets strip under it in HTML (the full-size readout would shrink to unreadable).
 */
export function NeuralNet({ data, compact = false }: { data: Record<string, unknown>; compact?: boolean }): ReactNode {
  const ink = compact ? GLASS : ISLAND
  const layers = (data.layers as number[]) ?? []
  const frames = (data.frames as Frame[]) ?? []
  const samples = (data.samples as number[][]) ?? []
  const targets = (data.targets as number[]) ?? []
  const mode = ((data.mode as string) ?? 'forward') as Mode
  const inputs = (data.inputs as string[]) ?? []
  const output = (data.output as string) ?? ''
  const act = squash[(data.activation as string) ?? 'sigmoid'] ?? squash.sigmoid
  const reduced = !!useReducedMotion()
  const t = useTime(!reduced && frames.length > 0 && samples.length > 0)

  // Where every neuron sits.
  const pos = useMemo(() => {
    const cols = layers.length
    return layers.map((n, l) => {
      const x = 46 + (cols > 1 ? (l * (NET_W - 92)) / (cols - 1) : 0)
      const gap = Math.min(56, (H - 70) / Math.max(1, n))
      const y0 = (H - 24) / 2 - ((n - 1) * gap) / 2
      return Array.from({ length: n }, (_, i) => ({ x, y: y0 + i * gap }))
    })
  }, [layers])

  if (!frames.length || !samples.length || layers.length < 2) return null

  // ---- the clock -------------------------------------------------------------------------
  const L = layers.length - 1
  const perSample = L * (STAGE_MS + FILL_MS) + FILL_MS + HOLD_MS
  let frame = frames[frames.length - 1]
  let sample = 0
  /** Forward: how far the signal has got, in layers (0 = inputs lit … L = output lit), plus the travelling pulse. */
  let reached = L
  let pulse: { from: number; p: number; back?: boolean } | undefined
  let trainP = 1

  if (reduced) {
    sample = Math.min(1, samples.length - 1)
  } else if (mode === 'train') {
    const cycle = TRAIN_MS + TRAIN_HOLD_MS
    const local = t % cycle
    trainP = clamp01(local / TRAIN_MS)
    const at = trainP * (frames.length - 1)
    const i = Math.min(frames.length - 2, Math.floor(at))
    frame = frames.length > 1 ? mix(frames[i], frames[i + 1], at - i) : frames[0]
    sample = Math.floor(t / TRAIN_SAMPLE_MS) % samples.length
  } else if (mode === 'backward') {
    sample = Math.min(1, samples.length - 1)
    const stage = STAGE_MS + 200
    const cycle = L * stage + 1400
    const local = t % cycle
    const k = Math.floor(local / stage)
    if (k < L) pulse = { from: L - k, p: (local % stage) / STAGE_MS, back: true }
  } else {
    sample = Math.floor(t / perSample) % samples.length
    const local = t % perSample
    reached = 0
    let at = FILL_MS
    for (let l = 0; l < L; l++) {
      if (local < at) break
      if (local < at + STAGE_MS) {
        pulse = { from: l, p: (local - at) / STAGE_MS }
        break
      }
      at += STAGE_MS
      reached = l + 1
      at += FILL_MS
    }
  }

  if (!(sample >= 0 && sample < samples.length)) sample = 0
  const acts = forward(frame ?? frames[0], layers, samples[sample] ?? [], act)
  const shown = (l: number, i: number): number => {
    if (mode !== 'forward' || reduced) return acts[l][i]
    if (l > reached) return 0
    return acts[l][i]
  }
  const y = acts[L][0]
  const target = targets[sample]
  const err = target !== undefined ? y - target : undefined

  // Strongest weight on screen sets the scale (so a zero network reads as empty, not as faint lines).
  const maxW = Math.max(1.5, ...(frame.W ?? []).flat().map(Math.abs))

  // Room for the input names left of the first column and the output name right of the last (13 px text, ~7.4 px a
  // glyph), so the drawer's compact view scales the whole thing into its width instead of cutting the output off.
  const padL = Math.max(0, Math.ceil(Math.max(0, ...inputs.map((t) => String(t ?? '').length)) * 7.4 + R + 8 - 40))
  const padR = Math.max(0, Math.ceil(String(output ?? '').length * 7.4 + R + 8 - (NET_W - (pos[L]?.[0]?.x ?? NET_W - 46)) + 6))
  const net = (
    <svg
      width={compact ? '100%' : W}
      height={compact ? undefined : H}
      viewBox={compact ? `${-padL} 0 ${NET_W + padL + padR} ${H}` : `0 0 ${W} ${H}`}
      className="mx-auto block max-w-full"
      style={{ fontFamily: font.ui }}
    >
      {/* Weights */}
      {pos.slice(0, -1).map((col, l) =>
        col.flatMap((a, i) =>
          pos[l + 1].map((b, j) => {
            const w = frame.W?.[l]?.[i * layers[l + 1] + j] ?? 0
            const m = Math.min(1, Math.abs(w) / maxW)
            return (
              <line
                key={`w${l}-${i}-${j}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={w >= 0 ? POS : NEG}
                strokeOpacity={m < 0.01 ? 0 : 0.18 + 0.72 * m}
                strokeWidth={0.8 + 3.4 * m}
                strokeLinecap="round"
              />
            )
          })
        )
      )}

      {/* Signals travelling along the weights */}
      {pulse &&
        pos[pulse.back ? pulse.from - 1 : pulse.from].flatMap((a, i) =>
          pos[pulse.back ? pulse.from : pulse.from + 1].map((b, j) => {
            const l = pulse.back ? pulse.from - 1 : pulse.from
            const w = frame.W?.[l]?.[i * layers[l + 1] + j] ?? 0
            const m = Math.min(1, Math.abs(w) / maxW)
            const strength = pulse.back ? m : m * acts[l][i]
            if (strength < 0.04) return null
            const p = ease(pulse.p)
            const [sx, sy, ex, ey] = pulse.back ? [b.x, b.y, a.x, a.y] : [a.x, a.y, b.x, b.y]
            return (
              <circle
                key={`p${l}-${i}-${j}`}
                cx={lerp(sx, ex, p)}
                cy={lerp(sy, ey, p)}
                r={2.2 + 2.4 * strength}
                fill={pulse.back ? NEG : w >= 0 ? POS : NEG}
                opacity={0.35 + 0.65 * strength}
              />
            )
          })
        )}

      {/* Neurons */}
      {pos.map((col, l) =>
        col.map((p, i) => {
          const a = shown(l, i)
          const lit = a > 0.55
          const blamed = mode === 'backward' && pulse && l === pulse.from - 1 && pulse.p > 0.85
          return (
            <g key={`n${l}-${i}`}>
              <circle cx={p.x} cy={p.y} r={R} fill={ink.text} fillOpacity={0.04 + 0.92 * a} stroke={blamed ? NEG : ink.ring} strokeWidth={blamed ? 2.4 : 1.2} />
              <text x={p.x} y={p.y + 4} textAnchor="middle" fontSize={11} fontWeight={600} fill={lit ? ink.lit : ink.text} style={{ fontVariantNumeric: 'tabular-nums' }}>
                {l === 0 ? String(Math.round(a * 100) / 100) : a.toFixed(2)}
              </text>
            </g>
          )
        })
      )}

      {/* Labels: input names, the output name, layer captions */}
      {pos[0].map((p, i) => (
        <text key={`in${i}`} x={p.x - R - 8} y={p.y + 4} textAnchor="end" fontSize={13} fill={ink.label}>
          {inputs[i] ?? ''}
        </text>
      ))}
      <text x={pos[L][0].x + R + 8} y={pos[L][0].y + 4} fontSize={13} fill={ink.label}>
        {output}
      </text>
      {pos.map((col, l) => (
        <text key={`cap${l}`} x={col[0].x} y={H - 6} textAnchor="middle" fontSize={11} fill={ink.faint}>
          {l === 0 ? 'inputs' : l === L ? 'output' : `hidden · ${(data.activation as string) ?? ''}`}
        </text>
      ))}

      {!compact && <Readout ink={ink} x={NET_W + 18} frames={frames} frame={frame} mode={mode} samples={samples} targets={targets} sample={sample} layers={layers} act={act} err={err} reduced={reduced} trainP={trainP} />}
    </svg>
  )
  if (!compact) return net
  return (
    <div>
      {net}
      <CompactReadout ink={ink} frame={frame} mode={mode} samples={samples} targets={targets} sample={sample} layers={layers} act={act} err={err} />
    </div>
  )
}

/** Under the drawer's network: epoch · loss while training (or the error going back), then want / gets per sample (2 × 2). */
function CompactReadout(props: {
  ink: Ink
  frame: Frame
  mode: Mode
  samples: number[][]
  targets: number[]
  sample: number
  layers: number[]
  act: (z: number) => number
  err?: number
}): ReactNode {
  const { ink, frame, mode, samples, targets, sample, layers, act, err } = props
  const num = { fontVariantNumeric: 'tabular-nums' } as const
  return (
    <div className="mt-[6px] px-[2px]">
      {mode === 'train' && (
        <div data-part="nn-train" className="flex items-baseline gap-[14px] text-[13px] leading-[18px]" style={num}>
          <span style={{ color: ink.faint }}>
            epoch <span style={{ color: ink.text }}>{frame.epoch.toLocaleString('en-US')}</span>
          </span>
          <span style={{ color: ink.faint }}>
            loss <span style={{ color: ink.text, fontWeight: 600 }}>{frame.loss < 0.01 ? frame.loss.toExponential(1) : frame.loss.toFixed(4)}</span>
          </span>
        </div>
      )}
      {mode === 'backward' && err !== undefined && (
        <div className="text-[13px] leading-[18px]" style={{ ...num, color: ink.label }}>
          error ŷ − y = {err >= 0 ? '+' : '−'}
          {Math.abs(err).toFixed(2)}
        </div>
      )}
      <div className="mt-[4px] grid gap-[4px]" style={{ gridTemplateColumns: `repeat(${Math.min(2, samples.length)}, minmax(0, 1fr))` }}>
        {samples.map((s, k) => {
          const out = forward(frame, layers, s, act)[layers.length - 1][0]
          return (
            <div
              key={k}
              className="rounded-[8px] px-[6px] py-[3px] text-[11.5px] leading-[15px]"
              style={{ ...num, background: k === sample ? ink.highlight : 'transparent', opacity: k === sample ? 1 : 0.6, color: ink.text }}
            >
              <div style={{ fontFamily: font.mono }}>{s.join(' ')}</div>
              <div style={{ color: ink.faint }}>
                want {targets[k] ?? '–'} · <span style={{ color: ink.text }}>{out.toFixed(2)}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Right of the network: every sample with its target and ŷ (the current one lit), and the epoch / loss while training. */
function Readout(props: {
  ink: Ink
  x: number
  frames: Frame[]
  frame: Frame
  mode: Mode
  samples: number[][]
  targets: number[]
  sample: number
  layers: number[]
  act: (z: number) => number
  err?: number
  reduced: boolean
  trainP: number
}): ReactNode {
  const { ink, x, frame, mode, samples, targets, sample, layers, act, err } = props
  const rowH = 30
  const top = 34
  const barW = 74
  return (
    <g>
      <text x={x} y={18} fontSize={11} fill={ink.faint}>
        input
      </text>
      <text x={x + 62} y={18} fontSize={11} fill={ink.faint}>
        want
      </text>
      <text x={x + 104} y={18} fontSize={11} fill={ink.faint}>
        gets
      </text>
      {samples.map((s, k) => {
        const yk = top + k * rowH
        const out = forward(frame, layers, s, act)[layers.length - 1][0]
        const on = k === sample
        return (
          <g key={k} opacity={on ? 1 : 0.55}>
            {on && <rect x={x - 8} y={yk - 6} width={W - x} height={rowH - 4} rx={8} fill={ink.highlight} />}
            <text x={x} y={yk + 12} fontSize={13} fill={ink.text} style={{ fontVariantNumeric: 'tabular-nums', fontFamily: font.mono }}>
              {s.join(' ')}
            </text>
            <text x={x + 70} y={yk + 12} fontSize={13} fill={ink.text} style={{ fontVariantNumeric: 'tabular-nums', fontFamily: font.mono }}>
              {targets[k] ?? ''}
            </text>
            <rect x={x + 104} y={yk + 2} width={barW} height={12} rx={6} fill={ink.track} />
            <rect x={x + 104} y={yk + 2} width={Math.max(2, barW * out)} height={12} rx={6} fill={ink.text} />
            <text x={x + 104 + barW + 8} y={yk + 12} fontSize={12} fill={ink.label} style={{ fontVariantNumeric: 'tabular-nums' }}>
              {out.toFixed(2)}
            </text>
          </g>
        )
      })}
      {mode === 'train' && (
        <text x={x} y={top + samples.length * rowH + 16} fontSize={12} fill={ink.label} style={{ fontVariantNumeric: 'tabular-nums' }}>
          epoch {frame.epoch.toLocaleString('en-US')} · loss {frame.loss < 0.01 ? frame.loss.toExponential(1) : frame.loss.toFixed(4)}
        </text>
      )}
      {mode === 'backward' && err !== undefined && (
        <text x={x} y={top + samples.length * rowH + 16} fontSize={12} fill={ink.label} style={{ fontVariantNumeric: 'tabular-nums' }}>
          error ŷ − y = {err >= 0 ? '+' : '−'}
          {Math.abs(err).toFixed(2)}
        </text>
      )}
    </g>
  )
}
