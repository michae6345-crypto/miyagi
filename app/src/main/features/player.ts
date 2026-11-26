/**
 * Main-process side of the player (renderer: src/renderer/src/features/player/).
 *
 *   - One frameless window, route `player`, docked to the right 40% of the work area (dock.ts).
 *     The user can drag it by its header and resize it; its bounds are saved and restored.
 *   - Hidden until lesson.ready, then shown with showInactive() so it never takes focus from the editor.
 *     Not focusable, except while the pointer is over it (renderer → player:hover).
 *   - Floats at the overlay's level ('screen-saver', one step below it), so the dim, spotlight and cards
 *     still draw over it, and on macOS it shows over full-screen apps on every Space (type 'panel').
 *
 * Handles (bridge.invoke from any window):
 *   player:dock    snap back to the right 40% (and save that)
 *   player:hover   (on: boolean) focusable while hovered
 *   player:hide    the lesson is gone (the player window's lesson became null): hide the window
 *   player:setup   (on: boolean) a setup card is waiting (from the overlay, where the cards live): relayed to every
 *                  window as feat:player:setup, so the player holds the video until setup is done or skipped
 *   player:visible → boolean: is the player window on screen now
 *   player:host    → string | undefined: the URL the panel frames the video from (R33: main/playerHost.ts)
 *
 * R33: YouTube's player runs in that host page, a cross-origin frame with no preload, never in our page with the
 * bridge. The panel drives it over postMessage (renderer features/player/frame.ts). Frames in this window may only
 * navigate to the host page, then YouTube hosts (playerHost.frameAllowed).
 *
 * Broadcasts feat:player:visible (boolean) whenever the window shows, hides, minimizes or restores. The renderer plays
 * only while it's true (features/player/policy.ts): a window created with show:false reports
 * document.visibilityState 'visible' anyway, so the page can't tell on its own (Michael, Nov 21: audio from a hidden player).
 *
 * Hidden again on lesson.ended (except reason "interrupted": an engine deploy that comes back with the same lesson).
 *
 * UNVERIFIED: written and typechecked on Windows, where Smart App Control blocks electron.exe.
 * Check on the Mac: docking, drag by the header, bounds restore, no focus steal, autoplay. R33 (checked in a browser
 * stage only): the video loads in dev and in a built app, play / pause / seek / gate, no "[player] blocked" warning.
 */
import { nativeTheme, screen, type BrowserWindow, type Rectangle, type WebFrameMain } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { panelType } from '../platform'
import { frameAllowed, HOST_PAGE, playerHostOrigin } from '../playerHost'
import { dockRect } from '../../renderer/src/features/player/dock'
import { glassBg } from '../../renderer/src/core/theme'

/** rgba(r,g,b,a) → rgb(r,g,b): the window isn't transparent, so its background can't take an alpha. */
const opaque = (c: string): string => c.replace(/^rgba\(\s*([^,]+),\s*([^,]+),\s*([^,]+),[^)]*\)$/, 'rgb($1,$2,$3)')

/**
 * Painted before the renderer draws (and under its glass): the player is a glass panel, so it follows
 * Settings → Appearance. Core main sets nativeTheme.themeSource from the pref, so shouldUseDarkColors is
 * the resolved appearance. Dark: the glass panel color; light: the kit's light HUD glass. Both from core/theme.
 */
const windowBg = (): string => opaque(nativeTheme.shouldUseDarkColors ? glassBg.dark : glassBg.light)

function loadBounds(file: string): Rectangle | undefined {
  try {
    const b = JSON.parse(readFileSync(file, 'utf8')) as Rectangle
    if (![b.x, b.y, b.width, b.height].every(Number.isFinite)) return undefined
    // Only restore if it still lands on a display (monitors change).
    const visible = screen.getAllDisplays().some(({ workArea: w }) => {
      const ix = Math.min(b.x + b.width, w.x + w.width) - Math.max(b.x, w.x)
      const iy = Math.min(b.y + b.height, w.y + w.height) - Math.max(b.y, w.y)
      return ix >= 120 && iy >= 80
    })
    return visible ? b : undefined
  } catch {
    return undefined
  }
}

const originOf = (url: string): string => {
  try {
    return new URL(url).origin
  } catch {
    return '(not a URL)'
  }
}

/** 0 = the main frame (our page), 1 = a frame in it (the host page), 2+ = frames inside the host page. */
function frameDepth(frame: WebFrameMain | null): number {
  if (!frame) return -1
  let depth = 0
  for (let p = frame.parent; p; p = p.parent) depth++
  return depth
}

export default defineMainFeature({
  id: 'player',
  setup(ctx) {
    const file = join(ctx.app.getPath('userData'), 'player-bounds.json')
    const dock = (): Rectangle => dockRect(ctx.display().workArea)

    const win: BrowserWindow = ctx.createWindow('player', {
      ...(loadBounds(file) ?? dock()),
      show: false,
      frame: false,
      resizable: true,
      movable: true,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      minWidth: 360,
      minHeight: 320,
      skipTaskbar: true,
      focusable: false,
      hasShadow: true,
      // A non-activating panel on macOS (platform.ts panelType), like the overlay. It was a plain window made focusable
      // while hovered, so a click on it activated miyagi: over a full-screen VS Code that switched Spaces to miyagi's
      // home window (user report, main 1d453ca0). As a panel it takes the click (and the keys while hovered) and VS Code
      // stays the active app. acceptFirstMouse: the first click on the inactive panel counts (the overlay's fix, test 1).
      ...panelType(),
      acceptFirstMouse: true,
      backgroundColor: windowBg(),
      webPreferences: { autoplayPolicy: 'no-user-gesture-required' }
    })
    ctx.raise(win, -1)
    // Settings → Appearance (or the OS, on "System") changed: repaint the window's own background too.
    const onTheme = (): void => {
      if (!win.isDestroyed()) win.setBackgroundColor(windowBg())
    }
    nativeTheme.on('updated', onTheme)
    win.on('closed', () => nativeTheme.off('updated', onTheme))
    // The engine's screen reader must ignore the player, or it reads the tutorial's code as the learner's.
    ctx.reportBounds(win)

    // R33: the video plays in the host page (main/playerHost.ts), framed by our page; YouTube's embed is framed by
    // the host. Their navigation is locked to exactly that (frameAllowed). Our own page (the main frame) stays under
    // core's lock (index.ts hardenContents), and so do new windows: never an Electron window, plain https links go to
    // the browser through safeOpen (the iframe's sandbox already refuses popups).
    const lock = (e: Electron.Event, url: string, isMainFrame: boolean, frame: WebFrameMain | null): void => {
      if (isMainFrame || frameAllowed(url, frameDepth(frame))) return
      e.preventDefault()
      console.warn(`[player] blocked a frame navigation to ${originOf(url)}`)
    }
    win.webContents.on('will-frame-navigate', (e) => lock(e, e.url, e.isMainFrame, e.frame))
    win.webContents.on('will-redirect', (e) => lock(e, e.url, e.isMainFrame, e.frame))

    let saveTimer: ReturnType<typeof setTimeout> | undefined
    const save = (): void => {
      clearTimeout(saveTimer)
      saveTimer = setTimeout(() => {
        try {
          if (!win.isDestroyed()) writeFileSync(file, JSON.stringify(win.getBounds()))
        } catch (err) {
          console.warn('[player] could not save bounds', err)
        }
      }, 400)
    }
    win.on('moved', save)
    win.on('resized', save)

    // On screen or not, for the renderer's play gate. Re-told a beat after a reveal: showInactive() can be held until
    // the first paint, and a 'show' event isn't promised for it on every platform.
    const shown = (): boolean => !win.isDestroyed() && win.isVisible() && !win.isMinimized()
    let told: boolean | undefined
    const tell = (): void => {
      const now = shown()
      if (now === told) return
      told = now
      ctx.broadcast('player:visible', now)
    }
    win.on('show', tell)
    win.on('hide', tell)
    win.on('minimize', tell)
    win.on('restore', tell)
    win.on('ready-to-show', tell)
    ctx.handle('player:visible', () => shown())

    const reveal = (): void => {
      if (win.isDestroyed() || win.isVisible()) return
      win.showInactive()
      ctx.raise(win, -1)
      tell()
      setTimeout(tell, 300)
      setTimeout(tell, 1200)
    }
    // "Just teach me" (lesson.mode "lesson") has no video: never open or show the player for it (Michael, Sat 3:23 PM).
    const textLesson = (e: { type: string; payload?: unknown }): boolean =>
      e.type === 'lesson.ready' && (e.payload as { lesson?: { mode?: string } } | undefined)?.lesson?.mode === 'lesson'
    const hide = (): void => {
      if (!win.isDestroyed() && win.isVisible()) win.hide()
      tell()
    }
    let readyAt = 0
    ctx.engine.onEvent((e) => {
      // End lesson (Michael's desktop test 9): the empty panel ("The tutorial plays here once a lesson starts.") stayed
      // open. The lesson is over, so the player goes. Not for "interrupted" (an engine deploy that comes back with the
      // same lesson): the renderer asks for player:hide if that lesson never comes back.
      if (e.type === 'lesson.ended') {
        if ((e.payload as { reason?: string } | undefined)?.reason !== 'interrupted') hide()
        return
      }
      if (e.type !== 'lesson.ready') return
      readyAt = Date.now()
      if (textLesson(e)) hide()
      else reveal()
    })
    // A lesson already running (e.g. DEMO=1 started before this feature loaded).
    const ready = [...ctx.engine.log].reverse().find((e) => e.type === 'lesson.ready')
    if (ready && !textLesson(ready)) win.once('ready-to-show', reveal)

    ctx.handle('player:dock', () => {
      win.setBounds(dock())
      save()
    })
    // The player window's lesson became null without an End (an interrupted lesson that never came back, an engine
    // restart with no lesson): hide it too. A lesson.ready that just landed wins (its reset came first).
    ctx.handle('player:hide', () => {
      if (Date.now() - readyAt > 1500) hide()
    })
    // A setup card is waiting, or not any more (from the overlay, where the cards live): every window hears it, and the
    // player holds the video until setup is done or skipped (Michael's desktop test 9).
    ctx.handle('player:setup', (on) => ctx.broadcast('player:setup', on === true))
    ctx.handle('player:hover', (on) => {
      if (!win.isDestroyed()) win.setFocusable(!!on)
    })
    // R33: where the panel frames the video from (the host page on its own loopback origin), or undefined if the
    // host isn't serving (the panel then shows its load error).
    ctx.handle('player:host', () => {
      const origin = playerHostOrigin()
      return origin ? `${origin}${HOST_PAGE}` : undefined
    })
  }
})

