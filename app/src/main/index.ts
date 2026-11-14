/**
 * Two preloaded, always-on-top, transparent windows covering the display:
 *   overlay  : pill / cards / diagram / shortcut bar / dim + spotlight. Click-through except over controls.
 *   launcher : the Spotlight-style panel. Focusable. Shrinks into the pill on "Build lesson".
 * Both span the whole display, so the launcher can land exactly on the pill's pixels.
 * Nothing is ever resized during an animation; windows are only shown/hidden.
 */
import { app, BrowserWindow, globalShortcut, ipcMain, screen } from 'electron'
import { join } from 'node:path'
import { EngineLink } from './engine'
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
import { cmd } from '../common/wire'

const platform = describePlatform(process.platform)
const engine = new EngineLink(process.env.ENGINE_URL ?? 'ws://localhost:8787', process.env.DEMO === '1' ? (process.env.SCENARIO ?? 'full') : undefined)

let overlay: BrowserWindow
let launcher: BrowserWindow
let launcherOpen = false
let actionsRegistered = false

function createWindow(route: 'overlay' | 'launcher'): BrowserWindow {
  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
  const win = new BrowserWindow({
    ...overlayWindowOptions(overlayBounds(display)),
    ...(route === 'launcher' ? { focusable: true, ...launcherGlassOptions() } : { focusable: false }),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
      contextIsolation: true,
      backgroundThrottling: false,
      additionalArguments: [`--tut-platform=${encodeURIComponent(JSON.stringify(platform))}`]
    }
  })
  raise(win)
  win.setBounds(overlayBounds(display)) // after raising, so macOS lets it cover the menu bar
  if (!app.isPackaged) {
    // Pipe renderer warnings/errors into the terminal (the overlay has no visible devtools).
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

function layoutFor(win: BrowserWindow): Layout {
  const b = win.getBounds()
  const d = screen.getDisplayMatching(b)
  const wa = d.workArea
  return { origin: { x: b.x, y: b.y }, width: b.width, height: b.height, workArea: { x: wa.x - b.x, y: wa.y - b.y, width: wa.width, height: wa.height } }
}

function send(win: BrowserWindow | undefined, signal: UiSignal, payload?: unknown): void {
  if (win && !win.isDestroyed()) win.webContents.send(`ui:${signal}`, payload)
}

function openLauncher(): void {
  if (launcherOpen) return
  launcherOpen = true
  launcher.show()
  launcher.focus()
  raise(launcher)
  send(launcher, 'launcher:open')
}

function closeLauncher(): void {
  if (launcherOpen) send(launcher, 'launcher:close') // renderer animates out, then emits launcher:hidden
}

function hideLauncher(): void {
  launcherOpen = false
  launcher.hide()
  returnFocus(app, overlay)
}

function registerActionShortcuts(): void {
  if (actionsRegistered) return
  actionsRegistered = true
  const kinds: Exclude<ShortcutKind, 'launcher'>[] = ['back', 'explain', 'diagram', 'show_me', 'hint', 'voice_toggle']
  for (const kind of kinds) {
    const ok = globalShortcut.register(platform.accelerators[kind], () => {
      engine.send(cmd('action', { kind }))
      send(overlay, 'shortcut', kind)
    })
    if (!ok) console.warn(`[tut] shortcut ${platform.accelerators[kind]} is taken by another app`)
  }
}

app.whenReady().then(() => {
  setupApp(app)
  overlay = createWindow('overlay')
  launcher = createWindow('launcher')

  overlay.setIgnoreMouseEvents(true, { forward: true })
  overlay.once('ready-to-show', () => overlay.showInactive())
  launcher.on('blur', () => closeLauncher())

  engine.onEvent((e) => {
    for (const w of [overlay, launcher]) if (!w.isDestroyed()) w.webContents.send('engine:event', e)
    if (e.type === 'lesson.ready') registerActionShortcuts()
  })
  engine.onStatus((c) => {
    for (const w of [overlay, launcher]) if (!w.isDestroyed()) w.webContents.send('engine:status', c)
  })

  ipcMain.on('engine:cmd', (_e, cmd) => engine.send(cmd))

  ipcMain.on('ui:ready', (e) => {
    const win = BrowserWindow.fromWebContents(e.sender)
    if (!win) return
    e.sender.send('ui:layout', layoutFor(win))
    e.sender.send('engine:status', engine.connected)
    for (const ev of engine.log) e.sender.send('engine:event', ev)
  })

  ipcMain.on('ui:emit', (_e, signal: UiSignal, payload: unknown) => {
    switch (signal) {
      case 'overlay:interactive':
        overlay.setIgnoreMouseEvents(!payload, { forward: true })
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
  })

  const ok = globalShortcut.register(platform.accelerators.launcher, () => (launcherOpen ? closeLauncher() : openLauncher()))
  if (!ok) console.warn(`[tut] launcher shortcut ${platform.accelerators.launcher} is taken`)

  screen.on('display-metrics-changed', () => {
    for (const w of [overlay, launcher]) {
      w.setBounds(overlayBounds(screen.getDisplayMatching(w.getBounds())))
      send(w, 'layout', layoutFor(w))
    }
  })
})

app.on('will-quit', () => globalShortcut.unregisterAll())
app.on('window-all-closed', () => app.quit())
