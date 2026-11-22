/**
 * Feature: shell / flow. The slim progress strip at the top of the first run:
 *
 *   [bonsai]  · · · ▬ · ·  [same width, empty]
 *
 * Progress is six small dots (onboarding/Dots.tsx), no labels: Sign in, What miyagi sends (the consent screen),
 * Screen, Accessibility, VS Code, Ready. The
 * current one is longer and white, a done step is green (green only means done), a step ahead is faint. "Ready" covers
 * Getting miyagi ready and You're ready. The bonsai's slot is always there (so nothing shifts when the tree arrives)
 * and an empty slot of the same width balances it on the right, so the dots sit on the window's center line. The tree
 * sits in its slot from guided setup on, and leaves it for the sidebar at the end.
 * Not interactive: it is a progress line, not navigation (Back lives in the footer).
 * Windows (onboarding/device.ts): no Screen Recording or Accessibility grants exist there, so a PC's strip is three dots,
 * Sign in, VS Code, Ready, the same steps the guided walk has on that computer.
 */
import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { needsGrants, osNow, type Os } from '../../onboarding/device'
import { Dots, type DotItem } from '../../onboarding/Dots'
import type { Row } from '../../onboarding/rows'
import type { GuidedStepId } from '../../onboarding/store'
import { FlowMark } from './FlowMark'
import { stripIn } from './motion'
import type { FlowPhase } from './store'

export type StripId = 'login' | 'consent' | 'screen' | 'accessibility' | 'companion' | 'ready'
export const STRIP: ReadonlyArray<{ id: StripId; label: string }> = [
  { id: 'login', label: 'Sign in' },
  { id: 'consent', label: 'What miyagi sends' },
  { id: 'screen', label: 'Screen Recording' },
  { id: 'accessibility', label: 'Accessibility' },
  { id: 'companion', label: 'VS Code' },
  { id: 'ready', label: 'Ready' }
]

/** This computer's strip: all five on a Mac, without the two macOS grants on Windows. */
export function stripItems(os: Os = osNow()): ReadonlyArray<{ id: StripId; label: string }> {
  return needsGrants(os) ? STRIP : STRIP.filter((it) => it.id !== 'screen' && it.id !== 'accessibility')
}

const MARK = 18
const SLOT_GAP = 10

/** Which strip item is current for this phase and guided step. */
export function currentItem(phase: FlowPhase, step: GuidedStepId | undefined, os: Os = osNow()): StripId {
  if (phase === 'login' || phase === 'intro' || phase === 'pending') return 'login'
  if (phase === 'consent') return 'consent'
  if (phase === 'setup') {
    if (step === 'engine') return 'ready'
    if (!step) return needsGrants(os) ? 'screen' : 'companion'
    return step
  }
  return 'ready'
}

/** Done: green. The login is done once the walk is past it; a setup step once its row is green (or skipped). */
export function itemDone(id: StripId, phase: FlowPhase, rows: Row[], skipped: readonly GuidedStepId[]): boolean {
  if (id === 'login') return phase === 'consent' || phase === 'setup' || phase === 'ready' || phase === 'leaving'
  if (id === 'consent') return phase === 'setup' || phase === 'ready' || phase === 'leaving'
  if (id === 'ready') return phase === 'ready' || phase === 'leaving'
  return rows.find((r) => r.id === id)?.state === 'passed' || skipped.includes(id)
}

/** `mark={false}`: the bonsai has left for the sidebar (the hand-off to home), or stays there (setup again). */
export function Strip({
  phase,
  step,
  rows,
  skipped,
  mark = true
}: {
  phase: FlowPhase
  step?: GuidedStepId
  rows: Row[]
  skipped: readonly GuidedStepId[]
  mark?: boolean
  /** Kept for callers: the dots are the same at every width. */
  compact?: boolean
}): ReactNode {
  const reduce = useReducedMotion()
  const current = currentItem(phase, step)
  const withMark = mark && (phase === 'setup' || phase === 'ready')
  const items: DotItem[] = stripItems().map((it) => ({ id: it.id, label: it.label, state: it.id === current ? 'current' : itemDone(it.id, phase, rows, skipped) ? 'done' : 'next' }))
  return (
    <motion.nav aria-label="Setup progress" data-flow-strip={current} className="flex items-center" initial={reduce ? false : { opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={stripIn}>
      <span className="block shrink-0" style={{ width: MARK, height: MARK, marginRight: SLOT_GAP }}>
        {withMark && <FlowMark size={MARK} />}
      </span>
      <Dots items={items} />
      {/* Balances the bonsai's slot, so the dots sit on the window's center line. */}
      <span aria-hidden className="block shrink-0" style={{ width: MARK + SLOT_GAP, height: MARK }} />
    </motion.nav>
  )
}
