/**
 * Feature: settings. The Shortcuts section's rows and the stage-only recorder's key handling (pure, no React).
 *
 * Keycaps on the rows come from bridge.platform.keys only (core/ui/Keycap). A key the learner records is stored in
 * prefs.shortcuts as an Electron accelerator (validated by common/prefs isAccelerator) and shown as
 * plain words, never as a keycap: live rebinding is wave 2, so a stored key is not what the app listens to yet.
 */
import type { ShortcutKind } from '../../../../main/platform'
import { VOICE_ENABLED } from '../../../../common/flags'
import { isAccelerator, type ShortcutPrefs } from '../../../../common/prefs'
import type { KeyName } from '../../core/ui/Keycap'
import type { OptionAction } from '../../core/theme'

export type ShortcutRow = {
  key: KeyName
  label: string
  /** An option (Explain, Hint, Show me, Diagram): its label sits on its pastel chip. Chrome rows stay plain. */
  option?: OptionAction
  /** Dismiss (Esc) is fixed. */
  fixed?: boolean
}

/** Watch has no shortcut this push (decision 3); Voice keeps its key. */
export const SHORTCUT_ROWS: readonly ShortcutRow[] = ([
  { key: 'launcher', label: 'Open launcher' },
  { key: 'explain', label: 'Explain', option: 'explain' },
  { key: 'hint', label: 'Hint', option: 'hint' },
  { key: 'show_me', label: 'Show me', option: 'show_me' },
  { key: 'diagram', label: 'Diagram', option: 'diagram' },
  { key: 'back', label: 'Back' },
  { key: 'voice_toggle', label: 'Voice' },
  { key: 'dismiss', label: 'Dismiss', fixed: true }
] satisfies ShortcutRow[]).filter((r) => VOICE_ENABLED || r.key !== 'voice_toggle') // voice is off for now (common/flags)

const SHORTCUT_KINDS: readonly string[] = ['launcher', 'back', 'explain', 'diagram', 'show_me', 'hint', 'voice_toggle']
export const isShortcutKind = (k: unknown): k is ShortcutKind => typeof k === 'string' && SHORTCUT_KINDS.includes(k)

const MODIFIER_KEYS = new Set(['Control', 'Alt', 'Shift', 'Meta', 'AltGraph', 'CapsLock', 'Fn', 'OS'])
const NAMED: Record<string, string> = {
  Space: 'Space',
  ArrowLeft: 'Left',
  ArrowRight: 'Right',
  ArrowUp: 'Up',
  ArrowDown: 'Down',
  Enter: 'Enter',
  Tab: 'Tab',
  Backspace: 'Backspace',
  Delete: 'Delete',
  Minus: '-',
  Equal: '=',
  BracketLeft: '[',
  BracketRight: ']',
  Backslash: '\\',
  Semicolon: ';',
  Quote: "'",
  Comma: ',',
  Period: '.',
  Slash: '/',
  Backquote: '`'
}

/** The key part of an accelerator from KeyboardEvent.code (layout-independent: ⌥ on a Mac changes e.key). */
function keyOf(code: string): string | undefined {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3)
  if (/^Digit[0-9]$/.test(code)) return code.slice(5)
  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) return code
  return NAMED[code]
}

export type Recorded = { kind: 'modifiers' } | { kind: 'accelerator'; value: string } | { kind: 'invalid'; reason: string }

/** One keydown while recording: still holding modifiers, a full accelerator, or a combination we can't use. */
export function record(e: { code: string; key: string; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }, mac: boolean): Recorded {
  if (MODIFIER_KEYS.has(e.key)) return { kind: 'modifiers' }
  const key = keyOf(e.code)
  if (!key) return { kind: 'invalid', reason: 'That key can’t be used.' }
  const mods: string[] = []
  if (e.ctrlKey) mods.push('Control')
  if (e.altKey) mods.push('Alt')
  if (e.shiftKey) mods.push('Shift')
  if (e.metaKey) mods.push(mac ? 'Command' : 'Super')
  if (!mods.length || (mods.length === 1 && mods[0] === 'Shift')) return { kind: 'invalid', reason: mac ? 'Add Control, Option or Command.' : 'Add Ctrl or Alt.' }
  const value = [...mods, key].join('+')
  return isAccelerator(value) ? { kind: 'accelerator', value } : { kind: 'invalid', reason: 'That key can’t be used.' }
}

/** Which other shortcut already uses this accelerator (the platform default or a stored one). */
export function conflictWith(value: string, kind: ShortcutKind, defaults: Record<ShortcutKind, string>, stored: ShortcutPrefs): ShortcutKind | undefined {
  const norm = (a: string): string => a.toLowerCase().replace(/cmdorctrl|commandorcontrol/g, 'command').replace(/\boption\b/g, 'alt')
  const want = norm(value)
  for (const k of SHORTCUT_KINDS as ShortcutKind[]) {
    if (k === kind) continue
    if (norm(stored[k] ?? defaults[k]) === want) return k
  }
  return undefined
}

/** An accelerator as words for the row ("Control Option J" on a Mac). Words, not keycap symbols. */
export function words(accelerator: string, mac: boolean): string {
  return accelerator
    .split('+')
    .map((p) => (p === 'Alt' && mac ? 'Option' : p))
    .join(' ')
}
