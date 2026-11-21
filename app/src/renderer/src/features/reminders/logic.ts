/**
 * Feature: reminders. Everything pure, shared by the main process (src/main/features/reminders.ts, which posts the real
 * macOS notification) and the renderer (the offer, Settings, and the browser stage, which simulates the notification
 * with an in-app toast). No Electron, no React, no store here.
 *
 *   settings   off by default; one time a day (default 6:00 PM local); quiet hours (default 10:00 PM to 8:00 AM);
 *              a snooze ("Not today", "For a week"); whether the one-time offer was answered.
 *   decide     is it time to look? At most once a day, inside a grace window after the chosen time (a Mac asleep at
 *              6:00 PM catches up when it wakes, until 9:00 PM), never in quiet hours, never mid-lesson.
 *   due        what is due, read from the engine's `progress` answer with the dashboard's own reader (so the
 *              notification and Home always agree): review items due now, and reps left for today's goal.
 *   compose    the one calm, specific line ("2 skills ready for a quick review: pandas groupby, numpy arrays"), or
 *              nothing at all. Nothing due = no notification.
 */
import { DAY_MS, DEFAULT_DAILY, dayKey, dueItems } from '../dashboard/model'
import { readDashboard } from '../dashboard/types'

/** Minutes after local midnight. */
export type Minute = number

export type QuietHours = { on: boolean; from: Minute; to: Minute }

export type ReminderSettings = {
  /** Off until the learner says yes (the offer after the first finished lesson, or Settings). */
  enabled: boolean
  /** When to look each day. */
  time: Minute
  quiet: QuietHours
  /** No reminder before this moment (epoch ms). null = not snoozed. */
  snoozeUntil: number | null
  /** The one-time offer was answered (Yes, Not now or Esc). It never comes back. */
  offered: boolean
  /** A lesson was finished on this Mac at least once. */
  completedOnce: boolean
  /** Today's goal in reps, as the dashboard has it (the learner's own choice wins over the engine's). */
  dailyGoal: number | null
  /** The dashboard's rhythm pause: a rest the learner asked for, so no reminder until it ends. */
  restUntil: number | null
  /** Main only: the local day the daily look already ran ("YYYY-MM-DD"), sent or not. */
  lastDay: string | null
  /** Main only: when the last reminder went out. */
  lastSentAt: number | null
}

/** What every window sees (main adds what it knows about this Mac). */
export type ReminderState = ReminderSettings & {
  /** This system can show notifications at all. */
  supported: boolean
  /** A development build: reminders show as an in-app toast, never a real notification. */
  preview: boolean
}

export type ReminderNote = { title: string; body: string; kind: 'review' | 'goal' | 'welcome' }

export const STEP_MIN = 30
export const GRACE_MIN = 180
export const DEFAULT_SETTINGS: ReminderSettings = {
  enabled: false,
  time: 18 * 60,
  quiet: { on: true, from: 22 * 60, to: 8 * 60 },
  snoozeUntil: null,
  offered: false,
  completedOnce: false,
  dailyGoal: null,
  restUntil: null,
  lastDay: null,
  lastSentAt: null
}

/** The keys a window may change. lastDay / lastSentAt belong to the scheduler. */
export const EDITABLE = ['enabled', 'time', 'quiet', 'snoozeUntil', 'offered', 'completedOnce', 'dailyGoal', 'restUntil'] as const

const minute = (v: unknown): Minute | undefined =>
  typeof v === 'number' && Number.isFinite(v) && v >= 0 && v < 1440 ? Math.round(v / STEP_MIN) * STEP_MIN % 1440 : undefined
const moment = (v: unknown): number | null | undefined =>
  v === null ? null : typeof v === 'number' && Number.isFinite(v) && v > 0 && v < 8.64e15 ? Math.floor(v) : undefined

/** Keep known keys with valid values (from a file, or from any window). `all` also reads the scheduler's own keys. */
export function sanitize(raw: unknown, all = false): Partial<ReminderSettings> {
  const out: Partial<ReminderSettings> = {}
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out
  const r = raw as Record<string, unknown>
  if (typeof r.enabled === 'boolean') out.enabled = r.enabled
  if (typeof r.offered === 'boolean') out.offered = r.offered
  if (typeof r.completedOnce === 'boolean') out.completedOnce = r.completedOnce
  const t = minute(r.time)
  if (t !== undefined) out.time = t
  if (r.quiet && typeof r.quiet === 'object' && !Array.isArray(r.quiet)) {
    const q = r.quiet as Record<string, unknown>
    const from = minute(q.from)
    const to = minute(q.to)
    if (typeof q.on === 'boolean' && from !== undefined && to !== undefined) out.quiet = { on: q.on, from, to }
  }
  const snooze = moment(r.snoozeUntil)
  if (snooze !== undefined) out.snoozeUntil = snooze
  const rest = moment(r.restUntil)
  if (rest !== undefined) out.restUntil = rest
  if (r.dailyGoal === null) out.dailyGoal = null
  else if (typeof r.dailyGoal === 'number' && Number.isInteger(r.dailyGoal) && r.dailyGoal >= 1 && r.dailyGoal <= 10) out.dailyGoal = r.dailyGoal
  if (all) {
    if (r.lastDay === null || (typeof r.lastDay === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(r.lastDay))) out.lastDay = r.lastDay as string | null
    const sent = moment(r.lastSentAt)
    if (sent !== undefined) out.lastSentAt = sent
  }
  return out
}

/** A window's patch: only the editable keys. */
export function sanitizePatch(raw: unknown): Partial<ReminderSettings> {
  const s = sanitize(raw)
  const out: Partial<ReminderSettings> = {}
  for (const k of EDITABLE) if (k in s) (out as Record<string, unknown>)[k] = s[k]
  return out
}

// ---- time -------------------------------------------------------------------------------------------------------

export const minuteOf = (t: number): Minute => {
  const d = new Date(t)
  return d.getHours() * 60 + d.getMinutes()
}

/** "6:00 PM" (the learner's 12-hour clock; the stage and the Mac both read it the same way). */
export function fmtTime(m: Minute): string {
  const h = Math.floor(m / 60) % 24
  const mm = String(m % 60).padStart(2, '0')
  return `${h % 12 === 0 ? 12 : h % 12}:${mm} ${h < 12 ? 'AM' : 'PM'}`
}

/** One step of the time stepper, wrapping round midnight. */
export const stepTime = (m: Minute, dir: 1 | -1): Minute => (m + dir * STEP_MIN + 1440) % 1440

export function inQuiet(q: QuietHours, m: Minute): boolean {
  if (!q.on || q.from === q.to) return false
  return q.from < q.to ? m >= q.from && m < q.to : m >= q.from || m < q.to
}

/** Local midnight `days` days after the day holding `t` (DST safe: by date). */
export function midnightAfter(t: number, days: number): number {
  const d = new Date(t)
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() + days)
  return d.getTime()
}

/** Local time `m` on the day holding `t`. */
function at(t: number, m: Minute): number {
  const d = new Date(t)
  d.setHours(Math.floor(m / 60), m % 60, 0, 0)
  return d.getTime()
}

export const snoozed = (s: ReminderSettings, now: number): boolean => !!s.snoozeUntil && s.snoozeUntil > now
export const resting = (s: ReminderSettings, now: number): boolean => !!s.restUntil && s.restUntil > now

/** "Mon, Nov 23" for a snooze's end. */
export function fmtDay(t: number, now: number): string {
  const days = Math.round((midnightAfter(t, 0) - midnightAfter(now, 0)) / DAY_MS)
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  return new Date(t).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
}

// ---- deciding -----------------------------------------------------------------------------------------------------

export type Decision =
  /** Off, snoozed or resting: nothing to do today. */
  | 'off'
  /** Not the time yet, or today's look already ran. */
  | 'wait'
  /** The time came in quiet hours or mid-lesson: today is skipped, quietly. */
  | 'skip'
  /** Look at what is due now. */
  | 'look'

export function decide(s: ReminderSettings, now: number, lessonActive: boolean): Decision {
  if (!s.enabled || snoozed(s, now) || resting(s, now)) return 'off'
  const m = minuteOf(now)
  const end = Math.min(s.time + GRACE_MIN, 1440)
  if (m < s.time || m >= end) return 'wait'
  if (s.lastDay === dayKey(now)) return 'wait'
  if (inQuiet(s.quiet, m)) return 'skip'
  if (lessonActive) return 'skip'
  return 'look'
}

/** The next moment miyagi will look (for "Next: today at 6:00 PM"); undefined when reminders are off or the time is quiet. */
export function nextLook(s: ReminderSettings, now: number): number | undefined {
  if (!s.enabled || inQuiet(s.quiet, s.time)) return undefined
  let from = Math.max(now, s.snoozeUntil ?? 0, s.restUntil ?? 0)
  for (let i = 0; i < 9; i++) {
    const t = at(from, s.time)
    const doneToday = s.lastDay === dayKey(t)
    if (!doneToday && t + GRACE_MIN * 60_000 > from) return Math.max(t, from)
    from = midnightAfter(from, 1)
  }
  return undefined
}

// ---- what is due ----------------------------------------------------------------------------------------------------

export type Due = { reviews: string[]; repsLeft: number | null }

/** A label as plain text: no markdown code ticks (a notification can't render them), at most `n` characters. */
const clip = (raw: string, n = 32): string => {
  const s = raw.replace(/`/g, '').replace(/\s+/g, ' ').trim()
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s
}

/**
 * What is due now, from the engine's `progress` answer. Reviews: the dashboard's dueItems (dated items whose time has
 * come; the old shape's first `due` items). Goal: reps today against the goal, only when the engine counts activity
 * (null otherwise: never a guessed number). The learner's goal wins over the engine's.
 */
export function dueFrom(raw: unknown, now: number, goal: number | null): Due {
  const data = readDashboard(raw)
  if (!data) return { reviews: [], repsLeft: null }
  const seen = new Set<string>()
  const reviews: string[] = []
  for (const r of dueItems(data.review, now)) {
    const key = r.label.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    reviews.push(r.label)
  }
  // Home's ring uses the same order (dashboard goalsFor): the learner's own number, the engine's, then the default.
  const target = goal ?? data.settings.dailyGoal ?? DEFAULT_DAILY
  let repsLeft: number | null = null
  if (data.activity) {
    const today = data.activity.find((d) => d.date === dayKey(now))
    repsLeft = Math.max(0, target - (today?.reps ?? 0))
  }
  return { reviews, repsLeft }
}

/** The one line, or undefined when nothing is due (then nothing is sent). */
export function compose(due: Due): ReminderNote | undefined {
  const r = due.reviews.map((l) => clip(l)).filter(Boolean)
  if (r.length === 1) return { title: 'miyagi', body: `${r[0]} is ready for a quick review`, kind: 'review' }
  if (r.length === 2) return { title: 'miyagi', body: `2 skills ready for a quick review: ${r[0]}, ${r[1]}`, kind: 'review' }
  if (r.length > 2) return { title: 'miyagi', body: `${r.length} skills ready for a quick review: ${r[0]}, ${r[1]} and ${r.length - 2} more`, kind: 'review' }
  if (due.repsLeft && due.repsLeft > 0) {
    const body = due.repsLeft === 1 ? 'One more rep closes today’s goal' : `${due.repsLeft} reps left for today’s goal`
    return { title: 'miyagi', body, kind: 'goal' }
  }
  return undefined
}

/** Sent once, right when the learner turns reminders on: shows what one looks like (and asks macOS's permission now). */
export function welcome(s: ReminderSettings): ReminderNote {
  return { title: 'miyagi', body: `Reminders are on. One a day at ${fmtTime(s.time)}, only when something is due.`, kind: 'welcome' }
}
