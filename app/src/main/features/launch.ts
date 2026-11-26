/**
 * Launch ease (brief: app/agents/launch-ease.md). Opening miyagi always opens something useful.
 *
 *   - Clicking the app (Dock icon, Launchpad, Spotlight, Finder) while it runs: macOS sends a reopen ('activate'). A
 *     second launch on Windows (or `open -n` on a Mac): 'second-instance'. A file dropped on the icon: 'open-file'
 *     (the file itself is ignored: miyagi never acts on a dropped file). Each one opens home:
 *       a fallback login window   → bring it forward as it is (the Account page's Sign in)
 *       the gate is closed        → the home window, the same one: its first-run flow carries on where it is (one
 *                                   window from start to finish, Michael Nov 21; never a second window over it)
 *       an app window is open     → bring it forward (Library first)
 *       otherwise                 → the Library (home: Continue, Ready to run, the progress entry)
 *   - A cold launch opens the Library too (the gate closed: the same home window, in its first-run flow at the login).
 *     Not when started at login, not with MIYAGI_QUIET_LAUNCH=1.
 *   - The menu bar item (Tray): Open miyagi, Start a lesson (the launcher), Settings…, Quit miyagi. It keeps miyagi
 *     reachable with every window closed (the overlay app has no Dock icon until an app window opens, appWindows.ts).
 *     While the launch gate is closed (main/gate.ts: login and setup not through yet) it shows only Open miyagi and
 *     Quit miyagi, and nothing asks the overlay for the launcher or Settings.
 *   - "Hide miyagi overlays" / "Show miyagi overlays" (main/overlayHide.ts, features/overlay-hide.ts owns its key, shown here).
 *   - "Show me around" re-opens the first-lesson walkthrough (features/tips TourLayer.tsx) from the menu bar, the Help entry.
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
import { defineMainFeature } from '../context'
import { gateIsOpen, gateView, onGate } from '../gate'
import { getPrefs, onPrefsChange } from '../prefs'
import { TRAY_ICON_1X, TRAY_ICON_2X } from '../launchIcon'
import { onOverlaysHidden, overlaysHidden, toggleOverlaysHidden } from '../overlayHide'
import { hideOverlaysAccelerator } from '../../common/shortcuts'

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

    // macOS keeps one copy per app already; this covers `open -n` (Windows: features/windows.ts). Dev copies too: the
    // lock is keyed on userData, and a dev copy has its own, so a dev copy and the installed app never block each other.
    if (mac && !ctx.app.requestSingleInstanceLock()) {
      ctx.app.exit(0)
      return
    }

    /**
     * Setup done or put off on this Mac, as onboarding.ts reports it to the gate. Never prefs.json's onboarded: that
     * pref outlived a reset onboarding.json and skipped the first run (Michael, Nov 21).
     */
    const onboarded = (): boolean => process.env.MIYAGI_SKIP_ONBOARDING === '1' || gateView().setup

    /** An accessory app's window doesn't come forward by itself: activate miyagi once the window is showing. */
    const bringForward = (win: BrowserWindow | undefined): void => {
      if (!win || win.isDestroyed() || !mac) return
      const steal = (): void => {
        if (!win.isDestroyed()) ctx.app.focus({ steal: true })
      }
      if (win.isVisible()) steal()
      else win.once('show', steal)
    }

    /** An open window as it is: shown and focused, no new args (they would reset what it shows). */
    const raise = (win: BrowserWindow): void => {
      if (win.isMinimized()) win.restore()
      win.show()
      win.focus()
      bringForward(win)
    }

    const openHome = (): void => {
      if (ctx.overlay.isDestroyed()) return
      // A fallback login window is up (features/auth, the Account page's Sign in): bring it forward as it is.
      const login = ctx.appWindow('auth')
      if (login && !login.isDestroyed()) return raise(login)
      // The gate is closed (login or setup still ahead): the home window runs the first-run flow. Bring that same
      // window forward (never re-open it with args, which would move it off the step it is on), or open it.
      if (!gateIsOpen() || !onboarded()) {
        const home = ctx.appWindow('library')
        if (home && !home.isDestroyed()) return raise(home)
        return bringForward(ctx.openWindow('library'))
      }
      for (const route of FORWARD) {
        const w = ctx.appWindow(route)
        if (w && !w.isDestroyed()) return bringForward(ctx.openWindow(route))
      }
      bringForward(ctx.openWindow('library'))
    }

    /** The overlay's renderer opens the launcher (its toggle) and Settings (grown from the pill). */
    const askOverlay = (what: 'launcher' | 'settings' | 'tour'): void => {
      if (ctx.overlay.isDestroyed() || !gateIsOpen()) return
      if (what === 'launcher' && !ctx.launcher.isDestroyed() && ctx.launcher.isVisible()) return // already open: a toggle would close it
      ctx.overlay.webContents.send('feat:launch:open', what)
    }

    const launcherKey = (): string => getPrefs().shortcuts.launcher ?? ctx.platform.accelerators.launcher
    const template = (): MenuItemConstructorOptions[] =>
      gateIsOpen() ? full() : [{ label: 'Open miyagi', click: openHome }, { label: 'Quit miyagi', click: () => ctx.app.quit() }]
    const full = (): MenuItemConstructorOptions[] => [
      { label: 'Open miyagi', click: openHome },
      // The launcher's own global key (the learner's own when rebound), shown (not registered twice).
      { label: 'Start a lesson', accelerator: launcherKey(), registerAccelerator: false, click: () => askOverlay('launcher') },
      { label: 'Show me around', click: () => askOverlay('tour') },
      { label: 'Settings…', click: () => askOverlay('settings') },
      { type: 'separator' },
      {
        label: overlaysHidden() ? 'Show miyagi overlays' : 'Hide miyagi overlays',
        accelerator: hideOverlaysAccelerator(mac),
        registerAccelerator: false,
        click: () => void toggleOverlaysHidden()
      },
      { type: 'separator' },
      { label: 'Quit miyagi', click: () => ctx.app.quit() }
    ]

    // ---- the menu bar item ------------------------------------------------------------------------------------------
    try {
      const icon = nativeImage.createFromDataURL(TRAY_ICON_1X)
      icon.addRepresentation({ scaleFactor: 2, dataURL: TRAY_ICON_2X })
      tray = new Tray(icon)
      tray.setToolTip('miyagi')
      tray.setContextMenu(Menu.buildFromTemplate(template()))
      // The full menu once the gate opens; back to Open and Quit if it closes again (a sign-out).
      let shown = gateIsOpen()
      onGate((open) => {
        if (open === shown || !tray) return
        shown = open
        tray.setContextMenu(Menu.buildFromTemplate(template()))
      })
      // A rebound launcher key (Settings > Shortcuts): the menu shows the new one.
      let key = launcherKey()
      onPrefsChange(() => {
        if (!tray || key === launcherKey()) return
        key = launcherKey()
        tray.setContextMenu(Menu.buildFromTemplate(template()))
      })
      // Hide / Show miyagi overlays: the item says which one it will do.
      onOverlaysHidden(() => tray?.setContextMenu(Menu.buildFromTemplate(template())))
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
      if (ctx.overlay.isDestroyed() || !gateIsOpen()) return false
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
    // The one owner of a second launch (index.ts no longer opens the launcher for it).
    ctx.app.on('second-instance', openHome)
    onOpenRequest = openHome

    // ---- a cold launch ----------------------------------------------------------------------------------------------
    // Dev copies open home too (Michael tests from a dev build; MIYAGI_QUIET_LAUNCH=1 keeps it quiet for recordings).
    // A closed gate always opens home (its flow at the login): launch is start from new. onboarding.ts may open the
    // same window first; openHome then only brings it forward.
    const coldHome = !atLogin && process.env.MIYAGI_QUIET_LAUNCH !== '1'
    if (coldHome || pending) {
      pending = false
      const go = (): void => openHome()
      if (ctx.overlay.webContents.isLoading()) ctx.overlay.webContents.once('did-finish-load', go)
      else go()
    }
  }
})
