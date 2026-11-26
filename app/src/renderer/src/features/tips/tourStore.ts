/**
 * Feature: tips. State of the first-lesson walkthrough (TourLayer.tsx). It starts from "Show me around" on You're ready, from
 * the menu bar item and from Settings or Help (startTour), and by itself once after a first run (shell/flow asks main:
 * requestAutoTour). It never starts a lesson: the sample panel is drawn here.
 *
 * The overlay is its own window in Electron and the only one that draws the tour. Main owns whether it is open
 * (main/features/onboarding.ts, rules in main/features/onboarding/tour.ts): every start goes to main
 * (onboarding:tour 'start'), main broadcasts feat:onboarding:tour {open, seq} to every window, and the overlay opens on
 * it, on its first mark, every time (an earlier copy skipped a start when its local state already read open, so a
 * stuck "open" made Settings' Start do nothing). A start asked for while the launch gate is closed is held by main until
 * it opens. When the overlay's gate opens it also asks onboarding:get (tour.open), so a start it missed while loading
 * or hidden still shows. Done or skipped is remembered by main (onboarding.json tourSeen).
 */
import { create } from 'zustand'
import { bridge, isElectron } from '../../bridge'
import { onGateOpen } from '../../core/gate'
import { TOUR } from './tourMarks'

export const useTour = create<{ open: boolean; index: number }>(() => ({ open: false, index: 0 }))
const set = useTour.setState
const get = useTour.getState

/** This window draws the tour: the overlay in Electron, the one stage page in a browser. */
export const drawsTour = !isElectron || (typeof location !== 'undefined' && location.hash.replace(/^#\/?/, '') === 'overlay')

const tell = (what: 'start' | 'end' | 'seen' | 'auto'): Promise<unknown> => {
  try {
    return bridge.invoke('onboarding:tour', what).catch(() => undefined)
  } catch {
    /* the stage has no main: the local state is enough */
    return Promise.resolve(undefined)
  }
}

/** Open the walkthrough on its first mark (here at once when this window draws it; everywhere through main). */
export function startTour(): void {
  if (drawsTour) set({ open: true, index: 0 })
  void tell('start')
}

export function nextMark(): void {
  const i = get().index + 1
  if (i >= TOUR.length) return endTour()
  set({ index: i })
}

/** Jump to a mark (TourLayer skips one whose target isn't on screen). Past the last one ends the tour. */
export function goToMark(i: number): void {
  if (!get().open) return
  if (i < 0 || i >= TOUR.length) return endTour()
  if (i !== get().index) set({ index: i })
}

/**
 * Done, skipped or Esc: closed for good (never offered or auto-started again). `seen: false` closes it without that
 * (a real lesson took the floor: the tour is still owed).
 */
export function endTour(opts: { seen?: boolean } = {}): void {
  if (!get().open) return
  set({ open: false, index: 0 })
  if (opts.seen !== false) void tell('seen')
  void tell('end')
}

/** You're ready's Skip: the learner declined the tour; it won't start by itself later. */
export function declineTour(): void {
  void tell('seen')
}

/** The first-run flow handed over to home: main starts the tour once, if a first run made it due (Electron only). */
export function requestAutoTour(): void {
  if (!isElectron) return
  void tell('auto')
}

/** A feat:onboarding:tour broadcast (or onboarding:get's tour) as this window applies it. Pure for tests. */
export function applyTourSignal(cur: { open: boolean; index: number }, p: unknown): { open: boolean; index: number } {
  const open = !!p && typeof p === 'object' && (p as { open?: unknown }).open === true
  if (open) return { open: true, index: 0 } // every start opens it on the first mark, already open or not
  return cur.open ? { open: false, index: 0 } : cur
}

// Browser stage: ?tour=1 (or ?tour=3 for the third mark) opens the walkthrough once the stage is up, for shots and by hand.
if (!isElectron && typeof location !== 'undefined') {
  const q = new URLSearchParams(location.search).get('tour')
  if (q !== null) setTimeout(() => set({ open: true, index: Math.max(0, Math.min(TOUR.length - 1, (Number(q) || 1) - 1)) }), 1500)
}

if (drawsTour) {
  /** The last start applied (main's seq), so a late onboarding:get answer never restarts a tour already under way. */
  let lastSeq = -1
  bridge.onFeature('onboarding:tour', (p) => {
    const seq = Number((p as { seq?: unknown } | undefined)?.seq)
    if (Number.isFinite(seq)) lastSeq = Math.max(lastSeq, seq)
    const next = applyTourSignal(get(), p)
    if (next.open !== get().open || next.index !== get().index) set(next)
  })
  // The overlay's gate opened (it loads hidden behind it): catch a start main already broadcast before we listened.
  if (isElectron) {
    onGateOpen(() => {
      let p: Promise<unknown>
      try {
        p = bridge.invoke<unknown>('onboarding:get')
      } catch {
        return
      }
      p.then(
        (r) => {
          const t = (r as { tour?: { open?: unknown; seq?: unknown } } | undefined)?.tour
          const seq = Number(t?.seq)
          if (t?.open !== true || !Number.isFinite(seq) || seq <= lastSeq) return
          lastSeq = seq
          if (!get().open) set({ open: true, index: 0 })
        },
        () => undefined
      )
    })
  }
}
