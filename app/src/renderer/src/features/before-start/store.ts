/**
 * Feature: before-start (mockup 03, "Before you start"). Whether the sheet is showing.
 *
 * It opens by itself when a "Just teach me" lesson arrives with something to say before step 1 (lesson.ready
 * build / flow / prerequisites / learnFirst), and again from the drawer's "Needs: ..." chip. It closes on
 * "Start the lesson", "Learn ... first", Esc, a reset or the lesson ending. The engine's step 1 may already be
 * running underneath: closing never sends anything.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'

export const useBeforeStart = create<{ open: boolean }>(() => ({ open: false }))
const set = useBeforeStart.setState

type Lesson = NonNullable<ReturnType<typeof useLesson.getState>['lesson']>

/** Anything worth a sheet in this lesson? */
export function worthASheet(l: Lesson | undefined): boolean {
  return !!(l && (l.build || l.flow?.length || l.prerequisites?.length || l.learnFirst?.length))
}

export const openBeforeStart = (): void => {
  if (worthASheet(useLesson.getState().lesson)) set({ open: true })
}
export const closeBeforeStart = (): void => set({ open: false })

/**
 * Only a NEW lesson at step 0 gets the sheet (Michael's tests 2-3, A15): on a resume it came back over the code and
 * repeated the drawer. A resume shows as the engine's "Continue where you left off?" card or as a first
 * step.started past step 0; either closes it, and it can't open itself again until the next lesson.ready.
 */
let firstStepSeen = false
onMessage('lesson.ready', (p) => {
  firstStepSeen = false
  set({ open: p.lesson.mode === 'lesson' && worthASheet(p.lesson) })
})
onMessage('step.started', (p) => {
  if (!firstStepSeen && p.index > 0) closeBeforeStart()
  firstStepSeen = true
})
onMessage('card', (p) => {
  if (p.kind === 'resume') closeBeforeStart()
})
onUi('dismiss', closeBeforeStart)
onUi('reset', closeBeforeStart)
