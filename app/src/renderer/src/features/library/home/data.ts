/**
 * Feature: library. Home v4 (Adrian's ui-next mock, Nov 23-24: `home` and `home-empty`), the page's view model.
 *
 * Pure functions from what the app already has (the engine's progress as DashData, the saved lessons) plus the v4 data
 * the contract adds (activity minutes, plans from the catalog, step passes, the goal). Until the "contract: ui-v4" commit
 * lands those come in as `V4Extra`, a local typed placeholder: every part with nothing to show is left out, so the page
 * never shows rows of zeros (README rule: "A page for a new learner shows things to start ... never rows of zeros").
 *
 * Wire-later list (the contract's fields this placeholder stands in for): week minutes, plans in progress, step passes
 * with their skill, the goal. Everything else is wired now.
 */
import type { LessonTool, LibraryItem } from '../../../../../../../shared/contracts/events'
import { DAY_MS, dayKey, mondayOf } from '../../dashboard/model'
import type { DashData } from '../../dashboard/types'

// ---- the view model ------------------------------------------------------------------------------------------------

/** A cover drawing for a lesson or plan (home/bits.tsx Cover): picked from the tool, never a photo. */
export type CoverKind = 'code' | 'nb' | 'plot' | 'table' | 'term' | 'net' | 'mug' | 'cad'

export type PlanRow = { id: string; title: string; done: number; total: number; next?: string }
export type NextRow = { id: string; title: string; skill?: string; meta: string; cover: CoverKind }
/** A passed step (contract), or until then a finished lesson (`lesson: true`). */
export type PassRow = { key: string; at: number; step: string; skill?: string; lesson?: boolean }
export type WeekBar = { label: string; name: string; value: number; today: boolean; future: boolean }
export type WeekStats = { minutes?: number; steps: number; mastered: number }
export type GoalView = { title: string; done: number; total: number; minutesLeft?: number }
export type SkillBar = { label: string; done: number; total: number }
export type FreshRow = { label: string; at?: number }

/** The contract's v4 additions, as the page needs them (placeholder until shared/contracts/UI-V4.md lands). */
export type V4Extra = {
  /** Minutes practiced per local day, "YYYY-MM-DD" → minutes. Absent: the bars count steps. */
  minutes?: Record<string, number>
  plans?: PlanRow[]
  passes?: PassRow[]
  goal?: GoalView
  /** Plans that are a good first start (catalog), for the first-run page. */
  starters?: StarterPlan[]
  shortLessons?: ShortLesson[]
  goals?: GoalPick[]
}
export type StarterPlan = { id: string; title: string; tool: string; lessons: number; minutes: number; ends?: string; cover: CoverKind }
export type ShortLesson = { id: string; title: string; skill?: string; meta: string; cover: CoverKind; goal: string }
export type GoalPick = { title: string; skills: number; minutes: number }

export type HomeModel = {
  plans: PlanRow[]
  next: NextRow[]
  passes: PassRow[]
  week: WeekBar[]
  stats: WeekStats
  goal?: GoalView
  skills: SkillBar[]
  skillsDone: number
  skillsTotal: number
  fresh: FreshRow[]
}

// ---- small helpers -------------------------------------------------------------------------------------------------

const LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const TOOL_WORD: Record<LessonTool, string> = { vscode: 'VS Code', jupyter: 'Jupyter', terminal: 'Terminal', excel: 'Excel' }
const TOOL_COVER: Record<LessonTool, CoverKind> = { vscode: 'code', jupyter: 'nb', terminal: 'term', excel: 'table' }

/** "Good morning" / "Good afternoon" / "Good evening", with the first name when there is one. */
export function greeting(now: number, name?: string): string {
  const h = new Date(now).getHours()
  const part = h < 5 ? 'Good evening' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
  const first = name?.trim().split(/\s+/)[0]
  return first ? `${part}, ${first}` : part
}

/** "Sunday, November 22". */
export const longDate = (now: number): string => new Date(now).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })

/** "1 h 48 min" split for the stat ("1", "h", "48", "min"). */
export function hoursMinutes(min: number): Array<[string, string]> {
  const m = Math.max(0, Math.round(min))
  const h = Math.floor(m / 60)
  const r = m % 60
  if (!h) return [[String(r), 'min']]
  return r ? [[String(h), 'h'], [String(r), 'min']] : [[String(h), 'h']]
}

/** "about 3 hours left", "about 40 min left". */
export function leftLabel(min: number): string {
  if (min < 55) return `about ${Math.max(5, Math.round(min / 5) * 5)} min left`
  const h = Math.round(min / 60)
  return `about ${h} ${h === 1 ? 'hour' : 'hours'} left`
}

/** "about 3 hr", "about 2.5 hr", "about 40 min" (a plan's size, as the catalog cards say it). */
export function sizeLabel(min: number): string {
  if (min < 55) return `about ${Math.round(min / 5) * 5} min`
  const h = Math.round((min / 60) * 2) / 2
  return `about ${h} hr`
}

/** "Today, 4:12 PM", "Yesterday", "Wednesday", "Nov 3". */
export function whenLabel(at: number, now: number): string {
  const d0 = new Date(now)
  d0.setHours(0, 0, 0, 0)
  const days = Math.floor((d0.getTime() - new Date(at).setHours(0, 0, 0, 0)) / DAY_MS)
  if (days <= 0) return `Today, ${new Date(at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
  if (days === 1) return 'Yesterday'
  if (days < 7) return new Date(at).toLocaleDateString('en-US', { weekday: 'long' })
  return new Date(at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** "12 days ago", "today", "yesterday". */
export function agoLabel(at: number, now: number): string {
  const days = Math.floor((now - at) / DAY_MS)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}

/** "Jupyter · 6 steps · 15 min". */
export function lessonMeta(i: Pick<LibraryItem, 'tools' | 'steps' | 'estMinutes'>): string {
  return [i.tools.map((t) => TOOL_WORD[t] ?? t).join(', '), `${i.steps} ${i.steps === 1 ? 'step' : 'steps'}`, i.estMinutes ? `${i.estMinutes} min` : ''].filter(Boolean).join(' · ')
}

export const coverFor = (tools: LessonTool[]): CoverKind => TOOL_COVER[tools[0]] ?? 'code'

// ---- the parts -----------------------------------------------------------------------------------------------------

/** Monday to Sunday of this week: minutes when the contract has them, else steps passed. */
export function weekBars(data: DashData | undefined, extra: V4Extra, now: number): WeekBar[] {
  const mon = mondayOf(now)
  const today = dayKey(now)
  const reps = new Map((data?.activity ?? []).map((a) => [a.date, a.reps]))
  return LETTERS.map((label, i) => {
    const key = dayKey(mon + i * DAY_MS + DAY_MS / 2)
    const value = extra.minutes ? (extra.minutes[key] ?? 0) : (reps.get(key) ?? 0)
    return { label, name: DAY_NAMES[i], value, today: key === today, future: key > today }
  })
}

export function weekStats(data: DashData | undefined, extra: V4Extra, now: number): WeekStats {
  const mon = mondayOf(now)
  const inWeek = (k: string): boolean => k >= dayKey(mon) && k <= dayKey(now)
  const steps = (data?.activity ?? []).filter((a) => inWeek(a.date)).reduce((n, a) => n + a.reps, 0)
  const mastered = (data?.tracks ?? []).flatMap((t) => t.skills).filter((s) => s.state === 'mastered' && s.masteredAt !== undefined && s.masteredAt >= mon).length
  const minutes = extra.minutes ? Object.entries(extra.minutes).filter(([k]) => inWeek(k)).reduce((n, [, m]) => n + m, 0) : undefined
  return { minutes, steps, mastered }
}

/** One bar per track: mastered of total, the track's own name. */
export function skillBars(data: DashData | undefined): { rows: SkillBar[]; done: number; total: number } {
  const rows = (data?.tracks ?? []).filter((t) => t.total > 0).map((t) => ({ label: t.track, done: t.mastered, total: t.total }))
  return { rows, done: rows.reduce((n, r) => n + r.done, 0), total: rows.reduce((n, r) => n + r.total, 0) }
}

/** Skills due for a short review, oldest practice first. */
export function freshRows(data: DashData | undefined, now: number): FreshRow[] {
  return (data?.review?.items ?? [])
    .filter((r) => (r.dueAt === undefined ? !!r.when : r.dueAt <= now))
    .map((r) => ({ label: r.label.split(String.fromCharCode(96)).join(''), at: r.lastAt }))
    .sort((a, b) => (a.at ?? 0) - (b.at ?? 0))
}

/** Saved lessons ready to start, never one that's on Continue or already finished. Its tag is the first skill it teaches. */
export function nextRows(items: LibraryItem[], data: DashData | undefined, skip: Set<string>, done: Set<string>, max = 4): NextRow[] {
  const names = new Map((data?.tracks ?? []).flatMap((t) => t.skills.map((s) => [s.id, s.label] as const)))
  return items
    .filter((i) => i.ready && !i.progress && !skip.has(i.id) && !done.has(i.id))
    .slice(0, max)
    .map((i) => ({ id: i.id, title: i.title, skill: i.teaches?.map((t) => names.get(t)).find(Boolean), meta: lessonMeta(i), cover: coverFor(i.tools) }))
}

/** Step passes from the contract; until then the finished lessons, newest first. */
export function passRows(data: DashData | undefined, extra: V4Extra, max = 5): PassRow[] {
  if (extra.passes?.length) return [...extra.passes].sort((a, b) => b.at - a.at).slice(0, max)
  return (data?.completed ?? [])
    .filter((c) => c.finishedAt !== undefined)
    .sort((a, b) => (b.finishedAt ?? 0) - (a.finishedAt ?? 0))
    .slice(0, max)
    .map((c) => ({ key: c.lessonId, at: c.finishedAt!, step: c.title, lesson: true }))
}

/** A learner with nothing started, nothing finished and no skill touched: the first-run page. */
export function isFirstRun(data: DashData | undefined, items: LibraryItem[], extra: V4Extra): boolean {
  if (extra.plans?.length || extra.passes?.length) return false
  if (data?.completed.length || data?.inProgress.length) return false
  if ((data?.tracks ?? []).some((t) => t.skills.some((s) => s.state !== 'not_started'))) return false
  if ((data?.activity ?? []).some((a) => a.reps > 0)) return false
  return !items.some((i) => i.progress)
}

export function buildHome(i: { data?: DashData; items: LibraryItem[]; extra: V4Extra; now: number; skip: Set<string>; done: Set<string> }): HomeModel {
  const sk = skillBars(i.data)
  return {
    plans: (i.extra.plans ?? []).filter((p) => p.done < p.total),
    next: nextRows(i.items, i.data, i.skip, i.done),
    passes: passRows(i.data, i.extra),
    week: weekBars(i.data, i.extra, i.now),
    stats: weekStats(i.data, i.extra, i.now),
    goal: i.extra.goal,
    skills: sk.rows,
    skillsDone: sk.done,
    skillsTotal: sk.total,
    fresh: freshRows(i.data, i.now)
  }
}
