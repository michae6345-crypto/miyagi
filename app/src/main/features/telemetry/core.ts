/**
 * Feature: telemetry (ROADMAP 1.6 crash reporting + 1.7 analytics), the pure part: no Electron, no network, no timers.
 * main/features/telemetry.ts drives it; app/test/telemetryCore.test.ts and app/test/telemetry.test.ts test it.
 *
 * Wire contract (miyagi-cloud POST /v1/events):
 *   Authorization: Bearer <mi_ install token>
 *   {"events": [{"name": str, "at": iso, "props": {str: str | number | bool}}]}   at most 50 events and 32 KB a request
 *   202 {"ok": true}; 404 is an older cloud without the route: drop silently and stop for this run.
 *   Never screen text, code, file paths, emails or tokens.
 *
 *   telemetryUrl(off, cloudHost)   where events go: <miyagi-cloud>/v1/events (the host that minted the install token)
 *   scrubCrash(text)               an error line made safe to send: keys, emails, URLs, paths and quoted text out
 *   cleanProps(props)              only short keys with numbers, booleans or short enum-like strings
 *   usageEvent(msg, track)         an engine event the app already receives → a lesson count (never its text)
 *   Batcher                        a capped queue, sent in batches that fit the contract, retried with backoff
 *
 * Nothing is ever queued while the learner's "Share crash reports and usage" switch is off (the feature checks that).
 */
import { scrub } from '../../../renderer/src/features/errors/scrub'

/** Every event name the app sends. */
export const EVENT_NAMES = [
  'app_installed',
  'onboarding_done',
  'lesson_built',
  'step_passed',
  'step_failed_check',
  'hint_used',
  'lesson_completed',
  'lesson_abandoned',
  'crash'
] as const
export type EventName = (typeof EVENT_NAMES)[number]
const NAMES = new Set<string>(EVENT_NAMES)

export type Props = Record<string, string | number | boolean>
export type TelemetryEvent = { name: EventName; at: string; props: Props }

/** The contract's limits for one request. */
export const MAX_EVENTS = 50
export const MAX_BYTES = 32 * 1024

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

/** MIYAGI_TELEMETRY said off / 0 / false / no. */
export const switchedOff = (off: string | undefined): boolean => !!off?.trim() && OFF_RE.test(off.trim())

/**
 * The events endpoint: `<cloudHost>/v1/events`. `cloudHost` is the host that minted the install token (cloud.ts
 * installToken().host), so the token only ever goes back where it came from. `off` is MIYAGI_TELEMETRY: off / 0 /
 * false / no turns telemetry off for the run whatever the switch says.
 */
export function telemetryUrl(off: string | undefined, cloudHost: string | undefined): string | undefined {
  if (switchedOff(off)) return undefined
  return cloudHost ? cleanUrl(`${cloudHost.replace(/\/+$/, '').replace(/\/v1$/, '')}/v1/events`) : undefined
}

/** The longest crash line sent. */
export const MAX_CRASH = 300

/** A URL of any scheme (file:// is handled first, as a path). */
const URL_RE = /\b[a-z][a-z0-9+.-]*:\/\/[^\s"'`<>()]+/gi
/** A path: two or more /- or \-separated parts, optionally from ~ or a drive letter. */
const PATH = /(?:~|\b[A-Za-z]:)?(?:[\\/][^\\/\s:()[\]"'`]+){2,}/g
/** Where miyagi's own bundled code lives (packaged app.asar, or electron-vite's out/ in a dev copy). */
const OWN_CODE = /app\.asar|[\\/]out[\\/](?:main|preload|renderer)[\\/]/
const JS_FILE = /^[\w.-]+\.(?:js|mjs|cjs)$/

/** A path → `app:<file>.js` when it is miyagi's own bundled script, else `[path]` (never a learner's file name). */
function pathToken(p: string): string {
  const base = p.split(/[\\/]/).filter(Boolean).at(-1) ?? ''
  return OWN_CODE.test(p) && JS_FILE.test(base) ? `app:${base}` : '[path]'
}

/**
 * An error line, safe to send. scrub() takes keys, tokens, emails and home folders; then anything quoted is dropped
 * (quoted text in an error is usually data: what was on screen, a file's contents, a typed query), URLs go, and every
 * path goes too: only miyagi's own bundled script keeps its file name (`app:index.js:12:5`) so a crash can be found.
 */
export function scrubCrash(text: string): string {
  let s = scrub(String(text ?? '').replace(/\s+/g, ' ').trim(), 4 * MAX_CRASH)
  s = s.replace(/"[^"]*"|'[^']*'|`[^`]*`|“[^”]*”|‘[^’]*’/g, '[text]')
  s = s.replace(/\bfile:\/\/\/?(?:[A-Za-z]:)?([^\s"'`<>():]+)/gi, (_m, p: string) => pathToken(p))
  s = s.replace(URL_RE, '[url]')
  s = s.replace(PATH, (m) => pathToken(m))
  // scrub() turned home folders into ~: a lone ~ left over says nothing.
  s = s.replace(/~(?=[\s:]|$)/g, '[path]')
  return s.length > MAX_CRASH ? `${s.slice(0, MAX_CRASH - 1)}…` : s
}

const KEY = /^[a-z][a-z0-9_]{0,31}$/
/** Enum-like values only (a reason, a mode, a version): never sentences, never paths. */
const WORD = /^[A-Za-z0-9_.-]{1,40}$/
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
    else if (typeof v === 'string' && WORD.test(v.trim())) {
      const w = scrub(v.trim(), 40)
      if (!w.includes('[')) out[k] = w // a token or key-shaped word is dropped, not sent as a placeholder
    }
  }
  return out
}

export function makeEvent(name: string, props?: unknown, now: Date = new Date()): TelemetryEvent | undefined {
  if (!NAMES.has(name)) return undefined
  return { name: name as EventName, at: now.toISOString(), props: cleanProps(props) }
}

/** The request body the contract expects, and its size in bytes. */
export const body = (events: readonly TelemetryEvent[]): string => JSON.stringify({ events })
const bytes = (s: string): number => Buffer.byteLength(s, 'utf8')

/**
 * What one send did. sent: taken (202). retry: keep it and back off (offline, 5xx, 429, 401 while the token heals).
 * drop: this batch will never be taken (400, 413, 422): drop it, keep going. stop: the route is gone (404, an older
 * cloud): drop everything and send nothing more this run.
 */
export type SendResult = 'sent' | 'retry' | 'drop' | 'stop'

/** An HTTP status → what to do with the batch. */
export function resultFor(status: number): SendResult {
  if (status >= 200 && status < 300) return 'sent'
  if (status === 404 || status === 410) return 'stop'
  if (status === 400 || status === 413 || status === 422) return 'drop'
  return 'retry'
}

export type BatcherOptions = {
  /** Sends one batch. */
  send: (events: TelemetryEvent[]) => Promise<SendResult>
  /** Events per request (at most MAX_EVENTS). */
  batch?: number
  /** Bytes per request body (at most MAX_BYTES). */
  maxBytes?: number
  /** Events kept at most (oldest dropped first). */
  cap?: number
  /** First backoff after a failed send; doubles up to maxBackoffMs. */
  backoffMs?: number
  maxBackoffMs?: number
  now?: () => number
}

/**
 * A capped in-memory queue, sent in batches. flush() sends while there is something to send, one request at a time;
 * every batch fits the contract (MAX_EVENTS, MAX_BYTES). A 'retry' keeps the batch at the front and waits (backoff
 * doubling, capped); 'drop' drops it; 'stop' drops everything and refuses new events. clear() drops everything (the
 * switch went off).
 */
export class Batcher {
  private queue: TelemetryEvent[] = []
  private busy = false
  private failures = 0
  private notBefore = 0
  private halted = false
  private readonly o: Required<Omit<BatcherOptions, 'send'>> & Pick<BatcherOptions, 'send'>

  constructor(opts: BatcherOptions) {
    this.o = { batch: 25, maxBytes: MAX_BYTES, cap: 200, backoffMs: 30_000, maxBackoffMs: 30 * 60_000, now: Date.now, ...opts }
    this.o.batch = Math.max(1, Math.min(this.o.batch, MAX_EVENTS))
    this.o.maxBytes = Math.min(this.o.maxBytes, MAX_BYTES)
  }

  get size(): number {
    return this.queue.length
  }

  /** The endpoint said it does not exist (404): nothing more is queued or sent this run. */
  get stopped(): boolean {
    return this.halted
  }

  push(e: TelemetryEvent | undefined): void {
    if (!e || this.halted) return
    this.queue.push(e)
    if (this.queue.length > this.o.cap) this.queue.splice(0, this.queue.length - this.o.cap)
  }

  clear(): void {
    this.queue = []
    this.failures = 0
    this.notBefore = 0
  }

  /** The next batch: at most `batch` events whose body fits maxBytes. */
  private next(): TelemetryEvent[] {
    const b = this.queue.slice(0, this.o.batch)
    while (b.length > 1 && bytes(body(b)) > this.o.maxBytes) b.pop()
    return b
  }

  /** Take `batch` off the front, unless clear() ran meanwhile (then the queue no longer starts with it). */
  private shift(batch: TelemetryEvent[]): void {
    const head = this.queue.slice(0, batch.length)
    if (head.length === batch.length && head.every((e, i) => e === batch[i])) this.queue.splice(0, batch.length)
  }

  /** Send what is queued, batch by batch. Returns how many events the endpoint took. */
  async flush(): Promise<number> {
    if (this.busy || this.halted || !this.queue.length || this.o.now() < this.notBefore) return 0
    this.busy = true
    let sent = 0
    try {
      while (this.queue.length && !this.halted) {
        const batch = this.next()
        if (bytes(body(batch)) > this.o.maxBytes) {
          this.shift(batch) // one event alone is too big: it can never be sent
          continue
        }
        let r: SendResult = 'retry'
        try {
          r = await this.o.send(batch)
        } catch {
          r = 'retry'
        }
        if (r === 'stop') {
          this.halted = true
          this.queue = []
          break
        }
        if (r === 'retry') {
          this.failures++
          this.notBefore = this.o.now() + Math.min(this.o.backoffMs * 2 ** (this.failures - 1), this.o.maxBackoffMs)
          break
        }
        this.failures = 0
        this.notBefore = 0
        this.shift(batch)
        if (r === 'sent') sent += batch.length
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
export function crashEvent(line: LogLine, appVersion?: string): TelemetryEvent | undefined {
  const m = /^([a-z][a-z ]{0,30}?)(?: gone)?:\s*(.*)$/i.exec(line.text)
  const kind = (m?.[1] ?? 'error').trim().toLowerCase().replace(/\s+/g, '_').slice(0, 32)
  const at = Number.isFinite(Date.parse(line.at)) ? new Date(Date.parse(line.at)) : new Date()
  return makeEvent('crash', { kind, message: m?.[2] ?? line.text, ...(appVersion ? { app_version: appVersion } : {}) }, at)
}

/** What the app remembers about the lesson in progress, in memory only (the lesson id is never sent). */
export type LessonTrack = { lessonId?: string; active: boolean; completed: boolean; passed: Set<string> }
export const newTrack = (): LessonTrack => ({ active: false, completed: false, passed: new Set() })

const BUILT_BY = new Set(['gemini', 'claude', 'mixed', 'chapters', 'unknown', 'curated'])
const MODES = new Set(['video', 'lesson'])
const rec = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {})
const count = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.round(v) : undefined)

/**
 * An engine event main already receives (EngineLink.onEvent) → at most one usage count. Only counts, booleans and
 * contract enums: never a title, a step's text, a card's body, an id or a URL. `t` is updated in place.
 *
 *   lesson.ready (new lesson, not a replay)  lesson_built {steps, built_by, mode}
 *   step.passed (a real pass, once a step)   step_passed {already}
 *   card kind hint                           hint_used
 *   card source judge, verdict not_done      step_failed_check
 *   card kind complete                       lesson_completed {passed, skipped, total, minutes}
 *   lesson.ended before complete             lesson_abandoned {reason}
 */
export function usageEvent(msg: unknown, t: LessonTrack, now: Date = new Date()): TelemetryEvent | undefined {
  const m = rec(msg)
  const p = rec(m.payload)
  switch (m.type) {
    case 'lesson.ready': {
      const lesson = rec(p.lesson)
      const id = typeof lesson.id === 'string' ? lesson.id : undefined
      if (p.replay === true || (t.active && id !== undefined && id === t.lessonId)) return undefined
      t.lessonId = id
      t.active = true
      t.completed = false
      t.passed.clear()
      const outline = rec(lesson.outline)
      const steps = count(outline.count) ?? (Array.isArray(p.steps) ? p.steps.length : undefined)
      return makeEvent(
        'lesson_built',
        {
          ...(steps !== undefined ? { steps } : {}),
          ...(typeof lesson.builtBy === 'string' && BUILT_BY.has(lesson.builtBy) ? { built_by: lesson.builtBy } : {}),
          ...(typeof lesson.mode === 'string' && MODES.has(lesson.mode) ? { mode: lesson.mode } : {})
        },
        now
      )
    }
    case 'step.passed': {
      const id = typeof p.stepId === 'string' ? p.stepId : undefined
      if (!t.active || !id || p.skipped === true || t.passed.has(id)) return undefined
      t.passed.add(id)
      return makeEvent('step_passed', { already: p.already === true }, now)
    }
    case 'card': {
      if (!t.active) return undefined
      if (p.kind === 'complete') {
        if (t.completed) return undefined
        t.completed = true
        const r = rec(p.result)
        const props: Record<string, number> = {}
        for (const k of ['passed', 'skipped', 'total', 'minutes'] as const) {
          const n = count(r[k])
          if (n !== undefined) props[k] = n
        }
        return makeEvent('lesson_completed', props, now)
      }
      if (p.kind === 'hint') return makeEvent('hint_used', {}, now)
      if (p.source === 'judge' && p.verdict === 'not_done') return makeEvent('step_failed_check', {}, now)
      return undefined
    }
    case 'lesson.ended': {
      const was = t.active && !t.completed
      t.active = false
      t.completed = false
      t.lessonId = undefined
      t.passed.clear()
      if (!was) return undefined
      const reason = typeof p.reason === 'string' && /^[a-z_]{1,32}$/.test(p.reason) ? p.reason : 'other'
      return makeEvent('lesson_abandoned', { reason }, now)
    }
    default:
      return undefined
  }
}
