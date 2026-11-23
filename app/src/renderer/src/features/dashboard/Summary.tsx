/**
 * Feature: dashboard. The top of the Progress page: four counts and the last twelve weeks as a quiet grid, so the page
 * opens on how you are doing before the lists. Only what the engine sent: a count it does not track is left out, and
 * with no activity the grid says how it starts instead of drawing empty squares. Ink on the track (no hue: none of this
 * is a status), never a streak.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../core/theme'
import { enter, staggerDelay } from '../../core/ui/motion'
import { CARD } from '../shell/ui'
import { totals, weekGrid, type DayCell } from './model'
import type { DashData, ReviewEntry } from './types'

const SQ = 14

function Tile({ n, of, label }: { n: number; of?: number; label: string }): ReactNode {
  return (
    <div data-prog-tile className="flex min-w-0 flex-col" style={{ ...CARD, padding: '16px 18px', gap: 4 }}>
      <span className="font-semibold" style={{ fontSize: type2.xxl, lineHeight: '32px', letterSpacing: '-0.4px', color: color.text, fontVariantNumeric: 'tabular-nums' }}>
        {n}
        {of !== undefined && (
          <span className="font-normal" style={{ fontSize: type2.lg, color: color.faint }}>
            {' '}
            / {of}
          </span>
        )}
      </span>
      <span className="truncate" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
        {label}
      </span>
    </div>
  )
}

/** Five levels of ink: the day's steps against the best day shown. A quiet day is the track, not a gap in a streak. */
const level = (c: DayCell, max: number): number => (c.state === 'future' ? 0 : c.reps <= 0 ? 0 : Math.max(0.3, Math.min(1, c.reps / max)))

function Grid({ weeks }: { weeks: DayCell[][] }): ReactNode {
  const max = Math.max(...weeks.flat().map((d) => d.reps), 1)
  return (
    <div role="img" aria-label="Steps passed each day over the last 12 weeks" className="flex" style={{ gap: 4 }}>
      {weeks.map((w, wi) => (
        <div key={wi} className="flex flex-col" style={{ gap: 4 }}>
          {w.map((d) => (
            <motion.span
              key={d.date}
              title={d.state === 'future' ? undefined : `${d.date}: ${d.reps} ${d.reps === 1 ? 'step' : 'steps'}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={enter(staggerDelay(wi) / 2)}
              className="block"
              style={{ width: SQ, height: SQ, borderRadius: radius2.keycap, background: d.state === 'future' ? 'transparent' : fill.track, position: 'relative', outline: d.today ? `1.5px solid ${color.text}` : undefined, outlineOffset: 1 }}
            >
              {level(d, max) > 0 && <span aria-hidden className="absolute inset-0" style={{ borderRadius: 'inherit', background: color.text, opacity: level(d, max) }} />}
            </motion.span>
          ))}
        </div>
      ))}
    </div>
  )
}

export function ProgressSummary({ data, now, goal, due }: { data?: DashData; now: number; goal: number; due: ReviewEntry[] }): ReactNode {
  const t = totals(data, now)
  const skills = (data?.tracks ?? []).flatMap((x) => x.skills)
  const mastered = skills.filter((s) => s.state === 'mastered').length
  const active = !!data?.activity && data.activity.some((d) => d.reps > 0)
  return (
    <section aria-label="At a glance" data-prog-summary className="flex flex-col" style={{ gap: 16 }}>
      <div className="grid grid-cols-2 gap-[12px] @min-[720px]:grid-cols-4">
        {data?.activity && <Tile n={t.week} label="Steps this week" />}
        <Tile n={data?.completed.length ?? 0} label="Lessons finished" />
        <Tile n={mastered} of={skills.length || undefined} label="Skills mastered" />
        <Tile n={due.length} label="Due for review" />
      </div>
      <div className="flex flex-col" style={{ ...CARD, padding: '16px 18px', gap: 12 }}>
        <span className="font-semibold" style={{ fontSize: type2.sm, color: color.label }}>
          Last 12 weeks
        </span>
        {active ? <Grid weeks={weekGrid(data!.activity, now, goal, 12)} /> : (
          <span style={{ fontSize: type2.sm, color: color.label }}>Every step you pass shows up here, one square a day.</span>
        )}
      </div>
    </section>
  )
}
