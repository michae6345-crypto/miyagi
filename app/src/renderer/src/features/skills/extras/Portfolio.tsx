/**
 * The portfolio on Progress (mockup skills-07-extras, 4): projects the learner finished, as cards (a picture of their
 * own file when the engine saved one, else the file's name on a quiet well; the project, its track, the date and how
 * many skills it used), then the current goal as a dashed placeholder with the bonsai ("your goal · 5 skills away"),
 * which opens the Skills page. Nothing renders with no finished project and no chosen goal.
 */
import { FileCode2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { MiyagiMark } from '../../../core/ui/Mark'
import { color, fill, layout, radius2, surface, type2 } from '../../../core/theme'
import { CARD } from '../../shell/ui'
import type { SkillGraph, SkillGraphPortfolioItem } from '../model'
import { goalAway } from './recap'
import { ensureSkillGraph, useSkillGraph } from './store'

const PIC_H = 132

/** A picture the window can show: a data image, a web image, or a file on this Mac (an absolute path). */
function pictureSrc(path?: string): string | undefined {
  if (!path) return undefined
  if (/^data:image\//.test(path) || /^https?:\/\//.test(path) || /^file:\/\//.test(path)) return path
  if (path.startsWith('/')) return `file://${encodeURI(path)}`
  return undefined
}

const day = (t?: number): string => (t ? new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '')

function Picture({ item }: { item: SkillGraphPortfolioItem }): ReactNode {
  const src = item.artifact?.kind === 'image' ? pictureSrc(item.artifact.path) : undefined
  const [broken, setBroken] = useState(false)
  const path = item.artifact?.path
  const name = path && !/^(data|https?):/.test(path) ? path.split('/').pop() : undefined
  return (
    <div className="relative flex items-center justify-center overflow-hidden" style={{ height: PIC_H, background: surface.well, borderBottom: `1px solid ${fill.hairline}` }}>
      {src && !broken ? (
        <img src={src} alt={item.artifact?.caption ?? `${item.title}, your file`} draggable={false} onError={() => setBroken(true)} className="h-full w-full select-none object-cover" />
      ) : (
        <span className="flex flex-col items-center gap-[6px]" style={{ color: color.label }}>
          <FileCode2 aria-hidden size={22} strokeWidth={1.6} />
          {name && <span style={{ fontSize: type2.xs }}>{name}</span>}
        </span>
      )}
    </div>
  )
}

function ProjectCard({ item, g }: { item: SkillGraphPortfolioItem; g: SkillGraph }): ReactNode {
  const track = item.track ?? g.tracks.find((t) => t.id === g.byId[item.capstoneId]?.track)?.label
  const n = item.skillIds.length
  const meta = [track, day(item.at), n ? `${n} ${n === 1 ? 'skill' : 'skills'}` : ''].filter(Boolean).join(' · ')
  return (
    <li data-portfolio-item={item.capstoneId} className="flex flex-col overflow-hidden" style={{ ...CARD }}>
      <Picture item={item} />
      <div className="flex min-w-0 flex-col gap-[2px]" style={{ padding: '12px 16px 14px' }}>
        <span className="truncate font-semibold" style={{ fontSize: type2.md, color: color.text }}>
          {item.title}
        </span>
        {meta && (
          <span className="truncate" style={{ fontSize: type2.xs, color: color.label, fontVariantNumeric: 'tabular-nums' }}>
            {meta}
          </span>
        )}
      </div>
    </li>
  )
}

function GoalCard({ g, onOpen }: { g: SkillGraph; onOpen?: () => void }): ReactNode {
  const away = goalAway(g)
  const line = ['your goal', away ? `${away} ${away === 1 ? 'skill' : 'skills'} away` : away === 0 ? 'ready to build' : ''].filter(Boolean).join(' · ')
  const body = (
    <>
      <MiyagiMark size={28} />
      <span className="max-w-full truncate font-semibold" style={{ marginTop: 10, fontSize: type2.md, color: color.text }}>
        {g.goal!.label}
      </span>
      <span style={{ fontSize: type2.xs, color: color.label }}>{line}</span>
    </>
  )
  const style = { minHeight: PIC_H + 62, padding: 16, borderRadius: layout.radius.card, border: `1.5px dashed ${fill.trackNextMini}` }
  return (
    <li data-portfolio-goal={g.goal!.id} className="flex">
      {onOpen ? (
        <button type="button" onClick={onOpen} aria-label={`${g.goal!.label}. ${line}. Open Skills.`} className="mg-press relative flex w-full cursor-pointer flex-col items-center justify-center gap-[2px] outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid" style={{ ...style, background: 'transparent', outlineColor: color.text }}>
          {body}
        </button>
      ) : (
        <div className="flex w-full flex-col items-center justify-center gap-[2px]" style={style}>
          {body}
        </div>
      )}
    </li>
  )
}

/** Finished projects and the goal, or nothing. `head`: the page's section header; `onOpenGoal`: opens Skills. */
export function Portfolio({ head, onOpenGoal }: { head?: ReactNode; onOpenGoal?: () => void }): ReactNode {
  const g = useSkillGraph((s) => s.graph)
  useEffect(ensureSkillGraph, [])
  if (!g) return null
  // The goal placeholder only for a project the learner (or the engine) chose, never a track end drawn as one.
  const goal = g.goal && !g.goal.inferred && !g.portfolio.some((p) => p.capstoneId === g.goal!.id) ? g.goal : null
  if (!g.portfolio.length && !goal) return null
  return (
    <section aria-labelledby="prog-portfolio" data-prog-portfolio>
      {head}
      <ul className="m-0 grid list-none p-0" style={{ gap: 16, gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', borderRadius: radius2.card }}>
        {g.portfolio.map((p) => (
          <ProjectCard key={p.capstoneId} item={p} g={g} />
        ))}
        {goal && <GoalCard g={g} onOpen={onOpenGoal} />}
      </ul>
    </section>
  )
}
