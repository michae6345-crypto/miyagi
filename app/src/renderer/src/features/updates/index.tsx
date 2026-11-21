/**
 * Feature: updates (agents/updates.md). A newer miyagi is offered calmly, from the island, and never mid-lesson:
 *
 *   45 upd-card   "A new miyagi is ready." The lowest card: every error, lesson and completion card wins over it.
 *                 Shows only with no lesson, no build and no pause, after QUIET_MS of that (so it never flashes in
 *                 between a lesson ending and the next starting). A lesson that starts hides it; it comes back after.
 *
 * Main (src/main/features/updates.ts) checks on launch and every 6 h, and holds the installer URL. Download opens it
 * in the browser (no auto-install: the app is ad-hoc signed). Later / Esc = 24 h.
 *
 * Never before the sign-in gate opens (core/gate.ts): the quiet wait starts only then.
 */
import { useEffect, useState } from 'react'
import { useGateOpen } from '../../core/gate'
import { useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { CARD_WIDTH, UpdateCard } from './Card'
import { useUpdates, wantsCard } from './store'

const QUIET_MS = 4000

/**
 * The card is up: the sign-in gate is open, an update is wanted with no lesson, and either the learner asked for the
 * install steps or the offer has waited out QUIET_MS (`settled`). Pure, for test/overlayGate.test.ts.
 */
export function updCardActive(s: { gateOpen: boolean; want: boolean; idle: boolean; steps: boolean; settled: boolean }): boolean {
  if (!s.gateOpen) return false
  return s.steps ? s.want && s.idle : s.settled
}

/** true once `on` has held for `ms` (false again the moment it drops). */
function useHeld(on: boolean, ms: number): boolean {
  const [held, setHeld] = useState(false)
  useEffect(() => {
    if (!on) {
      setHeld(false)
      return
    }
    const t = setTimeout(() => setHeld(true), ms)
    return () => clearTimeout(t)
  }, [on, ms])
  return on && held
}

export default defineFeature({
  id: 'updates',
  islandModes: [
    {
      id: 'upd-card',
      priority: 45,
      width: CARD_WIDTH,
      useActive: () => {
        const gateOpen = useGateOpen()
        const want = useUpdates((s) => wantsCard(s))
        const steps = useUpdates((s) => s.steps)
        const idle = useLesson((s) => !s.lesson && !s.building && !s.paused)
        const settled = useHeld(gateOpen && want && idle, QUIET_MS)
        // The install steps the learner just asked for stay put; only the unasked offer waits for quiet.
        return updCardActive({ gateOpen, want, idle, steps, settled })
      },
      Content: UpdateCard
    }
  ]
})
