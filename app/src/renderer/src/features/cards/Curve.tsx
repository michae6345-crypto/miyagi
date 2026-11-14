/**
 * The loss curve on the coach cards. No axes, no grid: one primary line ("yours") with a live dot
 * and its value, plus faint reference lines (tutorial, before the fix).
 *
 * Units: live `metric` values are drawn on a log10 scale (a plateau vs a drop only reads in log).
 * The mock's optional `offtrack.curve` arrays are already in plot units (log10), so they're used as-is.
 */
import { motion } from 'motion/react'
import { useEffect, useId, useState, type ReactNode } from 'react'
import { color } from '../../core/theme'
import type { Point } from './store'

export type XY = [x: number, y: number]

export type Line = {
  key: string
  pts: XY[]
  stroke: string
  /** Reference lines are thinner, faded, optionally dashed. */
  reference?: boolean
  dashed?: boolean
}

/** Live points → plot units (log10 when every value is positive). */
export function plotPoints(points: Point[]): XY[] {
  const log = points.every((p) => p.value > 0)
  return points.map((p) => [p.step, log ? Math.log10(p.value) : p.value])
}

/** Index-spaced values (the mock's offtrack.curve) spread across [0, span]. */
export function plotArray(values: number[], span = 1): XY[] {
  const n = Math.max(1, values.length - 1)
  return values.map((v, i) => [(i / n) * span, v])
}

/** 0.2504 → "0.25", 0.000608 → "6.1e-4" */
export function fmt(v: number): string {
  if (v === 0) return '0'
  const a = Math.abs(v)
  if (a >= 0.01 && a < 1000) return String(Number(v.toPrecision(2)))
  const [m, e] = v.toExponential(1).split('e')
  return `${m}e${Number(e)}`
}

const LIVE_MS = 1600

/** True while points keep arriving (re-renders once when the run goes quiet). */
function useLive(at?: number): boolean {
  const [, tick] = useState(0)
  const live = !!at && Date.now() - at < LIVE_MS
  useEffect(() => {
    if (!at) return
    const ms = at + LIVE_MS - Date.now()
    if (ms <= 0) return
    const t = setTimeout(() => tick((x) => x + 1), ms + 20)
    return () => clearTimeout(t)
  }, [at])
  return live
}

/**
 * lines[0] is the primary line: drawn last (on top), with an area fill, the end dot and `end.label`.
 * `end.at` = when its last point arrived; while recent, the dot breathes (live).
 */
export function Curve({ lines, width, height = 64, end }: { lines: Line[]; width: number; height?: number; end?: { label?: string; at?: number } }): ReactNode {
  const gradId = useId()
  const live = useLive(end?.at)
  const drawn = lines.filter((l) => l.pts.length > 0)
  if (drawn.length === 0) return null

  const all = drawn.flatMap((l) => l.pts)
  const xMax = Math.max(...all.map((p) => p[0]), 1e-9)
  const xMin = Math.min(...all.map((p) => p[0]))
  const yLo = Math.min(...all.map((p) => p[1]))
  const yHi = Math.max(...all.map((p) => p[1]))
  const padT = end?.label ? 16 : 5
  const padB = 5
  const padR = 6
  const X = (x: number): number => ((x - xMin) / (xMax - xMin || 1)) * (width - padR - 2) + 2
  const Y = (y: number): number => padT + ((yHi - y) / (yHi - yLo || 1)) * (height - padT - padB)
  const d = (pts: XY[]): string => pts.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')

  const [primary, ...refs] = drawn
  const last = primary.pts[primary.pts.length - 1]
  const ex = X(last[0])
  const ey = Y(last[1])
  const area = `${d(primary.pts)} L${ex.toFixed(1)},${height} L${X(primary.pts[0][0]).toFixed(1)},${height} Z`

  return (
    <svg width={width} height={height} className="block overflow-visible">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={primary.stroke} stopOpacity={0.22} />
          <stop offset="100%" stopColor={primary.stroke} stopOpacity={0} />
        </linearGradient>
      </defs>

      {refs.map((l) =>
        l.dashed ? (
          <motion.path
            key={l.key}
            d={d(l.pts)}
            fill="none"
            stroke={l.stroke}
            strokeWidth={1.5}
            strokeDasharray="3 4"
            strokeLinecap="round"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.55 }}
            transition={{ duration: 0.4 }}
          />
        ) : (
          <motion.path
            key={l.key}
            d={d(l.pts)}
            fill="none"
            stroke={l.stroke}
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.7}
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
          />
        )
      )}

      <motion.path d={area} fill={`url(#${gradId})`} stroke="none" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, delay: 0.25 }} />
      <motion.path
        key={primary.key}
        d={d(primary.pts)}
        fill="none"
        stroke={primary.stroke}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0.1 }}
      />

      {live && (
        <motion.circle
          cx={ex}
          cy={ey}
          fill="none"
          stroke={primary.stroke}
          strokeWidth={1.5}
          r={3.5}
          initial={{ scale: 1, opacity: 0.6 }}
          animate={{ scale: 2.8, opacity: 0 }}
          transition={{ duration: 1.4, repeat: Infinity, ease: 'easeOut' }}
        />
      )}
      <circle cx={ex} cy={ey} r={3.5} fill={primary.stroke} />
      {end?.label && (
        <text
          x={ex - 7}
          y={ey - 7}
          textAnchor="end"
          className="tabular-nums"
          fontSize={11}
          fontWeight={600}
          fill={primary.stroke}
          stroke={color.island}
          strokeWidth={3}
          paintOrder="stroke"
        >
          {end.label}
        </text>
      )}
    </svg>
  )
}

/** One legend entry: a short stroke + its name. */
export function Key({ tone, dashed, children }: { tone: string; dashed?: boolean; children: ReactNode }): ReactNode {
  return (
    <span className="flex items-center gap-[5px]">
      <svg width="12" height="2" className="block">
        <line x1="0" y1="1" x2="12" y2="1" stroke={tone} strokeWidth="2" strokeDasharray={dashed ? '3 2' : undefined} />
      </svg>
      {children}
    </span>
  )
}
