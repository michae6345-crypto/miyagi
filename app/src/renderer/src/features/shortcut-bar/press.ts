/**
 * The 90 ms press: whichever way a shortcut fires (bar click, global key, stage key, launcher chip), the
 * matching tile dips to press.scale (.97) on the house spring and back. Listens to every 'shortcut', claimed or not, and never claims one.
 */
import { create } from 'zustand'
import { onUi } from '../../core/bus'
import { press } from '../../core/ui/motion'

export const PRESS_MS = 90
/** The house press (core/ui/motion press.scale), on the spring: the bar's tiles dip like every other control. */
export const PRESS_SCALE = press.scale

/** The kind being pressed right now (for PRESS_MS), else undefined. */
export const usePress = create<{ kind?: string }>(() => ({ kind: undefined }))

let timer: ReturnType<typeof setTimeout> | undefined
onUi('shortcut', (kind) => {
  // A second press inside 90 ms restarts the timer, so the first one's release can't cut it short.
  clearTimeout(timer)
  usePress.setState({ kind: kind as string })
  timer = setTimeout(() => usePress.setState({ kind: undefined }), PRESS_MS)
})
onUi('reset', () => {
  clearTimeout(timer)
  usePress.setState({ kind: undefined })
})
