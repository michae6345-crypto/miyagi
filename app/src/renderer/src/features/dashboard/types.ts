/**
 * Feature: dashboard. The engine's `progress` answer read for the lesson dashboard, checked piece by piece. Nothing is
 * filled in: a missing part stays empty (null = "not tracked yet") and the view shows that part's empty state.
 *
 * Reads both shapes on the wire today:
 *   engine (server/sessions/progress.py)   skills[].skills, completed[].finishedAt (epoch s), inProgress[]
 *   app contract (shared/contracts Progress) skills[].items, completed[].at (ISO)
 * and the additive fields the dashboard asks for (agents/dashboard.md, Core requests): per-track edges / cross,
 * per-skill detail / lessons / masteredAt / lastPracticedAt / reps, next[], activity[], review.items[].dueAt, settings.
 * Times arrive as epoch seconds (the engine's habit) or ISO text; here they are epoch milliseconds.
 */
import type { SkillProgressState } from '../../../../../../shared/contracts/events'

export type { SkillProgressState }

export type DashSkill = {
  id: string
  label: string
  state: SkillProgressState
  detail?: string
  /** lessonIds that taught it. */
  lessons: string[]
  masteredAt?: number
  lastPracticedAt?: number
  /** Passed, unassisted steps behind it. undefined = the engine doesn't count them yet. */
  reps?: number
}
export type DashEdge = { from: string; to: string }
export type DashCross = { track: string; label: string; to: string; note?: string }
export type DashTrack = { track: string; mastered: number; total: number; skills: DashSkill[]; edges: DashEdge[]; cross: DashCross[] }
export type DashNext = { title: string; goal: string; id?: string; estMinutes?: number; unlocks: string[] }
export type DashDone = { lessonId: string; title: string; finishedAt?: number; libraryId?: string; result?: { passed?: number; skipped?: number; total?: number } }
export type DashActive = {
  lessonId: string
  title: string
  mode: 'lesson' | 'video'
  stepIndex?: number
  stepCount?: number
  passed?: number
  skipped?: number
  assisted?: number
  stepTitle?: string
  lastActiveAt?: number
  libraryId?: string
}
/** One local day. date = "YYYY-MM-DD" in the learner's time zone. */
export type ActivityDay = { date: string; reps: number; assisted: number; hints: number }
export type ReviewEntry = {
  skillId?: string
  label: string
  track?: string
  /** When it is due (ms). Absent on the old contract shape, which says `when` in words instead. */
  dueAt?: number
  /** Days in the current interval (3, 7, 21, 60). */
  interval?: number
  lastResult?: 'passed' | 'missed'
  lastAt?: number
  /** Old contract shape: "Today", "Saturday". */
  when?: string
  file?: string
}
export type EngineSettings = { dailyGoal?: number; weeklyGoal?: number; pausedFrom?: number; pausedUntil?: number }

export type DashData = {
  tracks: DashTrack[]
  completed: DashDone[]
  inProgress: DashActive[]
  next: DashNext[]
  /** null: the engine keeps no per-day activity yet. */
  activity: ActivityDay[] | null
  /** null: no review scheduler yet. */
  review: { items: ReviewEntry[]; due?: number } | null
  settings: EngineSettings
}

const STATES = new Set<SkillProgressState>(['mastered', 'practicing', 'not_started'])
const ID_RE = /^[A-Za-z0-9_-]{1,64}$/
const DAY_RE = /^\d{4}-\d{2}-\d{2}$/

const rec = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {})
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const str = (v: unknown, max = 200): string => (typeof v === 'string' ? v.replace(/\s+/g, ' ').trim().slice(0, max) : '')
const opt = (v: unknown, max = 200): string | undefined => str(v, max) || undefined
const count = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 && v < 1e7 ? Math.floor(v) : undefined)
const libId = (v: unknown): string | undefined => (typeof v === 'string' && ID_RE.test(v) ? v : undefined)

/** Epoch seconds, epoch ms or ISO text, as ms. Date-only text is that day's local noon (never a time zone slip). */
export function toMs(v: unknown): number | undefined {
  if (typeof v === 'number' && Number.isFinite(v) && v > 0) return v > 1e12 ? v : v * 1000
  if (typeof v !== 'string' || !v.trim()) return undefined
  const t = DAY_RE.test(v) ? new Date(`${v}T12:00:00`).getTime() : Date.parse(v)
  return Number.isFinite(t) ? t : undefined
}

export const skillKey = (s: string): string => s.trim().toLowerCase()

function readSkill(raw: unknown): DashSkill | undefined {
  const i = rec(raw)
  const label = str(i.label, 80)
  if (!label) return undefined
  const state = (STATES.has(i.state as SkillProgressState) ? i.state : 'not_started') as SkillProgressState
  return {
    id: str(i.id, 80) || skillKey(label),
    label,
    state,
    detail: opt(i.detail, 160),
    lessons: list(i.lessons).map((x) => str(x, 120)).filter(Boolean),
    masteredAt: state === 'mastered' ? toMs(i.masteredAt) : undefined,
    lastPracticedAt: toMs(i.lastPracticedAt),
    reps: count(i.reps)
  }
}

function readTrack(raw: unknown): DashTrack | undefined {
  const o = rec(raw)
  const track = str(o.track, 80)
  if (!track) return undefined
  // The engine says `skills`; the old contract says `items`. Either one, never both merged.
  const rows = Array.isArray(o.skills) ? o.skills : o.items
  const skills: DashSkill[] = []
  const seen = new Set<string>()
  for (const r of list(rows)) {
    const s = readSkill(r)
    if (!s || seen.has(s.id)) continue
    seen.add(s.id)
    skills.push(s)
  }
  // Edges and cross links may name a node by id or by label; both resolve to the id here, anything else is dropped.
  const byKey = new Map<string, string>()
  for (const s of skills) {
    byKey.set(s.id, s.id)
    byKey.set(skillKey(s.label), s.id)
  }
  const ref = (v: unknown): string | undefined => {
    const t = str(v, 80)
    return t ? (byKey.get(t) ?? byKey.get(skillKey(t))) : undefined
  }
  const edges: DashEdge[] = []
  for (const e of list(o.edges)) {
    const from = ref(rec(e).from)
    const to = ref(rec(e).to)
    if (from && to && from !== to && !edges.some((x) => x.from === from && x.to === to)) edges.push({ from, to })
  }
  const cross: DashCross[] = []
  for (const c of list(o.cross)) {
    const r = rec(c)
    const to = ref(r.to)
    const label = str(r.label, 80)
    if (to && label) cross.push({ track: str(r.track, 80), label, to, note: opt(r.note, 120) })
  }
  const mastered = count(o.mastered) ?? skills.filter((s) => s.state === 'mastered').length
  const total = Math.max(count(o.total) ?? skills.length, skills.length)
  return { track, mastered: Math.min(mastered, total), total, skills, edges, cross }
}

function readActivity(raw: unknown): ActivityDay[] | null {
  if (!Array.isArray(raw)) return null
  const byDate = new Map<string, ActivityDay>()
  for (const x of raw) {
    const r = rec(x)
    const date = typeof r.date === 'string' && DAY_RE.test(r.date) ? r.date : ''
    if (!date) continue
    const have = byDate.get(date) ?? { date, reps: 0, assisted: 0, hints: 0 }
    have.reps += count(r.reps) ?? 0
    have.assisted += count(r.assisted) ?? 0
    have.hints += count(r.hints) ?? 0
    byDate.set(date, have)
  }
  return [...byDate.values()].sort((a, b) => (a.date < b.date ? -1 : 1))
}

function readReview(raw: unknown): DashData['review'] {
  if (!raw || typeof raw !== 'object') return null
  const r = rec(raw)
  const items: ReviewEntry[] = []
  for (const x of list(r.items)) {
    const i = rec(x)
    const label = str(i.label, 80)
    if (!label) continue
    const last = i.lastResult === 'passed' || i.lastResult === 'missed' ? i.lastResult : undefined
    items.push({
      skillId: opt(i.skillId, 80),
      label,
      track: opt(i.track, 80),
      dueAt: toMs(i.dueAt),
      interval: count(i.interval),
      lastResult: last,
      lastAt: toMs(i.lastAt),
      when: opt(i.when, 40),
      file: opt(i.file, 120)
    })
  }
  return { items, due: count(r.due) }
}

function readSettings(raw: unknown): EngineSettings {
  const s = rec(raw)
  const goal = (v: unknown, max: number): number | undefined => {
    const n = count(v)
    return n && n >= 1 ? Math.min(n, max) : undefined
  }
  return { dailyGoal: goal(s.dailyGoal, 10), weeklyGoal: goal(s.weeklyGoal, 7), pausedFrom: toMs(s.pausedFrom), pausedUntil: toMs(s.pausedUntil) }
}

/** The `progress` payload for the dashboard, or undefined when it isn't one at all. */
export function readDashboard(raw: unknown): DashData | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const m = rec(raw)
  const tracks = list(m.skills)
    .map(readTrack)
    .filter((t): t is DashTrack => !!t && t.skills.length > 0)
  const completed: DashDone[] = []
  for (const x of list(m.completed)) {
    const c = rec(x)
    const title = str(c.title)
    if (!title) continue
    const res = rec(c.result)
    const result = { passed: count(res.passed), skipped: count(res.skipped), total: count(res.total) }
    completed.push({
      lessonId: str(c.lessonId, 120),
      title,
      finishedAt: toMs(c.finishedAt ?? c.at),
      libraryId: libId(c.libraryId),
      ...(result.total !== undefined || result.passed !== undefined ? { result } : {})
    })
  }
  const inProgress: DashActive[] = []
  for (const x of list(m.inProgress)) {
    const a = rec(x)
    const title = str(a.title)
    if (!title) continue
    inProgress.push({
      lessonId: str(a.lessonId, 120),
      title,
      mode: a.mode === 'lesson' ? 'lesson' : 'video',
      stepIndex: count(a.stepIndex),
      stepCount: count(a.stepCount),
      passed: count(a.passed),
      skipped: count(a.skipped),
      assisted: count(a.assisted),
      stepTitle: opt(a.stepTitle, 120),
      lastActiveAt: toMs(a.lastActiveAt),
      libraryId: libId(a.libraryId)
    })
  }
  const next: DashNext[] = []
  for (const x of list(m.next)) {
    const n = rec(x)
    const title = str(n.title, 120)
    const goal = str(n.goal, 300)
    if (!title || !goal) continue
    next.push({ title, goal, id: libId(n.id), estMinutes: count(n.estMinutes), unlocks: list(n.unlocks).map((u) => str(u, 80)).filter(Boolean) })
  }
  return {
    tracks,
    completed,
    inProgress,
    next,
    activity: readActivity(m.activity),
    review: readReview(m.review),
    settings: readSettings(m.settings)
  }
}
