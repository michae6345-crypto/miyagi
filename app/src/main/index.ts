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
import { app, BrowserWindow, globalShortcut, ipcMain, Menu, net, powerMonitor, screen, session, systemPreferences, type BrowserWindowConstructorOptions, type IpcMainEvent, type IpcMainInvokeEvent, type WebContents } from 'electron'
import { appendFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { V2_COMMANDS } from '../common/wire'
import { setupIdentity } from './identity'
import { EngineLink } from './engine'
import { setShortcutCheck, setupPrefs, trackWindowBackground, windowBackground } from './prefs'
import { createShortcutKeys } from './shortcutKeys'
import { quitAccelerator, SHORTCUT_KINDS } from '../common/shortcuts'
import { ENGINE_TOKEN, localEngineState, QUIT_CONFIRM_MS, QUIT_GRACE_MS, setupLocalEngine } from './localEngine'
import { serveRenderer } from './serve'
import { servePlayerHost } from './playerHost'
import playerHostScript from './playerHost.page.js?raw'
import { appWindowFrame, setupAppWindows, type AppWindows } from './appWindows'
import { setupPermissions } from './permissions'
import { debugFlagIn, openLinkInBrowser, safeOpenExternal } from './safeOpen'
import { previousApp } from './features/front-app'
import { gateCore, gateIsOpen } from './gate'
import { coalesce } from './coalesce'
import type { MainContext, MainFeature } from './context'
import { overlaysHidden } from './overlayHide'
import {
  describePlatform,
  focusPanel,
  pillTopOverride,
  followSpaces,
  isLeavingModifier,
  launcherGlassOptions,
  overlayBounds,
  overlayWindowOptions,
  raise,
  returnFocus,
  setupApp,
  OVERLAY_RESTORE_MS,
  trackOverlayLifecycle,
  type ShortcutKind
} from './platform'
import type { Layout, UiSignal } from '../preload/api'
import { VOICE_ENABLED } from '../common/flags'
import { belowTop, notchFor, recheckThenResend, startNotch, type NotchService } from './notch'
import { appendRotating, createIslandDiag, type IslandDiag } from './features/islandDiag'
import { helperPath } from './features/ptt'
import { getPrefs, onPrefsChange } from './prefs'
import { holdSplash, holdUntilPainted, showSplash, skipSplash } from './splash'

// A built app never starts under a debugger (app-harden): --inspect*, --remote-debugging-* or --js-flags in argv quits
// here, the first statement of this file's own body. The imported modules' top-level code has run by then (ES imports
// are hoisted: localEngine makes its ENGINE_TOKEN, for one), but nothing that waits for app 'ready' has: no window and
// no engine process yet. The fuses already make Node ignore --inspect; Chromium's remote debugging has no fuse. Dev
// runs (npm run dev) keep them.
if (app.isPackaged) {
  const flag = debugFlagIn(process.argv)
  if (flag) {
    console.error(`[tut] a packaged miyagi does not start with --${flag}; quitting`)
    app.exit(1)
    process.exit(1)
  }
}

const platform = describePlatform(process.platform)
// A packaged app always talks to its own engine on localhost: ENGINE_URL from the environment is for dev runs only
// (risk A12, launch register R33: a `launchctl setenv` could otherwise point the app at another engine).
const ENGINE_URL = (!app.isPackaged && process.env.ENGINE_URL) || 'ws://localhost:8787'
// The token goes in with the constructor: the first connect starts there, before setupLocalEngine runs.
const engine = new EngineLink(ENGINE_URL, process.env.DEMO === '1' ? (process.env.SCENARIO ?? 'full') : undefined, ENGINE_TOKEN)
let stopLocalEngine: () => Promise<void> | void = () => undefined
/** R44: the most a quit waits for the engine to go (SIGTERM, QUIT_GRACE_MS, SIGKILL, QUIT_CONFIRM_MS), plus a margin. */
const QUIT_ENGINE_DEADLINE_MS = QUIT_GRACE_MS + QUIT_CONFIRM_MS + 1000
/** Notch geometry and the other-notch-app flag (main/notch.ts); started at launch. */
let notchService: NotchService | undefined
/** Every window gets its layout again (Settings > General shows where the island is). Module level: the first notch read can land before whenReady has finished. */
const resendLayout = (): void => {
  // A helper read can change the band (a notch whose menu bar hides itself): the pill's top follows the overlay's display.
  if (overlay && !overlay.isDestroyed()) platform.pillTop = belowTopNow(screen.getDisplayMatching(overlay.getBounds()))
  forEachWindow((w) => {
    const l = layoutFor(w)
    if (w === overlay) {
      logIsland('resend', l)
      islandDiag?.snapshot('resend')
    }
    send(w, 'layout', l)
  })
}
/** Island diagnostics (main/features/islandDiag.ts): bounds, level, grab and display measurements, log-only. Created once the overlay exists. */
let islandDiag: IslandDiag | undefined
/** ~/Library/Logs/miyagi/island.log: where main told the overlay the island lives, and why (a packaged app has no console). Rotates at ~512 KB. */
let lastIslandLine = ''
function logIsland(why: string, l: ReturnType<typeof layoutFor>): void {
  const n = l.notch
  const line = `pref=${getPrefs().island?.place} place=${n.place} hasNotch=${n.hasNotch} coexist=${n.coexist ? 1 : 0} notch=${n.x},${n.width}x${n.height} service=${notchService ? 'on' : 'off'}`
  if (line === lastIslandLine && why === 'resend') return
  lastIslandLine = line
  appendRotating(join(app.getPath('logs'), 'island.log'), `${new Date().toISOString()} ${why} ${line}`)
}

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
/**
 * The island's top below the menu bar for a display (common/notch.ts belowTop via the notch service): flush with the
 * menu bar's bottom edge on a Mac, MIYAGI_PILL_TOP when set. Without the service (or before the helper answers) it is
 * the same rule from the work area alone, so a missing or slow helper still gives a top-anchored island.
 */
function belowTopNow(display: Electron.Display): number {
  const override = pillTopOverride()
  // The primary display always has a menu bar (shown or hiding itself). A second display with no band may have none at
  // all ("Displays have separate Spaces" off): it gets the very top.
  const menuBar = display.id === screen.getPrimaryDisplay().id || display.workArea.y > display.bounds.y
  return notchService?.belowTopFor(display, override, menuBar) ?? belowTop(display, { mac: platform.os === 'mac', override, menuBar })
}
/** The island's latest size, so the launcher can grow out of its exact shape (dx/dy: a card moved off the spotlight). */
let islandSize: { w: number; h: number; dx?: number; dy?: number; shown?: boolean; top?: number; place?: 'notch'; radii?: { top: number; bottom: number } } = { w: 300, h: 34 }
/** Built app: where main/serve.ts serves the renderer (set before any window is created). */
let rendererOrigin: string | undefined
let actionsRegistered = false
/** The launcher's key follows the gate (gateCore's launcherKey): true only between its on and off. */
let launcherWanted = false

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
      backgroundThrottling: false,
      additionalArguments: [`--tut-platform=${encodeURIComponent(JSON.stringify(platform))}`],
      ...options.webPreferences,
      // Last, so no caller (player, settings, app windows) can turn them off: sandboxed, isolated, no Node in any frame,
      // no <webview>, and no DevTools in a built app (app-harden). The player relies on these for the video's frames (R33).
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      nodeIntegrationInSubFrames: false,
      nodeIntegrationInWorker: false,
      webviewTag: false,
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
  const notch = notchService?.layoutFor(display, getPrefs().island.place) ?? { ...notchFor(display), place: 'below' as const, coexist: false }
  return { notch, origin: { x: b.x, y: b.y }, width: b.width, height: b.height, pillTop: platform.pillTop, displayId: display.id, scaleFactor: display.scaleFactor, workArea: { x: wa.x - b.x, y: wa.y - b.y, width: wa.width, height: wa.height } }
}

/**
 * A leased overlay:interactive ({on: true, leaseMs}, circle to ask): the grab lasts only while the renderer keeps saying
 * it. Not said again within leaseMs (a hung renderer) and main gives the mouse back itself. A plain true (core hover)
 * leaves a running lease alone; false ends it.
 */
let lease: ReturnType<typeof setTimeout> | undefined
function leaseInteractive(payload: unknown): void {
  const ms = payload && typeof payload === 'object' ? Number((payload as { leaseMs?: unknown }).leaseMs) : NaN
  if (payload && !(ms > 0)) return
  clearTimeout(lease)
  lease = undefined
  if (!payload) return
  lease = setTimeout(() => {
    lease = undefined
    if (overlay.isDestroyed()) return
    overlay.setIgnoreMouseEvents(true, { forward: true })
    signalListeners.get('overlay:interactive')?.forEach((fn) => fn(false))
  }, Math.min(5000, Math.max(250, ms)))
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
  // Key without activating miyagi (platform.ts focusPanel). The old fallback's app.focus({steal: true}) activated the
  // app, and over a full-screen VS Code macOS then switched Spaces to miyagi's home window (user report, main 1d453ca0).
  focusPanel(launcher)
  raise(launcher)
  // Michael's test 10: with Finder in front the panel showed but the keystrokes kept going there. If the launcher still
  // isn't key a moment later, ask again, still as a panel (never app.focus({steal}): that is the Space switch above).
  if (process.platform === 'darwin') {
    for (const ms of [60, 200]) {
      setTimeout(() => {
        if (!launcherOpen || launcher.isDestroyed() || launcher.isFocused()) return
        launcher.focus()
      }, ms)
    }
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
    // The overlay comes back only behind the gate (a sign-out while the launcher was open keeps it hidden).
    if (gateIsOpen()) {
      overlay.showInactive()
      raise(overlay)
    }
    if (process.platform === 'darwin') app.focus({ steal: true })
    origin.focus()
    return
  }
  returnFocus(app, overlay, previousApp())
}

/** The launcher key: open, or close unless this press comes right after the open. */
function onLauncherKey(): void {
  if (!launcherOpen) return openLauncher()
  if (Date.now() - launcherOpenedAt >= LAUNCHER_DOUBLE_MS) closeLauncher() // a second press right after an open is ignored
}

/**
 * Whether a shortcut is registered right now. The launcher only while the login gate is open (main/gate.ts); the lesson
 * keys only while a lesson is active (lesson.ready to lesson.ended), also behind the gate; voice's key never while voice
 * is off (common/flags), so ⌃⌥V stays with the other apps. loginFirst.check.ts holds this function to the gate.
 */
function shortcutLive(kind: ShortcutKind): boolean {
  if (!gateIsOpen()) return false
  if (kind === 'launcher') return launcherWanted
  if (kind === 'voice_toggle' && !VOICE_ENABLED) return false
  return actionsRegistered
}

/**
 * Live custom shortcuts (main/shortcutKeys.ts): the key in effect is prefs.shortcuts[kind] ?? platform.accelerators[kind].
 * Every global registration of the launcher and lesson keys goes through here; sync() follows shortcutLive and the prefs.
 * Action keys go to the overlay renderer, which decides (features may claim them) and tells the engine.
 */
const shortcutKeys = createShortcutKeys({
  ops: { register: (acc, fn) => globalShortcut.register(acc, fn), unregister: (acc) => globalShortcut.unregister(acc) },
  defaults: platform.accelerators,
  mac: platform.os === 'mac',
  kinds: SHORTCUT_KINDS.filter((k) => VOICE_ENABLED || k !== 'voice_toggle'),
  overrides: () => getPrefs().shortcuts,
  live: shortcutLive,
  press: (kind) => (kind === 'launcher' ? onLauncherKey() : send(overlay, 'shortcut', kind)),
  // A saved key another app owns fell back to the default (or to none): every keycap shows the key really bound.
  onTaken: (taken) => forEachWindow((w) => w.webContents.send('feat:shortcuts:taken', taken)),
  warn: (m) => console.warn(`[tut] ${m}`)
})

/** A lesson is ready: the lesson keys reach miyagi from any app. */
function registerActionShortcuts(): void {
  if (actionsRegistered || !gateIsOpen()) return
  actionsRegistered = true
  shortcutKeys.sync()
}

/** A lesson ended: hand the lesson keys back to the other apps until the next lesson.ready (Michael, Sun 12:49 AM). */
function unregisterActionShortcuts(): void {
  if (!actionsRegistered) return
  actionsRegistered = false
  shortcutKeys.sync()
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
  // R33: the YouTube player's host page, on its own loopback origin, before any window (main/serve.ts's CSP frames it).
  const appOrigin = process.env.ELECTRON_RENDERER_URL ? new URL(process.env.ELECTRON_RENDERER_URL).origin : rendererOrigin
  if (appOrigin) {
    try {
      await servePlayerHost(playerHostScript, appOrigin)
    } catch (err) {
      console.error('[tut] could not serve the player host page; the video will not load', err)
    }
  }
  // The notch geometry (miyagi-listen --screens, persisted last-good in userData) and the other-notch-app flag; a change re-sends the layout to every core window.
  notchService = startNotch({ helperBin: helperPath(), mac: platform.os === 'mac', cacheFile: join(app.getPath('userData'), 'notch-cache.json'), onChange: () => resendLayout() })
  // Launch-ease lane: the pill sits under the menu bar / notch band, never on it, and never floats below it (belowTopNow).
  // Before any window exists: every renderer gets pillTop in its launch arguments. The cache is already loaded, the
  // helper not needed.
  platform.pillTop = belowTopNow(displayNow())
  overlay = createCoreWindow('overlay')
  launcher = createCoreWindow('launcher')
  // The launch splash (main/splash.ts) waits for the renderer bundle's first load and, briefly, the engine link.
  holdSplash(new Promise((res) => overlay.webContents.once('did-finish-load', () => res(undefined))))
  holdSplash(new Promise((res) => engine.onOpen(() => res(undefined))), ENGINE_SPLASH_MS)
  islandDiag = createIslandDiag({
    logFile: join(app.getPath('logs'), 'island.log'),
    overlay: () => overlay,
    display: () => {
      const d = screen.getDisplayMatching(overlay.getBounds())
      return { id: d.id, bounds: d.bounds, workArea: d.workArea, scaleFactor: d.scaleFactor }
    },
    notch: () => layoutFor(overlay).notch as { place: string; hasNotch?: boolean; coexist?: boolean },
    islandSize: () => islandSize,
    pillTop: () => platform.pillTop,
    cursor: () => screen.getCursorScreenPoint(),
    helperBin: helperPath(),
    mac: platform.os === 'mac',
    pid: process.pid
  })
  islandDiag.start()
  ipcMain.handle('feat:island:diag', (e, report: unknown) => {
    if (trustedSender(e)) islandDiag?.onRenderer(report)
  })

  overlay.setIgnoreMouseEvents(true, { forward: true })
  // Launch gate (main/gate.ts, Michael Nov 21: launch = start from new): the overlay shows and the launcher key
  // registers only once the login and setup are through, and both go away on a sign-out. Until then only the home
  // window (its first-run flow) is on screen. showInactive before the first paint is held (showAfterFirstPaint).
  gateCore({
    overlay,
    // The launcher key (the learner's own or the default) registers through shortcutKeys, which also checks the gate.
    launcherKey: (on) => {
      launcherWanted = on
      shortcutKeys.sync()
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
    const l = layoutFor(win)
    if (win === overlay) {
      logIsland('ready', l)
      islandDiag?.snapshot('ready')
    }
    e.sender.send('ui:layout', l)
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
        // "Hide miyagi overlays" (overlayHide.ts): nothing drawn, so nothing may take the mouse.
        overlay.setIgnoreMouseEvents(!payload || overlaysHidden(), { forward: true })
        leaseInteractive(payload)
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
  const quitKey = quitAccelerator(platform.os === 'mac')
  if (!globalShortcut.register(quitKey, () => app.quit())) console.warn(`[tut] quit shortcut ${quitKey} is taken`)

  // Engine link health: after sleep, unlock or a network change the socket may be half open. Ping it (drop + redial
  // when nothing answers) instead of showing a healthy pill that is deaf.
  const wake = (): void => engine.wake()
  // Displays change (plugged, unplugged, resolution, the menu bar's band, a new primary): the two core windows follow the
  // PRIMARY display (the one the engine watches), the pill is re-fitted under its menu bar / notch band and centered on
  // it, and the windows are raised again (a display change drops them below other panels). Debounced: a plug fires several.
  // Choosing "In the notch" must act now: read the geometry afresh, then resend the layout whatever the answer, so the
  // island moves at once without waiting for a poll.
  onPrefsChange(() => void recheckThenResend(notchService, resendLayout))
  ipcMain.handle('feat:notch:recheck', async (e) => {
    if (!trustedSender(e)) return false
    await notchService?.recheck()
    return true
  })
  // Back from another app: look again (rate limited in the service).
  app.on('browser-window-focus', () => void notchService?.recheck())
  app.on('activate', () => void notchService?.recheck())
  /** Re-apply the display's bounds and the pill's fitted top to both core windows, raise them, send the layout. */
  const applyDisplay = (): void => {
    islandDiag?.snapshot('refit')
    platform.pillTop = belowTopNow(displayNow())
    for (const w of [overlay, launcher]) {
      if (w.isDestroyed()) continue
      w.setBounds(overlayBounds(displayNow()))
      raise(w)
      send(w, 'layout', layoutFor(w))
    }
  }
  // Every way the island can be left half-open by the system: collapse it to rest (core/Island.tsx collapseAll).
  const collapseIsland = (): void => send(overlay, 'island:collapse')
  overlay.webContents.on('responsive', collapseIsland)
  // The overlay itself: hidden while displays swap and while locked, shown again ~150 ms later, re-raised on a space
  // change (platform.ts trackOverlayLifecycle). Its refit is applyDisplay.
  const stopLifecycle = trackOverlayLifecycle(overlay, { screen, powerMonitor, systemPreferences, canShow: gateIsOpen }, applyDisplay)
  app.on('before-quit', stopLifecycle)
  // Display events, wake and unlock: collapse the island and ask for one geometry read (the service debounces it
  // 250 ms, so a burst of display events is one helper call); a changed answer re-sends the layout through onChange.
  let refitTimer: ReturnType<typeof setTimeout> | undefined
  const displayChanged = (): void => {
    islandDiag?.snapshot('display')
    void islandDiag?.refreshScreens('display')
    collapseIsland()
    notchService?.refresh()
    // Off macOS there is no lifecycle tracker: re-fit the windows here (debounced, a plug fires several events).
    if (platform.os !== 'mac') {
      clearTimeout(refitTimer)
      refitTimer = setTimeout(applyDisplay, OVERLAY_RESTORE_MS)
    }
  }
  screen.on('display-metrics-changed', displayChanged)
  screen.on('display-added', displayChanged)
  screen.on('display-removed', displayChanged)
  // Wake: macOS can drop the panels' level and the renderer's frames; re-fit, re-raise, re-send the layout.
  powerMonitor.on('resume', () => {
    void islandDiag?.dumpWindows('resume')
    displayChanged()
    setTimeout(applyDisplay, OVERLAY_RESTORE_MS)
    wake()
  })
  // Unlock: the lifecycle shows the overlay again; here the island collapses and the link is checked.
  powerMonitor.on('unlock-screen', () => {
    void islandDiag?.dumpWindows('unlock')
    displayChanged()
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
  // Live custom shortcuts: main checks a new key before it is saved (taken by another app: the old key stays, the
  // prefs:set result says so), and every change of the prefs re-registers what is live. Once now for the saved keys.
  setShortcutCheck((next, prev) => {
    const { accepted, refused } = shortcutKeys.accept(next, prev)
    for (const r of refused) console.warn(`[tut] shortcut ${r.accelerator} for ${r.kind} refused (${r.reason})`)
    return accepted
  })
  onPrefsChange(() => void shortcutKeys.sync())
  // Which saved keys fell back (another app owns them), for a window that opens after the broadcast (core/keys.ts).
  ipcMain.handle('feat:shortcuts:taken', (e) => (trustedSender(e) ? shortcutKeys.taken() : undefined))
  shortcutKeys.sync()
  // One download: a built app on a Mac starts (and first installs) the engine itself. See main/localEngine.ts.
  // Never let the engine's start-up stop the rest of the app (Home, setup, the features below): log it and carry on.
  try {
    stopLocalEngine = setupLocalEngine(engine, ENGINE_URL, (channel, payload) => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload)), trustedSender)
  } catch (err) {
    console.error('[tut] engine start-up threw', err)
  }

  // v2 (W0-4 / W0-5 / W0-6): app windows, permission probes, the one way out to a browser.
  const broadcastAll = (channel: string, payload: unknown): void => forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload))
  appWindows = setupAppWindows({
    app,
    create: (route, options) => {
      const win = createWindow(route, options, 'app')
      holdUntilPainted(win) // the splash leaves onto a painted home window (a no-op once the splash is gone)
      return win
    },
    trusted: trustedSender
  })
  setupPermissions({ engineExternal: () => localEngineState() === 'external', broadcast: broadcastAll, trusted: trustedSender, helperBin: helperPath })
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
        islandDiag?.onFeature(channel, args[0])
        return fn(...args)
      }),
    broadcast: (channel, payload) => {
      islandDiag?.onFeature(channel, payload)
      forEachWindow((w) => w.webContents.send(`feat:${channel}`, payload))
    },
    onSignal: (signal, fn) => {
      if (!signalListeners.has(signal)) signalListeners.set(signal, new Set())
      signalListeners.get(signal)!.add(fn)
    },
    reportBounds,
    raise: (w, rel) => {
      raise(w, rel)
      islandDiag?.snapshot('raise')
    },
    islandSize: () => islandSize,
    yieldIsland: (on) => send(overlay, on ? 'island:yield' : 'island:return'),
    overlayRects: () => overlayRects,
    openWindow: (route, args) => appWindows?.open(route, args),
    appWindow: (route) => appWindows?.get(route)
  })
  setupMenu()
  // A cold launch opens on the splash (main/splash.ts), in home's own frame; home opens and paints underneath it. Not when started at login
  // or for recordings (MIYAGI_QUIET_LAUNCH=1, the same switch features/launch.ts reads), not with MIYAGI_NO_SPLASH=1,
  // and not in a second copy that features/launch.ts is about to quit.
  if (wantsSplash()) showSplash(appWindowFrame('library'))
  else skipSplash()
})

/** How long the splash waits on the engine link before it leaves anyway (the engine keeps starting behind the app). */
const ENGINE_SPLASH_MS = 2500

function wantsSplash(): boolean {
  if (process.env.MIYAGI_QUIET_LAUNCH === '1' || process.env.MIYAGI_NO_SPLASH === '1') return false
  if (platform.os === 'mac' && !app.hasSingleInstanceLock()) return false
  try {
    if (platform.os === 'mac' && app.getLoginItemSettings().wasOpenedAtLogin) return false
  } catch {
    // no login item info: a normal launch
  }
  return true
}

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
/**
 * R44: the engine goes with the app. Its windows are already closed here; when the engine this app started is still
 * running, the quit waits (bounded) while localEngine SIGTERMs its group and, if it's hung, SIGKILLs it, then exits.
 * The other will-quit listeners (features) have run by then: app.exit skips the events, so none of them runs twice.
 */
let engineStopping = false
app.on('will-quit', (event) => {
  globalShortcut.unregisterAll()
  if (engineStopping) return event.preventDefault()
  let pending: Promise<void> | void = undefined
  try {
    pending = stopLocalEngine()
  } catch (err) {
    console.error('[tut] stopping the engine threw', err)
  }
  if (!pending) return
  engineStopping = true
  event.preventDefault()
  let done = false
  const exit = (): void => {
    if (done) return
    done = true
    app.exit(0)
  }
  const deadline = setTimeout(exit, QUIT_ENGINE_DEADLINE_MS)
  pending
    .catch((err: unknown) => console.error('[tut] stopping the engine failed', err))
    .finally(() => {
      clearTimeout(deadline)
      exit()
    })
})
app.on('window-all-closed', () => app.quit())
