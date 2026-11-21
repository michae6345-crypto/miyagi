/**
 * Feature: dashboard. The lesson dashboard (DASHBOARD-RESEARCH.md section 3):
 *
 *   top band   Today ring · This week (or 12 weeks) · Reps · Rhythm
 *   center     the skill constellation, one cluster per track; a node's card opens over its top right
 *   right rail Review · Continue · Up next
 *   footer     Milestones (quiet text, no fireworks)
 *
 * Shown as Library's Home section (the window the Dock click and the tray open) and as the Progress window's body.
 * Every number comes from verified steps the engine counted; what the engine doesn't track yet shows an empty state.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useLesson } from '../../core/lesson'
import type { AppRoute } from '../../core/surfaces'
import { color, fill, radius2, type2 } from '../../core/theme'
import { Band } from './Band'
import { Constellation } from './Constellation'
import { dueItems, goalsFor, laterItems, milestones, rhythm, shortDay, totals, type Milestone } from './model'
import { caption } from './parts'
import { Continue, Review, SkillCard, UpNext } from './Rail'
import { requestDashboard, useDash, useLoad } from './store'

/** The clock, refreshed each minute so "today" turns over at midnight with the window open. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])
  return now
}

function Milestones({ list }: { list: Milestone[] }): ReactNode {
  const done = list.filter((m) => m.done).sort((a, b) => (a.at ?? 0) - (b.at ?? 0))
  const next = list.find((m) => !m.done)
  const shown = done.slice(-4)
  return (
    <section aria-label="Milestones" data-milestones className="flex shrink-0 items-center gap-[20px] overflow-hidden" style={{ height: 48, padding: '0 20px', borderRadius: radius2.chip, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
      <h2 className="m-0 shrink-0" style={{ fontSize: type2.sm, fontWeight: 600, color: color.text }}>
        Milestones
      </h2>
      {!shown.length && !next ? (
        <span style={caption}>Your first passed step will show up here.</span>
      ) : (
        <ul className="m-0 flex min-w-0 flex-1 list-none items-center gap-[20px] p-0">
          {shown.map((m) => (
            <li key={m.id} data-milestone={m.id} className="flex min-w-0 shrink items-center gap-[8px]">
              <span className="block shrink-0" style={{ width: 6, height: 6, borderRadius: radius2.round, background: color.text }} />
              <span className="truncate" style={{ fontSize: type2.xs, color: color.text }}>
                {m.label}
              </span>
              {m.at && (
                <span className="shrink-0" style={{ fontSize: type2.micro, color: color.faint }}>
                  {shortDay(m.at)}
                </span>
              )}
            </li>
          ))}
          {next && (
            <li data-milestone-next={next.id} className="ml-auto flex shrink-0 items-center gap-[8px]">
              <span className="block shrink-0" style={{ width: 6, height: 6, borderRadius: radius2.round, boxShadow: `inset 0 0 0 1px ${fill.ring}` }} />
              <span style={{ fontSize: type2.xs, color: color.label }}>
                Next: {next.label}
                {next.toGo ? `, ${next.toGo}` : ''}
              </span>
            </li>
          )}
        </ul>
      )}
    </section>
  )
}

export function Dashboard({ route }: { route: AppRoute }): ReactNode {
  const data = useDash((s) => s.data)
  const prefs = useDash((s) => s.prefs)
  const load = useLoad()
  const connected = useLesson((s) => s.connected)
  const hello = useLesson((s) => s.hello)
  const now = useNow()

  // Ask on open, when the engine (re)connects, and whenever the window comes forward.
  useEffect(() => {
    void requestDashboard()
  }, [connected, hello])
  useEffect(() => {
    const onFocus = (): void => void requestDashboard()
    addEventListener('focus', onFocus)
    return () => removeEventListener('focus', onFocus)
  }, [])

  const goals = goalsFor(data, prefs)
  const r = rhythm(data?.activity ?? null, now, goals)
  const t = totals(data, now)
  const due = dueItems(data?.review ?? null, now)
  const later = laterItems(data?.review ?? null, now)
  const active = [...(data?.inProgress ?? [])].sort((a, b) => (b.lastActiveAt ?? 0) - (a.lastActiveAt ?? 0))
  // The one primary: Resume the newest saved lesson in progress, else Start the first up-next lesson.
  const resumable = active.find((a) => a.libraryId)
  const primary = resumable ? `resume:${resumable.lessonId}` : data?.next[0] ? `next:${data.next[0].title}` : undefined

  return (
    <div data-dashboard className="flex h-full min-h-0 w-full flex-col gap-[16px]" style={{ padding: '20px 24px 24px', color: color.text }}>
      <Band data={data} now={now} goals={goals} r={r} t={t} />
      <div className="grid min-h-0 flex-1 gap-[16px]" style={{ gridTemplateColumns: 'minmax(0, 1fr) 300px' }}>
        <Constellation data={data} review={due} loading={load === 'loading'}>
          <SkillCard data={data} now={now} route={route} />
        </Constellation>
        <div className="flex min-h-0 flex-col gap-[12px] overflow-y-auto" data-rail>
          <Continue items={active} primary={primary} route={route} />
          <Review data={data} due={due} later={later} now={now} route={route} />
          <UpNext data={data} primary={primary} route={route} />
        </div>
      </div>
      <Milestones list={milestones(data, r, now)} />
    </div>
  )
}
