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
import { ipcMain, screen, type App, type BrowserWindow, type BrowserWindowConstructorOptions, type IpcMainInvokeEvent } from 'electron'
import { windowSize } from '../renderer/src/core/theme'
import { windowBackground } from './prefs'
import { appWindowOptions, showInDock } from './platform'

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

export type AppWindows = {
  open(route: string, args?: unknown): BrowserWindow | undefined
  close(route: string): void
  focus(route: string): boolean
  get(route: string): BrowserWindow | undefined
  /** Is this webContents one of ours (an open app window)? */
  owns(sender: Electron.WebContents): boolean
}

export function setupAppWindows(deps: {
  app: App
  /** index.ts's window factory, with the app-window flavor (no panel type, no following Spaces). */
  create: (route: string, options: BrowserWindowConstructorOptions) => BrowserWindow
  /** Sender check (W0-6): only our own windows' main frames may call these. */
  trusted: (e: IpcMainInvokeEvent) => boolean
}): AppWindows {
  const open = new Map<AppRoute, BrowserWindow>()
  const args = new Map<AppRoute, Record<string, string | number | boolean> | undefined>()

  const syncDock = (): void => showInDock(deps.app, open.size > 0)

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
        return have
      }
      const size = APP_ROUTES[route]
      const area = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
      const w = Math.min(size.w, area.width - 32)
      const h = Math.min(size.h, area.height - 32)
      const win = deps.create(route, {
        ...appWindowOptions(windowBackground()),
        width: w,
        height: h,
        minWidth: Math.min(w, 560),
        minHeight: Math.min(h, 420),
        x: Math.round(area.x + (area.width - w) / 2),
        y: Math.round(area.y + (area.height - h) / 2),
        title: 'miyagi'
      })
      open.set(route, win)
      syncDock()
      win.once('ready-to-show', () => {
        if (win.isDestroyed()) return
        win.show()
        win.focus()
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
      return true
    },
    get(route) {
      return isRoute(route) ? open.get(route) : undefined
    },
    owns(sender) {
      return routeOf(sender) !== undefined
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
