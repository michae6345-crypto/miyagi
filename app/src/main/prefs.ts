/**
 * Core: the learner's general preferences (Settings → General). Not secret, so a plain JSON file in userData.
 * Keys are NOT here: they live encrypted in the settings feature (safeStorage).
 *
 *   bridge.invoke('prefs:get')            → Prefs
 *   bridge.invoke('prefs:set', patch)     → Prefs (merged, saved, broadcast to every window as feat:prefs)
 *
 * Side effects in main: appearance → nativeTheme.themeSource (so vibrancy and prefers-color-scheme follow),
 * launchAtLogin → app.setLoginItemSettings.
 *
 * v2 (W0-5): panelCollapsed, onboarded, crashReports ('ask' by default), usageCounts (off), shortcuts. They are only
 * stored here (no side effect yet): `shortcuts` is validated as Electron accelerators and kept for wave 2's live
 * rebinding; a patch's `shortcuts` replaces the whole map, so send all of it.
 */
import { app, ipcMain, nativeTheme, type BrowserWindow, type IpcMainInvokeEvent } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { DEFAULT_PREFS, sanitizePrefs, type Prefs } from '../common/prefs'
import { rawBg } from '../renderer/src/core/theme'

/** The opaque window color for the theme in effect (nativeTheme follows Settings > Appearance and the OS). */
export const windowBackground = (): string => (nativeTheme.shouldUseDarkColors ? rawBg.dark : rawBg.light)

/**
 * An opaque app window repaints its own background when the theme changes (so a resize or an overscroll never flashes the
 * old color), and tells its page when it enters or leaves macOS full screen (html[data-fullscreen], core/prefs.ts).
 */
export function trackWindowBackground(win: BrowserWindow): void {
  const paint = (): void => {
    if (!win.isDestroyed()) win.setBackgroundColor(windowBackground())
  }
  nativeTheme.on('updated', paint)
  win.on('closed', () => nativeTheme.off('updated', paint))
  const fs = (on: boolean) => (): void => {
    if (!win.isDestroyed()) win.webContents.send('feat:fullscreen', on)
  }
  win.on('enter-full-screen', fs(true))
  win.on('leave-full-screen', fs(false))
}

/** `trusted`: main's sender check (index.ts trustedSender); an untrusted sender reads nothing and changes nothing. */
export function setupPrefs(broadcast: (channel: string, payload: unknown) => void, trusted: (e: IpcMainInvokeEvent) => boolean): void {
  const file = join(app.getPath('userData'), 'prefs.json')
  let prefs: Prefs = DEFAULT_PREFS
  try {
    prefs = { ...DEFAULT_PREFS, ...sanitizePrefs(JSON.parse(readFileSync(file, 'utf8'))) }
  } catch {
    /* first run or unreadable: defaults */
  }

  const apply = (): void => {
    nativeTheme.themeSource = prefs.appearance
    try {
      app.setLoginItemSettings({ openAtLogin: prefs.launchAtLogin })
    } catch (err) {
      console.warn('[prefs] launch at login not available here', err)
    }
  }
  apply()

  ipcMain.handle('feat:prefs:get', (e) => (trusted(e) ? prefs : undefined))
  ipcMain.handle('feat:prefs:set', (e, patch: unknown) => {
    if (!trusted(e)) return undefined
    prefs = { ...prefs, ...sanitizePrefs(patch) }
    try {
      writeFileSync(file, JSON.stringify(prefs, null, 2))
    } catch (err) {
      console.warn('[prefs] could not save', err)
    }
    apply()
    broadcast('prefs', prefs)
    return prefs
  })
}
