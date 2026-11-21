/**
 * Feature: telemetry (ROADMAP 1.6 crash reporting + 1.7 analytics), the pure part: no Electron, no network, no timers.
 * main/features/telemetry.ts drives it; core.test.ts tests it (node --test).
 *
 *   telemetryUrl(env, cloudHost)   where events go: MIYAGI_TELEMETRY_URL, else <miyagi-cloud>/v1/events, else nowhere
 *   scrubCrash(text)               an error line made safe to send: keys, emails, home folders (usernames) and any
 *                                  quoted text (screen text, file contents) out, one line, capped
 *   cleanProps(props)              only short keys with numbers, booleans or short enum-like strings
 *   Batcher                        a capped queue, sent in batches, kept and retried with backoff when a send fails
 *
 * Nothing is ever queued while the learner's "Share crash reports and usage" switch is off (the feature checks that).
 */
import { scrub } from '../../../renderer/src/features/errors/scrub'

/** Every event name the app or the engine may send (the proxy accepts the same shape). */
export const EVENT_NAMES = [
  'app_installed',
  'onboarding_done',
  'lesson_search',
  'lesson_built',
  'step_passed',
  'step_failed_check',
  'hint_used',
  'lesson_completed',
  'lesson_abandoned',
  'cost_usd',
  'crash'
] as const
export type EventName = (typeof EVENT_NAMES)[number]
const NAMES = new Set<string>(EVENT_NAMES)

export type Props = Record<string, string | number | boolean>
export type TelemetryEvent = { name: EventName; at: string; props: Props }

const OFF_RE = /^(off|0|false|no)$/i

/** A clean https endpoint (http only for this Mac), or undefined. */
function cleanUrl(raw: string): string | undefined {
  try {
    const u = new URL(raw)
    const local = u.hostname === '127.0.0.1' || u.hostname === 'localhost'
    if (u.username || u.password || u.search || u.hash) return undefined
    if (u.protocol !== 'https:' && !(u.protocol === 'http:' && local)) return undefined
    return `${u.origin}${u.pathname.replace(/\/+$/, '')}`
  } catch {
    return undefined
  }
}

/**
 * The events endpoint. `env` is MIYAGI_TELEMETRY_URL (a full endpoint URL; off / 0 / false / no turns telemetry off);
 * `cloudHost` is the miyagi-cloud host (features/cloud.ts cloudUrl(), no trailing /v1), used when env is unset.
 */
export function telemetryUrl(env: string | undefined, cloudHost: string | undefined): string | undefined {
  const t = env?.trim()
  if (t) return OFF_RE.test(t) ? undefined : cleanUrl(t)
  return cloudHost ? cleanUrl(`${cloudHost}/v1/events`) : undefined
}

/** A path: two or more /- or \-separated parts, optionally from ~ or a drive letter. */
const PATH = /(?:~|[A-Za-z]:)?(?:[\\/][^\\/\s:()[\]]+){2,}/g

/** The longest crash line sent. */
export const MAX_CRASH = 300

/**
 * An error line, safe to send. scrub() takes keys, tokens, emails and home folders (/Users/<name> becomes ~); then
 * anything quoted is dropped, because quoted text in an error is usually data: what was on screen, a file's
 * contents, a typed query. Paths keep only their last two parts.
 */
export function scrubCrash(text: string): string {
  let s = scrub(String(text ?? '').replace(/\s+/g, ' ').trim(), 4 * MAX_CRASH)
  s = s.replace(/"[^"]*"|'[^']*'|`[^`]*`|“[^”]*”|‘[^’]*’/g, '[text]')
  // Absolute paths outside home (/private/var/..., C:\...) keep their tail only: enough to find the file in our code.
  s = s.replace(PATH, (m) => {
    const parts = m.split(/[\\/]/).filter((p) => p && p !== '~' && !/^[A-Za-z]:$/.test(p))
    return parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : m
  })
  return s.length > MAX_CRASH ? `${s.slice(0, MAX_CRASH - 1)}…` : s
}

const KEY = /^[a-z][a-z0-9_]{0,31}$/
/** Enum-like values only (a reason, a mode, a version): never sentences, never paths. */
const WORD = /^[A-Za-z0-9_.\- ]{1,40}$/
const MAX_PROPS = 12

/** Keep only short snake_case keys whose values are finite numbers, booleans, or short enum-like strings. */
export function cleanProps(raw: unknown, crashKeys: readonly string[] = ['message']): Props {
  const out: Props = {}
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (Object.keys(out).length >= MAX_PROPS) break
    if (!KEY.test(k)) continue
    if (typeof v === 'boolean') out[k] = v
    else if (typeof v === 'number' && Number.isFinite(v)) out[k] = Math.round(v * 1e6) / 1e6
    else if (typeof v === 'string' && crashKeys.includes(k)) out[k] = scrubCrash(v)
    else if (typeof v === 'string' && WORD.test(v.trim())) out[k] = scrub(v.trim(), 40)
  }
  return out
}

export function makeEvent(name: string, props?: unknown, now: Date = new Date()): TelemetryEvent | undefined {
  if (!NAMES.has(name)) return undefined
  return { name: name as EventName, at: now.toISOString(), props: cleanProps(props) }
}

export type BatcherOptions = {
  /** Sends one batch; resolves true when the endpoint took it. */
  send: (events: TelemetryEvent[]) => Promise<boolean>
  /** Events per request. */
  batch?: number
  /** Events kept at most (oldest dropped first). */
  cap?: number
  /** First backoff after a failed send; doubles up to maxBackoffMs. */
  backoffMs?: number
  maxBackoffMs?: number
  now?: () => number
}

/**
 * A capped in-memory queue, sent in batches. flush() sends while there is something to send, one request at a time;
 * a failed send keeps the batch at the front and waits (backoff doubling, capped) before the next try. clear() drops
 * everything (the switch went off).
 */
export class Batcher {
  private queue: TelemetryEvent[] = []
  private busy = false
  private failures = 0
  private notBefore = 0
  readonly batch: number
  readonly cap: number
  private readonly o: Required<Omit<BatcherOptions, 'send'>> & Pick<BatcherOptions, 'send'>

  constructor(opts: BatcherOptions) {
    this.o = { batch: 20, cap: 200, backoffMs: 30_000, maxBackoffMs: 30 * 60_000, now: Date.now, ...opts }
    this.batch = this.o.batch
    this.cap = this.o.cap
  }

  get size(): number {
    return this.queue.length
  }

  /** A full batch is waiting: worth flushing now rather than at the next tick. */
  get full(): boolean {
    return this.queue.length >= this.o.batch
  }

  push(e: TelemetryEvent | undefined): void {
    if (!e) return
    this.queue.push(e)
    if (this.queue.length > this.o.cap) this.queue.splice(0, this.queue.length - this.o.cap)
  }

  clear(): void {
    this.queue = []
    this.failures = 0
    this.notBefore = 0
  }

  /** Send what is queued, batch by batch. Returns how many events the endpoint took. */
  async flush(): Promise<number> {
    if (this.busy || !this.queue.length || this.o.now() < this.notBefore) return 0
    this.busy = true
    let sent = 0
    try {
      while (this.queue.length) {
        const batch = this.queue.slice(0, this.o.batch)
        let ok = false
        try {
          ok = await this.o.send(batch)
        } catch {
          ok = false
        }
        if (!ok) {
          this.failures++
          this.notBefore = this.o.now() + Math.min(this.o.backoffMs * 2 ** (this.failures - 1), this.o.maxBackoffMs)
          break
        }
        this.failures = 0
        this.notBefore = 0
        // Only what was sent leaves the queue (clear() may have run meanwhile: then nothing is left to drop).
        const head = this.queue.slice(0, batch.length)
        if (head.every((e, i) => e === batch[i])) this.queue.splice(0, batch.length)
        sent += batch.length
      }
    } finally {
      this.busy = false
    }
    return sent
  }
}

export type LogLine = { at: string; text: string }

/** errors.json lines written after `since` (ISO), oldest first. Bad rows are skipped. */
export function newLines(log: unknown, since: string | undefined): LogLine[] {
  if (!Array.isArray(log)) return []
  const t0 = since ? Date.parse(since) || 0 : 0
  return log
    .filter((l): l is LogLine => !!l && typeof (l as LogLine).at === 'string' && typeof (l as LogLine).text === 'string')
    .filter((l) => (Date.parse(l.at) || 0) > t0)
}

/** One errors.json line → a crash event: its kind (the text before the first colon) and the scrubbed message. */
export function crashEvent(line: LogLine): TelemetryEvent | undefined {
  const m = /^([a-z][a-z ]{0,30}?)(?: gone)?:\s*(.*)$/i.exec(line.text)
  const kind = (m?.[1] ?? 'error').trim().toLowerCase().replace(/\s+/g, '_').slice(0, 32)
  const at = Number.isFinite(Date.parse(line.at)) ? new Date(Date.parse(line.at)) : new Date()
  return makeEvent('crash', { kind, message: m?.[2] ?? line.text }, at)
}
