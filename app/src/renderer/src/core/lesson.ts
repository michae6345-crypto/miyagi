/**
 * Core lesson state: what every feature can read. Feature-specific state (cards, diagram,
 * spotlight, search, voice…) lives in each feature's own store, subscribed via core/bus.
 *
 * Owner: core. Agents READ this store freely; add fields only through a small "core:" commit.
 */
import { useMemo } from 'react'
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'
import type { CheckStatus, Source, StepSummary, VideoSegment } from '../../../../../shared/contracts/events'
import type { ConfigStatus, Payload } from '../../../common/wire'
import { bridge } from '../bridge'
import { emitUi, onMessage, onUi, setGate } from './bus'
// Circular on purpose (shortcuts reads this store inside functions only; neither file uses the other at load).
import { usePressed } from './shortcuts'

export type CheckItem = { id: string; label: string; status: CheckStatus; detail?: string }
export type Status = 'watching' | 'offtrack' | 'passed'
export type Rect = { x: number; y: number; w: number; h: number }

/** Optional extras the mock sends today (the contract allows adding fields). */
export type Offtrack = Payload<'offtrack'> & {
  reason?: string
  curve?: { label: string; yours: number[]; tutorial: number[] }
}

/**
 * What the video should do, and why: the player follows it. `kind` tells a follower a seek from a pause/play,
 * and from a jump the app itself asked for (card link, chapter click), even when `t` didn't change.
 */
export type VideoIntent = { t: number; playing: boolean; at: number; kind: 'seek' | 'pause' | 'play' | 'jump' }

/** lesson.ready's lesson: id, title, sources, plus complete / builtBy / goalMatch when the engine sends them. */
export type LessonInfo = Payload<'lesson.ready'>['lesson']

type LessonState = {
  connected: boolean
  lesson?: LessonInfo
  steps: StepSummary[]
  /** false while a long video is still building part by part (lesson.updated appends steps). */
  complete: boolean
  parts?: { done: number; failed: number; total: number }
  /** step.passed with pending: no next step YET ("Next part is still building"). Cleared by lesson.updated / step.started. */
  pendingNext: boolean
  stepId?: string
  stepTitle: string
  instructions: string
  stepVideo?: VideoSegment
  checks: CheckItem[]
  passed: string[]
  /** Steps the learner skipped (step.passed skipped): done, but never shown green. */
  skipped: string[]
  /** Between "Build lesson" and the first step.started. */
  building: boolean
  buildingMessage?: string
  buildingProgress?: number
  /** Seconds since the build started (the 1 s heartbeat). Show it, never animate on it. */
  buildingElapsed?: number
  /** The active off-track diagnosis (cleared when the step starts or passes). Drives the amber status. */
  offtrack?: Offtrack
  /** Increments on every step.passed: drives the pill's green flash. */
  passFlash: number
  lastPassed?: { stepId: string; summary?: string; checks: CheckItem[]; at: number }
  /** What the engine wants the video to do; the player follows it and reports back with video.state. */
  video: VideoIntent
  engineState?: Payload<'status'>['state']
  seen?: Payload<'screen.seen'>
  keyStatus?: ConfigStatus['payload']
  error?: { message: string; at: number }
  /** One short line for the pill (~5 s): engine errors, offline, an off-screen spotlight caption. See notify(). */
  notice?: Notice
  /** The engine this app starts on a Mac (main/localEngine.ts): installing, starting, missing, failed… */
  localEngine?: { state: string; line?: string; logs?: string; reason?: string }
  /** This lesson came from the launcher's Demo option (the curated lesson): no "Claude wrote this lesson" line. */
  demo: boolean
  // ---- v2 (W0-5) ----
  /** engine.hello: what this engine speaks. Absent until it says hello (an older engine never does). */
  hello?: Payload<'engine.hello'>
  /** Every queued notice, oldest first (notify(); `notice` above stays the latest for older readers). */
  notices: Notice[]
  /** The current step as step.started sent it (where / then / kind / what / code ...). */
  step?: Payload<'step.started'>
  /** status.detail: what the engine is doing right now ("Checking your cell"). */
  statusDetail?: string
  /** status busy: the provider is overloaded; retrying in retryInS seconds from `at`. */
  busy?: { retryInS?: number; at: number }
  /** lesson.paused until lesson.resumed. */
  paused?: Payload<'lesson.paused'>
  /** blocker events by kind, until { clear: true }. */
  blockers: Partial<Record<BlockerKind, Payload<'blocker'>>>
  /** lesson.building's v2 fields while building. */
  build?: Pick<Payload<'lesson.building'>, 'stage' | 'phases' | 'etaS' | 'source'>
  /** The last build that failed (lesson.building failed). silent: the learner moved on, show no failure card. */
  buildFailed?: Pick<Payload<'lesson.building'>, 'failCode' | 'failReason' | 'alternatives' | 'source' | 'silent'> & { at: number }
}

/** v2: notices carry an id (the same id replaces its earlier notice) and an optional time to live. */
export type Notice = { text: string; tone: 'error' | 'info'; at: number; id?: string; ttlMs?: number }
export type BlockerKind = Payload<'blocker'>['kind']

const blank = {
  lesson: undefined,
  steps: [],
  complete: true,
  parts: undefined,
  pendingNext: false,
  stepId: undefined,
  stepTitle: '',
  instructions: '',
  stepVideo: undefined,
  checks: [],
  passed: [],
  skipped: [],
  building: false,
  buildingMessage: undefined,
  buildingProgress: undefined,
  buildingElapsed: undefined,
  offtrack: undefined,
  passFlash: 0,
  lastPassed: undefined,
  video: { t: 0, playing: false, at: 0, kind: 'seek' },
  engineState: undefined,
  seen: undefined,
  error: undefined,
  notice: undefined,
  demo: false,
  notices: [],
  step: undefined,
  statusDetail: undefined,
  busy: undefined,
  paused: undefined,
  blockers: {},
  build: undefined,
  buildFailed: undefined
} satisfies Partial<LessonState>

export const useLesson = create<LessonState>(() => ({ connected: false, ...blank }))

const set = useLesson.setState
const get = useLesson.getState

/** Called by the launcher when "Build lesson" fires (before the engine answers). */
export const startBuild = (): void => set({ building: true })
/** The build was called off before it started (preflight "Pick another"): drop the building pill. */
export const stopBuild = (): void => set({ building: false, buildingMessage: undefined, buildingProgress: undefined, buildingElapsed: undefined })
export const setConnected = (connected: boolean): void => {
  // (Re)connected: the engine's snapshot is the truth (after an engine restart it's just "idle"),
  // so drop the lesson this window was showing before the snapshot refills it.
  // Held for a moment: if the engine replays the same lesson (same id), the UI stays as it was (Michael, test 6:
  // no jumping back to the "Your lesson" sheet); anything else, or nothing, and the reset goes ahead.
  if (connected && !get().connected) holdReconnectReset()
  // Dropped mid-build: no `failed` can arrive any more, so drop the building UI too (audit P1-3).
  if (!connected && get().building) set({ building: false, buildingMessage: undefined, buildingProgress: undefined, buildingElapsed: undefined })
  // Nothing is thinking on a dead socket.
  if (!connected && get().engineState === 'thinking') set({ engineState: undefined })
  // v2: the next engine says hello again (it may be an older one): no v2 command goes out until it does.
  if (!connected) set({ hello: undefined, busy: undefined, statusDetail: undefined })
  set({ connected })
}

onUi('reset', () => set({ ...blank }))

const REPLAY_WAIT_MS = 2000
/** lesson.ended reason "interrupted" (an engine deploy): how long the screen stays as it is for the engine to come back. */
const INTERRUPT_WAIT_MS = 30000
let held: { id?: string; timer: ReturnType<typeof setTimeout> } | undefined
function holdReconnectReset(wait = REPLAY_WAIT_MS): void {
  if (held) return
  const id = get().lesson?.id
  if (!id) {
    emitUi('reset', { scope: 'lesson', reason: 'reconnect' })
    return
  }
  held = {
    id,
    timer: setTimeout(() => {
      held = undefined
      emitUi('reset', { scope: 'lesson', reason: 'reconnect' })
    }, wait)
  }
}

/**
 * Idempotent lesson.ready (Michael, test 6): the same lesson id as the one on screen (a replay on reconnect, a
 * resent snapshot) merges its steps like lesson.updated and is dropped before any feature resets its UI.
 * A different id is a new lesson and goes through as before.
 */
setGate((msg) => {
  if (msg.type !== 'lesson.ready') return true
  const p = msg.payload as Payload<'lesson.ready'>
  const cur = get().lesson
  const same = !!cur?.id && cur.id === p.lesson?.id
  if (held) {
    clearTimeout(held.timer)
    held = undefined
    if (!same) emitUi('reset', { scope: 'lesson', reason: 'reconnect' })
  }
  if (!same) return true
  set((s) => {
    const incoming = new Map(p.steps.map((x) => [x.id, x]))
    const kept = s.steps.map((x) => incoming.get(x.id) ?? x)
    const known = new Set(s.steps.map((x) => x.id))
    return { lesson: p.lesson, steps: [...kept, ...p.steps.filter((x) => !known.has(x.id))], complete: p.lesson.complete !== false }
  })
  return false
})

/**
 * The engine ended the lesson (end_lesson, a new learn, POST /end): blank every lesson-side store.
 * scope "lesson" tells the launcher to keep its query and results (a new search may be in flight).
 */
onMessage('lesson.ended', (p) => {
  // reason "interrupted" (claude/stable-nosave): an engine deploy, and it comes back with the same lesson. Keep the
  // screen, say so quietly, and reset only if no replay of this lesson arrives.
  if ((p.reason as string | undefined) === 'interrupted' && get().lesson?.id) {
    notify('Reconnecting…')
    holdReconnectReset(INTERRUPT_WAIT_MS)
    return
  }
  emitUi('reset', { scope: 'lesson', reason: p.reason })
})

onMessage('lesson.building', (p) =>
  // failed: the build ended in error (an `error` + status idle follow): drop the building UI.
  // v2: keep why (buildFailed) for the failure card; `silent` = the learner already moved on, so no card (A7 reads it).
  p.failed
    ? set({
        building: false,
        buildingMessage: undefined,
        buildingProgress: undefined,
        buildingElapsed: undefined,
        build: undefined,
        buildFailed: { failCode: p.failCode, failReason: p.failReason, alternatives: p.alternatives, source: p.source ?? get().build?.source, silent: p.silent === true, at: Date.now() }
      })
    : set({
        building: true,
        buildingMessage: p.message,
        buildingProgress: p.progress,
        buildingElapsed: p.elapsedS,
        buildFailed: undefined,
        ...(p.stage || p.phases || p.etaS !== undefined || p.source ? { build: { ...get().build, stage: p.stage, phases: p.phases, etaS: p.etaS, source: p.source ?? get().build?.source } } : {})
      })
)
/** The mode of the last learn the launcher sent. lesson.ready doesn't say "demo", so the app remembers what it asked for. */
let learnMode: string | undefined
export function noteLearnMode(mode: string | undefined): void {
  learnMode = mode
}

onMessage('lesson.ready', (p) => set({ ...blank, lesson: p.lesson, steps: p.steps, complete: p.lesson.complete !== false, building: true, demo: learnMode === 'demo' }))
/**
 * A long video's next part: the engine sends only the NEW steps (contract: appended, ids stable), sometimes an
 * empty list with complete:true. Merge by id (a known id is updated in place) so the list never shrinks.
 * Rows already shown must not re-animate.
 */
onMessage('lesson.updated', (p) =>
  set((s) => {
    const incoming = new Map(p.steps.map((x) => [x.id, x]))
    const kept = s.steps.map((x) => incoming.get(x.id) ?? x)
    const known = new Set(s.steps.map((x) => x.id))
    const steps = [...kept, ...p.steps.filter((x) => !known.has(x.id))]
    return { steps, complete: p.complete, parts: p.parts ?? s.parts, pendingNext: false }
  })
)
onMessage('step.started', (p) => {
  const s = get()
  // replay: true (claude/stable-nosave): the step on screen sent again. Keep its checks and progress.
  if ((p as typeof p & { replay?: boolean }).replay && p.stepId === s.stepId) return
  const pos = s.steps.findIndex((x) => x.id === p.stepId)
  const before = pos > 0 ? s.steps.slice(0, pos).map((x) => x.id) : []
  set({
    building: false,
    buildingMessage: undefined,
    build: undefined,
    step: p,
    stepId: p.stepId,
    stepTitle: p.title,
    instructions: p.instructions,
    stepVideo: p.video ?? undefined,
    checks: [],
    passed: Array.from(new Set([...s.passed, ...before])),
    pendingNext: false,
    offtrack: undefined
  })
})
onMessage('check.updated', (p) => {
  const s = get()
  if (p.stepId !== s.stepId) return
  const item: CheckItem = { id: p.checkId, label: p.label, status: p.status, detail: p.detail }
  const exists = s.checks.some((c) => c.id === p.checkId)
  set({ checks: exists ? s.checks.map((c) => (c.id === p.checkId ? item : c)) : [...s.checks, item] })
})
onMessage('step.passed', (p) => {
  const s = get()
  const summary = (p as typeof p & { summary?: string }).summary
  // already: true (claude/stable-nosave): a step done before (a resume). Mark it done quietly: no green flash, no
  // step-done card; the engine's own "You already did..." card follows.
  if (p.skipped || (p as typeof p & { already?: boolean }).already) {
    if (!p.skipped) {
      set({ passed: Array.from(new Set([...s.passed, p.stepId])), pendingNext: p.pending === true, offtrack: undefined })
      return
    }
    // Skipped, not passed: no green flash, no "Good. Now the next one."
    set({ passed: Array.from(new Set([...s.passed, p.stepId])), skipped: Array.from(new Set([...s.skipped, p.stepId])), pendingNext: p.pending === true, offtrack: undefined })
    return
  }
  set({
    passed: Array.from(new Set([...s.passed, p.stepId])),
    passFlash: s.passFlash + 1,
    pendingNext: p.pending === true,
    offtrack: undefined,
    lastPassed: { stepId: p.stepId, summary, checks: s.checks, at: Date.now() }
  })
})
/**
 * A dismissAfterMs this short is the engine withdrawing a card: its culprit lines or diagnosis went away (Michael,
 * test 8 engine work, integration/live 74e11cd). Not in shared/contracts yet: read it off the payload.
 */
export const WITHDRAW_MS = 50
export const dismissAfter = (p: object): number | undefined => {
  const ms = (p as { dismissAfterMs?: unknown }).dismissAfterMs
  return typeof ms === 'number' && ms > 0 ? ms : undefined
}
/** Ends the off-track state (the pill's ring and hover peek) for this step, or whatever step it's on. */
export function clearOfftrack(stepId?: string): void {
  const o = get().offtrack
  if (o && (!stepId || o.stepId === stepId)) set({ offtrack: undefined })
}
let offtrackTimer: ReturnType<typeof setTimeout> | undefined
onMessage('offtrack', (p) => {
  clearTimeout(offtrackTimer)
  const after = dismissAfter(p)
  if (after !== undefined && after <= WITHDRAW_MS) return clearOfftrack(p.stepId)
  const o = p as Offtrack
  set({ offtrack: o })
  if (after !== undefined) offtrackTimer = setTimeout(() => get().offtrack === o && set({ offtrack: undefined }), after)
})
onMessage('video.seek', (p) => set({ video: { t: p.t, playing: p.play, at: Date.now(), kind: 'seek' } }))
onMessage('video.pause', () => set({ video: { ...get().video, playing: false, at: Date.now(), kind: 'pause' } }))
onMessage('video.play', () => set({ video: { ...get().video, playing: true, at: Date.now(), kind: 'play' } }))

/**
 * The app itself moves the video (a card's "7:00" link, a chapter click). Sets the intent here AND in every
 * other window (in Electron the player is its own window), so features never relay it themselves.
 */
export function seekVideo(t: number, play = true): void {
  const video: VideoIntent = { t, playing: play, at: Date.now(), kind: 'jump' }
  set({ video })
  bridge.emit('video:intent', video)
}
// Another window called seekVideo (main relays it to every window except the sender).
bridge.on('video:intent', (v) => set({ video: { ...(v as VideoIntent), at: Date.now() } }))
onMessage('status', (p) =>
  set({
    engineState: p.state,
    // v2: detail travels with every status; a status without one clears it. busy comes and goes with its state.
    statusDetail: typeof p.detail === 'string' && p.detail.trim() ? p.detail.trim() : undefined,
    busy: p.state === 'busy' ? { retryInS: typeof p.retryInS === 'number' && p.retryInS >= 0 ? p.retryInS : undefined, at: Date.now() } : undefined
  })
)

// ---- v2 (W0-5) engine events ------------------------------------------------------------------------------------
onMessage('engine.hello', (p) => set({ hello: { ...p, capabilities: Array.isArray(p.capabilities) ? p.capabilities.filter((c) => typeof c === 'string') : [] } }))
onMessage('lesson.paused', (p) => set({ paused: p }))
onMessage('lesson.resumed', () => set({ paused: undefined }))
onMessage('blocker', (p) =>
  set((s) => {
    const next = { ...s.blockers }
    if (p.clear) delete next[p.kind]
    else next[p.kind] = p
    return { blockers: next }
  })
)
onMessage('lesson.ended', (p) => {
  // "interrupted" keeps the screen for the engine to come back (see above).
  if ((p.reason as string | undefined) === 'interrupted' && get().lesson?.id) return
  set({ paused: undefined, blockers: {}, statusDetail: undefined, busy: undefined })
})
onMessage('screen.seen', (p) => set({ seen: p }))
onMessage('config.status', (p) => set({ keyStatus: p }))
// The engine this app starts itself (built Mac app). Read once, then follow main's updates.
bridge.onFeature('engine-local', (p) => useLesson.setState({ localEngine: p as LessonState['localEngine'] }))
bridge.invoke<LessonState['localEngine']>('engine-local:get').then((p) => p && useLesson.setState({ localEngine: p })).catch(() => undefined)

onMessage('error', (p) => {
  set({ error: { message: p.message, at: Date.now() } })
  notify(p.message, 'error', { id: 'engine-error' })
})

/**
 * Show one short line on the pill for ~5 s (the pill feature renders `notice`). For anything the learner must
 * see but that has no card: "Add an ElevenLabs key in Settings", a spotlight caption whose rect is off-screen.
 * Engine `error` events land here too (audit P1-2). Keep it under ~8 words.
 */
export function notify(text: string, tone: Notice['tone'] = 'info', opts: { id?: string; ttlMs?: number } = {}): string {
  // v2 (W0-5): also queued with an id. The same id replaces its earlier notice ("Reconnecting…" → "Back."), so a
  // queue never shows two lines about one thing. `notice` stays the latest for the readers that only show one.
  const id = opts.id ?? `n${++noticeSeq}`
  const n: Notice = { text, tone, at: Date.now(), id, ...(opts.ttlMs ? { ttlMs: opts.ttlMs } : {}) }
  set((s) => ({ notice: n, notices: [...s.notices.filter((x) => x.id !== id), n].slice(-MAX_NOTICES) }))
  return id
}

let noticeSeq = 0
const MAX_NOTICES = 5

/** v2: drop one queued notice (its card or pill line was shown / dismissed). The latest `notice` goes with it if it's that one. */
export function dismissNotice(id: string): void {
  set((s) => {
    const notices = s.notices.filter((x) => x.id !== id)
    return { notices, notice: s.notice?.id === id ? notices[notices.length - 1] : s.notice }
  })
}

/** v2: the oldest queued notice (show it, then dismissNotice(id)). */
export function useNextNotice(): Notice | undefined {
  return useLesson((s) => s.notices[0])
}

/**
 * v2: may the app send this v2 command (core/../common/wire V2_COMMANDS)? Only when engine.hello listed it. Main
 * enforces the same rule for Electron (main/engine.ts); this lets a feature hide a control that would do nothing.
 */
export function canSend(type: string): boolean {
  return !!get().hello?.capabilities.includes(type)
}
export function useCapability(type: string): boolean {
  return useLesson((s) => !!s.hello?.capabilities.includes(type))
}

// ---------------------------------------------------------------------------
// Derived hooks
// ---------------------------------------------------------------------------

/**
 * The engine is working on a model call (explain, diagram, coach: 2-5 s). Show a small spinner on the pill and
 * on the button that was pressed, so a shortcut never looks dead (audit P1-7, Michael's P0-2).
 */
export function useThinking(): boolean {
  return useLesson((s) => s.engineState === 'thinking')
}

/**
 * "Steps timed to the video" style line, from lesson.builtBy (undefined when unknown).
 * mode "lesson" ("Just teach me"): Claude wrote the lesson and no tutorial was read, so "Claude wrote this lesson".
 */
export function builtByLabel(by: LessonInfo['builtBy'], mode?: LessonInfo['mode'], demo = false): string | undefined {
  // The Demo lesson is curated (server/orchestrator/stage.py), not written by a model (Michael, 5 AM shoot).
  if (demo) return undefined
  if (mode === 'lesson' && (by === 'claude' || by === 'unknown' || by == null)) return 'Claude wrote this lesson'
  return by === 'gemini' ? 'Steps timed to the video' : by === 'claude' ? 'Claude read this tutorial' : by === 'mixed' ? 'Built by Gemini and Claude' : undefined
}

export function useStatus(): Status {
  return useLesson((s) => (s.offtrack ? 'offtrack' : s.stepId && s.passed.includes(s.stepId) && !s.skipped.includes(s.stepId) ? 'passed' : 'watching'))
}

// ---------------------------------------------------------------------------
// v2 derived hooks (W0-5): one reading of "where am I" for the panel, the Mini pill, cards and progress.
// ---------------------------------------------------------------------------

export type CurrentStep = {
  id?: string
  /** 0-based position in the lesson (the steps list, else the outline); -1 before the first step. */
  index: number
  /** Steps in the lesson: the outline's count when it's known (never jumps), else the steps so far. */
  total: number
  title: string
  instructions: string
  kind?: StepSummary['kind']
  what?: string
  code?: string
  where?: string
  then?: string
  estMinutes?: number
  /** 0-based positions already passed (green) and skipped (never green). */
  passed: number[]
  skipped: number[]
  /** This step is passed (not skipped). */
  done: boolean
  /** The lesson's last step. */
  last: boolean
}

export function useCurrentStep(): CurrentStep {
  // Primitives only in the selector (arrays as keys), so the snapshot is stable between renders.
  const v = useLesson(
    useShallow((s) => {
      const outline = s.lesson?.outline
      const total = Math.max(s.steps.length, outline?.count ?? 0)
      const index = s.stepId ? s.steps.findIndex((x) => x.id === s.stepId) : -1
      const pos = (id: string): number => s.steps.findIndex((x) => x.id === id)
      const st = s.step && s.step.stepId === s.stepId ? s.step : undefined
      return {
        id: s.stepId,
        index,
        total,
        title: s.stepTitle,
        instructions: s.instructions,
        kind: st?.kind,
        what: st?.what,
        code: st?.code,
        where: st?.where,
        then: st?.then,
        estMinutes: st?.estMinutes,
        passedKey: s.passed
          .filter((id) => !s.skipped.includes(id))
          .map(pos)
          .filter((i) => i >= 0)
          .join(','),
        skippedKey: s.skipped
          .map(pos)
          .filter((i) => i >= 0)
          .join(','),
        done: !!s.stepId && s.passed.includes(s.stepId) && !s.skipped.includes(s.stepId),
        last: index >= 0 && total > 0 && index === total - 1 && s.complete
      }
    })
  )
  const { passedKey, skippedKey, ...rest } = v
  const passed = useMemo(() => (passedKey ? passedKey.split(',').map(Number) : []), [passedKey])
  const skipped = useMemo(() => (skippedKey ? skippedKey.split(',').map(Number) : []), [skippedKey])
  return useMemo(() => ({ ...rest, passed, skipped }), [v, passed, skipped]) // eslint-disable-line react-hooks/exhaustive-deps
}

/**
 * The lesson panel's view of the step (BUILD-PLAN A1 priority: passed > checking > notyet > hint > working; hint is
 * the cards' business, so it isn't here). paused (lesson.paused / a blocker) and building come first; idle = no lesson.
 */
export type StepPhase = 'idle' | 'building' | 'paused' | 'passed' | 'checking' | 'notyet' | 'working'

export function useStepPhase(): StepPhase {
  const pressed = usePressed((p) => p.kind)
  return useLesson((s) => {
    if (!s.lesson && !s.building) return 'idle'
    if (s.building && !s.stepId) return 'building'
    if (s.paused || Object.keys(s.blockers).length) return 'paused'
    if (s.stepId && s.passed.includes(s.stepId) && !s.skipped.includes(s.stepId)) return 'passed'
    if (s.engineState === 'thinking' && pressed === 'check_step') return 'checking'
    if (s.offtrack || s.checks.some((c) => c.status === 'fail')) return 'notyet'
    return 'working'
  })
}

/** The step after this one (from the steps, else the outline while the rest is still being written). */
export function useUpNext(): { title: string; index: number; kind?: StepSummary['kind']; estMinutes?: number } | undefined {
  return useLesson(
    useShallow((s) => {
      const at = s.stepId ? s.steps.findIndex((x) => x.id === s.stepId) : -1
      const next = s.steps[at + 1]
      if (next) return { title: next.title, index: at + 1, kind: next.kind, estMinutes: next.estMinutes }
      const row = s.lesson?.outline?.steps.find((o) => o.index === (s.steps[at]?.index ?? at) + 1)
      return row ? { title: row.title, index: at + 1, kind: row.kind, estMinutes: row.estMinutes } : undefined
    })
  )
}

/** Position comes from the steps array (robust to 0- or 1-based `index` from the engine). */
export function useProgress(): { index: number; total: number; fraction: number } {
  return useLesson(
    useShallow((s) => {
      const total = Math.max(1, s.steps.length)
      const index = Math.max(0, s.steps.findIndex((x) => x.id === s.stepId))
      const done = s.checks.filter((c) => c.status === 'pass').length
      const within = s.stepId && s.passed.includes(s.stepId) ? 1 : s.checks.length ? done / s.checks.length : 0
      return { index, total, fraction: Math.min(1, (index + within) / total) }
    })
  )
}
