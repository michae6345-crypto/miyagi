/**
 * Feature: settings. The key names and the safe view of them, shared by main (src/main/features/settings.ts)
 * and the renderer. Pure TS: no DOM, no Electron, no React.
 *
 * Rules (agents/settings.md): keys live in main only. The renderer sends new values in a SavePatch and gets
 * back a KeysView ({set, last4}) — never a key. Nothing here logs or stores anything.
 */
import type { KeyState } from '../../../../../../shared/contracts/events'

/** Same names as config.keys / config.status in shared/contracts/events.ts, in display order. */
export const KEY_NAMES = ['anthropic', 'gemini', 'brightdata', 'elevenlabs', 'tigerUrl'] as const
export type KeyName = (typeof KEY_NAMES)[number]

/** The app can't build a lesson without these. First run opens Settings if either is `missing`. */
export const REQUIRED: readonly KeyName[] = ['anthropic'] // Gemini is off in this build (Michael, Sat)

export type Keys = Partial<Record<KeyName, string>>
export type KeyStatus = Record<KeyName, KeyState>

export type KeyInfo = { set: boolean; last4?: string }
/** What the renderer may see. `secure` false = no safeStorage: kept in memory for this run only. */
export type KeysView = { keys: Record<KeyName, KeyInfo>; secure: boolean; status?: KeyStatus; error?: string }
/** A new value per key, `null` = remove it, absent = unchanged. */
export type SavePatch = Partial<Record<KeyName, string | null>>

/** Longer than any real key or connection URL; anything bigger is a paste accident. */
const MAX_LEN = 4096

const isName = (k: string): k is KeyName => (KEY_NAMES as readonly string[]).includes(k)

/** The last four characters, only for values long enough that four don't give much away. */
export function last4(v: string): string | undefined {
  return v.length >= 12 ? v.slice(-4) : undefined
}

export function viewOf(keys: Keys): Record<KeyName, KeyInfo> {
  const out = {} as Record<KeyName, KeyInfo>
  for (const k of KEY_NAMES) {
    const v = keys[k]
    out[k] = v ? { set: true, last4: last4(v) } : { set: false }
  }
  return out
}

/**
 * Apply a patch from the renderer (untrusted IPC input: unknown names and non-strings are ignored).
 * Values are trimmed; an empty string means "unchanged".
 */
export function mergeKeys(stored: Keys, patch: unknown): Keys {
  const next: Keys = { ...stored }
  if (!patch || typeof patch !== 'object') return next
  for (const [k, v] of Object.entries(patch as Record<string, unknown>)) {
    if (!isName(k)) continue
    if (v === null) delete next[k]
    else if (typeof v === 'string') {
      const t = v.trim()
      if (t && t.length <= MAX_LEN) next[k] = t
    }
  }
  return next
}

/** Only known names with non-empty string values (a decrypted file is checked the same way). */
export function cleanKeys(raw: unknown): Keys {
  return mergeKeys({}, raw)
}

/**
 * The full config.keys payload: EVERY name, '' when unset. The engine's set_app_keys drops any key missing
 * from the payload, so a partial send would clear the others.
 */
export function fullPayload(keys: Keys): Record<KeyName, string> {
  const out = {} as Record<KeyName, string>
  for (const k of KEY_NAMES) out[k] = keys[k] ?? ''
  return out
}

/** First run: a required key the engine has no source for at all (not even its .env). */
export function needsKeys(status: Partial<KeyStatus> | undefined): boolean {
  return !!status && REQUIRED.some((k) => status[k] === 'missing')
}
