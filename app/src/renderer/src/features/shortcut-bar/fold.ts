/**
 * When the bar folds to its handle (Michael's review of desktop tests 2-3, A12 and A8).
 *
 * A12: the bar covered VS Code's terminal output, notifications and status bar. During a lesson it folds to a thin
 *      handle over the middle of the status bar once the pointer has been off it for IDLE_MS. The pointer on the handle
 *      or any shortcut (a key, a launcher chip) brings it back. It never folds under the pointer, while End is armed or
 *      Skip is locked, or while the engine thinks about a press (the tile's spinner must stay in view).
 * A8:  away (front.ts: another app in front) folds it too, and the handle then also wakes the overlay.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { usePressed } from '../../core/shortcuts'

/** How long the pointer stays off the bar before it folds. */
export const IDLE_MS = 5000
/** The bar was busy when the count ran out: look again this soon. */
const RECHECK_MS = 1000

export const useFold = create<{ idle: boolean }>(() => ({ idle: false }))

/** The pointer is on the bar or its handle (CSS :hover: in Electron the overlay gets forwarded mouse moves). */
export function barHovered(): boolean {
  if (typeof document === 'undefined') return false
  return !!document.querySelector('[data-shortcut-bar]:hover, [data-shortcut-handle]:hover')
}

/** The bar's own reasons to stay open (End armed, Skip locked): ShortcutBar sets it. */
let held = (): boolean => false
export function holdWhile(fn: () => boolean): void {
  held = fn
}

const busy = (): boolean => held() || barHovered() || (useLesson.getState().engineState === 'thinking' && !!usePressed.getState().kind)

let timer: ReturnType<typeof setTimeout> | undefined
function arm(ms = IDLE_MS): void {
  clearTimeout(timer)
  timer = setTimeout(() => {
    if (!useLesson.getState().lesson) return
    if (busy()) return arm(RECHECK_MS)
    useFold.setState({ idle: true })
  }, ms)
}

/** Unfold now; fold again IDLE_MS after the pointer is off it. */
export function reveal(): void {
  if (useFold.getState().idle) useFold.setState({ idle: false })
  arm()
}

/** The pointer left the bar: the count starts over. */
export function pointerLeft(): void {
  if (!useFold.getState().idle) arm()
}

onMessage('lesson.ready', reveal)
// Any shortcut, claimed or not (never claims one: returns nothing).
onUi('shortcut', () => {
  reveal()
})
onUi('reset', () => {
  clearTimeout(timer)
  useFold.setState({ idle: false })
})
