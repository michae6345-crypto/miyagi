/**
 * Feature: skills. The words on the page, in one place (calm, short, sentence case; the brand is lowercase "miyagi").
 * Every line is built from the data: labels, counts, the engine's "why". Nothing lesson-specific.
 */
import { needsLine, type SkillGraph, type SkillGraphNode } from './model'

/**
 * The Skills page with no skills yet. Arriving from a clicked skill (a plan's chip, a Library row: showSkill in
 * skills/go puts its label in the search), the page names that skill instead of a bare "No skills yet".
 */
export function emptyLines(wanted?: string): { title: string; line: string } {
  const name = wanted?.trim()
  if (name) return { title: name, line: 'Not started yet. A lesson that teaches it adds it here.' }
  return { title: 'No skills yet', line: 'Finish a lesson. The skills its checks proved show up here.' }
}

/**
 * The line under a node's name: what it is now ("ready", "2 of 4 steps", "needs 3 skills", "review"). `fits` says
 * whether a line fits under the node; a "needs <name>" that doesn't becomes "needs 1 skill" (never an ellipsis).
 */
export function stateLine(n: SkillGraphNode, g: SkillGraph, fits: (line: string) => boolean = () => true): string {
  if (n.kind === 'capstone') {
    if (n.state === 'mastered') return 'project · done'
    if (n.isGoal && g.goal) {
      const line = `project · ${g.goal.mastered} of ${g.goal.total} skills`
      return fits(line) ? line : `${g.goal.mastered} of ${g.goal.total} skills`
    }
    const c = g.capstones.find((x) => x.id === n.id)
    const need = (c?.requires.length ? c.requires : n.requires).filter((id) => g.byId[id]?.state !== 'mastered').length
    const line = need ? `project · ${need} to go` : 'project · ready'
    return fits(line) ? line : need ? `${need} to go` : 'ready'
  }
  if (n.state === 'locked') {
    const line = needsLine(n, g) ?? 'locked'
    return fits(line) ? line : n.needs.length === 1 ? 'needs 1 skill' : `needs ${n.needs.length} skills`
  }
  if (n.state === 'practicing') return n.evidence ? `${n.evidence.done} of ${n.evidence.total} steps` : 'practicing'
  if (n.state === 'ready') return 'ready'
  return n.review ? 'review' : 'mastered'
}

/**
 * The Map's state line, only where it says something the node doesn't: Next (with its steps when it has some),
 * practicing "2 of 4 steps", locked "needs 3 skills", a mastered skill due for review, a project's progress. A ready
 * or mastered skill has none (its ring and fill say it).
 */
export function mapLine(n: SkillGraphNode, g: SkillGraph, fits: (line: string) => boolean = () => true): string {
  if (n.kind === 'capstone') return stateLine(n, g, fits)
  if (n.isNext) return n.state === 'practicing' && n.evidence ? `Next · ${n.evidence.done} of ${n.evidence.total} steps` : 'Next'
  if (n.state === 'practicing' || n.state === 'locked') return stateLine(n, g, fits)
  return n.review ? 'review' : ''
}

/** The word a panel or list row uses for a state. */
export function stateWord(n: SkillGraphNode): string {
  if (n.state === 'mastered') return n.review ? 'Mastered, due for review' : 'Mastered'
  if (n.state === 'practicing') return n.evidence ? `Practicing, ${n.evidence.done} of ${n.evidence.total} steps` : 'Practicing'
  if (n.state === 'ready') return 'Ready'
  return 'Locked'
}

/** "Arrays, Loops and Lists". */
export function names(ids: string[], g: SkillGraph, max = 3): string {
  const ls = ids.map((id) => g.byId[id]?.label).filter((x): x is string => !!x)
  if (ls.length <= 1) return ls[0] ?? ''
  if (ls.length > max) return `${ls.slice(0, max - 1).join(', ')} and ${ls.length - max + 1} more`
  return `${ls.slice(0, -1).join(', ')} and ${ls[ls.length - 1]}`
}

export const sentence = (s: string | undefined): string | undefined => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s)

/** The one line the unlock motion says. */
export function unlockLine(kind: 'mastered' | 'unlocked' | 'review_due' | 'capstone_done', label: string): string {
  if (kind === 'unlocked') return `${label} is ready.`
  if (kind === 'mastered') return `${label} mastered.`
  if (kind === 'capstone_done') return `${label} is done.`
  return `${label} is due for a review.`
}

/** "Last practiced today / yesterday / Nov 19". */
export function practicedLine(ms: number | undefined, now: number): string | undefined {
  if (!ms) return undefined
  const day = (t: number): number => Math.floor((t - new Date(t).getTimezoneOffset() * 60_000) / 86_400_000)
  const d = day(now) - day(ms)
  if (d <= 0) return 'today'
  if (d === 1) return 'yesterday'
  return new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
