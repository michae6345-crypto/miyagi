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
 *   - Never opens by itself: the learner opens it (gear, launcher, ⌘,).
 *
 * Handles (bridge.invoke from any window):
 *   settings:open     ({section}?) grow the sheet out of the island on that section (openSettings(section) in the
 *                     renderer, core/surfaces); already open: switch to the section
 *   settings:about    → {version} for the sidebar's foot
 *   settings:delete   Privacy › Delete my data: erase the keys on this Mac (keys.bin), send the empty config.keys,
 *                     then the sign-in files (settings/erase.ts SIGN_IN_FILES: auth.bin, login.json, cloud-link.json)
 *                     → {ok, keys: KeysView, signIn}. ok false: nothing was removed. signIn false: the keys went but
 *                     a sign-in file stayed. The renderer then resets the prefs and calls auth:sign-out (auth.ts
 *                     owns the session in memory and revokes it).
 *   settings:get      → KeysView
 *   settings:save     (SavePatch) merge, encrypt, write, send config.keys → KeysView
 *   settings:test     re-send config.keys (the engine answers config.status)
 *   settings:island   → the island's current size (the sheet collapses onto it)
 *   settings:hidden   the sheet finished collapsing: hide the window, hand focus back
 * Broadcasts: settings:open {from, section}, settings:section {section}, settings:close (blur).
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
import { focusPanel, returnFocus } from '../platform'
import { previousApp } from './front-app'
import { removeFiles, SIGN_IN_FILES } from './settings/erase'

/** How long the closed sheet's window keeps catching clicks (see hide()). */
const CATCH_MS = 400
import {
  cleanKeys,
  fullPayload,
  isSection,
  mergeKeys,
  viewOf,
  type AboutView,
  type DeleteResult,
  type Keys,
  type KeyStatus,
  type KeysView,
  type Section
} from '../../renderer/src/features/settings/keys'

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

    let hideTimer: ReturnType<typeof setTimeout> | undefined
    const show = (section?: Section): void => {
      if (win.isDestroyed()) return
      if (open) {
        if (section) ctx.broadcast('settings:section', { section })
        win.focus()
        return
      }
      clearTimeout(hideTimer)
      open = true
      // Key without activating miyagi (platform.ts focusPanel): showInactive, then focus.
      focusPanel(win)
      ctx.raise(win)
      // The renderer starts the sheet on this exact shape, then yields the island once it has painted.
      ctx.broadcast('settings:open', { from: ctx.islandSize(), section })
    }

    // The sheet has already collapsed when this runs. The (transparent, full-screen) window stays up CATCH_MS longer, so
    // a click aimed at the sheet's ✕ lands here instead of falling through the overlay to the wallpaper (Michael's
    // test 11: macOS "click wallpaper to reveal desktop" took the whole screen away).
    const hide = (): void => {
      if (!open || win.isDestroyed()) return
      open = false
      ctx.yieldIsland(false) // in case the renderer's island:return didn't make it (reload mid-close)
      clearTimeout(hideTimer)
      hideTimer = setTimeout(() => {
        if (open || win.isDestroyed()) return
        win.hide()
        returnFocus(ctx.app, ctx.overlay, previousApp())
      }, CATCH_MS)
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

    ctx.engine.onEvent((e) => {
      if (e.type !== 'config.status') return
      lastStatus = e.payload
      // Never opens by itself (Adrian, Sat 5 PM): the learner opens Settings (gear, launcher, ⌘,).
    })

    // ---- IPC ----------------------------------------------------------------------------------

    ctx.handle('settings:open', (p) => show(isSection((p as { section?: unknown } | undefined)?.section) ? (p as { section: Section }).section : undefined))
    ctx.handle('settings:about', (): AboutView => ({ version: ctx.app.getVersion() }))
    ctx.handle('settings:delete', (): DeleteResult => {
      const prev = keys
      keys = {}
      persist() // removes keys.bin
      if (error) {
        // keys.bin is still there: keep the keys in memory and on the engine too, so "Nothing was removed" is true.
        keys = prev
        error = undefined
        return { ok: false, keys: view() }
      }
      sendKeys() // every name, all empty: the engine drops the app's keys
      // The sign-in too (ROADMAP 5.4): only after the keys went, so ok false still means "nothing was removed".
      const signIn = removeFiles(ctx.app.getPath('userData'), SIGN_IN_FILES)
      if (!signIn) console.warn('[settings] a sign-in file could not be removed')
      return { ok: true, keys: view(), signIn }
    })
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
