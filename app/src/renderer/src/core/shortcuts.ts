/**
 * One path for every shortcut, wherever it comes from (Electron global key → main → 'shortcut'
 * signal, a shortcut-bar click, a key in the browser stage):
 *   1. emitUi('shortcut', kind): features react locally and may claim it (return true)
 *   2. if nobody claimed it, send action {kind} to the engine
 */
import { create } from 'zustand'
import type { ShortcutKind } from '../../../main/platform'
import type { AppCommands } from '../../../../../shared/contracts/events'
import { cmd } from '../../../common/wire'
import { bridge, isElectron } from '../bridge'
import { emitUi, onMessage, onUi } from './bus'
import { stopBuild, useLesson } from './lesson'

export type ActionShortcut = Exclude<ShortcutKind, 'launcher'>
export type ActionKind = AppCommands['action']['kind']

/**
 * The last action the learner sent (shortcut, bar click, card button). With useThinking() from core/lesson it
 * puts the spinner on the button that was pressed: `thinking && pressed === kind`. Cleared when the engine
 * answers with something visible (card, offtrack, diagram, video.seek) or the lesson resets.
 */
export const usePressed = create<{ kind?: ActionKind; at: number }>(() => ({ kind: undefined, at: 0 }))
const clearPressed = (): void => usePressed.setState({ kind: undefined, at: Date.now() })
// video.seek is Show me's answer.
// Not 'spotlight': on Explain the engine sends one 1-89 ms after status thinking, which cleared the press before any
// spinner showed (Michael's test 11: 6.4 s of nothing). The status check below ends a press that only got a spotlight.
for (const t of ['card', 'offtrack', 'diagram', 'video.seek', 'lesson.ended'] as const) onMessage(t, clearPressed)
onUi('reset', clearPressed)
// A press is spent when the thinking spell after it ends, whatever the engine answered (or didn't).
let thinkingSincePress = false
onMessage('status', (p) => {
  if (p.state === 'thinking') thinkingSincePress = true
  else if (thinkingSincePress) {
    thinkingSincePress = false
    clearPressed()
  }
})

/** Send action {kind} to the engine and remember it as pressed. Use this for every action button. */
/** Actions the engine never "thinks" about: they must not leave a stale pressed kind for a later spinner. */
const INSTANT = new Set<ActionKind>(['voice_toggle', 'back'])

export function sendAction(kind: ActionKind, text?: string): void {
  thinkingSincePress = useLesson.getState().engineState === 'thinking'
  usePressed.setState(INSTANT.has(kind) ? { kind: undefined, at: Date.now() } : { kind, at: Date.now() })
  // Pick another (preflight card): no build is running any more; the launcher reopens on the same results.
  if (kind === 'pick_another') stopBuild()
  bridge.send(cmd('action', text === undefined ? { kind } : { kind, text }))
}

export function triggerShortcut(kind: ActionShortcut): void {
  // Electron: only the overlay window runs shortcuts (it has the bar, the cards and the spinner). Any other window
  // (the launcher) hands the press to main, which replays it in the overlay like a global key.
  if (isElectron && document.documentElement.dataset.route !== 'overlay') return bridge.emit('shortcut', kind)
  if (emitUi('shortcut', kind)) return
  sendAction(kind)
}
