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
import { bridge } from '../bridge'
import { emitUi, onMessage, onUi } from './bus'

export type ActionShortcut = Exclude<ShortcutKind, 'launcher'>
export type ActionKind = AppCommands['action']['kind']

/**
 * The last action the learner sent (shortcut, bar click, card button). With useThinking() from core/lesson it
 * puts the spinner on the button that was pressed: `thinking && pressed === kind`. Cleared when the engine
 * answers with something visible (card, offtrack, diagram, spotlight) or the lesson resets.
 */
export const usePressed = create<{ kind?: ActionKind; at: number }>(() => ({ kind: undefined, at: 0 }))
const clearPressed = (): void => usePressed.setState({ kind: undefined, at: Date.now() })
for (const t of ['card', 'offtrack', 'diagram', 'spotlight', 'lesson.ended'] as const) onMessage(t, clearPressed)
onUi('reset', clearPressed)

/** Send action {kind} to the engine and remember it as pressed. Use this for every action button. */
export function sendAction(kind: ActionKind, text?: string): void {
  usePressed.setState({ kind, at: Date.now() })
  bridge.send(cmd('action', text === undefined ? { kind } : { kind, text }))
}

export function triggerShortcut(kind: ActionShortcut): void {
  if (emitUi('shortcut', kind)) return
  sendAction(kind)
}
