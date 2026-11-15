/**
 * Mockup 12's small pictures of the lesson's own network, drawn from the diagrams the engine pushed (net.ts):
 * the header thumbnail, the loss over training and the trained network's fit against the lesson's targets.
 * Neutral ink only (no hue): the network's weights are white at an opacity of |w|, negative ones dashed.
 */
import type { ReactNode } from 'react'
import { color, fill, font } from '../../core/theme'
import { short, type Net } from './net'

/** The network, small: one column per layer, every edge at an opacity of |w|, neurons lit by their activation. */
export function NetThumb({ net, w = 196, h = 78 }: { net: Net; w?: number; h?: number }): ReactNode {
  const f = net.frames[net.frames.length - 1]
  const L = net.layers
  const padX = 16
  const padY = 12
  const x = (k: number): number => padX + ((w - 2 * padX) * k) / Math.max(1, L.length - 1)
  const y = (k: number, i: number): number => (L[k] <= 1 ? h / 2 : padY + ((h - 2 * padY) * i) / (L[k] - 1))
  const maxW = Math.max(1e-6, ...f.W.flat(2).map(Math.abs))
  const maxA = Math.max(1e-6, ...(f.a ?? []).flat().map(Math.abs))
  return (
    <svg width={w} height={h} className="block" data-net-thumb>
      {f.W.map((m, k) =>
        m.map((row, i) =>
          row.map((v, j) => (
            <line
              key={`${k}-${i}-${j}`}
              x1={x(k)}
              y1={y(k, i)}
              x2={x(k + 1)}
              y2={y(k + 1, j)}
              stroke={color.text}
              strokeOpacity={0.08 + 0.55 * (Math.abs(v) / maxW)}
              strokeWidth={0.6 + 1.4 * (Math.abs(v) / maxW)}
              strokeDasharray={v < 0 ? '2 2' : undefined}
            />
          ))
        )
      )}
      {L.map((n, k) =>
        Array.from({ length: n }, (_, i) => {
          const a = f.a?.[k]?.[i]
          const lit = a === undefined ? 0.6 : 0.25 + 0.75 * (Math.abs(a) / maxA)
          return <circle key={`${k}-${i}`} cx={x(k)} cy={y(k, i)} r={k === 0 || k === L.length - 1 ? 6 : 5} fill={color.text} fillOpacity={lit} stroke={fill.ring} strokeWidth={1} />
        })
      )}
    </svg>
  )
}

const AXIS = 'text-[11px] leading-none'
const mono = { fontFamily: font.mono }

/** Loss over epochs on a log scale, first and last values marked. */
export function LossChart({ pts, w, h = 78 }: { pts: Array<{ epoch: number; loss: number }>; w: number; h?: number }): ReactNode {
  const pad = { l: 10, r: 10, t: 20, b: 20 }
  const e0 = pts[0].epoch
  const e1 = pts[pts.length - 1].epoch
  const logs = pts.map((p) => Math.log10(p.loss))
  const lo = Math.min(...logs)
  const hi = Math.max(...logs)
  const X = (e: number): number => pad.l + ((w - pad.l - pad.r) * (e - e0)) / Math.max(1, e1 - e0)
  const Y = (l: number): number => pad.t + ((h - pad.t - pad.b) * (hi - l)) / Math.max(1e-9, hi - lo)
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.epoch).toFixed(1)},${Y(logs[i]).toFixed(1)}`).join(' ')
  const last = pts[pts.length - 1]
  return (
    <div className="relative rounded-[12px]" style={{ width: w, height: h, background: fill.field, boxShadow: `inset 0 0 0 1px ${fill.fieldBorder}` }} data-loss-chart>
      <svg width={w} height={h} className="absolute left-0 top-0">
        <path d={d} fill="none" stroke={color.text} strokeWidth={1.6} strokeLinejoin="round" />
        <circle cx={X(e0)} cy={Y(logs[0])} r={2.5} fill={color.text} />
        <circle cx={X(e1)} cy={Y(logs[logs.length - 1])} r={3} fill={color.text} />
      </svg>
      <span className={`absolute ${AXIS}`} style={{ left: X(e0) + 6, top: Math.max(4, Y(logs[0]) - 4), color: color.text, ...mono }}>
        {short(pts[0].loss)}
      </span>
      <span className={`absolute ${AXIS}`} style={{ right: pad.r + 4, top: Math.max(4, Y(logs[logs.length - 1]) - 16), color: color.text, ...mono }}>
        {short(last.loss)}
      </span>
      <span className={`absolute ${AXIS}`} style={{ left: pad.l, bottom: 5, color: color.faint, ...mono }}>
        epoch {e0.toLocaleString('en-US')}
      </span>
      <span className={`absolute ${AXIS}`} style={{ right: pad.r, bottom: 5, color: color.faint, ...mono }}>
        {e1.toLocaleString('en-US')}
      </span>
    </div>
  )
}

/** The trained network's curve (solid) over the lesson's targets (dashed, with their points). */
export function FitChart({ fit, w, h = 78 }: { fit: { xs: number[]; ys: number[]; samples: number[]; targets: number[] }; w: number; h?: number }): ReactNode {
  const pad = { l: 12, r: 12, t: 24, b: 20 }
  const all = [...fit.ys, ...fit.targets]
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const x0 = fit.xs[0]
  const x1 = fit.xs[fit.xs.length - 1]
  const X = (x: number): number => pad.l + ((w - pad.l - pad.r) * (x - x0)) / Math.max(1e-9, x1 - x0)
  const Y = (y: number): number => pad.t + ((h - pad.t - pad.b) * (hi - y)) / Math.max(1e-9, hi - lo)
  const order = fit.samples.map((s, i) => [s, fit.targets[i]] as const).sort((a, b) => a[0] - b[0])
  const target = order.map(([s, t], i) => `${i ? 'L' : 'M'}${X(s).toFixed(1)},${Y(t).toFixed(1)}`).join(' ')
  const net = fit.xs.map((x, i) => `${i ? 'L' : 'M'}${X(x).toFixed(1)},${Y(fit.ys[i]).toFixed(1)}`).join(' ')
  return (
    <div className="relative rounded-[12px]" style={{ width: w, height: h, background: fill.field, boxShadow: `inset 0 0 0 1px ${fill.fieldBorder}` }} data-fit-chart>
      <svg width={w} height={h} className="absolute left-0 top-0">
        <path d={target} fill="none" stroke={color.faint} strokeWidth={1.4} strokeDasharray="3 3" />
        {order.map(([s, t]) => (
          <circle key={s} cx={X(s)} cy={Y(t)} r={2} fill={color.faint} />
        ))}
        <path d={net} fill="none" stroke={color.text} strokeWidth={1.8} strokeLinejoin="round" />
      </svg>
      <span className={`absolute flex items-center gap-[10px] ${AXIS}`} style={{ left: pad.l, top: 7, color: color.label }}>
        <span className="flex items-center gap-[5px]">
          target
          <svg width="14" height="4">
            <path d="M0 2 H14" stroke={color.faint} strokeWidth="1.4" strokeDasharray="3 2" />
          </svg>
        </span>
        <span className="flex items-center gap-[5px]">
          your net
          <svg width="14" height="4">
            <path d="M0 2 H14" stroke={color.text} strokeWidth="1.8" />
          </svg>
        </span>
      </span>
      <span className={`absolute ${AXIS}`} style={{ left: pad.l, bottom: 5, color: color.faint, ...mono }}>
        {short(x0)}
      </span>
      <span className={`absolute ${AXIS}`} style={{ right: pad.r, bottom: 5, color: color.faint, ...mono }}>
        {short(x1)}
      </span>
    </div>
  )
}
