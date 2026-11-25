/**
 * Core: live custom shortcuts in main. No Electron import (index.ts hands in globalShortcut as KeyOps), so it is unit
 * tested offline (test/liveShortcuts.test.ts).
 *
 * The key in effect for a shortcut is prefs.shortcuts[kind] ?? platform.accelerators[kind] (common/shortcuts.ts). Which
 * shortcuts are registered at all is index.ts's rule, through `live(kind)`: the launcher only while the login gate is
 * open, the lesson keys only while a lesson is active, the voice key never while voice is off.
 *
 *   rebind(current, want, ops, press, fallback)
 *                                       pure: unregister what changed, register the new keys, put back the old key of
 *                                       any that failed (another app owns it), else try its fallback (the platform
 *                                       default). Returns what is bound and what failed.
 *   createShortcutKeys({...})           the controller index.ts keeps:
 *     .sync()                           bring the registered keys in line with live() and the prefs (startup, lesson
 *                                       start and end, the gate, any prefs change)
 *     .accept(next, prev)               a prefs patch's shortcuts (main/prefs.ts setShortcutCheck): an override another
 *                                       shortcut or another app already uses is refused and the previous key stays
 *     .bound()                          what is registered now (tests, logs)
 *     .taken()                          the rebound shortcuts whose saved key another app owns: bound to the platform
 *                                       default instead, or to nothing (onTaken tells the windows on every change)
 *
 * A saved override that won't register (startup, a lesson starting, the gate opening) falls back to the platform default
 * when that default is free and no other shortcut uses it. The override stays in prefs (the learner's choice), and every
 * later registration tries it again, so it works once the other app lets it go. A kind not registered now keeps what was
 * last learned about it until its override changes.
 */
import type { ShortcutPrefs } from '../common/prefs'
import { clashOf, effectiveAccelerators, sameAccelerator, SHORTCUT_KINDS, type ShortcutFallback, type ShortcutFallbacks } from '../common/shortcuts'
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
 * old key back when it had one (and nothing else took it meanwhile), else its `fallback` key (the platform default, when
 * the caller found it free of other shortcuts) if that registers; otherwise it is left unbound.
 */
export function rebind(current: Bound, want: Bound, ops: KeyOps, press: (k: ShortcutKind) => () => void, fallback: Bound = {}): RebindResult {
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
    if (old && !inUse(old) && ops.register(old, press(k))) {
      bound[k] = old
      continue
    }
    const fb = fallback[k]
    if (fb && fb !== want[k] && fb !== old && !inUse(fb) && ops.register(fb, press(k))) bound[k] = fb
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
  /** The fallbacks changed (main/index.ts broadcasts them to every window as feat:shortcuts:taken). */
  onTaken?: (taken: ShortcutFallbacks) => void
  warn?: (message: string) => void
}

export type ShortcutKeys = {
  sync(): ShortcutKind[]
  accept(next: ShortcutPrefs, prev: ShortcutPrefs): { accepted: ShortcutPrefs; refused: Refusal[] }
  bound(): Bound
  taken(): ShortcutFallbacks
}

export function createShortcutKeys(deps: ShortcutKeysDeps): ShortcutKeys {
  const { ops, defaults, mac } = deps
  const warn = deps.warn ?? ((m: string) => console.warn(m))
  const press = (k: ShortcutKind) => (): void => deps.press(k)
  let bound: Bound = {}
  /** Per kind: the override that would not register, and what is bound instead. */
  const taken = new Map<ShortcutKind, { override: string; fallback: ShortcutFallback }>()
  const takenNow = (): ShortcutFallbacks => Object.fromEntries([...taken].map(([k, t]) => [k, t.fallback]))

  const wanted = (overrides: ShortcutPrefs): Bound => {
    const now = effectiveAccelerators(defaults, overrides)
    const out: Bound = {}
    for (const k of SHORTCUT_KINDS) if (deps.live(k)) out[k] = now[k]
    return out
  }

  /** Each live override's fallback: the platform default, unless another shortcut (or quit) uses that default now. */
  const fallbacks = (overrides: ShortcutPrefs): Bound => {
    const out: Bound = {}
    for (const k of SHORTCUT_KINDS) {
      const o = overrides[k]
      const d = defaults[k]
      if (!o || !deps.live(k) || sameAccelerator(o, d)) continue
      if (!clashOf(d, k, defaults, overrides, mac, deps.kinds)) out[k] = d
    }
    return out
  }

  /**
   * After a rebind: what each override really got. A live kind whose override is bound is fine again; one bound to
   * anything else fell back. A kind not live keeps its record until its override changes or goes.
   */
  const note = (overrides: ShortcutPrefs): void => {
    const before = JSON.stringify(takenNow())
    for (const k of SHORTCUT_KINDS) {
      const o = overrides[k]
      const rec = taken.get(k)
      if (!o || (rec && rec.override !== o)) taken.delete(k)
      if (!o || !deps.live(k)) continue
      const b = bound[k]
      if (b === o) {
        taken.delete(k)
        continue
      }
      const fallback: ShortcutFallback = b ? 'default' : 'none'
      if (taken.get(k)?.fallback !== fallback) warn(`[keys] ${k} shortcut ${o} is taken by another app; ${b ? `using ${b}` : 'no key bound'}`)
      taken.set(k, { override: o, fallback })
    }
    const now = takenNow()
    if (JSON.stringify(now) !== before) deps.onTaken?.(now)
  }

  const sync = (): ShortcutKind[] => {
    const overrides = deps.overrides()
    const r = rebind(bound, wanted(overrides), ops, press, fallbacks(overrides))
    bound = r.bound
    note(overrides)
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

    // Another miyagi shortcut (or quit) already has it: the renderer checks this too, main has the last word. The key
    // checked is the one in effect, so a reset (override removed) is checked on its default: another shortcut may have
    // taken that default meanwhile.
    for (const k of changed) {
      const acc = effectiveAccelerators(defaults, accepted)[k]
      if (clashOf(acc, k, defaults, accepted, mac, deps.kinds)) {
        refused.push({ kind: k, accelerator: acc, reason: 'clash' })
        revert(k)
      }
    }

    // Registered now: swap for real, and put the old key back when the new one won't take.
    const r = rebind(bound, wanted(accepted), ops, press, fallbacks(accepted))
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
    note(accepted)
    return { accepted, refused }
  }

  return { sync, accept, bound: () => ({ ...bound }), taken: takenNow }
}
