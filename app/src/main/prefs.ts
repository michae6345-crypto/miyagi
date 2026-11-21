/**
 * Core: the learner's general preferences (Settings → General). Not secret, so a plain JSON file in userData.
 * Keys are NOT here: they live encrypted in the settings feature (safeStorage).
 *
 *   bridge.invoke('prefs:get')            → Prefs
 *   bridge.invoke('prefs:set', patch)     → Prefs (merged, saved, broadcast to every window as feat:prefs)
 *
 * Side effects in main: appearance → nativeTheme.themeSource (so vibrancy and prefers-color-scheme follow),
 * launchAtLogin → app.setLoginItemSettings.
 */
import { app, ipcMain, nativeTheme } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { DEFAULT_PREFS, sanitizePrefs, type Prefs } from '../common/prefs'

export function setupPrefs(broadcast: (channel: string, payload: unknown) => void): void {
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

  ipcMain.handle('feat:prefs:get', () => prefs)
  ipcMain.handle('feat:prefs:set', (_e, patch: unknown) => {
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
