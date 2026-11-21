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
import { app, BrowserWindow, globalShortcut, ipcMain, Menu, net, powerMonitor, screen, session, type BrowserWindowConstructorOptions, type IpcMainEvent, type IpcMainInvokeEvent, type WebContents } from 'electron'
import { join } from 'node:path'
import { V2_COMMANDS } from '../common/wire'
import { setupIdentity } from './identity'
import { EngineLink } from './engine'
import { setupPrefs, trackWindowBackground, windowBackground } from './prefs'
import { ENGINE_TOKEN, localEngineState, setupLocalEngine } from './localEngine'
import { serveRenderer } from './serve'
import { setupAppWindows, type AppWindows } from './appWindows'
import { setupPermissions } from './permissions'
import { debugFlagIn, openLinkInBrowser, safeOpenExternal } from './safeOpen'
import { previousApp } from './features/front-app'
import { gateCore, gateIsOpen } from './gate'
import { coalesce } from './coalesce'
import type { MainContext, MainFeature } from './context'
import {
  describePlatform,
  fitPillTop,
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
import { VOICE_ENABLED } from '../common/flags'
import { notchFor, startNotch, type NotchService } from './notch'
import { helperPath } from './features/ptt'
import { getPrefs, onPrefsChange } from './prefs'

// A built app never starts under a debugger (app-harden): --inspect*, --remote-debugging-* or --js-flags in argv quits
// before any window, engine or key exists. The fuses already make Node ignore --inspect; Chromium's remote debugging has
// no fuse. Dev runs (npm run dev) keep them.
if (app.isPackaged) {
  const flag = debugFlagIn(process.argv)
  if (flag) {
    console.error(`[tut] a packaged miyagi does not start with --${flag}; quitting`)
    app.exit(1)
    process.exit(1)
  }
}

const platform = describePlatform(process.platform)
const ENGINE_URL = process.env.ENGINE_URL ?? 'ws://localhost:8787'
// The token goes in with the constructor: the first connect starts there, before setupLocalEngine runs.
const engine = new EngineLink(ENGINE_URL, process.env.DEMO === '1' ? (process.env.SCENARIO ?? 'full') : undefined, ENGINE_TOKEN)
let stopLocalEngine: () => void = () => undefined
/** Notch geometry + Boring Notch state (main/notch.ts); started at launch. */
let notchService: NotchService | undefined
/** Every window gets its layout again (Settings > General shows whether Boring Notch is using the notch). Module level: the first notch read can land before whenReady has finished. */
const resendLayout = (): void => forEachWindow((w) => send(w, 'layout', layoutFor(w)))

const windows = new Set<BrowserWindow>()
/** Feature windows whose rects join the overlay's overlay.bounds report (ctx.reportBounds). */
const reported = new Set<BrowserWindow>()
type R = { x: number; y: number; w: number; h: number }
let overlayRects: R[] = []
const signalListeners = new Map<string, Set<(payload?: unknown) => void>>()
let overlay: BrowserWindow
let launcher: BrowserWindow
let launcherOpen = false
/** Bumped on every close request and open: a stale close watchdog never hides a newer open. */
let launcherGen = 0
/** When the launcher last opened (ms): a second press of the key inside LAUNCHER_DOUBLE_MS is the same press twice, not a close. */
let launcherOpenedAt = 0
const LAUNCHER_DOUBLE_MS = 400
/** The miyagi window (home, settings...) that had the keyboard when the launcher opened: Esc gives it back there, never to Finder. */
let launcherOrigin: BrowserWindow | undefined
/** The pill's top before fitting to a display's menu bar / notch band (platform.pillTop is the fitted one). */
let basePillTop = 0
/** The island's latest size, so the launcher can grow out of its exact shape (dx/dy: a card moved off the spotlight). */
let islandSize: { w: number; h: number; dx?: number; dy?: number; shown?: boolean; top?: number; place?: 'notch'; radii?: { top: number; bottom: number } } = { w: 300, h: 34 }
/** Built app: where main/serve.ts serves the renderer (set before any window is created). */
let rendererOrigin: string | undefined
let actionsRegistered = false

/** v1: the engine watches the PRIMARY display only (contract: rects are relative to its full frame), so the overlay lives there. */
const displayNow = (): Electron.Display => screen.getPrimaryDisplay()

// ---------------------------------------------------------------------------
// Security core (W0-6, BUILD-PLAN Section 6)
// ---------------------------------------------------------------------------

/** Where our own pages come from: Vite in dev, main/serve.ts when built (file:// only as the last resort). */
function ownOrigin(url: string): boolean {
  try {
    const u = new URL(url)
    if (process.env.ELECTRON_RENDERER_URL) return u.origin === new URL(process.env.ELECTRON_RENDERER_URL).origin
    if (rendererOrigin) return u.origin === rendererOrigin
    return u.protocol === 'file:'
  } catch {
    return false
  }
}

/**
 * An IPC sender we trust: one of OUR windows, its main frame (never an iframe such as the YouTube embed), showing our
 * own page. Every ipcMain handler in core and ctx.handle checks it.
 */
function trustedSender(e: IpcMainEvent | IpcMainInvokeEvent): boolean {
  const frame = e.senderFrame
  if (!frame || frame !== e.sender.mainFrame) return false
  const win = BrowserWindow.fromWebContents(e.sender)
  if (!win || !windows.has(win)) return false
  return ownOrigin(frame.url)
}

/**
 * Commands a renderer may send to the engine (engine:cmd). config.keys is NOT here: keys go only through the settings
 * feature in main (settings:save), so a renderer can never set or overwrite them. dev.reset only outside a built app.
 */
const RENDERER_COMMANDS = new Set<string>([
  'learn',
  'learn_url',
  'build_lesson',
  'action',
  'video.state',
  'end_lesson',
  'overlay.bounds',
  'card.shown',
  'card.closed',
  ...V2_COMMANDS
])

/**
 * Microphone only, for voice, only for our own page. Everything else a page can ask for is refused.
 * Voice is off for now (common/flags): then the microphone is refused too, so the app never asks for it.
 */
function hardenSession(): void {
  const s = session.defaultSession
  s.setPermissionRequestHandler((wc, permission, cb, details) => {
    const media = details as { mediaTypes?: string[]; requestingUrl?: string }
    const micOnly = permission === 'media' && !!media.mediaTypes?.length && media.mediaTypes.every((t) => t === 'audio')
    cb(VOICE_ENABLED && micOnly && ownOrigin(media.requestingUrl ?? wc.getURL()))
  })
  s.setPermissionCheckHandler((_wc, permission, origin, details) => {
    const media = details as { mediaType?: string }
    return VOICE_ENABLED && permission === 'media' && media.mediaType === 'audio' && ownOrigin(origin)
  })
}

/** Every web contents (windows, and any iframe's host): no navigating away from our page, no new windows. */
function hardenContents(wc: WebContents): void {
  const block = (e: Electron.Event, url: string): void => {
    if (!ownOrigin(url)) e.preventDefault()
  }
  wc.on('will-navigate', block)
  wc.on('will-redirect', (e, url, _inPlace, isMainFrame) => {
    if (isMainFrame) block(e, url)
  })
  wc.on('will-attach-webview', (e) => e.preventDefault())
  // window.open / target=_blank: never a new Electron window; any plain https link (setup downloads, citations,
  // drawer sources) goes to the default browser. Other schemes are refused (safeOpen.isBrowserLink).
  wc.setWindowOpenHandler(({ url }) => {
    void openLinkInBrowser(url)
    return { action: 'deny' }
  })
}

/** v2 (W0-4): open / focus allowlisted app windows. Set up once the app is ready. */
let appWindows: AppWindows | undefined

function createWindow(route: string, options: BrowserWindowConstructorOptions, kind: 'overlay' | 'app' = 'overlay'): BrowserWindow {
  const win = new BrowserWindow({
    show: false,
    // A panel on macOS, like the core windows, so it can sit over full-screen apps. App windows (v2) are normal windows.
    ...(platform.os === 'mac' && kind === 'overlay' ? { type: 'panel' } : {}),
    ...options,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
      contextIsolation: true,
      backgroundThrottling: false,
      additionalArguments: [`--tut-platform=${encodeURIComponent(JSON.stringify(platform))}`],
      ...options.webPreferences,
      // Last, so no caller (player, settings, app windows) can turn it back on: no DevTools in a built app (app-harden).
      devTools: !app.isPackaged
    }
  })
  windows.add(win)
  win.on('closed', () => windows.delete(win))
  if (kind === 'app') {
    win.setBackgroundColor(windowBackground())
    trackWindowBackground(win)
  }
  showAfterFirstPaint(win)
  // Every overlay window follows the learner across Spaces and over full-screen apps (Michael, Sat). App windows
  // (v2) stay on their own Space like any Mac window.
  if (kind === 'overlay') followSpaces(win)
  // No navigation away, no new windows (W0-6): hardenContents runs for every web contents on creation.
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
  const display = screen.getDisplayMatching(b)
  const wa = display.workArea
  const notch = notchService?.layoutFor(display, getPrefs().island.place) ?? { ...notchFor(display), place: 'below' as const, boringNotch: false }
  return { notch, origin: { x: b.x, y: b.y }, width: b.width, height: b.height, pillTop: platform.pillTop, workArea: { x: wa.x - b.x, y: wa.y - b.y, width: wa.width, height: wa.height } }
}

function send(win: BrowserWindow | undefined, signal: UiSignal, payload?: unknown): void {
  if (win && !win.isDestroyed()) win.webContents.send(`ui:${signal}`, payload)
}

function forEachWindow(fn: (w: BrowserWindow) => void): void {
  for (const w of windows) if (!w.isDestroyed()) fn(w)
}

function openLauncher(): void {
  // Launch gate (main/gate.ts): no launcher before the login and setup are through.
  if (launcherOpen || !gateIsOpen()) return
  const front = BrowserWindow.getFocusedWindow()
  launcherOrigin = front && front !== overlay && front !== launcher && !front.isDestroyed() ? front : undefined
  launcherOpen = true
  launcherGen++
  launcherOpenedAt = Date.now()
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
  if (!launcherOpen) return
  send(launcher, 'launcher:close') // renderer animates out, then emits launcher:hidden
  // Watchdog: the launcher renderer is hung or gone and never says launcher:hidden: the island must not stay invisible.
  // (Only if it is still the same open: a quick reopen has a newer generation.)
  const gen = ++launcherGen
  setTimeout(() => {
    if (launcherOpen && gen === launcherGen && !launcher.isDestroyed()) hideLauncher()
  }, 2500)
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
  const origin = launcherOrigin
  launcherOrigin = undefined
  if (origin && !origin.isDestroyed() && origin.isVisible()) {
    // Opened from a miyagi window: it gets the keyboard back. returnFocus would reactivate "the last other app" (Finder).
    overlay.showInactive()
    raise(overlay)
    if (process.platform === 'darwin') app.focus({ steal: true })
    origin.focus()
    return
  }
  returnFocus(app, overlay, previousApp())
}

// Voice is off for now (common/flags): its key is never registered, so ⌃⌥V stays with the other apps.
const ACTION_KINDS: Exclude<ShortcutKind, 'launcher'>[] = (['back', 'explain', 'diagram', 'show_me', 'hint', 'voice_toggle'] as const).filter(
  (k) => VOICE_ENABLED || k !== 'voice_toggle'
)

/** Global action shortcuts go to the overlay renderer, which decides (features may claim them) and tells the engine. */
function registerActionShortcuts(): void {
  if (actionsRegistered || !gateIsOpen()) return
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
function sendBoundsNow(): void {
  const extra = [...reported]
    .filter((w) => !w.isDestroyed() && w.isVisible())
    .map((w) => {
      const b = w.getBounds()
      return { x: b.x, y: b.y, w: b.width, h: b.height }
    })
  engine.send({ type: 'overlay.bounds', payload: { rects: [...overlayRects, ...extra] } })
}

/** Window move/resize fire per frame while dragging; the engine only needs the last one (50 ms trailing). */
const boundsOut = coalesce<void>(sendBoundsNow, 50)
function sendBounds(): void {
  boundsOut.push()
}
/** A window hid or closed: the OCR mask must shrink now, not up to 50 ms later. */
function sendBoundsFlushed(): void {
  boundsOut.push()
  boundsOut.flush()
}

function reportBounds(win: BrowserWindow): void {
  reported.add(win)
  for (const ev of ['move', 'resize', 'show'] as const) win.on(ev as 'move', sendBounds)
  win.on('hide', sendBoundsFlushed)
  win.on('closed', () => {
    reported.delete(win)
    sendBoundsFlushed()
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

app.on('web-contents-created', (_e, wc) => hardenContents(wc))

app.whenReady().then(async () => {
  setupApp(app)
  setupIdentity()
  hardenSession()
  youtubeReferer()
  if (!process.env.ELECTRON_RENDERER_URL) {
    try {
      rendererOrigin = await serveRenderer(join(__dirname, '../renderer'))
    } catch (err) {
      console.error('[tut] could not serve the renderer over http, falling back to file:// (YouTube may refuse embeds)', err)
    }
  }
  // Launch-ease lane: the pill sits under the menu bar / notch band, never on it (platform.ts fitPillTop). Before any
  // window exists: every renderer gets pillTop in its launch arguments.
  basePillTop = platform.pillTop
  platform.pillTop = fitPillTop(basePillTop, displayNow())
  // The notch geometry (miyagi-listen --screens) and Boring Notch detection; a change re-sends the layout to every core window.
  notchService = startNotch({ helperBin: helperPath(), mac: platform.os === 'mac', onChange: () => resendLayout() })
  overlay = createCoreWindow('overlay')
  launcher = createCoreWindow('launcher')

  overlay.setIgnoreMouseEvents(true, { forward: true })
  // Launch gate (main/gate.ts, Michael Nov 21: launch = start from new): the overlay shows and the launcher key
  // registers only once the login and setup are through, and both go away on a sign-out. Until then only the home
  // window (its first-run flow) is on screen. showInactive before the first paint is held (showAfterFirstPaint).
  gateCore({
    overlay,
    launcherKey: (on) => {
      if (!on) return globalShortcut.unregister(platform.accelerators.launcher)
      const ok = globalShortcut.register(platform.accelerators.launcher, () => {
        if (!launcherOpen) return openLauncher()
        if (Date.now() - launcherOpenedAt >= LAUNCHER_DOUBLE_MS) closeLauncher() // a second press right after an open is ignored
      })
      if (!ok) console.warn(`[tut] launcher shortcut ${platform.accelerators.launcher} is taken`)
    },
    closed: () => {
      if (launcherOpen) closeLauncher()
      unregisterActionShortcuts()
    }
  })
  launcher.on('blur', onLauncherBlur)
  launcher.webContents.on('before-input-event', (_e, input) => (launcherModifier = isLeavingModifier(input)))

  engine.onEvent((e) => {
    forEachWindow((w) => w.webContents.send('engine:event', e))
    if (e.type === 'lesson.ready' && gateIsOpen()) registerActionShortcuts()
    if (e.type === 'lesson.ended') unregisterActionShortcuts()
  })
  engine.onStatus((c) => forEachWindow((w) => w.webContents.send('engine:status', c)))

  ipcMain.on('engine:cmd', (e, cmd) => {
    // W0-6: only our own windows' main frames, only allowlisted command types, never config.keys from a renderer.
    if (!trustedSender(e) || !cmd || typeof cmd !== 'object' || typeof cmd.type !== 'string') return
    const devReset = cmd.type === 'dev.reset' && !app.isPackaged
    if (!RENDERER_COMMANDS.has(cmd.type) && !devReset) {
      if (cmd.type === 'config.keys') console.warn('[tut] dropped config.keys sent by a renderer (keys go through settings:save)')
      return
    }
    if (cmd.payload !== undefined && (typeof cmd.payload !== 'object' || cmd.payload === null)) return
    if (cmd.type === 'overlay.bounds') {
      const rects: unknown = cmd.payload?.rects
      overlayRects = Array.isArray(rects)
        ? rects
            .slice(0, 64)
            .filter((r): r is R => !!r && ['x', 'y', 'w', 'h'].every((k) => Number.isFinite((r as Record<string, unknown>)[k])))
            .map((r) => ({ x: r.x, y: r.y, w: r.w, h: r.h }))
        : []
      return sendBounds()
    }
    engine.send(cmd)
  })

  ipcMain.on('ui:ready', (e) => {
    if (!trustedSender(e)) return
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
    if (!trustedSender(e) || typeof signal !== 'string') return
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
        // The pill can't open the launcher while the gate is closed (closing one that is open is always fine).
        if (launcherOpen) closeLauncher()
        else if (gateIsOpen()) openLauncher()
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

  // The launcher key follows the gate (gateCore above). A second launch opens home: features/launch.ts owns
  // 'second-instance' (it used to open the launcher here too, over a closed gate).

  // Always-available kill switch: ⌃⌥Q (Mac; ⌥Q alone types "œ" in editors) / Alt+Q (Windows) quits the overlay.
  const quitKey = platform.os === 'mac' ? 'Control+Alt+Q' : 'Alt+Q'
  if (!globalShortcut.register(quitKey, () => app.quit())) console.warn(`[tut] quit shortcut ${quitKey} is taken`)

  // Engine link health: after sleep, unlock or a network change the socket may be half open. Ping it (drop + redial
  // when nothing answers) instead of showing a healthy pill that is deaf.
  const wake = (): void => engine.wake()
  // Displays change (plugged, unplugged, resolution, the menu bar's band, a new primary): the two core windows follow the
  // PRIMARY display (the one the engine watches), the pill is re-fitted under its menu bar / notch band and centered on
  // it, and the windows are raised again (a display change drops them below other panels). Debounced: a plug fires several.
  onPrefsChange(() => resendLayout())
  let refitTimer: ReturnType<typeof setTimeout> | undefined
  const refit = (): void => {
    clearTimeout(refitTimer)
    notchService?.refresh()
    refitTimer = setTimeout(() => {
      platform.pillTop = fitPillTop(basePillTop, displayNow())
      for (const w of [overlay, launcher]) {
        if (w.isDestroyed()) continue
        w.setBounds(overlayBounds(displayNow()))
        raise(w)
        send(w, 'layout', layoutFor(w))
      }
    }, 150)
  }
  // Every way the island can be left half-open by the system: collapse it to rest (core/Island.tsx collapseAll).
  const collapseIsland = (): void => send(overlay, 'island:collapse')
  overlay.webContents.on('responsive', collapseIsland)
  screen.on('display-metrics-changed', () => {
    collapseIsland()
    refit()
  })
  screen.on('display-added', () => {
    collapseIsland()
    refit()
  })
  screen.on('display-removed', () => {
    collapseIsland()
    refit()
  })
  // Wake and unlock: macOS can drop the panels' level and the renderer's frames; re-raise and re-send the layout.
  powerMonitor.on('resume', () => {
    collapseIsland()
    refit()
    wake()
  })
  powerMonitor.on('unlock-screen', () => {
    collapseIsland()
    refit()
    wake()
  })
  let wasOnline = net.isOnline()
  const netTimer = setInterval(() => {
    const on = net.isOnline()
    if (on && !wasOnline) wake()
    wasOnline = on
  }, 3000)
  netTimer.unref()

  setupPrefs((channel, payload) => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload)), trustedSender)
  // One download: a built app on a Mac starts (and first installs) the engine itself. See main/localEngine.ts.
  // Never let the engine's start-up stop the rest of the app (Home, setup, the features below): log it and carry on.
  try {
    stopLocalEngine = setupLocalEngine(engine, ENGINE_URL, (channel, payload) => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload)), trustedSender)
  } catch (err) {
    console.error('[tut] engine start-up threw', err)
  }

  // v2 (W0-4 / W0-5 / W0-6): app windows, permission probes, the one way out to a browser.
  const broadcastAll = (channel: string, payload: unknown): void => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload))
  appWindows = setupAppWindows({ app, create: (route, options) => createWindow(route, options, 'app'), trusted: trustedSender })
  setupPermissions({ engineExternal: () => localEngineState() === 'external', broadcast: broadcastAll, trusted: trustedSender })
  ipcMain.handle('feat:open:external', (e, url: unknown) => (trustedSender(e) ? safeOpenExternal(url) : false))

  loadFeatures({
    app,
    platform,
    engine,
    overlay,
    launcher,
    display: () => screen.getDisplayMatching(overlay.getBounds()),
    createWindow,
    overlayOptions: overlayWindowOptions,
    // W0-6: a feature handler only ever runs for our own windows' main frames.
    handle: (channel, fn) =>
      ipcMain.handle(`feat:${channel}`, (e, ...args) => {
        if (!trustedSender(e)) throw new Error('untrusted sender')
        return fn(...args)
      }),
    broadcast: (channel, payload) => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload)),
    onSignal: (signal, fn) => {
      if (!signalListeners.has(signal)) signalListeners.set(signal, new Set())
      signalListeners.get(signal)!.add(fn)
    },
    reportBounds,
    raise,
    islandSize: () => islandSize,
    yieldIsland: (on) => send(overlay, on ? 'island:yield' : 'island:return'),
    overlayRects: () => overlayRects,
    openWindow: (route, args) => appWindows?.open(route, args),
    appWindow: (route) => appWindows?.get(route)
  })
  setupMenu()
})

/**
 * The standard macOS app menu (Nov 21: the test found only "Edit"): miyagi, Edit, View (Enter Full Screen), Window
 * (Minimize, Zoom). The only menu definition (overlay-raise.ts no longer sets one), set once after the features load. Full screen
 * and zoom act on the focused window; only app windows are fullscreenable (platform.ts appWindowOptions), so for the
 * overlay, pill and panels those items stay disabled by Electron.
 */
function setupMenu(): void {
  // Windows / Linux: no menu at all. Electron's default one carries Reload (Ctrl+R), Force Reload and Toggle Developer
  // Tools (Ctrl+Shift+I) as accelerators even in a built app (app-harden). Copy and paste work without a menu there.
  if (platform.os !== 'mac') return Menu.setApplicationMenu(null)
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      { label: 'miyagi', submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' }, { type: 'separator' }, { role: 'quit' }] },
      { role: 'editMenu' },
      { label: 'View', submenu: [{ role: 'togglefullscreen' }] },
      { label: 'Window', role: 'windowMenu', submenu: [{ role: 'minimize' }, { role: 'zoom' }, { type: 'separator' }, { role: 'front' }] }
    ])
  )
}

app.on('before-quit', () => boundsOut.flush())
app.on('will-quit', () => {
  globalShortcut.unregisterAll()
  stopLocalEngine()
})
app.on('window-all-closed', () => app.quit())
