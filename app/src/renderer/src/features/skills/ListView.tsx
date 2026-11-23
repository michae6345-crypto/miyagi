/**
 * Feature: skills. The List: one card per track in one centered column, the goal's track first.
 *
 *   head    the track's name, "2 of 4 mastered" and one short bar per skill (green mastered, ink practicing)
 *   skills  every skill in the track's order as its glyph and name (practicing adds "2 of 4", review adds "review");
 *           each opens the panel
 *   foot    when it was last practiced, and one useful line (where the goal is, a project's distance, a review due)
 * Search keeps the cards with a match and lights the matches.
 */
import type { ReactNode } from 'react'
import { color, fill, radius2, type2, typeScale } from '../../core/theme'
import { CARD, PageColumn } from '../shell/ui'
import { Scroller } from '../shell/pages/Column'
import type { SkillGraph, SkillGraphNode, SkillGraphTrack } from './model'
import { practicedLine } from './copy'
import { Glyph } from './SkillNode'

function TrackBar({ t, g }: { t: SkillGraphTrack; g: SkillGraph }): ReactNode {
  const skills = t.nodeIds.map((id) => g.byId[id]).filter((n) => n?.kind === 'skill')
  return (
    <span role="img" aria-label={`${t.mastered} of ${t.total} mastered`} className="flex items-center" style={{ gap: 3, width: Math.min(skills.length * 22, 132) }}>
      {skills.map((n) => (
        <span key={n.id} className="block flex-1" style={{ height: 4, borderRadius: radius2.round, background: n.state === 'mastered' ? color.green : n.state === 'practicing' ? color.text : fill.hairline }} />
      ))}
    </span>
  )
}

function Square({ locked }: { locked: boolean }): ReactNode {
  return (
    <svg width={16} height={16} aria-hidden className="block shrink-0">
      <rect x={0.75} y={0.75} width={14.5} height={14.5} rx={4} fill="none" stroke={locked ? fill.ring : color.text} strokeWidth={1.5} strokeDasharray={locked ? '2 2.4' : undefined} />
    </svg>
  )
}

function Chip({ n, dim, onOpen }: { n: SkillGraphNode; dim: boolean; onOpen: (id: string) => void }): ReactNode {
  const locked = n.state === 'locked'
  const extra = n.state === 'practicing' && n.evidence ? `${n.evidence.done} of ${n.evidence.total}` : n.review ? 'review' : n.isGoal ? 'your goal' : undefined
  return (
    <button
      type="button"
      data-skills-chip={n.id}
      className="mg-press flex cursor-pointer items-center gap-[8px] whitespace-nowrap"
      style={{ height: 32, padding: '0 10px 0 8px', marginLeft: -8, borderRadius: radius2.control, opacity: dim ? 0.3 : 1 }}
      onClick={() => onOpen(n.id)}
    >
      {n.kind === 'capstone' ? <Square locked={locked} /> : <Glyph n={n} size={16} />}
      <span style={{ fontSize: type2.md, color: locked ? color.label : color.text, fontWeight: n.isNext ? 600 : 400 }}>{n.label}</span>
      {extra && <span style={{ fontSize: type2.xs, color: color.label, fontVariantNumeric: 'tabular-nums' }}>{extra}</span>}
    </button>
  )
}

function footLine(t: SkillGraphTrack, g: SkillGraph): string | undefined {
  const ns = t.nodeIds.map((id) => g.byId[id])
  if (g.goal && ns.some((n) => n.id === g.goal!.id)) return `Your goal is here: ${g.goal.label}`
  const next = ns.find((n) => n.isNext)
  if (next) return `Next: ${next.label}`
  const project = ns.find((n) => n.kind === 'capstone' && n.state !== 'mastered')
  if (project) {
    const c = g.capstones.find((x) => x.id === project.id)
    const left = (c?.requires.length ? c.requires : project.requires).filter((id) => g.byId[id]?.state !== 'mastered').length
    return left ? `Project: ${project.label}, ${left} skill${left === 1 ? '' : 's'} away` : `Project: ${project.label} is ready`
  }
  const review = ns.find((n) => n.review)
  if (review) return `${review.label}: due for a review`
  return undefined
}

export function ListView({ g, query, now, onOpen }: { g: SkillGraph; query: string; now: number; onOpen: (id: string) => void }): ReactNode {
  const q = query.trim().toLowerCase()
  const match = (n: SkillGraphNode): boolean => !q || n.label.toLowerCase().includes(q)
  const goalTrack = g.goal ? g.byId[g.goal.id]?.track : undefined
  const tracks = [...g.tracks].sort((a, b) => Number(b.id === goalTrack) - Number(a.id === goalTrack)).filter((t) => t.nodeIds.some((id) => match(g.byId[id])))
  return (
    <Scroller>
      <PageColumn wide top={16} bottom={32} gap={12}>
        {tracks.map((t) => {
          const ns = t.nodeIds.map((id) => g.byId[id])
          const last = Math.max(0, ...ns.map((n) => n.lastPracticedAt ?? n.masteredAt ?? 0))
          const when = practicedLine(last || undefined, now)
          const note = footLine(t, g)
          return (
            <section key={t.id} data-skills-list-track={t.id} aria-label={t.label} className="flex flex-col" style={{ ...CARD, padding: '18px 24px 14px', gap: 10 }}>
              <div className="flex items-center" style={{ gap: 16 }}>
                <h3 className="m-0 min-w-0 flex-1 truncate" style={{ ...typeScale.cardTitle, color: color.text }}>
                  {t.label}
                </h3>
                <span style={{ fontSize: type2.sm, color: color.label, fontVariantNumeric: 'tabular-nums' }}>
                  {t.mastered} of {t.total} mastered
                </span>
                <TrackBar t={t} g={g} />
              </div>
              <div className="flex flex-wrap items-center" style={{ columnGap: 16, rowGap: 2, paddingLeft: 8 }}>
                {ns.map((n) => (
                  <Chip key={n.id} n={n} dim={!match(n)} onOpen={onOpen} />
                ))}
              </div>
              {(when || note) && (
                <div className="flex flex-wrap items-center" style={{ gap: 24, paddingTop: 10, borderTop: `1px solid ${fill.hairline}`, fontSize: type2.sm, color: color.label }}>
                  <span>{when ? <>Last practiced <span style={{ color: color.text, fontWeight: 500 }}>{when}</span></> : 'Not started yet'}</span>
                  {note && <span>{note}</span>}
                </div>
              )}
            </section>
          )
        })}
        {!tracks.length && <span style={{ fontSize: type2.sm, color: color.label, padding: '24px 0' }}>No skill matches “{query.trim()}”.</span>}
      </PageColumn>
    </Scroller>
  )
}
