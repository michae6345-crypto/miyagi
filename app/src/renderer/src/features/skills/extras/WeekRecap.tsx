/**
 * The weekly recap on Progress (mockup skills-07-extras, 3), in place of a streak: what the week built ("2 skills
 * mastered, 3 kept fresh, 1 h 40 min."), how far the goal is, and the week as seven blocks, Monday first. A practiced
 * day is a solid block; every other day is the same quiet track, so a missed day is never called out. The foot says
 * how many practice days and the weekly goal. Neutral only (ink / white and the track): this is not a status.
 */
import { useEffect, type ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../../core/theme'
import { CARD } from '../../shell/ui'
import { goalsFor } from '../../dashboard/model'
import { useDash } from '../../dashboard/store'
import { goalAway, weekLines } from './recap'
import { ensureSkillGraph, useSkillGraph } from './store'

const LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

/** This week's recap card, or nothing when the engine sent no week. `head`: the page's section header. */
export function WeekRecap({ head }: { head?: ReactNode }): ReactNode {
  const graph = useSkillGraph((s) => s.graph)
  const data = useDash((s) => s.data)
  const prefs = useDash((s) => s.prefs)
  useEffect(ensureSkillGraph, [])
  const week = graph?.week
  if (!week || week.days.length !== 7) return null
  const weekly = week.weeklyGoal ?? goalsFor(data, prefs).weekly
  const t = weekLines(week, goalAway(graph), weekly)
  return (
    <section aria-labelledby="prog-week" data-prog-week>
      {head}
      <div className="flex flex-col" style={{ ...CARD, padding: 24, gap: 20 }}>
        <p className="m-0" style={{ fontSize: type2.lg, lineHeight: '26px', letterSpacing: '-0.2px', color: color.text, textWrap: 'pretty' }}>
          <span className="font-semibold">{t.lead}</span>
          {t.rest}
          {t.goal && (
            <>
              <br />
              <span style={{ color: color.label }}>{t.goal}</span>
            </>
          )}
        </p>
        <div role="img" aria-label={`Practiced on ${week.days.map((d, i) => (d ? DAY_NAMES[i] : '')).filter(Boolean).join(', ') || 'no days yet'}`} className="grid gap-[8px]" style={{ gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }}>
          {week.days.map((d, i) => (
            <div key={i} className="flex flex-col items-center gap-[8px]">
              <span data-week-day={d ? 'on' : 'off'} className="block w-full" style={{ height: 28, borderRadius: radius2.control, background: d ? color.text : fill.trackSoft }} />
              <span style={{ fontSize: type2.micro, color: color.faint }}>{LETTERS[i]}</span>
            </div>
          ))}
        </div>
        <p className="m-0" style={{ paddingTop: 16, borderTop: `1px solid ${fill.hairline}`, fontSize: type2.sm, color: color.label }}>
          {t.days}
        </p>
      </div>
    </section>
  )
}
