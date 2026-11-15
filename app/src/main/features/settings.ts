/**
 * Main-process side of Settings (renderer: src/renderer/src/features/settings/). Bring-your-own keys.
 *
 *   - Keys live HERE only: userData/keys.bin = safeStorage.encryptString(JSON.stringify(keys)) (Keychain on
 *     the Mac, DPAPI on Windows). No secure storage → memory for this run only, and the sheet says so.
 *     Never plain text, never logged (not even an error message: JSON.parse errors quote their input).
 *   - The renderer never gets a key back: settings:get / settings:save return {set, last4} per key.
 *   - config.keys always carries ALL names (the engine's set_app_keys drops any that are missing), on every
 *     (re)connect (engine.onOpen) and on Save / Test.
 *   - One focusable window, route `settings`, covering the overlay's display like the launcher, so its sheet
 *     can grow out of the island's exact rect and collapse back into it. Hidden until opened; hidden windows
 *     never take focus.
 *   - First run: opens once if Anthropic or Gemini is `missing` (not `env`) in config.status.
 *
 * Handles (bridge.invoke from any window):
 *   settings:open     grow the sheet out of the island (the overview's gear; openSettings() in the renderer)
 *   settings:get      → KeysView
 *   settings:save     (SavePatch) merge, encrypt, write, send config.keys → KeysView
 *   settings:test     re-send config.keys (the engine answers config.status)
 *   settings:island   → the island's current size (the sheet collapses onto it)
 *   settings:hidden   the sheet finished collapsing: hide the window, hand focus back
 * Broadcasts: settings:open {from}, settings:close (blur).
 *
 * UNVERIFIED: written and typechecked on Windows, where Smart App Control blocks electron.exe.
 * Check on the Mac: Keychain prompt (if any), keys.bin survives a restart, focus on open, blur closes,
 * focus returns to the editor after closing.
 */
import { safeStorage, screen, type BrowserWindow } from 'electron'
import { existsSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { cmd } from '../../common/wire'
import { defineMainFeature } from '../context'
import { returnFocus } from '../platform'
import { cleanKeys, fullPayload, mergeKeys, needsKeys, viewOf, type Keys, type KeyStatus, type KeysView } from '../../renderer/src/features/settings/keys'

/** Linux can fall back to a hard-coded password ("basic_text"): that's not secure storage. */
function secureStorage(): boolean {
  if (!safeStorage.isEncryptionAvailable()) return false
  if (process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text') return false
  return true
}

export default defineMainFeature({
  id: 'settings',
  setup(ctx) {
    const file = join(ctx.app.getPath('userData'), 'keys.bin')
    const secure = secureStorage()
    let keys: Keys = {}
    let lastStatus: KeyStatus | undefined
    let error: string | undefined

    if (secure && existsSync(file)) {
      try {
        keys = cleanKeys(JSON.parse(safeStorage.decryptString(readFileSync(file))))
      } catch {
        console.warn('[settings] keys.bin could not be read; starting with no keys') // never log the error itself
      }
    }

    const persist = (): void => {
      error = undefined
      if (!secure) return
      try {
        if (!Object.keys(keys).length) {
          if (existsSync(file)) unlinkSync(file)
          return
        }
        // Write-then-rename, so a crash mid-write never leaves a half file.
        const tmp = `${file}.tmp`
        writeFileSync(tmp, safeStorage.encryptString(JSON.stringify(keys)), { mode: 0o600 })
        renameSync(tmp, file)
      } catch {
        error = 'Couldn’t save. Kept for this run.'
        console.warn('[settings] could not write keys.bin')
      }
    }

    const view = (): KeysView => ({ keys: viewOf(keys), secure, status: lastStatus, error })
    /** Every name, every time. While offline the engine link drops it; onOpen re-sends. */
    const sendKeys = (): void => ctx.engine.send(cmd('config.keys', fullPayload(keys)))

    // ---- the window ---------------------------------------------------------------------------

    const win: BrowserWindow = ctx.createWindow('settings', { ...ctx.overlayOptions(ctx.overlay.getBounds()), focusable: true })
    ctx.raise(win)
    win.setBounds(ctx.overlay.getBounds()) // after raising, so macOS lets it cover the menu bar (as core does)
    // While open it covers the display: the engine's screen reader should ignore it.
    ctx.reportBounds(win)

    let open = false

    const show = (): void => {
      if (win.isDestroyed()) return
      if (open) {
        win.focus()
        return
      }
      open = true
      win.show()
      win.focus()
      ctx.raise(win)
      // The renderer starts the sheet on this exact shape, then yields the island once it has painted.
      ctx.broadcast('settings:open', { from: ctx.islandSize() })
    }

    const hide = (): void => {
      if (!open || win.isDestroyed()) return
      open = false
      win.hide()
      ctx.yieldIsland(false) // in case the renderer's island:return didn't make it (reload mid-close)
      returnFocus(ctx.app, ctx.overlay)
    }

    // Clicking elsewhere: collapse back into the island (the renderer animates, then calls settings:hidden).
    win.on('blur', () => open && ctx.broadcast('settings:close'))
    // A renderer that (re)loads starts closed: don't leave an invisible full-screen window holding the mouse.
    win.webContents.on('did-finish-load', () => hide())

    screen.on('display-metrics-changed', () => {
      // After core has moved the overlay (its listener was registered first).
      setTimeout(() => !win.isDestroyed() && win.setBounds(ctx.overlay.getBounds()))
    })

    // ---- the engine ---------------------------------------------------------------------------

    ctx.engine.onOpen(sendKeys)

    let autoOpened = false
    ctx.engine.onEvent((e) => {
      if (e.type !== 'config.status') return
      lastStatus = e.payload
      if (!autoOpened && needsKeys(e.payload)) {
        autoOpened = true
        // The window may still be loading on the very first connect.
        if (win.webContents.isLoading()) win.webContents.once('did-finish-load', () => setTimeout(show, 200))
        else show()
      }
    })

    // ---- IPC ----------------------------------------------------------------------------------

    ctx.handle('settings:open', () => show())
    ctx.handle('settings:get', () => view())
    ctx.handle('settings:save', (patch) => {
      keys = mergeKeys(keys, patch)
      persist()
      sendKeys()
      return view()
    })
    ctx.handle('settings:test', () => sendKeys())
    ctx.handle('settings:island', () => ctx.islandSize())
    ctx.handle('settings:hidden', () => hide())
  }
})
