/**
 * Feature: skills. Go to one skill on the Skills page from anywhere in the home window: a skill chip on a plan, a
 * Library row's Grows chip, Progress's "Closest to mastered". The existing Skills route (setPage('skills')) with the
 * skill picked:
 *
 *   in the graph   select(id): its peek opens and the views light it (and what it needs); its card is scrolled into view
 *   not (yet)      the search is set to its label, so the views mark the match instead ("Find a skill")
 *
 * A chip that only knows a label (a table cell) is looked up in the graph by label first.
 */
import { setPage } from '../shell/store'
import { buildSkillGraph, type SkillGraph } from './model'
import { useSkills } from './store'

export type SkillRef = { id?: string; label?: string }
export type SkillHit = 'peek' | 'search' | 'none'

/** The skill graph the Skills page would draw now (null: no `progress` yet). */
function graphNow(): SkillGraph | undefined {
  const raw = useSkills.getState().raw
  return raw ? buildSkillGraph(raw, Date.now()) : undefined
}

/** Which node a ref names in `g`: its id, else a node whose label matches (case and spaces aside). */
export function findSkill(g: SkillGraph | undefined, ref: SkillRef): string | undefined {
  if (!g) return undefined
  if (ref.id && g.byId[ref.id]) return ref.id
  const want = ref.label?.trim().toLowerCase()
  if (!want) return undefined
  return g.nodes.find((n) => n.label.trim().toLowerCase() === want)?.id
}

/** The card, chip or row that draws a skill, in any of the Skills views. */
function skillEl(id: string): Element | null {
  if (typeof document === 'undefined' || typeof document.querySelector !== 'function') return null
  const q = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(id) : id.replace(/["\\]/g, '\\$&')
  return document.querySelector(`[data-skill-card="${q}"], [data-skills-chip="${q}"], [data-skills-row="${q}"]`)
}

/** Bring the skill's card into view once the page has drawn it (a first visit mounts the page after this call). */
function reveal(id: string): void {
  if (typeof setTimeout !== 'function') return
  for (const ms of [80, 320]) {
    setTimeout(() => {
      const el = skillEl(id)
      if (el && 'scrollIntoView' in el) (el as HTMLElement).scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' })
    }, ms)
  }
}

/** Open the Skills page on a skill. Returns what it could do: open its peek, mark it through the search, or nothing. */
export function showSkill(ref: SkillRef): SkillHit {
  const id = findSkill(graphNow(), ref)
  const label = ref.label?.trim() ?? ''
  if (!id && !label && !ref.id) return 'none'
  setPage('skills')
  if (id) {
    useSkills.setState({ selected: id, query: '', picker: false })
    reveal(id)
    return 'peek'
  }
  // Not in the graph yet (no `progress`, or a skill the learner hasn't met): keep the id picked for when the graph
  // lands, and mark it by name now.
  useSkills.setState({ selected: ref.id, query: label, picker: false })
  return label ? 'search' : 'none'
}
