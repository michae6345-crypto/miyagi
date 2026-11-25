/**
 * Feature: skills. The flat page's lines (round 3), pure. Every word comes from the data; nothing is invented as
 * progress. The rules the engine applies (shared with it, never computed here):
 *   mastery   a skill is mastered once its checks pass on 2 different days without help (no hint, no "do it for me")
 *   reviews   a mastered skill comes back for a review 3, 7, 21 and 60 days after it was mastered
 */
import type { SkillGraph, SkillGraphNode } from '../model'
import { names } from '../copy'

export const MASTERY_DAYS = 2
export const REVIEW_DAYS = [3, 7, 21, 60] as const

/** "Goal · 6 of 11 skills · about 3 hours left" pieces (the goal's name is drawn bold by the view). */
export function goalBits(g: SkillGraph, minutesLeft?: number, pace?: { now: number; minutesPerWeek?: number }): string[] {
  if (!g.goal) return []
  const bits = [`${g.goal.mastered} of ${g.goal.total} skills`]
  if (minutesLeft && minutesLeft > 0) {
    let left = minutesLeft < 90 ? `about ${Math.round(minutesLeft / 5) * 5 || 5} min left` : `about ${Math.round(minutesLeft / 60)} hours left`
    // "around Dec 4 at your pace": only from the learner's own minutes this week.
    const perDay = pace?.minutesPerWeek ? pace.minutesPerWeek / 7 : 0
    if (pace && perDay > 0) left += `, around ${shortDate(pace.now + Math.ceil(minutesLeft / perDay) * 86_400_000)} at your pace`
    bits.push(left)
  }
  return bits
}

/** The minutes still to go on the goal's path, when every remaining skill says how long it takes. */
export function minutesLeft(g: SkillGraph, minutesOf: (n: SkillGraphNode) => number | undefined): number | undefined {
  if (!g.goal) return undefined
  const left = g.goal.pathIds.map((id) => g.byId[id]).filter((n) => n && n.kind === 'skill' && n.state !== 'mastered')
  let sum = 0
  for (const n of left) {
    const m = minutesOf(n)
    if (m === undefined) return undefined
    sum += m
  }
  return sum
}

/** The Status cell of "Still to go". */
export function statusCell(n: SkillGraphNode, g: SkillGraph): string {
  if (n.state === 'practicing') return n.evidence ? `${n.evidence.done} of ${n.evidence.total} steps` : 'Practicing'
  if (n.state === 'ready') return 'Ready'
  if (n.state === 'locked') return n.needs.length > 2 ? `Needs ${n.needs.length} skills` : n.needs.length ? `Needs ${names(n.needs, g)}` : 'Locked'
  return n.review ? 'Review due' : 'Mastered'
}

/** "Still to go": the goal's skills not mastered yet, practicing first, then ready, then locked in path order. */
export function stillToGo(g: SkillGraph): SkillGraphNode[] {
  if (!g.goal) return []
  const rank = { practicing: 0, ready: 1, locked: 2, mastered: 3 } as const
  return g.goal.pathIds
    .map((id) => g.byId[id])
    .filter((n): n is SkillGraphNode => !!n && n.kind === 'skill' && n.state !== 'mastered')
    .sort((a, b) => Number(b.isNext) - Number(a.isNext) || rank[a.state] - rank[b.state] || a.depth - b.depth)
}

/** The panel's rule line: how it gets mastered, or when it comes back. */
export function ruleLine(n: SkillGraphNode, now: number): string {
  if (n.state === 'mastered') {
    if (n.review) return 'Due for a review.'
    if (n.dueAt && n.dueAt > now) {
      const days = Math.max(1, Math.round((n.dueAt - now) / 86_400_000))
      return days === 1 ? 'Next review tomorrow.' : `Next review in ${days} days.`
    }
    return `Reviews after ${REVIEW_DAYS.slice(0, -1).join(', ')} and ${REVIEW_DAYS[REVIEW_DAYS.length - 1]} days.`
  }
  if (n.state === 'locked') return n.needs.length ? `Opens after ${n.needs.length === 1 ? 'one skill' : `${n.needs.length} skills`}.` : 'Locked.'
  return `Mastered when you pass it on ${MASTERY_DAYS} days without help.`
}

/** "Nov 14". */
export const shortDate = (ms: number): string => new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
