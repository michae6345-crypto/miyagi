/**
 * The lesson-complete panel, direction A "Summary": one narrow column grown out of the notch island.
 *   header   the track and how many of its skills were mastered (built from skillMap; the card's own title only
 *            when there's no map, since that title already carries the count)
 *   result   the lesson's training curve as one line of numbers, first value to last, with a small sparkline
 *            (the network diagrams' frames, else the last real run's metric events)
 *   skills   what the lesson covered, two columns of names: mastered = a dot, learning (typed by Do it for me) = a
 *            hollow ring and quieter text. Click one for its detail, inline.
 *   footer   "Next <title>" with the one primary button; End lesson is a quiet text button
 * Every number comes from the engine; a piece without data is left out.
 */
import { motion } from 'motion/react'
import { useMemo, useState, type ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { CloseButton, CodeText, PrimaryButton, Spinner } from '../../core/ui/atoms'
import { color, fill } from '../../core/theme'
import { useOverlayWidth } from '../cards/store'
import { lossSeries, short } from './net'
import { endLesson, startLesson, useComplete, type CompleteCard } from './store'
import type { SkillMap, SkillNode } from './types'

const W = 580
const PAD_X = 32

/** The panel's width on an overlay this wide (the island keeps 16 px from each edge). One column, map or not. */
export function panelWidth(overlay: number, _hasMap: boolean): number {
  return Math.min(W, overlay - 32)
}

/** Small values stay readable as decimals ("0.00078"); only the very small fall back to short()'s exponent. */
function num(v: number): string {
  const a = Math.abs(v)
  if (a >= 0.001 || a === 0) return short(v)
  if (a >= 1e-5) return v.toPrecision(2)
  return short(v)
}

const sentence = (s: string): string => (/^[a-z][a-z ]*$/.test(s) ? s[0].toUpperCase() + s.slice(1) : s)

type Curve = { label: string; xs: number[]; ys: number[] }

/** The training curve: the lesson's trained network (loss per epoch), else the last real run's first metric. */
function useCurve(): Curve | undefined {
  const trained = useComplete((s) => s.trained)
  const metric = useComplete((s) => s.curve)
  return useMemo(() => {
    const pts = lossSeries(trained)
    if (pts) {
      const span = pts[pts.length - 1].epoch - pts[0].epoch
      return { label: `Loss over ${span.toLocaleString('en-US')} epochs`, xs: pts.map((p) => p.epoch), ys: pts.map((p) => p.loss) }
    }
    if (metric && metric.pts.length >= 2) return { label: sentence(metric.name), xs: metric.pts.map((p) => p.step), ys: metric.pts.map((p) => p.value) }
    return undefined
  }, [trained, metric])
}

/** A tiny monochrome line of the curve (log scale when every value is positive): first point faint, last point bright, like the numbers. */
function Sparkline({ xs, ys, w = 148, h = 40 }: { xs: number[]; ys: number[]; w?: number; h?: number }): ReactNode {
  const d = useMemo(() => {
    const log = ys.every((y) => y > 0)
    const v = ys.map((y) => (log ? Math.log10(y) : y))
    const step = Math.max(1, Math.floor(xs.length / 120))
    const idx = xs.map((_, i) => i).filter((i) => i % step === 0 || i === xs.length - 1)
    const x0 = xs[0]
    const x1 = xs[xs.length - 1]
    const lo = Math.min(...v)
    const hi = Math.max(...v)
    const pad = 3
    const X = (x: number): number => pad + ((w - 2 * pad) * (x - x0)) / Math.max(1e-9, x1 - x0)
    const Y = (y: number): number => pad + ((h - 2 * pad) * (hi - y)) / Math.max(1e-9, hi - lo)
    const pts = idx.map((i) => [X(xs[i]), Y(v[i])] as const)
    return { path: pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' '), start: pts[0], end: pts[pts.length - 1] }
  }, [xs, ys, w, h])
  return (
    <svg width={w} height={h} className="block shrink-0" data-complete-spark aria-hidden>
      <motion.path
        d={d.path}
        fill="none"
        stroke={color.label}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.7, ease: 'easeOut', delay: 0.15 }}
      />
      <circle cx={d.start[0]} cy={d.start[1]} r={2} fill={color.faint} />
      <motion.circle cx={d.end[0]} cy={d.end[1]} r={2.5} fill={color.text} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8, duration: 0.2 }} />
    </svg>
  )
}

function Header({ card }: { card: CompleteCard }): ReactNode {
  const map = card.map
  const mastered = map?.nodes.filter((n) => n.state === 'mastered').length ?? 0
  const learning = map?.nodes.filter((n) => n.state === 'learning').length ?? 0
  // The card's title already says "<track> · N skills mastered": use it only when there's no track to build from.
  const title = map?.track || card.title
  const sub = map?.track
    ? mastered
      ? learning
        ? `${mastered} of ${mastered + learning} skills mastered`
        : `${mastered} skill${mastered === 1 ? '' : 's'} mastered`
      : ''
    : map
      ? ''
      : card.body
  return (
    <div className="pr-[40px]" data-complete-head>
      <div className="text-[20px] font-semibold leading-[26px] tracking-[-0.015em]" style={{ color: color.text }}>
        {title}
      </div>
      {sub && (
        <div className="mt-[2px] text-[15px] leading-[20px] tabular-nums" style={{ color: color.label }}>
          {sub}
        </div>
      )}
    </div>
  )
}

function Result(): ReactNode {
  const curve = useCurve()
  if (!curve) return null
  const first = curve.ys[0]
  const last = curve.ys[curve.ys.length - 1]
  return (
    <div className="mt-[32px] flex items-end justify-between gap-[24px]" data-complete-result>
      <div className="min-w-0">
        <div className="flex items-center gap-[12px] text-[28px] font-semibold leading-[34px] tracking-[-0.02em] tabular-nums">
          <span style={{ color: color.label }}>{num(first)}</span>
          <ArrowRight size={20} strokeWidth={1.8} style={{ color: color.faint }} className="shrink-0" />
          <span style={{ color: color.text }}>{num(last)}</span>
        </div>
        <div className="mt-[6px] text-[13px] leading-[18px] tabular-nums" style={{ color: color.faint }}>
          {curve.label}
        </div>
      </div>
      <Sparkline xs={curve.xs} ys={curve.ys} />
    </div>
  )
}

function Skill({ n, open, onToggle }: { n: SkillNode; open: boolean; onToggle: () => void }): ReactNode {
  const learning = n.state === 'learning'
  return (
    <li>
      <button
        type="button"
        data-skill={n.id}
        data-state={n.state}
        aria-expanded={n.detail ? open : undefined}
        className={`group flex w-full items-start gap-[12px] py-[5px] text-left ${n.detail ? 'cursor-pointer' : 'cursor-default'}`}
        onMouseDown={(e) => e.preventDefault()}
        onClick={n.detail ? onToggle : undefined}
      >
        <span className="grid h-[22px] w-[5px] shrink-0 place-items-center">
          <span
            className="block h-[5px] w-[5px] rounded-full"
            style={learning ? { boxShadow: `inset 0 0 0 1.2px ${color.faint}` } : { background: open ? color.text : color.faint }}
          />
        </span>
        <span className="min-w-0">
          <span
            className={`block text-[15px] leading-[22px] transition-opacity duration-150 group-hover:opacity-100 ${open ? 'opacity-100' : 'opacity-[.88]'}`}
            style={{ color: learning && !open ? color.label : color.text }}
          >
            {n.label}
          </span>
          {open && n.detail && (
            <motion.span
              className="block pb-[4px] text-[13px] leading-[18px]"
              style={{ color: color.faint }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.18 }}
            >
              <CodeText text={n.detail} />
            </motion.span>
          )}
        </span>
      </button>
    </li>
  )
}

/** What the lesson covered (mastered and learning; what's next is the footer's job), in two columns that flow on their own. */
function Skills({ map }: { map: SkillMap }): ReactNode {
  const [open, setOpen] = useState<string>()
  const skills = map.nodes.filter((n) => n.state !== 'next')
  if (!skills.length) return null
  const half = Math.ceil(skills.length / 2)
  const cols = [skills.slice(0, half), skills.slice(half)]
  return (
    <div className="mt-[28px] grid grid-cols-2 gap-x-[28px]" data-complete-skills>
      {cols.map((col, i) => (
        <ul key={i} className="flex min-w-0 flex-col">
          {col.map((n) => (
            <Skill key={n.id} n={n} open={open === n.id} onToggle={() => setOpen((o) => (o === n.id ? undefined : n.id))} />
          ))}
        </ul>
      ))}
    </div>
  )
}

function Footer({ card }: { card: CompleteCard }): ReactNode {
  const ending = useComplete((s) => s.ending)
  const next = card.map?.next[0]
  const endLabel = card.endLabel || 'End lesson'
  return (
    <div className="mt-[28px] flex items-center gap-[20px] border-t pt-[20px]" style={{ borderColor: fill.rule }} data-up-next>
      {next ? (
        <div className="min-w-0 flex-1 truncate text-[15px] leading-[20px]" title={next.goal}>
          <span style={{ color: color.faint }}>Next</span>
          <span className="ml-[10px] font-medium" style={{ color: color.text }}>
            {next.title}
          </span>
        </div>
      ) : (
        <span className="flex-1" />
      )}
      {next ? (
        <>
          <button
            type="button"
            data-complete-end
            className="flex h-[30px] shrink-0 cursor-pointer items-center gap-[6px] text-[13px] font-medium opacity-60 transition-opacity duration-150 hover:opacity-100"
            style={{ color: color.text }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={endLesson}
          >
            {ending && <Spinner size={12} c={color.text} />}
            {endLabel}
          </button>
          <span data-complete-primary>
            <PrimaryButton label="Start" onClick={() => startLesson(next.goal)} />
          </span>
        </>
      ) : (
        <span data-complete-end>
          <PrimaryButton label={endLabel} onClick={endLesson} disabled={ending} />
        </span>
      )}
    </div>
  )
}

export function CompletePanel(): ReactNode {
  const card = useComplete((s) => s.card)
  const overlay = useOverlayWidth((s) => s.w)
  if (!card) return null
  return (
    <div data-complete="panel" className="relative" style={{ width: panelWidth(overlay, !!card.map), padding: `28px ${PAD_X}px 24px` }}>
      <div className="absolute right-[32px] top-[30px]">
        <CloseButton />
      </div>
      <Header card={card} />
      <Result />
      {card.map && <Skills map={card.map} />}
      <Footer card={card} />
    </div>
  )
}
