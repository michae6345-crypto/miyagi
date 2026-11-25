/**
 * Skills extras, pure (no React, no store): what the lesson-end recap, the weekly recap and the portfolio say.
 *
 *   lessonRecap   what moved in one lesson: mastered (the lesson's unseen `mastered` events, else its skills that are
 *                 mastered now), ready now (its `unlocked` events, else skills it just opened), and the nearest locked
 *                 skill downstream as "N skills away". At most 4 rows, plus the graph's NEXT for the one primary.
 *   weekLines     the weekly recap's sentence, never a streak and never a missed day.
 *   goalAway      skills between the learner and the goal.
 */
import { ancestors, type SkillGraph, type SkillGraphNode, type SkillGraphPick, type SkillGraphWeek } from '../model'

export type RecapKind = 'mastered' | 'ready' | 'practicing' | 'away'
export type RecapRow = { node: SkillGraphNode; kind: RecapKind; /** away: skills still between it and the learner. */ away?: number }
export type Recap = { rows: RecapRow[]; next?: SkillGraphPick }

const MAX_ROWS = 4

/** The `requires` map of a graph (helps links are not prerequisites). */
function requiresMap(g: SkillGraph): Map<string, string[]> {
  return new Map(g.nodes.map((n) => [n.id, n.requires]))
}

/** Skills not mastered yet between the learner and `id` (its own id not counted). */
export function skillsAway(id: string, g: SkillGraph): number {
  return ancestors(id, requiresMap(g)).filter((a) => g.byId[a] && g.byId[a].state !== 'mastered').length
}

/**
 * What one lesson moved. `lessonIds`: the lesson's ids as the engine may name them (lesson id, library id);
 * `skillIds`: the lesson's steps' skillIds. Undefined when nothing on the graph belongs to it.
 */
export function lessonRecap(g: SkillGraph | undefined, ref: { lessonIds: string[]; skillIds: string[] }): Recap | undefined {
  if (!g || !g.nodes.length) return undefined
  const lessons = new Set(ref.lessonIds.filter(Boolean))
  const mine = (lessonId?: string): boolean => !lessons.size || !lessonId || lessons.has(lessonId)
  const events = g.events.filter((e) => mine(e.lessonId))

  // The lesson's own skills: step skillIds, then every node that names this lesson.
  const touched = new Set(ref.skillIds.filter((id) => g.byId[id]))
  if (lessons.size) for (const n of g.nodes) if (n.lessons.some((l) => lessons.has(l.lessonId) || (l.libraryId && lessons.has(l.libraryId)))) touched.add(n.id)

  const mastered: string[] = []
  const ready: string[] = []
  const add = (xs: string[], id: string): void => void (g.byId[id] && !xs.includes(id) && xs.push(id))
  for (const e of events) {
    if (e.kind === 'mastered' || e.kind === 'capstone_done') add(mastered, e.skillId)
    else if (e.kind === 'unlocked' && g.byId[e.skillId].state !== 'mastered') add(ready, e.skillId)
  }
  const practicing: string[] = []
  if (!events.length) {
    for (const id of touched) {
      const s = g.byId[id].state
      if (s === 'mastered') add(mastered, id)
      else if (s === 'practicing') add(practicing, id)
    }
    // Opened by it: ready skills that need one of the skills it mastered.
    for (const n of g.nodes) if (n.kind === 'skill' && n.state === 'ready' && n.requires.some((r) => mastered.includes(r))) add(ready, n.id)
  }

  // The nearest locked skill downstream of what moved, the goal's path first.
  const moved = new Set([...mastered, ...ready, ...practicing, ...touched])
  const req = requiresMap(g)
  let away: RecapRow | undefined
  for (const n of g.nodes) {
    if (n.state !== 'locked' || moved.has(n.id)) continue
    if (!ancestors(n.id, req).some((a) => moved.has(a))) continue
    const k = skillsAway(n.id, g)
    if (!k) continue
    const better = !away || Number(n.onGoalPath) > Number(away.node.onGoalPath) || (n.onGoalPath === away.node.onGoalPath && k < (away.away ?? 0))
    if (better) away = { node: n, kind: 'away', away: k }
  }

  const rows: RecapRow[] = [
    ...mastered.slice(0, 2).map((id) => ({ node: g.byId[id], kind: 'mastered' as const })),
    ...practicing.slice(0, 1).map((id) => ({ node: g.byId[id], kind: 'practicing' as const })),
    ...ready.slice(0, 2).map((id) => ({ node: g.byId[id], kind: 'ready' as const }))
  ].slice(0, away ? MAX_ROWS - 1 : MAX_ROWS)
  if (away) rows.push(away)
  if (!rows.length) return undefined
  const next = g.next && g.byId[g.next.skillId]?.state !== 'mastered' ? g.next : undefined
  return { rows, next }
}

/** The status word on a recap row: "mastered", "ready now", "2 of 4 steps", "2 skills away". */
export function recapWord(r: RecapRow): string {
  if (r.kind === 'mastered') return 'mastered'
  if (r.kind === 'ready') return 'ready now'
  if (r.kind === 'practicing') return r.node.evidence ? `${r.node.evidence.done} of ${r.node.evidence.total} steps` : 'practicing'
  return `${r.away} ${r.away === 1 ? 'skill' : 'skills'} away`
}

/** "Next: Broadcasting · 12 min" (the minutes only when the engine sent them). */
export function nextLabel(p: SkillGraphPick): string {
  return `Next: ${p.label}${p.estMinutes ? ` · ${p.estMinutes} min` : ''}`
}

// ---- the week -----------------------------------------------------------------------------------------------------

/** "1 h 40 min", "45 min", "2 h". */
export function minutesWords(m: number): string {
  const h = Math.floor(m / 60)
  const r = Math.round(m % 60)
  if (!h) return `${r} min`
  return r ? `${h} h ${r} min` : `${h} h`
}

const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`

/** Skills between the learner and the goal: the engine's number, else counted from the goal's path. */
export function goalAway(g: SkillGraph | undefined): number | undefined {
  if (!g) return undefined
  if (g.week?.goalAway !== undefined) return g.week.goalAway
  if (!g.goal) return undefined
  return Math.max(0, g.goal.total - g.goal.mastered)
}

/**
 * The weekly recap in words. `lead` is bold ("2 skills mastered"), `rest` follows it (", 3 kept fresh, 1 h 40 min.").
 * Only what the engine counted; a week with nothing counted yet says so calmly.
 */
export function weekLines(w: SkillGraphWeek, away: number | undefined, weeklyGoal: number): { lead: string; rest: string; goal?: string; days: string } {
  const parts: string[] = []
  if (w.mastered !== undefined) parts.push(plural(w.mastered, 'skill') + ' mastered')
  if (w.keptFresh !== undefined) parts.push(`${w.keptFresh} kept fresh`)
  if (w.minutes) parts.push(minutesWords(w.minutes))
  const lead = parts[0] ?? 'A fresh week'
  const rest = parts.length > 1 ? `, ${parts.slice(1).join(', ')}.` : '.'
  const goal = away === undefined ? undefined : away === 0 ? 'Your goal is ready to build.' : `Your goal is ${plural(away, 'skill')} away.`
  const n = w.days.filter(Boolean).length
  const days = `${n ? plural(n, 'practice day') + '.' : 'No practice days yet.'} Your weekly goal is ${weeklyGoal}.`
  return { lead, rest, goal, days }
}
