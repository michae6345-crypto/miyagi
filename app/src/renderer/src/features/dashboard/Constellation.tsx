/**
 * Feature: dashboard. The skill constellation: one cluster per track, nodes in columns by prerequisite depth, edges as
 * thin gray lines (green once both ends are mastered), another track's shared idea as a dashed ghost on the left.
 * Hover a node for its label, state and detail; click it for its card (lessons that teach it, Start).
 *
 *   mastered    green, a check            practicing  a white ring
 *   available   a solid gray outline       locked      a dashed gray outline at 40%
 *   review due  a white dot on the green node (the node stays green)
 */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { CodeText } from '../../core/ui/atoms'
import { alpha, color, fill, radius2, status, surface, type2 } from '../../core/theme'
import { layoutTrack, nodeStates, reviewFor, reviewIndex, trackHeadline, type NodeState } from './model'
import { caption, Empty, h2, NodeGlyph, STATE_WORD } from './parts'
import { select, useDash } from './store'
import type { DashData, DashTrack, ReviewEntry } from './types'

const ROW_H = 72
const NODE_TOP = 6
const GLYPH = 28
const MIN_COL = 104
const MAX_COL = 168

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setW(el.clientWidth)
    const ro = new ResizeObserver(() => setW(el.clientWidth))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

const LEGEND: Array<{ state: NodeState; due?: boolean; word: string }> = [
  { state: 'mastered', word: 'Mastered' },
  { state: 'practicing', word: 'Practicing' },
  { state: 'available', word: 'Ready to learn' },
  { state: 'locked', word: 'Locked' },
  { state: 'mastered', due: true, word: 'Review due' }
]

function Cluster({ t, dueOf, width }: { t: DashTrack; dueOf: (id: string) => boolean; width: number }): ReactNode {
  const selected = useDash((s) => (s.selected?.track === t.track ? s.selected.id : undefined))
  const [hover, setHover] = useState<string>()
  const lay = layoutTrack(t)
  const states = nodeStates(t)
  const colW = Math.max(MIN_COL, Math.min(MAX_COL, Math.floor(width / lay.cols)))
  const w = Math.max(width, lay.cols * colW)
  const h = lay.rows * ROW_H
  const inCol: Record<number, number> = {}
  for (const n of lay.nodes) inCol[n.col] = (inCol[n.col] ?? 0) + 1
  const pos = new Map(
    lay.nodes.map((n) => {
      const offset = ((lay.rows - (inCol[n.col] ?? 1)) / 2) * ROW_H
      return [n.id, { x: Math.round((w - lay.cols * colW) / 2 + n.col * colW + colW / 2), y: Math.round(offset + n.row * ROW_H + NODE_TOP + GLYPH / 2) }]
    })
  )
  const ghostPos = (i: number): { x: number; y: number } => ({
    x: Math.round((w - lay.cols * colW) / 2 + colW / 2),
    y: Math.round(((lay.rows - t.cross.length) / 2) * ROW_H + i * ROW_H + NODE_TOP + GLYPH / 2)
  })
  const skill = (id: string): DashTrack['skills'][number] | undefined => t.skills.find((s) => s.id === id)
  const curve = (a: { x: number; y: number }, b: { x: number; y: number }, r1: number, r2: number): string => {
    const x1 = a.x + r1
    const x2 = b.x - r2
    const mx = (x1 + x2) / 2
    return `M${x1},${a.y} C${mx},${a.y} ${mx},${b.y} ${x2},${b.y}`
  }
  const tip = hover ? skill(hover) : undefined
  const tipAt = hover ? pos.get(hover) : undefined
  return (
    <section data-track={t.track} aria-label={trackHeadline(t)} className="flex flex-col gap-[8px]">
      <div className="flex items-baseline justify-between gap-[12px]">
        <h3 className="m-0 min-w-0 truncate" style={{ ...h2, fontSize: type2.md }}>
          {t.track}
        </h3>
        <span className="shrink-0 tabular-nums" style={caption}>
          {t.mastered} of {t.total} mastered
        </span>
      </div>
      <div className="overflow-x-auto overflow-y-hidden" style={{ borderRadius: radius2.card, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
        <div className="relative" style={{ width: w, height: h + 8 }}>
          <svg width={w} height={h + 8} className="pointer-events-none absolute inset-0" aria-hidden>
            {t.edges.map((e) => {
              const a = pos.get(e.from)
              const b = pos.get(e.to)
              if (!a || !b) return null
              const both = states[e.from] === 'mastered' && states[e.to] === 'mastered'
              return <path key={`${e.from}-${e.to}`} data-edge={both ? 'mastered' : 'open'} d={curve(a, b, 13, 13)} fill="none" stroke={both ? alpha(status.passed, 0.7) : fill.ring} strokeWidth={both ? 1.6 : 1.2} />
            })}
            {t.cross.map((c, i) => {
              const b = pos.get(c.to)
              if (!b) return null
              return <path key={`x-${i}`} data-edge="cross" d={curve(ghostPos(i), b, 8, 13)} fill="none" stroke={fill.ring} strokeWidth={1.2} strokeDasharray="3 3" />
            })}
          </svg>
          {t.cross.map((c, i) => {
            const g = ghostPos(i)
            return (
              <div
                key={`g-${i}`}
                data-cross={c.track}
                title={c.note}
                className="absolute flex flex-col items-center gap-[4px] text-center"
                style={{ left: g.x - colW / 2 + 4, top: g.y - GLYPH / 2 + 7, width: colW - 8 }}
              >
                <svg width={14} height={14} viewBox="0 0 14 14" aria-hidden>
                  <circle cx="7" cy="7" r="5.6" fill="none" stroke={status.watching} strokeWidth="1.2" strokeDasharray="2 2" />
                </svg>
                <span className="line-clamp-2" style={{ fontSize: type2.micro, lineHeight: '13px', color: color.faint, marginTop: 7 }}>
                  {c.track ? `${c.track}: ` : ''}
                  {c.label}
                </span>
              </div>
            )
          })}
          {t.skills.map((s) => {
            const p = pos.get(s.id)
            if (!p) return null
            const st = states[s.id]
            const due = st === 'mastered' && dueOf(s.id)
            const on = selected === s.id
            return (
              <button
                key={s.id}
                type="button"
                data-node={s.id}
                data-state={st}
                data-due={due || undefined}
                aria-pressed={on}
                aria-label={`${s.label.split(String.fromCharCode(96)).join('')}: ${STATE_WORD[st]}${due ? ', review due' : ''}`}
                onMouseEnter={() => setHover(s.id)}
                onMouseLeave={() => setHover((h0) => (h0 === s.id ? undefined : h0))}
                onFocus={() => setHover(s.id)}
                onBlur={() => setHover((h0) => (h0 === s.id ? undefined : h0))}
                onClick={() => select(on ? undefined : { track: t.track, id: s.id })}
                className="absolute flex cursor-pointer flex-col items-center gap-[4px] text-center outline-none"
                style={{ left: p.x - colW / 2 + 4, top: p.y - GLYPH / 2, width: colW - 8, opacity: st === 'locked' ? 0.4 : 1 }}
              >
                <NodeGlyph state={st} due={due} selected={on} />
                <span
                  className="line-clamp-2 w-full"
                  style={{ fontSize: type2.xs, lineHeight: '15px', color: st === 'available' || st === 'locked' ? color.label : color.text, fontWeight: on ? 600 : 400 }}
                >
                  <CodeText text={s.label} />
                </span>
              </button>
            )
          })}
          {tip && tipAt && !selected && (
            <div
              role="tooltip"
              className="pointer-events-none absolute z-10 flex flex-col gap-[2px]"
              style={{
                left: Math.max(4, Math.min(w - 224, tipAt.x - 110)),
                top: tipAt.y + GLYPH / 2 + 34 > h ? Math.max(0, tipAt.y - GLYPH / 2 - 62) : tipAt.y + GLYPH / 2 + 34,
                width: 220,
                padding: '8px 10px',
                borderRadius: radius2.row,
                background: surface.sheet,
                boxShadow: `inset 0 0 0 1px ${surface.border}, ${surface.shadowSmall}`
              }}
            >
              <span className="truncate" style={{ fontSize: type2.xs, fontWeight: 600, color: color.text }}>
                <CodeText text={tip.label} />
              </span>
              <span style={{ fontSize: type2.micro, color: states[tip.id] === 'mastered' ? status.passed : color.label }}>{STATE_WORD[states[tip.id]]}</span>
              {tip.detail && (
                <span className="line-clamp-2" style={{ fontSize: type2.micro, color: color.label }}>
                  {tip.detail}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

export function Constellation({ data, review, loading, children }: { data?: DashData; review: ReviewEntry[]; loading: boolean; children?: ReactNode }): ReactNode {
  const [ref, width] = useWidth<HTMLDivElement>()
  const tracks = data?.tracks ?? []
  const dueIdx = new Set<string>()
  const idx = reviewIndex(review)
  for (const t of tracks) for (const s of t.skills) if (reviewFor(idx, s)) dueIdx.add(`${t.track}\u0000${s.id}`)
  const mastered = tracks.reduce((n, t) => n + t.mastered, 0)
  const total = tracks.reduce((n, t) => n + t.total, 0)
  // Esc closes the open skill card.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape' && useDash.getState().selected) select(undefined)
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])
  return (
    <section aria-labelledby="dash-skills" className="relative flex min-h-0 min-w-0 flex-col gap-[12px]" style={{ padding: 20, borderRadius: radius2.chip, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-x-[16px] gap-y-[6px]">
        <div className="flex flex-col gap-[2px]">
          <h2 id="dash-skills" style={{ ...h2, fontSize: type2.lg }}>
            Skills
          </h2>
          <span style={caption}>{tracks.length ? `${mastered} of ${total} mastered, checked in your own work.` : 'Checked in your own work, not quizzes.'}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-[12px] gap-y-[4px]" style={caption}>
          {LEGEND.map((l) => (
            <span key={l.word} className="flex items-center gap-[4px]">
              <span style={{ opacity: l.state === 'locked' ? 0.4 : 1, display: 'inline-flex' }}>
                <NodeGlyph state={l.state} due={l.due} size={16} />
              </span>
              {l.word}
            </span>
          ))}
        </div>
      </div>
      <div ref={ref} className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <span style={caption}>Reading your progress</span>
        ) : !tracks.length ? (
          <div style={{ padding: 4 }}>
            <Empty title="No skills yet" body="Finish a lesson. The skills its checks proved show up here." />
          </div>
        ) : (
          width > 0 && (
            <div className="flex flex-col gap-[16px]" style={{ paddingBottom: 4 }}>
              {tracks.map((t) => (
                <Cluster key={t.track} t={t} width={width} dueOf={(id) => dueIdx.has(`${t.track}\u0000${id}`)} />
              ))}
            </div>
          )
        )}
      </div>
      {children}
    </section>
  )
}
