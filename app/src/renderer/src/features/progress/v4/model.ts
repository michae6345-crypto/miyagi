/**
 * Feature: progress, the v4 Progress page (Adrian's ui-next mock `progress` / `progress-empty`, Nov 24 trim pass).
 * Pure data: no React, no bridge, so test/progressV4.test.ts runs it in node.
 *
 * Reads the additive fields the UI-V4 data contract adds to the engine's `progress` answer, tolerantly, until the
 * contract lands in shared/contracts (then these readers switch to its types; the names below are the ones asked for):
 *
 *   activity[].minutes    minutes practiced that local day (next to reps); absent = minutes not tracked yet
 *   recent[] | passed[]   the last passed steps: {at, step|title, skill?, lesson?}, newest first
 *   totals                {minutes?, steps?, lessons?} over all time
 *   bon                   {passed}: the buddy's passed-step count (engine side, not localStorage)
 *   goal                  {title, mastered, total, minutesLeft?, eta?}
 *   plans[]               {id?, title, done, total}
 *   milestones[]          {label, at}: dated, engine-made (the Nov 24 trim pass took them off the page; kept here)
 *   skills[].skills[]     per skill `reps` and `need` (steps to master) for "Closest to mastered"
 *   review.minutes        how long the Keep fresh review takes ("4 min" over the rail's Keep fresh)
 *
 * Nothing is made up: a part that is missing stays empty and the page leaves it out (or shows steps where minutes
 * aren't known). Times are epoch seconds, epoch ms or ISO text; here they are epoch ms.
 */

export const DAY_MS = 86_400_000
const DAY_RE = /^\d{4}-\d{2}-\d{2}$/

const rec = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {})
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const str = (v: unknown, max = 160): string => (typeof v === 'string' ? v.replace(/\s+/g, ' ').trim().slice(0, max) : '')
const count = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 && v < 1e7 ? Math.floor(v) : undefined)

/** A skill or step label as plain text: the engine writes code names in markdown backticks ("Training with `fit`"). */
export const plain = (s: string): string => s.replace(/`+/g, '').replace(/\s+/g, ' ').trim()

/** Epoch seconds, epoch ms or ISO text, as ms. A bare date is that day's local noon. */
export function toMs(v: unknown): number | undefined {
  if (typeof v === 'number' && Number.isFinite(v) && v > 0) return v > 1e12 ? v : v * 1000
  if (typeof v !== 'string' || !v.trim()) return undefined
  const t = DAY_RE.test(v) ? new Date(`${v}T12:00:00`).getTime() : Date.parse(v)
  return Number.isFinite(t) ? t : undefined
}

export const dayKey = (t: number): string => {
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export const dayStart = (t: number): number => {
  const d = new Date(t)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}
/** Local midnight of the Monday on or before t. */
export const mondayOf = (t: number): number => {
  const d = new Date(dayStart(t))
  const back = (d.getDay() + 6) % 7
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - back).getTime()
}
export const addDays = (t: number, n: number): number => {
  const d = new Date(t)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n).getTime()
}

export type Day = { minutes?: number; steps: number }
export type Pass = {
  at: number
  step: string
  skill?: string
  lesson?: string
}
export type Goal = {
  title: string
  mastered: number
  total: number
  minutesLeft?: number
  eta?: number
}
export type Plan = { id?: string; title: string; done: number; total: number }
export type Milestone = { label: string; at: number }
export type SkillSteps = {
  label: string
  done: number
  need: number
  mastered: boolean
}

export type V4 = {
  /** Per local day ("YYYY-MM-DD"). */
  days: Map<string, Day>
  /** Some day carries minutes: the charts are in minutes. Otherwise they count passed steps. */
  minutesKnown: boolean
  passes: Pass[]
  totals: { minutes?: number; steps?: number; lessons?: number }
  bonPassed?: number
  /** Minutes the Keep fresh review takes, when the engine says. */
  reviewMinutes?: number
  goal?: Goal
  plans: Plan[]
  milestones: Milestone[]
  skills: SkillSteps[]
}

export const EMPTY_V4: V4 = {
  days: new Map(),
  minutesKnown: false,
  passes: [],
  totals: {},
  plans: [],
  milestones: [],
  skills: []
}

/** The additive v4 fields of a `progress` payload. Anything malformed is dropped, never filled in. */
export function readV4(raw: unknown): V4 {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return EMPTY_V4
  const m = rec(raw)
  const days = new Map<string, Day>()
  let minutesKnown = false
  for (const x of list(m.activity)) {
    const r = rec(x)
    const date = typeof r.date === 'string' && DAY_RE.test(r.date) ? r.date : ''
    if (!date) continue
    const have = days.get(date) ?? { steps: 0 }
    have.steps += count(r.reps) ?? count(r.steps) ?? 0
    const min = count(r.minutes)
    if (min !== undefined) {
      minutesKnown = true
      have.minutes = (have.minutes ?? 0) + min
    }
    days.set(date, have)
  }
  const passes: Pass[] = []
  for (const x of list(Array.isArray(m.recent) ? m.recent : m.passed)) {
    const r = rec(x)
    const at = toMs(r.at ?? r.passedAt)
    const step = plain(str(r.step) || str(r.title) || str(r.stepTitle))
    if (!at || !step) continue
    passes.push({
      at,
      step,
      skill: plain(str(r.skill, 60)) || undefined,
      lesson: plain(str(r.lesson, 120) || str(r.lessonTitle, 120)) || undefined
    })
  }
  passes.sort((a, b) => b.at - a.at)
  const t = rec(m.totals)
  const totals = {
    minutes: count(t.minutes),
    steps: count(t.steps),
    lessons: count(t.lessons)
  }
  const bonPassed = count(rec(m.bon).passed)
  const reviewMinutes = count(rec(m.review).minutes) || undefined
  const g = rec(m.goal)
  const gTitle = plain(str(g.title, 120))
  const gTotal = count(g.total)
  const goal: Goal | undefined =
    gTitle && gTotal
      ? {
          title: gTitle,
          mastered: Math.min(count(g.mastered) ?? 0, gTotal),
          total: gTotal,
          minutesLeft: count(g.minutesLeft),
          eta: toMs(g.eta)
        }
      : undefined
  const plans: Plan[] = []
  for (const x of list(m.plans)) {
    const p = rec(x)
    const title = plain(str(p.title, 120))
    const total = count(p.total)
    if (!title || !total) continue
    plans.push({
      id: str(p.id, 80) || undefined,
      title,
      done: Math.min(count(p.done) ?? 0, total),
      total
    })
  }
  const milestones: Milestone[] = []
  for (const x of list(m.milestones)) {
    const r = rec(x)
    const label = str(r.label, 80)
    const at = toMs(r.at)
    if (label && at) milestones.push({ label, at })
  }
  milestones.sort((a, b) => b.at - a.at)
  const skills: SkillSteps[] = []
  for (const tr of list(m.skills)) {
    for (const x of list(rec(tr).skills ?? rec(tr).items)) {
      const s = rec(x)
      const label = plain(str(s.label, 80))
      const need = count(s.need)
      if (!label || !need) continue
      skills.push({
        label,
        done: Math.min(count(s.reps) ?? 0, need),
        need,
        mastered: s.state === 'mastered'
      })
    }
  }
  return {
    days,
    minutesKnown,
    passes,
    totals,
    bonPassed,
    reviewMinutes,
    goal,
    plans,
    milestones,
    skills
  }
}

// ---- charts -----------------------------------------------------------------------------------------------------

export type Bar = {
  key: string
  label: string
  value: number
  now: boolean
  future: boolean
}

const value = (d: Day | undefined, minutes: boolean): number => (d ? (minutes ? (d.minutes ?? 0) : d.steps) : 0)
const WEEKDAY = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** This week, Monday to Sunday: minutes (or steps) a day. Today is `now`; later days are `future`. */
export function weekBars(v: V4, now: number): Bar[] {
  const mon = mondayOf(now)
  const today = dayKey(now)
  return WEEKDAY.map((label, i) => {
    const t = addDays(mon, i)
    const key = dayKey(t)
    return {
      key,
      label,
      value: value(v.days.get(key), v.minutesKnown),
      now: key === today,
      future: t > now
    }
  })
}

const monthDay = (t: number): string => new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

/** The last 12 weeks, oldest first: minutes (or steps) a week. Labels on weeks 1, 5 and 9 and "Now" on the last. */
export function weeks12(v: V4, now: number): Bar[] {
  const thisMon = mondayOf(now)
  const out: Bar[] = []
  for (let w = 11; w >= 0; w--) {
    const start = addDays(thisMon, -7 * w)
    let sum = 0
    for (let d = 0; d < 7; d++) sum += value(v.days.get(dayKey(addDays(start, d))), v.minutesKnown)
    const i = 11 - w
    out.push({
      key: dayKey(start),
      label: i === 11 ? 'Now' : i % 4 === 0 ? monthDay(start) : '',
      value: sum,
      now: i === 11,
      future: false
    })
  }
  return out
}

/** A round guide line under the chart's top: 30 min a day, 2 hr a week, or 5 / 10 / 20 steps. */
export function guide(max: number, minutes: boolean, weekly: boolean): { at: number; label: string } | undefined {
  if (max <= 0) return minutes && !weekly ? { at: 30, label: '30 min' } : undefined
  const steps = minutes ? (weekly ? [30, 60, 120, 240, 480, 900] : [10, 15, 30, 60, 90, 120]) : [2, 5, 10, 20, 50, 100, 200]
  let at = steps[0]
  for (const s of steps) if (s <= max * 0.95) at = s
  return {
    at,
    label: minutes ? (at >= 60 && at % 60 === 0 ? `${at / 60} hr` : `${at} min`) : `${at} ${at === 1 ? 'step' : 'steps'}`
  }
}

// ---- numbers ----------------------------------------------------------------------------------------------------

/** 108 → {h: 1, m: 48}. */
export const hm = (min: number): { h: number; m: number } => ({
  h: Math.floor(min / 60),
  m: Math.round(min % 60)
})

export type WeekNums = { minutes?: number; steps: number }
export function weekNums(v: V4, now: number): WeekNums {
  const bars = weekBars(v, now)
  const steps = bars.reduce((n, b) => n + (v.days.get(b.key)?.steps ?? 0), 0)
  const minutes = v.minutesKnown ? bars.reduce((n, b) => n + (v.days.get(b.key)?.minutes ?? 0), 0) : undefined
  return { minutes, steps }
}
/** All-time numbers: the engine's totals when sent, otherwise summed from what was sent (never guessed). */
export function allNums(v: V4, lessonsFinished: number): { minutes?: number; steps: number; lessons: number } {
  let steps = 0
  let minutes = 0
  for (const d of v.days.values()) {
    steps += d.steps
    minutes += d.minutes ?? 0
  }
  return {
    minutes: v.totals.minutes ?? (v.minutesKnown ? minutes : undefined),
    steps: v.totals.steps ?? steps,
    lessons: v.totals.lessons ?? lessonsFinished
  }
}

/** "Today, 4:12 PM" / "Yesterday" / "Wednesday" (this past week) / "Nov 16". */
export function whenLabel(at: number, now: number): string {
  const days = Math.round((dayStart(now) - dayStart(at)) / DAY_MS)
  if (days <= 0) return `Today, ${new Date(at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
  if (days === 1) return 'Yesterday'
  if (days < 7) return new Date(at).toLocaleDateString('en-US', { weekday: 'long' })
  return monthDay(at)
}
/** "Today" / "Yesterday" / "Nov 16" (a track's last practice). */
export function dayLabel(at: number, now: number): string {
  const days = Math.round((dayStart(now) - dayStart(at)) / DAY_MS)
  return days <= 0 ? 'Today' : days === 1 ? 'Yesterday' : monthDay(at)
}
/** "12 days ago". */
export function agoLabel(at: number, now: number): string {
  const days = Math.max(0, Math.round((dayStart(now) - dayStart(at)) / DAY_MS))
  return days === 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`
}
/** The right side of a Keep fresh row: when it was last practiced, else when it is due, else "due" (never blank). */
export function freshLabel(r: { lastAt?: number; when?: string; dueAt?: number }, now: number): string {
  if (r.lastAt) return agoLabel(r.lastAt, now)
  if (r.when) return r.when
  if (r.dueAt && dayStart(r.dueAt) > dayStart(now)) {
    const days = Math.round((dayStart(r.dueAt) - dayStart(now)) / DAY_MS)
    return days === 1 ? 'due tomorrow' : `due in ${days} days`
  }
  return 'due'
}
/** "about 3 hours, around Dec 4" from the goal's minutes left and date. */
export function goalLine(g: Goal): string | undefined {
  const parts: string[] = []
  if (g.minutesLeft !== undefined) {
    const h = Math.round(g.minutesLeft / 60)
    parts.push(g.minutesLeft < 60 ? `about ${g.minutesLeft} min` : `about ${h} ${h === 1 ? 'hour' : 'hours'}`)
  }
  if (g.eta) parts.push(`around ${monthDay(g.eta)}`)
  return parts.length ? parts.join(', ') : undefined
}

/** Practicing skills nearest to mastered, by how far along (needs the engine's per-skill `need`). */
export function closest(v: V4, n = 3): SkillSteps[] {
  return v.skills
    .filter((s) => !s.mastered && s.done > 0 && s.done < s.need)
    .sort((a, b) => b.done / b.need - a.done / a.need || b.done - a.done)
    .slice(0, n)
}

// ---- first run --------------------------------------------------------------------------------------------------

/** A short lesson to start (UI-V4 catalog: a plan's first lesson). `goal` is the text `learn` builds it from. */
export type Starter = {
  id: string
  title: string
  grows: string
  tool: string
  steps: number
  minutes: number
  goal: string
  cover: 'code' | 'sheet' | 'plot' | '3d' | 'cad'
}
export type StarterPlan = {
  id: string
  title: string
  tool: string
  lessons: number
  minutes: number
  ends: string
  cover: Starter['cover']
}
export type GoalPick = {
  title: string
  skills: number
  hours: number
  query: string
}

/**
 * Local placeholders from Adrian's catalog (docs/ui-next/catalog, Nov 22) until the UI-V4 contract carries the catalog.
 * Titles, tools and sizes are the catalog's own.
 */
export const STARTERS: readonly Starter[] = [
  {
    id: 'intro-python',
    title: 'Run your first Python file',
    grows: 'Running a script',
    tool: 'VS Code',
    steps: 4,
    minutes: 10,
    cover: 'code',
    goal: 'Teach a complete beginner to create hello.py in VS Code, print two lines and run it from the terminal with python3.'
  },
  {
    id: 'intro-sheets',
    title: 'Start a sign-up sheet',
    grows: 'Cells and ranges',
    tool: 'Google Sheets',
    steps: 5,
    minutes: 15,
    cover: 'sheet',
    goal: 'Teach a complete beginner Google Sheets. Make a new spreadsheet named Club sign-ups, add headers for name, grade, event and paid, and enter ten rows.'
  },
  {
    id: 'plotting',
    title: 'Your first line plot',
    grows: 'Line plots',
    tool: 'Jupyter',
    steps: 5,
    minutes: 15,
    cover: 'plot',
    goal: 'Teach matplotlib in Jupyter. Import matplotlib.pyplot as plt, make a figure and axes with plt.subplots and draw a week of temperatures as a line.'
  },
  {
    id: 'intro-blender',
    title: 'Move around the 3D viewport',
    grows: 'Viewport',
    tool: 'Blender',
    steps: 5,
    minutes: 10,
    cover: '3d',
    goal: 'Teach a complete beginner the Blender viewport. Orbit, pan, zoom, the front, side and top views, and frame the selected object.'
  }
]
export const STARTER_PLANS: readonly StarterPlan[] = [
  {
    id: 'intro-python',
    title: 'Intro to Python',
    tool: 'VS Code',
    lessons: 10,
    minutes: 180,
    ends: 'a number guessing game',
    cover: 'code'
  },
  {
    id: 'intro-blender',
    title: 'Intro to Blender',
    tool: 'Blender',
    lessons: 10,
    minutes: 150,
    ends: 'a desk lamp, modeled and rendered',
    cover: '3d'
  },
  {
    id: 'intro-cad',
    title: 'Intro to CAD',
    tool: 'FreeCAD',
    lessons: 10,
    minutes: 150,
    ends: 'a phone stand you could print',
    cover: 'cad'
  }
]
export const GOAL_PICKS: readonly GoalPick[] = [
  {
    title: 'Fit sin(x) with a network',
    skills: 13,
    hours: 6,
    query: 'Fit sin(x) with a small neural network'
  },
  {
    title: 'A sales report from a CSV',
    skills: 9,
    hours: 4,
    query: 'Make a sales report from a CSV with pandas'
  },
  {
    title: 'A budget in Google Sheets',
    skills: 8,
    hours: 3,
    query: 'Build a monthly budget in Google Sheets'
  },
  {
    title: 'A 3D-printable part',
    skills: 11,
    hours: 5,
    query: 'Model a 3D-printable part in FreeCAD'
  }
]
/** "about 3 hr" / "about 2.5 hr" / "about 45 min". */
export function aboutHr(min: number): string {
  // Non-breaking spaces: "about 2.5 hr" never splits over two lines.
  if (min < 60) return `about\u00a0${min}\u00a0min`
  const h = Math.round((min / 60) * 2) / 2
  return `about\u00a0${h}\u00a0hr`
}
