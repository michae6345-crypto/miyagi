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
import { app, BrowserWindow, globalShortcut, ipcMain, screen, session, shell, type BrowserWindowConstructorOptions } from 'electron'
import { join } from 'node:path'
import { EngineLink } from './engine'
import { setupPrefs } from './prefs'
import { setupLocalEngine } from './localEngine'
import { serveRenderer } from './serve'
import type { MainContext, MainFeature } from './context'
import {
  describePlatform,
  followSpaces,
  isLeavingModifier,
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
const ENGINE_URL = process.env.ENGINE_URL ?? 'ws://localhost:8787'
const engine = new EngineLink(ENGINE_URL, process.env.DEMO === '1' ? (process.env.SCENARIO ?? 'full') : undefined)
let stopLocalEngine: () => void = () => undefined

const windows = new Set<BrowserWindow>()
/** Feature windows whose rects join the overlay's overlay.bounds report (ctx.reportBounds). */
const reported = new Set<BrowserWindow>()
type R = { x: number; y: number; w: number; h: number }
let overlayRects: R[] = []
const signalListeners = new Map<string, Set<(payload?: unknown) => void>>()
let overlay: BrowserWindow
let launcher: BrowserWindow
let launcherOpen = false
/** The island's latest size, so the launcher can grow out of its exact shape (dx/dy: a card moved off the spotlight). */
let islandSize: { w: number; h: number; dx?: number; dy?: number } = { w: 300, h: 34 }
/** Built app: where main/serve.ts serves the renderer (set before any window is created). */
let rendererOrigin: string | undefined
let actionsRegistered = false

/** v1: the engine watches the PRIMARY display only (contract: rects are relative to its full frame), so the overlay lives there. */
const displayNow = (): Electron.Display => screen.getPrimaryDisplay()

function createWindow(route: string, options: BrowserWindowConstructorOptions): BrowserWindow {
  const win = new BrowserWindow({
    show: false,
    // A panel on macOS, like the core windows, so it can sit over full-screen apps.
    ...(platform.os === 'mac' ? { type: 'panel' } : {}),
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
  showAfterFirstPaint(win)
  // Every Miyagi window follows the learner across Spaces and over full-screen apps (Michael, Sat).
  followSpaces(win)
  // window.open / target=_blank from any window: never a new Electron window; http(s) goes to the default browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url)
    return { action: 'deny' }
  })
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
  // Dev: Vite's server. Built: our own http://127.0.0.1 server (main/serve.ts), never file://, so YouTube embeds work.
  if (process.env.ELECTRON_RENDERER_URL) win.loadURL(`${process.env.ELECTRON_RENDERER_URL}#/${route}`)
  else if (rendererOrigin) win.loadURL(`${rendererOrigin}/index.html#/${route}`)
  else win.loadFile(join(__dirname, '../renderer/index.html'), { hash: `/${route}` })
  return win
}

/** If a window never reports its first paint (a failed load), show it anyway after this long rather than never. */
const FIRST_PAINT_FALLBACK_MS = 4000

/**
 * Review A23: a window shows only after its renderer's first paint (ready-to-show), so a transparent window never
 * flashes an empty or opaque frame. show() / showInactive() before then are held and run on ready-to-show (the
 * latest call wins; hide() cancels it). Every window is created hidden (show: false), so this covers the overlay,
 * the launcher and every feature window (player, settings). Windows are only ever resized when the display
 * changes, never during an animation.
 */
function showAfterFirstPaint(win: BrowserWindow): void {
  let painted = false
  let held: (() => void) | undefined
  const show = win.show.bind(win)
  const showInactive = win.showInactive.bind(win)
  const hide = win.hide.bind(win)
  const ready = (): void => {
    if (painted) return
    painted = true
    clearTimeout(fallback)
    const run = held
    held = undefined
    if (run && !win.isDestroyed()) run()
  }
  const fallback = setTimeout(ready, FIRST_PAINT_FALLBACK_MS)
  win.once('ready-to-show', ready)
  win.on('closed', () => clearTimeout(fallback))
  win.show = () => (painted ? show() : void (held = show))
  win.showInactive = () => (painted ? showInactive() : void (held = showInactive))
  win.hide = () => {
    held = undefined
    hide()
  }
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
  keptBlurs = []
  launcherModifier = false
  launcher.show()
  launcher.focus()
  raise(launcher)
  // macOS: focus() doesn't activate an inactive app, so with Finder (or any other app) in front the panel showed
  // but the keystrokes kept going there (Michael's test 10). If the launcher still isn't key a moment later, take it.
  if (process.platform === 'darwin') {
    setTimeout(() => {
      if (!launcherOpen || launcher.isDestroyed() || launcher.isFocused()) return
      app.focus({ steal: true })
      launcher.focus()
    }, 60)
  }
  send(launcher, 'launcher:open', { from: islandSize })
  send(overlay, 'launcher:open') // the island hides: the launcher window has it now
}

function closeLauncher(): void {
  if (launcherOpen) send(launcher, 'launcher:close') // renderer animates out, then emits launcher:hidden
}

/** When blurs kept the launcher open (loop guard: an app that keeps grabbing focus wins after a few tries). */
let keptBlurs: number[] = []
/** ⌘ or Ctrl is down in the launcher (from its own key events): a blur now is ⌘Tab, ⌘Space, Ctrl+→… */
let launcherModifier = false

/**
 * The launcher closes when the learner leaves it, not every time another app grabs the keyboard. It is a
 * non-activating panel, so VS Code stays the active app, and the editor coming forward on its own (the engine
 * opening it or jumping to a line) blurred it mid-typing (Michael, Sat 4 PM).
 * Leaving = ⌘/Ctrl held (app or Space switch), focus on another Miyagi window (Settings), or the pointer on
 * another display (a click there; a click on this display hits the launcher's dim, which closes it itself).
 * Those close it at once. Any other blur had no input from the learner behind it: take the keyboard back.
 * Plain typing never moves focus, so a recent keystroke doesn't count as leaving.
 */
function onLauncherBlur(): void {
  if (!launcherOpen) return
  setTimeout(() => {
    if (!launcherOpen || launcher.isDestroyed() || launcher.isFocused()) return
    const b = launcher.getBounds()
    const p = screen.getCursorScreenPoint()
    const onDisplay = p.x >= b.x && p.x < b.x + b.width && p.y >= b.y && p.y < b.y + b.height
    const now = Date.now()
    keptBlurs = keptBlurs.filter((t) => now - t < 3000)
    if (launcherModifier || BrowserWindow.getFocusedWindow() || !onDisplay || keptBlurs.length >= 4) return closeLauncher()
    keptBlurs.push(now)
    launcher.focus()
  }, 0)
}

function hideLauncher(): void {
  launcherOpen = false
  launcher.hide()
  send(overlay, 'launcher:closed') // the island is back
  returnFocus(app, overlay)
}

const ACTION_KINDS: Exclude<ShortcutKind, 'launcher'>[] = ['back', 'explain', 'diagram', 'show_me', 'hint', 'voice_toggle']

/** Global action shortcuts go to the overlay renderer, which decides (features may claim them) and tells the engine. */
function registerActionShortcuts(): void {
  if (actionsRegistered) return
  actionsRegistered = true
  for (const kind of ACTION_KINDS) {
    const ok = globalShortcut.register(platform.accelerators[kind], () => send(overlay, 'shortcut', kind))
    if (!ok) console.warn(`[tut] shortcut ${platform.accelerators[kind]} is taken by another app`)
  }
}

/** A lesson ended: hand the lesson keys back to the other apps until the next lesson.ready (Michael, Sun 12:49 AM). */
function unregisterActionShortcuts(): void {
  if (!actionsRegistered) return
  actionsRegistered = false
  for (const kind of ACTION_KINDS) globalShortcut.unregister(platform.accelerators[kind])
}

/** overlay.bounds = the overlay's own UI rects + every visible reported feature window (screen points). */
function sendBounds(): void {
  const extra = [...reported]
    .filter((w) => !w.isDestroyed() && w.isVisible())
    .map((w) => {
      const b = w.getBounds()
      return { x: b.x, y: b.y, w: b.width, h: b.height }
    })
  engine.send({ type: 'overlay.bounds', payload: { rects: [...overlayRects, ...extra] } })
}

function reportBounds(win: BrowserWindow): void {
  reported.add(win)
  for (const ev of ['move', 'resize', 'show', 'hide'] as const) win.on(ev as 'move', sendBounds)
  win.on('closed', () => {
    reported.delete(win)
    sendBounds()
  })
  sendBounds()
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

/**
 * Packaged builds load the renderer from file://, which sends no Referer, and YouTube's embed then refuses
 * to play (error 153). Give YouTube's own requests the site as Referer. Dev (http://localhost) is unaffected.
 * UNVERIFIED until a packaged build runs on the Mac.
 */
function youtubeReferer(): void {
  if (!app.isPackaged) return
  const urls = ['*://*.youtube.com/*', '*://*.youtube-nocookie.com/*', '*://*.googlevideo.com/*', '*://*.ytimg.com/*']
  session.defaultSession.webRequest.onBeforeSendHeaders({ urls }, (d, cb) => {
    if (!d.requestHeaders.Referer) d.requestHeaders.Referer = 'https://miyagi.study/'
    cb({ requestHeaders: d.requestHeaders })
  })
}

app.whenReady().then(async () => {
  setupApp(app)
  youtubeReferer()
  if (!process.env.ELECTRON_RENDERER_URL) {
    try {
      rendererOrigin = await serveRenderer(join(__dirname, '../renderer'))
    } catch (err) {
      console.error('[tut] could not serve the renderer over http, falling back to file:// (YouTube may refuse embeds)', err)
    }
  }
  overlay = createCoreWindow('overlay')
  launcher = createCoreWindow('launcher')

  overlay.setIgnoreMouseEvents(true, { forward: true })
  overlay.once('ready-to-show', () => overlay.showInactive())
  launcher.on('blur', onLauncherBlur)
  launcher.webContents.on('before-input-event', (_e, input) => (launcherModifier = isLeavingModifier(input)))

  engine.onEvent((e) => {
    forEachWindow((w) => w.webContents.send('engine:event', e))
    if (e.type === 'lesson.ready') registerActionShortcuts()
    if (e.type === 'lesson.ended') unregisterActionShortcuts()
  })
  engine.onStatus((c) => forEachWindow((w) => w.webContents.send('engine:status', c)))

  ipcMain.on('engine:cmd', (_e, cmd) => {
    if (cmd?.type === 'overlay.bounds') {
      overlayRects = cmd.payload?.rects ?? []
      return sendBounds()
    }
    engine.send(cmd)
  })

  ipcMain.on('ui:ready', (e) => {
    const win = BrowserWindow.fromWebContents(e.sender)
    if (!win) return
    // A renderer that (re)loads starts closed/click-through. If main still thinks the launcher is open,
    // its invisible full-screen window would keep the keyboard and every click: hide it.
    if (win === launcher && launcherOpen) hideLauncher()
    if (win === overlay) overlay.setIgnoreMouseEvents(true, { forward: true })
    e.sender.send('ui:layout', layoutFor(win))
    e.sender.send('engine:status', engine.connected)
    for (const ev of engine.log) e.sender.send('engine:event', ev)
  })

  ipcMain.on('ui:emit', (e, signal: string, payload: unknown) => {
    switch (signal) {
      case 'video:intent':
        // core seekVideo(): every OTHER window follows (the sender already set it).
        forEachWindow((w) => w.webContents !== e.sender && w.webContents.send('ui:video:intent', payload))
        break
      case 'overlay:interactive':
        overlay.setIgnoreMouseEvents(!payload, { forward: true })
        break
      case 'island:size':
        islandSize = payload as typeof islandSize
        break
      case 'island:yield':
      case 'island:return':
        send(overlay, signal, payload)
        break
      case 'launcher:toggle':
        launcherOpen ? closeLauncher() : openLauncher()
        break
      case 'shortcut':
        // A shortcut pressed in another window (the launcher's Explain / Hint chips): run it in the overlay, where
        // the bar, cards and the pressed-button spinner live, exactly like a global key.
        if (e.sender !== overlay.webContents) send(overlay, 'shortcut', payload)
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

  // Always-available kill switch: ⌃⌥Q (Mac; ⌥Q alone types "œ" in editors) / Alt+Q (Windows) quits the overlay.
  const quitKey = platform.os === 'mac' ? 'Control+Alt+Q' : 'Alt+Q'
  if (!globalShortcut.register(quitKey, () => app.quit())) console.warn(`[tut] quit shortcut ${quitKey} is taken`)

  screen.on('display-metrics-changed', () => {
    for (const w of [overlay, launcher]) {
      w.setBounds(overlayBounds(screen.getDisplayMatching(w.getBounds())))
      send(w, 'layout', layoutFor(w))
    }
  })

  setupPrefs((channel, payload) => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload)))
  // One download: a built app on a Mac starts (and first installs) the engine itself. See main/localEngine.ts.
  stopLocalEngine = setupLocalEngine(engine, ENGINE_URL, (channel, payload) => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload)))

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
    },
    reportBounds,
    raise,
    islandSize: () => islandSize,
    yieldIsland: (on) => send(overlay, on ? 'island:yield' : 'island:return'),
    overlayRects: () => overlayRects
  })
})

app.on('will-quit', () => {
  globalShortcut.unregisterAll()
  stopLocalEngine()
})
app.on('window-all-closed', () => app.quit())
