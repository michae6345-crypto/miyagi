/**
 * Core: "Hide miyagi overlays" in a renderer (main/overlayHide.ts owns the switch). While hidden the overlay draws
 * nothing and takes no mouse (core/Overlay.tsx), but every layer stays mounted, so showing brings back exactly what was
 * there: the step panel, the island and its cards, spotlight boxes, circles, the buddy.
 *
 *   useOverlaysHidden(s => s.hidden)   for components
 *   overlaysHiddenNow()                for timers (core/Overlay.tsx's bounds report)
 *   toggleOverlays(on?)                ask main (a control on a surface); the browser stage flips it locally
 */
import { create } from 'zustand'
import { bridge, isElectron, registerWebHandler } from '../bridge'

export const useOverlaysHidden = create<{ hidden: boolean }>(() => ({ hidden: false }))
export const overlaysHiddenNow = (): boolean => useOverlaysHidden.getState().hidden

const apply = (on: unknown): void => {
  const hidden = on === true
  if (useOverlaysHidden.getState().hidden !== hidden) useOverlaysHidden.setState({ hidden })
}

export function toggleOverlays(on?: boolean): void {
  void bridge
    .invoke('overlays:toggle', on)
    .then(apply)
    .catch(() => undefined)
}

if (isElectron) {
  bridge.onFeature('overlays:hidden', apply)
  void bridge
    .invoke('overlays:hidden')
    .then(apply)
    .catch(() => undefined)
} else {
  // Browser stage: no main. The switch lives here.
  registerWebHandler('overlays:hidden', () => overlaysHiddenNow())
  registerWebHandler('overlays:toggle', (on) => (typeof on === 'boolean' ? on : !overlaysHiddenNow()))
}
