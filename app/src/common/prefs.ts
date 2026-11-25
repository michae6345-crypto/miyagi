/** General preferences (Settings → General), shared by main (src/main/prefs.ts) and the renderer (core/prefs.ts). */
import type { ShortcutKind } from '../main/platform'
import { cleanConsent, type Consent } from './consent'
import type { IslandPlace } from './notch'

export type Appearance = 'system' | 'light' | 'dark'
/** v2: what to do with a crash report (Err-CrashConsent). Local only either way; nothing is uploaded this push. */
export type CrashReports = 'ask' | 'always' | 'never'
/**
 * The learner's own key for a shortcut, as an Electron accelerator ("Control+Alt+E"). Live: main registers it in place of
 * the platform default (main/shortcutKeys.ts) and every keycap follows it (common/shortcuts.ts, core/keys.ts).
 */
export type ShortcutPrefs = Partial<Record<ShortcutKind, string>>

/** Push to talk (Settings > General): the hold-to-ask chord. fn+control is the default; control+option is for keyboards without Fn. */
export type PttChord = 'fn+control' | 'control+option'
export type PttPrefs = { enabled: boolean; chord: PttChord }
/** Where the island lives (Settings > General). Notch is the default; it only takes effect on a Mac with a notch (common/notch.ts effectivePlace). */
export type IslandPrefs = { place: IslandPlace }
export const ISLAND_PLACES: readonly IslandPlace[] = ['notch', 'below']

export const PTT_CHORDS: readonly PttChord[] = ['fn+control', 'control+option']

export type Prefs = {
  /** The glass panels (shortcut bar, player, drawer) follow this. The island and cards stay black. */
  appearance: Appearance
  /** Turn voice on when a lesson starts. */
  voiceOnStart: boolean
  /** Open Miyagi when the computer starts. */
  launchAtLogin: boolean
  // ---- v2 (W0-5) ----
  /** The lesson panel was collapsed to the Mini pill last time (Les-Mini): reopen that way. */
  panelCollapsed: boolean
  /** Onboarding finished once on this Mac (A3 also keeps its own done flag in userData). */
  onboarded: boolean
  /** Crash reports: ask (default), always keep, never keep. */
  crashReports: CrashReports
  /** Count which buttons get used (local only). Off by default; the Privacy switch is hidden this push. */
  usageCounts: boolean
  /** Shortcut overrides (Settings → Shortcuts). Applied live; main drops one another app already owns. */
  shortcuts: ShortcutPrefs
  /** Settings › Privacy "Share crash reports and usage" (main/features/telemetry.ts). Off by default, for everyone. */
  shareTelemetry: boolean
  /** Push to talk: on by default (when PTT_ENABLED), and which chord. Send the whole object in a patch. */
  ptt: PttPrefs
  /** The island in the notch or below the menu bar. Send the whole object in a patch. */
  island: IslandPrefs
  /**
   * The learner agreed to the terms and privacy policy (common/consent.ts): which version, and when. Absent until they
   * continue past the consent screen. Written only by main (onboarding:agree); a renderer's prefs:set can't set it.
   */
  consent?: Consent
}

export const DEFAULT_PREFS: Prefs = {
  appearance: 'light',
  voiceOnStart: false,
  launchAtLogin: false,
  panelCollapsed: false,
  onboarded: false,
  crashReports: 'ask',
  usageCounts: false,
  shortcuts: {},
  shareTelemetry: false,
  ptt: { enabled: true, chord: 'fn+control' },
  island: { place: 'notch' }
}

export const SHORTCUT_KINDS: readonly ShortcutKind[] = ['launcher', 'back', 'explain', 'diagram', 'show_me', 'hint', 'voice_toggle']
const MODIFIER = /^(Command|Cmd|Control|Ctrl|CommandOrControl|CmdOrCtrl|Alt|Option|AltGr|Shift|Super|Meta)$/
const KEY = /^([A-Z0-9]|F([1-9]|1[0-9]|2[0-4])|Space|Left|Right|Up|Down|Enter|Tab|Backspace|Delete|Escape|Plus|[,./;'[\]\\`=-])$/

/** An Electron accelerator with 1 to 3 modifiers and one key. A bare key is refused (it would type into the editor). */
export function isAccelerator(s: unknown): s is string {
  if (typeof s !== 'string' || s.length > 48) return false
  const parts = s.split('+')
  if (parts.length < 2 || parts.length > 4) return false
  const key = parts.pop()!
  return KEY.test(key) && parts.every((p) => MODIFIER.test(p)) && new Set(parts).size === parts.length
}

/** Keep only known keys with valid values (prefs come from a file and from any window). */
export function sanitizePrefs(raw: unknown): Partial<Prefs> {
  const out: Partial<Prefs> = {}
  if (!raw || typeof raw !== 'object') return out
  const r = raw as Record<string, unknown>
  if (r.appearance === 'system' || r.appearance === 'light' || r.appearance === 'dark') out.appearance = r.appearance
  if (typeof r.voiceOnStart === 'boolean') out.voiceOnStart = r.voiceOnStart
  if (typeof r.launchAtLogin === 'boolean') out.launchAtLogin = r.launchAtLogin
  if (typeof r.panelCollapsed === 'boolean') out.panelCollapsed = r.panelCollapsed
  if (typeof r.onboarded === 'boolean') out.onboarded = r.onboarded
  if (r.crashReports === 'ask' || r.crashReports === 'always' || r.crashReports === 'never') out.crashReports = r.crashReports
  if (typeof r.usageCounts === 'boolean') out.usageCounts = r.usageCounts
  if (typeof r.shareTelemetry === 'boolean') out.shareTelemetry = r.shareTelemetry
  if (r.ptt && typeof r.ptt === 'object' && !Array.isArray(r.ptt)) {
    const p = r.ptt as Record<string, unknown>
    out.ptt = {
      enabled: typeof p.enabled === 'boolean' ? p.enabled : DEFAULT_PREFS.ptt.enabled,
      chord: PTT_CHORDS.includes(p.chord as PttChord) ? (p.chord as PttChord) : DEFAULT_PREFS.ptt.chord
    }
  }
  if (r.island && typeof r.island === 'object' && !Array.isArray(r.island)) {
    const p = (r.island as Record<string, unknown>).place
    out.island = { place: ISLAND_PLACES.includes(p as IslandPlace) ? (p as IslandPlace) : DEFAULT_PREFS.island.place }
  }
  const consent = cleanConsent(r.consent)
  if (consent) out.consent = consent
  if (r.shortcuts && typeof r.shortcuts === 'object' && !Array.isArray(r.shortcuts)) {
    const s: ShortcutPrefs = {}
    for (const k of SHORTCUT_KINDS) {
      const v = (r.shortcuts as Record<string, unknown>)[k]
      if (isAccelerator(v)) s[k] = v
    }
    out.shortcuts = s
  }
  return out
}
