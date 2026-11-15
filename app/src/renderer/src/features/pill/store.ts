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
 * Also here: the notice line (core `notice`, shown ~5 s), the offline state (core `connected`, after a grace, and only
 * once a connect attempt has failed: review A16), "Lesson saved · Undo" after End (review A3) and the saved lesson the
 * engine offers back (review A7).
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
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
  /** connected has been false for longer than OFFLINE_GRACE_MS and a connect attempt has failed (review A16). */
  offline: boolean
  /**
   * The engine socket as main reports it (main/engine.ts LinkInfo). 'pending' until the first answer; 'unsupported' when
   * this runtime doesn't report it (then offline is the plain grace, as before).
   */
  link: LinkInfo | 'pending' | 'unsupported'
  /** Retry was pressed: the bonsai spins until that attempt ends (at least RETRY_MIN_MS, so the press reads). */
  retrying: boolean
  /** "Lesson saved · Undo" is on the pill (UNDO_MS after an End that kept the save). */
  undo: boolean
  /** Undo or Continue was pressed: the bonsai spins until the lesson is back (never look dead), at most RESUME_WAIT_MS. */
  resuming: boolean
  /** A saved lesson the engine offers back (its resume card), kept after the learner closes the card: the idle pill's Continue. */
  offer?: SavedOffer
}

/** main/engine.ts LinkInfo (main-only module, so the shape is repeated here). */
export type LinkInfo = { open: boolean; attempting: boolean; failures: number }

export const usePill = create<PillState>(() => ({ offline: false, undo: false, resuming: false, link: 'pending', retrying: false }))
const set = usePill.setState

let holdTimer: ReturnType<typeof setTimeout> | undefined

const clear = (): void => {
  clearTimeout(holdTimer)
  set({ celebrating: undefined, advanced: undefined, buildMessage: undefined })
}

// A full reset (dev HUD) clears everything. A lesson-scoped one (reconnect, lesson ended) keeps a notice on screen
// (it may be the reason the lesson ended) and the Undo after End (that reset comes just before it). A reconnect drops
// the saved-lesson offer: the engine's snapshot is the truth, and it sends the resume card again if the save is there.
onUi('reset', (p) => {
  clear()
  const r = p as { scope?: string; reason?: string } | undefined
  if (r?.scope) {
    if (r.reason === 'reconnect') set({ offer: undefined })
    return
  }
  hideNotice()
  dropUndo()
  doneResuming()
  set({ offer: undefined })
})
onMessage('lesson.ready', () => {
  clearTimeout(holdTimer)
  set({ celebrating: undefined, advanced: undefined })
})
// A failed build drops its message: the error arrives as a notice instead.
onMessage('lesson.building', (p) => set({ buildMessage: p.failed ? undefined : p.message }))
// The engine caught up. A celebration still in progress finishes on its own timer.
onMessage('step.started', () => set({ advanced: undefined, buildMessage: undefined }))
// A lesson is on screen again (resumed, or a new one): the Undo and the offer are spent and nothing is waiting any more.
for (const t of ['lesson.building', 'lesson.ready', 'step.started'] as const)
  onMessage(t, () => {
    dropUndo()
    doneResuming()
    if (usePill.getState().offer) set({ offer: undefined })
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

/** Back into the saved lesson (Undo, or the idle pill's Continue): action resume, and the bonsai spins until it's back. */
export function resumeSaved(): void {
  if (usePill.getState().resuming) return // one press is enough
  sendAction('resume')
  clearTimeout(resumeTimer)
  set({ resuming: true })
  resumeTimer = setTimeout(doneResuming, RESUME_WAIT_MS)
}

/** Undo (the pill's button after End): the engine resumes the kept save; the line goes at once. */
export function undoEnd(): void {
  dropUndo()
  resumeSaved()
}

onMessage('lesson.ended', (p) => {
  doneResuming()
  if (p.reason === 'stopped') return offerUndo()
  // Any other end ("Start a new lesson", a new lesson) clears or replaces the save: nothing to undo or continue.
  dropUndo()
  if (usePill.getState().offer) set({ offer: undefined })
})
// The engine answered the resume some other way (a card, an error): stop waiting.
onMessage('card', doneResuming)
onMessage('error', doneResuming)
// "Start a new lesson" on the resume card (action end_lesson) clears the save: no Undo, no Continue for that.
usePressed.subscribe((s) => {
  if (s.kind !== 'end_lesson') return
  dropUndo()
  if (usePill.getState().offer) set({ offer: undefined })
})

// ---------------------------------------------------------------------------
// The saved lesson the engine offers back (Michael's review A7: "While the engine is awaiting_resume, the idle pill
// could read 'Continue · <lesson> 2/7'"). The engine sends card {kind:'resume', actions:[resume, end_lesson]} while a
// save waits; the cards feature shows it, and once the learner closes it (✕) the idle pill keeps the way back.
// ---------------------------------------------------------------------------

/** What the resume card's body says about the saved lesson. n/total only when the body has both. */
export type SavedOffer = { title?: string; n?: number; total?: number }

/**
 * The resume card's body: "<lesson title> · Step 3 of 7 · 12 min ago" or "<lesson title> · step 3: <step title>".
 * The title is everything before the first step / time part (a title may hold " · " itself: "PINNs · Convection");
 * a body with neither is all title.
 */
export function parseOffer(body: string): SavedOffer {
  const parts = body.trim().split(/\s+·\s+/).map((x) => x.trim()).filter(Boolean)
  const marker = (x: string): boolean => /^step\s+\d+/i.test(x) || /^\d+\s*(?:\/|of)\s*\d+$/i.test(x) || /\bago$|^just now$/i.test(x)
  const cut = parts.findIndex(marker)
  const title = (cut < 0 ? parts : parts.slice(0, cut)).join(' · ') || undefined
  for (const x of cut < 0 ? [] : parts.slice(cut)) {
    const m = /^(?:step\s+)?(\d+)\s*(?:\/|of)\s*(\d+)\b/i.exec(x)
    if (!m) continue
    const n = Number(m[1])
    const total = Number(m[2])
    if (n >= 1 && total >= n) return { title, n, total }
  }
  return { title }
}

onMessage('card', (p) => {
  if (p.kind === 'resume') set({ offer: parseOffer(p.body ?? '') })
})

// ---------------------------------------------------------------------------
// Offline: connected false for a moment is normal (startup, a socket hiccup); only a lasting drop shows, and only once
// a connect attempt has actually failed (Michael's review A16: "Offline" flashed on load and stayed ~10 s after an
// engine reload). Main retries every 1 s for the first 30 s of an outage (main/engine.ts); the pill's Retry tries now.
// ---------------------------------------------------------------------------

export const OFFLINE_GRACE_MS = 2000
/** The idle pill while the engine can't be reached (review A16), with a Retry. */
export const UNREACHABLE = "Can't reach miyagi"
export const RETRY_MIN_MS = 600
const RETRY_MAX_MS = 6000
let offlineTimer: ReturnType<typeof setTimeout> | undefined
/** When this window last saw the engine go away (or loaded without it). */
let downAt = Date.now()

function syncOffline(): void {
  clearTimeout(offlineTimer)
  const { connected } = useLesson.getState()
  const { link, offline } = usePill.getState()
  if (connected) {
    if (offline) set({ offline: false })
    return
  }
  // No attempt has failed yet (the first one on load, or the first after a drop, is still in flight): not offline yet.
  const failed = link === 'unsupported' || (link !== 'pending' && link.failures > 0)
  if (!failed) return
  const left = OFFLINE_GRACE_MS - (Date.now() - downAt)
  if (left <= 0) {
    if (!offline) set({ offline: true })
  } else offlineTimer = setTimeout(syncOffline, left)
}

let retryTimer: ReturnType<typeof setTimeout> | undefined
let retryAt = 0
function doneRetrying(): void {
  clearTimeout(retryTimer)
  const wait = RETRY_MIN_MS - (Date.now() - retryAt)
  if (wait > 0) {
    retryTimer = setTimeout(doneRetrying, wait)
    return
  }
  if (usePill.getState().retrying) set({ retrying: false })
}

function onLink(l: LinkInfo): void {
  set({ link: l })
  // The attempt Retry started has ended (open, or failed again).
  if (usePill.getState().retrying && (l.open || !l.attempting)) doneRetrying()
  syncOffline()
}

/** The pill's Retry: main tries now (and goes back to 1 s retries); the bonsai spins until that attempt ends. */
export function retryEngine(): void {
  if (usePill.getState().retrying) return
  retryAt = Date.now()
  clearTimeout(retryTimer)
  set({ retrying: true })
  retryTimer = setTimeout(() => set({ retrying: false }), RETRY_MAX_MS)
  bridge
    .invoke<LinkInfo>('engine-link:retry')
    .then((l) => l && onLink(l))
    .catch(() => doneRetrying())
}

bridge.onFeature('engine-link', (p) => p && onLink(p as LinkInfo))
// Connect as soon as the renderer loads (review A16): main tries now if it's down, and says where the link is.
bridge
  .invoke<LinkInfo>('engine-link:retry')
  .then((l) => (l ? onLink(l) : undefined))
  .catch(() => {
    set({ link: 'unsupported' })
    syncOffline()
  })
syncOffline()

useLesson.subscribe((s, prev) => {
  if (s.notice && s.notice !== prev.notice) showNotice(s.notice)
  if (s.connected !== prev.connected) {
    if (!s.connected) downAt = Date.now()
    syncOffline()
  }
})

/** Off-track episodes whose amber pulse has been seen, so hover/card remounts don't pulse again. */
export const pulsedOfftrack = new WeakSet<object>()
