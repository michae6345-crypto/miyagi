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
 */
import { useMemo } from 'react'
import type { KeyName, ShortcutKind } from '../../../main/platform'
import { effectiveAccelerators, effectiveLabel } from '../../../common/shortcuts'
import type { ShortcutPrefs } from '../../../common/prefs'
import { bridge } from '../bridge'
import { usePrefs } from './prefs'

const ALL: readonly KeyName[] = ['launcher', 'back', 'explain', 'diagram', 'show_me', 'hint', 'voice_toggle', 'settings', 'dismiss', 'ptt', 'ptt_alt']

/** The label for a key name right now, or undefined when this platform has none. */
export function liveKeyLabel(k: KeyName): string | undefined {
  return effectiveLabel(k, bridge.platform, usePrefs.getState().shortcuts)
}

/** The live label for a key name (undefined for no name, or none on this platform). */
export function useKey(k: KeyName | undefined): string | undefined {
  const overrides = usePrefs((s) => s.shortcuts)
  return k ? effectiveLabel(k, bridge.platform, overrides) : undefined
}

const labels = (overrides: ShortcutPrefs): Record<KeyName, string> => {
  const out = { ...bridge.platform.keys }
  for (const k of ALL) {
    const l = effectiveLabel(k, bridge.platform, overrides)
    if (l) out[k] = l
  }
  return out
}

/** Every key name's live label, like bridge.platform.keys but following the learner's own shortcuts. */
export function useKeys(): Record<KeyName, string> {
  const overrides = usePrefs((s) => s.shortcuts)
  return useMemo(() => labels(overrides), [overrides])
}

/** Every shortcut's accelerator in effect: the learner's own, else the platform's. */
export function useAccelerators(): Record<ShortcutKind, string> {
  const overrides = usePrefs((s) => s.shortcuts)
  return useMemo(() => effectiveAccelerators(bridge.platform.accelerators, overrides), [overrides])
}
