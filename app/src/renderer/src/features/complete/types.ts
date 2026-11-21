/**
 * card.skillMap (the lesson-complete card). These mirror shared/contracts/events.ts on origin/integration/live
 * (3a267a9, Michael's claude/skill-map): same names, same shapes. Swap them for the contract import once that
 * contract reaches adrian/shell.
 */
export type SkillState = 'mastered' | 'learning' | 'next'
export interface SkillNode { id: string; label: string; state: SkillState; detail?: string }
export interface SkillEdge { from: string; to: string }
export interface SkillCross { track: string; label: string; to: string; note?: string }
/**
 * id / estMinutes are not in the contract yet (A8 Core request): a next lesson already cached on this Mac (library id,
 * started with library.start, zero model calls) and about how long it takes. Read only when they're well formed.
 */
export interface SkillNext { title: string; goal: string; id?: string; estMinutes?: number }
export interface SkillMap { track: string; headline: string; nodes: SkillNode[]; edges: SkillEdge[]; cross: SkillCross[]; next: SkillNext[] }

const str = (v: unknown): string => (typeof v === 'string' ? v.trim() : '')
const STATES = new Set<SkillState>(['mastered', 'learning', 'next'])
/** A library lesson id (contract LibraryItem.id): never a path. */
const LIB_ID = /^[A-Za-z0-9_-]{1,64}$/

/** The engine's skillMap, checked: bad nodes dropped, edges / cross links only between known ids. Undefined when there's nothing to draw. */
export function readSkillMap(raw: unknown): SkillMap | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const m = raw as Record<string, unknown>
  const seen = new Set<string>()
  const nodes: SkillNode[] = []
  for (const n of Array.isArray(m.nodes) ? m.nodes : []) {
    const o = (n ?? {}) as Record<string, unknown>
    const id = str(o.id)
    const label = str(o.label)
    if (!id || !label || seen.has(id)) continue
    seen.add(id)
    const state = STATES.has(o.state as SkillState) ? (o.state as SkillState) : 'next'
    const detail = str(o.detail)
    nodes.push(detail ? { id, label, state, detail } : { id, label, state })
  }
  if (!nodes.length) return undefined
  const edges: SkillEdge[] = (Array.isArray(m.edges) ? m.edges : [])
    .map((e) => ({ from: str((e as SkillEdge)?.from), to: str((e as SkillEdge)?.to) }))
    .filter((e) => seen.has(e.from) && seen.has(e.to) && e.from !== e.to)
  const cross: SkillCross[] = (Array.isArray(m.cross) ? m.cross : [])
    .map((c) => {
      const o = (c ?? {}) as Record<string, unknown>
      const note = str(o.note)
      return { track: str(o.track), label: str(o.label), to: str(o.to), ...(note ? { note } : {}) }
    })
    .filter((c) => c.track && c.label && seen.has(c.to))
  const next: SkillNext[] = (Array.isArray(m.next) ? m.next : [])
    .map((x): SkillNext => {
      const o = (x ?? {}) as Record<string, unknown>
      const id = str(o.id)
      const est = typeof o.estMinutes === 'number' && Number.isFinite(o.estMinutes) && o.estMinutes > 0 ? Math.round(o.estMinutes) : undefined
      return { title: str(o.title), goal: str(o.goal), ...(LIB_ID.test(id) ? { id } : {}), ...(est ? { estMinutes: est } : {}) }
    })
    .filter((x) => x.title && x.goal)
  return { track: str(m.track), headline: str(m.headline), nodes, edges, cross, next }
}
