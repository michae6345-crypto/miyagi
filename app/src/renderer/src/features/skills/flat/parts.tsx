/**
 * Feature: skills. The flat tree's small parts (round 3, Notion style): the 14 px state mark, the skill card, the
 * project card, the track card, the stage that draws a FlatLayout, and the page's tokens.
 *
 * States: mastered = the green check (the only green), practicing = a ring filling in ink, ready = an open ink ring,
 * locked = a lock on a sunk card. Review due = mastered with a small refresh mark after the name (never a demotion).
 * Next = a 1.5 px ink ring around the card.
 */
import type { CSSProperties, ReactNode } from 'react'
import { ChevronRight, RotateCw } from 'lucide-react'
import { color, fill, surface } from '../../../core/theme'
import { MiyagiMark } from '../../../core/ui/Mark'
import type { SkillGraph, SkillGraphNode } from '../model'
import { usePicture } from '../extras/Portfolio'
import { skillExtras } from './contract'
import { CARD_H, type EdgeKind, type FlatLayout } from './layout'

/** The flat page's tokens, all theme variables (light and dark follow the app). */
export const T = {
  ink: color.text,
  text: color.text,
  muted: color.label,
  faint: color.faint,
  hair: surface.border,
  card: 'var(--s-sheet)',
  sunk: surface.row,
  hover: surface.row,
  track: fill.trackSoft,
  chip: `0 0 0 1px ${fill.trackSoft}`,
  lift: `0 0 0 1px ${fill.trackSoft}, var(--e-tile)`,
  next: `0 0 0 1.5px ${color.text}`,
  edge: { done: color.green, open: fill.ring, locked: fill.trackSoft } as Record<EdgeKind, string>
} as const

function arc(cx: number, cy: number, r: number, f: number): string {
  const a = f * 2 * Math.PI - Math.PI / 2
  const x = cx + r * Math.cos(a)
  const y = cy + r * Math.sin(a)
  return `M${cx} ${cy - r}A${r} ${r} 0 ${f > 0.5 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)}`
}

export type MarkState = SkillGraphNode['state']

/** The 14 px state mark. `f`: practicing's share done (0..1). */
export function StateMark({ state, f = 0.5, size = 14 }: { state: MarkState; f?: number; size?: number }): ReactNode {
  return (
    <svg aria-hidden viewBox="0 0 14 14" width={size} height={size} className="block shrink-0">
      {state === 'mastered' ? (
        <>
          <circle cx="7" cy="7" r="7" fill={color.green} />
          <path d="M4 7.3l2.1 2.1 4-4.4" stroke={color.onGreen} strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ) : state === 'practicing' ? (
        <>
          <circle cx="7" cy="7" r="5.6" fill="none" stroke={fill.trackSoft} strokeWidth="1.8" />
          <path d={arc(7, 7, 5.6, Math.min(0.999, Math.max(0.08, f)))} fill="none" stroke={T.ink} strokeWidth="1.8" strokeLinecap="round" />
        </>
      ) : state === 'ready' ? (
        <circle cx="7" cy="7" r="5.7" fill="none" stroke={T.ink} strokeWidth="1.5" />
      ) : (
        <>
          <rect x="3.2" y="6.3" width="7.6" height="5.6" rx="1.4" fill={T.faint} />
          <path d="M4.9 6.3V4.7a2.1 2.1 0 0 1 4.2 0v1.6" fill="none" stroke={T.faint} strokeWidth="1.3" />
        </>
      )}
    </svg>
  )
}

export const share = (n: SkillGraphNode): number => (n.evidence && n.evidence.total ? n.evidence.done / n.evidence.total : 0.5)

export function NodeMark({ n }: { n: SkillGraphNode }): ReactNode {
  return <StateMark state={n.state} f={share(n)} />
}

export function Refresh({ size = 12 }: { size?: number }): ReactNode {
  return <RotateCw aria-hidden size={size} strokeWidth={2} className="shrink-0" style={{ color: T.faint }} />
}

const cardBase: CSSProperties = {
  position: 'absolute',
  height: CARD_H,
  display: 'flex',
  alignItems: 'center',
  gap: 7,
  padding: '0 10px',
  borderRadius: 7,
  fontSize: 13.5,
  whiteSpace: 'nowrap'
}

/** A skill card on the stage. */
export function SkillCard({
  n,
  x,
  y,
  w,
  next,
  selected,
  dim,
  match,
  onOpen
}: {
  n: SkillGraphNode
  x: number
  y: number
  w: number
  next?: boolean
  selected?: boolean
  dim?: boolean
  match?: boolean
  onOpen: (id: string) => void
}): ReactNode {
  const locked = n.state === 'locked'
  return (
    <button
      type="button"
      data-skill-card={n.id}
      data-state={n.state}
      aria-label={`${n.label}, ${n.state === 'mastered' ? (n.review ? 'mastered, review due' : 'mastered') : n.state}`}
      onClick={() => onOpen(n.id)}
      className="mg-press cursor-pointer text-left outline-offset-2 focus-visible:outline-2"
      style={{
        ...cardBase,
        left: x,
        top: y,
        width: w,
        background: locked ? T.sunk : T.card,
        boxShadow: next || selected || match ? T.next : locked ? undefined : T.chip,
        color: locked ? T.faint : T.ink,
        fontWeight: next ? 600 : locked ? 450 : 500,
        opacity: dim ? 0.3 : 1,
        transition: 'opacity .2s'
      }}
    >
      <NodeMark n={n} />
      <span className="min-w-0 truncate">{n.label}</span>
      {n.review && (
        <span className="ml-auto flex">
          <Refresh />
        </span>
      )}
    </button>
  )
}

/** The folded base track ("python 4 >"). Opens the List. */
export function FoldCard({ label, count, x, y, w, dim, onOpen }: { label: string; count: number; x: number; y: number; w: number; dim?: boolean; onOpen: () => void }): ReactNode {
  return (
    <button
      type="button"
      data-skill-fold
      aria-label={`${label}, ${count} skills mastered`}
      onClick={onOpen}
      className="mg-press cursor-pointer text-left outline-offset-2 focus-visible:outline-2"
      style={{ ...cardBase, left: x, top: y, width: w, background: T.card, boxShadow: T.chip, color: T.ink, fontWeight: 500, opacity: dim ? 0.3 : 1 }}
    >
      <StateMark state="mastered" />
      <span className="min-w-0 truncate">{label}</span>
      <span className="ml-auto tabular-nums" style={{ fontSize: 12, fontWeight: 450, color: T.muted }}>
        {count}
      </span>
      <ChevronRight aria-hidden size={12} strokeWidth={2} style={{ color: T.faint, marginLeft: -2 }} />
    </button>
  )
}

/** The project's picture: the learner's artifact would go here; until then the bonsai on a quiet fill. */
/** The project's own result (SkillCapstone.artifact, an image) when there is one; the bonsai until then. */
function ProjectArt({ h, path, caption }: { h: number; path?: string; caption?: string }): ReactNode {
  const src = usePicture(path)
  return (
    <div aria-hidden={!src} className="flex shrink-0 items-center justify-center overflow-hidden" style={{ height: h, borderRadius: 6, background: T.sunk }}>
      {src ? <img src={src} alt={caption ?? 'Your result'} draggable={false} className="h-full w-full select-none object-cover" /> : <MiyagiMark size={Math.min(32, h - 12)} />}
    </div>
  )
}

export function ProjectCard({
  id,
  g,
  x,
  y,
  w,
  h,
  layout,
  dim,
  onOpen
}: {
  id: string
  g: SkillGraph
  x: number
  y: number
  w: number
  h: number
  layout: 'tall' | 'wide' | 'small'
  dim?: boolean
  onOpen: (id: string) => void
}): ReactNode {
  const n = g.byId[id]
  const isGoal = g.goal?.id === id
  const art = n ? skillExtras(n, g).artifact : undefined
  const done = isGoal && g.goal ? g.goal.mastered / Math.max(1, g.goal.total) : 0
  const style: CSSProperties = {
    position: 'absolute',
    left: x,
    top: y,
    width: w,
    height: h,
    borderRadius: 10,
    background: T.card,
    boxShadow: layout === 'small' ? T.chip : T.lift,
    color: T.ink,
    opacity: dim ? 0.3 : 1
  }
  const title = (
    <b className="block" style={{ fontSize: layout === 'small' ? 13.5 : 14.5, fontWeight: 620, lineHeight: 1.25, color: T.ink }}>
      {n?.label ?? id}
    </b>
  )
  return (
    <button type="button" data-skill-project={id} onClick={() => onOpen(id)} className="mg-press flex cursor-pointer text-left outline-offset-2 focus-visible:outline-2" style={style}>
      {layout === 'tall' ? (
        <div className="flex h-full w-full flex-col" style={{ padding: '10px 12px 12px' }}>
          <ProjectArt h={54} path={art?.path} caption={art?.caption} />
          <div style={{ fontSize: 12, color: T.muted, marginTop: 9 }}>Project</div>
          {title}
          {isGoal && (
            <div style={{ marginTop: 'auto', height: 4, borderRadius: 2, background: T.track, overflow: 'hidden' }}>
              <div style={{ width: `${Math.round(done * 100)}%`, height: '100%', background: color.green, borderRadius: 2 }} />
            </div>
          )}
        </div>
      ) : layout === 'wide' ? (
        <div className="flex h-full w-full items-center" style={{ padding: '10px 12px', gap: 12 }}>
          <div style={{ width: 84 }}>
            <ProjectArt h={46} path={art?.path} caption={art?.caption} />
          </div>
          <div className="min-w-0">
            <div style={{ fontSize: 12, color: T.muted }}>Project</div>
            {title}
          </div>
        </div>
      ) : (
        <div className="min-w-0" style={{ padding: '7px 10px' }}>
          <div style={{ fontSize: 12, color: T.muted }}>Project</div>
          <div className="truncate">{title}</div>
        </div>
      )}
    </button>
  )
}

/** The Map zoomed out: one card per track, its share mastered. */
export function TrackCard({ label, done, total, x, y, w, h }: { label: string; done: number; total: number; x: number; y: number; w: number; h: number }): ReactNode {
  return (
    <div data-skill-track={label} style={{ position: 'absolute', left: x, top: y, width: w, height: h, padding: '9px 12px 0', borderRadius: 8, background: T.card, boxShadow: T.chip }}>
      <div className="flex items-baseline">
        <b className="truncate" style={{ fontSize: 14, fontWeight: 600, color: T.ink }}>
          {label}
        </b>
        <span className="ml-auto shrink-0 tabular-nums" style={{ fontSize: 12, color: T.muted }}>
          {done} of {total}
        </span>
      </div>
      <div style={{ marginTop: 9, height: 4, borderRadius: 2, background: T.track, overflow: 'hidden' }}>
        <div style={{ width: `${total ? Math.round((done / total) * 100) : 0}%`, height: '100%', background: color.green }} />
      </div>
    </div>
  )
}

/** Draws a layout's edges and its track labels; the cards come in as children (absolutely placed). */
export function Stage({ l, scale = 1, dimEdge, children }: { l: FlatLayout; scale?: number; dimEdge?: (from: string, to: string) => boolean; children: ReactNode }): ReactNode {
  return (
    <div style={{ width: l.w * scale, height: l.h * scale, position: 'relative' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, width: l.w, height: l.h, transform: scale === 1 ? undefined : `scale(${scale})`, transformOrigin: '0 0' }}>
        <svg aria-hidden width={l.w} height={l.h} viewBox={`0 0 ${l.w} ${l.h}`} className="absolute inset-0 overflow-visible">
          {l.edges.map((e, i) => (
            <path
              key={`${e.from}>${e.to}:${i}`}
              d={e.d}
              fill="none"
              stroke={T.edge[e.kind]}
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={dimEdge?.(e.from, e.to) ? 0.3 : 1}
            />
          ))}
        </svg>
        {l.labels.map((t) => (
          <div
            key={`label:${t.track}`}
            data-skill-track-label={t.track}
            style={{
              position: 'absolute',
              top: t.y,
              ...(t.align === 'right' ? { right: l.w - t.x } : { left: t.x }),
              fontSize: 12,
              fontWeight: 500,
              color: T.faint,
              whiteSpace: 'nowrap'
            }}
          >
            {t.text}
          </div>
        ))}
        {children}
      </div>
    </div>
  )
}
