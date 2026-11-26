/**
 * Feature: signincard. The pure half (no bridge, no React, so test/signincard.test.ts runs it in Node).
 *
 * The engine's shared-lesson-cache client (server/lesson/cloud_cache.py on_notice) hears why the cloud would not take
 * a build claim and hands the app one plain dict:
 *
 *   {"reason": "signin_required" | "lesson_builds" | "anon_daily_cap" | "user_daily_cap" | ..., "status": 401 | 403 | 429,
 *    "resets_at"?: "2026-11-24T00:00:00Z"}
 *
 * reason is the cloud's `limit` when it sent one (429 caps), else its error type (401 signin_required), else the
 * HTTP status as text. The lesson itself still builds on this Mac either way: these are calm notes, never errors.
 *
 *   parseNotice(raw)       a bounded, typed copy of that dict, or null
 *   classify(notice)       'signin' (401 signin_required) | a cap kind (429) | null (anything else: no UI)
 *   formatReset(iso, now)  "at 4:00 PM" | "tomorrow at 4:00 PM" | "on Dec 1", in the learner's own time zone
 *   capLine(notice, now)   the one short line for a cap (12 words or fewer)
 */

export type CloudNotice = { reason: string; status: number; resetsAt?: string }

/**
 * What a 429 was about, from the cloud's `limit` (cloud/app.py quota_error and rate_limited):
 *   anon    anon_daily_cap: a guest install's daily help (REQUIRE_SIGNIN=build)
 *   user    user_daily_cap: a signed-in learner's daily help
 *   daily   daily_requests / daily_spend: this install's (or network's) daily help
 *   global  daily_usd: the service-wide daily brake
 *   builds  lesson_builds (miyagi_lesson_quota): this month's shared builds. The lesson still builds here, just not
 *           shared, so the line says that calmly and never says the learner ran out of lessons
 *   rate    *_hourly / rate_limit_error: too many requests just now
 *   full    new_installs / install_daily / install_global (miyagi_full): no room for new installs today
 *   other   a 429 this build doesn't know yet
 */
export type CapKind = 'anon' | 'user' | 'daily' | 'global' | 'builds' | 'rate' | 'full' | 'other'
export type NoticeClass = { kind: 'signin' } | { kind: 'cap'; cap: CapKind } | { kind: 'region' }

const REASON_RE = /^[A-Za-z0-9_.-]{1,60}$/

/** A bounded copy of the engine's notice dict. Accepts resets_at (the engine's key) or resetsAt. */
export function parseNotice(raw: unknown): CloudNotice | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  const status = typeof r.status === 'number' ? r.status : typeof r.status === 'string' && /^\d{3}$/.test(r.status) ? Number(r.status) : NaN
  if (!Number.isInteger(status) || status < 400 || status > 499) return null
  const reason = typeof r.reason === 'string' ? r.reason.trim() : ''
  const n: CloudNotice = { reason: REASON_RE.test(reason) ? reason : String(status), status }
  const at = typeof r.resets_at === 'string' ? r.resets_at : typeof r.resetsAt === 'string' ? r.resetsAt : undefined
  if (at && at.length <= 40 && !Number.isNaN(Date.parse(at))) n.resetsAt = at
  return n
}

const CAPS: Record<string, CapKind> = {
  anon_daily_cap: 'anon',
  user_daily_cap: 'user',
  daily_requests: 'daily',
  daily_spend: 'daily',
  miyagi_quota: 'daily',
  daily_usd: 'global',
  lesson_builds: 'builds',
  miyagi_lesson_quota: 'builds',
  ip_hourly: 'rate',
  token_hourly: 'rate',
  install_hourly: 'rate',
  rate_limit_error: 'rate',
  new_installs: 'full',
  install_daily: 'full',
  install_global: 'full',
  miyagi_full: 'full'
}

export function capKind(reason: string): CapKind {
  return CAPS[reason] ?? (/_hourly$/.test(reason) ? 'rate' : 'other')
}

/**
 * Which UI a notice gets. Only a 401 that says signin_required is the sign-in card: a 401 for an unknown install
 * token is the token self-heal's business (cloud.token_invalid), and a 403 (an install an operator turned off) has
 * its own config.status line. Every 429 is a cap line. 451 region_unavailable (the cloud's region block) is the region
 * line: signing in would not help, so it never offers to.
 */
export function classify(n: CloudNotice): NoticeClass | null {
  if (n.reason === 'region_unavailable' || n.status === 451) return { kind: 'region' }
  if (n.status === 401 && n.reason === 'signin_required') return { kind: 'signin' }
  if (n.status === 429) return { kind: 'cap', cap: capKind(n.reason) }
  return null
}

export type ResetOpts = { timeZone?: string; locale?: string }

/** The calendar day of `d` in the time zone, as a comparable day number. */
function dayNumber(d: Date, timeZone?: string): number {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: 'numeric', day: 'numeric' }).formatToParts(d)
  const get = (t: string): number => Number(parts.find((p) => p.type === t)?.value)
  return Math.round(Date.UTC(get('year'), get('month') - 1, get('day')) / 86_400_000)
}

/**
 * When the cap resets, in the learner's local time (timeZone / locale default to the system's): "at 4:00 PM" today,
 * "tomorrow at 4:00 PM", else "on Dec 1". null when there is no usable time or it is already past.
 */
export function formatReset(iso: string | undefined, now: Date = new Date(), opts: ResetOpts = {}): string | null {
  if (!iso) return null
  const t = new Date(iso)
  if (Number.isNaN(t.getTime()) || t.getTime() <= now.getTime()) return null
  const { timeZone, locale } = opts
  const time = new Intl.DateTimeFormat(locale, { timeZone, hour: 'numeric', minute: '2-digit' }).format(t)
  const days = dayNumber(t, timeZone) - dayNumber(now, timeZone)
  if (days <= 0) return `at ${time}`
  if (days === 1) return `tomorrow at ${time}`
  return `on ${new Intl.DateTimeFormat(locale, { timeZone, month: 'short', day: 'numeric' }).format(t)}`
}

/** The lesson_builds cap: the lesson builds here all the same, only slower. */
export const BUILDS_LINE = 'This lesson builds right here. It may take a minute.'

/** The cap line: what ran out, then when it comes back. 12 words or fewer, no alarm. */
export function capLine(n: CloudNotice, now: Date = new Date(), opts: ResetOpts = {}): string {
  const cap = capKind(n.reason)
  const when = formatReset(n.resetsAt, now, opts)
  const resets = when ? `It resets ${when}.` : 'It resets soon.'
  const retry = when ? `Try again ${when}.` : 'Try again later.'
  switch (cap) {
    case 'anon':
      return `You've used today's free guest help. ${resets}`
    case 'user':
    case 'daily':
      return `You've used today's free help. ${resets}`
    case 'global':
      return `miyagi is at today's limit. ${resets}`
    case 'builds':
      // cloud_cache.claim "denied": the build runs here anyway. Nothing ran out for the learner.
      return BUILDS_LINE
    case 'rate':
      return `Too many requests just now. ${retry}`
    case 'full':
      return `miyagi is full today. ${retry}`
    default:
      return `You've reached a limit for now. ${retry}`
  }
}

/** The cloud's own words for its region block (cloud/app.py REGION_UNAVAILABLE). Also onboarding's and the startup
 *  status's line when POST /v1/install answers 451. */
export const REGION_LINE = "miyagi isn't available in your region yet."
export const REGION_NOTICE: CloudNotice = { reason: 'region_unavailable', status: 451 }

/** The sign-in card's copy (one place, so the test can hold it to 12 words). */
export const SIGNIN = {
  title: 'Sign in to build new lessons',
  body: "Lessons you've opened still work.",
  signIn: 'Sign in',
  notNow: 'Not now',
  signedIn: "You're signed in."
} as const
