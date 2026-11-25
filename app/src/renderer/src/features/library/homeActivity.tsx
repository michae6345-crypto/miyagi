/**
 * Feature: library. Home's activity timeline: what you did lately, newest first, as a vertical line of dots. Only what
 * the engine sent: a day with passed steps (from the activity grid) and a lesson you finished (the finished list).
 * With nothing yet the card still stands, with the three kinds of entry as quiet placeholders and one line that says
 * how it starts, so the column never ends in empty space. Neutral ink on the track: nothing here is a status.
 */
import type { ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../core/theme'
import { dayKey, relDay } from '../dashboard/model'
import type { DashData } from '../dashboard/types'
import { CARD } from '../shell/ui'
import { SectionLabel } from './layout'
import { Lift } from './motion'

type Entry = { id: string; at: number; title: string; meta: string }

const plural = (n: number, one: string, many: string): string => `${n} ${n === 1 ? one : many}`

/** The newest entries first: finished lessons and days with steps, merged by time. */
export function activityEntries(data: DashData | undefined, now: number, limit = 5): Entry[] {
  const out: Entry[] = []
  for (const d of data?.completed ?? []) if (d.finishedAt) out.push({ id: `l-${d.lessonId}`, at: d.finishedAt, title: d.title, meta: 'Lesson finished' })
  const todayKey = dayKey(now)
  for (const a of data?.activity ?? []) {
    if (a.reps <= 0) continue
    const at = Date.parse(`${a.date}T12:00:00`)
    if (Number.isNaN(at)) continue
    out.push({ id: `d-${a.date}`, at: a.date === todayKey ? now : at, title: plural(a.reps, 'step passed', 'steps passed'), meta: a.assisted ? `${a.assisted} with help` : 'On your own' })
  }
  return out.sort((x, y) => y.at - x.at).slice(0, limit)
}

/** What the card shows before there is anything: the kinds of entry it will hold. */
const HINTS = ['A step you pass', 'A lesson you finish', 'A skill you master'] as const

export function ActivityCard({ data, now }: { data?: DashData; now: number }): ReactNode {
  const rows = activityEntries(data, now)
  return (
    <section aria-labelledby="home-activity" data-home-activity>
      <SectionLabel id="home-activity">Activity</SectionLabel>
      <Lift>
        <ol className="m-0 flex list-none flex-col p-0" style={{ ...CARD, padding: '8px 20px' }}>
          {rows.length > 0
            ? rows.map((e, i) => (
                <li key={e.id} className="relative flex items-center gap-[14px]" style={{ minHeight: 56 }}>
                  <Rail first={i === 0} last={i === rows.length - 1} />
                  <span className="flex min-w-0 flex-1 flex-col" style={{ gap: 2 }}>
                    <span className="truncate" style={{ fontSize: type2.md, color: color.text }}>
                      {e.title}
                    </span>
                    <span className="truncate" style={{ fontSize: type2.xs, color: color.label }}>
                      {e.meta}
                    </span>
                  </span>
                  <span className="shrink-0" style={{ fontSize: type2.xs, color: color.faint, fontVariantNumeric: 'tabular-nums' }}>
                    {relDay(e.at, now)}
                  </span>
                </li>
              ))
            : HINTS.map((h, i) => (
                <li key={h} className="relative flex items-center gap-[14px]" style={{ minHeight: 56, opacity: 1 - i * 0.2 }}>
                  <Rail first={i === 0} last={i === HINTS.length - 1} hollow />
                  <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.md, color: color.label }}>
                    {h}
                  </span>
                  <span aria-hidden className="shrink-0" style={{ width: 40, height: 8, borderRadius: radius2.round, background: fill.track }} />
                </li>
              ))}
        </ol>
      </Lift>
    </section>
  )
}

/** The timeline's line and dot: the line runs through the row, the dot sits on it. */
function Rail({ first, last, hollow }: { first: boolean; last: boolean; hollow?: boolean }): ReactNode {
  return (
    <span aria-hidden className="relative flex shrink-0 items-center justify-center self-stretch" style={{ width: 12 }}>
      <span className="absolute" style={{ left: 5.5, width: 1, top: first ? '50%' : 0, bottom: last ? '50%' : 0, background: fill.hairline }} />
      <span className="relative block" style={{ width: 8, height: 8, borderRadius: radius2.round, background: hollow ? 'var(--l-overlay)' : color.text, boxShadow: hollow ? `inset 0 0 0 1px ${fill.ring}` : undefined }} />
    </span>
  )
}
