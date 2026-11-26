/**
 * Core (v2, W0-4): app windows. Onboarding, Library, Progress and the Account sheet are normal macOS windows, an
 * explicit exception to "born from the island" (BUILD-PLAN decision 4): titled (hiddenInset traffic lights), opaque,
 * NOT a panel, NOT always on top, sandboxed like every window, a Dock icon while any is open.
 *
 * Renderer (core/surfaces.ts):
 *   bridge.invoke('window:open', route, args?)   open or focus; args (small JSON) reach the window as window:args
 *   bridge.invoke('window:close', route?)        close it (no route: the calling app window)
 *   bridge.invoke('window:focus', route)         bring it forward if open → boolean
 *   bridge.invoke('window:args')                 the calling window's latest args
 * Broadcast to that window only: feat:window:args (args), on every open after the first.
 *
 * Only the routes in APP_ROUTES open (allowlist). A renderer can't pick a URL, size, or window option.
 */
import { BrowserWindow, ipcMain, screen, type App, type BrowserWindowConstructorOptions, type IpcMainInvokeEvent } from 'electron'
import { windowSize } from '../renderer/src/core/theme'
import { windowBackground } from './prefs'
import { appWindowOptions, holdKeyboard, followsEverySpace, showInDock } from './platform'

/** Route → size (points). The feature's FeatureWindow {kind:'app'} must use the same route. */
export const APP_ROUTES = {
  onboarding: windowSize.onboarding,
  library: windowSize.library,
  progress: windowSize.progress,
  account: windowSize.account,
  auth: windowSize.auth
} as const
export type AppRoute = keyof typeof APP_ROUTES

const isRoute = (r: unknown): r is AppRoute => typeof r === 'string' && Object.prototype.hasOwnProperty.call(APP_ROUTES, r)

/** Args are tiny view hints ({id}, {view}, {section}): plain JSON, capped, never a URL the main process acts on. */
const MAX_ARGS = 2048
function cleanArgs(raw: unknown): Record<string, string | number | boolean> | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const out: Record<string, string | number | boolean> = {}
  for (const [k, v] of Object.entries(raw as Record<string, unknown>).slice(0, 8)) {
    if (!/^[a-zA-Z][a-zA-Z0-9_]{0,31}$/.test(k)) continue
    if (typeof v === 'string' && v.length <= 256) out[k] = v
    else if ((typeof v === 'number' && Number.isFinite(v)) || typeof v === 'boolean') out[k] = v
  }
  return JSON.stringify(out).length <= MAX_ARGS ? out : undefined
}

/**
 * Where an app window opens: its size, capped to the work area of the display under the pointer, centered there. The
 * launch splash (main/splash.ts) takes the home window's frame from here, so it sits exactly where home will appear.
 */
export function appWindowFrame(route: AppRoute): { x: number; y: number; width: number; height: number } {
  const size = APP_ROUTES[route]
  const area = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
  const width = Math.min(size.w, area.width - 32)
  const height = Math.min(size.h, area.height - 32)
  return { x: Math.round(area.x + (area.width - width) / 2), y: Math.round(area.y + (area.height - height) / 2), width, height }
}

export type AppWindows = {
  open(route: string, args?: unknown): BrowserWindow | undefined
  close(route: string): void
  focus(route: string): boolean
  get(route: string): BrowserWindow | undefined
  /** Is this webContents one of ours (an open app window)? */
  owns(sender: Electron.WebContents): boolean
  /** Is any app window on screen? Activating miyagi then may switch Spaces to it (platform.ts keyStep). */
  anyVisible(): boolean
}

export function setupAppWindows(deps: {
  app: App
  /** index.ts's window factory, with the app-window flavor (no panel type, no following Spaces). */
  create: (route: string, options: BrowserWindowConstructorOptions) => BrowserWindow
  /** Sender check (W0-6): only our own windows' main frames may call these. */
  trusted: (e: IpcMainInvokeEvent) => boolean
  /** The app in front (bundle id) when known: a keyboard retry stops once the learner went to another app. */
  frontApp?: () => string | undefined
}): AppWindows {
  const open = new Map<AppRoute, BrowserWindow>()
  const args = new Map<AppRoute, Record<string, string | number | boolean> | undefined>()

  const syncDock = (): void => showInDock(deps.app, open.size > 0)

  /**
   * An app window is a normal window: bringing it forward is meant to activate miyagi. show() + focus() asks for that, but
   * when the click came from a non-activating panel (the island, the launcher) the app behind can keep the keyboard, and
   * typing in Library's fields went to it (a tester, Nov 25: "I can't even type coffee"). Still not key a moment later:
   * ask again, then activate (holdKeyboard; here activating is the point: it is this very window macOS switches to).
   */
  // It stops for good once the window was key, or the learner went to another app (holdKeyboard), so a late retry never
  // pulls the keyboard back from where they went. A newer show of the same window replaces the older retries.
  const holding = new WeakMap<BrowserWindow, () => void>()
  const takeKeys = (win: BrowserWindow): void => {
    holding.get(win)?.()
    holding.set(win, holdKeyboard(win, { app: deps.app, isOpen: () => !win.isDestroyed() && win.isVisible(), fieldFocused: () => true, appWindowOpen: () => false, frontApp: deps.frontApp }))
  }

  const routeOf = (sender: Electron.WebContents): AppRoute | undefined => {
    for (const [r, w] of open) if (!w.isDestroyed() && w.webContents === sender) return r
    return undefined
  }

  const api: AppWindows = {
    open(route, a) {
      if (!isRoute(route)) return undefined
      const next = cleanArgs(a)
      args.set(route, next)
      const have = open.get(route)
      if (have && !have.isDestroyed()) {
        have.webContents.send('feat:window:args', next)
        if (have.isMinimized()) have.restore()
        have.show()
        have.focus()
        takeKeys(have)
        return have
      }
      const frame = appWindowFrame(route)
      const win = deps.create(route, {
        ...appWindowOptions(windowBackground()),
        ...frame,
        minWidth: Math.min(frame.width, 560),
        minHeight: Math.min(frame.height, 420),
        title: 'miyagi'
      })
      open.set(route, win)
      syncDock()
      win.once('ready-to-show', () => {
        if (win.isDestroyed()) return
        win.show()
        win.focus()
        takeKeys(win)
      })
      win.on('closed', () => {
        if (open.get(route) === win) open.delete(route)
        syncDock()
      })
      return win
    },
    close(route) {
      if (!isRoute(route)) return
      const w = open.get(route)
      if (w && !w.isDestroyed()) w.close()
    },
    focus(route) {
      if (!isRoute(route)) return false
      const w = open.get(route)
      if (!w || w.isDestroyed()) return false
      w.show()
      w.focus()
      takeKeys(w)
      return true
    },
    get(route) {
      return isRoute(route) ? open.get(route) : undefined
    },
    owns(sender) {
      return routeOf(sender) !== undefined
    },
    anyVisible() {
      for (const w of open.values()) if (!w.isDestroyed() && w.isVisible()) return true
      // Any other normal (non-panel) window on screen counts too (the splash, a window opened outside this map): those
      // are the ones macOS may switch Spaces to. Panels follow every Space (platform.ts panelType / followSpaces).
      return BrowserWindow.getAllWindows().some((w) => !w.isDestroyed() && w.isVisible() && !followsEverySpace(w))
    }
  }

  ipcMain.handle('feat:window:open', (e, route: unknown, a: unknown) => {
    if (!deps.trusted(e) || !isRoute(route)) return false
    return !!api.open(route, a)
  })
  ipcMain.handle('feat:window:close', (e, route: unknown) => {
    if (!deps.trusted(e)) return false
    const r = route === undefined ? routeOf(e.sender) : isRoute(route) ? route : undefined
    if (!r) return false
    api.close(r)
    return true
  })
  ipcMain.handle('feat:window:focus', (e, route: unknown) => (deps.trusted(e) && isRoute(route) ? api.focus(route) : false))
  ipcMain.handle('feat:window:args', (e) => {
    if (!deps.trusted(e)) return null
    const r = routeOf(e.sender)
    return r ? (args.get(r) ?? null) : null
  })

  return api
}
