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

/** Every step of a fully built lesson is done (passed or skipped): the sheet has nothing left to say before it. */
export function lessonDone(s: ReturnType<typeof useLesson.getState> = useLesson.getState()): boolean {
  return s.complete && s.steps.length > 0 && s.steps.every((x) => s.passed.includes(x.id))
}

export const openBeforeStart = (): void => {
  if (worthASheet(useLesson.getState().lesson)) set({ open: true }) // the drawer's chip: on purpose, even when done
}
export const closeBeforeStart = (): void => set({ open: false })

/**
 * Only a NEW lesson at step 0 gets the sheet (Michael's tests 2-3, A15): on a resume it came back over the code and
 * repeated the drawer. A resume shows as the engine's "Continue where you left off?" card or as a first
 * step.started that isn't the plan's first step; either closes it, and it can't open itself again until the next lesson.ready.
 */
let firstStepSeen = false
onMessage('lesson.ready', (p) => {
  firstStepSeen = false
  set({ open: p.lesson.mode === 'lesson' && worthASheet(p.lesson) })
})
onMessage('step.started', (p) => {
  // By position, not p.index: the engine numbers steps from 1 (Michael's test 5), so index > 0 closed every new lesson.
  if (!firstStepSeen && useLesson.getState().steps.findIndex((s) => s.id === p.stepId) > 0) closeBeforeStart()
  firstStepSeen = true
})
// Michael's run (Sun 03:19): a sheet left open at step 1 came back over the finished lesson. Once a step passes the
// lesson is underway, so the sheet goes (the drawer's "Needs" chip can still reopen it on purpose).
onMessage('step.passed', closeBeforeStart)
onMessage('card', (p) => {
  if (p.kind === 'resume') closeBeforeStart()
})
onUi('dismiss', closeBeforeStart)
onUi('reset', closeBeforeStart)
