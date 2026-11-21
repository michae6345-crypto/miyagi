/**
 * The engine's `progress` answer (contract Progress), checked. Every number comes from passed checks engine side; a
 * piece that is missing or malformed is dropped here, never filled in. `week` / `review` stay null when the engine
 * doesn't track them yet, so the window can show its empty states.
 */
import type { Progress, SkillProgressState } from '../../../../../../shared/contracts/events'

export type { Progress, SkillProgressState }
export type SkillTrack = Progress['skills'][number]
export type ReviewItem = NonNullable<Progress['review']>['items'][number]
export type Week = NonNullable<Progress['week']>

const str = (v: unknown): string => (typeof v === 'string' ? v.trim() : '')
const count = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : undefined)
const STATES = new Set<SkillProgressState>(['mastered', 'practicing', 'not_started'])
const rec = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {})
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])

/** The payload as a Progress, or undefined when it isn't one at all. */
export function readProgress(raw: unknown): Progress | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const m = rec(raw)
  const skills: SkillTrack[] = []
  for (const t of list(m.skills)) {
    const o = rec(t)
    const track = str(o.track)
    if (!track) continue
    const items = list(o.items)
      .map((x) => {
        const i = rec(x)
        return { label: str(i.label), state: (STATES.has(i.state as SkillProgressState) ? i.state : 'not_started') as SkillProgressState }
      })
      .filter((i) => i.label)
    // The track's own counts when the engine sends them; otherwise counted from its items (still only what was sent).
    const mastered = count(o.mastered) ?? items.filter((i) => i.state === 'mastered').length
    const total = count(o.total) ?? items.length
    skills.push({ track, mastered: Math.min(mastered, Math.max(total, mastered)), total, items })
  }
  const completed = list(m.completed)
    .map((x) => {
      const c = rec(x)
      return { lessonId: str(c.lessonId), title: str(c.title), at: str(c.at) }
    })
    .filter((c) => c.title)
  return { skills, completed, week: readWeek(m.week), review: readReview(m.review) }
}

function readWeek(raw: unknown): Week | null {
  if (!raw || typeof raw !== 'object') return null
  const w = rec(raw)
  const days = list(w.days).slice(0, 7).map((d) => d === true)
  if (days.length !== 7) return null
  const minutes = count(w.minutes)
  const streak = count(w.streak)
  return { days, minutes: minutes ?? null, streak: streak ?? null }
}

function readReview(raw: unknown): Progress['review'] {
  if (!raw || typeof raw !== 'object') return null
  const r = rec(raw)
  const items: ReviewItem[] = list(r.items)
    .map((x) => {
      const i = rec(x)
      const file = str(i.file)
      return { label: str(i.label), checks: count(i.checks) ?? 0, when: str(i.when), ...(file ? { file } : {}) }
    })
    .filter((i) => i.label)
  return { due: count(r.due) ?? 0, items }
}

/** "Nov 19" from an ISO date; the raw text when it doesn't parse (never a made-up date). */
export function shortDate(iso: string): string {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00`) : new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** "Today" / "Tomorrow" read as words in a sentence ("Due today"); a weekday or date keeps its capital. */
export function whenWord(when: string): string {
  return /^(today|tomorrow|now)$/i.test(when) ? when.toLowerCase() : when
}
