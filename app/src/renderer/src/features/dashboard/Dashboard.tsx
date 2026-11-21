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
import { Constellation } from './Constellation'
import { dueItems, goalsFor, laterItems, milestones, rhythm, shortDay, totals, type Milestone } from './model'
import { caption } from './parts'
import { continueList } from './continue'
import { Continue, Review, SkillCard, UpNext } from './Rail'
import { useLibrary } from '../library/store'
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

export function Milestones({ list }: { list: Milestone[] }): ReactNode {
  const done = list.filter((m) => m.done).sort((a, b) => (a.at ?? 0) - (b.at ?? 0))
  const next = list.find((m) => !m.done)
  const shown = done.slice(-4)
  return (
    <section aria-label="Milestones" data-milestones className="flex shrink-0 flex-wrap items-center gap-x-[20px] gap-y-[6px]" style={{ minHeight: 32 }}>
      <h2 className="m-0 shrink-0" style={{ fontSize: type2.xs, fontWeight: 500, letterSpacing: '0.02em', color: color.label }}>
        Milestones
      </h2>
      {!list.length ? null : !shown.length && !next ? (
        <span style={caption}>Your first passed step will show up here.</span>
      ) : (
        <ul className="m-0 flex min-w-0 flex-1 list-none flex-wrap items-center gap-x-[20px] gap-y-[6px] p-0">
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

/**
 * The dashboard's data and derived numbers, with the asks that keep it fresh (on open, when the engine (re)connects,
 * and whenever the window comes forward). Shared by the full dashboard below and Library's Home (features/library).
 */
export function useDashView() {
  const data = useDash((s) => s.data)
  const prefs = useDash((s) => s.prefs)
  const load = useLoad()
  const connected = useLesson((s) => s.connected)
  const hello = useLesson((s) => s.hello)
  const now = useNow()

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
  return { data, load, now, goals, r, t, due, later, active }
}

export function Dashboard({ route }: { route: AppRoute }): ReactNode {
  const { data, load, now, r, due, later } = useDashView()
  const items = useLibrary((s) => s.items)
  const cont = continueList(data, items)
  const loading = load === 'loading'
  const hasReview = !!data?.review && (due.length > 0 || later.length > 0)
  const hasNext = (data?.next.length ?? 0) > 0
  const ms = loading ? [] : milestones(data, r, now)
  const rail = !loading && (hasReview || hasNext)
  // One quiet page: Continue, then Skills with Review and Up next beside them. Parts with nothing to show are left out.
  return (
    <div data-dashboard className="relative h-full min-h-0 w-full" style={{ color: color.text }}>
      <div className="h-full overflow-y-auto" style={{ padding: '24px 32px 32px', scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
        <div className="mx-auto flex w-full flex-col gap-[36px]" style={{ maxWidth: 1040 }}>
          {cont.length > 0 && <Continue items={cont} route={route} />}
          <div className={rail ? 'grid items-start gap-[40px] @min-[900px]:grid-cols-[minmax(0,1fr)_280px]' : ''}>
            <Constellation data={data} review={due} loading={loading} bare />
            {rail && (
              <div className="flex flex-col gap-[28px]" data-rail>
                {hasReview && <Review data={data} due={due} later={later} now={now} route={route} />}
                {hasNext && <UpNext data={data} route={route} />}
              </div>
            )}
          </div>
          {ms.some((m) => m.done) && <Milestones list={ms} />}
        </div>
      </div>
      <SkillCard data={data} now={now} route={route} />
    </div>
  )
}
