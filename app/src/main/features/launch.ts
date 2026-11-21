/**
 * Launch ease (brief: app/agents/launch-ease.md). Opening miyagi always opens something useful.
 *
 *   - Clicking the app (Dock icon, Launchpad, Spotlight, Finder) while it runs: macOS sends a reopen ('activate'). A
 *     second launch on Windows (or `open -n` on a Mac): 'second-instance'. A file dropped on the icon: 'open-file'
 *     (the file itself is ignored: miyagi never acts on a dropped file). Each one opens home:
 *       setup not done            → the setup window (onboarding)
 *       an app window is open     → bring it forward (Library first)
 *       otherwise                 → the Library (home: Continue, Ready to run, the progress entry)
 *   - A cold launch of the built app with setup done opens the Library too (setup not done: onboarding.ts opens setup).
 *     Not when started at login, not in `npm run dev`, not with MIYAGI_QUIET_LAUNCH=1.
 *   - The menu bar item (Tray): Open miyagi, Start a lesson (the launcher), Settings…, Quit miyagi. It keeps miyagi
 *     reachable with every window closed (the overlay app has no Dock icon until an app window opens, appWindows.ts).
 *   - Right-click on the pill: the same menu, at the pointer (launch:menu). Settings lives there now instead of a gear
 *     glued to the pill's edge (Michael's Mac: the gear covered the pill's status dot).
 *
 * The launcher and Settings open in the overlay's renderer (the launcher's toggle and settings:open are renderer
 * calls), so main asks the overlay window only: feat:launch:open 'launcher' | 'settings' (features/launch/index.tsx).
 *
 * Handles: launch:menu ({x, y}) → true once the menu is up (false: the renderer opens Settings instead).
 * UNVERIFIED in Electron (cost freeze, no live run in this lane): the reopen event on an LSUIElement app, the Tray, the
 * popup over the non-focusable overlay. Typechecked; stage-checked through features/launch/web.ts.
 */
import { app, Menu, nativeImage, Tray, type BrowserWindow, type MenuItemConstructorOptions } from 'electron'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { TRAY_ICON_1X, TRAY_ICON_2X } from '../launchIcon'

/** App windows, in the order a reopen brings them forward (appWindows.ts routes). */
const FORWARD = ['library', 'onboarding', 'progress', 'account'] as const
/** A reopen this soon after a launch at login is macOS finishing that launch, not the learner. */
const LOGIN_SETTLE_MS = 3000

// Module top level (main features load before app ready): a file dropped on the icon can launch the app, and that
// open-file arrives before setup runs.
let pending = false
let onOpenRequest: (() => void) | undefined
app.on('open-file', (e) => {
  e.preventDefault()
  if (onOpenRequest) onOpenRequest()
  else pending = true
})

/** Kept for the life of the app: a Tray that gets garbage-collected leaves the menu bar. */
let tray: Tray | undefined

function readJson(file: string): Record<string, unknown> | undefined {
  try {
    const v: unknown = JSON.parse(readFileSync(file, 'utf8'))
    return v && typeof v === 'object' ? (v as Record<string, unknown>) : undefined
  } catch {
    return undefined
  }
}

function startedAtLogin(): boolean {
  try {
    return process.platform === 'darwin' && app.getLoginItemSettings().wasOpenedAtLogin === true
  } catch {
    return false
  }
}

export default defineMainFeature({
  id: 'launch',
  setup(ctx) {
    const mac = ctx.platform.os === 'mac'
    const readyAt = Date.now()
    const atLogin = startedAtLogin()

    // macOS keeps one copy per app already; this covers `open -n` in the built app (Windows: features/windows.ts).
    if (mac && ctx.app.isPackaged && !ctx.app.requestSingleInstanceLock()) {
      ctx.app.exit(0)
      return
    }

    /** Setup finished on this Mac: onboarding.ts's flag file (or the shared pref it also sets). Read on every open. */
    const onboarded = (): boolean => {
      if (process.env.MIYAGI_SKIP_ONBOARDING === '1') return true
      const dir = ctx.app.getPath('userData')
      return readJson(join(dir, 'onboarding.json'))?.done === true || readJson(join(dir, 'prefs.json'))?.onboarded === true
    }

    /** An accessory app's window doesn't come forward by itself: activate miyagi once the window is showing. */
    const bringForward = (win: BrowserWindow | undefined): void => {
      if (!win || win.isDestroyed() || !mac) return
      const steal = (): void => {
        if (!win.isDestroyed()) ctx.app.focus({ steal: true })
      }
      if (win.isVisible()) steal()
      else win.once('show', steal)
    }

    const openHome = (): void => {
      if (ctx.overlay.isDestroyed()) return
      if (!onboarded()) return bringForward(ctx.openWindow('onboarding'))
      for (const route of FORWARD) {
        const w = ctx.appWindow(route)
        if (w && !w.isDestroyed()) return bringForward(ctx.openWindow(route))
      }
      bringForward(ctx.openWindow('library'))
    }

    /** The overlay's renderer opens the launcher (its toggle) and Settings (grown from the pill). */
    const askOverlay = (what: 'launcher' | 'settings'): void => {
      if (ctx.overlay.isDestroyed()) return
      if (what === 'launcher' && !ctx.launcher.isDestroyed() && ctx.launcher.isVisible()) return // already open: a toggle would close it
      ctx.overlay.webContents.send('feat:launch:open', what)
    }

    const template = (): MenuItemConstructorOptions[] => [
      { label: 'Open miyagi', click: openHome },
      // The launcher's own global key, shown (not registered twice).
      { label: 'Start a lesson', accelerator: ctx.platform.accelerators.launcher, registerAccelerator: false, click: () => askOverlay('launcher') },
      { label: 'Settings…', click: () => askOverlay('settings') },
      { type: 'separator' },
      // Lane realapp: About (app version + the engine inside, main/identity.ts) with no app window open. macOS only:
      // the accessory app's own menu shows only while an app window is in front. Activate first so the panel is on top.
      ...(process.platform === 'darwin'
        ? [
            {
              label: 'About miyagi',
              click: (): void => {
                ctx.app.focus({ steal: true })
                ctx.app.showAboutPanel()
              }
            } satisfies MenuItemConstructorOptions
          ]
        : []),
      { label: 'Quit miyagi', click: () => ctx.app.quit() }
    ]

    // ---- the menu bar item ------------------------------------------------------------------------------------------
    try {
      const icon = nativeImage.createFromDataURL(TRAY_ICON_1X)
      icon.addRepresentation({ scaleFactor: 2, dataURL: TRAY_ICON_2X })
      tray = new Tray(icon)
      tray.setToolTip('miyagi')
      tray.setContextMenu(Menu.buildFromTemplate(template()))
      // Windows: a left click opens home (right click shows the menu). macOS shows the menu on any click.
      if (!mac) tray.on('click', openHome)
      ctx.app.on('before-quit', () => {
        tray?.destroy()
        tray = undefined
      })
    } catch (err) {
      console.warn('[launch] no menu bar item', err instanceof Error ? err.message : '')
    }

    // ---- right-click on the pill ------------------------------------------------------------------------------------
    ctx.handle('launch:menu', (p) => {
      if (ctx.overlay.isDestroyed()) return false
      const at = p as { x?: unknown; y?: unknown } | undefined
      const x = Number(at?.x)
      const y = Number(at?.y)
      const b = ctx.overlay.getBounds()
      const inside = Number.isFinite(x) && Number.isFinite(y) && x >= 0 && y >= 0 && x <= b.width && y <= b.height
      try {
        Menu.buildFromTemplate(template()).popup({ window: ctx.overlay, ...(inside ? { x: Math.round(x), y: Math.round(y) } : {}) })
        return true
      } catch {
        return false
      }
    })

    // ---- opening the app again ----------------------------------------------------------------------------------------
    ctx.app.on('activate', () => {
      if (atLogin && Date.now() - readyAt < LOGIN_SETTLE_MS) return
      openHome()
    })
    ctx.app.on('second-instance', openHome)
    onOpenRequest = openHome

    // ---- a cold launch ----------------------------------------------------------------------------------------------
    const coldHome = ctx.app.isPackaged && !atLogin && process.env.MIYAGI_QUIET_LAUNCH !== '1' && onboarded()
    if (coldHome || pending) {
      pending = false
      const go = (): void => openHome()
      if (ctx.overlay.webContents.isLoading()) ctx.overlay.webContents.once('did-finish-load', go)
      else go()
    }
  }
})
