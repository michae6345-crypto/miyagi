/**
 * Feature: tips. State of the first-lesson walkthrough (TourLayer.tsx). It starts from "Show me around" on You're ready, from
 * the menu bar item and from Settings or Help (startTour). It never starts a lesson: the sample panel is drawn here.
 *
 * The overlay is its own window in Electron, so a start from the home window goes through main
 * (onboarding:tour → feat:onboarding:tour), and every window's store hears it; only the overlay draws it.
 * Done or skipped is remembered by main (onboarding.json tourSeen) so Ready offers it once.
 */
import { create } from 'zustand'
import { bridge, isElectron } from '../../bridge'
import { TOUR } from './tourMarks'

export const useTour = create<{ open: boolean; index: number }>(() => ({ open: false, index: 0 }))
const set = useTour.setState
const get = useTour.getState

const tell = (what: 'start' | 'end' | 'seen'): void => {
  try {
    bridge.invoke('onboarding:tour', what).catch(() => undefined)
  } catch {
    /* the stage has no main: the local state is enough */
  }
}

/** Open the walkthrough on its first mark. */
export function startTour(): void {
  set({ open: true, index: 0 })
  tell('start')
}

export function nextMark(): void {
  const i = get().index + 1
  if (i >= TOUR.length) return endTour()
  set({ index: i })
}

/** Done, skipped or Esc: closed for good (Ready won't offer it again). */
export function endTour(): void {
  if (!get().open) return
  set({ open: false, index: 0 })
  tell('seen')
  tell('end')
}

// Browser stage: ?tour=1 (or ?tour=3 for the third mark) opens the walkthrough once the stage is up, for shots and by hand.
if (!isElectron && typeof location !== 'undefined') {
  const q = new URLSearchParams(location.search).get('tour')
  if (q !== null) setTimeout(() => set({ open: true, index: Math.max(0, Math.min(TOUR.length - 1, (Number(q) || 1) - 1)) }), 1500)
}

bridge.onFeature('onboarding:tour', (p) => {
  const open = (p as { open?: unknown } | undefined)?.open === true
  if (open !== get().open) set({ open, index: 0 })
})
