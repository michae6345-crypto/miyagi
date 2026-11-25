/**
 * Core: the learner's general preferences (Settings → General). Not secret, so a plain JSON file in userData.
 * Keys are NOT here: they live encrypted in the settings feature (safeStorage).
 *
 *   bridge.invoke('prefs:get')            → Prefs
 *   bridge.invoke('prefs:set', patch)     → Prefs (merged, saved, broadcast to every window as feat:prefs)
 *   patchPrefs(patch)                     main's own change, the same way (the consent record: features/onboarding.ts)
 *
 * `consent` (common/consent.ts) is main's alone: prefs:set from a window drops it (fromRenderer).
 *
 * Side effects in main: appearance → nativeTheme.themeSource (so vibrancy and prefers-color-scheme follow),
 * launchAtLogin → app.setLoginItemSettings.
 *
 * v2 (W0-5): panelCollapsed, onboarded, crashReports ('ask' by default), usageCounts (off): stored only.
 * `shortcuts` is live: validated as Electron accelerators (common/prefs isAccelerator), then checked by main
 * (setShortcutCheck → main/shortcutKeys.ts accept), which registers the new keys and drops any override another
 * shortcut or another app already owns, so the saved map is what works. A patch's `shortcuts` replaces the whole map,
 * so send all of it; the prefs:set result shows which overrides were kept.
 */
import { app, ipcMain, nativeTheme, type BrowserWindow, type IpcMainInvokeEvent } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { DEFAULT_PREFS, sanitizePrefs, type Prefs, type ShortcutPrefs } from '../common/prefs'
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

let current: Prefs = DEFAULT_PREFS
const listeners = new Set<(p: Prefs) => void>()
/** The prefs in effect now (defaults before setupPrefs runs). */
export const getPrefs = (): Prefs => current
/** Called after every change (and once after the file loads). Returns the unsubscribe. */
export function onPrefsChange(fn: (p: Prefs) => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/**
 * What a renderer's prefs:set may change: every known pref except `consent`. The consent record (common/consent.ts) is
 * written only by main (features/onboarding.ts onboarding:agree, through patchPrefs), with main's clock and this
 * build's version, so no window can claim an agreement the learner never gave.
 */
export function fromRenderer(patch: unknown): Partial<Prefs> {
  const { consent: _mainOnly, ...rest } = sanitizePrefs(patch)
  return rest
}

/**
 * Main's say on a new shortcuts map before it is saved (main/index.ts hands in main/shortcutKeys.ts accept): returns the
 * map to keep (a refused override goes back to what it was). Unset: kept as sent.
 */
let shortcutCheck: ((next: ShortcutPrefs, prev: ShortcutPrefs) => ShortcutPrefs) | undefined
export function setShortcutCheck(fn: ((next: ShortcutPrefs, prev: ShortcutPrefs) => ShortcutPrefs) | undefined): void {
  shortcutCheck = fn
}
const checked = (clean: Partial<Prefs>, prev: Prefs): Partial<Prefs> =>
  clean.shortcuts && shortcutCheck ? { ...clean, shortcuts: shortcutCheck(clean.shortcuts, prev.shortcuts) } : clean

/** setupPrefs's writer (merge, save, apply, broadcast, listeners). Unset before setupPrefs runs (tests). */
let write: ((clean: Partial<Prefs>) => Prefs) | undefined

/**
 * Main's own change to the prefs (anything sanitizePrefs keeps, consent included), saved and broadcast like a
 * prefs:set. Before setupPrefs has run (offline tests) it changes the in-memory prefs and tells the listeners.
 */
export function patchPrefs(patch: Partial<Prefs>): Prefs {
  const clean = sanitizePrefs(patch)
  if (write) return write(clean)
  current = { ...current, ...checked(clean, current) }
  listeners.forEach((fn) => fn(current))
  return current
}

/** Tests only: back to the defaults, no listeners, no writer. */
export function resetPrefsForTests(): void {
  current = DEFAULT_PREFS
  listeners.clear()
  write = undefined
  shortcutCheck = undefined
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
  current = prefs
  apply()

  write = (clean: Partial<Prefs>): Prefs => {
    prefs = { ...prefs, ...checked(clean, prefs) }
    try {
      writeFileSync(file, JSON.stringify(prefs, null, 2))
    } catch (err) {
      console.warn('[prefs] could not save', err)
    }
    current = prefs
    apply()
    broadcast('prefs', prefs)
    listeners.forEach((fn) => fn(prefs))
    return prefs
  }

  ipcMain.handle('feat:prefs:get', (e) => (trusted(e) ? prefs : undefined))
  // A renderer never writes the consent record (fromRenderer drops it); main does, through patchPrefs.
  ipcMain.handle('feat:prefs:set', (e, patch: unknown) => (trusted(e) && write ? write(fromRenderer(patch)) : undefined))
}
