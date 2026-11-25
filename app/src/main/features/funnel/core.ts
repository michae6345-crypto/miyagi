/**
 * Feature: funnel (activation analytics), the pure part: no Electron, no network, no timers.
 * main/features/funnel.ts drives it; app/test/funnel.test.ts tests it.
 *
 * The activation funnel, one timestamp per milestone per install, the FIRST time it happened on this Mac:
 *
 *   first_launch → signed_in → permissions_granted → lesson_started → step_passed → lesson_finished
 *
 * (Download happens before the app exists, so it is counted on the site / release side, not here.)
 *
 * Wire contract (miyagi-cloud POST /v1/funnel, claude/eng-proxy-funnel):
 *   Authorization: Bearer <mi_ install token>
 *   {"milestones": [{"name": <milestone>, "at": <ISO 8601 UTC>}]}         at most 6 items, 2 KB
 *   202 {"ok": true}: the cloud keeps the earliest `at` per (install, name). Sending one again is harmless.
 *   404: an older cloud without the route: stop for this run.
 * Only these names and times. Never lesson titles, screen text, code, paths, emails or tokens. The cloud ties the
 * install to the Supabase user through its own `links` table (POST /v1/link), so no user id is sent here.
 */
import { newTrack, usageEvent, type LessonTrack } from '../telemetry/core'

export const MILESTONES = ['first_launch', 'signed_in', 'permissions_granted', 'lesson_started', 'step_passed', 'lesson_finished'] as const
export type Milestone = (typeof MILESTONES)[number]
const NAMES = new Set<string>(MILESTONES)
export const isMilestone = (v: unknown): v is Milestone => typeof v === 'string' && NAMES.has(v)

/** userData/funnel/state.json. `at`: ISO time per milestone; `sent`: the cloud took that exact time (202). */
export type FunnelState = { at: Partial<Record<Milestone, string>>; sent: Partial<Record<Milestone, string>> }
export type FunnelItem = { name: Milestone; at: string }

export const MAX_BYTES = 2 * 1024

/** An ISO time we wrote ourselves (Date#toISOString), or undefined. */
function iso(v: unknown): string | undefined {
  if (typeof v !== 'string' || v.length > 40) return undefined
  const t = Date.parse(v)
  return Number.isFinite(t) ? new Date(t).toISOString() : undefined
}

/** A plain copy of what the state file held: unknown names and bad times dropped. */
export function cleanState(raw: unknown): FunnelState {
  const s: FunnelState = { at: {}, sent: {} }
  if (!raw || typeof raw !== 'object') return s
  const r = raw as { at?: unknown; sent?: unknown }
  for (const key of ['at', 'sent'] as const) {
    const m = r[key]
    if (!m || typeof m !== 'object') continue
    for (const [k, v] of Object.entries(m as Record<string, unknown>)) {
      const t = iso(v)
      if (isMilestone(k) && t) s[key][k] = t
    }
  }
  return s
}

/** Record a milestone. Keeps the earliest time. Returns whether the state changed. */
export function mark(s: FunnelState, name: Milestone, when: Date | string = new Date()): boolean {
  const at = iso(typeof when === 'string' ? when : when.toISOString())
  if (!at) return false
  const had = s.at[name]
  if (had && Date.parse(had) <= Date.parse(at)) return false
  s.at[name] = at
  return true
}

/** What still has to reach the cloud, in funnel order. */
export function unsent(s: FunnelState): FunnelItem[] {
  return MILESTONES.filter((m) => s.at[m] && s.sent[m] !== s.at[m]).map((m) => ({ name: m, at: s.at[m]! }))
}

/** After a 202: these exact times are on the cloud. */
export function markSent(s: FunnelState, items: FunnelItem[]): void {
  for (const i of items) if (s.at[i.name] === i.at) s.sent[i.name] = i.at
}

export const body = (items: FunnelItem[]): string => JSON.stringify({ milestones: items })

/** `<cloudHost>/v1/funnel`, from the host that minted the install token (cloud.ts installToken().host). */
export function funnelUrl(cloudHost: string | undefined): string | undefined {
  if (!cloudHost) return undefined
  try {
    const u = new URL(cloudHost.replace(/\/+$/, '').replace(/\/v1$/, ''))
    const local = u.hostname === '127.0.0.1' || u.hostname === 'localhost'
    if (u.username || u.password || u.search || u.hash) return undefined
    if (u.protocol !== 'https:' && !(u.protocol === 'http:' && local)) return undefined
    return `${u.origin}${u.pathname.replace(/\/+$/, '')}/v1/funnel`
  } catch {
    return undefined
  }
}

/** Engine events → lesson milestones, through telemetry's own lesson tracking (same rules: no replays, no skips). */
export type Tracker = { track(msg: unknown, now?: Date): Milestone | undefined }
export function lessonTracker(): Tracker {
  const t: LessonTrack = newTrack()
  return {
    track(msg, now = new Date()) {
      const ev = usageEvent(msg, t, now)
      switch (ev?.name) {
        case 'lesson_built':
          return 'lesson_started'
        case 'step_passed':
          return 'step_passed'
        case 'lesson_completed':
          return 'lesson_finished'
        default:
          return undefined
      }
    }
  }
}
