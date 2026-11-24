/**
 * Feature: skills. The flat Skills page (Adrian's round 3, Nov 23, Notion style):
 *
 *   lede      Goal <name> · 6 of 11 skills · Change          (under the shell's title; Continue sits in the header)
 *   tabs      Path | Map | List, underlined; on the Map: Tracks | Skills | Steps; the search
 *   Path      the goal's path left to right, then "Still to go" (a table) and "Keep fresh" (one row)
 *   Map       Skills: the whole tree bottom up; Tracks: one card per track; Steps: the path's skills with their steps
 *   peek      a skill's page on the right (mastered: the code you wrote, the check it passed, steps, Opens)
 */
import { Check, ChevronRight, Search, X } from 'lucide-react'
import { useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { color, focus, surface } from '../../../core/theme'
import { QuietButton } from '../../../core/ui/buttons'
import { useLibrary } from '../../library/store'
import type { SkillGraph, SkillGraphNode } from '../model'
import { names } from '../copy'
import { setQuery, setView, setZoom, startSkill, useSkills, VIEWS, ZOOMS, type MapZoom, type SkillsView } from '../store'
import { goalBits, minutesLeft, ruleLine, shortDate, statusCell, stillToGo } from './copy'
import { estimate, FOLD_ID, mapLayout, pathLayout, stepsLayout, STEPS, tracksLayout, type FlatLayout, type Measure } from './layout'
import { everyHasMinutes, skillExtras, type SkillStepLine } from './contract'
import { useSkillProof, type ProofItem } from '../proof'
import { usePlanGoal } from '../planGoal'
import { FoldCard, NodeMark, ProjectCard, Refresh, SkillCard, Stage, StateMark, T, TrackCard } from './parts'

export function useWidth<E extends HTMLElement>(initial = 960): [React.RefObject<E | null>, number, number] {
  const ref = useRef<E>(null)
  const [size, setSize] = useState<[number, number]>([initial, 600])
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const read = (): void => setSize([el.clientWidth, el.clientHeight])
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, size[0], size[1]]
}

/** A card label's width in the page's own font (13.5 px, 500), so cards fit their names; the estimate when there is no canvas. */
let ctx: CanvasRenderingContext2D | null | undefined
const widths = new Map<string, number>()
export const measure: Measure = (t) => {
  const hit = widths.get(t)
  if (hit !== undefined) return hit
  if (ctx === undefined) {
    try {
      ctx = document.createElement('canvas').getContext('2d')
      if (ctx) ctx.font = `500 13.5px ${getComputedStyle(document.body).fontFamily || 'system-ui'}`
    } catch {
      ctx = null
    }
  }
  const w = ctx ? Math.ceil(ctx.measureText(t).width) + 2 : estimate(t)
  widths.set(t, w)
  return w
}

// ---- the lede and the tabs ---------------------------------------------------------------------------------------

export function Lede({ g, onChange }: { g: SkillGraph; onChange?: () => void }): ReactNode {
  // An inferred goal gives way to the one Home names (the plan's project), so both pages state one goal (QA R2-02).
  const plan = usePlanGoal(g)
  if (!g.goal) return null
  const bits = plan ? [`${plan.done} of ${plan.total} ${plan.unit ?? 'skills'}`] : goalBits(g, minutesLeft(g, (n) => skillExtras(n, g).estMinutes), { now: Date.now(), minutesPerWeek: g.week?.minutes })
  return (
    <p data-skills-lede className="m-0 truncate" style={{ fontSize: 14.5, lineHeight: '20px', color: T.muted, marginTop: 2 }}>
      Goal{' '}
      <b style={{ color: T.ink, fontWeight: 560 }}>{plan?.title ?? g.goal.label}</b>
      {bits.map((b) => (
        <span key={b}> · {b}</span>
      ))}
      {onChange && (
        <>
          {' · '}
          <button
            type="button"
            onClick={onChange}
            className="cursor-pointer outline-offset-2 focus-visible:outline-2"
            style={{ color: T.muted, textDecoration: 'underline', textDecorationColor: T.track, textUnderlineOffset: 3, outlineColor: focus.dark }}
          >
            Change
          </button>
        </>
      )}
    </p>
  )
}

function Tab<V extends string>({ value, label, on, set }: { value: V; label: string; on: boolean; set: (v: V) => void }): ReactNode {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={on}
      onClick={() => set(value)}
      className="relative flex cursor-pointer items-center outline-offset-[-2px] focus-visible:outline-2"
      style={{ height: 40, padding: '0 9px', fontSize: 14, fontWeight: on ? 560 : 500, color: on ? T.ink : T.muted, outlineColor: focus.dark }}
    >
      {label}
      {on && <span aria-hidden className="absolute" style={{ left: 0, right: 0, bottom: -1, height: 2, borderRadius: 1, background: T.ink }} />}
    </button>
  )
}

function Zoom({ zoom }: { zoom: MapZoom }): ReactNode {
  return (
    <div role="radiogroup" aria-label="Map zoom" className="flex" style={{ gap: 2 }}>
      {ZOOMS.map((z) => (
        <button
          key={z.value}
          type="button"
          role="radio"
          aria-checked={zoom === z.value}
          onClick={() => setZoom(z.value)}
          className="cursor-pointer outline-offset-1 focus-visible:outline-2"
          style={{
            height: 28,
            padding: '0 10px',
            borderRadius: 6,
            fontSize: 13.5,
            fontWeight: zoom === z.value ? 560 : 500,
            color: zoom === z.value ? T.ink : T.muted,
            background: zoom === z.value ? surface.rowHover : 'transparent',
            outlineColor: focus.dark
          }}
        >
          {z.label}
        </button>
      ))}
    </div>
  )
}

function SearchBox(): ReactNode {
  const query = useSkills((s) => s.query)
  const [open, setOpen] = useState(false)
  const showing = open || !!query
  return showing ? (
    <div className="relative" style={{ width: 200, marginLeft: 6 }}>
      <Search aria-hidden size={14} strokeWidth={1.8} className="pointer-events-none absolute" style={{ left: 9, top: 8, color: T.faint }} />
      <input
        type="search"
        aria-label="Find a skill"
        placeholder="Find a skill"
        autoFocus
        autoComplete="off"
        spellCheck={false}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onBlur={() => !query && setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.preventDefault()
            e.stopPropagation()
            setQuery('')
            setOpen(false)
          }
        }}
        className="w-full outline-offset-1 focus-visible:outline-2"
        style={{ height: 30, padding: '0 8px 0 29px', borderRadius: 7, background: surface.well, color: T.ink, fontSize: 13.5, outlineColor: focus.dark }}
      />
    </div>
  ) : (
    <button
      type="button"
      aria-label="Find a skill"
      title="Find a skill"
      onClick={() => setOpen(true)}
      className="mg-press flex cursor-pointer items-center justify-center outline-offset-1 focus-visible:outline-2"
      style={{ width: 30, height: 30, borderRadius: 7, marginLeft: 6, color: T.muted, outlineColor: focus.dark }}
    >
      <Search aria-hidden size={16} strokeWidth={1.8} />
    </button>
  )
}

export function Tabs({ view, zoom }: { view: SkillsView; zoom: MapZoom }): ReactNode {
  return (
    <div data-skills-tabs className="flex items-center" style={{ gap: 4, height: 40, borderBottom: `1px solid ${T.hair}`, marginTop: 16 }}>
      <div role="tablist" aria-label="Skills view" className="flex" style={{ gap: 4 }}>
        {VIEWS.map((v) => (
          <Tab key={v.value} value={v.value} label={v.label} on={view === v.value} set={setView} />
        ))}
      </div>
      <div className="flex-1" />
      {view === 'map' && <Zoom zoom={zoom} />}
      <SearchBox />
    </div>
  )
}

// ---- shared ------------------------------------------------------------------------------------------------------

function matches(g: SkillGraph, query: string): Set<string> | undefined {
  const q = query.trim().toLowerCase()
  if (!q) return undefined
  return new Set(g.nodes.filter((n) => n.label.toLowerCase().includes(q)).map((n) => n.id))
}

/** A selected skill lights itself, what it needs and what it opens; the rest dims. */
function hotSet(g: SkillGraph, selected: string | undefined): Set<string> | undefined {
  const n = selected ? g.byId[selected] : undefined
  if (!n) return undefined
  return new Set([n.id, ...n.requires, ...g.links.filter((l) => l.kind === 'requires' && l.from === n.id).map((l) => l.to)])
}

function useTitleOf(): (n: SkillGraphNode) => string | undefined {
  const library = useLibrary((s) => s.items)
  return (n) => {
    const l = [...n.lessons].sort((a, b) => Number(b.inProgress) - Number(a.inProgress))[0]
    if (!l) return undefined
    return l.title ?? library.find((x) => x.id === (l.libraryId ?? l.lessonId) || x.id === l.lessonId)?.title
  }
}

function Cards({
  g,
  l,
  hot,
  found,
  selected,
  onOpen,
  project,
  onFold
}: {
  g: SkillGraph
  l: FlatLayout
  hot?: Set<string>
  found?: Set<string>
  selected?: string
  onOpen: (id: string) => void
  project: (id: string) => 'tall' | 'wide' | 'small'
  onFold?: () => void
}): ReactNode {
  const dim = (id: string): boolean => (hot ? !hot.has(id) : found ? !found.has(id) : false)
  return (
    <>
      {l.boxes.map((b) => {
        if (b.id === FOLD_ID && l.fold)
          return <FoldCard key={b.id} label={l.fold.label} count={l.fold.ids.length} x={b.x} y={b.y} w={b.w} dim={!!hot || !!found} onOpen={onFold ?? (() => setView('list'))} />
        const n = g.byId[b.id]
        if (!n) return null
        if (n.kind === 'capstone') return <ProjectCard key={b.id} id={b.id} g={g} x={b.x} y={b.y} w={b.w} h={b.h} layout={project(b.id)} dim={dim(b.id)} onOpen={onOpen} />
        return (
          <SkillCard
            key={b.id}
            n={n}
            x={b.x}
            y={b.y}
            w={b.w}
            next={!hot && n.isNext}
            selected={selected === n.id}
            match={!!found && found.has(n.id) && !hot}
            dim={dim(b.id)}
            onOpen={onOpen}
          />
        )
      })}
    </>
  )
}

// ---- Path ------------------------------------------------------------------------------------------------------

function StillToGo({ g, dim, onOpen }: { g: SkillGraph; dim: boolean; onOpen: (id: string) => void }): ReactNode {
  const rows = stillToGo(g)
  const titleOf = useTitleOf()
  const track = (n: SkillGraphNode): string => g.tracks.find((t) => t.id === n.track)?.label ?? n.track
  const th = { textAlign: 'left', fontSize: 12.5, fontWeight: 450, color: T.muted, height: 32, padding: '0 8px', borderBottom: `1px solid ${T.hair}` } as const
  if (!rows.length) return null
  const timed = everyHasMinutes(rows, g)
  return (
    <section data-skills-togo style={{ opacity: dim ? 0.3 : 1, transition: 'opacity .2s' }}>
      <h2 className="m-0" style={{ fontSize: 12.5, fontWeight: 550, color: T.muted, margin: '36px 0 10px' }}>
        Still to go
      </h2>
      <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: 14, tableLayout: 'fixed' }}>
        <colgroup>
          <col style={{ width: '25%' }} />
          <col style={{ width: 144 }} />
          <col style={{ width: '25%' }} />
          <col />
          {timed && <col style={{ width: 72 }} />}
        </colgroup>
        <thead>
          <tr>
            <th style={{ ...th, paddingLeft: 0 }}>Skill</th>
            <th style={th}>Track</th>
            <th style={th}>Status</th>
            <th style={th}>Lesson</th>
            {timed && <th style={{ ...th, textAlign: 'right' }}>Time</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((n) => {
            const locked = n.state === 'locked'
            const pick = g.next?.skillId === n.id ? g.next : undefined
            const title = pick?.lessonTitle ?? titleOf(n)
            const lesson = title ? (pick?.stepIndex !== undefined ? `${title}, step ${pick.stepIndex + 1}` : title) : ''
            const td = { height: 46, padding: '0 8px', borderBottom: `1px solid ${T.hair}`, color: T.text, background: n.isNext ? T.hover : undefined } as const
            return (
              <tr key={n.id} data-skills-row={n.id} onClick={() => onOpen(n.id)} className="cursor-pointer" style={{ opacity: locked ? 0.3 : 1 }}>
                <td style={{ ...td, paddingLeft: 0 }}>
                  <div className="flex min-w-0 items-center" style={{ gap: 10, paddingLeft: n.isNext ? 0 : 0 }}>
                    <NodeMark n={n} />
                    <b className="truncate" style={{ fontWeight: locked ? 500 : 550, color: T.ink }}>
                      {n.label}
                    </b>
                  </div>
                </td>
                <td style={td}>
                  <span className="inline-block max-w-full truncate align-middle" style={{ height: 20, lineHeight: '20px', padding: '0 6px', borderRadius: 4, fontSize: 12.5, background: surface.rowHover, color: T.text }}>
                    {track(n)}
                  </span>
                </td>
                <td style={{ ...td, lineHeight: '18px', paddingBlock: 6 }}>
                  {statusCell(n, g)}
                </td>
                <td className="truncate" style={td}>
                  {lesson}
                </td>
                {timed && (
                  <td className="tabular-nums" style={{ ...td, textAlign: 'right' }}>
                    {`${skillExtras(n, g).estMinutes} min`}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

function KeepFresh({ g, onOpen }: { g: SkillGraph; onOpen: (id: string) => void }): ReactNode {
  const due = g.keepFresh.map((id) => g.byId[id]).filter((n): n is SkillGraphNode => !!n)
  if (!due.length) return null
  return (
    <button
      type="button"
      data-skills-fresh
      onClick={() => onOpen(due[0].id)}
      className="mg-press flex w-full cursor-pointer items-center text-left outline-offset-1 focus-visible:outline-2"
      style={{ gap: 12, minHeight: 44, marginTop: 8, padding: '0 8px', marginInline: -8, width: 'calc(100% + 16px)', borderRadius: 6, fontSize: 14, color: T.text, outlineColor: focus.dark }}
    >
      <Refresh size={15} />
      <b style={{ fontWeight: 550, color: T.ink }}>Keep fresh</b>
      <span className="truncate" style={{ fontSize: 13, color: T.muted }}>
        {names(due.map((n) => n.id), g)}
      </span>
      <span className="flex-1" />
      <ChevronRight aria-hidden size={14} strokeWidth={2} style={{ color: T.faint }} />
    </button>
  )
}

export function PathView({ g, query, selected, onOpen }: { g: SkillGraph; query: string; selected?: string; onOpen: (id: string) => void }): ReactNode {
  const [ref, width] = useWidth<HTMLDivElement>()
  const l = useMemo(() => pathLayout(g, width, measure), [g, width])
  const hot = hotSet(g, selected)
  const found = matches(g, query)
  const scale = l.w > width ? width / l.w : 1
  return (
    <div ref={ref} data-skills-view="path" style={{ paddingTop: 36 }}>
      <Stage l={l} scale={scale} dimEdge={hot ? (a, b) => !(hot.has(a) && hot.has(b)) : undefined}>
        <Cards g={g} l={l} hot={hot} found={found} selected={selected} onOpen={onOpen} project={() => 'tall'} />
      </Stage>
      <StillToGo g={g} dim={!!hot} onOpen={onOpen} />
      <KeepFresh g={g} onOpen={onOpen} />
    </div>
  )
}

// ---- Map ---------------------------------------------------------------------------------------------------------

function StepCard({ g, n, x, y, w, h, onOpen }: { g: SkillGraph; n: SkillGraphNode; x: number; y: number; w: number; h: number; onOpen: (id: string) => void }): ReactNode {
  const locked = n.state === 'locked'
  const { steps, real, reviewDue } = skillExtras(n, g)
  const done = steps.filter((s) => s.passed).length
  const ev = n.evidence
  const note = reviewDue ? 'review due' : n.state === 'practicing' ? (real ? `${done} of ${steps.length}` : ev ? `${ev.done} of ${ev.total}` : '') : n.state === 'ready' ? 'ready' : ''
  // The rows: its steps, else its lessons, else one line saying where it stands (never invented step names).
  const rows: SkillStepLine[] = steps.length
    ? steps
    : [
        n.state === 'practicing' && ev
          ? { title: `${ev.done} of ${ev.total} steps passed`, passed: false, current: true }
          : { title: n.state === 'locked' ? 'Not open yet' : n.state === 'mastered' ? 'Mastered' : 'Not started', passed: n.state === 'mastered' }
      ]
  return (
    <button
      type="button"
      data-skill-card={n.id}
      onClick={() => onOpen(n.id)}
      className="mg-press absolute cursor-pointer text-left outline-offset-2 focus-visible:outline-2"
      style={{ left: x, top: y, width: w, height: h, padding: '14px 16px 12px', borderRadius: 10, background: locked ? T.sunk : T.card, boxShadow: n.isNext ? T.next : locked ? undefined : T.chip }}
    >
      <div className="flex items-center" style={{ gap: 9, marginBottom: 10 }}>
        <NodeMark n={n} />
        <b className="truncate" style={{ fontSize: 15, fontWeight: 640, color: locked ? T.faint : T.ink }}>
          {n.label}
        </b>
        <span className="ml-auto shrink-0" style={{ fontSize: 12, color: T.muted }}>
          {note}
        </span>
      </div>
      {rows.map((st, i) => (
        <div
          key={i}
          data-skill-step={st.passed ? 'done' : st.current ? 'current' : 'open'}
          className="flex items-center"
          style={{ gap: 9, height: STEPS.line, fontSize: 13.5, fontWeight: st.current ? 600 : 400, color: locked ? T.faint : st.passed || st.current ? T.ink : T.muted }}
        >
          <span className="flex shrink-0" style={{ opacity: locked ? 0.55 : 1 }}>
            <StateMark state={st.passed ? 'mastered' : st.current ? 'practicing' : 'ready'} f={0.5} size={14} />
          </span>
          <span className="truncate">{st.title}</span>
        </div>
      ))}
    </button>
  )
}

type Box = FlatLayout['boxes'][number]

/** How many cards a vertical line at content x (unscaled stage at `scale`) cuts through. */
function cutAt(boxes: Box[], x: number, scale: number): number {
  return boxes.filter((b) => b.x * scale < x && (b.x + b.w) * scale > x).length
}

/** Where the Map opens: the focus card (the goal, or the next skill) in view and near the middle, with the pane's edges
 *  stopping between cards when they can (no card cut in half on open). Scroll coordinates (the gutter included). */
function openingLeft(boxes: Box[], focus: Box | undefined, contentW: number, viewW: number, scale: number, gutter: number): number {
  const max = Math.max(0, contentW - viewW)
  if (!max) return 0
  const fx = focus ? gutter + (focus.x + focus.w / 2) * scale : contentW / 2
  const ideal = Math.max(0, Math.min(max, fx - viewW / 2))
  // Near the middle first; when every spot there cuts a card, anywhere the focus card still shows.
  let best = ideal
  let bestScore = Infinity
  for (const reach of [96, max]) {
    for (let L = Math.max(0, ideal - reach); L <= Math.min(max, ideal + reach); L += 4) {
      if (focus && (gutter + focus.x * scale < L + 8 || gutter + (focus.x + focus.w) * scale > L + viewW - 8)) continue
      const cutL = L <= 0 ? 0 : cutAt(boxes, L - gutter, scale)
      const cutR = L >= max ? 0 : cutAt(boxes, L + viewW - gutter, scale)
      const score = (cutL + cutR) * 1000 + Math.abs(L - ideal)
      if (score < bestScore) {
        bestScore = score
        best = L
      }
    }
    if (bestScore < 1000) break
  }
  return Math.round(best)
}

/** The Map's soft edges: a fade on each side the map goes on past, so it reads as one you pan. */
function fadeMask(e: { l: boolean; r: boolean; t: boolean; b: boolean }): CSSProperties {
  if (!e.l && !e.r && !e.t && !e.b) return {}
  const F = 40
  const across = `linear-gradient(to right, ${e.l ? 'transparent' : 'black'}, black ${F}px, black calc(100% - ${F}px), ${e.r ? 'transparent' : 'black'})`
  const down = `linear-gradient(to bottom, ${e.t ? 'transparent' : 'black'}, black ${F}px, black calc(100% - ${F}px), ${e.b ? 'transparent' : 'black'})`
  return { maskImage: `${across}, ${down}`, WebkitMaskImage: `${across}, ${down}`, maskComposite: 'intersect', WebkitMaskComposite: 'source-in' }
}

/** The smallest each zoom draws its cards: Skills and Steps at the Path's card size (they pan instead), Tracks a little under. */
const MIN_SCALE: Record<MapZoom, number> = { skills: 1, steps: 1, tracks: 0.9 }
/** The space around the map inside the pane: no card ever sits on the pane's edge. */
const GUTTER = 28

export function MapView({ g, query, selected, onOpen }: { g: SkillGraph; query: string; selected?: string; onOpen: (id: string) => void }): ReactNode {
  const zoom = useSkills((s) => s.zoom)
  const [ref, width, height] = useWidth<HTMLDivElement>()
  const map = useMemo(() => mapLayout(g, measure), [g])
  const lines = (id: string): number => (g.byId[id] ? Math.max(1, skillExtras(g.byId[id], g).steps.length) : 1)
  const l = useMemo(() => (zoom === 'tracks' ? tracksLayout(g) : zoom === 'steps' ? stepsLayout(g, lines) : map), [g, map, zoom]) // eslint-disable-line react-hooks/exhaustive-deps
  const hot = hotSet(g, selected)
  const found = matches(g, query)
  // Fit the pane while the cards keep their size; past that the map pans (it never shrinks the words).
  const fit = Math.min((width - 2 * GUTTER) / Math.max(1, l.w), (height - 2 * GUTTER) / Math.max(1, l.h))
  const scale = Math.max(MIN_SCALE[zoom], Math.min(1, fit))
  const contentW = l.w * scale + 2 * GUTTER
  const focus = zoom === 'steps' ? (l.boxes.find((b) => g.byId[b.id]?.isNext) ?? l.boxes[l.boxes.length - 1]) : l.boxes.find((b) => b.id === g.goal?.id)
  const [fade, setFade] = useState({ l: false, r: false, t: false, b: false })
  const readFade = (): void => {
    const el = ref.current
    if (!el) return
    const f = { l: el.scrollLeft > 1, r: el.scrollLeft + el.clientWidth < el.scrollWidth - 1, t: el.scrollTop > 1, b: el.scrollTop + el.clientHeight < el.scrollHeight - 1 }
    setFade((o) => (o.l === f.l && o.r === f.r && o.t === f.t && o.b === f.b ? o : f))
  }
  // Open on the goal's column with the projects along the top (Skills, Tracks), or on the next skill (Steps).
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.scrollLeft = openingLeft(l.boxes, focus, contentW, el.clientWidth, scale, GUTTER)
    el.scrollTop = focus ? Math.max(0, Math.min(el.scrollHeight - el.clientHeight, focus.y * scale)) : 0
    readFade()
  }, [zoom, l.w, l.h, Math.round(width / 40), Math.round(height / 40)]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div
      ref={ref}
      data-skills-view="map"
      data-skills-zoom={zoom}
      onScroll={readFade}
      className="relative min-h-0 flex-1 overflow-auto"
      style={{ ...fadeMask(fade), scrollbarWidth: 'none' }}
    >
      <div className="flex min-h-full w-max min-w-full items-center justify-center" style={{ padding: GUTTER }}>
        <Stage l={l} scale={scale} dimEdge={hot ? (a, b) => !(hot.has(a) && hot.has(b)) : undefined}>
          {zoom === 'tracks' ? (
            <>
              {l.boxes.map((b) => {
                if (!b.id.startsWith('track:')) return <ProjectCard key={b.id} id={b.id} g={g} x={b.x} y={b.y} w={b.w} h={b.h} layout="wide" onOpen={onOpen} />
                const t = g.tracks.find((x) => `track:${x.id}` === b.id)
                return t ? <TrackCard key={b.id} label={t.label} done={t.mastered} total={t.total} x={b.x} y={b.y} w={b.w} h={b.h} /> : null
              })}
            </>
          ) : zoom === 'steps' ? (
            <>
              {l.boxes.map((b) => {
                const n = g.byId[b.id]
                return n ? <StepCard key={b.id} g={g} n={n} x={b.x} y={b.y} w={STEPS.w} h={b.h} onOpen={onOpen} /> : null
              })}
            </>
          ) : (
            <Cards g={g} l={l} hot={hot} found={found} selected={selected} onOpen={onOpen} project={(id) => (id === g.goal?.id ? 'wide' : 'small')} />
          )}
        </Stage>
      </div>
    </div>
  )
}

// ---- the peek (a skill's page on the right) -----------------------------------------------------------------------

/** "Step 3 of 3": where the proof's step sits among the skill's steps (blank when it isn't one of them). */
function proofStep(p: ProofItem, steps: SkillStepLine[]): string {
  const i = steps.findIndex((s) => s.title === p.stepTitle)
  return i >= 0 ? `Step ${i + 1} of ${steps.length}` : p.stepTitle
}

const lab = { fontSize: 12.5, fontWeight: 550, color: T.muted, margin: '22px 0 8px' } as const

function Tag({ children, ok }: { children: ReactNode; ok?: boolean }): ReactNode {
  return (
    <span className="inline-flex items-center" style={{ gap: 5, height: 20, padding: '0 6px', borderRadius: 4, fontSize: 12.5, background: ok ? color.greenTint : surface.rowHover, color: ok ? color.greenText : T.text, whiteSpace: 'nowrap' }}>
      {children}
    </span>
  )
}

export function Peek({ g, id, now, onClose, onOpen }: { g: SkillGraph; id: string; now: number; onClose: () => void; onOpen: (id: string) => void }): ReactNode {
  const titleOf = useTitleOf()
  const n = g.byId[id]
  // The proof shows for a skill with a pass behind it (mastered, a passed step, or a kept proof).
  const proof = useSkillProof(n?.id, !!n && (n.state === 'mastered' || n.proofIds.length > 0 || !!n.steps?.some((s) => s.passed)))
  if (!n) return null
  const track = g.tracks.find((t) => t.id === n.track)?.label ?? n.track
  const opens = g.links.filter((l) => l.kind === 'requires' && l.from === n.id).map((l) => g.byId[l.to]).filter((x): x is SkillGraphNode => !!x)
  const needs = n.requires.map((x) => g.byId[x]).filter((x): x is SkillGraphNode => !!x)
  const { steps, real, reviewDue } = skillExtras(n, g)
  const lesson = titleOf(n)
  const cap = n.kind === 'capstone' ? g.capstones.find((c) => c.id === n.id) : undefined
  const state = n.state === 'mastered' ? (reviewDue ? 'Review due' : 'Mastered') : n.state === 'practicing' ? 'Practicing' : n.state === 'ready' ? 'Ready' : 'Locked'
  const startable = n.kind === 'skill' && n.state !== 'locked'
  return (
    <aside
      data-skills-peek={n.id}
      aria-label={n.label}
      className="absolute flex flex-col overflow-y-auto"
      style={{ top: 0, right: 0, bottom: 0, width: 440, maxWidth: '100%', padding: '0 28px 24px', background: T.card, boxShadow: surface.shadowSmall, zIndex: 5 }}
    >
      <div className="flex shrink-0 items-center" style={{ height: 44, gap: 6, fontSize: 13.5, color: T.muted, margin: '0 -14px' }}>
        <span style={{ paddingLeft: 14 }}>{track}</span>
        <span style={{ color: T.faint }}>/</span>
        <b className="truncate" style={{ fontWeight: 500, color: T.text }}>
          {n.label}
        </b>
        <span className="flex-1" />
        <button type="button" aria-label="Close" title="Close" onClick={onClose} className="mg-press flex cursor-pointer items-center justify-center outline-offset-1 focus-visible:outline-2" style={{ width: 28, height: 28, borderRadius: 7, color: T.muted, outlineColor: focus.dark }}>
          <X aria-hidden size={16} strokeWidth={1.8} />
        </button>
      </div>
      <h2 className="m-0" style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.02em', color: T.ink, margin: '14px 0 8px' }}>
        {n.label}
      </h2>
      <div className="flex flex-wrap" style={{ gap: 6 }}>
        <Tag ok={n.state === 'mastered'}>
          {n.state === 'mastered' ? <Check aria-hidden size={12} strokeWidth={2.4} /> : <NodeMark n={n} />}
          {state}
        </Tag>
        {n.masteredAt && <Tag>{shortDate(n.masteredAt)}</Tag>}
        <Tag>{track}</Tag>
      </div>
      <p className="m-0" style={{ fontSize: 13, color: T.muted, marginTop: 10 }}>
        {cap?.brief ?? ruleLine(n, now)}
      </p>
      {proof?.text ? (
        <>
          <div style={lab}>The code you wrote</div>
          <pre data-skills-proof-code className="m-0 shrink-0 overflow-x-auto" style={{ font: '13px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace', background: surface.well, borderRadius: 8, padding: '12px 14px', color: T.text }}>
            {proof.text}
            {proof.output && (
              <span className="block" style={{ marginTop: 8, color: T.muted }}>
                {proof.output}
              </span>
            )}
          </pre>
          {proof.file && <div style={{ fontSize: 13, color: T.muted, marginTop: 6 }}>{proof.truncated ? `${proof.file}, cut short` : proof.file}</div>}
        </>
      ) : (
        n.example?.code && (
          <>
            <div style={lab}>{n.state === 'mastered' ? 'The code you wrote' : 'What you will write'}</div>
            <pre className="m-0 shrink-0 overflow-x-auto" style={{ font: '13px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace', background: surface.well, borderRadius: 8, padding: '12px 14px', color: T.text }}>
              {n.example.code}
            </pre>
            {n.example.caption && <div style={{ fontSize: 13, color: T.muted, marginTop: 6 }}>{n.example.caption}</div>}
          </>
        )
      )}
      {proof && (
        <>
          <div style={lab}>The check it passed</div>
          <div data-skills-proof-check className="flex items-start" style={{ gap: 12 }}>
            <span className="flex shrink-0" style={{ marginTop: 3 }}>
              <StateMark state="mastered" />
            </span>
            <div className="min-w-0">
              <b className="block" style={{ fontSize: 14, fontWeight: 600, color: T.ink }}>
                {proof.check}
              </b>
              <div className="truncate" style={{ fontSize: 13, color: T.muted, marginTop: 2 }}>
                {[proofStep(proof, steps), proof.lessonTitle, proof.at ? shortDate(proof.at) : ''].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>
        </>
      )}
      {steps.length > 0 && (
        <>
          <div style={lab}>{real ? 'Steps' : 'Lessons'}</div>
          {steps.map((st, i) => (
            <div key={i} className="flex items-center" style={{ gap: 12, minHeight: 36, fontSize: 14, fontWeight: st.current ? 600 : 400, color: st.passed || st.current ? T.text : T.muted, boxShadow: i ? `0 -1px 0 ${T.hair}` : undefined }}>
              <span className="flex shrink-0" style={{ opacity: n.state === 'locked' ? 0.55 : 1 }}>
                <StateMark state={st.passed ? 'mastered' : st.current ? 'practicing' : 'ready'} />
              </span>
              <span className="min-w-0 truncate">{st.title}</span>
              {real && st.lesson && (i === 0 || steps[i - 1].lesson !== st.lesson) && (
                <span className="ml-auto shrink-0 truncate" style={{ fontSize: 13, color: T.muted, maxWidth: '45%' }}>
                  {st.lesson}
                </span>
              )}
            </div>
          ))}
        </>
      )}
      {n.state === 'locked' && needs.length > 0 && (
        <>
          <div style={lab}>Needs</div>
          <div className="flex flex-wrap" style={{ gap: 6 }}>
            {needs.map((x) => (
              <button key={x.id} type="button" onClick={() => onOpen(x.id)} className="cursor-pointer">
                <Tag ok={x.state === 'mastered'}>{x.label}</Tag>
              </button>
            ))}
          </div>
        </>
      )}
      {opens.length > 0 && (
        <>
          <div style={lab}>Opens</div>
          <div className="flex flex-wrap" style={{ gap: 6 }}>
            {opens.map((x) => (
              <button key={x.id} type="button" onClick={() => onOpen(x.id)} className="cursor-pointer">
                <Tag>{x.label}</Tag>
              </button>
            ))}
          </div>
        </>
      )}
      <div className="flex-1" style={{ minHeight: 24 }} />
      {startable && (
        <div className="flex" style={{ gap: 8 }}>
          <QuietButton label={n.state === 'mastered' ? 'Practice again' : n.state === 'practicing' ? 'Continue' : 'Start'} onClick={() => startSkill(n, g)} />
          {lesson && n.state === 'mastered' && <QuietButton label="Open lesson" onClick={() => startSkill(n, g)} />}
        </div>
      )}
    </aside>
  )
}
