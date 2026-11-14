/**
 * Core lesson state: what every feature can read. Feature-specific state (cards, diagram,
 * spotlight, search, voice…) lives in each feature's own store, subscribed via core/bus.
 *
 * Owner: core. Agents READ this store freely; add fields only through a small "core:" commit.
 */
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'
import type { CheckStatus, Source, StepSummary, VideoSegment } from '../../../../../shared/contracts/events'
import type { ConfigStatus, Payload } from '../../../common/wire'
import { bridge } from '../bridge'
import { emitUi, onMessage, onUi } from './bus'

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
}

export type Notice = { text: string; tone: 'error' | 'info'; at: number }

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
  notice: undefined
} satisfies Partial<LessonState>

export const useLesson = create<LessonState>(() => ({ connected: false, ...blank }))

const set = useLesson.setState
const get = useLesson.getState

/** Called by the launcher when "Build lesson" fires (before the engine answers). */
export const startBuild = (): void => set({ building: true })
export const setConnected = (connected: boolean): void => {
  // (Re)connected: the engine's snapshot is the truth (after an engine restart it's just "idle"),
  // so drop the lesson this window was showing before the snapshot refills it.
  if (connected && !get().connected) emitUi('reset', { scope: 'lesson', reason: 'reconnect' })
  // Dropped mid-build: no `failed` can arrive any more, so drop the building UI too (audit P1-3).
  if (!connected && get().building) set({ building: false, buildingMessage: undefined, buildingProgress: undefined, buildingElapsed: undefined })
  // Nothing is thinking on a dead socket.
  if (!connected && get().engineState === 'thinking') set({ engineState: undefined })
  set({ connected })
}

onUi('reset', () => set({ ...blank }))

/**
 * The engine ended the lesson (end_lesson, a new learn, POST /end): blank every lesson-side store.
 * scope "lesson" tells the launcher to keep its query and results (a new search may be in flight).
 */
onMessage('lesson.ended', (p) => {
  emitUi('reset', { scope: 'lesson', reason: p.reason })
})

onMessage('lesson.building', (p) =>
  // failed: the build ended in error (an `error` + status idle follow): drop the building UI.
  p.failed
    ? set({ building: false, buildingMessage: undefined, buildingProgress: undefined, buildingElapsed: undefined })
    : set({ building: true, buildingMessage: p.message, buildingProgress: p.progress, buildingElapsed: p.elapsedS })
)
onMessage('lesson.ready', (p) => set({ ...blank, lesson: p.lesson, steps: p.steps, complete: p.lesson.complete !== false, building: true }))
/** A long video's next part: the new step list (ids stable, new steps appended). Rows already shown must not re-animate. */
onMessage('lesson.updated', (p) => set({ steps: p.steps, complete: p.complete, parts: p.parts, pendingNext: false }))
onMessage('step.started', (p) => {
  const s = get()
  const pos = s.steps.findIndex((x) => x.id === p.stepId)
  const before = pos > 0 ? s.steps.slice(0, pos).map((x) => x.id) : []
  set({
    building: false,
    buildingMessage: undefined,
    stepId: p.stepId,
    stepTitle: p.title,
    instructions: p.instructions,
    stepVideo: p.video,
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
  set({
    passed: Array.from(new Set([...s.passed, p.stepId])),
    passFlash: s.passFlash + 1,
    pendingNext: p.pending === true,
    offtrack: undefined,
    lastPassed: { stepId: p.stepId, summary, checks: s.checks, at: Date.now() }
  })
})
onMessage('offtrack', (p) => set({ offtrack: p as Offtrack }))
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
onMessage('status', (p) => set({ engineState: p.state }))
onMessage('screen.seen', (p) => set({ seen: p }))
onMessage('config.status', (p) => set({ keyStatus: p }))
onMessage('error', (p) => set({ error: { message: p.message, at: Date.now() }, notice: { text: p.message, tone: 'error', at: Date.now() } }))

/**
 * Show one short line on the pill for ~5 s (the pill feature renders `notice`). For anything the learner must
 * see but that has no card: "Add an ElevenLabs key in Settings", a spotlight caption whose rect is off-screen.
 * Engine `error` events land here too (audit P1-2). Keep it under ~8 words.
 */
export function notify(text: string, tone: Notice['tone'] = 'info'): void {
  set({ notice: { text, tone, at: Date.now() } })
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

/** "Gemini watched this video" style line, from lesson.builtBy (undefined when unknown). */
export function builtByLabel(by: LessonInfo['builtBy']): string | undefined {
  return by === 'gemini' ? 'Gemini watched this video' : by === 'claude' ? 'Claude read this tutorial' : by === 'mixed' ? 'Built by Gemini and Claude' : undefined
}

export function useStatus(): Status {
  return useLesson((s) => (s.offtrack ? 'offtrack' : s.stepId && s.passed.includes(s.stepId) ? 'passed' : 'watching'))
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
