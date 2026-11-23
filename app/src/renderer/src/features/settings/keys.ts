/**
 * Feature: settings. The key names and the safe view of them, shared by main (src/main/features/settings.ts)
 * and the renderer. Pure TS: no DOM, no Electron, no React.
 *
 * Rules (agents/settings.md): keys live in main only. The renderer sends new values in a SavePatch and gets
 * back a KeysView ({set, last4}), never a key. Nothing here logs or stores anything.
 */
import type { KeyState } from '../../../../../../shared/contracts/events'
import { GEMINI_ENABLED } from '../../../../common/flags'

/**
 * The keys miyagi keeps, in display order (names as in config.keys / config.status, shared/contracts/events.ts).
 * Anthropic, Gemini and ElevenLabs. Tiger Data is dropped (v2): the contract still lists tigerUrl as optional, but the
 * app no longer stores, shows or sends it, and a stored value from an older build is ignored on the next read.
 */
export const KEY_NAMES = ['anthropic', 'gemini', 'elevenlabs'] as const
export type KeyName = (typeof KEY_NAMES)[number]

/** The app can't build a lesson without one of these or the miyagi cloud (needsKeys). Settings never opens by itself. */
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
 * The full config.keys payload: every name in KEY_NAMES, '' when unset. The engine's set_app_keys drops any key missing
 * from the payload, so a partial send would clear the others.
 */
export function fullPayload(keys: Keys): Record<KeyName, string> {
  const out = {} as Record<KeyName, string>
  for (const k of KEY_NAMES) out[k] = keys[k] ?? ''
  return out
}

/** The sidebar's sections (core/surfaces SettingsSection), in order. Here so main can check `settings:open {section}`. */
export const SECTIONS = ['general', 'permissions', 'privacy', 'account', 'shortcuts'] as const
export type Section = (typeof SECTIONS)[number]
export const isSection = (s: unknown): s is Section => typeof s === 'string' && (SECTIONS as readonly string[]).includes(s)

/** What each key is called in the sheet. */
export const KEY_LABEL: Record<KeyName, string> = {
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  elevenlabs: 'ElevenLabs'
}

/** Rows shown in the sheet. ElevenLabs is hidden: voice speaks with the computer's own voice now (Adrian, Sat),
 * but the key name stays in storage and in config.keys so the engine contract is unchanged. Gemini is hidden while
 * GEMINI_ENABLED is false (D1, Adrian, Nov 21: Claude only at launch); its name stays in storage and config.keys too. */
export const SHOWN: readonly KeyName[] = KEY_NAMES.filter((k) => k !== 'elevenlabs' && (GEMINI_ENABLED || k !== 'gemini'))

/** settings:about: what the sidebar footer shows. */
export type AboutView = { version?: string }

/** settings:delete (Privacy › Delete my data): what was erased on this Mac. */
/** signIn: false when the keys went but a sign-in file (auth.bin, login.json, cloud-link.json) could not be removed. */
export type DeleteResult = { ok: boolean; keys: KeysView; signIn?: boolean }

/** A patch that removes every stored key. */
export function clearAll(): SavePatch {
  const out: SavePatch = {}
  for (const k of KEY_NAMES) out[k] = null
  return out
}

/** The cloud install token's phase (main/features/cloud.ts CloudView, the fields this check reads). */
export type CloudPhaseView = { configured: boolean; state: 'off' | 'minting' | 'ok' | 'failed' }

/**
 * A required key the engine has no source for at all (not even its .env), and no miyagi cloud to cover it. With the
 * cloud configured and its token minted or still minting, no key is needed: never ask for one (bring-your-own-key
 * stays in Settings › Account).
 */
export function needsKeys(status: Partial<KeyStatus> | undefined, cloud?: CloudPhaseView): boolean {
  if (cloud?.configured && (cloud.state === 'ok' || cloud.state === 'minting')) return false
  return !!status && REQUIRED.some((k) => status[k] === 'missing')
}
