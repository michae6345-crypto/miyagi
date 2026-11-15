/**
 * The skill map (mockup 10's "Skill map" panel), drawn from card.skillMap only: lanes with a header on the left,
 * concept nodes left to right, arrows between them. Mastered = a green ring with a check (green only ever means
 * passed), learning = a white ring with a dot, next = a dashed ring. Other tracks' concepts sit in a lane above,
 * with dashed "shared idea" arrows down to the node they feed. Hover or click a node: its detail in the strip below.
 */
import { motion } from 'motion/react'
import { useMemo, useState, type ReactNode } from 'react'
import { BookOpen, Code2, FileText, Layers, Sigma, Wrench, type LucideIcon } from 'lucide-react'
import { color, fill, spring } from '../../core/theme'
import { DETAIL_LINE, LANE_W, LINE, NODE, NOTE_LINE, layout, type Lane } from './layout'
import type { SkillMap as Map, SkillNode, SkillState } from './types'

/** A lane's glyph by track name (neutral tile; the name itself always comes from the data). */
const GLYPH: Array<[RegExp, LucideIcon]> = [
  [/math|algebra|calculus|statistic|probab/i, Sigma],
  [/code|program|python|javascript|typescript|software/i, Code2],
  [/paper|research|read/i, FileText],
  [/tool|git|terminal|shell|devops/i, Wrench]
]
const glyph = (name: string, track: boolean): LucideIcon => GLYPH.find(([rx]) => rx.test(name))?.[1] ?? (track ? Layers : BookOpen)

const STATE_WORD: Record<SkillState, string> = { mastered: 'Mastered', learning: 'Learning', next: 'Up next' }

/** The node's ring (and the legend's small one). */
export function Ring({ state, size = NODE, delay = 0 }: { state: SkillState | 'shared'; size?: number; delay?: number }): ReactNode {
  const r = size / 2 - 1.5
  const c = size / 2
  const k = size / NODE
  if (state === 'mastered')
    return (
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
        <circle cx={c} cy={c} r={r} fill="none" stroke={color.green} strokeWidth={size > 20 ? 2.2 : 1.6} />
        <motion.path
          d={`M${c - 7 * k} ${c + 0.5 * k} L${c - 2 * k} ${c + 5.5 * k} L${c + 7.5 * k} ${c - 5 * k}`}
          fill="none"
          stroke={color.green}
          strokeWidth={size > 20 ? 2.4 : 1.6}
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.3, ease: 'easeOut', delay: delay + 0.12 }}
        />
      </svg>
    )
  if (state === 'learning')
    return (
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
        <circle cx={c} cy={c} r={r} fill="none" stroke={color.text} strokeWidth={size > 20 ? 2.2 : 1.6} />
        <circle cx={c} cy={c} r={Math.max(2, 4 * k)} fill={color.text} />
      </svg>
    )
  if (state === 'shared')
    return (
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
        <circle cx={c} cy={c} r={r} fill={fill.tile} stroke={fill.ring} strokeWidth={1.6} />
      </svg>
    )
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      <circle cx={c} cy={c} r={r} fill="none" stroke={fill.ring} strokeWidth={size > 20 ? 1.8 : 1.4} strokeDasharray={size > 20 ? '3.5 4' : '2 2.5'} />
      <circle cx={c} cy={c} r={Math.max(1.5, 2.5 * k)} fill={color.faint} />
    </svg>
  )
}

function LaneHeader({ lane }: { lane: Lane }): ReactNode {
  const I = glyph(lane.name, lane.kind === 'track')
  const sub = lane.kind === 'track' ? `${lane.done} of ${lane.total} mastered` : `${lane.total} shared idea${lane.total === 1 ? '' : 's'}`
  return (
    <div className="absolute left-0 flex items-center gap-[10px]" style={{ top: lane.centerY - 17, width: LANE_W - 12 }}>
      <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[9px]" style={{ background: fill.tile, color: fill.tileGlyph }}>
        <I size={15} strokeWidth={1.8} />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[14px] font-medium leading-[18px]" style={{ color: color.text }}>
          {lane.name}
        </span>
        <span className="block truncate text-[12px] leading-[16px]" style={{ color: color.label }}>
          {sub}
        </span>
      </span>
    </div>
  )
}

/** The default selection: the first node still being learned, else the first one up next, else the last. */
const firstOpen = (nodes: SkillNode[]): string | undefined =>
  (nodes.find((n) => n.state === 'learning') ?? nodes.find((n) => n.state === 'next') ?? nodes[nodes.length - 1])?.id

export function SkillMapView({ map, width }: { map: Map; width: number }): ReactNode {
  const L = useMemo(() => layout(map, width), [map, width])
  const [sel, setSel] = useState<string | undefined>(() => firstOpen(map.nodes))
  const node = map.nodes.find((n) => n.id === sel)
  const shared = node ? map.cross.filter((c) => c.to === node.id) : []
  const states = (['mastered', 'learning', 'next'] as const).filter((s) => map.nodes.some((n) => n.state === s))

  return (
    <div data-skill-map>
      <div className="mb-[18px] flex items-center gap-[16px]">
        <span className="text-[15px] font-semibold" style={{ color: color.text }}>
          Skill map
        </span>
        <span className="flex-1" />
        {states.map((s) => (
          <span key={s} className="flex items-center gap-[6px] text-[12px]" style={{ color: color.label }}>
            <Ring state={s} size={13} />
            {s === 'next' ? 'Next' : STATE_WORD[s]}
          </span>
        ))}
        {map.cross.length > 0 && (
          <span className="flex items-center gap-[6px] text-[12px]" style={{ color: color.label }}>
            <svg width="18" height="6" className="shrink-0">
              <path d="M1 3 H17" stroke={fill.ring} strokeWidth="1.6" strokeDasharray="3 3" />
            </svg>
            Shared idea
          </span>
        )}
      </div>

      <div className="relative" style={{ width: L.width, height: L.height }}>
        {L.rules.map((y) => (
          <div key={y} className="absolute left-0 right-0 h-px" style={{ top: y, background: fill.rule }} />
        ))}
        <svg className="pointer-events-none absolute left-0 top-0" width={L.width} height={L.height}>
          <defs>
            <marker id="sk-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0.5 0.8 L7.5 4 L0.5 7.2 Z" fill={fill.ring} />
            </marker>
          </defs>
          {L.paths.map((p, i) => (
            <motion.path
              key={i}
              d={p.d}
              fill="none"
              stroke={fill.ring}
              strokeWidth={p.dashed ? 1.5 : 1.4}
              strokeDasharray={p.dashed ? '4 4' : undefined}
              markerEnd="url(#sk-arrow)"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, delay: 0.2 }}
            />
          ))}
        </svg>
        {L.lanes.map((lane) => (
          <LaneHeader key={`${lane.kind}:${lane.name}`} lane={lane} />
        ))}
        {L.notes.map((n) => (
          <div
            key={`${n.x}:${n.y}`}
            className="absolute overflow-hidden text-[12px]"
            style={{ left: n.x, top: n.y, width: n.w, lineHeight: `${NOTE_LINE}px`, color: color.faint, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 2 }}
            title={n.text}
          >
            {n.text}
          </div>
        ))}
        {L.cross.map((c, i) => (
          <motion.div
            key={c.key}
            className="absolute flex flex-col items-center"
            style={{ left: c.x - L.labelW / 2, top: c.y - NODE / 2, width: L.labelW }}
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ ...spring, delay: 0.1 + i * 0.04 }}
            title={c.note}
          >
            <Ring state="shared" />
            <span className="mt-[8px] overflow-hidden text-center text-[13px]" style={{ lineHeight: `${LINE}px`, color: color.text, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 2 }}>
              {c.label}
            </span>
          </motion.div>
        ))}
        {L.nodes.map((n, i) => (
          <motion.button
            key={n.id}
            type="button"
            data-node={n.id}
            data-state={n.state}
            className="absolute flex cursor-pointer flex-col items-center rounded-[10px] outline-none"
            style={{ left: n.x - L.labelW / 2, top: n.y - NODE / 2, width: L.labelW }}
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ ...spring, delay: 0.1 + i * 0.03 }}
            onMouseEnter={() => setSel(n.id)}
            onFocus={() => setSel(n.id)}
            onClick={() => setSel(n.id)}
            title={n.detail}
          >
            <span className="grid place-items-center rounded-full" style={{ boxShadow: sel === n.id ? `0 0 0 3px ${fill.highlight}` : undefined }}>
              <Ring state={n.state} delay={0.1 + i * 0.03} />
            </span>
            <span
              className="mt-[8px] overflow-hidden text-center text-[13px]"
              style={{ lineHeight: `${LINE}px`, color: n.state === 'next' ? color.label : color.text, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 3 }}
            >
              {n.label}
            </span>
            {n.state === 'learning' && n.detail && (
              <span className="mt-[2px] truncate text-[12px]" style={{ lineHeight: `${DETAIL_LINE}px`, color: color.faint, maxWidth: L.labelW }}>
                {n.detail}
              </span>
            )}
          </motion.button>
        ))}
      </div>

      {node && (
        <div data-skill-detail className="mt-[18px] flex min-h-[40px] items-center gap-[12px] border-t pt-[14px]" style={{ borderColor: fill.rule }}>
          <Ring state={node.state} size={22} />
          <span className="shrink-0 text-[14px] font-medium" style={{ color: color.text }}>
            {node.label}
          </span>
          <span
            className="shrink-0 rounded-full px-[8px] py-[2px] text-[11px] font-medium"
            style={node.state === 'mastered' ? { background: color.greenTint, color: color.green } : { background: fill.chip, color: color.label, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}` }}
          >
            {STATE_WORD[node.state]}
          </span>
          <span className="min-w-0 flex-1 truncate text-[13px]" style={{ color: color.label }}>
            {node.detail}
            {shared.length > 0 && (
              <span style={{ color: color.faint }}>
                {node.detail ? ' · ' : ''}
                Shared idea from {shared.map((c) => `${c.track}: ${c.label}`).join(', ')}
              </span>
            )}
          </span>
        </div>
      )}
    </div>
  )
}
