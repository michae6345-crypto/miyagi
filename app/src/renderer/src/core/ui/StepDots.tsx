/**
 * Core (v2, W0-3): where the learner is in the lesson (the panel header, the Mini pill, Les-Mini).
 *
 * Up to `cap` steps (10): one segment per step. passed = green (the only green), skipped = the faint ring tone (never
 * green), the current step = white, not reached = trackNext. More steps than `cap`: one proportional track instead
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
  /** Track width in px for the proportional form (default 120). Segments fill their container. */
  width?: number
  height?: number
}

export function StepDots({ total, current, passed, skipped = [], cap = 10, width = 120, height = 4 }: StepDotsProps): ReactNode {
  const n = Math.max(0, Math.floor(total))
  if (!n) return null
  const done = new Set(passed)
  const skip = new Set(skipped)
  const label = `Step ${Math.min(n, Math.max(1, current + 1))} of ${n}`
  if (n <= cap) {
    return (
      <div role="img" aria-label={label} data-step-dots={n} className="flex w-full items-center gap-[3px]">
        {Array.from({ length: n }, (_, i) => {
          const bg = skip.has(i) ? fill.ring : done.has(i) ? color.green : i === current ? color.accent : fill.trackNext
          return <span key={i} data-dot={skip.has(i) ? 'skipped' : done.has(i) ? 'passed' : i === current ? 'current' : 'next'} className="block flex-1" style={{ height, borderRadius: radius2.round, background: bg }} />
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
