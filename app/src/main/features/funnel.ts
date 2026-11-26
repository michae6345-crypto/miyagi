/**
 * Main-process feature: funnel (activation analytics). No renderer side, no handles.
 *
 *   Records, on this Mac, the first time each activation milestone happened (funnel/core.ts):
 *     first_launch          this feature's first setup on this Mac
 *     signed_in             the install was linked to a Supabase user (userData/cloud-link.json linkedAt, cloudLink.ts)
 *     permissions_granted   Screen Recording AND Accessibility both granted (read without prompting, like permissions.ts)
 *     lesson_started        the first lesson ready (engine lesson.ready, not a replay)
 *     step_passed           the first step the learner passed (engine step.passed, not skipped)
 *     lesson_finished       the first completion card (engine card kind complete)
 *   Local file: userData/funnel/state.json {at: {name: iso}, sent: {name: iso}}. Names and times only.
 *
 *   Sends them to miyagi-cloud POST /v1/funnel (core.ts has the contract) only when ALL hold:
 *     - the learner's Settings › Privacy "Share crash reports and usage" switch is on (prefs.shareTelemetry, off by
 *       default), and MIYAGI_TELEMETRY isn't off for the run;
 *     - the launch gate is open (main/gate.ts);
 *     - the learner is signed in and this install is linked (cloud-link.json): the cloud joins install → user itself;
 *     - an install token exists (cloud.ts).
 *   Milestones from before the switch was turned on are sent once it is on: a time is all they carry.
 *   A 202 marks those exact times sent; 404 (older cloud) or a refusal (400/413/422) stops for the run; anything else
 *   retries on the next tick.
 *
 * Core requests (app/agents/funnel.md): wipe userData/funnel on account delete; one line in the Privacy facts.
 */
import { systemPreferences } from 'electron'
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { sanitizePrefs } from '../../common/prefs'
import { defineMainFeature } from '../context'
import { gateIsOpen } from '../gate'
import { installToken, type InstallInfo } from './cloud'
import { readRecord } from './cloudLink'
import { body, cleanState, funnelUrl, lessonTracker, mark, markSent, unsent, MAX_BYTES, type FunnelState, type Milestone } from './funnel/core'
import { switchedOff } from './telemetry/core'

const TICK_MS = 30_000
const FIRST_TICK_MS = 8_000
const SEND_TIMEOUT_MS = 10_000

export type FunnelDeps = {
  fetch: (input: string, init: RequestInit) => Promise<Response>
  install: () => InstallInfo | undefined
  /** prefs.shareTelemetry, read live. */
  enabled: () => boolean
  gateOpen: () => boolean
  /** cloud-link.json: when this install was linked to the signed-in learner, or undefined. */
  linkedAt: () => string | undefined
  /** Screen Recording and Accessibility both granted right now (never prompts). */
  permissionsGranted: () => boolean
  stateFile: string
  off?: string
  now?: () => Date
}

export type Funnel = {
  /** An engine event (EngineLink.onEvent). */
  track(e: unknown): void
  /** Read the polled milestones, save, send what is new when allowed. */
  tick(): Promise<void>
  state(): FunnelState
}

export function createFunnel(d: FunnelDeps): Funnel {
  const now = d.now ?? (() => new Date())
  const lessons = lessonTracker()
  let state = loadState(d.stateFile)
  let stopped = false
  let sending = false

  const save = (): void => {
    try {
      mkdirSync(dirname(d.stateFile), { recursive: true })
      const tmp = `${d.stateFile}.tmp`
      writeFileSync(tmp, JSON.stringify(state), { mode: 0o600 })
      renameSync(tmp, d.stateFile)
    } catch {
      console.warn('[funnel] could not save its state')
    }
  }
  const record = (m: Milestone, when: Date | string): void => {
    if (mark(state, m, when)) save()
  }

  record('first_launch', now()) // a no-op after the first launch: the earliest time stays

  const allowed = (): boolean => !stopped && !switchedOff(d.off) && d.enabled() && d.gateOpen() && d.linkedAt() !== undefined

  return {
    state: () => state,
    track(e) {
      const m = lessons.track(e, now())
      if (m) record(m, now())
    },
    async tick() {
      const linked = d.linkedAt()
      if (linked) record('signed_in', linked)
      if (!state.at.permissions_granted && d.permissionsGranted()) record('permissions_granted', now())
      if (sending || !allowed()) return
      const info = d.install()
      const url = funnelUrl(info?.host)
      const items = unsent(state)
      if (!info || !url || !items.length) return
      const payload = body(items)
      if (payload.length > MAX_BYTES) return
      sending = true
      const ctl = new AbortController()
      const timer = setTimeout(() => ctl.abort(), SEND_TIMEOUT_MS)
      try {
        const res = await d.fetch(url, {
          method: 'POST',
          headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' },
          body: payload,
          signal: ctl.signal
        })
        if (res.status === 202 || res.status === 200) {
          markSent(state, items)
          save()
        } else if ([400, 404, 413, 422].includes(res.status)) {
          stopped = true // an older cloud or a contract mismatch: not again this run
          if (res.status !== 404) console.warn('[funnel] the cloud refused the funnel:', res.status)
        }
      } catch {
        // offline or timed out: the next tick tries again
      } finally {
        clearTimeout(timer)
        sending = false
      }
    }
  }
}

function loadState(file: string): FunnelState {
  try {
    return cleanState(existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : undefined)
  } catch {
    return cleanState(undefined)
  }
}

function readJson(file: string): unknown {
  try {
    return existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : undefined
  } catch {
    return undefined
  }
}

/** Both macOS grants, read without prompting. Off macOS there is nothing to grant. */
function bothGranted(): boolean {
  if (process.platform !== 'darwin') return true
  try {
    return systemPreferences.getMediaAccessStatus('screen') === 'granted' && systemPreferences.isTrustedAccessibilityClient(false)
  } catch {
    return false
  }
}

export default defineMainFeature({
  id: 'funnel',
  setup(ctx) {
    const data = ctx.app.getPath('userData')
    const funnel = createFunnel({
      fetch: (input, init) => globalThis.fetch(input, init),
      install: installToken,
      enabled: () => sanitizePrefs(readJson(join(data, 'prefs.json'))).shareTelemetry === true,
      gateOpen: gateIsOpen,
      linkedAt: () => readRecord(join(data, 'cloud-link.json'))?.linkedAt,
      permissionsGranted: bothGranted,
      stateFile: join(data, 'funnel', 'state.json'),
      off: process.env.MIYAGI_TELEMETRY
    })
    ctx.engine.onEvent((e) => funnel.track(e))

    const first = setTimeout(() => void funnel.tick(), FIRST_TICK_MS)
    first.unref?.()
    const every = setInterval(() => void funnel.tick(), TICK_MS)
    every.unref?.()
    ctx.app.on('will-quit', () => {
      clearTimeout(first)
      clearInterval(every)
    })
  }
})
