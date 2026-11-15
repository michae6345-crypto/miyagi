/**
 * Pill-local state: the step-pass moment and the building line.
 *
 * The step-pass moment is one gesture (FRONTEND-HANDOFF → "Step passes"):
 *   t = 0      step.passed: the status dot becomes a green check that draws its stroke,
 *              core flashes the island green (600ms)
 *   t = 560ms  the text and the step count crossfade to the next step by itself; the check settles back into a gray dot
 *   t = 400ms  (player) the video resumes
 * The pill moves on without waiting for the engine's step.started (the mock sends it ~4s later),
 * using step.passed.nextStepId or the next entry in lesson.steps. step.started then just confirms it.
 *
 * Also here: the notice line (core `notice`, shown ~5 s), the offline state (core `connected`, after a grace), and
 * "Lesson saved · Undo" after End (review A3).
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useLesson, type Notice } from '../../core/lesson'
import { sendAction, usePressed } from '../../core/shortcuts'

/** How long the green check holds before the text crossfades to the next step. */
export const PASS_HOLD_MS = 560

type PillState = {
  /** The step whose pass is being celebrated right now (the check is showing). */
  celebrating?: string
  /** After a pass: the pill has moved past `from` and shows `to` (undefined = the lesson is complete). */
  advanced?: { from: string; to?: string }
  /** Last lesson.building message, kept through lesson.ready (core clears it there). Never a failed build's. */
  buildMessage?: string
  /** The line the pill is showing right now (core `notice`, for NOTICE_MS). */
  notice?: Notice
  /** connected has been false for longer than OFFLINE_GRACE_MS. */
  offline: boolean
  /** "Lesson saved · Undo" is on the pill (UNDO_MS after an End that kept the save). */
  undo: boolean
  /** Undo was pressed: the bonsai spins until the lesson is back (never look dead), at most RESUME_WAIT_MS. */
  resuming: boolean
}

export const usePill = create<PillState>(() => ({ offline: false, undo: false, resuming: false }))
const set = usePill.setState

let holdTimer: ReturnType<typeof setTimeout> | undefined

const clear = (): void => {
  clearTimeout(holdTimer)
  set({ celebrating: undefined, advanced: undefined, buildMessage: undefined })
}

// A full reset (dev HUD) clears everything. A lesson-scoped one (reconnect, lesson ended) keeps a notice on screen
// (it may be the reason the lesson ended) and the Undo after End (that reset comes just before it).
onUi('reset', (p) => {
  clear()
  if ((p as { scope?: string } | undefined)?.scope) return
  hideNotice()
  dropUndo()
  doneResuming()
})
onMessage('lesson.ready', () => {
  clearTimeout(holdTimer)
  set({ celebrating: undefined, advanced: undefined })
})
// A failed build drops its message: the error arrives as a notice instead.
onMessage('lesson.building', (p) => set({ buildMessage: p.failed ? undefined : p.message }))
// The engine caught up. A celebration still in progress finishes on its own timer.
onMessage('step.started', () => set({ advanced: undefined, buildMessage: undefined }))
// A lesson is on screen again (resumed, or a new one): the Undo is spent and nothing is waiting any more.
for (const t of ['lesson.building', 'lesson.ready', 'step.started'] as const)
  onMessage(t, () => {
    dropUndo()
    doneResuming()
  })
onMessage('step.passed', (p) => {
  const { steps } = useLesson.getState()
  const i = steps.findIndex((s) => s.id === p.stepId)
  const to = p.nextStepId ?? (i >= 0 ? steps[i + 1]?.id : undefined)
  clearTimeout(holdTimer)
  if (p.skipped) return set({ celebrating: undefined, advanced: { from: p.stepId, to } }) // no green check for a skip
  set({ celebrating: p.stepId, advanced: undefined })
  holdTimer = setTimeout(() => set({ celebrating: undefined, advanced: { from: p.stepId, to } }), PASS_HOLD_MS)
})

// ---------------------------------------------------------------------------
// Notice line: one short line for ~5 s (engine errors, a failed build, notify() from any feature).
// ---------------------------------------------------------------------------

export const NOTICE_MS = 5000
let noticeTimer: ReturnType<typeof setTimeout> | undefined

function showNotice(n: Notice): void {
  clearTimeout(noticeTimer)
  // Same words again: keep the line as it is (no second crossfade), just hold it longer.
  const shown = usePill.getState().notice
  set({ notice: shown && shown.text === n.text && shown.tone === n.tone ? shown : n })
  noticeTimer = setTimeout(hideNotice, NOTICE_MS)
}
function hideNotice(): void {
  clearTimeout(noticeTimer)
  set({ notice: undefined })
}

/**
 * The learner ended the lesson with End (the bar's or the launcher's): say where it went and offer Undo (Michael's
 * review A3: "After any end, show where it went and offer Undo"; desktop test 3, item 11). The pill reads
 * "Lesson saved · Undo" for UNDO_MS, then falls back to the idle pill. Undo sends action resume, which restores the
 * kept save even with no lesson in memory (the engine's Resumer.resume reloads the step graph at the saved step).
 * Only for the engine's reason "stopped": that End keeps the save (server/sessions/resume.py KEEP_END). No line for
 * "new lesson" (a new search or build replaced it), nor "end_lesson" / "POST /end" ("Start a new lesson" on the resume
 * card: the save is cleared, so "saved" would be untrue and Undo couldn't work).
 * Core turns lesson.ended into a lesson-scoped reset first (it registered before this handler); that reset keeps
 * the Undo, so it survives it.
 */
export const LESSON_SAVED = 'Lesson saved'
export const UNDO_MS = 8000
export const RESUME_WAIT_MS = 10_000
let undoTimer: ReturnType<typeof setTimeout> | undefined
let resumeTimer: ReturnType<typeof setTimeout> | undefined

function offerUndo(): void {
  clearTimeout(undoTimer)
  set({ undo: true })
  undoTimer = setTimeout(dropUndo, UNDO_MS)
}
function dropUndo(): void {
  clearTimeout(undoTimer)
  if (usePill.getState().undo) set({ undo: false })
}
function doneResuming(): void {
  clearTimeout(resumeTimer)
  if (usePill.getState().resuming) set({ resuming: false })
}

/** Undo (the pill's button after End): the engine resumes the kept save; the line goes at once. */
export function undoEnd(): void {
  dropUndo()
  sendAction('resume')
  clearTimeout(resumeTimer)
  set({ resuming: true })
  resumeTimer = setTimeout(doneResuming, RESUME_WAIT_MS)
}

onMessage('lesson.ended', (p) => {
  doneResuming()
  if (p.reason === 'stopped') offerUndo()
  else dropUndo()
})
// The engine answered the resume some other way (a card, an error): stop waiting.
onMessage('card', doneResuming)
onMessage('error', doneResuming)
// "Start a new lesson" on the resume card (action end_lesson) clears the save: no Undo for that.
usePressed.subscribe((s) => {
  if (s.kind === 'end_lesson') dropUndo()
})

// ---------------------------------------------------------------------------
// Offline: connected false for a moment is normal (startup, a socket hiccup); only a lasting drop shows.
// ---------------------------------------------------------------------------

export const OFFLINE_GRACE_MS = 2000
let offlineTimer: ReturnType<typeof setTimeout> | undefined

function syncOffline(connected: boolean): void {
  clearTimeout(offlineTimer)
  if (connected) set({ offline: false })
  else offlineTimer = setTimeout(() => set({ offline: true }), OFFLINE_GRACE_MS)
}
syncOffline(useLesson.getState().connected)

useLesson.subscribe((s, prev) => {
  if (s.notice && s.notice !== prev.notice) showNotice(s.notice)
  if (s.connected !== prev.connected) syncOffline(s.connected)
})

/** Off-track episodes whose amber pulse has been seen, so hover/card remounts don't pulse again. */
export const pulsedOfftrack = new WeakSet<object>()
