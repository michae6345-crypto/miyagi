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

onMessage('lesson.ready', (p) => set({ open: p.lesson.mode === 'lesson' && worthASheet(p.lesson) }))
onUi('dismiss', closeBeforeStart)
onUi('reset', closeBeforeStart)
