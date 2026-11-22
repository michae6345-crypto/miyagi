/**
 * Feature: errors. Is miyagi ready, in one calm line (Michael, round 5: "Engine Connecting" and "Cloud Waiting" read
 * like an alarm). Every surface that talks about starting up reads this one model, so the home rail, the pill and the
 * errors lines never disagree:
 *
 *   checking      not up yet, for less than SHOW_MS: say nothing new (a fast connect never flashes "getting ready")
 *   starting      "miyagi is getting ready": the engine or the cloud access is still starting (first start)
 *   reconnecting  "miyagi is reconnecting": it was up this launch and went away (main keeps retrying)
 *   ready         "Ready": the engine answers and the cloud access is set up (or not used on this Mac)
 *   limited       up, but the cloud says no for now (used up, paused, off, offline): a plain line, no alarm
 *   failed        only after a real failure (the engine failed or is missing, cloud access failed, five failed tries
 *                 after it was up) or BOOT_MS of waiting: "miyagi couldn't start" with Retry and Copy details
 *
 * The wait never times out while main is still working on it: never while the app's own engine is installing (each new
 * install line starts the wait over), and a local start gets LOCAL_START_MS, past main's own 60 s START_TIMEOUT_MS, so
 * main reports the real failure first. Retry is only offered when it can do something (engine-local:restart does
 * nothing while main is checking, installing or starting).
 *
 * Retry restarts what failed: the bundled engine (engine-local:restart, or the link when it runs in Terminal: errors
 * store restartEngine) or the cloud access (cloud:retry). Then the wait starts over.
 *
 * Quiet start (pill and errors lines): while first-run setup is not finished, or while the app's own engine is in its
 * first start, there is no "Can't reach miyagi", no "Reconnecting", no "Offline": the setup flow shows the engine
 * itself. A lesson on screen is never quiet (real mid-lesson errors stay as they are).
 *
 * Reads core/lesson, the onboarding store (done, cloud) and this feature's store. Writes only its own clock.
 */
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'
import { bridge, isElectron } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { copy } from '../../core/theme'
import { useOnboarding, type CloudView } from '../onboarding/store'
import { copyDetails } from './cards'
import { restartEngine, TRIES, useErrors } from './store'
import { shellName, thisDevice } from '../onboarding/device'

const capFirst = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1)

/** How long a start may take before it counts as failed. */
export const BOOT_MS = 45_000
/** The app's own engine checking or starting: main fails it itself after 60 s (main/localEngine.ts START_TIMEOUT_MS). */
export const LOCAL_START_MS = 70_000
/** Grace before "getting ready" shows at all. */
export const SHOW_MS = 700
/** After Retry: how long a failure that hasn't changed yet is still read as "starting again". */
const RETRY_HOLD_MS = 5000

export type BootPhase = 'checking' | 'starting' | 'reconnecting' | 'ready' | 'limited' | 'failed'
export type BootCause = 'engine' | 'cloud'
export type Boot = {
  phase: BootPhase
  /** The one line ("miyagi is getting ready", "Ready", "miyagi couldn't start"). */
  line: string
  /** The second, smaller line (the tooltip on the rail; under the line when it failed). */
  detail?: string
  /** What Retry restarts (failed only). */
  cause?: BootCause
}

export type BootInput = {
  connected: boolean
  local?: string
  localLine?: string
  cloud?: CloudView['state']
  cloudStatus?: string
  /** The engine was up at least once this launch. */
  everOpen: boolean
  /** Five failed tries after it was up (the errors card's threshold). */
  stopped: boolean
  timedOut: boolean
  /** The wait has lasted SHOW_MS. */
  shown: boolean
  /** Retry was just pressed: an unchanged failure reads as starting again. */
  retryHold: boolean
}

const FAILED_FIRST = `${copy.name} couldn't start`
const FAILED_AFTER = `${copy.name} isn't responding`

function failed(i: BootInput, cause: BootCause, detail: string): Boot {
  return { phase: 'failed', line: i.everOpen && cause === 'engine' ? FAILED_AFTER : FAILED_FIRST, detail, cause }
}

/** The engine's own words when it failed: main's short line, or ours. Never a path or a log. */
function localDetail(line?: string): string {
  const t = (line ?? '').trim()
  // "miyagi couldn't start its engine." (main ENGINE_FAILED_LINE) under "miyagi couldn't start" says it twice.
  if (/couldn.t start/i.test(t)) return 'The engine stopped while starting.'
  return t && t.length <= 80 && !/[/\\]/.test(t) ? t : 'The engine stopped.'
}

/** Pure: what the status says for these inputs. */
export function bootOf(i: BootInput): Boot {
  if (!i.connected) {
    if (!i.retryHold) {
      if (i.local === 'failed') return failed(i, 'engine', localDetail(i.localLine))
      if (i.local === 'missing') return failed(i, 'engine', "The engine isn't installed yet.")
      if (i.stopped) return failed(i, 'engine', 'It stopped answering.')
      // Installing is never a timeout: main is working on it and says when it fails (the clock waits too).
      if (i.timedOut && i.local !== 'installing') return failed(i, 'engine', i.local === 'external' ? `Start the engine in ${shellName()}.` : 'It took too long to start.')
    }
    if (!i.shown && !i.retryHold) return { phase: 'checking', line: '' }
    if (i.everOpen) return { phase: 'reconnecting', line: `${copy.name} is reconnecting`, detail: 'Picking up where it left off.' }
    return {
      phase: 'starting',
      line: `${copy.name} is getting ready`,
      detail: i.local === 'installing' ? 'Setting up the engine. The first time takes a minute.' : `Starting the engine on ${thisDevice()}.`
    }
  }
  if (i.cloud === 'failed' && !i.retryHold) return failed(i, 'cloud', `Couldn't set up access for ${thisDevice()}.`)
  if (i.cloud === 'minting' || (i.cloud === 'failed' && i.retryHold)) {
    if (i.timedOut) return failed(i, 'cloud', `Couldn't set up access for ${thisDevice()}.`)
    if (!i.shown && !i.retryHold) return { phase: 'checking', line: '' }
    return { phase: 'starting', line: `${copy.name} is getting ready`, detail: `Setting up access for ${thisDevice()}.` }
  }
  switch (i.cloudStatus) {
    case 'quota':
      return { phase: 'limited', line: 'Free use is used up', detail: 'It comes back tomorrow.' }
    case 'paused':
      return { phase: 'limited', line: `${copy.name} is paused`, detail: 'Try again a little later.' }
    case 'unauthorized':
      return { phase: 'limited', line: 'Access is off', detail: `${capFirst(thisDevice())}'s access was turned off.` }
    case 'offline':
      return { phase: 'limited', line: `${copy.name} is offline`, detail: 'Check your connection.' }
  }
  const where = i.local === 'external' ? `Running in ${shellName()}.` : i.cloud === 'ok' || i.cloudStatus === 'ok' ? 'Lessons build in the cloud.' : `Running on ${thisDevice()}.`
  return { phase: 'ready', line: 'Ready', detail: where }
}

/** Is it up (nothing left to wait for)? The clock runs only while it isn't. */
function upNow(connected: boolean, cloud?: CloudView['state']): boolean {
  return connected && cloud !== 'minting'
}

// ---- the clock -----------------------------------------------------------------------------------------------------

/**
 * Stage fixtures only (features/errors/web.ts, ?boot=): inputs that stand in for main while the inline mock is up.
 * Never set in Electron.
 */
export type BootStage = Partial<Pick<BootInput, 'connected' | 'local' | 'localLine' | 'cloud' | 'everOpen'>>

type Clock = {
  /** When this wait began (load, a drop, a Retry). */
  since: number
  timedOut: boolean
  shown: boolean
  retryHold: boolean
  /** Copy details: what the last press said, for 2 s. */
  copied?: 'yes' | 'no'
  stage?: BootStage
  /** Stage only (?bootMs=): a shorter BOOT_MS so the timeout can be seen. */
  bootMs: number
}

export const useBootClock = create<Clock>(() => ({ since: Date.now(), timedOut: false, shown: false, retryHold: false, bootMs: BOOT_MS }))
const setClock = useBootClock.setState
const clock = useBootClock.getState

let showTimer: ReturnType<typeof setTimeout> | undefined
let outTimer: ReturnType<typeof setTimeout> | undefined
let holdTimer: ReturnType<typeof setTimeout> | undefined

function liveUp(): boolean {
  const st = clock().stage
  const l = useLesson.getState()
  const connected = st?.connected ?? l.connected
  const cloud = st && 'cloud' in st ? st.cloud : useOnboarding.getState().cloud?.state
  return upNow(connected, cloud)
}

/** The app's own engine as main reports it (or the stage fixture). */
function liveLocal(): string | undefined {
  const st = clock().stage
  return st && 'local' in st ? st.local : useLesson.getState().localEngine?.state
}

/** How long this wait may last: longer than main's own start timeout while main is checking or starting the engine. */
function waitMs(): number {
  const local = liveLocal()
  const ms = clock().bootMs
  return local === 'checking' || local === 'starting' ? Math.max(ms, LOCAL_START_MS) : ms
}

/** The timeout. While main is installing the engine it never fires: the next install line or state arms it again. */
function armOut(): void {
  clearTimeout(outTimer)
  outTimer = setTimeout(() => {
    if (liveLocal() !== 'installing') setClock({ timedOut: true })
  }, waitMs())
}

/** A new wait: the grace, then the timeout. `show`: skip the grace (Retry: the learner just asked). */
function startWait(show = false): void {
  clearTimeout(showTimer)
  setClock({ since: Date.now(), timedOut: false, shown: show })
  if (!show) showTimer = setTimeout(() => setClock({ shown: true }), SHOW_MS)
  armOut()
}

/** Main moved on (a new engine state, or a new install line) while it's down: the timeout starts over from now. */
function progressed(): void {
  if (liveUp()) return
  if (clock().timedOut) setClock({ timedOut: false })
  armOut()
}
function endWait(): void {
  clearTimeout(showTimer)
  clearTimeout(outTimer)
  setClock({ timedOut: false, shown: false })
}

let wasUp = liveUp()
if (!wasUp) startWait()
function settle(): void {
  const up = liveUp()
  if (up === wasUp) return
  wasUp = up
  if (up) endWait()
  else startWait()
}
useLesson.subscribe((s, p) => {
  if (s.connected !== p.connected) settle()
  const state = s.localEngine?.state
  const moved = state !== p.localEngine?.state || (state === 'installing' && s.localEngine?.line !== p.localEngine?.line)
  if (moved && !clock().stage) progressed()
  // The failure the learner retried changed (starting again, or failed again): the hold is over.
  if (state !== p.localEngine?.state && clock().retryHold) dropHold()
})
useOnboarding.subscribe((s, p) => {
  if (s.cloud?.state !== p.cloud?.state) {
    settle()
    if (clock().retryHold && s.cloud?.state !== 'failed') dropHold()
  }
})
useBootClock.subscribe((s, p) => {
  if (s.stage === p.stage) return
  settle()
  if (s.stage?.local !== p.stage?.local || s.stage?.localLine !== p.stage?.localLine) progressed()
})

function dropHold(): void {
  clearTimeout(holdTimer)
  if (clock().retryHold) setClock({ retryHold: false })
}

// ---- reading it ----------------------------------------------------------------------------------------------------

function inputNow(): BootInput {
  const l = useLesson.getState()
  const o = useOnboarding.getState()
  const e = useErrors.getState()
  const c = clock()
  const live: BootInput = {
    connected: l.connected,
    local: l.localEngine?.state,
    localLine: l.localEngine?.line,
    cloud: o.cloud?.state,
    cloudStatus: l.keyStatus?.cloud,
    everOpen: e.everOpen,
    stopped: e.everOpen && !!e.link && !e.link.open && e.link.failures >= TRIES,
    timedOut: c.timedOut,
    shown: c.shown,
    retryHold: c.retryHold
  }
  return c.stage ? { ...live, ...c.stage } : live
}

/** The inputs, live (React), with the stage fixtures over them. */
export function useBootInput(): BootInput {
  const l = useLesson(useShallow((s) => ({ connected: s.connected, local: s.localEngine?.state, localLine: s.localEngine?.line, cloudStatus: s.keyStatus?.cloud })))
  const cloud = useOnboarding((s) => s.cloud?.state)
  const e = useErrors(useShallow((s) => ({ everOpen: s.everOpen, stopped: s.everOpen && !!s.link && !s.link.open && s.link.failures >= TRIES })))
  const c = useBootClock(useShallow((s) => ({ timedOut: s.timedOut, shown: s.shown, retryHold: s.retryHold, stage: s.stage })))
  const live: BootInput = { ...l, cloud, ...e, timedOut: c.timedOut, shown: c.shown, retryHold: c.retryHold }
  return c.stage ? { ...live, ...c.stage } : live
}

/** The status, live (React). */
export function useBoot(): Boot {
  return bootOf(useBootInput())
}

/** The same, outside React. */
export function bootNow(): Boot {
  return bootOf(inputNow())
}

/** First-run setup is not finished (the onboarding flag, read only). Unknown until onboarding:get answers: not pending. */
export function useSetupPending(): boolean {
  return useOnboarding((s) => s.loaded && !s.done)
}

/**
 * Quiet start: no lesson on screen, and first-run setup is not finished or the app's own engine is in its first start
 * (it has not been up this launch and has not failed). The pill and the errors lines say nothing alarming then.
 */
export function useQuietStart(): boolean {
  const setup = useSetupPending()
  const idle = useLesson((s) => !s.lesson && !s.stepId && !s.building)
  const input = useBootInput()
  const phase = bootOf(input).phase
  if (!idle) return false
  return setup || (!input.everOpen && phase !== 'failed' && phase !== 'ready' && phase !== 'limited')
}

// ---- acting on it --------------------------------------------------------------------------------------------------

/** Retry: restart what failed, show "getting ready" at once, and give it BOOT_MS again. */
export function retryBoot(): void {
  const b = bootNow()
  clearTimeout(holdTimer)
  setClock({ retryHold: true })
  holdTimer = setTimeout(dropHold, RETRY_HOLD_MS)
  startWait(true)
  const st = clock().stage
  if (st) {
    // Stage: the restart "works" after a moment (web.ts fixtures stand in for main).
    setTimeout(() => setClock({ stage: undefined }), 1600)
    return
  }
  if (b.cause === 'cloud') {
    bridge.invoke('cloud:retry').catch(() => undefined)
    return
  }
  void restartEngine()
}

/**
 * Copy details. The engine failed on this Mac (failed / missing): main's own details (engine-local:details: the state,
 * why, and the end of engine.log, keys and tokens hidden). Anything else: the errors card's allowlisted, scrubbed
 * summary, plus what the startup said.
 */
export async function copyBootDetails(): Promise<void> {
  const b = bootNow()
  const i = inputNow()
  const own = b.cause === 'engine' && (i.local === 'failed' || i.local === 'missing') && !clock().stage
  const ok = own
    ? await bridge.invoke<boolean>('engine-local:details').catch(() => false)
    : await copyDetails({ cloud: [i.cloud, i.cloudStatus].filter(Boolean).join(', ') || undefined, startup: [b.line, b.detail].filter(Boolean).join('. ') })
  setClock({ copied: ok ? 'yes' : 'no' })
  setTimeout(() => clock().copied && setClock({ copied: undefined }), 2000)
}

/** Stage fixtures (web.ts): stand in for main's engine and cloud. */
export function setBootStage(stage: BootStage | undefined, bootMs?: number): void {
  setClock({ stage, ...(bootMs ? { bootMs } : {}) })
  if (stage && !liveUp()) startWait()
}

// ---- stage fixtures (?boot=, the browser stage only) ----------------------------------------------------------------
/**
 *   starting      the engine starting, held                 installing   first-time setup, held (never times out,
 *                                                                        even with ?bootMs=)
 *   slow          starting for 3.5 s, then Ready            timeout      nothing answers: failed after ?bootMs= (4 s)
 *   failed        the engine failed (Retry: back in 1.6 s)  reconnecting it was up and went away, held
 *   cloud         cloud access setting up for 3.5 s, Ready  cloud-failed cloud access failed (Retry works)
 */
if (!isElectron && typeof location !== 'undefined') {
  const params = new URLSearchParams(location.search)
  const boot = params.get('boot') ?? ''
  const ms = Number(params.get('bootMs')) || 4000
  const down = { connected: false, everOpen: false } as const
  const fixtures: Record<string, { stage: BootStage; until?: number; bootMs?: number }> = {
    starting: { stage: { ...down, local: 'starting' } },
    installing: { stage: { ...down, local: 'installing' }, bootMs: params.get('bootMs') ? ms : undefined },
    slow: { stage: { ...down, local: 'starting' }, until: 3500 },
    timeout: { stage: { ...down, local: 'off' }, bootMs: ms },
    failed: { stage: { ...down, local: 'failed', localLine: "Couldn't start the engine." } },
    reconnecting: { stage: { connected: false, everOpen: true, local: 'running' } },
    cloud: { stage: { connected: true, everOpen: true, cloud: 'minting' }, until: 3500 },
    'cloud-failed': { stage: { connected: true, everOpen: true, cloud: 'failed' } }
  }
  const f = fixtures[boot]
  if (f) {
    setBootStage(f.stage, f.bootMs)
    if (f.until) setTimeout(() => setClock({ stage: undefined }), f.until)
  }
}
