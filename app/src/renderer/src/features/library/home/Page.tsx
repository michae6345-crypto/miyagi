/**
 * Feature: library. Home v4, the page (Adrian's ui-next mock, `home` and `home-empty`, after the Nov 24 trim pass).
 *
 * 1040 wide: a main column and a 316 px rail with one hairline between them; under ~960 px of pane the rail drops
 * under the main column. Rows and hairlines, no tiles; the only card is Continue.
 *
 *   main    greeting and date · ask · Continue · Plans · Up next · Recently passed
 *   rail    This week (bars + practiced, steps passed, skills mastered) · Goal · Skills · Keep fresh
 *   first   Welcome · ask · Start here (three plans) · Or one short lesson · Make your own
 *           rail: Set up · How a lesson works · Pick a goal
 */
import { Flag, ListVideo, RotateCcw, Sprout } from 'lucide-react'
import type { ReactNode } from 'react'
import { openOnboarding } from '../../../core/surfaces'
import { color, fill } from '../../../core/theme'
import { QuietButton } from '../../../core/ui/buttons'
import type { Row as SetupRow } from '../../onboarding/rows'
import { setPage } from '../../shell/store'
import { Pane } from '../layout'
import { openDetail, setSection } from '../store'
import { Bar, Check, Chev, Cover, Hollow, RailRow, RowBtn, Sec, T, Tag, WeekChart, hair, muted, rowCss } from './bits'
import { agoLabel, hoursMinutes, leftLabel, longDate, sizeLabel, whenLabel, type GoalPick, type HomeModel, type ShortLesson, type StarterPlan } from './data'
import { focusAsk } from './Top'

/** Pane width where the rail sits beside the main column (a static class string so Tailwind sees it). */
const TWO = '@min-[960px]/pane:grid-cols-[minmax(0,1fr)_316px] @min-[960px]/pane:gap-x-[40px]'
const RAIL = 'rail border-t pt-[8px] @min-[960px]/pane:border-t-0 @min-[960px]/pane:border-l @min-[960px]/pane:pt-0 @min-[960px]/pane:pl-[32px]'

function Frame({ main, rail, data }: { main: ReactNode; rail: ReactNode; data: string }): ReactNode {
  return (
    <Pane data-home={data} className="flex flex-1 flex-col overflow-y-auto" style={{ color: color.text, scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
      <style>{rowCss}</style>
      <div className="mx-auto w-full max-w-[1120px] px-[40px] @max-[760px]/pane:px-[24px]" style={{ paddingTop: 44, paddingBottom: 60 }}>
        <div className={`grid grid-cols-1 items-start gap-y-[32px] ${TWO}`}>
          <div data-home-main className="min-w-0">
            {main}
          </div>
          <aside data-home-rail aria-label="Your week" className={RAIL} style={{ borderColor: hair, paddingBottom: 48, minWidth: 0, maxWidth: undefined }}>
            {rail}
          </aside>
        </div>
      </div>
    </Pane>
  )
}

function Hello({ title, now, lede }: { title: string; now: number; lede?: string }): ReactNode {
  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-[12px]">
        <h1 className="m-0" style={{ fontSize: T.h1, lineHeight: 1.2, fontWeight: 700, letterSpacing: '-0.022em', color: color.text }}>
          {title}
        </h1>
        <span className="ml-auto" style={{ fontSize: T.meta, color: color.faint }}>
          {longDate(now)}
        </span>
      </div>
      {lede && <p style={{ margin: '6px 0 0', fontSize: 14.5, color: color.label }}>{lede}</p>}
    </>
  )
}

// ---- the main column ------------------------------------------------------------------------------------------------

function Plans({ m }: { m: HomeModel }): ReactNode {
  if (!m.plans.length) return null
  return (
    <section aria-labelledby="home-plans" data-home-plans>
      <Sec id="home-plans" link="Browse plans" onLink={() => setSection('library')}>
        Plans
      </Sec>
      <div className="mg-h4-list">
        {m.plans.map((p) => (
          <RowBtn key={p.id} cols="minmax(0,1.25fr) 130px minmax(0,1fr) 14px" label={`${p.title}, ${p.done} of ${p.total}${p.next ? `, next ${p.next}` : ''}`} onClick={() => setSection('library')} data={{ 'data-plan': p.id }}>
            <b className="truncate" style={{ fontWeight: 550, color: color.text }}>
              {p.title}
            </b>
            <span className="flex items-center gap-[10px]">
              <Bar fraction={p.done / p.total} width={72} />
              <span style={muted}>
                {p.done} of {p.total}
              </span>
            </span>
            <span className="truncate" style={muted}>
              {p.next ? `Next · ${p.next}` : ''}
            </span>
            <Chev />
          </RowBtn>
        ))}
      </div>
    </section>
  )
}

function LessonRows({ rows, onOpen }: { rows: Array<{ id: string; title: string; skill?: string; meta: string; cover: ShortLesson['cover'] }>; onOpen: (id: string) => void }): ReactNode {
  return (
    <div className="mg-h4-list">
      {rows.map((r) => (
        <RowBtn key={r.id} cols="minmax(0,1fr) auto minmax(204px,max-content) 14px" minH={50} label={`${r.title}. ${r.meta}.`} onClick={() => onOpen(r.id)} data={{ 'data-lesson': r.id }}>
          <span className="flex min-w-0 items-center gap-[10px]">
            <Cover kind={r.cover} width={54} radius={5} />
            <b className="truncate" style={{ fontWeight: 550, color: color.text }}>
              {r.title}
            </b>
          </span>
          <span className="min-w-0">{r.skill ? <Tag>{r.skill}</Tag> : null}</span>
          <span className="truncate text-right" style={muted}>
            {r.meta}
          </span>
          <Chev />
        </RowBtn>
      ))}
    </div>
  )
}

function UpNext({ m }: { m: HomeModel }): ReactNode {
  if (!m.next.length) return null
  return (
    <section aria-labelledby="home-next" data-home-ready>
      <Sec id="home-next" link="Library" onLink={() => setSection('library')}>
        Up next
      </Sec>
      <LessonRows rows={m.next} onOpen={openDetail} />
    </section>
  )
}

function Passed({ m, now }: { m: HomeModel; now: number }): ReactNode {
  if (!m.passes.length) return null
  const th = { textAlign: 'left', fontSize: T.small, fontWeight: 450, color: color.label, height: 32, padding: '0 8px', borderBottom: `1px solid ${hair}` } as const
  const td = { height: 40, padding: '0 8px', borderBottom: `1px solid ${hair}`, verticalAlign: 'middle' } as const
  const showSkill = m.passes.some((p) => p.skill)
  return (
    <section aria-labelledby="home-passed" data-home-recent>
      <Sec id="home-passed" link="Progress" onLink={() => setPage('progress')}>
        Recently passed
      </Sec>
      <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: T.body, margin: '0 -8px', width: 'calc(100% + 16px)', tableLayout: 'fixed' }}>
        <colgroup>
          <col style={{ width: 140 }} />
          <col />
          {showSkill && <col style={{ width: '28%' }} />}
        </colgroup>
        <thead>
          <tr>
            <th style={th}>When</th>
            <th style={th}>{m.passes.every((p) => p.lesson) ? 'Lesson' : 'Step'}</th>
            {showSkill && <th style={th}>Skill</th>}
          </tr>
        </thead>
        <tbody>
          {m.passes.map((p, i) => {
            const last = i === m.passes.length - 1
            const c = last ? { ...td, borderBottom: 0 } : td
            return (
              <tr key={p.key} data-pass={p.key}>
                <td className="truncate" style={{ ...c, color: color.label, whiteSpace: 'nowrap' }}>
                  {whenLabel(p.at, now)}
                </td>
                <td style={c}>
                  <span className="flex min-w-0 items-center gap-[10px]">
                    <Check />
                    <b className="truncate" style={{ fontWeight: 550, color: color.text }}>
                      {p.step}
                    </b>
                  </span>
                </td>
                {showSkill && <td style={{ ...c, overflow: 'hidden' }}>{p.skill && <Tag>{p.skill}</Tag>}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

// ---- the rail ---------------------------------------------------------------------------------------------------

function Stat({ parts, label, first }: { parts: Array<[string, string]>; label: string; first?: boolean }): ReactNode {
  return (
    <div className="min-w-0 flex-none" style={{ padding: first ? '0 15px 0 0' : '0 15px', borderLeft: first ? 0 : `1px solid ${fill.chipBorder}` }}>
      <b className="block whitespace-nowrap" style={{ fontSize: 17, fontWeight: 650, letterSpacing: '-0.015em', color: color.text, lineHeight: 1.2, fontVariantNumeric: 'tabular-nums' }}>
        {parts.map(([n, u], i) => (
          <span key={i}>
            {i > 0 && ' '}
            {n}
            {u && <small style={{ fontSize: 12.5, fontWeight: 550, color: color.label, marginLeft: 2 }}>{u}</small>}
          </span>
        ))}
      </b>
      <span className="block whitespace-nowrap" style={{ fontSize: 12, color: color.label }}>
        {label}
      </span>
    </div>
  )
}

function Week({ m }: { m: HomeModel }): ReactNode {
  const any = m.week.some((b) => b.value > 0)
  if (!any && !m.stats.steps) return null
  const unit = m.stats.minutes !== undefined ? 'min' : 'steps'
  return (
    <section aria-labelledby="home-week" data-home-week>
      <Sec id="home-week" first link="Progress" onLink={() => setPage('progress')}>
        This week
      </Sec>
      <WeekChart bars={m.week} unit={unit} />
      <div className="flex" style={{ marginTop: 10 }}>
        {m.stats.minutes !== undefined && <Stat first parts={hoursMinutes(m.stats.minutes)} label="practiced" />}
        <Stat first={m.stats.minutes === undefined} parts={[[String(m.stats.steps), '']]} label="steps passed" />
        <Stat parts={[[String(m.stats.mastered), '']]} label="skills mastered" />
      </div>
    </section>
  )
}

function Goal({ m }: { m: HomeModel }): ReactNode {
  const g = m.goal
  if (!g || !g.total) return null
  return (
    <section aria-labelledby="home-goal" data-home-goal>
      <Sec id="home-goal">Goal</Sec>
      <div className="flex items-center gap-[8px]" style={{ fontSize: 14 }}>
        <Flag aria-hidden size={15} strokeWidth={1.8} style={{ color: color.label }} />
        <b className="truncate" style={{ fontWeight: 560, color: color.text }}>
          {g.title}
        </b>
      </div>
      <div style={{ margin: '11px 0 8px' }}>
        <Bar fraction={g.done / g.total} label={`${g.done} of ${g.total} skills`} />
      </div>
      <div className="flex justify-between" style={muted}>
        <span>
          {g.done} of {g.total} skills
        </span>
        {g.minutesLeft !== undefined && <span>{leftLabel(g.minutesLeft)}</span>}
      </div>
    </section>
  )
}

function Skills({ m }: { m: HomeModel }): ReactNode {
  if (!m.skills.length) return null
  return (
    <section aria-labelledby="home-skills" data-home-skills>
      <Sec id="home-skills" link={`${m.skillsDone} of ${m.skillsTotal} mastered`} onLink={() => setPage('skills')}>
        Skills
      </Sec>
      <div className="mg-h4-list">
        {m.skills.slice(0, 6).map((s) => (
          <RailRow key={s.label} right={
              <>
                <Bar fraction={s.done / s.total} green width={64} />
                <span style={{ ...muted, width: 42, textAlign: 'right' }}>
                  {s.done} of {s.total}
                </span>
              </>
            }>
            {s.label}
          </RailRow>
        ))}
      </div>
    </section>
  )
}

function Fresh({ m, now }: { m: HomeModel; now: number }): ReactNode {
  if (!m.fresh.length) return null
  return (
    <section aria-labelledby="home-fresh" data-home-review>
      <Sec id="home-fresh" link="Progress" onLink={() => setPage('progress')}>
        Keep fresh
      </Sec>
      <div className="mg-h4-list">
        {m.fresh.slice(0, 3).map((f) => (
          <RailRow key={f.label} icon={<RotateCcw aria-hidden size={15} strokeWidth={1.8} className="shrink-0" style={{ color: color.label }} />} right={f.at !== undefined ? <span style={muted}>{agoLabel(f.at, now)}</span> : undefined}>
            {f.label}
          </RailRow>
        ))}
      </div>
    </section>
  )
}

// ---- the pages --------------------------------------------------------------------------------------------------------

export function HomePage({ m, now, ask, cont, greeting, notice }: { m: HomeModel; now: number; ask: ReactNode; cont: ReactNode; greeting: string; notice?: ReactNode }): ReactNode {
  const rail = (
    <>
      <Week m={m} />
      <Goal m={m} />
      <Skills m={m} />
      <Fresh m={m} now={now} />
    </>
  )
  return (
    <Frame
      data="v4"
      main={
        <>
          {notice}
          <Hello title={greeting} now={now} />
          <div style={{ marginTop: 14 }}>{ask}</div>
          {cont && <div style={{ marginTop: 14 }}>{cont}</div>}
          <Plans m={m} />
          <UpNext m={m} />
          <Passed m={m} now={now} />
        </>
      }
      rail={rail}
    />
  )
}

function StarterCard({ p }: { p: StarterPlan }): ReactNode {
  return (
    <button type="button" data-starter={p.id} onClick={() => focusAsk(`Teach me ${p.title}`)} className="mg-press flex min-w-0 cursor-pointer flex-col items-stretch justify-start self-start rounded-[8px] text-left outline-offset-4 focus-visible:outline-2" style={{ outlineColor: color.text }}>
      <Cover kind={p.cover} width="100%" />
      <b className="mt-[10px] block truncate" style={{ fontSize: 14.5, fontWeight: 600, color: color.text }}>
        {p.title}
      </b>
      <span className="mt-[2px] block" style={{ fontSize: T.small, color: color.label }}>
        {p.tool} · {p.lessons} lessons · {sizeLabel(p.minutes)}
      </span>
      {p.ends && (
        <span className="block" style={{ fontSize: T.small, color: color.label }}>
          {p.ends}
        </span>
      )}
    </button>
  )
}

function Way({ icon, title, line, onClick }: { icon: ReactNode; title: string; line: string; onClick: () => void }): ReactNode {
  return (
    <button type="button" onClick={onClick} className="flex min-w-0 cursor-pointer items-center gap-[12px] text-left outline-offset-2 hover:bg-(--s-row-hover) focus-visible:outline-2" style={{ height: 62, padding: '0 14px', borderRadius: 10, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}`, outlineColor: color.text }}>
      <span className="shrink-0" style={{ color: color.label }}>
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <b className="block truncate" style={{ fontSize: 14, fontWeight: 560, color: color.text }}>
          {title}
        </b>
        <span className="block truncate" style={{ fontSize: T.meta, color: color.label }}>
          {line}
        </span>
      </span>
      <Chev />
    </button>
  )
}

const hoursWord = (min: number): string => {
  const h = Math.round(min / 60)
  return `about ${h} ${h === 1 ? 'hour' : 'hours'}`
}

export function FirstRunPage({ now, greeting, ask, starters, lessons, goals, setup, notice }: { now: number; greeting: string; ask: ReactNode; starters: StarterPlan[]; lessons: ShortLesson[]; goals: GoalPick[]; setup: SetupRow[]; notice?: ReactNode }): ReactNode {
  const ok = setup.filter((r) => r.state === 'passed').length
  const rail = (
    <>
      {setup.length > 0 && (
        <section aria-labelledby="home-setup" data-home-setup>
          <Sec id="home-setup" first link={`${ok} of ${setup.length}`} onLink={() => void openOnboarding()}>
            Set up
          </Sec>
          <div className="mg-h4-list">
            {setup.map((r) => (
              <RailRow key={r.id} icon={r.state === 'passed' ? <Check /> : <Hollow />} right={r.state === 'passed' ? <span style={muted}>{r.word}</span> : r.action ? <QuietButton label={r.action.label} onClick={() => void openOnboarding()} /> : <span style={muted}>{r.word}</span>}>
                {r.label}
              </RailRow>
            ))}
          </div>
        </section>
      )}
      <section aria-labelledby="home-how" data-home-how>
        <Sec id="home-how" first={!setup.length}>
          How a lesson works
        </Sec>
        <ol className="mg-h4-list m-0 list-none p-0">
          {['miyagi shows one step.', 'You do it in the real app.', 'It checks your work, then the next.'].map((t, i) => (
            <li key={i} className="mg-h4-row flex items-center gap-[10px]" style={{ minHeight: 33, fontSize: 13.5, color: color.text }}>
              <span aria-hidden className="grid shrink-0 place-items-center" style={{ width: 16, height: 16, borderRadius: 999, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}`, fontSize: 10.5, fontWeight: 600, color: color.label }}>
                {i + 1}
              </span>
              {t}
            </li>
          ))}
        </ol>
      </section>
      {goals.length > 0 && (
        <section aria-labelledby="home-goals" data-home-goals>
          <Sec id="home-goals" link="Skills" onLink={() => setPage('skills')}>
            Pick a goal
          </Sec>
          <div className="mg-h4-list">
            {goals.map((g) => (
              <RailRow key={g.title} tall label={`${g.title}. ${g.skills} skills, ${hoursWord(g.minutes)}.`} onClick={() => focusAsk(g.title)} right={<Chev />}>
                <span className="block truncate" style={{ fontWeight: 520 }}>
                  {g.title}
                </span>
                <span className="block" style={{ fontSize: T.small, fontWeight: 400, color: color.label }}>
                  {g.skills} skills · {hoursWord(g.minutes)}
                </span>
              </RailRow>
            ))}
          </div>
        </section>
      )}
    </>
  )
  return (
    <Frame
      data="v4-first"
      main={
        <>
          {notice}
          <Hello title={greeting} now={now} lede="Pick a plan, paste a video, or ask for anything you want to learn." />
          <div style={{ marginTop: 8 }}>{ask}</div>
          {starters.length > 0 && (
            <section aria-labelledby="home-start" data-home-start>
              <Sec id="home-start" link="All plans" onLink={() => setSection('library')}>
                Start here
              </Sec>
              <div className="grid grid-cols-1 gap-x-[16px] gap-y-[20px] @min-[640px]/pane:grid-cols-3">
                {starters.slice(0, 3).map((p) => (
                  <StarterCard key={p.id} p={p} />
                ))}
              </div>
            </section>
          )}
          {lessons.length > 0 && (
            <section aria-labelledby="home-short" data-home-short>
              <Sec id="home-short" link="Library" onLink={() => setSection('library')}>
                Or one short lesson
              </Sec>
              <LessonRows rows={lessons} onOpen={(id) => focusAsk(lessons.find((l) => l.id === id)?.goal)} />
            </section>
          )}
          <section aria-labelledby="home-own" data-home-own>
            <Sec id="home-own">Make your own</Sec>
            <div className="grid grid-cols-1 gap-[12px] @min-[640px]/pane:grid-cols-2">
              <Way icon={<ListVideo aria-hidden size={18} strokeWidth={1.8} />} title="From a playlist" line="Paste a YouTube playlist link" onClick={() => focusAsk('')} />
              <Way icon={<Sprout aria-hidden size={18} strokeWidth={1.8} />} title="From a goal" line="Say what you want to make" onClick={() => focusAsk('')} />
            </div>
          </section>
        </>
      }
      rail={rail}
    />
  )
}

