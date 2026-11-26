/**
 * EVERY macOS / Windows difference lives in this file. Nothing else branches on the OS.
 * (The renderer gets a PlatformInfo object from here; it never reads process.platform.)
 *
 * Only type imports from electron, so the renderer can import describePlatform() too.
 */
import type { App, BrowserWindow, BrowserWindowConstructorOptions } from 'electron'

export type Rect = { x: number; y: number; width: number; height: number }

export type ShortcutKind = 'launcher' | 'back' | 'explain' | 'diagram' | 'show_me' | 'hint' | 'voice_toggle'
/** v2 (W0-4): keys shown in the UI that are not global shortcuts: open Settings (in an app window's menu) and dismiss. */
export type UiKeyKind = 'settings' | 'dismiss' | 'ptt' | 'ptt_alt'
/** Every label in PlatformInfo.keys: the ONLY source of keycaps (core/ui/Keycap.tsx). */
export type KeyName = ShortcutKind | UiKeyKind

export type PlatformInfo = {
  os: 'mac' | 'win'
  /** Top of the pill, in px from the top of the display. Mac: just under the notch / menu-bar band (see pillTopFor). */
  pillTop: number
  /** Labels shown in the UI (⌥E on Mac, Alt+E on Windows), plus settings / dismiss (v2). */
  keys: Record<KeyName, string>
  /** Electron accelerators for globalShortcut. */
  accelerators: Record<ShortcutKind, string>
}

/**
 * Where the pill (and the launcher and every surface born from it) sits, in px from the top of the display.
 *
 * Mac: just UNDER the hardware notch (notch/menu bar is ~37pt on notched MacBook Pros), not behind it. Michael's review
 * A20 asked to anchor it in the menu-bar band (it sits over title bars), but on a notched Mac the band's centre IS the
 * notch: the pill's words would be hidden behind it, and that is exactly where notch apps live (desktop test 5:
 * a notch app expands its panel over the notch on hover, so clicks near it can land on that app). So the default
 * stays just below the band, and MIYAGI_PILL_TOP (main-process env, px, 0-200) moves it: down (e.g. 56) to keep clear
 * of a notch app's hover zone. Up into the menu bar is no longer possible. This is only the value before main knows
 * the display: main re-fits it per display with common/notch.ts belowTop (flush with the menu bar's bottom edge on a
 * Mac unless MIYAGI_PILL_TOP is set). Read only in main; the browser stage (no `process`) always gets the default.
 */
function pillTopFor(mac: boolean): number {
  return pillTopOverride() ?? (mac ? 40 : 8)
}

/**
 * MIYAGI_PILL_TOP when it is set to a usable value (px, 0-200), else undefined. Where the island goes below the menu
 * bar is common/notch.ts belowTop: flush with the menu bar's bottom edge on a Mac by default (no more floating 16 pt under
 * a 24 pt menu bar on a display without a notch, MacBook Neo, Nov 25); an override keeps the old rule (no higher than
 * MENU_BAR_GAP under the band). Main only.
 */
export function pillTopOverride(): number | undefined {
  let raw: string | undefined
  try {
    raw = typeof process !== 'undefined' ? process.env?.MIYAGI_PILL_TOP : undefined
  } catch {
    raw = undefined
  }
  const n = raw === undefined || raw.trim() === '' ? NaN : Number(raw)
  return Number.isFinite(n) && n >= 0 && n <= 200 ? Math.round(n) : undefined
}

export function describePlatform(os: string): PlatformInfo {
  const mac = os === 'darwin' || os === 'mac'
  return {
    os: mac ? 'mac' : 'win',
    pillTop: pillTopFor(mac),
    // Mac lesson keys are ⌃⌥ (Control+Option), not ⌥ alone (Adrian, Sun 1 AM, after Michael's test): ⌥← is word-left
    // in VS Code and ⌥E/D/S/H/V type characters (⌥E is the accent key), so global ⌥ shortcuts stole the learner's
    // typing. ⌃⌥ combos type nothing. The launcher stays ⌥Space. Windows is unchanged (Ctrl+Alt is AltGr there).
    keys: mac
      ? { launcher: '⌥Space', back: '⌃⌥←', explain: '⌃⌥E', diagram: '⌃⌥D', show_me: '⌃⌥S', hint: '⌃⌥H', voice_toggle: '⌃⌥V', settings: '⌘,', dismiss: 'Esc', ptt: 'fn ⌃', ptt_alt: '⌃⌥' }
      : // Alt+Space is the Windows system menu: never bind it there.
        { launcher: 'Ctrl⇧Space', back: 'Alt←', explain: 'Alt+E', diagram: 'Alt+D', show_me: 'Alt+S', hint: 'Alt+H', voice_toggle: 'Alt+V', settings: 'Ctrl+,', dismiss: 'Esc', ptt: 'Ctrl+Win', ptt_alt: 'Ctrl+Alt' },
    accelerators: mac
      ? {
          launcher: 'Alt+Space',
          back: 'Control+Alt+Left',
          explain: 'Control+Alt+E',
          diagram: 'Control+Alt+D',
          show_me: 'Control+Alt+S',
          hint: 'Control+Alt+H',
          voice_toggle: 'Control+Alt+V'
        }
      : {
          launcher: 'Control+Shift+Space',
          back: 'Alt+Left',
          explain: 'Alt+E',
          diagram: 'Alt+D',
          show_me: 'Alt+S',
          hint: 'Alt+H',
          voice_toggle: 'Alt+V'
        }
  }
}

// ---------------------------------------------------------------------------
// Electron-only helpers (main process)
// ---------------------------------------------------------------------------

const isMac = (): boolean => process.platform === 'darwin'

/**
 * Native glass behind the launcher (blurs the desktop like mockup 03).
 * Off by default until it's checked on the Mac: TUT_NATIVE_GLASS=1 turns it on.
 * Without it the launcher uses a CSS dim, which is safe everywhere.
 */
export const nativeGlass = (): boolean => process.env.TUT_NATIVE_GLASS === '1'

/** Flags shared by every overlay window (FRONTEND-HANDOFF.md). No setContentProtection: we want it in recordings. */
export function overlayWindowOptions(bounds: Rect): BrowserWindowConstructorOptions {
  return {
    ...bounds,
    frame: false,
    // The overlay never takes focus (the launcher and Settings opt back in where they spread these options).
    focusable: false,
    transparent: true,
    hasShadow: false,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    show: false,
    backgroundColor: '#00000000',
    enableLargerThanScreen: true,
    // The overlay never becomes the active window, so without this macOS swallows the first click on the bar and
    // cards (Michael's desktop test, item 1: Skip, Check and Diagram needed a second click).
    acceptFirstMouse: true,
    ...panelType()
  }
}

/**
 * macOS: a non-activating panel (Electron's ElectronNSPanel with NSWindowStyleMaskNonactivatingPanel). A click on it never
 * activates miyagi, so the learner's app (VS Code, even in full screen) stays the active app and macOS never switches
 * Spaces to wherever an app window of miyagi lives. Every window of kind 'overlay' gets it (index.ts createWindow: the
 * overlay, the launcher, Settings, the player). Windows: a plain window.
 */
export function panelType(): BrowserWindowConstructorOptions {
  return isMac() ? { type: 'panel' } : {}
}

type PanelLike = Pick<BrowserWindow, 'isDestroyed' | 'isVisible' | 'show' | 'showInactive' | 'focus' | 'once'>

/** Panels with a 'show' listener from focusPanel still waiting: never stack a second one. */
const awaitingShow = new WeakSet<object>()

/**
 * Give a focusable panel (the launcher, Settings) the keyboard WITHOUT activating miyagi (user report, main 1d453ca0:
 * with VS Code in full screen, the overlay's "ask miyagi" switched Spaces to miyagi).
 *
 * The activation came from app.focus({steal: true}) (the launcher's old fallback, removed); Electron 45's Show() and
 * Focus() already skip activating the app for a panel (reviewed in its source). This keeps the path explicit and
 * stable whatever a future Electron does with show(): showInactive (orders the panel front only), then focus (key
 * window, no activation), once it is really on screen (index.ts holds a show until first paint).
 * Windows: show + focus, as before (no panel type there; the window must be activated to get keys).
 */
export function focusPanel(win: PanelLike): void {
  if (win.isDestroyed()) return
  if (!isMac()) {
    win.show()
    win.focus()
    return
  }
  if (win.isVisible()) return win.focus()
  win.showInactive()
  if (win.isVisible()) return win.focus()
  if (awaitingShow.has(win)) return
  awaitingShow.add(win)
  win.once('show', () => {
    awaitingShow.delete(win)
    if (!win.isDestroyed()) win.focus()
  })
}

/**
 * When a typing panel (the launcher: its field has the caret the moment it opens) asks again for the keyboard, after
 * focusPanel. Each one runs only while the panel is open and still not key.
 */
export const KEY_RETRY_MS = [60, 200, 450] as const

/** What the next retry does: nothing (it has the keys, it closed, not a Mac), focus the panel again, or activate miyagi. */
export type KeyStep = 'stop' | 'focus' | 'activate'

/**
 * Pure: the retry `attempt` (index into KEY_RETRY_MS) for a typing panel that should hold the keyboard.
 *
 * The first retries only ask again as a panel (key window, miyagi stays inactive: no Space switch over a full-screen app).
 * If the panel is STILL not key at the last one, the keystrokes are going to the app behind it (Michael's test 10 with
 * Finder in front; a tester, Nov 25: "It's coffee. I can't even type coffee."), so the last retry activates miyagi,
 * which makes AppKit route the keys to the panel. It does that only when it is safe:
 *   - activate: the caller says the panel's text field has the caret (the launcher always does while it is open);
 *     a panel without a focused field (Settings on open) never activates miyagi;
 *   - no app window (home, Library, Progress, onboarding) is open: activating miyagi with one of those on another Space
 *     is exactly what switched Spaces over a full-screen VS Code (main 1d453ca0). With only the panels, which are on
 *     every Space, there is nowhere to switch to;
 *   - once per open.
 * The caller hands the keyboard back when the panel closes (index.ts hideLauncher: returnFocus to the previous app).
 */
export function keyStep(s: {
  mac: boolean
  open: boolean
  focused: boolean
  attempt: number
  fieldFocused: boolean
  appWindowOpen: boolean
  activated: boolean
  /** It was key at some point since it asked: whatever took the keys since was the learner's doing (⌘Tab, a click). */
  everFocused?: boolean
  /** The app in front is not the one that was in front when it asked: the learner went there. */
  frontChanged?: boolean
}): KeyStep {
  if (!s.mac || !s.open || s.focused || s.everFocused || s.frontChanged) return 'stop'
  if (s.attempt < KEY_RETRY_MS.length - 1) return 'focus'
  if (s.fieldFocused && !s.appWindowOpen && !s.activated) return 'activate'
  return 'focus'
}

type KeyWin = Pick<BrowserWindow, 'isDestroyed' | 'isFocused' | 'focus'> & {
  on?: (event: 'focus', fn: () => void) => unknown
  removeListener?: (event: 'focus', fn: () => void) => unknown
}
type Timers = { set: (fn: () => void, ms: number) => unknown; clear: (t: unknown) => void }
const realTimers: Timers = { set: (fn, ms) => setTimeout(fn, ms), clear: (t) => clearTimeout(t as ReturnType<typeof setTimeout>) }

/**
 * Keep asking for the keyboard after focusPanel (KEY_RETRY_MS, keyStep). Returns a cancel for the retries still pending
 * (the panel closed). onActivate: miyagi was activated, so whoever closes the panel hands the keyboard back.
 * It stops for good once the window has been key (its 'focus' event or a retry that finds it key) or the app in front
 * (frontApp, read when it asked) changed: the learner left on purpose, and a late retry must never pull the keyboard
 * (or, worse, an activation and a Space switch) back from where they went.
 */
export function holdKeyboard(
  win: KeyWin,
  o: {
    app: Pick<App, 'focus'>
    isOpen: () => boolean
    fieldFocused: () => boolean
    appWindowOpen: () => boolean
    /** The app in front (its bundle id) now, when known (features/front-app previousApp). */
    frontApp?: () => string | undefined
    onActivate?: () => void
    timers?: Timers
  }
): () => void {
  const timers = o.timers ?? realTimers
  let activated = false
  let everFocused = false
  let done = false
  const front0 = o.frontApp?.()
  const onFocus = (): void => void (everFocused = true)
  win.on?.('focus', onFocus)
  const pending: unknown[] = []
  const stop = (): void => {
    if (done) return
    done = true
    pending.forEach((t) => timers.clear(t))
    if (!win.isDestroyed()) win.removeListener?.('focus', onFocus)
  }
  KEY_RETRY_MS.forEach((ms, attempt) =>
    pending.push(
      timers.set(() => {
        if (done || win.isDestroyed()) return stop()
        const focused = win.isFocused()
        if (focused) everFocused = true
        const front = o.frontApp?.()
        const frontChanged = front0 !== undefined && front !== undefined && front !== front0
        const step = keyStep({ mac: isMac(), open: o.isOpen(), focused, attempt, fieldFocused: o.fieldFocused(), appWindowOpen: o.appWindowOpen(), activated, everFocused, frontChanged })
        if (step === 'stop' || attempt === KEY_RETRY_MS.length - 1) stop()
        if (step === 'stop') return
        if (step === 'activate') {
          activated = true
          o.app.focus({ steal: true })
          o.onActivate?.()
        }
        win.focus()
      }, ms)
    )
  )
  return stop
}

export function launcherGlassOptions(): BrowserWindowConstructorOptions {
  if (!nativeGlass()) return {}
  return isMac()
    ? { vibrancy: 'fullscreen-ui', visualEffectState: 'active' }
    : { backgroundMaterial: 'acrylic' }
}

/** Show on every Space, including over full-screen apps and when the engine brings the editor forward (macOS). */
export function followSpaces(win: BrowserWindow): void {
  if (isMac()) win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
}

/** A window on every Space (the panels: followSpaces). Activating miyagi never switches Spaces to one of these. */
export function followsEverySpace(win: Pick<BrowserWindow, 'isVisibleOnAllWorkspaces'>): boolean {
  try {
    return win.isVisibleOnAllWorkspaces()
  } catch {
    return false
  }
}

/**
 * Float above everything, including full-screen apps (Michael, Sat: every Miyagi window gets this).
 * relativeLevel orders windows inside the 'screen-saver' level: the player uses -1 so it stays over
 * full-screen apps but under the overlay (the spotlight dim covers it).
 */
export function raise(win: BrowserWindow, relativeLevel = 0): void {
  win.setAlwaysOnTop(true, 'screen-saver', relativeLevel)
  followSpaces(win)
}

/**
 * A held key that means the learner is leaving the launcher: ⌘ or Ctrl (⌘Tab, ⌘Space, Ctrl+→) on macOS;
 * on Windows also Alt (Alt+Tab) and the Win key (input.meta).
 */
export function isLeavingModifier(input: { meta: boolean; control: boolean; alt: boolean }): boolean {
  return input.meta || input.control || (!isMac() && input.alt)
}

type WinLike = Pick<BrowserWindow, 'isDestroyed' | 'setOpacity' | 'setBounds' | 'showInactive' | 'moveTop' | 'setAlwaysOnTop' | 'setVisibleOnAllWorkspaces' | 'hide' | 'isVisible'>
type Emitter = { on(event: string, fn: () => void): unknown }

/** Pause after a display swap or an unlock before the overlay is shown again (the windows settle by then). */
export const OVERLAY_RESTORE_MS = 150

/**
 * Keep the overlay clean across the system events that move or drop its window (macOS):
 *  - display added / removed / metrics changed: the overlay goes transparent (opacity 0) while the displays swap, so
 *    no half-sized black shape flashes in the wrong place; after OVERLAY_RESTORE_MS it is re-fitted (`refit`), raised
 *    again and shown (opacity 1);
 *  - lock-screen: the overlay hides; unlock-screen: it comes back OVERLAY_RESTORE_MS later, raised again;
 *  - active space change (NSWorkspaceActiveSpaceDidChange): raise again, the level can drop with the space.
 * `refit` re-applies the display's bounds and re-sends the layout (main/index.ts). Returns a stop function.
 */
export function trackOverlayLifecycle(
  win: WinLike,
  deps: { screen: Emitter; powerMonitor: Emitter; canShow?: () => boolean; systemPreferences?: { subscribeWorkspaceNotification?: (name: string, cb: () => void) => number; unsubscribeWorkspaceNotification?: (id: number) => void } },
  refit: () => void
): () => void {
  if (!isMac()) return () => undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let locked = false
  // Only a window this lifecycle hid or faded may be shown again; a window that was hidden before (the launch gate
  // keeps the overlay hidden while signed out, main/gate.ts) stays hidden. `canShow` is the gate's say-so as well.
  let wasVisible: boolean | undefined
  const remember = (): void => {
    if (wasVisible === undefined) wasVisible = win.isVisible()
  }
  const live = (): boolean => !win.isDestroyed()
  const reassert = (): void => {
    if (!live()) return
    raise(win as BrowserWindow)
    win.moveTop()
  }
  const restoreSoon = (): void => {
    clearTimeout(timer)
    timer = setTimeout(() => {
      if (!live() || locked) return
      refit()
      const show = wasVisible === true && (deps.canShow?.() ?? true)
      wasVisible = undefined
      if (show && !win.isVisible()) win.showInactive()
      // Always undo the fade, even for a window that stays hidden: the gate shows it later with showInactive(), and a
      // window left at opacity 0 would come back fully transparent (an invisible island).
      if (!win.isVisible()) return void win.setOpacity(1)
      reassert()
      win.setOpacity(1)
    }, OVERLAY_RESTORE_MS)
  }
  const swap = (...args: unknown[]): void => {
    if (!live()) return
    if (workAreaOnly(args[2])) return // the menu bar / Dock showed or hid: the overlay's window doesn't move
    remember()
    win.setOpacity(0)
    restoreSoon()
  }
  const lock = (): void => {
    locked = true
    clearTimeout(timer)
    if (live()) {
      remember()
      win.setOpacity(0)
      win.hide()
    }
  }
  const unlock = (): void => {
    locked = false
    restoreSoon()
  }
  const space = (): void => reassert()
  const subs: [Emitter, string, () => void][] = [
    [deps.screen, 'display-added', swap],
    [deps.screen, 'display-removed', swap],
    [deps.screen, 'display-metrics-changed', swap],
    [deps.powerMonitor, 'lock-screen', lock],
    [deps.powerMonitor, 'unlock-screen', unlock]
  ]
  for (const [e, name, fn] of subs) e.on(name, fn)
  const sp = deps.systemPreferences
  let spaceId: number | undefined
  try {
    spaceId = sp?.subscribeWorkspaceNotification?.('NSWorkspaceActiveSpaceDidChange', space)
  } catch {
    /* no workspace notifications: the display events still re-raise */
  }
  return () => {
    clearTimeout(timer)
    if (spaceId !== undefined) sp?.unsubscribeWorkspaceNotification?.(spaceId)
    for (const [e, name, fn] of subs) (e as { removeListener?: (n: string, f: () => void) => void }).removeListener?.(name, fn)
  }
}

/**
 * display-metrics-changed's third argument (Electron: changedMetrics) names ONLY the work area: the menu bar or the Dock
 * showed or hid (a full-screen Space such as VS Code's coming or going, the Dock auto-hiding). The overlay covers the
 * display's full bounds, so nothing about its window changed: no fade, no refit, no island collapse (Nov 25, MacBook
 * Neo test: as VS Code opened, every Space switch faded the overlay and moved the pill, "back and forth"). Anything
 * else, or no list at all, is a real display change.
 */
/** A work-area-only change (menu bar / Dock) is acted on once this long after the last one of its burst. */
export const WORK_AREA_SETTLE_MS = 600

export function workAreaOnly(changed: unknown): boolean {
  return Array.isArray(changed) && changed.length > 0 && changed.every((m) => m === 'workArea')
}

/** The overlay covers the whole display (including the Mac menu bar, so the pill can hug the notch). */
export function overlayBounds(display: { bounds: Rect }): Rect {
  return display.bounds
}

/** Behave like a system feature: no Dock icon on macOS. */
export function setupApp(app: App): void {
  if (isMac()) app.dock?.hide()
}

/**
 * v2 (decision 4): an app window (Onboarding, Library, Progress, Account; main/appWindows.ts) shows a Dock icon while
 * it is open, so it can be found with ⌘Tab; the last one closing hides it again. Windows: taskbar entries are per
 * window already, nothing to do.
 */
export function showInDock(app: App, on: boolean): void {
  if (!isMac() || !app.dock) return
  if (on) void app.dock.show()
  else app.dock.hide()
}

/**
 * v2: options for an app window: a normal titled window (hiddenInset traffic lights on macOS), opaque, NOT a panel,
 * NOT always on top, sandboxed like every window. The caller adds bounds. `background` is the first-paint color for the
 * current theme (main/prefs.ts windowBackground()); trackWindowBackground keeps it in step when the theme changes.
 */
export function appWindowOptions(background: string): BrowserWindowConstructorOptions {
  return {
    show: false,
    frame: true,
    transparent: false,
    resizable: true,
    minimizable: true,
    // Nov 21: app windows (home, settings, onboarding...) zoom and go full screen like any Mac window. The overlay, the
    // pill and the panels stay non-fullscreenable (overlayWindowOptions, the launcher, the player).
    maximizable: true,
    fullscreenable: true,
    alwaysOnTop: false,
    skipTaskbar: false,
    backgroundColor: background,
    ...(isMac() ? { titleBarStyle: 'hiddenInset' as const, trafficLightPosition: { x: 14, y: 14 } } : { autoHideMenuBar: true })
  }
}

/**
 * After the launcher hides, hand keyboard focus back to the app the user was in (VS Code).
 * Windows does this by itself. On macOS, reactivate the app that was in front (`open -b <bundle>`, from
 * features/front-app) and keep the overlay up without activating it. app.hide() is only the fallback when that app
 * isn't known: in Michael's test 11 it hid the overlay with it, and showInactive didn't bring it back (Finder in front).
 */
export function returnFocus(app: App, overlay: BrowserWindow, previousBundle?: string): void {
  if (!isMac()) return
  if (previousBundle) {
    // Loaded here, never at the top: the renderer imports this file (describePlatform), and a top-level
    // node:child_process import crashed every window at load ("externalized for browser compatibility").
    void import('node:child_process').then(({ execFile }) =>
      execFile('open', ['-b', previousBundle], (err) => {
        if (err) console.warn('[focus] could not reactivate', previousBundle, err.message)
      })
    )
    overlay.showInactive()
    raise(overlay)
    return
  }
  app.hide()
  setTimeout(() => {
    overlay.showInactive()
    raise(overlay)
  }, 0)
}
