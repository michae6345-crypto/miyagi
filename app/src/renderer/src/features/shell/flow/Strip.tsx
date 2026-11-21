/**
 * Feature: shell / flow. The slim step strip at the top of the first run:
 *
 *   [bonsai]  Sign in · Screen · Accessibility · VS Code · Ready  [same width, empty]
 *
 * The current step is white on one raised pill that slides from step to step (layoutId STRIP_CURRENT, house spring).
 * A step that is done gets the green tick (green only means done) and quiets to the label gray; a step not reached
 * is faint. "Ready" covers Getting miyagi ready and You're ready. The bonsai's slot is always there (so nothing shifts
 * when the tree arrives) and an empty slot of the same width balances it on the right, so the labels sit on the
 * window's center line whether the tree is in the strip or not (login). The tree sits in its slot from guided setup
 * on, and leaves it for the sidebar at the end.
 * A tick arriving makes its step a little wider: every step glides to its new place on the house spring (layout
 * "position"), the label inside its step too, instead of all of them jumping sideways at once.
 * Compact (a narrow window, FlowLayer.tsx): only the current step keeps its label; the others are a green tick (done)
 * or a faint dot (not yet), named for screen readers.
 * Not interactive: it is a progress line, not navigation (Back lives in the footer).
 */
import { AnimatePresence, motion } from 'motion/react'
import { Check } from 'lucide-react'
import type { ReactNode } from 'react'
import { color, fill, highlight, radius2, spring, status as tone, type2 } from '../../../core/theme'
import type { Row } from '../../onboarding/rows'
import type { GuidedStepId } from '../../onboarding/store'
import { FlowMark } from './FlowMark'
import { STRIP_CURRENT, stripIn } from './motion'
import type { FlowPhase } from './store'

export type StripId = 'login' | 'screen' | 'accessibility' | 'companion' | 'ready'
export const STRIP: ReadonlyArray<{ id: StripId; label: string }> = [
  { id: 'login', label: 'Sign in' },
  { id: 'screen', label: 'Screen' },
  { id: 'accessibility', label: 'Accessibility' },
  { id: 'companion', label: 'VS Code' },
  { id: 'ready', label: 'Ready' }
]

const MARK = 18
const SLOT_GAP = 10
const DOT = 5

/** Which strip item is current for this phase and guided step. */
export function currentItem(phase: FlowPhase, step: GuidedStepId | undefined): StripId {
  if (phase === 'login' || phase === 'intro' || phase === 'pending') return 'login'
  if (phase === 'setup') return !step || step === 'engine' ? (step ? 'ready' : 'screen') : step
  return 'ready'
}

/** Done: green. The login is done once the walk is past it; a setup step once its row is green (or skipped). */
export function itemDone(id: StripId, phase: FlowPhase, rows: Row[], skipped: readonly GuidedStepId[]): boolean {
  if (id === 'login') return phase === 'setup' || phase === 'ready' || phase === 'leaving'
  if (id === 'ready') return phase === 'ready' || phase === 'leaving'
  return rows.find((r) => r.id === id)?.state === 'passed' || skipped.includes(id)
}

function Tick(): ReactNode {
  return (
    <motion.span key="tick" className="relative flex" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={spring}>
      <Check aria-hidden size={11} strokeWidth={2.6} color={tone.passed} />
    </motion.span>
  )
}

/** `mark={false}`: the bonsai has left for the sidebar (the hand-off to home), or stays there (setup again). */
export function Strip({
  phase,
  step,
  rows,
  skipped,
  mark = true,
  compact = false
}: {
  phase: FlowPhase
  step?: GuidedStepId
  rows: Row[]
  skipped: readonly GuidedStepId[]
  mark?: boolean
  compact?: boolean
}): ReactNode {
  const current = currentItem(phase, step)
  const withMark = mark && (phase === 'setup' || phase === 'ready')
  return (
    <motion.nav
      aria-label="Setup progress"
      data-flow-strip={current}
      data-compact={compact || undefined}
      className="flex items-center"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={stripIn}
    >
      <span className="block shrink-0" style={{ width: MARK, height: MARK, marginRight: SLOT_GAP }}>
        {withMark && <FlowMark size={MARK} />}
      </span>
      <ol className="m-0 flex list-none items-center p-0">
        {STRIP.map((it, i) => {
          const on = it.id === current
          const done = itemDone(it.id, phase, rows, skipped)
          const bare = compact && !on
          return (
            <motion.li key={it.id} layout="position" transition={spring} className="flex items-center">
              {i > 0 && !compact && (
                <span aria-hidden className="px-[2px]" style={{ fontSize: type2.xs, color: color.faint }}>
                  ·
                </span>
              )}
              <span
                data-flow-item={it.id}
                data-state={on ? 'current' : done ? 'done' : 'next'}
                aria-current={on ? 'step' : undefined}
                className={`relative flex h-[26px] items-center gap-[5px] whitespace-nowrap ${bare ? 'px-[6px]' : 'px-[10px]'}`}
                style={{ fontSize: type2.xs, fontWeight: 500, color: on ? color.text : done ? color.label : color.faint, transition: 'color 180ms' }}
              >
                {on && (
                  <motion.span
                    layoutId={STRIP_CURRENT}
                    aria-hidden
                    className="absolute inset-0"
                    style={{ borderRadius: radius2.round, background: fill.navActive, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${fill.hairline}` }}
                    transition={spring}
                  />
                )}
                <AnimatePresence initial={false}>{done && <Tick />}</AnimatePresence>
                {bare ? (
                  !done && <span aria-hidden className="relative block" style={{ width: DOT, height: DOT, borderRadius: radius2.round, background: color.faint }} />
                ) : (
                  <motion.span layout="position" transition={spring} className="relative">
                    {it.label}
                  </motion.span>
                )}
                {bare && <span className="sr-only">{it.label}</span>}
                {done && <span className="sr-only">, done</span>}
              </span>
            </motion.li>
          )
        })}
      </ol>
      {/* Balances the bonsai's slot, so the steps sit on the window's center line. */}
      <span aria-hidden className="block shrink-0" style={{ width: MARK + SLOT_GAP, height: MARK }} />
    </motion.nav>
  )
}
