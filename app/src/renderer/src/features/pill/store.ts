/**
 * Pill-local state: the step-pass moment and the building line.
 *
 * The step-pass moment is one gesture (FRONTEND-HANDOFF → "Step passes"):
 *   t = 0      step.passed: the status dot becomes a green check that draws its stroke,
 *              the ring advances on the spring, core flashes the island green (600ms)
 *   t = 560ms  the text crossfades to the next step by itself; the check settles back into a gray dot
 *   t = 400ms  (player) the video resumes
 * The pill moves on without waiting for the engine's step.started (the mock sends it ~4s later),
 * using step.passed.nextStepId or the next entry in lesson.steps. step.started then just confirms it.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'

/** How long the green check holds before the text crossfades to the next step. */
export const PASS_HOLD_MS = 560

type PillState = {
  /** The step whose pass is being celebrated right now (the check is showing). */
  celebrating?: string
  /** After a pass: the pill has moved past `from` and shows `to` (undefined = the lesson is complete). */
  advanced?: { from: string; to?: string }
  /** Last lesson.building message, kept through lesson.ready (core clears it there). */
  buildMessage?: string
}

export const usePill = create<PillState>(() => ({}))
const set = usePill.setState

let holdTimer: ReturnType<typeof setTimeout> | undefined

const clear = (): void => {
  clearTimeout(holdTimer)
  set({ celebrating: undefined, advanced: undefined, buildMessage: undefined })
  ring.shown = 0
}

onUi('reset', clear)
onMessage('lesson.ready', () => {
  clearTimeout(holdTimer)
  set({ celebrating: undefined, advanced: undefined })
  ring.shown = 0
})
onMessage('lesson.building', (p) => set({ buildMessage: p.message }))
// The engine caught up. A celebration still in progress finishes on its own timer.
onMessage('step.started', () => set({ advanced: undefined, buildMessage: undefined }))
onMessage('step.passed', (p) => {
  const { steps } = useLesson.getState()
  const i = steps.findIndex((s) => s.id === p.stepId)
  const to = p.nextStepId ?? (i >= 0 ? steps[i + 1]?.id : undefined)
  clearTimeout(holdTimer)
  set({ celebrating: p.stepId, advanced: undefined })
  holdTimer = setTimeout(() => set({ celebrating: undefined, advanced: { from: p.stepId, to } }), PASS_HOLD_MS)
})

/**
 * The ring's last drawn value, kept across remounts: when a card covers the pill during a pass,
 * the ring still visibly advances once the pill comes back (instead of appearing already full).
 */
export const ring = { shown: 0 }

/** Off-track episodes whose amber pulse has been seen, so hover/card remounts don't pulse again. */
export const pulsedOfftrack = new WeakSet<object>()
