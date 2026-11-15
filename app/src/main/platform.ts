/**
 * EVERY macOS / Windows difference lives in this file. Nothing else branches on the OS.
 * (The renderer gets a PlatformInfo object from here; it never reads process.platform.)
 *
 * Only type imports from electron, so the renderer can import describePlatform() too.
 */
import type { App, BrowserWindow, BrowserWindowConstructorOptions } from 'electron'

export type Rect = { x: number; y: number; width: number; height: number }

export type ShortcutKind = 'launcher' | 'back' | 'explain' | 'diagram' | 'show_me' | 'hint' | 'voice_toggle'

export type PlatformInfo = {
  os: 'mac' | 'win'
  /** Top of the pill, in px from the top of the display. Mac: inside the menu-bar band, around the notch. */
  pillTop: number
  /** Labels shown in the UI (⌥E on Mac, Alt+E on Windows). */
  keys: Record<ShortcutKind, string>
  /** Electron accelerators for globalShortcut. */
  accelerators: Record<ShortcutKind, string>
}

export function describePlatform(os: string): PlatformInfo {
  const mac = os === 'darwin' || os === 'mac'
  return {
    os: mac ? 'mac' : 'win',
    // Mac: sit just UNDER the hardware notch (notch/menu bar is ~37pt on notched MacBook Pros), not behind it.
    pillTop: mac ? 40 : 8,
    // Mac lesson keys are ⌃⌥ (Control+Option), not ⌥ alone (Adrian, Sun 1 AM, after Michael's test): ⌥← is word-left
    // in VS Code and ⌥E/D/S/H/V type characters (⌥E is the accent key), so global ⌥ shortcuts stole the learner's
    // typing. ⌃⌥ combos type nothing. The launcher stays ⌥Space. Windows is unchanged (Ctrl+Alt is AltGr there).
    keys: mac
      ? { launcher: '⌥Space', back: '⌃⌥←', explain: '⌃⌥E', diagram: '⌃⌥D', show_me: '⌃⌥S', hint: '⌃⌥H', voice_toggle: '⌃⌥V' }
      : // Alt+Space is the Windows system menu: never bind it there.
        { launcher: 'Ctrl⇧Space', back: 'Alt←', explain: 'Alt+E', diagram: 'Alt+D', show_me: 'Alt+S', hint: 'Alt+H', voice_toggle: 'Alt+V' },
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
 * After the launcher hides, hand keyboard focus back to the app the user was in (VS Code).
 * Windows does this by itself. On macOS, hiding the app returns focus; then re-show the overlay
 * without activating. VERIFY ON THE MAC: if the pill flickers, try removing app.hide().
 */
export function returnFocus(app: App, overlay: BrowserWindow): void {
  if (!isMac()) return
  app.hide()
  setTimeout(() => {
    overlay.showInactive()
    raise(overlay)
  }, 0)
}
