/**
 * Feature: library. Home v4, the page (Adrian's ui-next mock, `home` and `home-empty`, after the Nov 24 trim pass and
 * the demo pass: no greeting, no date, no empty boxes).
 *
 * A main column and, when it has something to show, a 316 px rail with one hairline between them; under ~960 px of pane
 * the rail drops under the main column. With nothing for the rail (a light learner) there is no rail and no hairline:
 * one centered column. Rows and hairlines, no tiles; the only card is Continue (or Start here on the first run).
 *
 *   main    ask · Continue · Plans · Up next · Recently passed
 *   rail    This week (bars + practiced, steps passed, skills mastered) · Goal · Skills · Keep fresh, each only when
 *           it has something in it
 *   first   the one thing left to set up · ask · Start here (one lesson, one Start lesson) · Or try a short one ·
 *           How a lesson works. One column, no rail.
 */
import { Flag, RotateCcw } from 'lucide-react'
import type { ReactNode } from 'react'
import { openOnboarding } from '../../../core/surfaces'
import { color, fill } from '../../../core/theme'
import { QuietButton } from '../../../core/ui/buttons'
import { setPage } from '../../shell/store'
import { openBrowsePlans, openPlan } from '../../plans/store'
import { showSkill as openSkill } from '../../skills/go'
import { Pane } from '../layout'
import { openDetail, setSection } from '../store'
import { Bar, Check, Chev, Hollow, RailRow, RowBtn, Sec, T, Tag, WeekChart, hair, muted, rowCss } from './bits'
import { agoLabel, hoursMinutes, leftLabel, railParts, whenLabel, type FirstRow, type HomeModel } from './data'
import { focusAsk } from './Top'

/** Pane width where the rail sits beside the main column (a static class string so Tailwind sees it). */
const TWO = '@min-[960px]/pane:grid-cols-[minmax(0,1fr)_316px] @min-[960px]/pane:gap-x-[40px]'
const RAIL = 'rail border-t pt-[8px] @min-[960px]/pane:border-t-0 @min-[960px]/pane:border-l @min-[960px]/pane:pt-0 @min-[960px]/pane:pl-[32px]'
const PAD = 'mx-auto w-full px-[40px] @max-[760px]/pane:px-[24px]'

/** No rail: one centered column (720 wide), so a light learner's page has no empty third and no stray hairline. */
function Frame({ main, rail, data }: { main: ReactNode; rail?: ReactNode; data: string }): ReactNode {
  return (
    <Pane data-home={data} className="flex flex-1 flex-col overflow-y-auto" style={{ color: color.text, scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
      <style>{rowCss}</style>
      {rail ? (
        <div className={`${PAD} max-w-[1120px]`} style={{ paddingTop: 44, paddingBottom: 60 }}>
          <div className={`grid grid-cols-1 items-start gap-y-[32px] ${TWO}`}>
            <div data-home-main className="min-w-0">
              {main}
            </div>
            <aside data-home-rail aria-label="Your week" className={RAIL} style={{ borderColor: hair, paddingBottom: 48, minWidth: 0 }}>
              {rail}
            </aside>
          </div>
        </div>
      ) : (
        <div className={`${PAD} max-w-[800px]`} style={{ paddingTop: 44, paddingBottom: 60 }}>
          <div data-home-main className="min-w-0">
            {main}
          </div>
        </div>
      )}
    </Pane>
  )
}

// ---- the main column ------------------------------------------------------------------------------------------------

function Plans({ m }: { m: HomeModel }): ReactNode {
  if (!m.plans.length) return null
  return (
    <section aria-labelledby="home-plans" data-home-plans>
      <Sec id="home-plans" link="Browse plans" onLink={openBrowsePlans}>
        Plans
      </Sec>
      <div className="mg-h4-list">
        {m.plans.map((p) => (
          <RowBtn key={p.id} cols="minmax(0,1.25fr) 130px minmax(0,1fr) 14px" label={`${p.title}, ${p.done} of ${p.total}${p.next ? `, next ${p.next}` : ''}`} onClick={() => openPlan(p.id)} data={{ 'data-plan': p.id }}>
            <b className="line-clamp-2" title={p.title} style={{ fontWeight: 550, color: color.text, lineHeight: 1.3, padding: '6px 0' }}>
              {p.title}
            </b>
            <span className="flex items-center gap-[10px]">
              <Bar fraction={p.done / p.total} width={72} />
              <span style={muted}>
                {p.done} of {p.total}
              </span>
            </span>
            <span title={p.next} style={{ ...muted, whiteSpace: 'normal', lineHeight: 1.35, margin: '6px 0', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {p.next ? `Next · ${p.next}` : ''}
            </span>
            <Chev />
          </RowBtn>
        ))}
      </div>
    </section>
  )
}

/** Lesson rows: the title (two lines at most), the skill it grows, its size. No thumbnail: covers belong to the one card. */
function LessonRows({ rows, onOpen }: { rows: Array<{ id: string; title: string; skill?: string; meta: string }>; onOpen: (id: string) => void }): ReactNode {
  return (
    <div className="mg-h4-list">
      {rows.map((r) => (
        <RowBtn key={r.id} cols={r.skill ? 'minmax(0,1fr) auto minmax(204px,max-content) 14px' : 'minmax(0,1fr) minmax(204px,max-content) 14px'} minH={50} label={`${r.title}. ${r.meta}.`} onClick={() => onOpen(r.id)} data={{ 'data-lesson': r.id }}>
          <b className="line-clamp-2" title={r.title} style={{ fontWeight: 550, color: color.text, lineHeight: 1.3, padding: '6px 0' }}>
            {r.title}
          </b>
          {r.skill && (
            <span className="min-w-0">
              <Tag>{r.skill}</Tag>
            </span>
          )}
          <span className="truncate text-right" title={r.meta} style={muted}>
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
      <LessonRows
        rows={m.next}
        onOpen={(id) => {
          const r = m.next.find((n) => n.id === id)
          if (r?.goal) focusAsk(r.goal)
          else openDetail(id)
        }}
      />
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
                    <b className="truncate" title={p.step} style={{ fontWeight: 550, color: color.text }}>
                      {p.step}
                    </b>
                  </span>
                </td>
                {showSkill && (
                  <td style={{ ...c, overflow: 'hidden' }}>
                    {p.skill && (
                      <Tag label={`Open ${p.skill} in Skills`} onClick={() => openSkill({ label: p.skill })}>
                        {p.skill}
                      </Tag>
                    )}
                  </td>
                )}
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
  // Only a week with a bar in it: never seven flat bars and a row of zeros (MIC-69).
  if (!railParts(m).week) return null
  const unit = m.stats.minutes !== undefined ? 'min' : 'steps'
  // A zero is left out, like practiced with no minutes: the rail never shows a row of zeros.
  const stats: Array<[string, Array<[string, string]>]> = []
  if (m.stats.minutes) stats.push(['practiced', hoursMinutes(m.stats.minutes)])
  if (m.stats.steps) stats.push(['steps passed', [[String(m.stats.steps), '']]])
  if (m.stats.mastered) stats.push(['skills mastered', [[String(m.stats.mastered), '']]])
  return (
    <section aria-labelledby="home-week" data-home-week>
      <Sec id="home-week" first link="Progress" onLink={() => setPage('progress')}>
        This week
      </Sec>
      <WeekChart bars={m.week} unit={unit} />
      {stats.length > 0 && (
        <div className="flex" style={{ marginTop: 10 }}>
          {stats.map(([label, parts], i) => (
            <Stat key={label} first={i === 0} parts={parts} label={label} />
          ))}
        </div>
      )}
    </section>
  )
}

function Goal({ m, first }: { m: HomeModel; first?: boolean }): ReactNode {
  const g = m.goal
  if (!g || !g.total) return null
  return (
    <section aria-labelledby="home-goal" data-home-goal>
      <Sec id="home-goal" first={first}>
        Goal
      </Sec>
      <div className="flex items-center gap-[8px]" style={{ fontSize: 14 }}>
        <Flag aria-hidden size={15} strokeWidth={1.8} style={{ color: color.label }} />
        <b className="line-clamp-2" title={g.title} style={{ fontWeight: 560, color: color.text, lineHeight: 1.3 }}>
          {g.title}
        </b>
      </div>
      <div style={{ margin: '11px 0 8px' }}>
        <Bar fraction={g.done / g.total} label={`${g.done} of ${g.total} ${g.unit ?? 'skills'}`} />
      </div>
      <div className="flex justify-between" style={muted}>
        <span>
          {g.done} of {g.total} {g.unit ?? 'skills'}
        </span>
        {g.minutesLeft !== undefined && <span>{leftLabel(g.minutesLeft)}</span>}
      </div>
    </section>
  )
}

function Skills({ m, first }: { m: HomeModel; first?: boolean }): ReactNode {
  if (!m.skills.length) return null
  return (
    <section aria-labelledby="home-skills" data-home-skills>
      <Sec id="home-skills" first={first} link={`${m.skillsDone} of ${m.skillsTotal} mastered`} onLink={() => setPage('skills')}>
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

function Fresh({ m, now, first }: { m: HomeModel; now: number; first?: boolean }): ReactNode {
  if (!m.fresh.length) return null
  return (
    <section aria-labelledby="home-fresh" data-home-review>
      <Sec id="home-fresh" first={first} link="Progress" onLink={() => setPage('progress')}>
        Keep fresh
      </Sec>
      <div className="mg-h4-list">
        {m.fresh.slice(0, 3).map((f) => (
          <RailRow key={f.label} icon={<RotateCcw aria-hidden size={15} strokeWidth={1.8} className="shrink-0" style={{ color: color.label }} />} right={<span style={muted}>{f.at !== undefined ? agoLabel(f.at, now) : 'first review'}</span>}>
            {f.label}
          </RailRow>
        ))}
      </div>
    </section>
  )
}

// ---- the pages --------------------------------------------------------------------------------------------------------

export function HomePage({ m, now, ask, cont, notice }: { m: HomeModel; now: number; ask: ReactNode; cont: ReactNode; notice?: ReactNode }): ReactNode {
  const r = railParts(m)
  const rail = r.any ? (
    <>
      <Week m={m} />
      <Goal m={m} first={!r.week} />
      <Skills m={m} first={!r.week && !r.goal} />
      <Fresh m={m} now={now} first={!r.week && !r.goal && !r.skills} />
    </>
  ) : undefined
  return (
    <Frame
      data="v4"
      main={
        <>
          {notice}
          {ask}
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

/** The one thing left to set up, above the ask: where it stands, and one quiet button that opens setup. */
export function SetupNote({ label, line }: { label: string; line: string }): ReactNode {
  return (
    <div data-home-setup className="flex items-center gap-[10px]" style={{ paddingBottom: 14, fontSize: T.meta, color: color.label }}>
      <Hollow />
      <span className="min-w-0 flex-1 truncate" title={line}>
        {line}
      </span>
      <QuietButton label={label} onClick={() => void openOnboarding()} />
    </div>
  )
}

const HOW = ['miyagi shows one step.', 'You do it in the real app.', 'It checks your work, then the next.']

/**
 * A new learner's Home: one lesson to start (`featured`, the card with the page's one primary), a few short ones that
 * start on a click, and how a lesson works. One column, nothing empty.
 */
export function FirstRunPage({ ask, featured, lessons, onLesson, setup, notice }: { ask: ReactNode; featured: ReactNode; lessons: FirstRow[]; onLesson: (r: FirstRow) => void; setup?: ReactNode; notice?: ReactNode }): ReactNode {
  return (
    <Frame
      data="v4-first"
      main={
        <>
          {notice}
          {setup}
          {ask}
          <section aria-label="Start here" data-home-start style={{ marginTop: 14 }}>
            {featured}
          </section>
          {lessons.length > 0 && (
            <section aria-labelledby="home-short" data-home-short>
              <Sec id="home-short" link="Library" onLink={() => setSection('library')}>
                Or try a short one
              </Sec>
              <LessonRows
                rows={lessons}
                onOpen={(id) => {
                  const r = lessons.find((l) => l.id === id)
                  if (r) onLesson(r)
                }}
              />
            </section>
          )}
          <section aria-labelledby="home-how" data-home-how>
            <Sec id="home-how">How a lesson works</Sec>
            <ol className="mg-h4-list m-0 list-none p-0">
              {HOW.map((t, i) => (
                <li key={i} className="mg-h4-row flex items-center gap-[10px]" style={{ minHeight: 33, fontSize: 13.5, color: color.text }}>
                  <span aria-hidden className="grid shrink-0 place-items-center" style={{ width: 16, height: 16, borderRadius: 999, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}`, fontSize: 10.5, fontWeight: 600, color: color.label }}>
                    {i + 1}
                  </span>
                  {t}
                </li>
              ))}
            </ol>
          </section>
        </>
      }
    />
  )
}
