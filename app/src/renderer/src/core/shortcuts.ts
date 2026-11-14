/**
 * One path for every shortcut, wherever it comes from (Electron global key → main → 'shortcut'
 * signal, a shortcut-bar click, a key in the browser stage):
 *   1. emitUi('shortcut', kind): features react locally and may claim it (return true)
 *   2. if nobody claimed it, send action {kind} to the engine
 */
import type { ShortcutKind } from '../../../main/platform'
import { cmd } from '../../../common/wire'
import { bridge } from '../bridge'
import { emitUi } from './bus'

export type ActionShortcut = Exclude<ShortcutKind, 'launcher'>

export function triggerShortcut(kind: ActionShortcut): void {
  if (emitUi('shortcut', kind)) return
  bridge.send(cmd('action', { kind }))
}
