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
 */
import { BrowserWindow, ipcMain, systemPreferences, type IpcMainInvokeEvent } from 'electron'
import type { PermissionKind } from '../../../shared/contracts/events'
import { openSystemSettings } from './safeOpen'

export type PermissionState = 'granted' | 'denied' | 'not-determined' | 'unknown'
export type Permissions = Record<PermissionKind, PermissionState> & { external: boolean; at: number }

const POLL_MS = 2000
const KINDS: PermissionKind[] = ['screen', 'accessibility', 'automation']

export function setupPermissions(deps: {
  /** Is the engine one this app did NOT start (localEngine state 'external')? */
  engineExternal: () => boolean
  broadcast: (channel: string, payload: unknown) => void
  trusted: (e: IpcMainInvokeEvent) => boolean
}): { read(): Permissions } {
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

  let last = ''
  let timer: ReturnType<typeof setInterval> | undefined
  /** webContents ids that asked for live updates. */
  const watchers = new Set<number>()

  const tick = (): void => {
    const p = read()
    const key = KINDS.map((k) => p[k]).join(',') + p.external
    if (key === last) return
    last = key
    deps.broadcast('permissions', p)
  }
  const sync = (): void => {
    if (watchers.size && !timer) {
      tick()
      timer = setInterval(tick, POLL_MS)
    } else if (!watchers.size && timer) {
      clearInterval(timer)
      timer = undefined
    }
  }

  ipcMain.handle('feat:permissions:get', (e) => (deps.trusted(e) ? read() : undefined))
  ipcMain.handle('feat:permissions:open', (e, kind: unknown) => (deps.trusted(e) && KINDS.includes(kind as PermissionKind) ? openSystemSettings(kind) : false))
  ipcMain.handle('feat:permissions:watch', (e, on: unknown) => {
    if (!deps.trusted(e)) return false
    const id = e.sender.id
    if (on === true) {
      if (!watchers.has(id)) {
        watchers.add(id)
        // A window that goes away stops watching.
        const win = BrowserWindow.fromWebContents(e.sender)
        e.sender.once('destroyed', () => {
          watchers.delete(id)
          sync()
        })
        win?.once('closed', () => {
          watchers.delete(id)
          sync()
        })
      }
    } else watchers.delete(id)
    sync()
    return true
  })

  return { read }
}
