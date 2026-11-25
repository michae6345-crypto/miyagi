/**
 * Skill chips on a lesson card (mockup skills-07-extras, 1): "teaches" and "uses", each skill with its tiny state
 * ring, from LibraryItem.teaches / uses resolved against the skill graph. A row with no skills is left out, and with
 * no data at all nothing renders, so a card without skills looks exactly as before. Neutral only: the ring carries the
 * state (green only on mastered), the words stay ink and label.
 */
import { useEffect, type ReactNode } from 'react'
import { color, type2 } from '../../../core/theme'
import { libraryItemSkills, type SkillGraphNode } from '../model'
import { SkillRing, ringState } from './SkillRing'
import { ensureSkillGraph, useSkillGraph } from './store'

/** Per row: past this many the row ends in "+N", so a card stays one line per row. */
const MAX_CHIPS = 3

function ChipRow({ word, nodes }: { word: string; nodes: SkillGraphNode[] }): ReactNode {
  if (!nodes.length) return null
  const shown = nodes.slice(0, MAX_CHIPS)
  const more = nodes.length - shown.length
  return (
    <span data-skill-chips={word} className="relative flex min-w-0 items-center gap-[10px] overflow-hidden whitespace-nowrap" style={{ height: 18, fontSize: type2.xs }}>
      <span className="shrink-0" style={{ width: 52, color: color.faint }}>
        {word}
      </span>
      {shown.map((n) => (
        <span key={n.id} data-skill-chip={ringState(n)} className="flex min-w-0 shrink items-center gap-[5px]" style={{ color: color.text }}>
          <SkillRing state={ringState(n)} size={12} fraction={n.evidence && n.evidence.total ? n.evidence.done / n.evidence.total : undefined} />
          <span className="truncate">{n.label}</span>
        </span>
      ))}
      {more > 0 && (
        <span className="shrink-0" style={{ color: color.label }}>
          +{more}
        </span>
      )}
    </span>
  )
}

/** The chips for one Library item, or nothing. Sits under the card's meta line. */
export function LessonSkills({ item }: { item: unknown }): ReactNode {
  const graph = useSkillGraph((s) => s.graph)
  useEffect(ensureSkillGraph, [])
  if (!graph) return null
  const { teaches, uses } = libraryItemSkills(item, graph)
  if (!teaches.length && !uses.length) return null
  return (
    <span data-lesson-skills className="relative flex min-w-0 flex-col gap-[4px]" style={{ marginTop: 6 }}>
      <ChipRow word="teaches" nodes={teaches} />
      <ChipRow word="uses" nodes={uses} />
    </span>
  )
}
