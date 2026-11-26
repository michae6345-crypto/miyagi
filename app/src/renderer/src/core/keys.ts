/**
 * Core: live keycap labels. A shortcut the learner rebound (Settings > Shortcuts, prefs.shortcuts) shows its own key
 * everywhere at once; every other key keeps the platform's label (bridge.platform.keys stays the default and the only
 * source for settings, dismiss and push to talk). The label is built from the accelerator in the same glyph style
 * (common/shortcuts.ts acceleratorLabel: ⌃⌥E on a Mac, Alt+E on Windows), never typed by hand.
 *
 *   useKey('explain')        '⌃⌥E', or the learner's own key; re-renders when it changes
 *   useKeys()                every key name's live label (for code that indexes by kind: keys[action])
 *   liveKeyLabel('hint')     the same, read once (outside React)
 *   useAccelerators()        every shortcut's accelerator in effect (the settings clash check)
 *   useTaken(s => s.explain) 'default' | 'none' | undefined: the saved key another app owns (main fell back)
 *
 * A saved key another app owns (main/shortcutKeys.ts, found when main registers it) is not the key in effect: main bound
 * the platform default instead, or nothing. Main sends which kinds fell back (feat:shortcuts:taken); the label then shows
 * the default, or no keycap at all. The override stays in prefs, so Settings still shows it can be reset.
 */
import { useMemo } from 'react'
import { create } from 'zustand'
import type { KeyName, ShortcutKind } from '../../../main/platform'
import { effectiveAccelerators, effectiveLabel, sanitizeFallbacks, type ShortcutFallbacks } from '../../../common/shortcuts'
import type { ShortcutPrefs } from '../../../common/prefs'
import { bridge, isElectron, registerWebHandler } from '../bridge'
import { usePrefs } from './prefs'

/** The rebound shortcuts main could not bind to their saved key (main's state, never saved). */
export const useTaken = create<ShortcutFallbacks>(() => ({}))
const setTaken = (x: unknown): void => useTaken.setState(sanitizeFallbacks(x), true)

// Browser stage: no main. ?taken=explain (fell back to the default) or ?taken=explain:none (no key) for the stage shots.
if (!isElectron) {
  const fell: ShortcutFallbacks = {}
  for (const part of (new URLSearchParams(location.search).get('taken') ?? '').split(',').filter(Boolean)) {
    const [k, v] = part.split(':')
    Object.assign(fell, sanitizeFallbacks({ [k]: v ?? 'default' }))
  }
  registerWebHandler('shortcuts:taken', () => fell)
}
bridge.invoke('shortcuts:taken').then(setTaken).catch(() => undefined)
bridge.onFeature('shortcuts:taken', setTaken)

const ALL: readonly KeyName[] = ['launcher', 'back', 'explain', 'diagram', 'show_me', 'hint', 'voice_toggle', 'settings', 'dismiss', 'ptt', 'ptt_alt']

/** The label for a key name right now, or undefined when this platform has none. */
export function liveKeyLabel(k: KeyName): string | undefined {
  return effectiveLabel(k, bridge.platform, usePrefs.getState().shortcuts, useTaken.getState())
}

/** The live label for a key name (undefined for no name, or none on this platform). */
export function useKey(k: KeyName | undefined): string | undefined {
  const overrides = usePrefs((s) => s.shortcuts)
  const taken = useTaken()
  return k ? effectiveLabel(k, bridge.platform, overrides, taken) : undefined
}

const labels = (overrides: ShortcutPrefs, taken: ShortcutFallbacks): Record<KeyName, string> => {
  const out = { ...bridge.platform.keys }
  for (const k of ALL) out[k] = effectiveLabel(k, bridge.platform, overrides, taken) ?? ''
  return out
}

/** Every key name's live label, like bridge.platform.keys but following the learner's own shortcuts. */
export function useKeys(): Record<KeyName, string> {
  const overrides = usePrefs((s) => s.shortcuts)
  const taken = useTaken()
  return useMemo(() => labels(overrides, taken), [overrides, taken])
}

/** Every shortcut's accelerator in effect: the learner's own, else the platform's. */
export function useAccelerators(): Record<ShortcutKind, string> {
  const overrides = usePrefs((s) => s.shortcuts)
  return useMemo(() => effectiveAccelerators(bridge.platform.accelerators, overrides), [overrides])
}
