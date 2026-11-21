/**
 * Feature: reminders. The renderer's state:
 *
 *   s          the settings as main has them (main/features/reminders.ts; the browser stage: web.ts). undefined until
 *              the first answer, so nothing is offered before we know whether it was answered already.
 *   offer      the one-time "Want a nudge when a review is due?" card. Armed when a lesson's completion card closes
 *              (this app session), shown at the next idle moment (no other card, no lesson building or running other
 *              than the one just finished). Answered once (Yes, Not now or Esc), it never comes back.
 *   toast      a reminder shown inside the app: the browser stage's simulation of the macOS notification, and a dev
 *              build's stand-in (main sends feat:reminders:toast instead of posting a real one).
 *
 * The dashboard's daily goal and rest live in that feature's localStorage; every window that has them reports the
 * current values to main, so the scheduler can say "2 reps left for today's goal" with the learner's own number.
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { onUi } from '../../core/bus'
import { notify, useLesson } from '../../core/lesson'
import { openWindow } from '../../core/surfaces'
import { useComplete } from '../complete/store'
import { goalsFor } from '../dashboard/model'
import { useDash } from '../dashboard/store'
import { fmtTime, type ReminderNote, type ReminderSettings, type ReminderState } from './logic'

/** A beat after the completion card folds away, so the offer never feels like it chased the learner. */
const OFFER_DELAY_MS = 900
/** How long the in-app toast stays (macOS banners stay about this long too). */
export const TOAST_MS = 8000

export type Toast = ReminderNote & { at: number; id: number }

type Store = {
  s?: ReminderState
  /** The completion card closed in this session: the offer may show at the next idle moment. */
  offerArmed: boolean
  /** The lesson that was just finished (its own lesson state doesn't count as "busy"). */
  finishedLesson?: string
  /** The offer card is on screen right now (its Content is mounted). */
  showing: boolean
  toast?: Toast
}

export const useReminders = create<Store>(() => ({ s: undefined, offerArmed: false, showing: false }))
const set = useReminders.setState
const get = useReminders.getState

const accept = (s: unknown): void => {
  if (s && typeof s === 'object' && 'enabled' in s) set({ s: s as ReminderState })
}

export async function loadReminders(): Promise<void> {
  const s = await bridge.invoke<ReminderState>('reminders:get').catch(() => undefined)
  accept(s)
}
bridge.onFeature('reminders', accept)

export async function patchReminders(patch: Partial<ReminderSettings>): Promise<void> {
  const cur = get().s
  if (cur) set({ s: { ...cur, ...patch } })
  const next = await bridge.invoke<ReminderState>('reminders:set', patch).catch(() => undefined)
  accept(next)
}

export async function snooze(kind: 'day' | 'week' | 'clear'): Promise<void> {
  const next = await bridge.invoke<ReminderState>('reminders:snooze', kind).catch(() => undefined)
  accept(next)
}

// ---- the toast ----------------------------------------------------------------------------------------------------

let toastSeq = 0
let toastTimer: ReturnType<typeof setTimeout> | undefined
const params = typeof location === 'undefined' ? new URLSearchParams() : new URLSearchParams(location.search)
/** Browser stage: `?reminders=toast&hold` keeps the toast up for screenshots. */
const HOLD = params.has('hold')

export function showToast(note: ReminderNote): void {
  clearTimeout(toastTimer)
  set({ toast: { ...note, at: Date.now(), id: ++toastSeq } })
  if (!HOLD) toastTimer = setTimeout(closeToast, TOAST_MS)
}
export function closeToast(): void {
  clearTimeout(toastTimer)
  if (get().toast) set({ toast: undefined })
}
/** The notification's click: the home window, on Home. */
export function openHome(): void {
  closeToast()
  void openWindow('library', { page: 'home', from: 'reminder' })
}

/** Only the window that draws the island shows the offer and the toast (every window loads this module). */
export const drawsIsland = (): boolean => {
  const route = typeof document === 'undefined' ? undefined : document.documentElement.dataset.route
  return route === 'overlay' || route === 'stage'
}

bridge.onFeature('reminders:toast', (n) => {
  if (!drawsIsland() || !n || typeof n !== 'object') return
  const note = n as Partial<ReminderNote>
  if (typeof note.body === 'string' && note.body) showToast({ title: note.title || 'miyagi', body: note.body, kind: note.kind ?? 'review' })
})

// ---- the offer ----------------------------------------------------------------------------------------------------

let armTimer: ReturnType<typeof setTimeout> | undefined
useComplete.subscribe((c, prev) => {
  if (!drawsIsland()) return
  if (c.card && !prev.card) {
    set({ finishedLesson: useLesson.getState().lesson?.id ?? 'finished', offerArmed: false })
    clearTimeout(armTimer)
    const s = get().s
    if (s && !s.completedOnce) void patchReminders({ completedOnce: true })
  }
  if (!c.card && prev.card && get().finishedLesson) {
    clearTimeout(armTimer)
    armTimer = setTimeout(() => set({ offerArmed: true }), OFFER_DELAY_MS)
  }
})

/** The island mode's hook: is the offer wanted right now? */
export function useOfferActive(): boolean {
  const want = useReminders((r) => r.offerArmed && !!r.s && r.s.supported && !r.s.offered && !r.s.enabled)
  const finished = useReminders((r) => r.finishedLesson)
  const busy = useLesson((l) => l.building || (!!l.lesson && l.lesson.id !== finished))
  const card = useComplete((c) => !!c.card)
  return want && !busy && !card
}

export function setShowing(on: boolean): void {
  if (get().showing !== on) set({ showing: on })
}

export function answerOffer(yes: boolean): void {
  set({ offerArmed: false, showing: false })
  // Yes: main sends the welcome notification at once (it is the confirmation, and macOS asks for permission right
  // then). The pill only says it when notifications can't show here at all.
  void patchReminders(yes ? { offered: true, enabled: true } : { offered: true })
  const s = get().s
  if (yes && s && !s.supported) notify(`Reminders on. ${fmtTime(s.time)}, only when something is due.`)
  if (!yes) notify('No reminders. You can turn them on in Settings.')
}

// Esc while the offer is up answers it ("Not now"); Esc on anything else leaves it armed.
onUi('dismiss', () => {
  if (get().showing) answerOffer(false)
})

// ---- the dashboard's goal, reported to main -------------------------------------------------------------------------

let goalTimer: ReturnType<typeof setTimeout> | undefined
function reportGoal(): void {
  clearTimeout(goalTimer)
  goalTimer = setTimeout(() => {
    const cur = get().s
    if (!cur) return
    const d = useDash.getState()
    // Only a window that knows something: its own choice on this Mac, or the engine's settings.
    if (d.prefs.daily === undefined && !d.data?.settings.dailyGoal && d.prefs.pause === undefined) return
    const g = goalsFor(d.data, d.prefs)
    const restUntil = g.pause && g.pause.until > Date.now() ? g.pause.until : null
    const dailyGoal = d.prefs.daily ?? d.data?.settings.dailyGoal ?? null
    if (cur.dailyGoal !== dailyGoal || cur.restUntil !== restUntil) void patchReminders({ dailyGoal, restUntil })
  }, 400)
}
useDash.subscribe((d, prev) => {
  if (d.prefs !== prev.prefs || d.data?.settings !== prev.data?.settings) reportGoal()
})
useReminders.subscribe((r, prev) => {
  if (r.s && !prev.s) reportGoal()
})

// After every module's top level ran (the browser stage registers its stand-in handlers in web.ts).
setTimeout(() => void loadReminders())
