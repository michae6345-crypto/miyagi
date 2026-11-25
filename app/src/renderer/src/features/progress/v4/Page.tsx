/**
 * Feature: progress. The v4 Progress page (Adrian's ui-next mock: `progress`, `progress-empty`; mockups -21 and -28),
 * after his Nov 24 trim pass. Two columns: the work on the left (this week, the last 12 weeks, tracks, recently
 * passed), the numbers in a rail on the right (bon and how it grows, the goal, closest to mastered, plans, keep fresh)
 * with one hairline between them. Under 860 px the rail drops under the main column.
 *
 * Rows and hairlines, no tiles. Green only for passed (the check on a recent pass, a track's mastered bar); everything
 * else ink and gray. One primary per surface (Continue, or Start a lesson on the first run).
 *
 * First run (nothing passed yet): ten-minute lessons and three plans to start, and goals to pick; no week chart until a
 * bar has something in it. Never rows of zeros. The primary is the lesson open now, else the one to continue, else
 * Start a lesson, whether or not anything has passed yet.
 */
import { Check, ChevronRight, Compass, Flag, Play, RefreshCw, SquarePen } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useLesson } from '../../../core/lesson'
import { closeWindow } from '../../../core/surfaces'
import { PrimaryButton } from '../../../core/ui/atoms'
import { color, fill, type2 } from '../../../core/theme'
import { PokeBon } from '../../buddy/Poke'
import { LEVELS, progressOf, useGrowth } from '../../buddy/growth'
import { NAME } from '../../buddy/name'
import { continueList } from '../../dashboard/continue'
import { nodeStates, prereqs } from '../../dashboard/model'
import { canReview, requestDashboard, startGoal, startReview, startSaved, useDash } from '../../dashboard/store'
import type { DashData, DashTrack } from '../../dashboard/types'
import { openLauncher } from '../../library/Library'
import { useLibrary } from '../../library/store'
import { useAskPlanGoal, usePlanGoal } from '../../skills/planGoal'
import { useSkillGraph } from '../../skills/store'
import { setPage } from '../../shell/store'
import { PageColumn } from '../../shell/ui'
import { Scroller } from '../../shell/pages/Column'
import {
  aboutHr,
  allNums,
  bonSteps,
  closest,
  dayLabel,
  freshLabel,
  fromGraph,
  type FreshRow,
  GOAL_PICKS,
  goalLine,
  guide,
  hm,
  lastPassed,
  plain,
  railGoal,
  STARTER_PLANS,
  STARTERS,
  weekBars,
  weekNums,
  weeks12,
  whenLabel,
  type Bar,
  type Starter,
  type V4
} from './model'
import { requestV4, useV4 } from './store'

const RAIL_W = 300
const TWO_COL = 860
const ROUTE = 'library' as const

const muted: CSSProperties = { color: color.label }
const num: CSSProperties = { fontVariantNumeric: 'tabular-nums' }

function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(t)
  }, [])
  return now
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(1040)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const read = (): void => setW(el.clientWidth)
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

// ---- small parts ------------------------------------------------------------------------------------------------

/** A section label, with a quiet link on the right ("Skills ›"). */
function Sec({ children, link, onLink, first }: { children: ReactNode; link?: string; onLink?: () => void; first?: boolean }): ReactNode {
  return (
    <div
      className="flex items-center"
      style={{
        fontSize: type2.xs,
        fontWeight: 550,
        color: color.label,
        margin: first ? '0 0 10px' : '30px 0 10px'
      }}
    >
      <h2 className="m-0" style={{ font: 'inherit' }}>
        {children}
      </h2>
      {link &&
        (onLink ? (
          <button type="button" onClick={onLink} className="mg-press ml-auto flex cursor-pointer items-center gap-[2px]" style={{ fontWeight: 450, color: color.label, minHeight: 24, marginBlock: -3 }}>
            {link}
            <ChevronRight size={13} strokeWidth={1.8} />
          </button>
        ) : (
          <span className="ml-auto" style={{ fontWeight: 450, color: color.label }}>
            {link}
          </span>
        ))}
    </div>
  )
}

function Meter({ done, total, green, width = 64 }: { done: number; total: number; green?: boolean; width?: number }): ReactNode {
  const f = total > 0 ? Math.max(0, Math.min(1, done / total)) : 0
  return (
    <span aria-hidden className="block shrink-0 overflow-hidden" style={{ width, height: 4, borderRadius: 2, background: fill.track }}>
      <span
        className="block h-full"
        style={{
          width: `${f * 100}%`,
          borderRadius: 2,
          background: green ? color.green : color.text
        }}
      />
    </span>
  )
}

function PassCheck(): ReactNode {
  return (
    <span
      aria-label="Passed"
      className="inline-grid shrink-0 place-items-center"
      style={{
        width: 16,
        height: 16,
        borderRadius: '50%',
        background: color.green
      }}
    >
      <Check size={10} strokeWidth={3} style={{ color: color.onGreen }} />
    </span>
  )
}

function Tag({ children }: { children: ReactNode }): ReactNode {
  return (
    <span
      className="inline-flex items-center whitespace-nowrap"
      style={{
        height: 20,
        padding: '0 6px',
        borderRadius: 4,
        fontSize: 12.5,
        lineHeight: '20px',
        background: fill.chip,
        color: color.text
      }}
    >
      {children}
    </span>
  )
}

const hair = `1px solid ${color.hairline}`

const clamp2: CSSProperties = {
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
  whiteSpace: 'normal',
  lineHeight: 1.3
}

type Col = { t: string; right?: boolean; wrap?: boolean }

/**
 * A table-like list: a header row, then rows with a hairline between them. One grid for the whole table (rows are
 * `display: contents`), so `max-content` columns line up across rows the way an HTML table's do. A `wrap` column runs
 * to two lines instead of cutting its text off.
 */
function Table({ cols, head, rows, rowH = 40, label }: { cols: string; head: Col[]; rows: ReactNode[][]; rowH?: number; label: string }): ReactNode {
  const GAP = 16
  return (
    <div role="table" aria-label={label} className="grid" style={{ gridTemplateColumns: cols, fontSize: type2.md }}>
      <div role="row" style={{ display: 'contents' }}>
        {head.map((h, j) => (
          <span
            key={h.t}
            role="columnheader"
            className="flex items-center whitespace-nowrap"
            style={{
              height: 32,
              borderBottom: hair,
              paddingRight: j < head.length - 1 ? GAP : 0,
              justifyContent: h.right ? 'flex-end' : 'flex-start',
              fontSize: 12.5,
              color: color.label
            }}
          >
            {h.t}
          </span>
        ))}
      </div>
      {rows.map((r, i) => (
        <div key={i} role="row" style={{ display: 'contents' }}>
          {r.map((c, j) => (
            <div
              key={j}
              role="cell"
              className="flex min-w-0 items-center"
              style={{
                minHeight: rowH,
                padding: `5px ${j < r.length - 1 ? GAP : 0}px 5px 0`,
                borderBottom: i < rows.length - 1 ? hair : undefined
              }}
            >
              <div className={head[j]?.wrap ? 'min-w-0 flex-1' : 'min-w-0 flex-1 truncate'} title={cellText(c)} style={{ textAlign: head[j]?.right ? 'right' : 'left', ...(head[j]?.wrap ? clamp2 : null) }}>
                {c}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

/** Numbers on one line with hairlines between them. */
function Stats({ items }: { items: Array<{ big: ReactNode; label: string }> }): ReactNode {
  return (
    <div className="flex" style={{ marginTop: 14 }}>
      {items.map((s, i) => (
        <div
          key={s.label}
          className="min-w-0 flex-1"
          style={{
            padding: i ? '0 20px' : '0 20px 0 0',
            borderLeft: i ? `1px solid ${fill.track}` : undefined
          }}
        >
          <div
            style={{
              fontSize: 22,
              fontWeight: 650,
              letterSpacing: '-.015em',
              lineHeight: 1.2,
              color: color.text,
              ...num
            }}
          >
            {s.big}
          </div>
          <div className="truncate" title={s.label} style={{ fontSize: 12.5, color: color.label }}>
            {s.label}
          </div>
        </div>
      ))}
    </div>
  )
}

function Minutes({ min }: { min: number }): ReactNode {
  const { h, m } = hm(min)
  const small: CSSProperties = {
    fontSize: 14,
    fontWeight: 550,
    color: color.label,
    marginLeft: 2,
    letterSpacing: 0
  }
  return (
    <>
      {h > 0 && (
        <>
          {h}
          <small style={{ ...small, marginRight: 6 }}>h</small>
        </>
      )}
      {m}
      <small style={small}>min</small>
    </>
  )
}

// ---- charts -----------------------------------------------------------------------------------------------------

/** Plain bars: today (or this week) in ink, the rest gray, a dashed round line, values over the bars. */
function Bars({ bars, minutes, weekly, height, empty }: { bars: Bar[]; minutes: boolean; weekly: boolean; height: number; empty?: boolean }): ReactNode {
  const W = 684
  const base = height - 30
  const top = 18
  const max = Math.max(...bars.map((b) => b.value), 0)
  const g = guide(max, minutes, weekly)
  const scale = Math.max(max, g?.at ?? 0, 1) * 1.08
  const bw = weekly ? 40 : 60
  const gap = (W - bars.length * bw) / (bars.length - 1)
  const peak = bars.reduce((p, b, i) => (b.value > bars[p].value ? i : p), 0)
  const unit = minutes ? 'minutes' : 'steps'
  return (
    <svg
      role="img"
      aria-label={`${weekly ? 'Last 12 weeks' : 'This week'}, ${unit} ${weekly ? 'a week' : 'a day'}`}
      viewBox={`0 0 ${W} ${height}`}
      className="block h-auto w-full"
      style={{ overflow: 'visible' }}
    >
      <path d={`M0 ${base}H${W}`} stroke={fill.track} />
      {g && (
        <>
          <path d={`M0 ${base - (g.at / scale) * (base - top)}H${W}`} stroke={color.hairline} strokeDasharray="2 4" />
          <text x={weekly ? 0 : W} y={base - (g.at / scale) * (base - top) - 5} textAnchor={weekly ? 'start' : 'end'} style={{ fontSize: 11.5, fill: color.label }}>
            {g.label}
          </text>
        </>
      )}
      {bars.map((b, i) => {
        const x = i * (bw + gap)
        const h = (b.value / scale) * (base - top)
        const showValue = !empty && b.value > 0 && (!weekly || b.now || i === peak)
        return (
          <g key={b.key}>
            <title>{`${b.label || b.key}: ${b.value} ${unit}`}</title>
            {b.value > 0 ? (
              <path d={`M${x} ${base}V${base - h + 4}a4 4 0 0 1 4-4h${bw - 8}a4 4 0 0 1 4 4V${base}z`} style={{ fill: b.now ? color.text : fill.ring }} />
            ) : (
              <rect x={x} y={base - 2} width={bw} height={2} style={{ fill: fill.track }} />
            )}
            {showValue && (
              <text
                x={x + bw / 2}
                y={base - h - 7}
                textAnchor="middle"
                style={{
                  fontSize: 11.5,
                  fontWeight: b.now ? 600 : 550,
                  fill: b.now ? color.text : color.label
                }}
              >
                {b.value}
              </text>
            )}
            {b.label && (
              <text
                x={x + bw / 2}
                y={base + 18}
                textAnchor="middle"
                style={{
                  fontSize: 11.5,
                  fontWeight: b.now ? 600 : 400,
                  fill: b.now ? color.text : color.label
                }}
              >
                {b.label}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

// ---- tracks -----------------------------------------------------------------------------------------------------

function trackNext(t: DashTrack): string {
  if (t.total > 0 && t.mastered >= t.total) return 'Done'
  const states = nodeStates(t)
  const open = t.skills.find((s) => states[s.id] === 'practicing') ?? t.skills.find((s) => states[s.id] === 'available')
  if (open) return plain(open.label)
  const locked = t.skills.find((s) => states[s.id] === 'locked')
  if (!locked) return ''
  const label = (id: string): string => plain(t.skills.find((s) => s.id === id)?.label ?? id)
  const needs = prereqs(t, locked.id).map(label)
  return needs.length ? `Needs ${needs.length > 1 ? `${needs.slice(0, -1).join(', ')} and ${needs[needs.length - 1]}` : needs[0]}` : ''
}
/** A track's last practice: its skills' lastPracticedAt, or the newest `activity.recent` pass of one of its skills. */
const trackLast = (t: DashTrack, passed: Map<string, number>): number | undefined => {
  const ts = t.skills.map((s) => Math.max(s.lastPracticedAt ?? 0, passed.get(s.label.toLowerCase()) ?? 0)).filter(Boolean)
  return ts.length ? Math.max(...ts) : undefined
}

// ---- the rail ---------------------------------------------------------------------------------------------------

/** "24 steps grew bon. 1 more to Budding." */
function bonLine(passed: number, name: string): string {
  const p = progressOf(passed)
  const grew = `${p.steps} ${p.steps === 1 ? 'step' : 'steps'} grew ${name}.`
  return p.next ? `${grew} ${p.next.left} more to ${p.next.name}.` : `${grew} Fully grown.`
}

function Bon({ passed }: { passed: number }): ReactNode {
  const p = progressOf(passed)
  return (
    <div data-progress-bon className="flex flex-col items-center text-center" style={{ paddingTop: 2 }}>
      <PokeBon size={128} level={p.level} />
      <div
        style={{
          fontSize: 12.5,
          color: color.text,
          fontWeight: 550,
          marginTop: 6
        }}
      >
        {NAME ?? 'bon'} · Level {p.level}, {p.name}
      </div>
      {/* bon's own count (since it started growing) is not the stats' "steps passed" in all: it gets its own words (QA R4-04). */}
      <div style={{ fontSize: 12.5, color: color.label, marginTop: 2 }}>{bonLine(passed, NAME ?? 'bon')}</div>
      {p.next && (
        <div className="flex w-full items-center justify-center gap-[8px]" style={{ marginTop: 8 }}>
          <Meter done={p.fraction * 100} total={100} width={140} />
        </div>
      )}
    </div>
  )
}

function RRow({ children, onClick, tall }: { children: ReactNode; onClick?: () => void; tall?: boolean }): ReactNode {
  const style: CSSProperties = { minHeight: tall ? 48 : 33, fontSize: 13.5 }
  const cls = 'mg-v4-rrow flex w-full items-center gap-[10px] text-left'
  return onClick ? (
    <button type="button" onClick={onClick} className={`${cls} mg-press cursor-pointer`} style={style}>
      {children}
    </button>
  ) : (
    <div className={cls} style={style}>
      {children}
    </div>
  )
}
const rl: CSSProperties = {
  flex: 1,
  minWidth: 0,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  fontWeight: 520,
  color: color.text
}
const rr: CSSProperties = {
  color: color.label,
  fontSize: 13,
  whiteSpace: 'nowrap',
  ...num
}

function Rail({ data, v4, now, stacked }: { data?: DashData; v4: V4; now: number; stacked: boolean }): ReactNode {
  const steps = useGrowth((g) => g.steps)
  // The engine's bon (`bon`), else the local count; never Seed at 0 while activity counts passed steps.
  const passed = bonSteps(v4, steps)
  // The engine's own goal / need / review first; else the skill graph the Skills and Home pages draw (QA R3-04).
  const sg = useSkillGraph(now)
  const graph = fromGraph(sg)
  // One goal across Home, Skills and here (QA R2-02): an inferred graph goal gives way to the plan's project, as on Skills.
  useAskPlanGoal()
  const goal = railGoal(v4.goal, usePlanGoal(sg), graph.goal)
  const own = closest(v4)
  const near = own.length ? own : graph.near
  const review = (data?.review?.items ?? []).slice(0, 3)
  const fresh: FreshRow[] = review.length ? review.map((r) => ({ ...r, key: r.skillId ?? r.label })) : graph.fresh
  return (
    <aside data-progress-rail aria-label="Your numbers" style={stacked ? { marginTop: 40, paddingTop: 30, borderTop: hair } : { borderLeft: hair, padding: '0 0 48px 32px' }}>
      <Bon passed={passed} />
      {goal && (
        <>
          <Sec link="Change" onLink={() => setPage('skills')}>
            Goal
          </Sec>
          <div data-progress-goal>
            <div className="flex items-center gap-[8px]" style={{ fontSize: type2.md }}>
              <Flag size={15} strokeWidth={1.8} style={muted} />
              <b className="line-clamp-2" title={goal.title} style={{ fontWeight: 560, color: color.text, lineHeight: 1.3 }}>
                {goal.title}
              </b>
            </div>
            <div style={{ margin: '11px 0 8px' }}>
              <Meter done={goal.mastered} total={goal.total} width={RAIL_W - 32} />
            </div>
            <div className="flex justify-between gap-[12px]" style={{ fontSize: 13, color: color.label, ...num }}>
              <span className="whitespace-nowrap">
                {goal.mastered} of {goal.total} {goal.unit ?? 'skills'}
              </span>
              <span className="truncate" title={goalLine(goal)}>
                {goalLine(goal)}
              </span>
            </div>
          </div>
        </>
      )}
      {near.length > 0 && (
        <>
          <Sec>Closest to mastered</Sec>
          <div className="mg-v4-rows">
            {near.map((s) => (
              <RRow key={s.label}>
                <span style={{ ...rl, ...clamp2, padding: '6px 0' }}>{s.label}</span>
                <Meter done={s.done} total={s.need} width={48} />
                <span style={{ ...rr, width: 74, textAlign: 'right' }}>
                  {s.done} of {s.need} steps
                </span>
              </RRow>
            ))}
          </div>
        </>
      )}
      {v4.plans.length > 0 && (
        <>
          <Sec link="Browse plans" onLink={() => setPage('lessons')}>
            Plans
          </Sec>
          <div className="mg-v4-rows">
            {v4.plans.map((p) => (
              <RRow key={p.id ?? p.title}>
                <span style={rl}>{p.title}</span>
                <span style={rr}>
                  {p.done} of {p.total}
                </span>
              </RRow>
            ))}
          </div>
        </>
      )}
      {fresh.length > 0 && (
        <>
          <Sec
            link={v4.reviewMinutes ? `${v4.reviewMinutes} min` : undefined}
            onLink={v4.reviewMinutes && review.length > 0 && canReview() ? () => startReview(review[0], ROUTE) : undefined}
          >
            Keep fresh
          </Sec>
          <div className="mg-v4-rows">
            {fresh.map((r) => (
              <RRow key={r.key}>
                <RefreshCw size={15} strokeWidth={1.8} style={{ ...muted, flex: 'none' }} />
                <span style={rl}>{plain(r.label)}</span>
                <span style={rr}>{freshLabel(r, now)}</span>
              </RRow>
            ))}
          </div>
        </>
      )}
    </aside>
  )
}

// ---- first run --------------------------------------------------------------------------------------------------

function Cover({ kind, w }: { kind: Starter['cover']; w: number }): ReactNode {
  const dark = kind === 'code' || kind === '3d'
  return (
    <span
      aria-hidden
      className="relative block shrink-0 overflow-hidden"
      style={{
        width: w,
        aspectRatio: '16 / 9',
        borderRadius: w > 100 ? 8 : 5,
        background: dark ? color.island : fill.chip,
        boxShadow: `inset 0 0 0 1px ${color.hairline}`
      }}
    >
      <svg viewBox="0 0 160 90" className="block h-full w-full">
        {kind === 'code' &&
          [18, 28, 38, 48, 58, 68].map((y, i) => <rect key={y} x={30 + (i % 3) * 8} y={y} width={[60, 80, 50, 90, 40, 70][i]} height={4} rx={2} style={{ fill: 'rgba(255,255,255,.55)' }} />)}
        {kind === 'sheet' && [0, 1, 2, 3, 4].map((r) => [0, 1, 2, 3].map((c) => <rect key={`${r}${c}`} x={18 + c * 32} y={14 + r * 13} width={26} height={2} style={{ fill: color.faint }} />))}
        {kind === 'plot' && <path d="M18 70 L40 62 L58 66 L80 48 L98 52 L120 32 L142 26" fill="none" strokeWidth={2} style={{ stroke: color.label }} />}
        {kind === '3d' && (
          <g>
            <rect x={58} y={30} width={38} height={36} rx={8} style={{ fill: 'rgba(255,255,255,.85)' }} />
            <path d="M96 38 q16 0 16 12 t-16 12" fill="none" strokeWidth={5} style={{ stroke: 'rgba(255,255,255,.85)' }} />
          </g>
        )}
        {kind === 'cad' && <path d="M40 58 L80 44 L124 54 L84 70 Z M40 58 V64 L84 76 V70 M84 76 L124 60 V54" fill="none" strokeWidth={1.6} style={{ stroke: color.label }} />}
      </svg>
    </span>
  )
}

function FirstMain({ wide }: { wide: boolean }): ReactNode {
  // No week yet: nothing passed means no chart at all, never seven flat bars (MIC-69). The starters lead.
  return (
    <>
      <Sec first link="Library" onLink={() => setPage('lessons')}>
        Start with ten minutes
      </Sec>
      <div data-progress-starters>
        {STARTERS.map((s, i) => (
          <button
            key={s.id}
            type="button"
            onClick={() => startGoal(s.goal, ROUTE)}
            className="mg-press grid w-full cursor-pointer items-center text-left"
            style={{
              gridTemplateColumns: wide ? 'minmax(0,1fr) auto 204px 14px' : 'minmax(0,1fr) 14px',
              columnGap: 14,
              minHeight: 50,
              borderTop: i ? hair : undefined
            }}
          >
            <span className="flex min-w-0 items-center gap-[12px]">
              <Cover kind={s.cover} w={54} />
              <b
                className="truncate"
                title={s.title}
                style={{
                  fontWeight: 550,
                  color: color.text,
                  fontSize: type2.md
                }}
              >
                {s.title}
              </b>
            </span>
            {wide && <Tag>{s.grows}</Tag>}
            {wide && (
              <span className="truncate text-right" title={`${s.tool} · ${s.steps} steps · ${s.minutes} min`} style={{ fontSize: 13, color: color.label, ...num }}>
                {s.tool} · {s.steps} steps · {s.minutes} min
              </span>
            )}
            <ChevronRight size={14} strokeWidth={1.8} style={{ color: color.faint }} />
          </button>
        ))}
      </div>
      <Sec link="All plans" onLink={() => setPage('lessons')}>
        Or start a plan
      </Sec>
      <div
        className="grid"
        style={{
          gridTemplateColumns: `repeat(${wide ? 3 : 2}, minmax(0, 1fr))`,
          gap: '20px 16px'
        }}
      >
        {STARTER_PLANS.map((p) => (
          <button key={p.id} type="button" onClick={() => setPage('lessons')} className="mg-press flex min-w-0 cursor-pointer flex-col text-left">
            <span className="block w-full">
              <span className="block w-full" style={{ aspectRatio: '16 / 9' }}>
                <CoverFill kind={p.cover} />
              </span>
            </span>
            <b
              className="truncate"
              title={p.title}
              style={{
                display: 'block',
                fontSize: 14.5,
                fontWeight: 600,
                color: color.text,
                marginTop: 10
              }}
            >
              {p.title}
            </b>
            <span style={{ fontSize: 12.5, color: color.label, marginTop: 2 }}>
              {p.tool} · {p.lessons} lessons · {aboutHr(p.minutes)}
            </span>
            <span style={{ fontSize: 12.5, color: color.label, marginTop: 2 }}>Ends with {p.ends}</span>
          </button>
        ))}
      </div>
    </>
  )
}
/** A cover that fills its box (the plan cards). */
function CoverFill({ kind }: { kind: Starter['cover'] }): ReactNode {
  const ref = useRef<HTMLSpanElement>(null)
  const [w, setW] = useState(200)
  useLayoutEffect(() => {
    const el = ref.current?.parentElement
    if (!el) return
    const ro = new ResizeObserver(() => setW(el.clientWidth))
    ro.observe(el)
    setW(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  return (
    <span ref={ref} className="block">
      <Cover kind={kind} w={w} />
    </span>
  )
}

function FirstRail({ stacked }: { stacked: boolean }): ReactNode {
  return (
    <aside data-progress-rail aria-label="Pick a goal" style={stacked ? { marginTop: 40, paddingTop: 30, borderTop: hair } : { borderLeft: hair, padding: '0 0 48px 32px' }}>
      <div className="flex flex-col items-center text-center" style={{ paddingTop: 2 }}>
        <PokeBon size={112} level={1} />
        <div style={{ fontSize: 12.5, color: color.label, marginTop: 6 }}>Each step you pass grows {NAME ?? 'bon'}</div>
        <div style={{ fontSize: 12.5, color: color.faint, marginTop: 2 }}>
          {LEVELS[1].at} steps to {LEVELS[1].name}
        </div>
      </div>
      <Sec link="Skills" onLink={() => setPage('skills')}>
        Pick a goal
      </Sec>
      <div className="mg-v4-rows">
        {GOAL_PICKS.map((g) => (
          <RRow key={g.title} tall onClick={() => startGoal(g.query, ROUTE)}>
            <span className="min-w-0 flex-1">
              <b className="block truncate" title={g.title} style={{ fontWeight: 520, color: color.text }}>
                {g.title}
              </b>
              <span className="block" style={{ fontSize: 12.5, color: color.label }}>
                {g.skills} skills · about {g.hours} hours
              </span>
            </span>
            <ChevronRight size={14} strokeWidth={1.8} style={{ color: color.faint, flex: 'none' }} />
          </RRow>
        ))}
      </div>
    </aside>
  )
}

/** A table cell's plain text (a string, or a one-level element around one), for its tooltip. */
function cellText(c: ReactNode): string | undefined {
  if (typeof c === 'string' || typeof c === 'number') return String(c)
  const kids = (c as { props?: { children?: unknown } } | null)?.props?.children
  if (typeof kids === 'string' || typeof kids === 'number') return String(kids)
  if (Array.isArray(kids) && kids.every((k) => typeof k === 'string' || typeof k === 'number')) return kids.join('')
  return undefined
}

// ---- the page ---------------------------------------------------------------------------------------------------

/**
 * The mock puts the primary on the title's row. The title is the shell's PageHeader, which takes no `right` from a
 * page yet (Core request to the shell lane), so the button is portaled into this page's own header, as its right slot
 * (the header lays it out: `ml-auto`, centered on the 36 px title row). No header found (another host): it stays inline.
 */
function TitleRight({ children }: { children: ReactNode }): ReactNode {
  const mark = useRef<HTMLSpanElement>(null)
  const [slot, setSlot] = useState<HTMLElement | null>(null)
  useLayoutEffect(() => {
    const head = mark.current?.closest('section')?.querySelector<HTMLElement>('[data-page-header]')
    // Only an empty right side: never next to something the shell put there.
    setSlot(head && !head.querySelector('[data-no-drag]:not([data-progress-primary])') ? head : null)
  }, [])
  return (
    <>
      <span ref={mark} hidden />
      {slot
        ? createPortal(
            <div data-no-drag data-progress-primary className="ml-auto flex shrink-0 items-center">
              {children}
            </div>,
            slot
          )
        : children}
    </>
  )
}

function Main({ data, v4, now, wide }: { data: DashData; v4: V4; now: number; wide: boolean }): ReactNode {
  const minutes = v4.minutesKnown
  const wk = weekNums(v4, now)
  const all = allNums(v4, data.completed.length)
  const masteredWeek = wk.mastered ?? data.tracks.reduce((n, t) => n + t.skills.filter((s) => s.masteredAt && s.masteredAt >= now - 7 * 86_400_000).length, 0)
  const tracks = data.tracks
  const passed = lastPassed(v4)
  const wkBars = weekBars(v4, now)
  const w12 = weeks12(v4, now)
  // Never rows of zeros: the week waits for `activity` (no empty chart that then fills), and the 12 weeks and their
  // numbers show once there is something in them.
  const seen = v4.activitySeen
  // A week with nothing in it is left out, like any part with nothing to show (MIC-69): no chart of flat bars.
  const week = seen && wkBars.some((b) => b.value > 0)
  const any12 = seen && w12.some((b) => b.value > 0)
  return (
    <>
      {week && (
        <>
          <Sec first link={minutes ? 'minutes a day' : 'steps a day'}>
            This week
          </Sec>
          <Bars bars={wkBars} minutes={minutes} weekly={false} height={150} />
        </>
      )}
      {week && (
        <Stats
          items={[
            ...(wk.minutes !== undefined
              ? [
                  {
                    big: <Minutes min={wk.minutes} />,
                    label: 'practiced this week'
                  }
                ]
              : []),
            { big: wk.steps, label: 'steps passed' },
            { big: masteredWeek, label: 'skills mastered' }
          ]}
        />
      )}
      {any12 && (
        <>
          <Sec first={!week} link={minutes ? 'minutes a week' : 'steps a week'}>
            Last 12 weeks
          </Sec>
          <Bars bars={w12} minutes={minutes} weekly height={122} />
          <Stats
            items={[
              ...(all.minutes !== undefined
                ? [
                    {
                      big: <Minutes min={all.minutes} />,
                      label: 'practiced in all'
                    }
                  ]
                : []),
              { big: all.steps, label: 'steps passed' },
              { big: all.lessons, label: 'lessons finished' }
            ]}
          />
        </>
      )}
      {tracks.length > 0 && (
        <>
          <Sec first={!week && !any12} link="Skills" onLink={() => setPage('skills')}>
            Tracks
          </Sec>
          <Table
            label="Tracks"
            cols={wide ? 'minmax(120px,1.1fr) 150px minmax(0,1.6fr) 100px' : 'minmax(100px,1fr) 130px minmax(0,1.2fr)'}
            head={[{ t: 'Track' }, { t: 'Mastered' }, { t: 'Next', wrap: true }, ...(wide ? [{ t: 'Last practiced', right: true }] : [])]}
            rowH={40}
            rows={tracks.map((t) => {
              const next = trackNext(t)
              const last = trackLast(t, passed)
              const done = t.total > 0 && t.mastered >= t.total
              return [
                <b key="t" style={{ fontWeight: 550, color: color.text }}>
                  {t.track}
                </b>,
                <span key="m" className="flex items-center gap-[10px]">
                  <Meter done={t.mastered} total={t.total} green />
                  <span style={{ fontSize: 13, color: color.label, ...num }}>
                    {t.mastered} of {t.total}
                  </span>
                </span>,
                <span
                  key="n"
                  style={{
                    color: done || !t.mastered ? color.label : color.text
                  }}
                >
                  {next}
                </span>,
                ...(wide
                  ? [
                      <span key="l" style={{ color: color.label }}>
                        {last ? dayLabel(last, now) : ''}
                      </span>
                    ]
                  : [])
              ]
            })}
          />
        </>
      )}
      {v4.passes.length > 0 && (
        <>
          <Sec link={`All ${all.steps || v4.passes.length}`}>Recently passed</Sec>
          <Table
            label="Recently passed"
            cols={wide ? 'max-content minmax(0,1.25fr) max-content minmax(0,1fr)' : 'max-content minmax(0,1fr) max-content'}
            head={[{ t: 'When' }, { t: 'Step' }, { t: 'Skill' }, ...(wide ? [{ t: 'Lesson', wrap: true }] : [])]}
            rowH={40}
            rows={v4.passes.slice(0, 8).map((p) => [
              <span key="w" style={muted}>
                {whenLabel(p.at, now)}
              </span>,
              <span key="s" className="flex min-w-0 items-center gap-[10px]">
                <PassCheck />
                <b className="min-w-0" style={{ ...clamp2, fontWeight: 550, color: color.text }}>
                  {p.step}
                </b>
              </span>,
              p.skill ? <Tag key="k">{p.skill}</Tag> : <span key="k" />,
              ...(wide
                ? [
                    <span key="l" style={muted}>
                      {p.lesson ?? ''}
                    </span>
                  ]
                : [])
            ])}
          />
        </>
      )}
    </>
  )
}

export function ProgressV4(): ReactNode {
  const data = useDash((s) => s.data)
  const v4 = useV4((s) => s.v4)
  const items = useLibrary((s) => s.items)
  const starting = useDash((s) => s.starting)
  const connected = useLesson((s) => s.connected)
  const hello = useLesson((s) => s.hello)
  // A lesson open right now is the one to continue, as on Home's continue card (QA R2-07).
  const live = useLesson((s) => (s.lesson?.title && !s.building ? s.lesson.title : undefined))
  const now = useNow()
  const [ref, w] = useWidth<HTMLDivElement>()
  useEffect(() => {
    void requestDashboard()
    requestV4()
  }, [connected, hello])

  const mastered = data?.tracks.reduce((n, t) => n + t.mastered, 0) ?? 0
  const total = data?.tracks.reduce((n, t) => n + t.total, 0) ?? 0
  const anyActivity = !!data && (mastered > 0 || data.completed.length > 0 || v4.passes.length > 0 || [...v4.days.values()].some((d) => d.steps > 0 || (d.minutes ?? 0) > 0))
  const first = !anyActivity
  const cont = continueList(data, items)[0]
  const two = w >= TWO_COL
  const mainWide = two ? w - RAIL_W - 40 >= 600 : w >= 600

  const primary = live ? (
    <PrimaryButton label={`Continue ${live}`} icon={Play} onClick={() => void closeWindow(ROUTE)} />
  ) : cont ? (
    <PrimaryButton label={`Continue ${cont.title}`} icon={Play} disabled={!!starting} onClick={() => void startSaved(cont.libraryId, ROUTE)} />
  ) : (
    <PrimaryButton label="Start a lesson" icon={first ? SquarePen : Compass} onClick={() => openLauncher()} />
  )
  const lede = first ? (live || cont ? 'Pick up where you left off.' : 'Nothing passed yet. Your first step grows bon.') : total ? `${mastered} of ${total} skills mastered.` : ''

  return (
    <Scroller>
      <PageColumn wide top={0} data={{ 'data-progress-v4': first ? 'first' : 'full' }}>
        <div ref={ref} className="w-full">
          {/* The lede right under the shell's title; the one primary on the title's row, as in the mock (TitleRight). */}
          <div className="flex items-center gap-[16px]" style={{ marginBottom: 26, minHeight: 20 }}>
            <p className="m-0 min-w-0 flex-1 truncate" title={lede} style={{ fontSize: 14.5, lineHeight: '20px', color: color.label }}>
              {lede}
            </p>
            <TitleRight>{primary}</TitleRight>
          </div>
          <div
            className={two ? 'grid items-start' : 'flex flex-col'}
            style={
              two
                ? {
                    gridTemplateColumns: `minmax(0, 1fr) ${RAIL_W}px`,
                    columnGap: 40
                  }
                : undefined
            }
          >
            <div data-progress-main className="min-w-0">
              {first || !data ? <FirstMain wide={mainWide} /> : <Main data={data} v4={v4} now={now} wide={mainWide} />}
            </div>
            {first ? <FirstRail stacked={!two} /> : <Rail data={data} v4={v4} now={now} stacked={!two} />}
          </div>
        </div>
      </PageColumn>
      <style>{'.mg-v4-rows > * + * { box-shadow: 0 -1px 0 ' + color.hairline + '; }'}</style>
    </Scroller>
  )
}
