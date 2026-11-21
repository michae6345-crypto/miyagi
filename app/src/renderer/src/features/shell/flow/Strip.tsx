/**
 * Feature: shell / flow. The slim step strip at the top of the first run:
 *
 *   [bonsai]  Sign in · Screen · Accessibility · VS Code · Ready
 *
 * The current step is white on one raised pill that slides from step to step (layoutId STRIP_CURRENT, house spring).
 * A step that is done gets the green tick (green only means done) and quiets to the label gray; a step not reached
 * is faint. "Ready" covers Getting miyagi ready and You're ready. The bonsai's slot is always there (so nothing shifts
 * when the tree arrives); the tree sits in it from guided setup on, and leaves it for the sidebar at the end.
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

/** `mark={false}`: the bonsai has left for the sidebar (the hand-off to home). */
export function Strip({ phase, step, rows, skipped, mark = true }: { phase: FlowPhase; step?: GuidedStepId; rows: Row[]; skipped: readonly GuidedStepId[]; mark?: boolean }): ReactNode {
  const current = currentItem(phase, step)
  const withMark = mark && (phase === 'setup' || phase === 'ready')
  return (
    <motion.nav aria-label="Setup progress" data-flow-strip={current} className="flex items-center" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={stripIn}>
      <span className="mr-[10px] block" style={{ width: MARK, height: MARK }}>
        {withMark && <FlowMark size={MARK} />}
      </span>
      <ol className="m-0 flex list-none items-center p-0">
        {STRIP.map((it, i) => {
          const on = it.id === current
          const done = itemDone(it.id, phase, rows, skipped)
          return (
            <li key={it.id} className="flex items-center">
              {i > 0 && (
                <span aria-hidden className="px-[2px]" style={{ fontSize: type2.xs, color: color.faint }}>
                  ·
                </span>
              )}
              <span
                data-flow-item={it.id}
                data-state={on ? 'current' : done ? 'done' : 'next'}
                aria-current={on ? 'step' : undefined}
                className="relative flex h-[26px] items-center gap-[5px] whitespace-nowrap px-[10px]"
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
                <AnimatePresence initial={false}>
                  {done && (
                    <motion.span key="tick" className="relative flex" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={spring}>
                      <Check aria-hidden size={11} strokeWidth={2.6} color={tone.passed} />
                    </motion.span>
                  )}
                </AnimatePresence>
                <span className="relative">{it.label}</span>
                {done && <span className="sr-only">, done</span>}
              </span>
            </li>
          )
        })}
      </ol>
    </motion.nav>
  )
}
