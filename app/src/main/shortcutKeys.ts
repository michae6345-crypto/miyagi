/**
 * Core: live custom shortcuts in main. No Electron import (index.ts hands in globalShortcut as KeyOps), so it is unit
 * tested offline (test/liveShortcuts.test.ts).
 *
 * The key in effect for a shortcut is prefs.shortcuts[kind] ?? platform.accelerators[kind] (common/shortcuts.ts). Which
 * shortcuts are registered at all is index.ts's rule, through `live(kind)`: the launcher only while the login gate is
 * open, the lesson keys only while a lesson is active, the voice key never while voice is off.
 *
 *   rebind(current, want, ops, press)   pure: unregister what changed, register the new keys, put back the old key of
 *                                       any that failed (another app owns it). Returns what is bound and what failed.
 *   createShortcutKeys({...})           the controller index.ts keeps:
 *     .sync()                           bring the registered keys in line with live() and the prefs (startup, lesson
 *                                       start and end, the gate, any prefs change)
 *     .accept(next, prev)               a prefs patch's shortcuts (main/prefs.ts setShortcutCheck): an override another
 *                                       shortcut or another app already uses is refused and the previous key stays
 *     .bound()                          what is registered now (tests, logs)
 */
import type { ShortcutPrefs } from '../common/prefs'
import { clashOf, effectiveAccelerators, SHORTCUT_KINDS } from '../common/shortcuts'
import type { ShortcutKind } from './platform'

export type KeyOps = {
  /** globalShortcut.register: false when the key is taken (macOS, another app, or already ours). */
  register(accelerator: string, fn: () => void): boolean
  unregister(accelerator: string): void
}
export type Bound = Partial<Record<ShortcutKind, string>>
export type RebindResult = { bound: Bound; failed: ShortcutKind[] }
/** Why a new key was not saved: another miyagi shortcut (or quit) has it, or registering it failed. */
export type Refusal = { kind: ShortcutKind; accelerator: string; reason: 'clash' | 'taken' }

/**
 * From `current` (registered now) to `want` (what should be). Only kinds whose key changed are touched. Every old key
 * goes first, so two shortcuts can trade keys. A key that won't register is reported in `failed`, and that kind gets its
 * old key back when it had one (and nothing else took it meanwhile); otherwise it is left unbound.
 */
export function rebind(current: Bound, want: Bound, ops: KeyOps, press: (k: ShortcutKind) => () => void): RebindResult {
  const bound: Bound = { ...current }
  const changed = SHORTCUT_KINDS.filter((k) => current[k] !== want[k])
  for (const k of changed) {
    const old = current[k]
    if (old) ops.unregister(old)
    delete bound[k]
  }
  const failed: ShortcutKind[] = []
  for (const k of changed) {
    const acc = want[k]
    if (!acc) continue
    if (ops.register(acc, press(k))) bound[k] = acc
    else failed.push(k)
  }
  const inUse = (acc: string): boolean => Object.values(bound).includes(acc)
  for (const k of failed) {
    const old = current[k]
    if (old && !inUse(old) && ops.register(old, press(k))) bound[k] = old
  }
  return { bound, failed }
}

export type ShortcutKeysDeps = {
  ops: KeyOps
  /** platform.accelerators */
  defaults: Record<ShortcutKind, string>
  mac: boolean
  /** The shortcuts a new key may not share a key with (default: all; index.ts leaves voice out while voice is off). */
  kinds?: readonly ShortcutKind[]
  /** The overrides in effect (getPrefs().shortcuts). */
  overrides: () => ShortcutPrefs
  /** Whether this shortcut should be registered right now (gate, lesson, voice). */
  live: (k: ShortcutKind) => boolean
  /** A registered key was pressed. */
  press: (k: ShortcutKind) => void
  warn?: (message: string) => void
}

export type ShortcutKeys = {
  sync(): ShortcutKind[]
  accept(next: ShortcutPrefs, prev: ShortcutPrefs): { accepted: ShortcutPrefs; refused: Refusal[] }
  bound(): Bound
}

export function createShortcutKeys(deps: ShortcutKeysDeps): ShortcutKeys {
  const { ops, defaults, mac } = deps
  const warn = deps.warn ?? ((m: string) => console.warn(m))
  const press = (k: ShortcutKind) => (): void => deps.press(k)
  let bound: Bound = {}

  const wanted = (overrides: ShortcutPrefs): Bound => {
    const now = effectiveAccelerators(defaults, overrides)
    const out: Bound = {}
    for (const k of SHORTCUT_KINDS) if (deps.live(k)) out[k] = now[k]
    return out
  }

  const sync = (): ShortcutKind[] => {
    const r = rebind(bound, wanted(deps.overrides()), ops, press)
    bound = r.bound
    for (const k of r.failed) warn(`[keys] ${k} shortcut ${wanted(deps.overrides())[k]} is taken by another app`)
    return r.failed
  }

  const accept = (next: ShortcutPrefs, prev: ShortcutPrefs): { accepted: ShortcutPrefs; refused: Refusal[] } => {
    const accepted: ShortcutPrefs = { ...next }
    const refused: Refusal[] = []
    const revert = (k: ShortcutKind): void => {
      if (prev[k]) accepted[k] = prev[k]
      else delete accepted[k]
    }
    const changed = SHORTCUT_KINDS.filter((k) => next[k] !== prev[k])

    // Another miyagi shortcut (or quit) already has it: the renderer checks this too, main has the last word.
    for (const k of changed) {
      const acc = next[k]
      if (acc && clashOf(acc, k, defaults, accepted, mac, deps.kinds)) {
        refused.push({ kind: k, accelerator: acc, reason: 'clash' })
        revert(k)
      }
    }

    // Registered now: swap for real, and put the old key back when the new one won't take.
    const r = rebind(bound, wanted(accepted), ops, press)
    bound = r.bound
    for (const k of r.failed) {
      if (!changed.includes(k)) continue
      const acc = effectiveAccelerators(defaults, accepted)[k]
      refused.push({ kind: k, accelerator: acc, reason: 'taken' })
      revert(k)
    }
    // A kind that failed and was reverted: its old key is registered again by rebind already (bound).

    // Not registered now (no lesson, gate closed): try the new key once and let it go, so a taken key is known today.
    for (const k of changed) {
      const acc = accepted[k]
      if (!acc || acc !== next[k] || deps.live(k)) continue
      if (ops.register(acc, () => undefined)) ops.unregister(acc)
      else {
        refused.push({ kind: k, accelerator: acc, reason: 'taken' })
        revert(k)
      }
    }
    return { accepted, refused }
  }

  return { sync, accept, bound: () => ({ ...bound }) }
}
