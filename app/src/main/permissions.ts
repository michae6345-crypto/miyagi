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
 * tells (main/permissionProbe.ts); only asked while something is off and a window watches, at most every 3 s. The
 * windows offer "Restart miyagi" for them (onboarding:relaunch).
 *
 * Live while watched: main polls every POLL_MS while any window watches (a window keeps watching while it is on screen,
 * also while the learner is over in System Settings), and reads again at once when miyagi comes back to the front.
 */
import { app, BrowserWindow, ipcMain, systemPreferences, type IpcMainInvokeEvent } from 'electron'
import type { PermissionKind } from '../../../shared/contracts/events'
import { probeFreshPerms, relaunchKinds, throttledProbe, type Fresh, type RelaunchKind } from './permissionProbe'
import { openSystemSettings } from './safeOpen'

export type PermissionState = 'granted' | 'denied' | 'not-determined' | 'unknown'
export type Permissions = Record<PermissionKind, PermissionState> & { external: boolean; at: number; relaunch?: RelaunchKind[] }

const POLL_MS = 2000
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
}): { read(): Permissions; readFull(): Promise<Permissions> } {
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

  let ticking = false
  const tick = async (): Promise<void> => {
    if (ticking) return
    ticking = true
    try {
      const p = await readFull()
      const key = KINDS.map((k) => p[k]).join(',') + p.external + (p.relaunch ?? []).join('+')
      if (key === last) return
      last = key
      deps.broadcast('permissions', p)
    } finally {
      ticking = false
    }
  }
  const sync = (): void => {
    if (watchers.size && !timer) {
      void tick()
      timer = setInterval(() => void tick(), POLL_MS)
    } else if (!watchers.size && timer) {
      clearInterval(timer)
      timer = undefined
    }
  }

  // Back from System Settings: read now, not on the next poll (only while a window watches; never prompts).
  const onFront = (): void => {
    if (watchers.size) void tick()
  }
  app.on('browser-window-focus', onFront)
  app.on('did-become-active', onFront)

  ipcMain.handle('feat:permissions:get', (e) => (deps.trusted(e) ? readFull() : undefined))
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
    return true
  })

  return { read, readFull }
}
