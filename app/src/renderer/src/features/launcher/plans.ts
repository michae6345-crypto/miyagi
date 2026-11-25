/**
 * Feature: launcher. The learner's plans in the launcher (v4, Nov 24: Home's "Plans" rows, Adrian's ui-next mock): with
 * nothing typed and no lesson running, the plans still going sit between Continue and Ready to run, one row each
 * ("Neural networks from scratch · 3 of 8 · Next · Broadcasting"). Enter, or a click, starts the plan's next lesson
 * (plans/store startNext: library.start, learn_url or learn with `plan: {id, index}`).
 *
 * Pure: the rows come from the plans store's `mine` (the engine's `plans` answer, or the stage's local plans); the
 * launcher asks for them on open with plans.list when the engine speaks it.
 */
import type { PlanState } from '../../../../../../shared/contracts/events'

/** Plan rows in the launcher: it stays a short list (the Library has the rest). */
export const MAX_PLANS = 2

/** The lesson a plan's Continue starts: `nextIndex`, else the first one not done; -1 when every lesson is done. */
export function nextLessonIndex(p: PlanState): number {
  if (p.nextIndex === null) return -1
  if (typeof p.nextIndex === 'number') return p.lessons[p.nextIndex] ? p.nextIndex : -1
  return p.lessons.findIndex((l) => l.state === 'next' || l.state === 'in_progress' || l.state === 'todo')
}

/** The plan has begun: a lesson passed or opened. Its primary says Continue, else Start. */
export function planStarted(p: PlanState): boolean {
  return p.done > 0 || p.lessons.some((l) => l.state === 'in_progress' || l.state === 'done')
}

const time = (p: PlanState): number => {
  const t = Date.parse(p.updatedAt ?? p.startedAt ?? '')
  return Number.isFinite(t) ? t : 0
}

/** Same words, for comparing a plan's next lesson with the lesson being built or waiting (never offered twice). */
const norm = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

/**
 * The plans the launcher lists: still going (a next lesson to start), most recently touched first (the engine's order
 * when it sends no dates), at most MAX_PLANS. A plan whose next lesson is `current` (being built, or waiting to resume)
 * is left out: that lesson already has its own row.
 */
export function launcherPlans(mine: PlanState[], current?: string): PlanState[] {
  const skip = current ? norm(current) : ''
  return mine
    .map((p, i) => ({ p, i, next: nextLessonIndex(p) }))
    .filter(({ p, next }) => next >= 0 && p.done < Math.max(p.total, 1) && (!skip || norm(p.lessons[next]?.title ?? '') !== skip))
    .sort((a, b) => time(b.p) - time(a.p) || a.i - b.i)
    .slice(0, MAX_PLANS)
    .map(({ p }) => p)
}

/**
 * How many rows a section under the plans shows (Ready to run: library.MAX_READY; Try asking: its three topics): `max`,
 * one fewer once plan rows are on screen, so the idle panel (Continue, Plans, Ready to run, Try asking) still fits
 * under the notch on a 1024 × 700 screen (persona QA's smallest).
 */
export function limitWithPlans(max: number, planRows: number): number {
  return planRows > 0 ? Math.max(1, max - 1) : max
}

/** "3 of 8" (lessons passed of lessons in the plan) and "Next · Broadcasting", for the row. */
export function planLine(p: PlanState): { count: string; next?: string; value: number } {
  const i = nextLessonIndex(p)
  const total = Math.max(0, p.total)
  return {
    count: `${p.done} of ${total}`,
    next: i >= 0 ? p.lessons[i]?.title : undefined,
    value: total ? p.done / total : 0
  }
}
