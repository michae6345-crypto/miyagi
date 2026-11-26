/**
 * Core (v2, W0-5): the macOS permissions miyagi needs, read WITHOUT prompting (Section 6: polling never prompts).
 *
 *   bridge.invoke('permissions:get')           → Permissions (now)
 *   bridge.invoke('permissions:open', kind)    open that System Settings pane (fixed URL, main/safeOpen.ts) → boolean
 *   bridge.invoke('permissions:watch', on)     this window wants live updates (the setup screen on show, Settings >
 *                                              Permissions, a recovery card); main polls only while someone watches
 *                                              and something is off, and broadcasts feat:permissions on any change
 *   bridge.invoke('permissions:relaunch')      Restart miyagi (packaged only), noting which grants it restarts for
 *   bridge.invoke('permissions:reset', kind)   tccutil reset for miyagi's row, on the learner's click only
 *
 * States: granted · denied · not-determined · restricted · unknown. `unknown` when we can't tell honestly:
 *   - the engine is EXTERNAL (started in Terminal): macOS grants belong to that Terminal, not to this app;
 *   - automation (Apple Events to VS Code): no API reads it without prompting;
 *   - not macOS (Windows reads screen and accessibility as granted: it has no such grants).
 * Prompting is never done here. A click handler that wants the prompt asks for it on purpose (onboarding, A3).
 *
 * `relaunch` (Nov 25, a learner on a MacBook Neo had to press Skip): the kinds switched on in System Settings that this
 * process can't see until miyagi restarts (macOS caches Screen Recording per process). A fresh miyagi-listen --screens
 * tells (main/permissionProbe.ts): only while something is off, a window watches, and not every off kind is already
 * known to need a restart; at most every PROBE_MIN_MS, backing off to 10 s and 30 s while nothing changes. The windows
 * offer "Restart miyagi" for them (permissions:relaunch). Accessibility is read live here, so it is flagged only when a
 * second read, at least AX_RESTART_AFTER_MS later, still disagrees with the fresh process (never a flash on a grant).
 * Restart-loop guard: a kind still in `relaunch` after miyagi restarted for it on this build gets hint 'reset' instead.
 *
 * One source, live and cheap (Nov 25): every window's banners, badges and rows read this (feat:permissions, broadcast to
 * ALL windows on any change, whoever caused the read), so a grant clears everywhere at once.
 *   events   miyagi comes back to the front (did-become-active, browser-window-focus) and macOS's
 *            com.apple.accessibility.api distributed notification (an Accessibility switch flipped): read now, always.
 *   poll     only while a window watches (the setup screen on show, a recovery card, Settings > Permissions) AND
 *            something is still off; it stops once both grants read granted (events still run).
 *   probe    the ground truth for "on, but only after a restart": a fresh miyagi-listen (main/permissionProbe.ts).
 *   cadence  main/permHealth.ts nextPollMs (#286): every 500 ms for 2 minutes after a step opened System Settings, then
 *            every 1.5 s; none while no window watches (hidden) or nothing is left to wait for.
 *
 * Hardening (#286, merged here):
 *   `place`     where miyagi runs from (permHealth installPlace): from the mounted .dmg or a translocated copy, grants
 *               don't stick, so the windows say "Move miyagi to Applications, then open it from there".
 *   `hint`      per kind, from permHealth judgePermission: 'move' (above), 'reset' (off now but on under an earlier
 *               build: System Settings likely shows it on for a copy macOS no longer recognises after an update),
 *               'managed' (restricted: a device profile decides).
 *   'restricted' is its own state: "Your organization manages this setting."
 *   permissions:reset(kind)   tccutil reset Accessibility|ScreenCapture dev.sandhacks.miyagi, only on the learner's
 *                             click (Reset miyagi in the list), then the pane opens so they can switch it on again.
 */
import { createHash } from 'node:crypto'
import { execFile } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { app, BrowserWindow, ipcMain, systemPreferences, type IpcMainInvokeEvent } from 'electron'
import type { PermissionKind } from '../../../shared/contracts/events'
import { appBundlePath, AX_NOTE_RECHECKS_MS, installPlace, judgePermission, nextPollMs, type InstallPlace, type PermKind } from './permHealth'
import { FIRST_PROBE_TIMEOUT_MS, probeFreshPerms, relaunchKinds, throttledProbe, type Fresh, type RelaunchKind } from './permissionProbe'
import { openSystemSettings } from './safeOpen'

export type PermissionState = 'granted' | 'denied' | 'not-determined' | 'restricted' | 'unknown'
/** What the windows say instead of "switch it on" for a kind (permHealth judgePermission). */
export type PermissionHint = 'move' | 'reset' | 'managed'
export type Permissions = Record<PermissionKind, PermissionState> & {
  external: boolean
  at: number
  relaunch?: RelaunchKind[]
  place?: InstallPlace
  hint?: Partial<Record<RelaunchKind, PermissionHint>>
}

const KINDS: PermissionKind[] = ['screen', 'accessibility', 'automation']
const GRANTS: PermKind[] = ['screen', 'accessibility']
/** tccutil's service names. */
const TCC_SERVICE: Record<PermKind, string> = { screen: 'ScreenCapture', accessibility: 'Accessibility' }
const BUNDLE_ID = 'dev.sandhacks.miyagi'
/** Accessibility is live in main: a restart is flagged for it only if main still disagrees with the fresh process this long. */
export const AX_RESTART_AFTER_MS = 2000

/** Where this miyagi runs from (packaged: the .app; a dev copy reads 'other'). Never throws. */
export function placeNow(): InstallPlace {
  try {
    return installPlace(appBundlePath(app.getPath('exe')))
  } catch {
    return 'other'
  }
}

/**
 * This build, as macOS's privacy database tells copies apart: the bundle's code signature seal (it changes with every
 * re-sign, which is when an earlier grant stops matching), else the version. Never throws.
 */
export function buildKey(): string {
  let version = 'dev'
  try {
    version = app.getVersion()
  } catch {
    /* tests */
  }
  try {
    const seal = join(appBundlePath(app.getPath('exe')), 'Contents', '_CodeSignature', 'CodeResources')
    if (existsSync(seal)) return `${version}+${createHash('sha1').update(readFileSync(seal)).digest('hex').slice(0, 12)}`
  } catch {
    /* no seal (dev): the version alone */
  }
  return version
}

export function setupPermissions(deps: {
  /** Is the engine one this app did NOT start (localEngine state 'external')? */
  engineExternal: () => boolean
  broadcast: (channel: string, payload: unknown) => void
  trusted: (e: IpcMainInvokeEvent) => boolean
  /** miyagi-listen's path (features/ptt.ts helperPath), for the fresh-process probe. Absent: no relaunch detection. */
  helperBin?: () => string
  /** Tests: replace the fresh-process probe. */
  probe?: () => Promise<Fresh | undefined>
  /** Per kind, the build that last read it as on and the build miyagi last restarted for it (default userData/perm-grants.json). */
  grantsFile?: string
  /** Tests: replace app.relaunch + quit. */
  relaunch?: () => void
  /** Tests: this build and where it runs from. */
  build?: string
  place?: InstallPlace
}): { read(): Permissions; readFull(): Promise<Permissions>; refresh(): Promise<Permissions>; relaunch(): boolean } {
  const place = deps.place ?? placeNow()
  const build = deps.build ?? buildKey()
  const grantsFile = ((): string | undefined => {
    if (deps.grantsFile) return deps.grantsFile
    try {
      return join(app.getPath('userData'), 'perm-grants.json')
    } catch {
      return undefined
    }
  })()
  /**
   * granted:   kind → the build that last read it as on (permHealth lastGrantedBuild).
   * restarted: kind → the build miyagi restarted on for it (the restart-loop guard).
   */
  type Memory = { granted: Partial<Record<PermKind, string>>; restarted: Partial<Record<PermKind, string>> }
  let mem: Memory = { granted: {}, restarted: {} }
  try {
    if (grantsFile && existsSync(grantsFile)) {
      const raw = JSON.parse(readFileSync(grantsFile, 'utf8')) as Partial<Memory>
      mem = { granted: raw.granted ?? {}, restarted: raw.restarted ?? {} }
    }
  } catch {
    mem = { granted: {}, restarted: {} }
  }
  const remember = (next: Memory): void => {
    if (JSON.stringify(next) === JSON.stringify(mem)) return
    mem = next
    try {
      if (!grantsFile) return
      mkdirSync(dirname(grantsFile), { recursive: true })
      writeFileSync(grantsFile, JSON.stringify(mem) + '\n')
    } catch {
      /* best effort */
    }
  }
  const noteGranted = (k: PermKind, here: boolean): void => {
    const restarted = { ...mem.restarted }
    // Seen as on by miyagi itself: the restart worked, the guard is done for this kind.
    if (here) delete restarted[k]
    remember({ granted: { ...mem.granted, [k]: build }, restarted })
  }

  const read = (): Permissions => {
    const external = deps.engineExternal()
    const base: Permissions = { screen: 'unknown', accessibility: 'unknown', automation: 'unknown', external, at: Date.now() }
    // Windows has no Screen Recording or Accessibility grant: any desktop app may capture the screen and use UI
    // Automation. Reporting them as on lets setup skip the two macOS steps (and their System Settings pictures) and
    // Settings > Permissions read "On" instead of "Not sure yet".
    if (process.platform === 'win32') return { ...base, screen: 'granted', accessibility: 'granted' }
    if (process.platform !== 'darwin' || external) return base
    try {
      const s = systemPreferences.getMediaAccessStatus('screen')
      // 'restricted': a device profile (MDM) decides; the learner can't change it (#286 P6).
      base.screen = s === 'granted' ? 'granted' : s === 'not-determined' ? 'not-determined' : s === 'denied' ? 'denied' : s === 'restricted' ? 'restricted' : 'unknown'
    } catch {
      base.screen = 'unknown'
    }
    base.accessibility = readAx()
    return base
  }
  /** false = do NOT prompt. Live: the answer follows the switch without a restart. */
  function readAx(): PermissionState {
    try {
      return systemPreferences.isTrustedAccessibilityClient(false) ? 'granted' : 'denied'
    } catch {
      return 'unknown'
    }
  }

  // The first probe of a run may wait for Gatekeeper's first scan of the helper (#286 P1).
  let firstProbe = true
  const fresh = throttledProbe(
    deps.probe ??
      (() => {
        if (!deps.helperBin) return Promise.resolve(undefined)
        const timeout = firstProbe ? FIRST_PROBE_TIMEOUT_MS : undefined
        firstProbe = false
        return probeFreshPerms(deps.helperBin(), timeout)
      })
  )
  /** Since when main's Accessibility has disagreed with a fresh process that reads it on (undefined: it doesn't). */
  let axSince: number | undefined
  /**
   * read() plus `relaunch` (a fresh process sees a grant this one doesn't), `place` and `hint`. The probe runs only
   * while something reads off here, a window watches, and not every off kind is already known to need a restart.
   */
  const readFull = async (): Promise<Permissions> => {
    const p = read()
    if (process.platform !== 'darwin' || p.external) return p
    const out: Permissions = { ...p, place }
    const off = GRANTS.filter((k) => p[k] !== 'granted')
    let f: Fresh | undefined
    if (!off.length) {
      fresh.reset()
      axSince = undefined
    } else {
      const known = fresh.peek()
      const settled = !!known && off.every((k) => known[k] === 'granted')
      f = watchers.size > 0 && !settled ? await fresh.get().catch(() => undefined) : known
    }
    // Accessibility: main's read may have lagged the switch by a moment. Read again after the probe; a restart is only
    // flagged when main still disagrees AX_RESTART_AFTER_MS after it first did.
    if (f?.accessibility === 'granted' && out.accessibility === 'denied') {
      out.accessibility = readAx()
      if (out.accessibility === 'granted') axSince = undefined
      else axSince ??= Date.now()
    } else axSince = undefined
    let kinds = relaunchKinds(out, f)
    if (axSince === undefined || Date.now() - axSince < AX_RESTART_AFTER_MS) kinds = kinds.filter((k) => k !== 'accessibility')
    const hint: Partial<Record<RelaunchKind, PermissionHint>> = {}
    // The restart-loop guard: miyagi already restarted for this kind on this build and still can't see it.
    for (const k of kinds) if (mem.restarted[k] === build) hint[k] = 'reset'
    kinds = kinds.filter((k) => !hint[k])
    if (kinds.length) out.relaunch = kinds
    for (const k of GRANTS) {
      const here = out[k]
      if (here === 'granted' || f?.[k] === 'granted') noteGranted(k, here === 'granted')
      if (hint[k]) continue
      const v = judgePermission(k, { main: here, probe: f?.[k], place, build, lastGrantedBuild: mem.granted[k] })
      if (v.action === 'move-to-applications') hint[k] = 'move'
      else if (v.action === 'reset-entry') hint[k] = 'reset'
      else if (v.action === 'managed') hint[k] = 'managed'
    }
    if (Object.keys(hint).length) out.hint = hint
    return out
  }

  let last = ''
  let timer: ReturnType<typeof setTimeout> | undefined
  /** webContents ids that asked for live updates. */
  const watchers = new Set<number>()
  /** webContents ids whose destroyed / closed listeners are in place. */
  const seen = new Set<number>()

  /** When a step last opened System Settings (permissions:open): the fast poll lasts FAST_WINDOW_MS after it. */
  let openedAt: number | undefined
  /** Kinds still worth waiting for: off here, not waiting on a restart, not managed, not unknown. */
  let pending: PermKind[] = []
  /** The last full read, and a broadcast to every window when it changed (any read, any trigger). */
  let lastPerms: Permissions | undefined
  const publish = (p: Permissions): Permissions => {
    lastPerms = p
    const key = JSON.stringify([KINDS.map((k) => p[k]), p.external, p.relaunch ?? [], p.place ?? '', p.hint ?? {}])
    if (key !== last) {
      last = key
      deps.broadcast('permissions', p)
    }
    pending = GRANTS.filter((k) => p[k] !== 'granted' && p[k] !== 'unknown' && p[k] !== 'restricted' && !p.relaunch?.includes(k))
    schedule()
    return p
  }
  let ticking: Promise<Permissions> | undefined
  const tick = (): Promise<Permissions> => (ticking ??= readFull().then(publish).finally(() => (ticking = undefined)))
  /** The next poll (permHealth nextPollMs): fast after a pane opened, slower otherwise, none when hidden or done. */
  const schedule = (): void => {
    clearTimeout(timer)
    timer = undefined
    const ms = nextPollMs({ visible: watchers.size > 0, pending, sinceOpenMs: openedAt === undefined ? null : Date.now() - openedAt, focused: false })
    if (ms === null) return
    timer = setTimeout(() => void tick(), ms)
    timer.unref?.()
  }
  const sync = schedule

  // Back from System Settings: read now, not on the next poll. Cheap (two in-process reads; the probe is rate-limited
  // and runs only while something is off). Never prompts.
  const now = (): void => void tick()
  app.on('did-become-active', now)
  app.on('browser-window-focus', now)
  // An Accessibility switch flipped anywhere: macOS posts this distributed notification (no polling needed for it). It
  // can land a moment before the change is committed: read at each AX_NOTE_RECHECKS_MS offset. Unsubscribed on quit.
  try {
    if (process.platform === 'darwin' && typeof systemPreferences.subscribeNotification === 'function') {
      const id = systemPreferences.subscribeNotification('com.apple.accessibility.api', () => {
        for (const ms of AX_NOTE_RECHECKS_MS) setTimeout(now, ms).unref?.()
      })
      app.on('will-quit', () => {
        try {
          systemPreferences.unsubscribeNotification(id)
        } catch {
          /* quitting anyway */
        }
      })
    }
  } catch {
    /* no notification: the poll and the front events still catch it */
  }

  /**
   * Restart miyagi for the grants only a restart applies: note them for this build first (the restart-loop guard), then
   * relaunch. A dev copy (npm run dev) can't relaunch itself: false, and it says so in its log.
   */
  const relaunch = (): boolean => {
    const kinds = lastPerms?.relaunch ?? []
    if (kinds.length) remember({ ...mem, restarted: { ...mem.restarted, ...Object.fromEntries(kinds.map((k) => [k, build])) } })
    if (deps.relaunch) {
      deps.relaunch()
      return true
    }
    if (!app.isPackaged) {
      console.log('[permissions] restart asked in a dev copy: restart npm run dev')
      return false
    }
    app.relaunch()
    app.quit()
    return true
  }

  // A read asked for by one window is published to all (a grant seen anywhere clears every banner).
  ipcMain.handle('feat:permissions:get', (e) => (deps.trusted(e) ? tick() : undefined))
  ipcMain.handle('feat:permissions:relaunch', (e) => (deps.trusted(e) ? relaunch() : false))
  ipcMain.handle('feat:permissions:open', (e, kind: unknown) => {
    if (!deps.trusted(e) || !KINDS.includes(kind as PermissionKind)) return false
    // The learner is on their way to the switch: poll fast for a while (#286 P2).
    openedAt = Date.now()
    schedule()
    return openSystemSettings(kind)
  })
  // Reset miyagi's row in the list (#286 P5): only from the learner's click on that button, never from a poll. A row
  // macOS remembers for an earlier build shows "on" but no longer matches; after the reset they switch it on again.
  ipcMain.handle('feat:permissions:reset', async (e, kind: unknown) => {
    if (!deps.trusted(e) || process.platform !== 'darwin' || (kind !== 'screen' && kind !== 'accessibility')) return false
    const ok = await new Promise<boolean>((resolve) => {
      try {
        execFile('/usr/bin/tccutil', ['reset', TCC_SERVICE[kind], BUNDLE_ID], { timeout: 5000 }, (err) => resolve(!err))
      } catch {
        resolve(false)
      }
    })
    openedAt = Date.now()
    void tick()
    return ok
  })
  ipcMain.handle('feat:permissions:watch', (e, on: unknown) => {
    if (!deps.trusted(e)) return false
    const id = e.sender.id
    if (on === true) {
      if (!watchers.has(id)) {
        const first = !seen.has(id)
        watchers.add(id)
        seen.add(id)
        // A window that goes away stops watching.
        // Registered once per webContents (a window toggles watching on every show and hide).
        if (first) {
          const win = BrowserWindow.fromWebContents(e.sender)
          const gone = (): void => {
            watchers.delete(id)
            seen.delete(id)
            sync()
          }
          e.sender.once('destroyed', gone)
          win?.once('closed', gone)
        }
      }
    } else watchers.delete(id)
    sync()
    if (on === true) void tick()
    return true
  })

  return { read, readFull, refresh: tick, relaunch }
}
