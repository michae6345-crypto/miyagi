/**
 * Pure decisions for live macOS permission detection (PR #286, hardening for #282). No Electron, no OS calls: the
 * caller (main/permissions.ts) feeds in what it read and gets back a verdict, a next poll delay, or a parsed probe.
 *
 * Why each input exists (failure-mode matrix in PR #286):
 *   - `main`   systemPreferences in miyagi's main process. Accessibility is read live; Screen Recording is NOT: Electron's
 *              getMediaAccessStatus('screen') wraps CGPreflightScreenCaptureAccess(), which keeps its first answer for
 *              the life of the process (electron/electron#42203; Apple's "Capturing screen content" sample: "restart
 *              the app to enable capture").
 *   - `probe`  a FRESH process (`miyagi-listen --probe-perms`, spawned by the app so TCC answers for miyagi): the only
 *              cheap way to see a Screen Recording grant without relaunching. ~5-40 ms warm, ~250 ms first spawn.
 *   - `engine` what the engine (child process, same responsible app) can actually do: ground truth for "the switch is
 *              on but it does not work" (a stale TCC row after an ad-hoc re-sign, a cached preflight in an engine
 *              that started before the grant).
 *   - `place`  where the .app runs from: translocated / disk image runs get a random read-only path.
 */

export type PermKind = 'screen' | 'accessibility'
export type PermRead = 'granted' | 'denied' | 'not-determined' | 'restricted' | 'unknown'
export type InstallPlace = 'applications' | 'translocated' | 'dmg' | 'other'

export type PermAction =
  | 'none' // granted and working
  | 'open-settings' // the user still has to flip the switch
  | 'move-to-applications' // running from the disk image or translocated: grants will not stick
  | 'restart-engine' // granted, but the engine started before the grant and still has the old answer
  | 'relaunch-app' // granted, but miyagi's own process needs it and caches the old answer
  | 'reset-entry' // the switch is (probably) on but this build is not the one macOS remembers: remove + re-add
  | 'managed' // a device profile (MDM) decides; the user cannot change it

export interface PermVerdict {
  state: 'granted' | 'denied' | 'not-determined' | 'unknown'
  action: PermAction
}

/** The .app bundle that holds this executable (…/miyagi.app/Contents/MacOS/miyagi → …/miyagi.app). */
export function appBundlePath(execPath: string): string {
  const i = execPath.indexOf('.app/Contents/')
  return i >= 0 ? execPath.slice(0, i + 4) : execPath
}

/**
 * Where the app runs from. App Translocation (Gatekeeper path randomisation) runs a quarantined app that was opened
 * where it landed from a random read-only mount under /private/var/folders/…/AppTranslocation/…; a grant made there
 * is tied to that copy and macOS may not even list it. A /Volumes/ path is the mounted .dmg. Both: "move miyagi to
 * Applications, then open it from there".
 */
export function installPlace(appPath: string): InstallPlace {
  if (!appPath) return 'other'
  if (appPath.includes('/AppTranslocation/')) return 'translocated'
  if (appPath.startsWith('/Volumes/')) return 'dmg'
  if (/^\/Applications\//.test(appPath) || /^\/Users\/[^/]+\/Applications\//.test(appPath)) return 'applications'
  return 'other'
}

/** One JSON line from `miyagi-listen --probe-perms`. Anything else (old helper, garbage, timeout text) → null. */
export function parsePermProbe(stdout: string): Partial<Record<PermKind, 'granted' | 'denied'>> | null {
  const line = stdout
    .split('\n')
    .map((l) => l.trim())
    .find((l) => l.startsWith('{'))
  if (!line) return null
  try {
    const o = JSON.parse(line) as Record<string, unknown>
    const out: Partial<Record<PermKind, 'granted' | 'denied'>> = {}
    for (const k of ['screen', 'accessibility'] as const) if (o[k] === 'granted' || o[k] === 'denied') out[k] = o[k]
    return Object.keys(out).length ? out : null
  } catch {
    return null
  }
}

export interface PermEvidence {
  /** systemPreferences in the main process (screen is cached for the process lifetime). */
  main: PermRead
  /** A fresh process's answer, when a probe ran; undefined = no probe (old helper, not macOS, timed out). */
  probe?: 'granted' | 'denied'
  /** Can the engine actually do it? true / false from its health rows, undefined = engine not up or not asked. */
  engine?: boolean
  place: InstallPlace
  /** This build's version, and the build that was running the last time this kind read granted (prefs). */
  build: string
  lastGrantedBuild?: string
  /** miyagi's main process itself needs the grant (it captures in-process). Default false: the engine captures. */
  mainNeedsIt?: boolean
}

/**
 * One verdict per kind. Order matters: the cheapest true fact wins.
 *   restricted → managed (MDM; getMediaAccessStatus says 'restricted' for a profile-denied service)
 *   fresh answer = probe ?? main
 *   fresh granted: engine says no → restart-engine; main still cached and main needs it → relaunch-app; else none
 *   fresh denied: translocated/dmg → move-to-applications; granted under another build → reset-entry; else open-settings
 */
export function judgePermission(kind: PermKind, ev: PermEvidence): PermVerdict {
  if (ev.main === 'restricted') return { state: 'denied', action: 'managed' }
  const fresh: PermRead = ev.probe ?? ev.main
  if (fresh === 'granted') {
    if (ev.engine === false) return { state: 'granted', action: 'restart-engine' }
    if (kind === 'screen' && ev.main !== 'granted' && ev.mainNeedsIt) return { state: 'granted', action: 'relaunch-app' }
    return { state: 'granted', action: 'none' }
  }
  if (fresh === 'unknown') return { state: 'unknown', action: 'none' }
  if (ev.place === 'translocated' || ev.place === 'dmg') return { state: fresh === 'not-determined' ? 'not-determined' : 'denied', action: 'move-to-applications' }
  if (ev.lastGrantedBuild && ev.lastGrantedBuild !== ev.build) return { state: 'denied', action: 'reset-entry' }
  return { state: fresh === 'not-determined' ? 'not-determined' : 'denied', action: 'open-settings' }
}

export interface PollState {
  /** The setup screen (or a "still need permissions" card) is on screen. */
  visible: boolean
  /** Kinds still not granted. Empty → stop. */
  pending: PermKind[]
  /** ms since the user clicked a step that opened System Settings; null if they have not. */
  sinceOpenMs: number | null
  /** miyagi's window has focus (the user is not in System Settings). */
  focused: boolean
}

/** While the user is in System Settings: the switch flip should show within half a second. */
export const POLL_FAST_MS = 500
/** Setup screen up, user not (recently) in System Settings. */
export const POLL_IDLE_MS = 1500
/** How long after an "open System Settings" click the fast rate lasts. */
export const FAST_WINDOW_MS = 120_000
/** After the distributed note `com.apple.accessibility.api`, re-read at these offsets: the note can land a moment
 *  before tccd commits the change, so a read at +0 alone can still see the old value. */
export const AX_NOTE_RECHECKS_MS = [0, 250, 1000] as const

/** ms until the next cheap read, or null to stop polling (screen hidden, or nothing left to wait for). */
export function nextPollMs(s: PollState): number | null {
  if (!s.visible || s.pending.length === 0) return null
  if (s.sinceOpenMs !== null && s.sinceOpenMs < FAST_WINDOW_MS) return POLL_FAST_MS
  return POLL_IDLE_MS
}

/** Probe timeouts: the first spawn of an unsigned helper can take seconds on a slow or busy Mac (Gatekeeper / XProtect
 *  scan, cold dyld cache); later spawns are tens of ms. A timeout must never flip a kind to denied. */
export const PROBE_TIMEOUT_FIRST_MS = 4000
export const PROBE_TIMEOUT_MS = 1500

/** Merge a probe outcome into the last known answer: a timeout or garbage keeps what we had. */
export function mergeProbe(
  prev: Partial<Record<PermKind, 'granted' | 'denied'>> | undefined,
  next: Partial<Record<PermKind, 'granted' | 'denied'>> | null | 'timeout'
): Partial<Record<PermKind, 'granted' | 'denied'>> | undefined {
  if (next === 'timeout' || next === null) return prev
  return { ...(prev ?? {}), ...next }
}
