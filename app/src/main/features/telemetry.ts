/**
 * Main-process feature: telemetry (ROADMAP 1.6 crash reporting + 1.7 analytics). Off unless the learner turns on
 * Settings › Privacy "Share crash reports and usage" (prefs.shareTelemetry, off by default for everyone). No renderer
 * side, no handles, no dependency (no Sentry): a tiny batched reporter built on fetch.
 *
 *   Where:  POST <miyagi-cloud>/v1/events, the host that minted the install token (cloud.ts installToken().host), with
 *           Authorization: Bearer <install token>. No token (cloud off, not minted yet, healing): nothing is sent, events
 *           wait in memory (capped). MIYAGI_TELEMETRY=off turns it off for a run.
 *   What:   only {"events": [{name, at, props}]} (core.ts has the contract): app_installed (once per Mac),
 *           onboarding_done (once, read from userData/onboarding.json), lesson counts read from the engine events main
 *           already receives (core.ts usageEvent: lesson_built, step_passed, step_failed_check, hint_used,
 *           lesson_completed, lesson_abandoned; counts and enums only), and crash: every new line of the error log
 *           (userData/errors/errors.json, features/errors.ts), scrubbed again (core.ts scrubCrash). Never screen text,
 *           code, file paths, emails or tokens.
 *   When:   only while the switch is on AND the launch gate is open (main/gate.ts: signed in or guest, setup done or put
 *           off). A tick every TICK_MS reads the switch (prefs.json), queues what is new and sends it in batches
 *           (core.ts Batcher: at most 50 events and 32 KB a request, backoff on failure). A 404 (an older cloud without
 *           the route) drops everything silently and stops for the run.
 *   Off:    the queue is dropped and the crash mark moves to the end of the log, so turning it on later never sends
 *           crashes from before.
 *   State:  userData/telemetry/state.json {installed, onboarding, crashMark}: flags are saved only once sent.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { arch } from 'node:os'
import { dirname, join } from 'node:path'
import { sanitizePrefs } from '../../common/prefs'
import { defineMainFeature } from '../context'
import { gateIsOpen } from '../gate'
import { installToken, type InstallInfo } from './cloud'
import { Batcher, body, crashEvent, makeEvent, newLines, newTrack, resultFor, switchedOff, telemetryUrl, usageEvent, type SendResult, type TelemetryEvent } from './telemetry/core'

const TICK_MS = 15_000
const FIRST_TICK_MS = 5_000
const SEND_TIMEOUT_MS = 10_000

type State = { installed?: boolean; onboarding?: boolean; crashMark?: string }

function readJson<T>(file: string): T | undefined {
  try {
    return existsSync(file) ? (JSON.parse(readFileSync(file, 'utf8')) as T) : undefined
  } catch {
    return undefined
  }
}

export type ReporterDeps = {
  fetch: (input: string, init: RequestInit) => Promise<Response>
  /** cloud.ts installToken(): the token and the host that minted it. */
  install: () => InstallInfo | undefined
  /** The learner's switch (prefs.shareTelemetry), read live. */
  enabled: () => boolean
  /** main/gate.ts gateIsOpen(): nothing leaves before the login gate opens. */
  gateOpen: () => boolean
  /** userData/errors/errors.json, parsed (or undefined). */
  errorLog: () => unknown
  /** Setup finished (userData/onboarding.json done). */
  onboarded: () => boolean
  stateFile: string
  appVersion: string
  os: string
  arch: string
  /** MIYAGI_TELEMETRY: off / 0 / false / no turns telemetry off for the run. */
  off?: string
  batcher?: { backoffMs?: number; now?: () => number }
}

export type Reporter = {
  tick: () => Promise<void>
  /** An engine event (EngineLink.onEvent): counted when it is a lesson milestone and sharing is allowed. */
  track: (e: unknown) => void
  readonly queued: number
  readonly stopped: boolean
}

export function createReporter(d: ReporterDeps): Reporter {
  let state: State = readJson<State>(d.stateFile) ?? {}
  const save = (): void => {
    try {
      mkdirSync(dirname(d.stateFile), { recursive: true, mode: 0o700 })
      writeFileSync(d.stateFile, JSON.stringify(state), { mode: 0o600 })
    } catch {
      console.warn('[telemetry] could not save its state')
    }
  }
  const endpoint = (): { url: string; token: string } | undefined => {
    const info = d.install()
    const url = telemetryUrl(d.off, info?.host)
    return info?.token && url ? { url, token: info.token } : undefined
  }
  /** Sharing allowed right now: not switched off for the run, the learner's switch on, the gate open. */
  const allowed = (): boolean => !switchedOff(d.off) && d.enabled() && d.gateOpen()

  const send = async (events: TelemetryEvent[]): Promise<SendResult> => {
    const to = endpoint()
    if (!to || !allowed()) return 'retry'
    const abort = new AbortController()
    const timer = setTimeout(() => abort.abort(), SEND_TIMEOUT_MS)
    try {
      const res = await d.fetch(to.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${to.token}` },
        body: body(events),
        signal: abort.signal,
        redirect: 'error'
      })
      return resultFor(res.status)
    } catch {
      return 'retry' // never the error: it can quote the request
    } finally {
      clearTimeout(timer)
    }
  }
  const batcher = new Batcher({ send, ...d.batcher })
  /** Flags queued but not sent yet: saved once the queue drains. */
  let pending: State = {}
  /** The switch was seen off this run: the next "on" starts the crash feed from there. */
  let sawOff = false
  const lesson = newTrack()

  const moveMarkToEnd = (): void => {
    const last = newLines(d.errorLog(), state.crashMark).at(-1)
    if (last) {
      state = { ...state, crashMark: last.at }
      save()
    }
  }

  let ticking = false
  const tick = async (): Promise<void> => {
    if (ticking) return
    ticking = true
    try {
      if (!d.enabled() || switchedOff(d.off)) {
        batcher.clear()
        pending = {}
        sawOff = true
        moveMarkToEnd()
        return
      }
      if (batcher.stopped || !d.gateOpen()) return
      if (sawOff || state.crashMark === undefined) {
        // Turned on just now, or the first time ever: crashes logged before that stay on this Mac.
        sawOff = false
        if (state.crashMark === undefined) {
          state = { ...state, crashMark: new Date().toISOString() }
          save()
        }
        moveMarkToEnd()
      }
      if (!state.installed && !pending.installed) {
        batcher.push(makeEvent('app_installed', { app_version: d.appVersion, os: d.os, arch: d.arch }))
        pending.installed = true
      }
      if (d.onboarded() && !state.onboarding && !pending.onboarding) {
        batcher.push(makeEvent('onboarding_done'))
        pending.onboarding = true
      }
      const lines = newLines(d.errorLog(), state.crashMark)
      for (const l of lines) batcher.push(crashEvent(l, d.appVersion))
      if (lines.length) {
        state = { ...state, crashMark: lines[lines.length - 1].at } // queued: never queued twice
        save()
      }
      if (!endpoint()) return // no install token yet: events wait
      await batcher.flush()
      if (batcher.size === 0 && !batcher.stopped && (pending.installed || pending.onboarding)) {
        state = { ...state, ...pending }
        pending = {}
        save()
      }
    } finally {
      ticking = false
    }
  }

  const track = (e: unknown): void => {
    const ev = usageEvent(e, lesson) // always, so the lesson in progress is known when sharing turns on
    if (ev && !batcher.stopped && allowed()) batcher.push(ev)
  }

  return {
    tick,
    track,
    get queued() {
      return batcher.size
    },
    get stopped() {
      return batcher.stopped
    }
  }
}

export default defineMainFeature({
  id: 'telemetry',
  setup(ctx) {
    const data = ctx.app.getPath('userData')
    const reporter = createReporter({
      fetch: (input, init) => globalThis.fetch(input, init),
      install: installToken,
      enabled: () => sanitizePrefs(readJson<unknown>(join(data, 'prefs.json'))).shareTelemetry === true,
      gateOpen: gateIsOpen,
      errorLog: () => readJson<unknown>(join(data, 'errors', 'errors.json')),
      onboarded: () => readJson<{ done?: unknown }>(join(data, 'onboarding.json'))?.done === true,
      stateFile: join(data, 'telemetry', 'state.json'),
      appVersion: ctx.app.getVersion(),
      os: process.platform,
      arch: arch(),
      off: process.env.MIYAGI_TELEMETRY
    })
    ctx.engine.onEvent((e) => reporter.track(e))

    const first = setTimeout(() => void reporter.tick(), FIRST_TICK_MS)
    first.unref?.()
    const every = setInterval(() => void reporter.tick(), TICK_MS)
    every.unref?.()
    ctx.app.on('will-quit', () => {
      clearTimeout(first)
      clearInterval(every)
    })
  }
})
