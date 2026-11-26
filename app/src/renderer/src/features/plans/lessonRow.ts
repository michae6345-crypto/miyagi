/**
 * Feature: plans. What a lesson row on a plan page offers once it is opened (PlanPage LessonTable): the action's label,
 * whether it can start now, and, when it can't, one calm line saying why. Pure, so the rule is tested without a DOM.
 *
 * A plan lesson always starts with plan: {id, index} (store.ts startLesson), which the Library's lesson preview
 * (library/Detail, library.start {id} alone) can't carry, so a plan row opens in place instead of going there.
 */
import type { PlanLessonState } from '../../../../../../shared/contracts/events'

export type LessonGate = { can: boolean; label: string; why?: string }

/**
 * `startable`: the lesson has something to start from (a saved lesson, a video, or a goal to build it from).
 * `connected`: the engine is there to start it. `name`: the product's name for the offline line (copy.name).
 */
export function lessonGate(l: { state?: PlanLessonState; passed: boolean; startable: boolean }, ctx: { connected: boolean; name: string }): LessonGate {
  const label = l.state === 'in_progress' ? 'Continue lesson' : l.passed ? 'Start again' : 'Start lesson'
  if (l.state === 'skipped') return { can: false, label, why: 'Left out of this plan.' }
  if (!l.startable) return { can: false, label, why: 'This lesson isn’t ready yet.' }
  if (!ctx.connected) return { can: false, label, why: `Starts once ${ctx.name} connects.` }
  return { can: true, label }
}

/** The row's spoken name: what it is and that it opens ("Move, rotate and scale. Lesson 2. Open."). */
export const rowLabel = (title: string, n: number, open: boolean): string => `${title}. Lesson ${n}. ${open ? 'Close' : 'Open'}.`
