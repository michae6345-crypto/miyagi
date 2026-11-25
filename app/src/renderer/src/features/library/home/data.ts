/**
 * Feature: library. Home v4 (Adrian's ui-next mock, Nov 23-24: `home` and `home-empty`), the page's view model.
 *
 * Pure functions from what the app already has (the engine's progress as DashData, the saved lessons) plus the ui-v4
 * contract (shared/contracts/UI-V4.md): `activity` (the week's bars and numbers, Recently passed) and `plans` (Plans,
 * Up next from the plans, the goal). `fromContract` turns those into `V4Parts`, what the page needs; an engine that
 * doesn't list activity.get / plans.list leaves them out. Every part with nothing to show is left out, so the page never
 * shows rows of zeros (README rule: "A page for a new learner shows things to start ... never rows of zeros").
 */
import type { Activity, LessonTool, LibraryItem, PlanState } from '../../../../../../../shared/contracts/events'
import { DAY_MS, dayKey, mondayOf } from '../../dashboard/model'
import type { DashData } from '../../dashboard/types'
import type { SkillGraph } from '../../skills/model'
import { skillLabel } from '../../plans/catalog'

// ---- the view model ------------------------------------------------------------------------------------------------

/** A cover drawing for a lesson or plan (home/bits.tsx Cover): picked from the tool, never a photo. */
export type CoverKind = 'code' | 'nb' | 'plot' | 'table' | 'term' | 'net' | 'mug' | 'cad'

export type PlanRow = { id: string; title: string; done: number; total: number; next?: string }
/** goal: a plan lesson not built yet (its learn text); opening it puts the text in the ask field. */
export type NextRow = { id: string; title: string; skill?: string; meta: string; cover: CoverKind; goal?: string }
/** A passed step (activity.recent), or with an engine before ui-v4 a finished lesson (`lesson: true`). */
export type PassRow = { key: string; at: number; step: string; skill?: string; lesson?: boolean }
export type WeekBar = { label: string; name: string; value: number; today: boolean; future: boolean }
export type WeekStats = { minutes?: number; steps: number; mastered: number }
/** unit: what done/total count ("skills", "lessons"). */
export type GoalView = { title: string; done: number; total: number; unit?: string; minutesLeft?: number }
export type SkillBar = { label: string; done: number; total: number }
export type FreshRow = { label: string; at?: number }

/** One local day of activity.days. */
export type DayValue = { date: string; minutes: number; steps: number }

/** The ui-v4 contract's parts, as the page needs them (fromContract). Absent: the engine didn't send it. */
export type V4Parts = {
  /** The last days of activity.days, oldest first (the bars use the last 7). */
  days?: DayValue[]
  /** activity.minutesTracked: false = the bars and numbers count steps, never "0 min". */
  minutesTracked?: boolean
  /** activity.week. */
  week?: { minutes?: number; steps: number; mastered: number }
  plans?: PlanRow[]
  /** The plans' coming lessons (after the one each plan is on). */
  next?: NextRow[]
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
const TOOL_COVER: Record<string, CoverKind> = { vscode: 'code', jupyter: 'nb', terminal: 'term', excel: 'table', sheets: 'table', rstudio: 'plot', blender: 'mug', freecad: 'cad', fusion: 'cad', onshape: 'cad' }


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

export const coverFor = (tools: readonly string[]): CoverKind => coverForTool(tools[0])
/** A lesson's or plan's cover from its tool id (LessonTool or a catalog PlanToolId). */
export const coverForTool = (tool?: string): CoverKind => (tool && TOOL_COVER[tool]) || 'code'

// ---- the parts -----------------------------------------------------------------------------------------------------

/** The last 7 days of activity (minutes, or steps when minutes aren't tracked); without it Monday to Sunday of this
 *  week from the progress's steps passed. */
export function weekBars(data: DashData | undefined, extra: V4Parts, now: number): WeekBar[] {
  if (extra.days?.length) {
    const last = extra.days.slice(-7)
    return last.map((d, i) => {
      const wd = (new Date(`${d.date}T12:00:00`).getDay() + 6) % 7
      return { label: LETTERS[wd], name: DAY_NAMES[wd], value: extra.minutesTracked ? d.minutes : d.steps, today: i === last.length - 1, future: false }
    })
  }
  const mon = mondayOf(now)
  const today = dayKey(now)
  const reps = new Map((data?.activity ?? []).map((a) => [a.date, a.reps]))
  return LETTERS.map((label, i) => {
    const key = dayKey(mon + i * DAY_MS + DAY_MS / 2)
    const value = reps.get(key) ?? 0
    return { label, name: DAY_NAMES[i], value, today: key === today, future: key > today }
  })
}

export function weekStats(data: DashData | undefined, extra: V4Parts, now: number): WeekStats {
  if (extra.week) return { minutes: extra.minutesTracked ? extra.week.minutes : undefined, steps: extra.week.steps, mastered: extra.week.mastered }
  const mon = mondayOf(now)
  const inWeek = (k: string): boolean => k >= dayKey(mon) && k <= dayKey(now)
  const steps = (data?.activity ?? []).filter((a) => inWeek(a.date)).reduce((n, a) => n + a.reps, 0)
  const mastered = (data?.tracks ?? []).flatMap((t) => t.skills).filter((s) => s.state === 'mastered' && s.masteredAt !== undefined && s.masteredAt >= mon).length
  return { minutes: undefined, steps, mastered }
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

/**
 * Saved lessons ready to start, never one that's on Continue or already finished. Its tag is the first skill it teaches:
 * its own `teaches`, else the skillIds of the plan lesson that built it (PlanLesson.libraryId / lessonId), named by the
 * progress graph or the catalog, the same rule as the Library's Grows column (QA R4-05).
 */
export function nextRows(items: LibraryItem[], data: DashData | undefined, skip: Set<string>, done: Set<string>, max = 4, plans?: PlanState[]): NextRow[] {
  const names = new Map((data?.tracks ?? []).flatMap((t) => t.skills.map((s) => [s.id, s.label] as const)))
  const planSkills = new Map<string, string[]>()
  for (const p of plans ?? [])
    for (const l of p.lessons) {
      if (!l.skillIds?.length) continue
      if (l.libraryId) planSkills.set(l.libraryId, l.skillIds)
      if (l.lessonId && !planSkills.has(l.lessonId)) planSkills.set(l.lessonId, l.skillIds)
    }
  const skillOf = (i: LibraryItem): string | undefined =>
    (i.teaches?.length ? i.teaches : (planSkills.get(i.id) ?? [])).map((t) => names.get(t) ?? skillLabel(t)).find(Boolean)
  return items
    .filter((i) => i.ready && !i.progress && !skip.has(i.id) && !done.has(i.id))
    .slice(0, max)
    .map((i) => ({ id: i.id, title: i.title, skill: skillOf(i), meta: lessonMeta(i), cover: coverFor(i.tools) }))
}

/** Step passes from activity.recent; with an engine before ui-v4 the finished lessons, newest first. */
export function passRows(data: DashData | undefined, extra: V4Parts, max = 5): PassRow[] {
  if (extra.passes?.length) return [...extra.passes].sort((a, b) => b.at - a.at).slice(0, max)
  return (data?.completed ?? [])
    .filter((c) => c.finishedAt !== undefined)
    .sort((a, b) => (b.finishedAt ?? 0) - (a.finishedAt ?? 0))
    .slice(0, max)
    .map((c) => ({ key: c.lessonId, at: c.finishedAt!, step: c.title, lesson: true }))
}

/** A learner with nothing started, nothing finished and no skill touched: the first-run page. */
export function isFirstRun(data: DashData | undefined, items: LibraryItem[], extra: V4Parts): boolean {
  if (extra.plans?.length || extra.passes?.length || extra.week?.steps) return false
  if (data?.completed.length || data?.inProgress.length) return false
  if ((data?.tracks ?? []).some((t) => t.skills.some((s) => s.state !== 'not_started'))) return false
  if ((data?.activity ?? []).some((a) => a.reps > 0)) return false
  return !items.some((i) => i.progress)
}

/** A first-run row: a saved lesson ready on this Mac (`saved`, starts with library.start) or a suggestion (its goal). */
export type FirstRow = ShortLesson & { saved?: boolean }

/** The first-run page's short lessons: saved lessons ready to start (no model calls), then suggestions. */
export function firstLessons(items: LibraryItem[], done: Set<string>, picks: ShortLesson[], max = 3): FirstRow[] {
  const saved: FirstRow[] = items
    .filter((i) => i.ready && !i.progress && !done.has(i.id))
    .map((i) => ({ id: i.id, title: i.title, meta: lessonMeta(i), cover: coverFor(i.tools), goal: '', saved: true }))
  return [...saved, ...picks].slice(0, max)
}

/** Which rail parts have something to show. Nothing in any: no rail at all, one centered column. */
export function railParts(m: HomeModel): { week: boolean; goal: boolean; skills: boolean; fresh: boolean; any: boolean } {
  const p = { week: m.week.some((b) => b.value > 0), goal: !!m.goal?.total, skills: m.skills.length > 0, fresh: m.fresh.length > 0 }
  return { ...p, any: p.week || p.goal || p.skills || p.fresh }
}

// ---- the contract ----------------------------------------------------------------------------------------------------

const ms = (iso?: string | null): number | undefined => {
  const t = iso ? Date.parse(iso) : NaN
  return Number.isFinite(t) ? t : undefined
}
const lowerFirst = (t: string): string => t.charAt(0).toLowerCase() + t.slice(1)

/** A plan's coming lessons (state next or todo, after the one it is on), as Up next rows. */
function planNext(p: PlanState, names: Map<string, string>): NextRow[] {
  const on = p.nextIndex ?? -1
  return p.lessons
    .filter((l) => (l.state === 'next' || l.state === 'todo') && l.index !== on)
    .slice(0, 1)
    .map((l) => ({
      id: `${p.id}:${l.index}`,
      title: l.title,
      skill: l.skillIds?.map((s) => names.get(s)).find(Boolean),
      meta: [p.tool?.label, l.stepCount ? `${l.stepCount} steps` : '', l.minutes ? `${l.minutes} min` : ''].filter(Boolean).join(' · '),
      cover: coverForTool(p.tool?.id),
      goal: l.goal ?? l.title
    }))
}

/**
 * The ui-v4 contract's activity and plans, as the page's parts. `names`: skill id → label (the progress graph), for the
 * Up next tag. The goal is the project at the end of the plan the learner passed a step in last (else the first plan).
 */
export function fromContract(i: { activity?: Activity; plans?: PlanState[]; names?: Map<string, string> }): V4Parts {
  const out: V4Parts = {}
  const a = i.activity
  if (a) {
    out.minutesTracked = !!a.minutesTracked
    out.days = (a.days ?? []).map((d) => ({ date: d.date, minutes: d.minutes ?? 0, steps: d.steps ?? 0 }))
    out.week = { minutes: a.minutesTracked ? (a.week?.minutes ?? undefined) : undefined, steps: a.week?.stepsPassed ?? 0, mastered: a.week?.skillsMastered ?? 0 }
    out.passes = (a.recent ?? []).flatMap((r) => {
      const at = ms(r.at)
      return at === undefined ? [] : [{ key: r.key, at, step: r.stepTitle, skill: r.skills?.[0] }]
    })
  }
  const plans = (i.plans ?? []).filter((p) => p.total > 0 && p.done < p.total)
  if (i.plans) {
    out.plans = plans.map((p) => {
      const at = p.nextIndex === null || p.nextIndex === undefined ? undefined : p.lessons.find((l) => l.index === p.nextIndex)
      return { id: p.id, title: p.title, done: p.done, total: p.total, next: at?.title }
    })
    const names = i.names ?? new Map<string, string>()
    // One coming lesson per plan, in the plans' order.
    out.next = plans.flatMap((p) => planNext(p, names))
    const lastPlan = a?.recent?.find((r) => r.planId)?.planId
    const g = plans.find((p) => p.id === lastPlan && p.project) ?? plans.find((p) => p.project)
    if (g?.project) out.goal = { title: g.project.title, done: g.done, total: g.total, unit: 'lessons', minutesLeft: g.minutesLeft ?? undefined }
  }
  return out
}

/**
 * skills/planGoal.ts usePlanGoal's rule: the plan's goal (fromContract) stands in for the skill graph's goal only when
 * that one is inferred (the learner never picked one), and only when it counts something.
 */
export function planGoalFor(g: SkillGraph | undefined, goal: GoalView | undefined): GoalView | undefined {
  return g?.goal?.inferred && goal?.total ? goal : undefined
}

/** "Ends with a desk lamp, modeled and rendered" (a catalog plan's project, for Start here). */
export const endsWith = (project: string): string => `Ends with ${lowerFirst(project)}`

export function buildHome(i: { data?: DashData; items: LibraryItem[]; extra: V4Parts; now: number; skip: Set<string>; done: Set<string>; plans?: PlanState[] }): HomeModel {
  const sk = skillBars(i.data)
  return {
    plans: (i.extra.plans ?? []).filter((p) => p.done < p.total),
    next: [...nextRows(i.items, i.data, i.skip, i.done, 4, i.plans),...(i.extra.next ?? [])].filter((r, k, all) => all.findIndex((o) => o.title === r.title) === k).slice(0, 4),
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
