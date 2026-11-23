/**
 * Feature: dashboard. The home window's Progress page (redraft round 3, Adrian: "refine the fuck out of the dashboard").
 * Progress used to repeat the Skills page's graphs with a rail beside them. Now it earns its own page: what to do
 * next and what you have done, as plain lists, and the skills as one line per track that opens the Skills page.
 *
 *   Review     what is due (and coming), one row each; Start review only when the engine can review
 *   Up next    the engine's suggestions: title, what it unlocks, minutes, a quiet Start
 *   Skills     one row per track: the progress ring, the track, the skill that comes next; opens the Skills page
 *   This week  the weekly recap (skills/extras WeekRecap), never a streak; only when the engine sent a week
 *   Finished   the lessons you finished, newest first, with the green check (green = passed)
 *   Projects   finished projects and the goal (skills/extras Portfolio); only with a project or a chosen goal
 *   Milestones the quiet line at the foot
 *
 * Every row uses the shell's Row (and RowChevron when it opens something), so Progress reads like Home and Lessons.
 * Nothing here invents a number: each part shows only what the engine sent, or its own empty state.
 */
import type { ReactNode } from 'react'
import { CodeText } from '../../core/ui/atoms'
import { QuietButton } from '../../core/ui/buttons'
import { StatusGlyph } from '../../core/ui/status'
import type { AppRoute } from '../../core/surfaces'
import { color, fill, type2 } from '../../core/theme'
import { Row, RowChevron, SectionHead, TextAction } from '../shell/ui'
import { setPage } from '../shell/store'
import { openDetail } from '../library/store'
import { Skeleton } from '../library/parts'
import { Portfolio } from '../skills/extras/Portfolio'
import { WeekRecap } from '../skills/extras/WeekRecap'
import { ProgressSummary } from './Summary'
import { TrackRing } from './Constellation'
import { Milestones, useDashView } from './Dashboard'
import { groupTracks, milestones, nodeStates, relDay, relInLine, unlockLabels, type SkillGroup } from './model'
import { Empty } from './parts'
import { canReview, startGoal, startReview, startSaved, useDash } from './store'
import type { DashData, DashNext, ReviewEntry } from './types'

const list = { margin: 0, padding: 0, listStyle: 'none', marginInline: -10 } as const
const title = { fontSize: type2.md, color: color.text } as const
const meta = { fontSize: type2.xs, lineHeight: '16px', color: color.label } as const
const when = { fontSize: type2.xs, color: color.faint, fontVariantNumeric: 'tabular-nums' } as const
const plain = (s: string): string => s.split(String.fromCharCode(96)).join('')

/** Hairlines only in a long list (4+ rows); the first row never gets one. Inset to the text, like Lessons. */
function Li({ i, n, children }: { i: number; n: number; children: ReactNode }): ReactNode {
  return <li style={n >= 4 && i > 0 ? { borderTop: `1px solid ${fill.hairline}`, marginInline: 10 } : { marginInline: 10 }}><div style={{ marginInline: -10 }}>{children}</div></li>
}

function Loading(): ReactNode {
  return (
    <div aria-busy aria-label="Reading your progress" className="flex flex-col gap-[10px]">
      <Skeleton h={18} />
      <Skeleton h={40} />
      <Skeleton h={40} />
    </div>
  )
}

// ---- review -----------------------------------------------------------------------------------------------------

function dueWords(r: ReviewEntry, now: number): string {
  if (r.dueAt !== undefined) return `Due ${relInLine(r.dueAt, now)}`
  if (r.when) return `Due ${/^(today|tomorrow|now)$/i.test(r.when) ? r.when.toLowerCase() : r.when}`
  return 'Due'
}

function ReviewPart({ data, due, later, now, route }: { data?: DashData; due: ReviewEntry[]; later: ReviewEntry[]; now: number; route: AppRoute }): ReactNode {
  const can = canReview()
  const rows = [...due.slice(0, 3).map((r) => ({ r, due: true })), ...later.slice(0, due.length ? 2 : 4).map((r) => ({ r, due: false }))]
  return (
    <section aria-labelledby="prog-review" data-prog-review>
      <SectionHead id="prog-review" right={due.length > 0 && can ? <QuietButton label="Start review" title={`One short step on ${plain(due[0].label)}`} onClick={() => startReview(due[0], route)} /> : undefined}>
        Review
      </SectionHead>
      {!data?.review || !rows.length ? (
        <Empty title="Nothing to review yet" body="Mastered skills come back here at 3, 7, 21 and 60 days." />
      ) : (
        <ul style={list}>
          {rows.map(({ r, due: d }, i) => (
            <Li key={`${d ? 'd' : 'l'}-${r.label}-${i}`} i={i} n={rows.length}>
              <Row label={`${plain(r.label)}. ${d ? dueWords(r, now) : r.dueAt ? relDay(r.dueAt, now) : (r.when ?? '')}.`} data={{ 'data-review-item': d ? 'due' : 'later' }}>
                <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
                  <span className="truncate" style={title}>
                    <CodeText text={r.label} />
                  </span>
                  {r.track && (
                    <span className="truncate" style={meta}>
                      {r.track}
                    </span>
                  )}
                </span>
                <span className="relative shrink-0" style={d ? { ...when, color: color.text } : when}>
                  {d ? dueWords(r, now) : r.dueAt ? relDay(r.dueAt, now) : r.when}
                </span>
              </Row>
            </Li>
          ))}
        </ul>
      )}
    </section>
  )
}

// ---- up next ----------------------------------------------------------------------------------------------------

function NextPart({ data, route }: { data?: DashData; route: AppRoute }): ReactNode {
  const starting = useDash((s) => s.starting)
  const startErr = useDash((s) => s.startError)
  const next = (data?.next ?? []).slice(0, 3)
  return (
    <section aria-labelledby="prog-next" data-prog-next>
      <SectionHead id="prog-next">Up next</SectionHead>
      {!next.length ? (
        <Empty title="Nothing queued yet" body="Finish a lesson and miyagi suggests what comes next." />
      ) : (
        <ul style={list}>
          {next.map((n: DashNext, i) => {
            const unlocks = unlockLabels(data, n.unlocks)
            const line = [unlocks.length ? `Unlocks ${unlocks.map(plain).join(', ')}` : '', n.estMinutes ? `${n.estMinutes} min` : ''].filter(Boolean).join(' · ')
            const busy = !!n.id && starting === n.id
            const err = n.id && startErr?.key === n.id ? startErr.text : undefined
            return (
              <Li key={n.title} i={i} n={next.length}>
                <Row label={`${n.title}. ${line}`} data={{ 'data-next': n.title }}>
                  <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
                    <span className="truncate" style={title}>
                      {n.title}
                    </span>
                    {(line || err) && (
                      <span role={err ? 'status' : undefined} className="truncate" style={err ? { ...meta, color: color.text } : meta}>
                        {err ?? line}
                      </span>
                    )}
                  </span>
                  <span className="relative shrink-0">
                    <QuietButton label="Start" busy={busy} disabled={!!starting && !busy} onClick={() => (n.id ? void startSaved(n.id, route) : startGoal(n.goal, route))} />
                  </span>
                </Row>
              </Li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

// ---- skills, one line per track -----------------------------------------------------------------------------------

/** What comes next in a track, in words: the first skill ready to learn, else what is being practiced, else done. */
function trackLine(g: SkillGroup): string {
  const st = nodeStates(g.track)
  const skills = g.track.skills
  const ready = skills.find((s) => st[s.id] === 'available')
  if (ready) return `Next: ${plain(ready.label)}`
  const practicing = skills.find((s) => st[s.id] === 'practicing')
  if (practicing) return `Practicing ${plain(practicing.label)}`
  if (skills.length && skills.every((s) => st[s.id] === 'mastered')) return 'All mastered'
  return 'Locked for now'
}

function SkillsPart({ data, route }: { data?: DashData; route: AppRoute }): ReactNode {
  const groups = groupTracks(data)
  const open = route === 'library' ? () => setPage('skills') : undefined
  return (
    <section aria-labelledby="prog-skills" data-prog-skills>
      <SectionHead id="prog-skills" right={open ? <TextAction onClick={open}>All skills</TextAction> : undefined}>
        Skills
      </SectionHead>
      {!groups.length ? (
        <Empty title="No skills yet" body="Finish a lesson. The skills its checks proved show up here." />
      ) : (
        <ul style={list}>
          {groups.map((g, i) => {
            const mastered = g.track.skills.filter((s) => s.state === 'mastered').length
            return (
              <Li key={g.key} i={i} n={groups.length}>
                <Row onClick={open} label={`${g.title}. ${trackLine(g)}.${open ? ' Open Skills.' : ''}`} data={{ 'data-prog-track': g.key }}>
                  <span className="relative flex shrink-0">
                    <TrackRing mastered={mastered} total={g.track.skills.length} />
                  </span>
                  <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
                    <span className="truncate" style={title}>
                      {g.title}
                    </span>
                    <span className="truncate" style={meta}>
                      {[g.kicker, trackLine(g)].filter(Boolean).join(' · ')}
                    </span>
                  </span>
                  {open && <RowChevron />}
                </Row>
              </Li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

// ---- finished ---------------------------------------------------------------------------------------------------

function DonePart({ data, now, route }: { data?: DashData; now: number; route: AppRoute }): ReactNode {
  const done = [...(data?.completed ?? [])].sort((a, b) => (b.finishedAt ?? 0) - (a.finishedAt ?? 0)).slice(0, 6)
  if (!done.length) return null
  return (
    <section aria-labelledby="prog-done" data-prog-done>
      <SectionHead id="prog-done">Finished</SectionHead>
      <ul style={list}>
        {done.map((d, i) => {
          const open = route === 'library' && d.libraryId ? () => openDetail(d.libraryId!) : undefined
          return (
            <Li key={d.lessonId} i={i} n={done.length}>
              <Row onClick={open} label={`${d.title}. Finished${d.finishedAt ? ` ${relDay(d.finishedAt, now)}` : ''}.${open ? ' Open its preview.' : ''}`} data={{ 'data-prog-done': d.lessonId }}>
                <span className="relative flex shrink-0">
                  <StatusGlyph state="passed" size={14} still />
                </span>
                <span className="relative min-w-0 flex-1 truncate" style={title}>
                  {d.title}
                </span>
                {d.finishedAt && (
                  <span className="relative shrink-0" style={when}>
                    {relDay(d.finishedAt, now)}
                  </span>
                )}
                {open && <RowChevron />}
              </Row>
            </Li>
          )
        })}
      </ul>
    </section>
  )
}

// ---- the page -----------------------------------------------------------------------------------------------------

export function ProgressOverview({ route }: { route: AppRoute }): ReactNode {
  const { data, load, now, goals, r, due, later } = useDashView()
  const loading = load === 'loading'
  const ms = loading ? [] : milestones(data, r, now)
  return (
    <div data-progress-overview className="h-full overflow-y-auto" style={{ color: color.text, scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
      <div className="flex w-full flex-col gap-[32px]" style={{ padding: '8px 40px 48px', maxWidth: 1040 }}>
        {loading ? (
          <Loading />
        ) : (
          <>
            <ProgressSummary data={data} now={now} goal={goals.daily} due={due} />
            <WeekRecap head={<SectionHead id="prog-week">This week</SectionHead>} />
            {(data?.review || due.length > 0) && <ReviewPart data={data} due={due} later={later} now={now} route={route} />}
            <NextPart data={data} route={route} />
            <SkillsPart data={data} route={route} />
            <DonePart data={data} now={now} route={route} />
            <Portfolio head={<SectionHead id="prog-portfolio">Projects</SectionHead>} onOpenGoal={route === 'library' ? () => setPage('skills') : undefined} />
            {ms.some((m) => m.done) && <Milestones list={ms} />}
          </>
        )}
      </div>
    </div>
  )
}
