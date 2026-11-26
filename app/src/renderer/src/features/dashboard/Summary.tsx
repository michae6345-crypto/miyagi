/**
 * Feature: dashboard. The top of the Progress page: four counts, the last twelve weeks as a heatmap, the seven days of
 * this week as a strip, and the milestones as a list. Every block draws even with no activity (muted cells, a stub per
 * day, the milestones still to reach), so the page never opens on an empty screen. Only what the engine sent is
 * counted: nothing is invented. Ink on the track (no hue: none of this is a status), never a streak.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../core/theme'
import { enter, staggerDelay } from '../../core/ui/motion'
import { Tile as Rising } from '../library/motion'
import { CARD, SectionHead } from '../shell/ui'
import { shortDay, totals, weekGrid, weekStrip, type DayCell, type Milestone } from './model'
import type { DashData, ReviewEntry } from './types'

const LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

function Stat({ n, of, label }: { n: number; of?: number; label: string }): ReactNode {
  return (
    <div data-prog-tile className="flex h-full min-w-0 flex-col" style={{ ...CARD, padding: '16px 18px', gap: 4 }}>
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

/** The four counts. */
export function ProgressTiles({ data, now, due }: { data?: DashData; now: number; due: ReviewEntry[] }): ReactNode {
  const t = totals(data, now)
  const skills = (data?.tracks ?? []).flatMap((x) => x.skills)
  const mastered = skills.filter((s) => s.state === 'mastered').length
  return (
    <section aria-label="At a glance" data-prog-summary className="grid grid-cols-2 gap-[12px] @min-[760px]:grid-cols-4">
      <Rising i={0}>
        <Stat n={t.week} label="Steps this week" />
      </Rising>
      <Rising i={1}>
        <Stat n={data?.completed.length ?? 0} label="Lessons finished" />
      </Rising>
      <Rising i={2}>
        <Stat n={mastered} of={skills.length || undefined} label="Skills mastered" />
      </Rising>
      <Rising i={3}>
        <Stat n={due.length} label="Due for review" />
      </Rising>
    </section>
  )
}

/** Levels of ink: the day's steps against the best day shown. A quiet day is the track, not a gap in a streak. */
const level = (c: DayCell, max: number): number => (c.state === 'future' || c.reps <= 0 ? 0 : Math.max(0.3, Math.min(1, c.reps / max)))

/** 12 columns (weeks, oldest first) of 7 squares (Monday first). The squares stretch with the card. */
function Heatmap({ weeks }: { weeks: DayCell[][] }): ReactNode {
  const max = Math.max(...weeks.flat().map((d) => d.reps), 1)
  return (
    <div role="img" aria-label="Steps passed each day over the last 12 weeks" className="grid" style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))`, gap: 5 }}>
      {weeks.map((w, wi) => (
        <div key={wi} className="flex flex-col" style={{ gap: 5 }}>
          {w.map((d) => (
            <motion.span
              key={d.date}
              title={d.state === 'future' ? undefined : `${shortDay(Date.parse(d.date))}: ${d.reps} ${d.reps === 1 ? 'step' : 'steps'}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={enter(staggerDelay(wi) / 2)}
              className="relative block w-full"
              style={{ aspectRatio: '1 / 1', maxHeight: 22, borderRadius: radius2.keycap, background: d.state === 'future' ? 'transparent' : fill.track, boxShadow: d.state === 'future' ? `inset 0 0 0 1px ${fill.hairline}` : undefined, outline: d.today ? `1.5px solid ${color.text}` : undefined, outlineOffset: 1 }}
            >
              {level(d, max) > 0 && <span aria-hidden className="absolute inset-0" style={{ borderRadius: 'inherit', background: color.text, opacity: level(d, max) }} />}
            </motion.span>
          ))}
        </div>
      ))}
    </div>
  )
}

export function HeatmapCard({ data, now, goal }: { data?: DashData; now: number; goal: number }): ReactNode {
  const weeks = weekGrid(data?.activity ?? null, now, goal, 12)
  const active = !!data?.activity?.some((d) => d.reps > 0)
  return (
    <section aria-labelledby="prog-12" data-prog-heatmap className="flex h-full flex-col" style={{ ...CARD, padding: 20, gap: 16 }}>
      <SectionHead id="prog-12">Last 12 weeks</SectionHead>
      <Heatmap weeks={weeks} />
      <span style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label, marginTop: 'auto' }}>{active ? 'Darker means more steps that day.' : 'Every step you pass fills a square.'}</span>
    </section>
  )
}

/** This week, Monday first: a bar per day against the busiest day, the day's letter under it. */
export function WeekStripCard({ data, now, goal }: { data?: DashData; now: number; goal: number }): ReactNode {
  const days = weekStrip(data?.activity ?? null, now, goal)
  const max = Math.max(...days.map((d) => d.reps), 1)
  const steps = days.reduce((n, d) => n + d.reps, 0)
  return (
    <section aria-labelledby="prog-7" data-prog-week-strip className="flex h-full flex-col" style={{ ...CARD, padding: 20, gap: 16 }}>
      <SectionHead id="prog-7">This week</SectionHead>
      <ol aria-label="Steps passed each day this week" className="m-0 flex list-none items-end justify-between p-0" style={{ gap: 8, height: 76 }}>
        {days.map((d, i) => (
          <li key={d.date} aria-label={`${DAY_NAMES[i]}: ${d.reps} ${d.reps === 1 ? 'step' : 'steps'}${d.today ? ', today' : ''}`} className="flex flex-1 flex-col items-center justify-end" style={{ gap: 6 }}>
            <motion.span
              aria-hidden
              initial={{ opacity: 0, scaleY: 0.2 }}
              animate={{ opacity: 1, scaleY: 1 }}
              transition={enter(staggerDelay(i))}
              className="block w-full"
              style={{ height: d.state === 'future' ? 4 : Math.max(4, Math.round((d.reps / max) * 52)), maxWidth: 32, transformOrigin: 'bottom', borderRadius: radius2.keycap, background: d.reps > 0 ? color.text : d.state === 'future' ? fill.hairline : fill.track }}
            />
            <span aria-hidden style={{ fontSize: type2.micro, lineHeight: '12px', color: d.today ? color.text : color.faint, fontWeight: d.today ? 600 : 400 }}>
              {LETTERS[i]}
            </span>
          </li>
        ))}
      </ol>
      <span style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label, marginTop: 'auto' }}>
        {steps > 0 ? `${steps} ${steps === 1 ? 'step' : 'steps'} passed. Goal: ${goal} a day.` : `Goal: ${goal} steps a day.`}
      </span>
    </section>
  )
}

/** Every milestone, reached ones in ink with their date, the rest hollow with how far to go. */
export function MilestoneCard({ list }: { list: Milestone[] }): ReactNode {
  if (!list.length) return null
  const nextId = list.find((m) => !m.done)?.id
  return (
    <section aria-labelledby="prog-ms" data-milestones className="flex flex-col" style={{ ...CARD, padding: 20, gap: 4 }}>
      <SectionHead id="prog-ms">Milestones</SectionHead>
      <ul className="m-0 flex list-none flex-col p-0">
        {list.map((m, i) => (
          <li key={m.id} data-milestone={m.done ? m.id : undefined} data-milestone-next={m.id === nextId ? m.id : undefined} className="flex items-center gap-[12px]" style={{ minHeight: 36, borderTop: i ? `1px solid ${fill.hairline}` : undefined }}>
            <span aria-hidden className="block shrink-0" style={{ width: 8, height: 8, borderRadius: radius2.round, background: m.done ? color.text : 'transparent', boxShadow: m.done ? undefined : `inset 0 0 0 1px ${fill.ring}` }} />
            <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.sm, color: m.done ? color.text : color.label }}>
              {m.label}
            </span>
            <span className="shrink-0" style={{ fontSize: type2.xs, color: color.faint, fontVariantNumeric: 'tabular-nums' }}>
              {m.done ? (m.at ? shortDay(m.at) : 'Reached') : (m.toGo ?? 'Not yet')}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
