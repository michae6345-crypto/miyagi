/**
 * Core (v2, W0-3): where the learner is in the lesson (the panel header, the Mini pill, Les-Mini).
 *
 * Up to `cap` steps (10): one mark per step. passed = green (the only green), skipped = the faint ring tone (never
 * green), the current step = white (green once it has passed), not reached = trackNext.
 *   variant 'dots' (default, the Les-* panel header): 8x8 dots, the current step a 20x8 pill, gap 6.
 *   variant 'bars' (Les-Mini): fixed 16x4 bars, gap 3, steps not reached at trackNextMini.
 * More steps than `cap`: one proportional track instead
 * (passed share in green, a white tick where the learner is), so a 40-step lesson never becomes a row of specks.
 * Indices are 0-based positions in the lesson's step list (core/lesson useCurrentStep gives them).
 */
import type { ReactNode } from 'react'
import { color, fill, radius2 } from '../theme'

export type StepDotsProps = {
  total: number
  /** 0-based position of the current step; -1 = none yet. */
  current: number
  passed: ReadonlyArray<number>
  skipped?: ReadonlyArray<number>
  cap?: number
  /** 'dots' for the lesson panel header (default), 'bars' for the Mini pill. */
  variant?: 'dots' | 'bars'
  /** Track width in px for the proportional form (default 120). */
  width?: number
  /** Track height in px for the proportional form (default 4). */
  height?: number
}

const MARK = {
  dots: { w: 8, h: 8, currentW: 20, gap: 6, next: fill.trackNext },
  bars: { w: 16, h: 4, currentW: 16, gap: 3, next: fill.trackNextMini }
} as const

export function StepDots({ total, current, passed, skipped = [], cap = 10, variant = 'dots', width = 120, height = 4 }: StepDotsProps): ReactNode {
  const n = Math.max(0, Math.floor(total))
  if (!n) return null
  const done = new Set(passed)
  const skip = new Set(skipped)
  const label = `Step ${Math.min(n, Math.max(1, current + 1))} of ${n}`
  if (n <= cap) {
    const m = MARK[variant]
    return (
      <div role="img" aria-label={label} data-step-dots={n} data-variant={variant} className="flex shrink-0 items-center" style={{ gap: m.gap }}>
        {Array.from({ length: n }, (_, i) => {
          const state = skip.has(i) ? 'skipped' : i === current ? 'current' : done.has(i) ? 'passed' : 'next'
          const bg = state === 'skipped' ? fill.ring : done.has(i) ? color.green : state === 'current' ? color.accent : m.next
          return <span key={i} data-dot={state} className="block shrink-0" style={{ width: state === 'current' ? m.currentW : m.w, height: m.h, borderRadius: radius2.round, background: bg }} />
        })}
      </div>
    )
  }
  const passedShare = [...done].filter((i) => !skip.has(i) && i >= 0 && i < n).length / n
  const at = Math.min(1, Math.max(0, (current + 0.5) / n))
  return (
    <div role="img" aria-label={label} data-step-dots={n} className="relative shrink-0 overflow-hidden" style={{ width, height, borderRadius: radius2.round, background: fill.trackNext }}>
      <span className="absolute inset-y-0 left-0 block" style={{ width: `${passedShare * 100}%`, background: color.green }} />
      {current >= 0 && <span className="absolute inset-y-0 block" style={{ left: `calc(${at * 100}% - 1px)`, width: 2, background: color.accent }} />}
    </div>
  )
}
