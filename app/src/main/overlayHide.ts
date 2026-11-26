/**
 * Core: "Hide miyagi overlays" (Michael, Nov 25). One switch, owned by main, that hides every overlay surface at once
 * (the step panel, the island and its cards, spotlight boxes and circles, the buddy: everything in the overlay window;
 * and the player window) and brings them back exactly as they were. Nothing is torn down while hidden: the overlay's
 * renderer keeps its state and only stops drawing and taking the mouse (core/overlayHidden.ts), and the player window
 * hides, which pauses the video (its player:visible goes false).
 *
 * Who changes it: main/features/overlay-hide.ts (its key, the menu bar item, the renderer's overlays:toggle). Who reads
 * it: overlay-raise's grab poll (grabs nothing while hidden), the player (hides / comes back), the menu bar item.
 * No window ever takes focus for it: hiding orders windows out, showing uses showInactive.
 */
type Listener = (hidden: boolean) => void

let hidden = false
const listeners = new Set<Listener>()

export const overlaysHidden = (): boolean => hidden

/** Set it; listeners hear only a change. Returns the state now. */
export function setOverlaysHidden(on: boolean): boolean {
  const next = !!on
  if (next === hidden) return hidden
  hidden = next
  for (const fn of [...listeners]) {
    try {
      fn(hidden)
    } catch (err) {
      console.warn('[overlay-hide] a listener threw', err)
    }
  }
  return hidden
}

export const toggleOverlaysHidden = (): boolean => setOverlaysHidden(!hidden)

/** Hear every change. Returns a function that stops. */
export function onOverlaysHidden(fn: Listener): () => void {
  listeners.add(fn)
  return () => void listeners.delete(fn)
}
