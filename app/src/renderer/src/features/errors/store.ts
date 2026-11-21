/**
 * Feature: errors. One store for every way a lesson can stall (BUILD-PLAN A7):
 *
 *   link        main's engine link ({open, attempting, failures}); "N of 5" while reconnecting, then the offline card.
 *               5 tries is a UI threshold only: main keeps retrying, and the card goes the moment the link is back.
 *   flash       a short pill line after a recovery ("Back. Picking up where you were.", "Online. ...", "Back on ...").
 *   online      navigator.onLine (with the engine's network blocker, the offline line).
 *   dismissed   cards the learner closed (Esc / a button), keyed so the NEXT failure shows again.
 *   crash       the crash report main kept from the last launch (Err-CrashConsent), shown only with no lesson.
 *
 * Reads core/lesson (blockers, paused, busy, buildFailed, localEngine, keyStatus); edits no other feature's store.
 */
import { create } from 'zustand'
import { bridge, isElectron } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { notify, useLesson } from '../../core/lesson'
// Stage stand-ins first: the crash-pending ask below runs at load.
import './web'

export type Link = { open: boolean; attempting: boolean; failures: number }
/** The UI threshold: tries shown as "N of 5", then the Engine offline card. */
export const TRIES = 5
/** How long a recovery line stays on the pill. */
const FLASH_MS = 3500
/** Restart engine / Reopen in VS Code: how long a press may spin before the card says it did not work. */
const WAIT_MS = 20_000

/**
 * The overlay window (index.html, #/overlay, as main.tsx routes it). Feature windows (library, progress, onboarding,
 * account) load this module too, but only the overlay asks about a crash or reports the lesson for the marker: a
 * window with another or partial lesson state must not overwrite it.
 */
const isOverlayWindow = typeof location === 'undefined' || /^#?\/?(overlay)?$/.test(location.hash)

export type Flash = { id: 'back' | 'online' | 'in-place'; text: string; at: number }
export type CardId = 'err-engine-offline' | 'err-build-failed' | 'err-editor-closed' | 'err-limit' | 'err-crash'

type State = {
  link?: Link
  /** The engine was connected at least once this launch: only then is a drop a "reconnect". */
  everOpen: boolean
  /** The link went down after being open (so a later open is a recovery worth a "Back." line). */
  wasDown: boolean
  flash?: Flash
  online: boolean
  /** The offline line was showing: the next online gets "Online. Checking your work now." */
  wasOffline: boolean
  /** engine offline: dismissed for this outage. */
  offlineDismissed: boolean
  /** Restart: what the last press said ('external' = started in Terminal). */
  restart?: 'starting' | 'external' | 'failed'
  /** build failed: the `at` of the failure the learner closed. */
  buildDismissedAt?: number
  /** editor closed: closed to the pill line for this pause. */
  editorDismissed: boolean
  /** editor closed: Reopen pressed, waiting for the engine to say it's back. */
  reopening: boolean
  limitDismissed: boolean
  /** Err-CrashConsent: the scrubbed report main kept from the last launch. */
  crash?: { report: string }
  /** The card of ours that is on the island right now (for Esc). */
  visible?: CardId
}

export const useErrors = create<State>(() => ({
  link: undefined,
  everOpen: false,
  wasDown: false,
  flash: undefined,
  online: typeof navigator === 'undefined' ? true : navigator.onLine !== false,
  wasOffline: false,
  offlineDismissed: false,
  restart: undefined,
  buildDismissedAt: undefined,
  editorDismissed: false,
  reopening: false,
  limitDismissed: false,
  crash: undefined,
  visible: undefined
}))

const set = useErrors.setState
const get = useErrors.getState

let flashTimer: ReturnType<typeof setTimeout> | undefined
export function flash(id: Flash['id'], text: string): void {
  clearTimeout(flashTimer)
  const f: Flash = { id, text, at: Date.now() }
  set({ flash: f })
  flashTimer = setTimeout(() => get().flash === f && set({ flash: undefined }), FLASH_MS)
}

// ---- the engine link ---------------------------------------------------------------------------------------------
function onLink(l: Link): void {
  const s = get()
  if (l.open) {
    if (s.everOpen && s.wasDown) flash('back', 'Back. Picking up where you were.')
    set({ link: l, everOpen: true, wasDown: false, offlineDismissed: false, restart: undefined })
    return
  }
  set({ link: l, wasDown: s.wasDown || s.everOpen })
}
bridge.onFeature('engine-link', (p) => {
  const l = p as Partial<Link> | undefined
  if (!l || typeof l !== 'object') return
  onLink({ open: !!l.open, attempting: !!l.attempting, failures: Math.max(0, Number(l.failures) || 0) })
})
// The first open can fire before this module loads (the stage's inline mock): core's `connected` says so too.
useLesson.subscribe((s, prev) => {
  if (s.connected && !prev.connected && !get().everOpen) set({ everOpen: true })
})
if (useLesson.getState().connected) set({ everOpen: true })
// A restart that ends in a failed engine (main/localEngine.ts) says so on the card instead of spinning.
useLesson.subscribe((s, prev) => {
  const st = s.localEngine?.state
  if (st !== prev.localEngine?.state && get().restart === 'starting' && (st === 'failed' || st === 'missing')) set({ restart: 'failed' })
})

/** Reconnecting: the try in progress ("2 of 5"), or undefined when the link is fine or past the threshold. */
export function reconnectTry(s: State): number | undefined {
  const l = s.link
  if (!s.everOpen || !l || l.open || l.failures >= TRIES) return undefined
  return Math.min(TRIES, l.failures + 1)
}
export function engineOffline(s: State): boolean {
  const l = s.link
  return s.everOpen && !!l && !l.open && l.failures >= TRIES && !s.offlineDismissed
}

// A restart the engine never answers (it runs but the link never opens) and an open_editor the engine ignores must
// not spin forever: after WAIT_MS the restart says it did not work and the editor-closed card comes back.
let restartTimer: ReturnType<typeof setTimeout> | undefined
let reopenTimer: ReturnType<typeof setTimeout> | undefined
useErrors.subscribe((s, prev) => {
  if (s.restart !== prev.restart) {
    clearTimeout(restartTimer)
    if (s.restart === 'starting') restartTimer = setTimeout(() => get().restart === 'starting' && set({ restart: 'failed' }), WAIT_MS)
  }
  if (s.reopening !== prev.reopening) {
    clearTimeout(reopenTimer)
    if (s.reopening) reopenTimer = setTimeout(() => get().reopening && set({ reopening: false, editorDismissed: false }), WAIT_MS)
  }
})

// ---- the network -------------------------------------------------------------------------------------------------
if (typeof window !== 'undefined') {
  window.addEventListener('offline', () => set({ online: false, wasOffline: true }))
  window.addEventListener('online', () => {
    set({ online: true })
    settleOnline()
  })
}
/** Offline: the Mac says so, or the engine's network blocker does. */
export function useNetOffline(): boolean {
  const engine = useLesson((s) => !!s.blockers.network)
  return useErrors((s) => !s.online) || engine
}
function settleOnline(): void {
  if (!get().online || useLesson.getState().blockers.network) return
  if (get().wasOffline) {
    set({ wasOffline: false })
    flash('online', useLesson.getState().stepId ? 'Online. Checking your work now.' : 'Online again.')
  }
}

// ---- blockers, pauses, builds ------------------------------------------------------------------------------------
useLesson.subscribe((s, prev) => {
  // network blocker on → offline line; off → maybe the "Online." line.
  if (s.blockers.network && !prev.blockers.network) set({ wasOffline: true })
  if (!s.blockers.network && prev.blockers.network) settleOnline()
  // VS Code back: the pause is over. Say where the learner is, then the pill shrinks back.
  const closed = (x: typeof s): boolean => !!x.blockers.editor_closed || x.paused?.reason === 'editor_closed'
  if (closed(prev) && !closed(s)) {
    const title = s.stepTitle.trim()
    set({ reopening: false, editorDismissed: false })
    if (s.stepId) flash('in-place', title ? `Back on ${title}` : 'Back in place')
  }
  if (!closed(prev) && closed(s)) set({ editorDismissed: false, reopening: false })
  // A new lesson starts: the crash card never shows mid-lesson (it waits for the next launch; main keeps it).
  if (s.lesson && !prev.lesson && get().crash) set({ crash: undefined })
})

onMessage('config.status', (p) => {
  if (p.cloud !== 'quota') set({ limitDismissed: false })
})

onUi('reset', (p) => {
  const scope = (p as { scope?: string } | undefined)?.scope
  set({ reopening: false, editorDismissed: false, ...(scope === 'lesson' ? {} : { buildDismissedAt: undefined }) })
})

/**
 * Esc closes our card on the island (and only ours: `visible` is set by the card while it's mounted). The lesson panel
 * counts our card as open (features/drawer othersOpen), so the same Esc never also collapses the panel.
 *   engine offline  folds into the "miyagi stopped responding [Restart]" pill line: the outage is never hidden
 *   crash           Esc is "Don't save" (its keycap sits on that button), said on the pill: "Not saved"
 */
onUi('dismiss', () => {
  const v = get().visible
  if (!v) return
  if (v === 'err-crash') {
    decideCrash(false)
    set({ visible: undefined })
    notify('Not saved', 'info', { id: 'err-crash-esc' })
    return
  }
  closeCard(v)
})

/** The folded pill line's Restart: the engine-offline card comes back. */
export function reopenOffline(): void {
  set({ offlineDismissed: false })
}

/** The engine-offline card was folded by Esc and the outage is still on. */
export function engineStopped(s: State): boolean {
  const l = s.link
  return s.everOpen && !!l && !l.open && l.failures >= TRIES && s.offlineDismissed
}

export function closeCard(id: CardId): void {
  if (id === 'err-engine-offline') set({ offlineDismissed: true })
  else if (id === 'err-build-failed') set({ buildDismissedAt: useLesson.getState().buildFailed?.at })
  else if (id === 'err-editor-closed') set({ editorDismissed: true })
  else if (id === 'err-limit') set({ limitDismissed: true })
  else if (id === 'err-crash') decideCrash(false)
  if (get().visible === id) set({ visible: undefined })
}

export function setVisible(id: CardId, on: boolean): void {
  if (on) set({ visible: id })
  else if (get().visible === id) set({ visible: undefined })
}

// ---- crash consent -----------------------------------------------------------------------------------------------
/** Ask main once, at launch, for a report it kept ('ask' only: 'always' and 'never' are settled in main). Overlay only. */
if (isOverlayWindow)
  bridge
    .invoke<{ report?: unknown } | null>('errors:crash-pending')
    .then((p) => {
      if (p && typeof p.report === 'string' && p.report.trim() && !useLesson.getState().lesson) set({ crash: { report: p.report } })
    })
    .catch(() => undefined)

export function decideCrash(save: boolean): void {
  set({ crash: undefined })
  bridge.invoke('errors:crash-decide', { save }).catch(() => undefined)
}

// ---- lesson context for a crash report (Electron overlay only: main keeps it in this launch's marker) -------------
if (isElectron && isOverlayWindow) {
  let last = ''
  let timer: ReturnType<typeof setTimeout> | undefined
  useLesson.subscribe((s) => {
    const lesson = s.lesson?.title ?? ''
    const index = s.stepId ? s.steps.findIndex((x) => x.id === s.stepId) : -1
    const total = Math.max(s.steps.length, s.lesson?.outline?.count ?? 0)
    const key = `${lesson}|${index}|${total}`
    if (key === last) return
    last = key
    clearTimeout(timer)
    timer = setTimeout(() => {
      bridge.invoke('errors:context', { lesson: lesson || undefined, step: index >= 0 ? index + 1 : undefined, total: total || undefined }).catch(() => undefined)
    }, 500)
  })
}
