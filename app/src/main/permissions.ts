/**
 * Core (v2, W0-5): the macOS permissions miyagi needs, read WITHOUT prompting (Section 6: polling never prompts).
 *
 *   bridge.invoke('permissions:get')           → Permissions (now)
 *   bridge.invoke('permissions:open', kind)    open that System Settings pane (fixed URL, main/safeOpen.ts) → boolean
 *   bridge.invoke('permissions:watch', on)     this window wants live updates (onboarding / settings focused, a
 *                                              recovery card open); main polls every POLL_MS only while someone
 *                                              watches, and broadcasts feat:permissions when anything changes
 *
 * States: granted · denied · not-determined · unknown. `unknown` when we can't tell honestly:
 *   - the engine is EXTERNAL (started in Terminal): macOS grants belong to that Terminal, not to this app;
 *   - automation (Apple Events to VS Code): no API reads it without prompting;
 *   - not macOS (Windows reads screen and accessibility as granted: it has no such grants).
 * Prompting is never done here. A click handler that wants the prompt asks for it on purpose (onboarding, A3).
 *
 * `relaunch` (Nov 25, a learner on a MacBook Neo had to press Skip): the kinds switched on in System Settings that this
 * process can't see until miyagi restarts (macOS caches Screen Recording per process). A fresh miyagi-listen --screens
 * tells (main/permissionProbe.ts); only asked while something is off and a window watches, at most every 2 s. The
 * windows offer "Restart miyagi" for them (onboarding:relaunch).
 *
 * One source, live and cheap (Nov 25): every window's banners, badges and rows read this (feat:permissions, broadcast to
 * ALL windows on any change, whoever caused the read), so a grant clears everywhere at once.
 *   events   miyagi comes back to the front (did-become-active, browser-window-focus) and macOS's
 *            com.apple.accessibility.api distributed notification (an Accessibility switch flipped): read now, always.
 *   poll     every POLL_MS, only while a window watches (the setup screen on show, a recovery card, Settings >
 *            Permissions) AND something is still off; it stops once both grants read granted (events still run).
 *   probe    the ground truth for "on, but only after a restart": a fresh miyagi-listen (main/permissionProbe.ts).
 */
import { app, BrowserWindow, ipcMain, systemPreferences, type IpcMainInvokeEvent } from 'electron'
import type { PermissionKind } from '../../../shared/contracts/events'
import { probeFreshPerms, relaunchKinds, throttledProbe, type Fresh, type RelaunchKind } from './permissionProbe'
import { openSystemSettings } from './safeOpen'

export type PermissionState = 'granted' | 'denied' | 'not-determined' | 'unknown'
export type Permissions = Record<PermissionKind, PermissionState> & { external: boolean; at: number; relaunch?: RelaunchKind[] }

const POLL_MS = 1000
/** After the Accessibility notification, macOS can take a moment to answer the new value: read then, and once more. */
const AX_SETTLE_MS = [250, 1200] as const
const KINDS: PermissionKind[] = ['screen', 'accessibility', 'automation']

export function setupPermissions(deps: {
  /** Is the engine one this app did NOT start (localEngine state 'external')? */
  engineExternal: () => boolean
  broadcast: (channel: string, payload: unknown) => void
  trusted: (e: IpcMainInvokeEvent) => boolean
  /** miyagi-listen's path (features/ptt.ts helperPath), for the fresh-process probe. Absent: no relaunch detection. */
  helperBin?: () => string
  /** Tests: replace the fresh-process probe. */
  probe?: () => Promise<Fresh | undefined>
}): { read(): Permissions; readFull(): Promise<Permissions>; refresh(): Promise<Permissions> } {
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
      base.screen = s === 'granted' ? 'granted' : s === 'not-determined' ? 'not-determined' : s === 'denied' || s === 'restricted' ? 'denied' : 'unknown'
    } catch {
      base.screen = 'unknown'
    }
    try {
      // false = do NOT prompt.
      base.accessibility = systemPreferences.isTrustedAccessibilityClient(false) ? 'granted' : 'denied'
    } catch {
      base.accessibility = 'unknown'
    }
    return base
  }

  const fresh = throttledProbe(deps.probe ?? (() => (deps.helperBin ? probeFreshPerms(deps.helperBin()) : Promise.resolve(undefined))))
  /** read() plus `relaunch`: asks a fresh process only while Screen Recording or Accessibility reads as off here. */
  const readFull = async (): Promise<Permissions> => {
    const p = read()
    if (process.platform !== 'darwin' || p.external) return p
    if (p.screen === 'granted' && p.accessibility === 'granted') {
      fresh.reset()
      return p
    }
    const kinds = relaunchKinds(p, await fresh.get().catch(() => undefined))
    return kinds.length ? { ...p, relaunch: kinds } : p
  }

  let last = ''
  let timer: ReturnType<typeof setInterval> | undefined
  /** webContents ids that asked for live updates. */
  const watchers = new Set<number>()
  /** webContents ids whose destroyed / closed listeners are in place. */
  const seen = new Set<number>()

  /** The last full read, and a broadcast to every window when it changed (any read, any trigger). */
  const publish = (p: Permissions): Permissions => {
    const key = KINDS.map((k) => p[k]).join(',') + p.external + (p.relaunch ?? []).join('+')
    if (key !== last) {
      last = key
      deps.broadcast('permissions', p)
    }
    // Both on: nothing left to poll for (events still read). Something off again: poll again while watched.
    settled = p.screen === 'granted' && p.accessibility === 'granted' && !p.relaunch
    sync()
    return p
  }
  let settled = false
  let ticking: Promise<Permissions> | undefined
  const tick = (): Promise<Permissions> => (ticking ??= readFull().then(publish).finally(() => (ticking = undefined)))
  const sync = (): void => {
    const want = watchers.size > 0 && !settled
    if (want && !timer) {
      timer = setInterval(() => void tick(), POLL_MS)
      timer.unref?.()
    } else if (!want && timer) {
      clearInterval(timer)
      timer = undefined
    }
  }

  // Back from System Settings: read now, not on the next poll. Cheap (two in-process reads; the probe is rate-limited
  // and runs only while something is off). Never prompts.
  const now = (): void => void tick()
  app.on('did-become-active', now)
  app.on('browser-window-focus', now)
  // An Accessibility switch flipped anywhere: macOS posts this distributed notification (no polling needed for it).
  try {
    if (process.platform === 'darwin' && typeof systemPreferences.subscribeNotification === 'function')
      systemPreferences.subscribeNotification('com.apple.accessibility.api', () => {
        for (const ms of AX_SETTLE_MS) setTimeout(now, ms).unref?.()
      })
  } catch {
    /* no notification: the poll and the front events still catch it */
  }

  // A read asked for by one window is published to all (a grant seen anywhere clears every banner).
  ipcMain.handle('feat:permissions:get', (e) => (deps.trusted(e) ? tick() : undefined))
  ipcMain.handle('feat:permissions:open', (e, kind: unknown) => (deps.trusted(e) && KINDS.includes(kind as PermissionKind) ? openSystemSettings(kind) : false))
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

  return { read, readFull, refresh: tick }
}
