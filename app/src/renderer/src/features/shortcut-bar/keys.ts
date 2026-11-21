/**
 * Alt (⌥) held down: every tile shows its keycap (hover shows one). Window keydown/keyup, so it only works where
 * the window gets keys: the browser stage and a focused window. In Electron the overlay never has focus, so there
 * hover is the way to see a key.
 */
import { create } from 'zustand'

export const useAltHeld = create<{ held: boolean }>(() => ({ held: false }))

const set = (held: boolean): void => {
  if (useAltHeld.getState().held !== held) useAltHeld.setState({ held })
}

if (typeof window !== 'undefined') {
  // e.key 'Alt' only: AltGr (typing @ or € on some layouts) reports 'AltGraph' and must not flash the keycaps.
  addEventListener('keydown', (e) => e.key === 'Alt' && set(true))
  addEventListener('keyup', (e) => e.key === 'Alt' && set(false))
  addEventListener('blur', () => set(false))
  document.addEventListener('visibilitychange', () => document.hidden && set(false))
}
