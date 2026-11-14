/**
 * Core main process. Two preloaded, always-on-top, transparent windows covering the display:
 *   overlay  : pill / cards / diagram / shortcut bar / dim + spotlight. Click-through except over controls.
 *   launcher : the Spotlight-style panel. Focusable. Shrinks into the pill on "Build lesson".
 * Both span the whole display, so the launcher can land exactly on the pill's pixels.
 * Nothing is ever resized during an animation; windows are only shown/hidden.
 *
 * Features add their own main-process code in src/main/features/<name>.ts (see context.ts).
 * Owner: core.
 */
import { app, BrowserWindow, globalShortcut, ipcMain, screen, type BrowserWindowConstructorOptions } from 'electron'
import { join } from 'node:path'
import { EngineLink } from './engine'
import type { MainContext, MainFeature } from './context'
import {
  describePlatform,
  launcherGlassOptions,
  overlayBounds,
  overlayWindowOptions,
  raise,
  returnFocus,
  setupApp,
  type ShortcutKind
} from './platform'
import type { Layout, UiSignal } from '../preload/api'

const platform = describePlatform(process.platform)
const engine = new EngineLink(process.env.ENGINE_URL ?? 'ws://localhost:8787', process.env.DEMO === '1' ? (process.env.SCENARIO ?? 'full') : undefined)

const windows = new Set<BrowserWindow>()
const signalListeners = new Map<string, Set<(payload?: unknown) => void>>()
let overlay: BrowserWindow
let launcher: BrowserWindow
let launcherOpen = false
/** The island's latest size, so the launcher can grow out of its exact shape. */
let islandSize = { w: 300, h: 34 }
let actionsRegistered = false

const displayNow = (): Electron.Display => screen.getDisplayNearestPoint(screen.getCursorScreenPoint())

function createWindow(route: string, options: BrowserWindowConstructorOptions): BrowserWindow {
  const win = new BrowserWindow({
    show: false,
    ...options,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
      contextIsolation: true,
      backgroundThrottling: false,
      additionalArguments: [`--tut-platform=${encodeURIComponent(JSON.stringify(platform))}`],
      ...options.webPreferences
    }
  })
  windows.add(win)
  win.on('closed', () => windows.delete(win))
  if (!app.isPackaged) {
    // Pipe renderer warnings/errors into the terminal (overlay windows have no visible devtools).
    win.webContents.on('console-message', (...args: unknown[]) => {
      const ev = args[0] as { level?: string | number; message?: string }
      const level = ev.level ?? args[1]
      const msg = ev.message ?? String(args[2] ?? '')
      if (level === 'error' || level === 'warning' || level === 2 || level === 3) console.log(`[${route}] ${msg}`)
    })
    win.webContents.on('render-process-gone', (_e, d) => console.error(`[${route}] renderer gone: ${d.reason}`))
  }
  if (process.env.ELECTRON_RENDERER_URL) win.loadURL(`${process.env.ELECTRON_RENDERER_URL}#/${route}`)
  else win.loadFile(join(__dirname, '../renderer/index.html'), { hash: `/${route}` })
  return win
}

/** The two core windows: full display, transparent, always on top. */
function createCoreWindow(route: 'overlay' | 'launcher'): BrowserWindow {
  const bounds = overlayBounds(displayNow())
  const win = createWindow(route, {
    ...overlayWindowOptions(bounds),
    ...(route === 'launcher' ? { focusable: true, ...launcherGlassOptions() } : { focusable: false })
  })
  raise(win)
  win.setBounds(bounds) // after raising, so macOS lets it cover the menu bar
  return win
}

function layoutFor(win: BrowserWindow): Layout {
  const b = win.getBounds()
  const wa = screen.getDisplayMatching(b).workArea
  return { origin: { x: b.x, y: b.y }, width: b.width, height: b.height, workArea: { x: wa.x - b.x, y: wa.y - b.y, width: wa.width, height: wa.height } }
}

function send(win: BrowserWindow | undefined, signal: UiSignal, payload?: unknown): void {
  if (win && !win.isDestroyed()) win.webContents.send(`ui:${signal}`, payload)
}

function forEachWindow(fn: (w: BrowserWindow) => void): void {
  for (const w of windows) if (!w.isDestroyed()) fn(w)
}

function openLauncher(): void {
  if (launcherOpen) return
  launcherOpen = true
  launcher.show()
  launcher.focus()
  raise(launcher)
  send(launcher, 'launcher:open', { from: islandSize })
  send(overlay, 'launcher:open') // the island hides: the launcher window has it now
}

function closeLauncher(): void {
  if (launcherOpen) send(launcher, 'launcher:close') // renderer animates out, then emits launcher:hidden
}

function hideLauncher(): void {
  launcherOpen = false
  launcher.hide()
  send(overlay, 'launcher:closed') // the island is back
  returnFocus(app, overlay)
}

/** Global action shortcuts go to the overlay renderer, which decides (features may claim them) and tells the engine. */
function registerActionShortcuts(): void {
  if (actionsRegistered) return
  actionsRegistered = true
  const kinds: Exclude<ShortcutKind, 'launcher'>[] = ['back', 'explain', 'diagram', 'show_me', 'hint', 'voice_toggle']
  for (const kind of kinds) {
    const ok = globalShortcut.register(platform.accelerators[kind], () => send(overlay, 'shortcut', kind))
    if (!ok) console.warn(`[tut] shortcut ${platform.accelerators[kind]} is taken by another app`)
  }
}

function loadFeatures(ctx: MainContext): void {
  const mods = import.meta.glob<{ default: MainFeature }>('./features/*.ts', { eager: true })
  for (const [path, mod] of Object.entries(mods)) {
    try {
      mod.default?.setup(ctx)
      console.log(`[tut] main feature: ${mod.default?.id ?? path}`)
    } catch (err) {
      console.error(`[tut] main feature ${path} failed`, err)
    }
  }
}

app.whenReady().then(() => {
  setupApp(app)
  overlay = createCoreWindow('overlay')
  launcher = createCoreWindow('launcher')

  overlay.setIgnoreMouseEvents(true, { forward: true })
  overlay.once('ready-to-show', () => overlay.showInactive())
  launcher.on('blur', () => closeLauncher())

  engine.onEvent((e) => {
    forEachWindow((w) => w.webContents.send('engine:event', e))
    if (e.type === 'lesson.ready') registerActionShortcuts()
  })
  engine.onStatus((c) => forEachWindow((w) => w.webContents.send('engine:status', c)))

  ipcMain.on('engine:cmd', (_e, cmd) => engine.send(cmd))

  ipcMain.on('ui:ready', (e) => {
    const win = BrowserWindow.fromWebContents(e.sender)
    if (!win) return
    e.sender.send('ui:layout', layoutFor(win))
    e.sender.send('engine:status', engine.connected)
    for (const ev of engine.log) e.sender.send('engine:event', ev)
  })

  ipcMain.on('ui:emit', (_e, signal: string, payload: unknown) => {
    switch (signal) {
      case 'overlay:interactive':
        overlay.setIgnoreMouseEvents(!payload, { forward: true })
        break
      case 'island:size':
        islandSize = payload as typeof islandSize
        break
      case 'launcher:toggle':
        launcherOpen ? closeLauncher() : openLauncher()
        break
      case 'launcher:hidden':
        hideLauncher()
        break
      case 'launcher:built':
        // The launcher just shrank onto the pill's exact pixels: swap windows in the same frame.
        send(overlay, 'pill:receive')
        hideLauncher()
        break
    }
    signalListeners.get(signal)?.forEach((fn) => fn(payload))
  })

  const ok = globalShortcut.register(platform.accelerators.launcher, () => (launcherOpen ? closeLauncher() : openLauncher()))
  if (!ok) console.warn(`[tut] launcher shortcut ${platform.accelerators.launcher} is taken`)

  // Always-available kill switch: ⌥Q (Mac) / Alt+Q (Windows) quits the overlay.
  if (!globalShortcut.register('Alt+Q', () => app.quit())) console.warn('[tut] quit shortcut Alt+Q is taken')

  screen.on('display-metrics-changed', () => {
    for (const w of [overlay, launcher]) {
      w.setBounds(overlayBounds(screen.getDisplayMatching(w.getBounds())))
      send(w, 'layout', layoutFor(w))
    }
  })

  loadFeatures({
    app,
    platform,
    engine,
    overlay,
    launcher,
    display: () => screen.getDisplayMatching(overlay.getBounds()),
    createWindow,
    overlayOptions: overlayWindowOptions,
    handle: (channel, fn) => ipcMain.handle(`feat:${channel}`, (_e, ...args) => fn(...args)),
    broadcast: (channel, payload) => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload)),
    onSignal: (signal, fn) => {
      if (!signalListeners.has(signal)) signalListeners.set(signal, new Set())
      signalListeners.get(signal)!.add(fn)
    }
  })
})

app.on('will-quit', () => globalShortcut.unregisterAll())
app.on('window-all-closed', () => app.quit())
