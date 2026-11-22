/**
 * Windows parity for the installed app (no renderer side).
 *
 * One instance. macOS gives an app one instance for free: opening Miyagi again just focuses the running one.
 * Windows starts a second process, which would stack a second overlay and lose every global shortcut
 * to the first. So the installed Windows build keeps one instance and a second launch exits; features/launch.ts
 * opens home in the running one ('second-instance'), so opening miyagi from the Start menu again shows it.
 * Checked again on Nov 21 (v2 UI, packaged dir build): the second process exits, the running one brings home forward.
 * No-op on the Mac and in `npm run dev` (dev restarts must never be blocked by a stale process).
 * Checked on Windows 11 (packaged build): a second launch exits, the first keeps running.
 *
 * Presses on the non-focusable windows (the overlay: pill, gear, cards, bar; the player). After miyagi has had the
 * keyboard once (Settings or the launcher opened), Windows sends these windows WM_MOUSEACTIVATE on every press.
 * Chromium answers MA_NOACTIVATEANDEAT for a window that can't be activated, so the press is dropped and only the
 * release arrives: no click ever fires (Adrian, Nov 20: after one visit to Settings the gear did nothing and the pill
 * looked frozen). Chromium hides a window without activating another one (SWP_NOACTIVATE), so the hidden Settings or
 * launcher window stays miyagi's active window, and handing activation on with blur() lands on whatever window is
 * next (the NVIDIA overlay, in testing), not the learner's app. So give the page the dropped press ourselves, where it
 * happened, right before the move or release that follows it: clicks and drags both work. Focusable windows (launcher,
 * Settings) are activated by the press instead, and nothing is dropped there, so they aren't hooked.
 * Checked on Windows 11 (installed build, raw mouse input): gear → Settings → ✕, again and again, presses held 0-150 ms.
 */
import { app, BrowserWindow, Menu, screen } from 'electron'
import { defineMainFeature } from '../context'

/** electron-builder.yml appId: the AppUserModelID the installer gives miyagi's shortcuts. */
const APP_USER_MODEL_ID = 'dev.sandhacks.miyagi'

// The installed app's identity on Windows. The installer's Start menu and desktop shortcuts carry the appId as their
// AppUserModelID (NSIS); Windows shows a toast (features/reminders.ts) only for an ID that a Start menu shortcut has,
// and groups taskbar buttons by it. Electron's default ("electron.app.miyagi") has no shortcut, so reminders never
// appeared. Module top level (features load before app ready): it must be set before main/prefs.ts applies
// launch at login, whose Run entry is named after this ID. Keep in step with appId in electron-builder.yml.
if (process.platform === 'win32' && app.isPackaged) app.setAppUserModelId(APP_USER_MODEL_ID)

const WM_MOUSEACTIVATE = 0x0021
const WM_MOUSEMOVE = 0x0200
type Button = 'left' | 'right' | 'middle'
/** WM_xBUTTONDOWN / WM_xBUTTONUP → the button. */
const DOWN: Record<number, Button> = { 0x0201: 'left', 0x0204: 'right', 0x0207: 'middle' }
const UP: Record<number, Button> = { 0x0202: 'left', 0x0205: 'right', 0x0208: 'middle' }
/** WM_MOUSEMOVE's wParam: which buttons are held (MK_LBUTTON, MK_RBUTTON, MK_MBUTTON). */
const HELD: Record<Button, number> = { left: 0x0001, right: 0x0002, middle: 0x0010 }

function keepPresses(win: BrowserWindow): void {
  /** A press Windows dropped, where it happened (window coordinates). */
  let dropped: { button: Button; x: number; y: number } | undefined
  /** Send the dropped press right before Chromium handles the move (a drag) or the release (a click) after it. */
  const replay = (): void => {
    const d = dropped
    dropped = undefined
    if (d && !win.isDestroyed()) win.webContents.sendInputEvent({ type: 'mouseDown', button: d.button, x: d.x, y: d.y, clickCount: 1 })
  }
  // HIWORD(lParam) is the mouse message that caused the activation.
  win.hookWindowMessage(WM_MOUSEACTIVATE, (_wParam, lParam) => {
    const button = DOWN[lParam.readUInt16LE(2)]
    dropped = undefined
    if (!button || win.isDestroyed() || win.isFocusable()) return
    const p = screen.getCursorScreenPoint()
    const b = win.getContentBounds()
    dropped = { button, x: p.x - b.x, y: p.y - b.y }
  })
  // The press arrived after all (touch input is answered MA_NOACTIVATE, not dropped): nothing to send.
  for (const msg of Object.keys(DOWN)) win.hookWindowMessage(Number(msg), () => (dropped = undefined))
  win.hookWindowMessage(WM_MOUSEMOVE, (wParam) => {
    if (!dropped) return
    if (wParam.readUInt32LE(0) & HELD[dropped.button]) replay()
    else dropped = undefined // released over another window: no press to send
  })
  for (const [msg, button] of Object.entries(UP)) win.hookWindowMessage(Number(msg), () => dropped?.button === button && replay())
}

export default defineMainFeature({
  id: 'windows',
  setup(ctx) {
    if (ctx.platform.os !== 'win') return

    const hooked = new WeakSet<BrowserWindow>()
    const watch = (win: BrowserWindow): void => {
      if (hooked.has(win) || win.isDestroyed() || win.isFocusable()) return
      hooked.add(win)
      keepPresses(win)
    }
    BrowserWindow.getAllWindows().forEach(watch)
    ctx.app.on('browser-window-created', (_e, win) => watch(win))

    if (!ctx.app.isPackaged) return
    // Runs before the core windows' ready-to-show, so a second instance exits before anything appears.
    if (!ctx.app.requestSingleInstanceLock()) {
      ctx.app.exit(0)
      return
    }
    // No menu bar. main/index.ts sets the one app menu on macOS only, so Windows kept Electron's default (File, Edit,
    // View, Window): Alt showed it on every app window (home, setup), and it shipped Reload (Ctrl+R) and Toggle
    // Developer Tools (Ctrl+Shift+I) to learners. Text fields keep Ctrl+C / Ctrl+V / Ctrl+A / Ctrl+Z without it (only
    // macOS needs the Edit menu for those); Alt+F4 and the title bar still close, minimize and maximize.
    Menu.setApplicationMenu(null)
  }
})
