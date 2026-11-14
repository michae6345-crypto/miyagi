/**
 * Lesson state, reduced from engine messages (shared/contracts/events.ts).
 * One store per window: each Electron window gets the same stream from main;
 * the browser stage shares a single store.
 */
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'
import type { CheckStatus, Source, StepSummary, VideoSegment } from '../../../../shared/contracts/events'
import type { ConfigStatus, Incoming, Payload } from '../../common/wire'

export type CheckItem = { id: string; label: string; status: CheckStatus; detail?: string }

export type Status = 'watching' | 'offtrack' | 'passed'

/** Optional extras the mock sends today (the contract allows adding fields). */
export type Offtrack = Payload<'offtrack'> & {
  reason?: string
  curve?: { label: string; yours: number[]; tutorial: number[] }
}
/** Screen-first: rect is in screen POINTS, top-left of the primary display (the engine's OCR finds it). */
export type SpotlightTarget = Exclude<Payload<'spotlight'>, { clear: true }> & { code?: string }
export type Rect = { x: number; y: number; w: number; h: number }
export type Card = Payload<'card'>
export type Diagram = Payload<'diagram'>
export type SearchResult = Payload<'search.result'>

type State = {
  connected: boolean
  lesson?: { id: string; title: string; sources: Source[] }
  steps: StepSummary[]
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
  offtrack?: Offtrack
  offtrackOpen: boolean
  /** The current step went off-track at some point: show the success card when it passes. */
  recovered: boolean
  success?: { stepId: string; index: number; summary?: string; checks: CheckItem[]; at: number }
  card?: Card
  spotlight?: SpotlightTarget
  diagram?: Diagram
  diagramOpen: boolean
  /** What the engine wants the player to do; the player (F4) follows this and reports back with video.state. */
  video: { t: number; playing: boolean; at: number }
  voiceOn: boolean
  lastSpeak?: { url: string; text: string; at: number }
  /** Live metric feed, per metric name (capped). Powers the yours-vs-tutorial curve. */
  metrics: Record<string, { step: number; value: number }[]>
  engineState?: Payload<'status'>['state']
  /** What the engine's screen reader currently sees (debug HUD). */
  seen?: Payload<'screen.seen'>
  /** Per-key status from config.status (bring-your-own-key Settings). */
  keyStatus?: ConfigStatus['payload']
  error?: { message: string; at: number }
  /** Increments on every step.passed: drives the pill's green flash. */
  passFlash: number
  search: { query: string; results: SearchResult[]; done: boolean; pending: boolean }

  apply(m: Incoming): void
  setConnected(c: boolean): void
  startSearch(query: string): void
  startBuild(): void
  closeCard(): void
  closeDiagram(): void
  toggleVoice(): void
  reset(): void
}

const blank = {
  lesson: undefined,
  steps: [],
  stepId: undefined,
  stepTitle: '',
  instructions: '',
  stepVideo: undefined,
  checks: [],
  passed: [],
  building: false,
  buildingMessage: undefined,
  buildingProgress: undefined,
  offtrack: undefined,
  offtrackOpen: false,
  recovered: false,
  success: undefined,
  card: undefined,
  spotlight: undefined,
  diagram: undefined,
  diagramOpen: false,
  video: { t: 0, playing: false, at: 0 },
  lastSpeak: undefined,
  metrics: {},
  engineState: undefined,
  seen: undefined,
  error: undefined,
  passFlash: 0,
  search: { query: '', results: [], done: false, pending: false }
} satisfies Partial<State>

const METRIC_CAP = 600

export const useLesson = create<State>((set, get) => ({
  connected: false,
  voiceOn: false,
  ...blank,

  setConnected: (connected) => set({ connected }),
  startSearch: (query) => set({ search: { query, results: [], done: false, pending: true } }),
  startBuild: () => set({ building: true }),
  closeCard: () => set({ offtrackOpen: false, success: undefined, diagramOpen: false, card: undefined }),
  closeDiagram: () => set({ diagramOpen: false }),
  toggleVoice: () => set({ voiceOn: !get().voiceOn }),
  reset: () => set({ ...blank }),

  apply(m) {
    const s = get()
    switch (m.type) {
      case 'search.result': {
        const results = s.search.results.filter((r) => r.id !== m.payload.id).concat(m.payload)
        return set({ search: { ...s.search, results, pending: true } })
      }
      case 'search.done':
        return set({ search: { ...s.search, done: true, pending: false } })
      case 'lesson.building':
        return set({ building: true, buildingMessage: m.payload.message, buildingProgress: m.payload.progress })
      case 'lesson.ready':
        return set({ ...blank, search: s.search, metrics: {}, lesson: m.payload.lesson, steps: m.payload.steps, building: true })
      case 'step.started': {
        const p = m.payload
        const pos = s.steps.findIndex((x) => x.id === p.stepId)
        const before = pos > 0 ? s.steps.slice(0, pos).map((x) => x.id) : []
        return set({
          building: false,
          buildingMessage: undefined,
          stepId: p.stepId,
          stepTitle: p.title,
          instructions: p.instructions,
          stepVideo: p.video,
          checks: [],
          passed: Array.from(new Set([...s.passed, ...before])),
          offtrack: undefined,
          offtrackOpen: false,
          recovered: false,
          card: undefined,
          spotlight: undefined,
          diagramOpen: false
        })
      }
      case 'check.updated': {
        const p = m.payload
        if (p.stepId !== s.stepId) return
        const item: CheckItem = { id: p.checkId, label: p.label, status: p.status, detail: p.detail }
        const exists = s.checks.some((c) => c.id === p.checkId)
        return set({ checks: exists ? s.checks.map((c) => (c.id === p.checkId ? item : c)) : [...s.checks, item] })
      }
      case 'step.passed': {
        const p = m.payload as Payload<'step.passed'> & { summary?: string }
        const index = s.steps.findIndex((x) => x.id === p.stepId)
        return set({
          passed: Array.from(new Set([...s.passed, p.stepId])),
          passFlash: s.passFlash + 1,
          offtrack: undefined,
          offtrackOpen: false,
          spotlight: undefined,
          success: s.recovered ? { stepId: p.stepId, index, summary: p.summary, checks: s.checks, at: Date.now() } : undefined
        })
      }
      case 'offtrack':
        return set({ offtrack: m.payload as Offtrack, offtrackOpen: true, recovered: true, diagramOpen: false, card: undefined })
      case 'spotlight':
        return set({ spotlight: 'clear' in m.payload ? undefined : (m.payload as SpotlightTarget) })
      case 'screen.seen':
        return set({ seen: m.payload })
      case 'config.status':
        return set({ keyStatus: m.payload })
      case 'video.seek':
        return set({ video: { t: m.payload.t, playing: m.payload.play, at: Date.now() } })
      case 'video.pause':
        return set({ video: { ...s.video, playing: false, at: Date.now() } })
      case 'video.play':
        return set({ video: { ...s.video, playing: true, at: Date.now() } })
      case 'card':
        return set({ card: m.payload, diagramOpen: false, offtrackOpen: false })
      case 'diagram':
        return set({ diagram: m.payload, diagramOpen: true, card: undefined })
      case 'speak':
        return set({ lastSpeak: { url: m.payload.audioUrl, text: m.payload.text, at: Date.now() } })
      case 'metric': {
        const p = m.payload
        const series = (s.metrics[p.name] ?? []).concat({ step: p.step, value: p.value }).slice(-METRIC_CAP)
        return set({ metrics: { ...s.metrics, [p.name]: series } })
      }
      case 'status':
        return set({ engineState: m.payload.state })
      case 'error':
        return set({ error: { message: m.payload.message, at: Date.now() } })
    }
  }
}))

/** Derived helpers. */
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
