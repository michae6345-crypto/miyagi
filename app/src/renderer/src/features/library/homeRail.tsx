/**
 * Feature: library. Home's side column (wide windows): the week at a glance, quick actions and a tip. In a narrow
 * window it drops under the lists. Only real data: the week is the engine's per-day activity, the counts are the
 * engine's finished lessons and mastered skills; with no activity yet the card invites the first step instead of
 * showing zeros. Neutral ink on the track: nothing here is a status, so no green and no pastel.
 *
 *   WeekCard      seven bars (Monday first), the steps passed this week, lessons finished, skills mastered
 *   QuickActions  New lesson, Paste a link (reads the clipboard once, on click), Browse lessons, Open skills
 *   TipCard       one tip a day (homeTips.ts), its keycap from the platform's keys
 */
import { Link2, LibraryBig, SquarePen, Waypoints, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../core/theme'
import { enter, staggerDelay } from '../../core/ui/motion'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { weekStrip, type DayCell } from '../dashboard/model'
import type { DashData } from '../dashboard/types'
import { CARD, Row } from '../shell/ui'
import { setPage } from '../shell/store'
import { setAskText } from './homeModel'
import { tipFor } from './homeTips'
import { SectionLabel } from './layout'
import { Rise } from './motion'

const LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const BAR_MAX = 44

/** Puts the caret in Home's ask field (one place to type: the page's own input). */
export function focusAsk(): void {
  document.querySelector<HTMLInputElement>('[data-home-ask] input')?.focus()
}

/** A bar's height: the day's steps against the week's busiest day, never under 4 (a quiet day still has a stub). */
const barH = (c: DayCell, max: number): number => (c.state === 'future' ? 4 : Math.max(4, Math.round((c.reps / Math.max(1, max)) * BAR_MAX)))

function Bars({ days }: { days: DayCell[] }): ReactNode {
  const max = Math.max(...days.map((d) => d.reps), 1)
  return (
    <ol aria-label="Steps passed each day this week" className="m-0 flex list-none items-end justify-between p-0" style={{ gap: 6, height: BAR_MAX + 22 }}>
      {days.map((d, i) => (
        <li key={d.date} aria-label={`${DAY_NAMES[i]}: ${d.reps} ${d.reps === 1 ? 'step' : 'steps'}${d.today ? ', today' : ''}`} className="flex flex-1 flex-col items-center justify-end" style={{ gap: 6 }}>
          <motion.span
            aria-hidden
            initial={{ opacity: 0, scaleY: 0.2 }}
            animate={{ opacity: 1, scaleY: 1 }}
            transition={enter(staggerDelay(i))}
            className="block w-full"
            style={{ height: barH(d, max), maxWidth: 28, transformOrigin: 'bottom', borderRadius: radius2.keycap, background: d.reps > 0 ? color.text : d.state === 'future' ? fill.hairline : fill.track }}
          />
          <span aria-hidden style={{ fontSize: type2.micro, lineHeight: '12px', color: d.today ? color.text : color.faint, fontWeight: d.today ? 600 : 400 }}>
            {LETTERS[i]}
          </span>
        </li>
      ))}
    </ol>
  )
}

function Stat({ n, label }: { n: number; label: string }): ReactNode {
  return (
    <div className="flex min-w-0 flex-1 flex-col" style={{ gap: 2 }}>
      <span className="font-semibold" style={{ fontSize: type2.lg, lineHeight: '24px', color: color.text, fontVariantNumeric: 'tabular-nums' }}>
        {n}
      </span>
      <span className="truncate" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
        {label}
      </span>
    </div>
  )
}

/** This week: the bars and three counts. Nothing tracked yet = one inviting line, no zeros. */
export function WeekCard({ data, now, goal }: { data?: DashData; now: number; goal: number }): ReactNode {
  const days = weekStrip(data?.activity ?? null, now, goal)
  const steps = days.reduce((n, d) => n + d.reps, 0)
  const finished = data?.completed.length ?? 0
  const mastered = (data?.tracks ?? []).reduce((n, t) => n + t.skills.filter((s) => s.state === 'mastered').length, 0)
  return (
    <section aria-labelledby="home-week" data-home-week className="flex flex-col" style={{ ...CARD, padding: 20, gap: 16 }}>
      <SectionLabel id="home-week" style={{ marginBottom: 0 }}>
        This week
      </SectionLabel>
      <Bars days={days} />
      {steps > 0 ? (
        <div className="flex" style={{ gap: 12, paddingTop: 12, borderTop: `1px solid ${fill.hairline}` }}>
          <Stat n={steps} label={steps === 1 ? 'step' : 'steps'} />
          <Stat n={finished} label={finished === 1 ? 'lesson done' : 'lessons done'} />
          <Stat n={mastered} label={mastered === 1 ? 'mastered' : 'mastered'} />
        </div>
      ) : (
        <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
          Pass a step and your week starts here.
        </p>
      )}
    </section>
  )
}

function Action({ icon: Icon, label, onClick, data }: { icon: LucideIcon; label: string; onClick: () => void; data: string }): ReactNode {
  return (
    <Row onClick={onClick} label={label} data={{ 'data-home-action': data }}>
      <Icon aria-hidden size={16} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.label }} />
      <span className="relative min-w-0 flex-1 truncate" style={{ fontSize: type2.md, color: color.text }}>
        {label}
      </span>
    </Row>
  )
}

/** "Paste a link": the clipboard is read on this click only; if it is empty or blocked the field just takes focus. */
async function pasteLink(): Promise<void> {
  try {
    const text = (await navigator.clipboard.readText()).trim()
    if (text) setAskText(text)
  } catch {
    /* no clipboard permission: the field still takes focus, and paste works there */
  }
  focusAsk()
}

export function QuickActions(): ReactNode {
  return (
    <section aria-label="Quick actions" data-home-actions className="flex flex-col" style={{ ...CARD, padding: 6 }}>
      <Action icon={SquarePen} label="New lesson" onClick={focusAsk} data="new" />
      <Action icon={Link2} label="Paste a link" onClick={() => void pasteLink()} data="link" />
      <Action icon={LibraryBig} label="Browse lessons" onClick={() => setPage('lessons')} data="lessons" />
      <Action icon={Waypoints} label="Open skills" onClick={() => setPage('skills')} data="skills" />
    </section>
  )
}

export function TipCard({ now }: { now: number }): ReactNode {
  const tip = tipFor(now)
  return (
    <section aria-label="Tip" data-home-tip className="flex items-start" style={{ gap: 12, padding: '4px 8px' }}>
      <span aria-hidden className="flex shrink-0" style={{ paddingTop: 2 }}>
        <MiyagiMark size={16} />
      </span>
      <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '22px', color: color.label }}>
        {tip.before}
        {tip.key && (
          <span className="inline-flex align-middle">
            <Keycap k={tip.key} size="sm" />
          </span>
        )}
        {tip.after}
      </p>
    </section>
  )
}

/** The whole side column; each card rises in after the page's main column. */
export function Rail({ data, now, goal }: { data?: DashData; now: number; goal: number }): ReactNode {
  return (
    <aside data-home-rail aria-label="At a glance" className="flex min-w-0 flex-col" style={{ gap: 16 }}>
      <Rise i={2}>
        <WeekCard data={data} now={now} goal={goal} />
      </Rise>
      <Rise i={3}>
        <QuickActions />
      </Rise>
      <Rise i={4} className="@max-[940px]/pane:hidden">
        <TipCard now={now} />
      </Rise>
    </aside>
  )
}
