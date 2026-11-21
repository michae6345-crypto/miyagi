/**
 * Main-process feature: telemetry (ROADMAP 1.6 crash reporting + 1.7 analytics). Off unless the learner turns on
 * Settings › Privacy "Share crash reports and usage" (prefs.shareTelemetry, off by default for everyone). No renderer
 * side, no handles, no dependency (no Sentry): a tiny batched reporter built on fetch.
 *
 *   Where:  MIYAGI_TELEMETRY_URL (a full endpoint; off / 0 disables), else <miyagi-cloud>/v1/events (cloud.ts
 *           cloudUrl()), else nowhere (a no-op). Authenticated with the install token (cloud.ts installToken()); with
 *           the cloud endpoint and no token yet, events wait in memory.
 *   What:   app_installed (once per Mac), onboarding_done (once, read from userData/onboarding.json), and crash: every
 *           new line of the error log (userData/errors/errors.json, written by features/errors.ts: main's uncaught
 *           exceptions, windows and child processes that went away, renderer errors). Each line is scrubbed again
 *           (core.ts scrubCrash: no usernames in paths, nothing quoted, no keys). Never code, files or screen text.
 *           The engine sends the lesson events itself (lesson_search ... cost_usd, server/checks/telemetry.py) to the
 *           same endpoint, only while this switch is on: EngineLink.setTelemetry folds `telemetry: "on"` into config.keys.
 *   When:   a tick every TICK_MS reads the switch (prefs.json), queues what is new and sends it in batches
 *           (core.ts Batcher: capped, backoff on failure). Switch off: the queue is dropped and the crash cursor moves
 *           to the end of the log, so turning it on later never sends crashes from before.
 *   State:  userData/telemetry/state.json {installed, onboarding, crashCursor}: flags are saved only once sent.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { arch } from 'node:os'
import { join } from 'node:path'
import { sanitizePrefs } from '../../common/prefs'
import { defineMainFeature } from '../context'
import { cloudUrl, installToken } from './cloud'
import { Batcher, crashEvent, makeEvent, newLines, telemetryUrl, type TelemetryEvent } from './telemetry/core'

const TICK_MS = 15_000
const FIRST_TICK_MS = 5_000
const SEND_TIMEOUT_MS = 10_000

type State = { installed?: boolean; onboarding?: boolean; crashCursor?: string }

function readJson<T>(file: string): T | undefined {
  try {
    return existsSync(file) ? (JSON.parse(readFileSync(file, 'utf8')) as T) : undefined
  } catch {
    return undefined
  }
}

export default defineMainFeature({
  id: 'telemetry',
  setup(ctx) {
    const envUrl = process.env.MIYAGI_TELEMETRY_URL
    const url = telemetryUrl(envUrl, cloudUrl())
    const custom = !!envUrl?.trim()
    const data = ctx.app.getPath('userData')
    const dir = join(data, 'telemetry')
    const stateFile = join(dir, 'state.json')
    let state: State = readJson<State>(stateFile) ?? {}
    const save = (): void => {
      try {
        mkdirSync(dir, { recursive: true, mode: 0o700 })
        writeFileSync(stateFile, JSON.stringify(state), { mode: 0o600 })
      } catch {
        console.warn('[telemetry] could not save its state')
      }
    }

    const on = (): boolean => !!url && sanitizePrefs(readJson<unknown>(join(data, 'prefs.json'))).shareTelemetry === true

    const send = async (events: TelemetryEvent[]): Promise<boolean> => {
      const token = installToken()
      if (!url || (!token && !custom) || !on()) return false
      const abort = new AbortController()
      const timer = setTimeout(() => abort.abort(), SEND_TIMEOUT_MS)
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify({ source: 'app', app: ctx.app.getVersion(), platform: `${process.platform}/${arch()}`, events }),
          signal: abort.signal,
          redirect: 'error'
        })
        return res.ok
      } catch {
        return false // never the error: it can quote the request
      } finally {
        clearTimeout(timer)
      }
    }
    const batcher = new Batcher({ send })
    /** Flags queued but not sent yet: saved once the queue drains. */
    let pending: State = {}

    const crashFeed = (): ReturnType<typeof newLines> => newLines(readJson<unknown>(join(data, 'errors', 'errors.json')), state.crashCursor)

    let ticking = false
    const tick = async (): Promise<void> => {
      if (ticking) return
      ticking = true
      try {
        const enabled = on()
        ctx.engine.setTelemetry(enabled)
        if (!enabled) {
          batcher.clear()
          pending = {}
          const last = crashFeed().at(-1)
          if (last) {
            state = { ...state, crashCursor: last.at }
            save()
          }
          return
        }
        if (!state.installed && !pending.installed) {
          batcher.push(makeEvent('app_installed', { app_version: ctx.app.getVersion(), os: process.platform, arch: arch() }))
          pending.installed = true
        }
        const onboarded = readJson<{ done?: unknown }>(join(data, 'onboarding.json'))?.done === true
        if (onboarded && !state.onboarding && !pending.onboarding) {
          batcher.push(makeEvent('onboarding_done'))
          pending.onboarding = true
        }
        const lines = crashFeed()
        for (const l of lines) batcher.push(crashEvent(l))
        if (lines.length) {
          state = { ...state, crashCursor: lines[lines.length - 1].at } // queued: never queued twice
          save()
        }
        await batcher.flush()
        if (batcher.size === 0 && (pending.installed || pending.onboarding)) {
          state = { ...state, ...pending }
          pending = {}
          save()
        }
      } finally {
        ticking = false
      }
    }

    const first = setTimeout(() => void tick(), FIRST_TICK_MS)
    first.unref?.()
    const every = setInterval(() => void tick(), TICK_MS)
    every.unref?.()
    ctx.app.on('will-quit', () => {
      clearTimeout(first)
      clearInterval(every)
    })
  }
})
