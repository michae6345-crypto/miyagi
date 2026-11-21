/**
 * Feature: progress (A8). Three pieces of state, all read from engine events, nothing made up:
 *
 *   step    the step-passed card (Prog-Step-Passed): a snapshot taken when step.passed arrives (which step, of how
 *           many, the engine's summary, what comes next). Never for a skipped / already-done step, never for the
 *           lesson's last step (the completion card takes over). Closes by itself after STEP_MS, on Continue / Esc,
 *           when the lesson panel opens, on a new lesson or a reset.
 *   data    the engine's `progress` answer (Prog-Progress-Window). null = the engine has nothing (or can't answer
 *           progress.get): the window shows its empty states.
 *   review  the spaced-review reminder (Prog-Review-Reminder): asked for once per app session, at launch, only by the
 *           overlay, only while no lesson runs. There is no scheduler yet, so today only fixture data opens it.
 *
 * Capabilities come from main (main/features/progress.ts `progress:caps`), because an app window that opens mid-lesson
 * never saw this connection's engine.hello. In the browser stage web.ts answers from core/lesson canSend().
 */
import { create } from 'zustand'
import { cmd, type Outgoing } from '../../../../common/wire'
import { bridge, engineMode } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { useDock } from '../../core/dock'
import { canSend, useLesson } from '../../core/lesson'
import { readProgress, type Progress, type ReviewItem } from './types'

/** How long the step card stays before it folds back into the pill (the mockup: "after a few seconds"). */
export const STEP_MS = 4500
/** The progress window waits this long for `progress` before it shows its empty states. */
const ANSWER_MS = 4000
/** After engine.hello, the overlay waits this long for a lesson to show up before it looks for a due review. */
const REVIEW_CHECK_MS = 1500

const params = typeof location === 'undefined' ? new URLSearchParams() : new URLSearchParams(location.search)
/** Browser stage only: `?hold` keeps the step card open (screenshots) and shows it as if the panel were collapsed. */
export const STAGE_HOLD = engineMode() === 'inline' && params.has('hold')
/** Browser stage only: `?review` lets the overlay's launch check ask the mock for a due review. */
const STAGE_REVIEW = params.has('review')

export type StepCard = {
  stepId: string
  /** 0-based position of the step that passed. */
  index: number
  total: number
  title: string
  /** step.passed.summary: what the learner just did (<= 12 words). */
  summary?: string
  next?: string
  /** 0-based positions passed (green) and skipped (never green), the one that just passed included. */
  passed: number[]
  skipped: number[]
  at: number
}

export type Caps = { progress: boolean; review: boolean; library: boolean }
export type LoadState = 'idle' | 'loading' | 'ready' | 'none'

type State = {
  step?: StepCard
  data?: Progress
  load: LoadState
  caps: Caps
  /** The reminder's item while it is up. */
  review?: { item: ReviewItem; due: number }
}

const NO_CAPS: Caps = { progress: false, review: false, library: false }
export const useProgress = create<State>(() => ({ step: undefined, data: undefined, load: 'idle', caps: NO_CAPS, review: undefined }))
const set = useProgress.setState
const get = useProgress.getState

// ---- step passed ------------------------------------------------------------------------------------------------

let stepTimer: ReturnType<typeof setTimeout> | undefined
export function closeStep(): void {
  clearTimeout(stepTimer)
  if (get().step) set({ step: undefined })
}

onMessage('step.passed', (p) => {
  // Skipped or already done: no "passed" moment (green only means passed).
  if (p.skipped || p.already) return
  const s = useLesson.getState()
  const index = s.steps.findIndex((x) => x.id === p.stepId)
  if (index < 0) return closeStep()
  const total = Math.max(s.steps.length, s.lesson?.outline?.count ?? 0)
  // The lesson's last step: the completion card says it, not this one. A pending next part isn't the end.
  if (index === total - 1 && s.complete && !p.pending) return closeStep()
  const pos = (id: string): number => s.steps.findIndex((x) => x.id === id)
  const skippedIds = new Set(s.skipped)
  const passed = Array.from(new Set([...s.passed, p.stepId]))
    .filter((id) => !skippedIds.has(id))
    .map(pos)
    .filter((i) => i >= 0)
  const skipped = s.skipped.map(pos).filter((i) => i >= 0)
  const nextStep = (p.nextStepId && s.steps.find((x) => x.id === p.nextStepId)) || s.steps[index + 1]
  const nextRow = nextStep ? undefined : s.lesson?.outline?.steps.find((o) => o.index === s.steps[index].index + 1)
  clearTimeout(stepTimer)
  set({
    step: {
      stepId: p.stepId,
      index,
      total,
      title: s.steps[index].title,
      summary: p.summary?.trim() || undefined,
      next: nextStep?.title ?? nextRow?.title,
      passed,
      skipped,
      at: Date.now()
    }
  })
  if (!STAGE_HOLD) stepTimer = setTimeout(closeStep, STEP_MS)
})
// The panel opened: the step card never shows beside it, and doesn't come back when it collapses again.
useDock.subscribe((d, prev) => {
  if (d.open && !prev.open) closeStep()
})

// ---- progress data ----------------------------------------------------------------------------------------------

/** Did the overlay's launch check ask? Only its answer opens the reminder (the window's own request never does). */
let reminderAsked = false
let answerTimer: ReturnType<typeof setTimeout> | undefined

onMessage('progress', (raw) => {
  clearTimeout(answerTimer)
  const data = readProgress(raw)
  set({ data, load: data ? 'ready' : 'none' })
  if (!reminderAsked) return
  reminderAsked = false
  const item = data?.review?.items[0]
  const due = data?.review?.due ?? 0
  if (item && due > 0 && !lessonOn()) set({ review: { item, due } })
})

export async function refreshCaps(): Promise<Caps> {
  const caps = await bridge.invoke<Caps>('progress:caps').catch(() => undefined)
  const next: Caps = caps && typeof caps === 'object' ? { progress: !!caps.progress, review: !!caps.review, library: !!caps.library } : { progress: canSend('progress.get'), review: canSend('review.start'), library: canSend('library.start') }
  const cur = get().caps
  if (cur.progress !== next.progress || cur.review !== next.review || cur.library !== next.library) set({ caps: next })
  return next
}

/** The progress window: show what main last saw at once, then ask the engine (only when it listed progress.get). */
export async function requestProgress(): Promise<void> {
  if (!get().data) set({ load: 'loading' })
  const last = await bridge.invoke<unknown>('progress:last').catch(() => undefined)
  const cached = last ? readProgress(last) : undefined
  if (cached && !get().data) set({ data: cached, load: 'ready' })
  const caps = await refreshCaps()
  if (!caps.progress) {
    if (!get().data) set({ load: 'none' })
    return
  }
  bridge.send(cmd('progress.get', {}))
  clearTimeout(answerTimer)
  answerTimer = setTimeout(() => {
    if (get().load === 'loading') set({ load: 'none' })
  }, ANSWER_MS)
}

// ---- review reminder --------------------------------------------------------------------------------------------

const lessonOn = (): boolean => {
  const s = useLesson.getState()
  return !!s.lesson || s.building
}

let reviewChecked = false
let reviewTimer: ReturnType<typeof setTimeout> | undefined
/** Only the window that draws the island looks for a due review (every window loads this module). */
const drawsIsland = (): boolean => {
  const route = typeof document === 'undefined' ? undefined : document.documentElement.dataset.route
  return route === 'overlay' || route === 'stage'
}

function scheduleReviewCheck(): void {
  if (reviewChecked) return
  clearTimeout(reviewTimer)
  reviewTimer = setTimeout(() => {
    if (reviewChecked || lessonOn() || !drawsIsland()) return
    // The browser stage asks only with ?review, so ?scenario=full stays quiet for every other lane; there the mock
    // answers whatever the app sends, so it doesn't wait for a hello (the stage can miss the mock's first one).
    const stage = engineMode() === 'inline'
    if (stage ? !STAGE_REVIEW : !canSend('progress.get')) return
    reviewChecked = true
    reminderAsked = true
    bridge.send(cmd('progress.get', {}))
  }, REVIEW_CHECK_MS)
}

onMessage('engine.hello', () => {
  void refreshCaps()
  scheduleReviewCheck()
})
// Browser stage with ?review: look once after load even if no hello reached this window.
if (STAGE_REVIEW && engineMode() === 'inline') scheduleReviewCheck()

export function closeReview(): void {
  if (get().review) set({ review: undefined })
}

/**
 * Start review. No contract command exists yet (no scheduler): the button is disabled unless the engine lists
 * `review.start`, and then this sends it (Core request: add review.start {label} to the contract and main's allowlist).
 */
export function startReview(item: ReviewItem): void {
  if (!canSend('review.start') && !get().caps.review) return
  bridge.send({ type: 'review.start', payload: { label: item.label } } as unknown as Outgoing)
  closeReview()
}

// ---- lifecycle --------------------------------------------------------------------------------------------------

onMessage('lesson.ready', () => {
  closeStep()
  closeReview()
})
onMessage('lesson.building', () => closeReview())
onUi('dismiss', () => {
  closeStep()
  closeReview()
})
onUi('reset', () => {
  closeStep()
  closeReview()
})
