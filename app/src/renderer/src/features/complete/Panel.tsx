/**
 * The lesson-complete panel, direction B "Path", grown out of the notch island:
 *   header   the track's name, small, over "N skills mastered" (counted from the skill map; the card's own title,
 *            which already carries that count, is only used when there's no map)
 *   path     the track as one line of dots (Path.tsx); click a dot for its detail
 *   bottom   two or three stats in large tabular figures (loss first → last from the lesson's network frames, steps
 *            done, minutes, else checks passed) and, on the right, the one next action: "Start: <next lesson>",
 *            with a quiet "End lesson" beside it
 * Every number comes from the engine's card, its diagrams or the checks it sent; a piece without data is left out.
 */
import { motion } from 'motion/react'
import { useMemo, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useLesson } from '../../core/lesson'
import { CloseButton, Spinner } from '../../core/ui/atoms'
import { color, fill } from '../../core/theme'
import { useOverlayWidth } from '../cards/store'
import { PathView } from './Path'
import { endLesson, startLesson, useComplete } from './store'

const PAD_X = 40
/** Without a skill map: just the header, the stats and the buttons. */
const PLAIN_W = 520
/** Narrower than this, the buttons go under the stats. */
const ONE_ROW = 900

/** The panel's width on an overlay this wide (the island keeps 16 px from each edge). */
export function panelWidth(overlay: number, hasMap: boolean): number {
  if (!hasMap) return Math.min(PLAIN_W, overlay - 32)
  return Math.max(560, Math.min(1260, overlay - 32))
}

/** A loss for a big figure: plain decimals ("0.82", "0.00078"), exponent only when tiny. */
function plain(v: number): string {
  const a = Math.abs(v)
  if (a === 0) return '0'
  if (a >= 100) return Math.round(v).toLocaleString('en-US')
  if (a >= 1) return v.toFixed(2).replace(/\.?0+$/, '')
  if (a >= 1e-4) return v.toPrecision(2).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
  return v.toExponential(1)
}

type Stat = { id: string; label: string; value: ReactNode }

const Sub = ({ children }: { children: ReactNode }): ReactNode => (
  <span className="text-[20px] font-normal tracking-normal" style={{ color: color.faint }}>
    {children}
  </span>
)

/** Loss, steps, minutes; checks passed fills in when one of those isn't known. At most three, all real. */
function useStats(): Stat[] {
  const l = useLesson(useShallow((s) => ({ total: s.steps.length, passed: s.passed, skipped: s.skipped })))
  const startedAt = useComplete((s) => s.startedAt)
  const card = useComplete((s) => s.card) // re-read the minutes when the card comes
  const net = useComplete((s) => s.net)
  const trained = useComplete((s) => s.trained)
  const checks = useComplete((s) => Object.keys(s.checks).length)
  return useMemo(() => {
    const out: Stat[] = []
    const frames = (trained ?? net)?.frames ?? []
    const losses = frames.map((f) => f.loss).filter((v): v is number => v !== undefined && Number.isFinite(v))
    if (losses.length) {
      const a = losses[0]
      const b = losses[losses.length - 1]
      out.push({
        id: 'loss',
        label: 'Loss',
        value: (
          <>
            {losses.length > 1 && a !== b && <Sub>{`${plain(a)} → `}</Sub>}
            {plain(b)}
          </>
        )
      })
    }
    if (l.total) {
      const done = Math.min(l.passed.filter((id) => !l.skipped.includes(id)).length, l.total)
      out.push({
        id: 'steps',
        label: 'Steps',
        value: (
          <>
            {done}
            <Sub>{` of ${l.total}`}</Sub>
          </>
        )
      })
    }
    const mins = startedAt ? Math.round((Date.now() - startedAt) / 60000) : 0
    if (mins >= 1)
      out.push({
        id: 'time',
        label: 'Time',
        value: (
          <>
            {mins}
            <Sub> min</Sub>
          </>
        )
      })
    if (out.length < 3 && checks > 0) out.push({ id: 'checks', label: 'Checks passed', value: checks })
    return out.slice(0, 3)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [l, startedAt, card, net, trained, checks])
}

function Header(): ReactNode {
  const card = useComplete((s) => s.card)!
  const map = card.map
  const mastered = map ? map.nodes.filter((n) => n.state === 'mastered').length : 0
  const title = map && mastered ? `${mastered} skill${mastered === 1 ? '' : 's'} mastered` : (map?.track || card.title)
  const over = map && mastered && map.track ? map.track : ''
  return (
    <div className="flex items-start gap-[16px]">
      <div className="min-w-0 flex-1">
        {over && (
          <div className="text-[13px] leading-[18px]" style={{ color: color.label }}>
            {over}
          </div>
        )}
        <div className="mt-[2px] text-[28px] font-semibold leading-[34px] tracking-[-0.02em]" style={{ color: color.text }} data-complete-head>
          {title}
        </div>
        {!map && card.body && (
          <div className="mt-[6px] text-[15px] leading-[21px]" style={{ color: color.label }}>
            {card.body}
          </div>
        )}
      </div>
      <CloseButton />
    </div>
  )
}

function Stats({ stats }: { stats: Stat[] }): ReactNode {
  if (!stats.length) return null
  return (
    <div className="flex min-w-0 gap-[56px]" data-complete-stats>
      {stats.map((s) => (
        <div key={s.id} className="min-w-0" data-stat={s.id}>
          <div className="text-[13px] leading-[18px]" style={{ color: color.label }}>
            {s.label}
          </div>
          <div className="mt-[4px] whitespace-nowrap text-[28px] font-medium leading-[34px] tracking-[-0.02em] tabular-nums" style={{ color: color.text }}>
            {s.value}
          </div>
        </div>
      ))}
    </div>
  )
}

function Actions(): ReactNode {
  const card = useComplete((s) => s.card)!
  const ending = useComplete((s) => s.ending)
  const next = card.map?.next[0]
  const endLabel = card.endLabel || 'End lesson'
  const primary = 'flex h-[40px] min-w-0 max-w-[440px] cursor-pointer items-center gap-[8px] rounded-full px-[20px] text-[14px] font-medium'
  return (
    <div className="flex min-w-0 shrink-0 items-center gap-[8px]">
      {next ? (
        <motion.button
          type="button"
          data-complete-end
          className="flex h-[40px] shrink-0 cursor-pointer items-center gap-[8px] rounded-full px-[14px] text-[14px] font-medium"
          style={{ color: color.label }}
          whileHover={{ color: color.text }}
          transition={{ duration: 0.12 }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={endLesson}
        >
          {ending && <Spinner size={13} c={color.label} />}
          {endLabel}
        </motion.button>
      ) : null}
      <motion.button
        type="button"
        data-complete-primary
        className={primary}
        style={{ background: color.accent, color: color.onAccent }}
        whileHover={{ filter: 'brightness(0.94)' }}
        whileTap={{ scale: 0.98 }}
        transition={{ duration: 0.12 }}
        onMouseDown={(e) => e.preventDefault()}
        onClick={next ? () => startLesson(next.goal) : endLesson}
        title={next ? next.goal : undefined}
      >
        {!next && ending && <Spinner size={13} c={color.onAccent} track={fill.onAccentKey} />}
        <span className="truncate">{next ? `Start: ${next.title}` : endLabel}</span>
      </motion.button>
    </div>
  )
}

export function CompletePanel(): ReactNode {
  const card = useComplete((s) => s.card)
  const overlay = useOverlayWidth((s) => s.w)
  const stats = useStats()
  if (!card) return null
  const map = card.map
  const w = panelWidth(overlay, !!map)
  const inner = w - 2 * PAD_X
  const row = w >= ONE_ROW

  return (
    <div data-complete="panel" style={{ width: w, padding: `28px ${PAD_X}px 32px` }}>
      <Header />
      {map && (
        <div className="mt-[44px]">
          <PathView map={map} width={inner} />
        </div>
      )}
      <div className={`mt-[36px] flex ${row ? 'items-end justify-between gap-[32px]' : 'flex-col items-stretch gap-[24px]'}`}>
        <Stats stats={stats} />
        <div className={row ? '' : 'flex justify-end'}>
          <Actions />
        </div>
      </div>
    </div>
  )
}
