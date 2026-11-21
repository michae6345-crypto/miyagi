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
export type UiKeyKind = 'settings' | 'dismiss'
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
 * TheBoringNotch expands its panel over the notch on hover, so clicks near it can land on that app). So the default
 * stays just below the band, and MIYAGI_PILL_TOP (main-process env, px, 0-200) moves it: down (e.g. 56) to keep clear
 * of a notch app's hover zone. Up into the menu bar is no longer possible: main moves any value above the menu bar
 * (or the notch band) to just under it at launch (fitPillTop, launch-ease lane).
 * Read only in main; the browser stage (no `process`) always gets the default.
 */
function pillTopFor(mac: boolean): number {
  const fallback = mac ? 40 : 8
  let raw: string | undefined
  try {
    raw = typeof process !== 'undefined' ? process.env?.MIYAGI_PILL_TOP : undefined
  } catch {
    raw = undefined
  }
  const n = raw === undefined || raw.trim() === '' ? NaN : Number(raw)
  return Number.isFinite(n) && n >= 0 && n <= 200 ? Math.round(n) : fallback
}

/** Air between the bottom of the menu bar (or the notch band) and the top of the pill. */
const MENU_BAR_GAP = 4

/**
 * Launch-ease lane: the pill never covers the menu bar's items or the notch. The display's work area starts under the
 * menu bar (macOS: about 24 pt, about 37 pt on a notched MacBook, where the band is the notch's height; Windows: a
 * taskbar docked at the top), so the pill goes no higher than MENU_BAR_GAP under it. The default (or a
 * MIYAGI_PILL_TOP) below that is kept as is; one above it is moved down. A menu bar that hides itself reports no band
 * (work area at the very top): the default stays, which already clears a notch.
 * Main only, once at launch for the primary display (renderers get pillTop in their launch arguments).
 */
export function fitPillTop(pillTop: number, display: { bounds: Rect; workArea: Rect }): number {
  const band = Math.max(0, display.workArea.y - display.bounds.y)
  return band > 0 ? Math.max(pillTop, Math.round(band + MENU_BAR_GAP)) : pillTop
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
      ? { launcher: '⌥Space', back: '⌃⌥←', explain: '⌃⌥E', diagram: '⌃⌥D', show_me: '⌃⌥S', hint: '⌃⌥H', voice_toggle: '⌃⌥V', settings: '⌘,', dismiss: 'Esc' }
      : // Alt+Space is the Windows system menu: never bind it there.
        { launcher: 'Ctrl⇧Space', back: 'Alt←', explain: 'Alt+E', diagram: 'Alt+D', show_me: 'Alt+S', hint: 'Alt+H', voice_toggle: 'Alt+V', settings: 'Ctrl+,', dismiss: 'Esc' },
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
    ...(isMac() ? { type: 'panel' as const } : {})
  }
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
 * NOT always on top, sandboxed like every window. The caller adds bounds.
 */
export function appWindowOptions(background: string): BrowserWindowConstructorOptions {
  return {
    show: false,
    frame: true,
    transparent: false,
    resizable: true,
    minimizable: true,
    maximizable: false,
    fullscreenable: false,
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
