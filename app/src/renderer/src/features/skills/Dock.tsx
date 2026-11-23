/**
 * Feature: skills. The dock along the bottom of the page: what to do now.
 *
 *   left    the page's ONE primary button, "Continue: <skill>" (or "Start: <skill>"), and under it where it picks up and
 *           why ("Step 3 of 4 in NumPy in 20 minutes" / "Gets you closer to Layers · 12 min")
 *   middle  up to three other skills you could start (each opens its panel)
 *   right   up to three mastered skills due for a review ("Keep fresh")
 * Continue starts the saved lesson (library.start), else a lesson built for the skill (learn). Narrow panes drop Keep
 * fresh first, then Also ready; the primary and its why always stay.
 */
import { RotateCcw } from 'lucide-react'
import type { ReactNode } from 'react'
import { color, fill, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { useDash } from '../dashboard/store'
import type { SkillGraph } from './model'
import { sentence } from './copy'
import { startSkill } from './store'

const small = { fontSize: type2.xs, lineHeight: '16px', color: color.label } as const

function Names({ ids, g, onOpen }: { ids: string[]; g: SkillGraph; onOpen: (id: string) => void }): ReactNode {
  return (
    <span className="flex min-w-0 items-center gap-[12px]">
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          className="min-w-0 cursor-pointer truncate underline decoration-1 underline-offset-[3px]"
          style={{ fontSize: type2.sm, color: color.text, textDecorationColor: fill.ring }}
          onClick={() => onOpen(id)}
        >
          {g.byId[id]?.label}
        </button>
      ))}
    </span>
  )
}

export function Dock({ g, width, onOpen }: { g: SkillGraph; width: number; onOpen: (id: string) => void }): ReactNode {
  const starting = useDash((s) => s.starting)
  const startError = useDash((s) => s.startError?.text)
  const pick = g.next
  const node = pick ? g.byId[pick.skillId] : undefined
  const showAlso = width >= 640 && g.alsoReady.length > 0
  const showFresh = width >= 900 && g.keepFresh.length > 0
  const where =
    pick?.stepIndex !== undefined && pick.stepCount
      ? { pre: `Step ${Math.min(pick.stepIndex + 1, pick.stepCount)} of ${pick.stepCount} in `, title: pick.lessonTitle }
      : pick?.lessonTitle
        ? { pre: 'In ', title: pick.lessonTitle }
        : { pre: 'A short lesson built for it', title: undefined }
  const why = [sentence(pick?.why), pick?.estMinutes ? `${pick.estMinutes} min` : undefined].filter(Boolean).join(' · ')
  return (
    <div data-skills-dock className="flex w-full items-center" style={{ gap: 24, minHeight: 72, padding: '14px 0 18px', borderTop: `1px solid ${fill.hairline}` }}>
      {pick && node ? (
        <div className="flex min-w-0 flex-1 items-center" style={{ gap: 16 }}>
          <PrimaryButton
            label={`${pick.practicing ? 'Continue' : 'Start'}: ${pick.label}`}
            size="lg"
            busy={!!starting && starting === pick.libraryId}
            onClick={() => startSkill(node, g)}
          />
          <div className="flex min-w-0 flex-col">
            <span className="truncate" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
              {where.pre}
              {where.title && <span style={{ color: color.text, fontWeight: 500 }}>{where.title}</span>}
            </span>
            {(startError || why) && (
              <span className="truncate" role={startError ? 'status' : undefined} style={small}>
                {startError ?? why}
              </span>
            )}
          </div>
        </div>
      ) : (
        <span style={{ fontSize: type2.sm, color: color.label }}>{g.goal && g.byId[g.goal.id]?.state === 'mastered' ? 'Goal reached. Pick the next one.' : 'Nothing to start yet.'}</span>
      )}
      {(showAlso || showFresh) && <span className="block shrink-0 self-stretch" style={{ width: 1, background: fill.hairline }} />}
      {showAlso && (
        <div className="flex min-w-0 shrink-0 flex-col" style={{ gap: 2, maxWidth: '34%' }}>
          <span style={small}>Also ready</span>
          <Names ids={g.alsoReady.slice(0, width >= 1000 ? 3 : 2)} g={g} onOpen={onOpen} />
        </div>
      )}
      {showFresh && (
        <div className="ml-auto flex min-w-0 shrink-0 flex-col" style={{ gap: 2 }}>
          <span className="flex items-center gap-[6px]" style={small}>
            <RotateCcw size={12} strokeWidth={1.8} aria-hidden />
            Keep fresh
          </span>
          <Names ids={g.keepFresh} g={g} onOpen={onOpen} />
        </div>
      )}
    </div>
  )
}
