/**
 * Feature: dashboard. Everything the dashboard computes on the app side, pure (no store, no React):
 *
 *   node states    mastered / practicing from the engine; not_started splits into available (every prerequisite
 *                  mastered) and locked. A due review never changes a node's state, it only adds a dot.
 *   layout         a track's nodes in columns by prerequisite depth (track order when there are no edges).
 *   today, week    reps today against the daily goal; Monday-first strip; a 12-week grid.
 *   rhythm         weeks whose active days reach the weekly goal (Khan style). Rest tokens: one per counted week, at
 *                  most two, spent on a short week. Paused weeks count for nothing either way. Never a loss.
 *   milestones     first step, first skill, first full track, 10 / 50 / 100 / 500 reps, first review, 4 / 12 weeks.
 *
 * One rep = one step passed by the learner's own work (the engine counts them; "Do it for me" and skips are 0).
 */
import { skillKey, type ActivityDay, type DashData, type DashSkill, type DashTrack, type ReviewEntry } from './types'

export type NodeState = 'mastered' | 'practicing' | 'available' | 'locked'

export const DAY_MS = 86_400_000
export const DEFAULT_DAILY = 3
export const DEFAULT_WEEKLY = 3
export const MAX_TOKENS = 2

// ---- days -------------------------------------------------------------------------------------------------------

const pad = (n: number): string => String(n).padStart(2, '0')
/** "YYYY-MM-DD" of a moment, in the learner's own time zone. */
export const dayKey = (t: number): string => {
  const d = new Date(t)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
/** Local midnight of a day key (or of a moment). */
export const dayStart = (t: number): number => {
  const d = new Date(t)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}
const keyToMs = (k: string): number => new Date(`${k}T12:00:00`).getTime()
/** Local midnight of the Monday of the week holding `t`. */
export const mondayOf = (t: number): number => {
  const d = new Date(dayStart(t))
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return d.getTime()
}
/** `n` calendar days after `t` (DST safe: by date, not by 24 h). */
export const addDays = (t: number, n: number): number => {
  const d = new Date(t)
  d.setDate(d.getDate() + n)
  return d.getTime()
}

/** "Nov 19". */
export const shortDay = (t: number): string => new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
/** "Today", "Yesterday", "3 days ago", else "Nov 19". */
export function relDay(t: number, now: number): string {
  const d = Math.round((dayStart(now) - dayStart(t)) / DAY_MS)
  if (d === 0) return 'Today'
  if (d === 1) return 'Yesterday'
  if (d > 1 && d < 7) return `${d} days ago`
  if (d === -1) return 'Tomorrow'
  if (d < -1 && d > -7) return `In ${-d} days`
  return shortDay(t)
}

/** relDay inside a sentence: "due today", "practiced 3 days ago", but a date keeps its capital ("due Nov 19"). */
export function relInLine(t: number, now: number): string {
  const s = relDay(t, now)
  return /^[A-Z][a-z]{2} \d+$/.test(s) ? s : s.toLowerCase()
}

// ---- goals ------------------------------------------------------------------------------------------------------

/** The learner's own choices on this Mac (prefs) win over the engine's settings, then the defaults. */
export type Goals = { daily: number; weekly: number; pause?: { from: number; until: number } }

export function goalsFor(data: DashData | undefined, local: { daily?: number; weekly?: number; pause?: { from: number; until: number } | null }): Goals {
  const s = data?.settings ?? {}
  const enginePause = s.pausedUntil ? { from: s.pausedFrom ?? 0, until: s.pausedUntil } : undefined
  const pause = local.pause === null ? undefined : (local.pause ?? enginePause)
  return { daily: local.daily ?? s.dailyGoal ?? DEFAULT_DAILY, weekly: local.weekly ?? s.weeklyGoal ?? DEFAULT_WEEKLY, pause }
}

// ---- skill graph ------------------------------------------------------------------------------------------------

export function prereqs(t: DashTrack, id: string): string[] {
  return t.edges.filter((e) => e.to === id).map((e) => e.from)
}

export function nodeStates(t: DashTrack): Record<string, NodeState> {
  const byId = new Map(t.skills.map((s) => [s.id, s]))
  const out: Record<string, NodeState> = {}
  for (const s of t.skills) {
    if (s.state === 'mastered') out[s.id] = 'mastered'
    else if (s.state === 'practicing') out[s.id] = 'practicing'
    else out[s.id] = prereqs(t, s.id).every((p) => byId.get(p)?.state === 'mastered') ? 'available' : 'locked'
  }
  return out
}

/** Review entries by skill id and by label (the old shape names skills by label only). */
export function reviewIndex(items: ReviewEntry[]): Map<string, ReviewEntry> {
  const m = new Map<string, ReviewEntry>()
  for (const r of items) {
    if (r.skillId) m.set(r.skillId, r)
    m.set(skillKey(r.label), r)
  }
  return m
}

export function reviewFor(idx: Map<string, ReviewEntry>, s: DashSkill): ReviewEntry | undefined {
  return idx.get(s.id) ?? idx.get(skillKey(s.label))
}

/** Due now: its dueAt has come, or (old shape, no dates) it is among the first `due` items. */
export function dueItems(review: DashData['review'], now: number): ReviewEntry[] {
  if (!review) return []
  const dated = review.items.some((i) => i.dueAt !== undefined)
  if (dated) return review.items.filter((i) => i.dueAt !== undefined && i.dueAt <= now).sort((a, b) => (a.dueAt ?? 0) - (b.dueAt ?? 0))
  return review.items.slice(0, Math.min(review.due ?? 0, review.items.length))
}
export function laterItems(review: DashData['review'], now: number): ReviewEntry[] {
  if (!review) return []
  const due = new Set(dueItems(review, now))
  return review.items.filter((i) => !due.has(i)).sort((a, b) => (a.dueAt ?? Infinity) - (b.dueAt ?? Infinity))
}

export type Placed = { id: string; col: number; row: number }
export type TrackLayout = { nodes: Placed[]; cols: number; rows: number; crossCol: boolean }

/**
 * Columns by prerequisite depth (the longest chain of edges into a node), rows in track order within a column.
 * No edges: one column per node in track order (the track is a line), so nothing is drawn that the engine didn't say.
 * Cross links get a column of their own on the left.
 */
export function layoutTrack(t: DashTrack): TrackLayout {
  const ids = t.skills.map((s) => s.id)
  const depth: Record<string, number> = Object.fromEntries(ids.map((id, i) => [id, t.edges.length ? 0 : i]))
  if (t.edges.length) {
    // Longest path by relaxation; capped at n passes so a cycle can't spin.
    for (let pass = 0; pass < ids.length; pass++) {
      let moved = false
      for (const e of t.edges) {
        if (depth[e.to] < depth[e.from] + 1 && depth[e.from] + 1 < ids.length) {
          depth[e.to] = depth[e.from] + 1
          moved = true
        }
      }
      if (!moved) break
    }
  }
  const crossCol = t.cross.length > 0
  const shift = crossCol ? 1 : 0
  const rowsIn: Record<number, number> = {}
  const nodes: Placed[] = ids.map((id) => {
    const col = depth[id] + shift
    const row = rowsIn[col] ?? 0
    rowsIn[col] = row + 1
    return { id, col, row }
  })
  const cols = Math.max(1, ...nodes.map((n) => n.col + 1))
  const rows = Math.max(1, t.cross.length, ...Object.values(rowsIn))
  return { nodes, cols, rows, crossCol }
}

/** "3 of 8 skills mastered in pandas." */
export const trackHeadline = (t: DashTrack): string => `${t.mastered} of ${t.total} ${t.total === 1 ? 'skill' : 'skills'} mastered in ${t.track}.`

// ---- activity ---------------------------------------------------------------------------------------------------

export type DayCell = { date: string; reps: number; state: 'future' | 'empty' | 'active' | 'closed'; today: boolean }

export function activityMap(a: ActivityDay[] | null): Map<string, ActivityDay> {
  return new Map((a ?? []).map((d) => [d.date, d]))
}

function cell(map: Map<string, ActivityDay>, t: number, now: number, goal: number): DayCell {
  const date = dayKey(t)
  const reps = map.get(date)?.reps ?? 0
  const today = date === dayKey(now)
  const state: DayCell['state'] = dayStart(t) > dayStart(now) ? 'future' : reps >= goal ? 'closed' : reps > 0 ? 'active' : 'empty'
  return { date, reps, state, today }
}

/** This week, Monday first. */
export function weekStrip(a: ActivityDay[] | null, now: number, goal: number): DayCell[] {
  const map = activityMap(a)
  const mon = mondayOf(now)
  return Array.from({ length: 7 }, (_, i) => cell(map, addDays(mon, i), now, goal))
}

/** The last 12 weeks, oldest first; each column Monday to Sunday. */
export function weekGrid(a: ActivityDay[] | null, now: number, goal: number, weeks = 12): DayCell[][] {
  const map = activityMap(a)
  const mon = mondayOf(now)
  return Array.from({ length: weeks }, (_, w) => {
    const start = addDays(mon, (w - weeks + 1) * 7)
    return Array.from({ length: 7 }, (_, d) => cell(map, addDays(start, d), now, goal))
  })
}

export type Totals = { reps: number | null; today: number; week: number; assisted: number; hints: number }

export function totals(data: DashData | undefined, now: number): Totals {
  const a = data?.activity
  if (!a) {
    const perSkill = data?.tracks.flatMap((t) => t.skills.map((s) => s.reps)).filter((r): r is number => r !== undefined) ?? []
    return { reps: perSkill.length ? perSkill.reduce((x, y) => x + y, 0) : null, today: 0, week: 0, assisted: 0, hints: 0 }
  }
  const today = dayKey(now)
  const mon = dayKey(mondayOf(now))
  let reps = 0
  let week = 0
  let assisted = 0
  let hints = 0
  for (const d of a) {
    reps += d.reps
    assisted += d.assisted
    hints += d.hints
    if (d.date >= mon && d.date <= today) week += d.reps
  }
  return { reps, today: a.find((d) => d.date === today)?.reps ?? 0, week, assisted, hints }
}

// ---- rhythm -----------------------------------------------------------------------------------------------------

export type Rhythm = {
  /** Counted weeks in a row (this week included once it counts). */
  weeks: number
  tokens: number
  /** Active days so far this week. */
  thisWeek: number
  thisWeekCounts: boolean
  best: number
  /** When the rhythm is 0: the length it paused at (for "Your rhythm paused at 6 weeks."). */
  pausedAt: number
  /** A pause the learner chose is on now. */
  paused: boolean
  /** Monday (ms) of the week each rhythm milestone was reached. */
  reached: Record<number, number>
  /** Weeks a rest token covered (Monday ms), for the 12-week grid's tooltip. */
  rested: number[]
}

const RHYTHM_MARKS = [4, 12]

export function rhythm(a: ActivityDay[] | null, now: number, goals: Goals): Rhythm {
  const map = activityMap(a)
  const activeDays = (mon: number, upTo = 7): number => {
    let n = 0
    for (let i = 0; i < upTo; i++) if ((map.get(dayKey(addDays(mon, i)))?.reps ?? 0) > 0) n++
    return n
  }
  const curMon = mondayOf(now)
  const paused = !!goals.pause && goals.pause.from <= now && now < goals.pause.until
  const pausedWeek = (mon: number): boolean => !!goals.pause && mon < goals.pause.until && addDays(mon, 7) > goals.pause.from
  const out: Rhythm = { weeks: 0, tokens: 0, thisWeek: 0, thisWeekCounts: false, best: 0, pausedAt: 0, paused, reached: {}, rested: [] }
  const first = (a ?? []).find((d) => d.reps > 0)
  if (!first) return out
  const count = (mon: number): void => {
    out.weeks++
    out.tokens = Math.min(MAX_TOKENS, out.tokens + 1)
    out.best = Math.max(out.best, out.weeks)
    for (const m of RHYTHM_MARKS) if (out.weeks === m && out.reached[m] === undefined) out.reached[m] = mon
  }
  for (let mon = mondayOf(keyToMs(first.date)); mon < curMon; mon = addDays(mon, 7)) {
    if (pausedWeek(mon)) continue
    if (activeDays(mon) >= goals.weekly) count(mon)
    else if (out.weeks > 0 && out.tokens > 0) {
      out.tokens--
      out.rested.push(mon)
    } else if (out.weeks > 0) {
      out.pausedAt = out.weeks
      out.weeks = 0
    }
  }
  out.thisWeek = activeDays(curMon, Math.min(7, Math.round((dayStart(now) - curMon) / DAY_MS) + 1))
  if (out.thisWeek >= goals.weekly) {
    out.thisWeekCounts = true
    count(curMon)
  }
  if (out.weeks > 0) out.pausedAt = 0
  return out
}

// ---- milestones -------------------------------------------------------------------------------------------------

export type Milestone = { id: string; label: string; at?: number; done: boolean; toGo?: string }

const REP_MARKS = [10, 50, 100, 500]

export function milestones(data: DashData | undefined, r: Rhythm, now: number): Milestone[] {
  const list: Milestone[] = []
  // Step and rep milestones need per-day activity; without it they're left out rather than shown as not reached.
  const tracked = !!data?.activity
  const days = (data?.activity ?? []).filter((d) => d.reps > 0)
  const firstStep = days[0]
  if (tracked) list.push({ id: 'first-step', label: 'First step passed', done: !!firstStep, at: firstStep ? keyToMs(firstStep.date) : undefined })

  const skills = data?.tracks.flatMap((t) => t.skills) ?? []
  const masteredTimes = skills.filter((s) => s.state === 'mastered').map((s) => s.masteredAt)
  const firstSkill = masteredTimes.filter((x): x is number => x !== undefined).sort((x, y) => x - y)[0]
  list.push({ id: 'first-skill', label: 'First skill mastered', done: masteredTimes.length > 0, at: firstSkill })

  const full = (data?.tracks ?? [])
    .filter((t) => t.skills.length > 0 && t.skills.every((s) => s.state === 'mastered') && t.total === t.skills.length)
    .map((t) => ({ t, at: Math.max(0, ...t.skills.map((s) => s.masteredAt ?? 0)) || undefined }))
    .sort((x, y) => (x.at ?? Infinity) - (y.at ?? Infinity))[0]
  list.push({ id: 'first-track', label: full ? `Full track: ${full.t.track}` : 'First full track', done: !!full, at: full?.at })

  let sum = 0
  const crossed: Record<number, number> = {}
  for (const d of days) {
    const before = sum
    sum += d.reps
    for (const m of REP_MARKS) if (before < m && sum >= m) crossed[m] = keyToMs(d.date)
  }
  const total = data?.activity ? sum : null
  for (const m of tracked ? REP_MARKS : []) {
    const done = total !== null && total >= m
    list.push({ id: `reps-${m}`, label: `${m} reps`, done, at: crossed[m], toGo: !done && total !== null ? `${m - total} to go` : undefined })
  }

  const passedReviews = (data?.review?.items ?? []).filter((i) => i.lastResult === 'passed')
  const firstReview = passedReviews.map((i) => i.lastAt).filter((x): x is number => x !== undefined).sort((x, y) => x - y)[0]
  list.push({ id: 'first-review', label: 'First review passed', done: passedReviews.length > 0, at: firstReview })

  for (const m of tracked ? RHYTHM_MARKS : []) {
    const at = r.reached[m]
    const done = at !== undefined || r.best >= m
    list.push({ id: `rhythm-${m}`, label: `${m} week rhythm`, done, at: at !== undefined ? Math.min(addDays(at, 6), now) : undefined, toGo: !done && r.weeks > 0 ? `${m - r.weeks} to go` : undefined })
  }
  return list
}

// ---- lessons ----------------------------------------------------------------------------------------------------

export type LessonRef = { lessonId: string; title: string; libraryId?: string; finishedAt?: number; inProgress: boolean }

/** lessonId -> what the dashboard knows about it (title, cached library id). */
export function lessonIndex(data: DashData | undefined): Map<string, LessonRef> {
  const m = new Map<string, LessonRef>()
  for (const c of data?.completed ?? []) if (c.lessonId && !m.has(c.lessonId)) m.set(c.lessonId, { lessonId: c.lessonId, title: c.title, libraryId: c.libraryId, finishedAt: c.finishedAt, inProgress: false })
  for (const a of data?.inProgress ?? []) if (a.lessonId) m.set(a.lessonId, { ...(m.get(a.lessonId) ?? {}), lessonId: a.lessonId, title: a.title, libraryId: a.libraryId ?? m.get(a.lessonId)?.libraryId, inProgress: true })
  return m
}

/** Up-next lessons that would unlock (or teach) a skill. */
export function nextFor(data: DashData | undefined, s: DashSkill): DashData['next'] {
  const keys = new Set([s.id, skillKey(s.label)])
  return (data?.next ?? []).filter((n) => n.unlocks.some((u) => keys.has(u) || keys.has(skillKey(u))))
}

/** Labels for the up-next card's "Unlocks ..." line, resolved against every track. */
export function unlockLabels(data: DashData | undefined, unlocks: string[]): string[] {
  const all = data?.tracks.flatMap((t) => t.skills) ?? []
  return unlocks.map((u) => all.find((s) => s.id === u || skillKey(s.label) === skillKey(u))?.label ?? u)
}

// ---- skill groups -----------------------------------------------------------------------------------------------

export type SkillGroup = { key: string; title: string; kicker?: string; track: DashTrack }

/**
 * The skills page's groups: one per track, unless a track's skills came from two or more different lessons we know
 * by name. Then each lesson is its own group (titled by the lesson, the track as its small label), so one lesson's
 * skills never hide under a broad track name.
 */
export function groupTracks(data: DashData | undefined): SkillGroup[] {
  const lessons = lessonIndex(data)
  const out: SkillGroup[] = []
  for (const t of data?.tracks ?? []) {
    const titleOf = (s: DashSkill): string | undefined => {
      const id = s.lessons.find((l) => lessons.has(l))
      return id ? lessons.get(id)!.title : undefined
    }
    const titles = new Set(t.skills.map(titleOf).filter((x): x is string => !!x))
    if (titles.size < 2) {
      out.push({ key: t.track, title: t.track, track: t })
      continue
    }
    const groups = new Map<string, DashSkill[]>()
    for (const s of t.skills) {
      const k = titleOf(s) ?? t.track
      groups.set(k, [...(groups.get(k) ?? []), s])
    }
    for (const [title, skills] of groups) {
      const ids = new Set(skills.map((s) => s.id))
      const mastered = skills.filter((s) => s.state === 'mastered').length
      out.push({
        key: `${t.track}\u0000${title}`,
        title,
        kicker: title === t.track ? undefined : t.track,
        track: { ...t, skills, mastered, total: skills.length, edges: t.edges.filter((e) => ids.has(e.from) && ids.has(e.to)), cross: t.cross.filter((c) => ids.has(c.to)) }
      })
    }
  }
  return out
}
