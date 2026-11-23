/**
 * A skill's state as a tiny ring (agents/skills.md States), for chips and recap rows. No legend: words sit beside it.
 *
 *   locked      dashed faint ring
 *   ready       solid ink ring
 *   practicing  ink ring with an inner ink arc (evidence so far, else a quarter)
 *   mastered    the passed glyph: green fill with the check. The only green
 *   review      mastered but due: a hollow green ring (never a demotion)
 *
 * `play`: the unlock motion (the lesson-end recap plays it first). Mastered pops in and its check draws (StatusGlyph);
 * ready draws its ring closed; practicing draws its arc. Opacity only with reduced motion (core draw()).
 */
import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { draw } from '../../../core/ui/motion'
import { StatusGlyph } from '../../../core/ui/status'
import { color, fill } from '../../../core/theme'
import type { SkillGraphNode } from '../model'

export type RingState = SkillGraphNode['state'] | 'review'

export const ringState = (n: Pick<SkillGraphNode, 'state' | 'review'>): RingState => (n.state === 'mastered' && n.review ? 'review' : n.state)

const R = 8.2
const DASH = '2.4 1.9'

export function SkillRing({ state, size = 14, fraction, play = false, delay = 0 }: { state: RingState; size?: number; fraction?: number; play?: boolean; delay?: number }): ReactNode {
  const reduce = useReducedMotion()
  if (state === 'mastered') return <StatusGlyph state="passed" size={size} still={!play} />
  const motionFor = (opacity = 1) => (play ? draw(reduce, { delay, opacity }) : { initial: false as const })
  const stroke = state === 'locked' ? fill.ring : state === 'review' ? color.green : color.text
  const f = Math.max(0.12, Math.min(0.92, fraction ?? 0.25))
  return (
    <svg data-skill-ring={state} width={size} height={size} viewBox="0 0 18 18" className="shrink-0" aria-hidden>
      {state === 'locked' ? (
        <circle cx="9" cy="9" r={R} fill="none" stroke={stroke} strokeWidth={1.4} strokeDasharray={DASH} />
      ) : (
        <motion.circle cx="9" cy="9" r={R} fill="none" stroke={stroke} strokeWidth={1.6} transform="rotate(-90 9 9)" {...motionFor()} />
      )}
      {state === 'practicing' && (
        <motion.circle
          cx="9"
          cy="9"
          r={4.4}
          fill="none"
          stroke={color.text}
          strokeWidth={2.4}
          strokeLinecap="round"
          transform="rotate(-90 9 9)"
          {...(play ? { ...draw(reduce, { delay }), animate: { pathLength: f, opacity: 1 } } : { initial: false as const, animate: { pathLength: f } })}
        />
      )}
    </svg>
  )
}
