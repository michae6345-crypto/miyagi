/**
 * Live shortcuts, shared by main (main/shortcutKeys.ts registers them) and the renderer (core/keys.ts labels them).
 * Pure: no Electron, no React, no window.
 *
 * One source of truth: the key in effect for a shortcut is the learner's own (prefs.shortcuts, an Electron accelerator)
 * or, without one, the platform's default (platform.accelerators). Its label is the platform's own (platform.keys) for a
 * default and, for an override, built from the accelerator in the same glyph style (⌃⌥E on a Mac, Alt+E on Windows).
 *
 *   effectiveAccelerators(defaults, overrides)   every ShortcutKind's key in effect
 *   acceleratorLabel('Control+Alt+E', true)      '⌃⌥E'
 *   effectiveLabel(kind, platform, overrides)    the keycap text for a shortcut, live
 *   clashOf(value, kind, defaults, overrides)    which other shortcut (or quit) already uses that key
 */
import type { KeyName, PlatformInfo, ShortcutKind } from '../main/platform'
import { SHORTCUT_KINDS, type ShortcutPrefs } from './prefs'

export { SHORTCUT_KINDS }

/** The always-available quit key (main/index.ts). Not rebindable, and no shortcut may take it. */
export const quitAccelerator = (mac: boolean): string => (mac ? 'Control+Alt+Q' : 'Alt+Q')

export const isShortcutKind = (k: unknown): k is ShortcutKind => typeof k === 'string' && (SHORTCUT_KINDS as readonly string[]).includes(k)

/** The key in effect for every shortcut: the learner's override, else the platform default. */
export function effectiveAccelerators(defaults: Record<ShortcutKind, string>, overrides: ShortcutPrefs | undefined): Record<ShortcutKind, string> {
  const out = { ...defaults }
  for (const k of SHORTCUT_KINDS) {
    const v = overrides?.[k]
    if (v) out[k] = v
  }
  return out
}

type Mod = 'Control' | 'Alt' | 'Shift' | 'Command' | 'Super' | 'AltGr'
const MOD_ORDER: readonly Mod[] = ['Control', 'Alt', 'Shift', 'Command', 'Super', 'AltGr']
const MOD_ALIAS: Record<string, Mod> = {
  control: 'Control',
  ctrl: 'Control',
  alt: 'Alt',
  option: 'Alt',
  shift: 'Shift',
  command: 'Command',
  cmd: 'Command',
  // CmdOrCtrl is ⌘ on a Mac: compared as Command (the recorder never makes one; a hand-edited prefs.json might).
  commandorcontrol: 'Command',
  cmdorctrl: 'Command',
  super: 'Super',
  meta: 'Super',
  altgr: 'AltGr'
}

/** An accelerator split into its modifiers (in one fixed order) and its key, or undefined when it isn't one. */
function parse(accelerator: string): { mods: Mod[]; key: string } | undefined {
  const parts = accelerator.split('+')
  // "Control+Plus" spells "+" out; a trailing "+" would split into an empty last part.
  if (parts.length < 2 || parts.some((p) => !p)) return undefined
  const key = parts.pop()!
  const mods = new Set<Mod>()
  for (const p of parts) {
    const m = MOD_ALIAS[p.toLowerCase()]
    if (!m) return undefined
    mods.add(m)
  }
  return { mods: MOD_ORDER.filter((m) => mods.has(m)), key }
}

/** One spelling per key combination ("Option+Ctrl+e" and "Control+Alt+E" are the same key). */
export function normalizeAccelerator(accelerator: string): string {
  const p = parse(accelerator)
  return p ? [...p.mods, p.key.toUpperCase()].join('+') : accelerator.toUpperCase()
}

export const sameAccelerator = (a: string, b: string): boolean => normalizeAccelerator(a) === normalizeAccelerator(b)

const MAC_MOD: Record<Mod, string> = { Control: '⌃', Alt: '⌥', Shift: '⇧', Command: '⌘', Super: '⌘', AltGr: '⌥' }
const WIN_MOD: Record<Mod, string> = { Control: 'Ctrl', Alt: 'Alt', Shift: 'Shift', Command: 'Ctrl', Super: 'Win', AltGr: 'AltGr' }
const KEY_GLYPH: Record<string, string> = { Left: '←', Right: '→', Up: '↑', Down: '↓', Plus: '+' }
const MAC_KEY: Record<string, string> = { Enter: '↵', Tab: '⇥', Backspace: '⌫', Delete: '⌦', Escape: 'Esc' }
const WIN_KEY: Record<string, string> = { Escape: 'Esc' }

/**
 * The keycap text for an accelerator, in the platform's glyph style: a Mac writes the modifiers as ⌃⌥⇧⌘ (Apple's order)
 * straight before the key ('Control+Alt+E' → '⌃⌥E', 'Alt+Space' → '⌥Space'); Windows joins words with + ('Alt+E',
 * 'Ctrl+Shift+Space'). Arrows are arrows on both.
 */
export function acceleratorLabel(accelerator: string, mac: boolean): string {
  const p = parse(accelerator)
  if (!p) return accelerator
  const key = KEY_GLYPH[p.key] ?? (mac ? MAC_KEY[p.key] : WIN_KEY[p.key]) ?? (p.key.length === 1 ? p.key.toUpperCase() : p.key)
  if (mac) return p.mods.map((m) => MAC_MOD[m]).join('') + key
  return [...p.mods.map((m) => WIN_MOD[m]), key].join('+')
}

type Platformish = Pick<PlatformInfo, 'os' | 'keys'>

/**
 * The keycap text for any key name, live: a rebindable shortcut with an override gets the override's label; everything
 * else (defaults, settings, dismiss, push to talk) keeps the platform's own label. Undefined when the platform has none.
 */
export function effectiveLabel(k: KeyName, platform: Platformish, overrides: ShortcutPrefs | undefined): string | undefined {
  const override = isShortcutKind(k) ? overrides?.[k] : undefined
  if (override) return acceleratorLabel(override, platform.os === 'mac')
  return (platform.keys as Partial<Record<KeyName, string>>)[k] || undefined
}

/** Which other shortcut already uses this key (its default or its override), or 'quit' for the quit key. */
export function clashOf(
  value: string,
  kind: ShortcutKind,
  defaults: Record<ShortcutKind, string>,
  overrides: ShortcutPrefs | undefined,
  mac: boolean,
  kinds: readonly ShortcutKind[] = SHORTCUT_KINDS
): ShortcutKind | 'quit' | undefined {
  if (sameAccelerator(value, quitAccelerator(mac))) return 'quit'
  const now = effectiveAccelerators(defaults, overrides)
  for (const k of kinds) {
    if (k !== kind && sameAccelerator(now[k], value)) return k
  }
  return undefined
}
