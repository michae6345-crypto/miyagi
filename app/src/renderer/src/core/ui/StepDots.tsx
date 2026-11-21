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
 *
 * Polish (UI-POLISH-SPEC 7): when the learner moves on, the long "current" mark grows on the next step and the dots glide (motion layout,
 * a transform on the spring) instead of jumping, and a dot that has just passed pops once (.6 to 1). Only a dot that
 * passes while the dots are on screen pops: opening the panel or mounting the Mini pill shows the passed dots still.
 * The proportional track's green share grows from the left (scaleX, never width) and its tick glides (x, never left).
 */
import { motion } from 'motion/react'
import { useEffect, useRef, type ReactNode } from 'react'
import { color, fill, radius2, spring } from '../theme'

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
  // Polish: the passed set as of the last commit (null before the first) and the step count it belonged to, so only a
  // dot newly passed in the same lesson shape pops (switching to another lesson with passed steps shows them still).
  const seen = useRef<{ n: number; set: ReadonlySet<number> } | null>(null)
  useEffect(() => {
    seen.current = { n, set: new Set(passed) }
  })
  if (!n) return null
  const done = new Set(passed)
  const skip = new Set(skipped)
  const label = `Step ${Math.min(n, Math.max(1, current + 1))} of ${n}`
  if (n <= cap) {
    const m = MARK[variant]
    // Polish: pop only when the passed set grew by addition (same step count, nothing un-passed). The header is not keyed
    // by lesson, so another lesson of the same length with its own passed steps fails this and shows them still.
    const prev = seen.current
    const grew = !!prev && prev.n === n && [...prev.set].every((j) => done.has(j))
    return (
      <div role="img" aria-label={label} data-step-dots={n} data-variant={variant} className="flex shrink-0 items-center" style={{ gap: m.gap }}>
        {Array.from({ length: n }, (_, i) => {
          const state = skip.has(i) ? 'skipped' : i === current ? 'current' : done.has(i) ? 'passed' : 'next'
          const bg = state === 'skipped' ? fill.ring : done.has(i) ? color.green : state === 'current' ? color.accent : m.next
          const green = done.has(i) && !skip.has(i)
          const fresh = green && grew && !seen.current?.set.has(i)
          return (
            <motion.span
              // A new key the moment a dot turns green (current or not), so it remounts and can pop; the key then holds
              // while the current mark moves on, so it glides (layout). Layout measures only when the current step moves,
              // and only in a variant where the current mark changes size ('dots'); the 'bars' never move, so no projection.
              key={green ? `p${i}` : i}
              data-dot={state}
              layout={m.currentW !== m.w}
              layoutDependency={current}
              className="block shrink-0"
              style={{ width: state === 'current' ? m.currentW : m.w, height: m.h, borderRadius: radius2.round, background: bg }}
              initial={fresh ? { scale: 0.6 } : false}
              animate={{ scale: 1 }}
              transition={spring}
            />
          )
        })}
      </div>
    )
  }
  const passedShare = [...done].filter((i) => !skip.has(i) && i >= 0 && i < n).length / n
  const at = Math.min(1, Math.max(0, (current + 0.5) / n))
  return (
    <div role="img" aria-label={label} data-step-dots={n} className="relative shrink-0 overflow-hidden" style={{ width, height, borderRadius: radius2.round, background: fill.trackNext }}>
      <motion.span
        className="absolute inset-y-0 left-0 block w-full"
        style={{ background: color.green, originX: 0 }}
        initial={false}
        animate={{ scaleX: passedShare }}
        transition={spring}
      />
      {/* Polish: the tick glides on the same spring as the green share (x, a transform), so the two stay in step. */}
      {current >= 0 && (
        <motion.span
          className="absolute inset-y-0 block"
          style={{ left: 0, width: 2, background: color.accent }}
          initial={false}
          animate={{ x: at * width - 1 }}
          transition={spring}
        />
      )}
    </div>
  )
}
