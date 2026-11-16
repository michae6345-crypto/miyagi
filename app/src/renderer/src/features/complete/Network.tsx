/**
 * The learner's own trained network, drawn from the engine's `network` diagram frames (net.ts): one column per
 * layer, every connection at an opacity and width of its |weight|, each neuron lit by its last activation (scaled
 * within its layer). Monochrome, no labels, no hue. A layer wider than MAX_SHOWN shows its first neurons and its size.
 */
import type { ReactNode } from 'react'
import { color, fill } from '../../core/theme'
import type { Net } from './net'

const MAX_SHOWN = 8
const R = 8
/** Vertical step between neurons when there's room; it shrinks to fit a wide layer into MAX_H. */
const STEP = 52
const MAX_H = 220
const COUNT_H = 18

/** The network's drawn height at a given width (so the panel can lay out around it). */
export function netHeight(net: Net): number {
  const most = Math.max(1, ...net.layers.map((n) => Math.min(n, MAX_SHOWN)))
  const counts = net.layers.some((n) => n > MAX_SHOWN) ? COUNT_H : 0
  return Math.min(MAX_H, (most - 1) * STEP + 2 * (R + 1)) + counts
}

export function NetGraph({ net, w }: { net: Net; w: number }): ReactNode {
  const f = net.frames[net.frames.length - 1]
  const L = net.layers
  const shown = L.map((n) => Math.min(n, MAX_SHOWN))
  const most = Math.max(1, ...shown)
  const truncated = L.some((n) => n > MAX_SHOWN)
  const h = netHeight(net)
  const body = h - (truncated ? COUNT_H : 0)
  const step = most > 1 ? Math.min(STEP, (body - 2 * (R + 1)) / (most - 1)) : 0
  const r = Math.min(R, Math.max(3, step * 0.36 || R))
  const x = (k: number): number => R + 1 + ((w - 2 * (R + 1)) * k) / Math.max(1, L.length - 1)
  const y = (k: number, i: number): number => body / 2 + (i - (shown[k] - 1) / 2) * step
  const maxW = Math.max(1e-6, ...f.W.flat(2).map((v) => Math.abs(Number(v) || 0)))
  const lit = (k: number, i: number): number => {
    const row = f.a?.[k]
    const v = row?.[i]
    if (v === undefined || !Number.isFinite(v)) return 0.7
    const top = Math.max(1e-6, ...row!.map((u) => Math.abs(Number(u) || 0)))
    return 0.4 + 0.6 * (Math.abs(v) / top)
  }

  return (
    <svg width={w} height={h} className="block overflow-visible" data-net-graph aria-label={`Your network, ${L.join('-')}`}>
      {f.W.slice(0, L.length - 1).map((m, k) =>
        Array.from({ length: shown[k] }, (_, i) =>
          Array.from({ length: shown[k + 1] ?? 0 }, (_, j) => {
            const t = Math.abs(Number(m?.[i]?.[j]) || 0) / maxW
            return (
              <line
                key={`${k}-${i}-${j}`}
                x1={x(k)}
                y1={y(k, i)}
                x2={x(k + 1)}
                y2={y(k + 1, j)}
                stroke={color.text}
                strokeOpacity={0.07 + 0.5 * t}
                strokeWidth={0.6 + 1.6 * t}
                strokeLinecap="round"
              />
            )
          })
        )
      )}
      {shown.map((n, k) =>
        Array.from({ length: n }, (_, i) => (
          <g key={`${k}-${i}`}>
            <circle cx={x(k)} cy={y(k, i)} r={r} fill={color.island} />
            <circle cx={x(k)} cy={y(k, i)} r={r} fill={color.text} fillOpacity={lit(k, i)} stroke={fill.ring} strokeWidth={1} />
          </g>
        ))
      )}
      {truncated &&
        L.map((n, k) =>
          n > MAX_SHOWN ? (
            <text key={k} x={x(k)} y={h - 4} textAnchor="middle" fontSize={11} fill={color.faint} style={{ fontVariantNumeric: 'tabular-nums' }}>
              {n}
            </text>
          ) : null
        )}
    </svg>
  )
}
