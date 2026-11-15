/** General preferences (Settings → General), shared by main (src/main/prefs.ts) and the renderer (core/prefs.ts). */
export type Appearance = 'system' | 'light' | 'dark'

export type Prefs = {
  /** The glass panels (shortcut bar, player, drawer) follow this. The island and cards stay black. */
  appearance: Appearance
  /** Turn voice on when a lesson starts. */
  voiceOnStart: boolean
  /** Open Miyagi when the computer starts. */
  launchAtLogin: boolean
}

export const DEFAULT_PREFS: Prefs = { appearance: 'system', voiceOnStart: false, launchAtLogin: false }

/** Keep only known keys with valid values (prefs come from a file and from any window). */
export function sanitizePrefs(raw: unknown): Partial<Prefs> {
  const out: Partial<Prefs> = {}
  if (!raw || typeof raw !== 'object') return out
  const r = raw as Record<string, unknown>
  if (r.appearance === 'system' || r.appearance === 'light' || r.appearance === 'dark') out.appearance = r.appearance
  if (typeof r.voiceOnStart === 'boolean') out.voiceOnStart = r.voiceOnStart
  if (typeof r.launchAtLogin === 'boolean') out.launchAtLogin = r.launchAtLogin
  return out
}
