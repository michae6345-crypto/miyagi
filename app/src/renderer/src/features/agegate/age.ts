/**
 * Feature: agegate. The age maths and the one record miyagi keeps, pure (no DOM, no bridge), so main
 * (main/features/agegate.ts) and the tests (age.test.ts) share it.
 *
 *   Birth           what the pickers hold, in this screen's memory only: never stored, never sent, never logged.
 *   ageOn           whole years on a day. A Feb 29 birthday counts on Mar 1 in a year with no Feb 29.
 *   decide          under 13: blocked; 13 to 17: teen (the parent or guardian step); 18 and up: adult.
 *   AgeRecord       the ONLY thing kept (userData/age.json, written by main):
 *                     {band: '13-17' | '18+', confirmed: 'YYYY-MM-DD'}   after the step is through
 *                     {blockedUntil: 'YYYY-MM-01'}                       under 13
 *                   blockedUntil is the first day of the month AFTER the 13th birthday, so the record can't be turned
 *                   back into the birth date (and it errs late, never early).
 *   blockActive     a block holds until that day; re-entering a different date can't lift it (main refuses).
 */

export type Birth = { y: number; m: number; d: number }
export type Day = { y: number; m: number; d: number }
export type Band = '13-17' | '18+'
export type AgeRecord = { band: Band; confirmed: string } | { blockedUntil: string }
export type Decision = { kind: 'blocked'; record: { blockedUntil: string } } | { kind: 'teen' } | { kind: 'adult' }

export const MIN_AGE = 13
export const ADULT_AGE = 18
/** The year picker reaches back this far. */
export const OLDEST = 120

export const isLeap = (y: number): boolean => (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0

/** Days in month m (1-12) of year y. */
export function daysIn(y: number, m: number): number {
  if (m === 2) return isLeap(y) ? 29 : 28
  return [4, 6, 9, 11].includes(m) ? 30 : 31
}

const int = (n: unknown): n is number => typeof n === 'number' && Number.isInteger(n)
const pad = (n: number, w = 2): string => String(n).padStart(w, '0')
export const iso = (d: Day): string => `${pad(d.y, 4)}-${pad(d.m)}-${pad(d.d)}`
const cmp = (a: Day, b: Day): number => a.y - b.y || a.m - b.m || a.d - b.d

/** Today on this Mac's calendar (local time). */
export function todayOf(now: Date = new Date()): Day {
  return { y: now.getFullYear(), m: now.getMonth() + 1, d: now.getDate() }
}

/** A real calendar day (Feb 30 and Feb 29 of a common year are not). */
export function realDay(b: Partial<Birth> | null | undefined): b is Birth {
  if (!b || !int(b.y) || !int(b.m) || !int(b.d)) return false
  return b.m >= 1 && b.m <= 12 && b.d >= 1 && b.d <= daysIn(b.y, b.m)
}

/** A birth date the screen accepts: a real day, not after today, within OLDEST years. */
export function validBirth(b: Partial<Birth> | null | undefined, today: Day): b is Birth {
  if (!realDay(b)) return false
  if (b.y < today.y - OLDEST) return false
  return cmp(b, today) <= 0
}

/** The birthday as it falls in `year`: Feb 29 becomes Mar 1 in a year with no Feb 29. */
export function birthdayIn(b: Birth, year: number): Day {
  if (b.m === 2 && b.d === 29 && !isLeap(year)) return { y: year, m: 3, d: 1 }
  return { y: year, m: b.m, d: b.d }
}

/** Whole years old on `today`. */
export function ageOn(b: Birth, today: Day): number {
  const had = cmp(birthdayIn(b, today.y), today) <= 0
  return today.y - b.y - (had ? 0 : 1)
}

/** The first day of the month after the 13th birthday (see the header: never the birth date itself). */
export function blockUntil(b: Birth): string {
  const t = birthdayIn(b, b.y + MIN_AGE)
  const m = t.m === 12 ? 1 : t.m + 1
  return iso({ y: t.m === 12 ? t.y + 1 : t.y, m, d: 1 })
}

export function decide(b: Birth, today: Day): Decision {
  const age = ageOn(b, today)
  if (age < MIN_AGE) return { kind: 'blocked', record: { blockedUntil: blockUntil(b) } }
  return age < ADULT_AGE ? { kind: 'teen' } : { kind: 'adult' }
}

/** The record kept once the step is through. */
export const bandRecord = (band: Band, today: Day): AgeRecord => ({ band, confirmed: iso(today) })

const ISO_RE = /^\d{4}-\d{2}-\d{2}$/
const isoDay = (s: unknown): s is string => typeof s === 'string' && ISO_RE.test(s) && realDay({ y: +s.slice(0, 4), m: +s.slice(5, 7), d: +s.slice(8, 10) })

/** Only the two shapes, nothing else carried along (a stray field never reaches the file). */
export function cleanRecord(raw: unknown): AgeRecord | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const r = raw as Record<string, unknown>
  if (isoDay(r.blockedUntil) && r.blockedUntil.endsWith('-01')) return { blockedUntil: r.blockedUntil }
  if ((r.band === '13-17' || r.band === '18+') && isoDay(r.confirmed)) return { band: r.band, confirmed: r.confirmed }
  return undefined
}

/** A block still in force on `today`. */
export const blockActive = (r: AgeRecord | undefined, today: Day): r is { blockedUntil: string } => !!r && 'blockedUntil' in r && r.blockedUntil > iso(today)

/** Through the step: a band on record and no block in force. */
export const ageCleared = (r: AgeRecord | undefined, today: Day): boolean => !!r && 'band' in r && !blockActive(r, today)

/**
 * What main keeps when the renderer sends `next` while `prev` is on file: a block in force wins over anything (going
 * back and picking another date can't lift it); a lapsed block is dropped. undefined: nothing valid to write.
 */
export function mergeRecord(prev: AgeRecord | undefined, next: unknown, today: Day): AgeRecord | undefined {
  if (blockActive(prev, today)) return prev
  const n = cleanRecord(next)
  if (!n) return undefined
  if ('blockedUntil' in n && !blockActive(n, today)) return undefined // a block that is already over means nothing
  if ('band' in n) return { band: n.band, confirmed: iso(today) } // main's clock, not the renderer's
  return n
}
