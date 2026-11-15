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
 *
 * Hidden again on lesson.ended (except reason "interrupted": an engine deploy that comes back with the same lesson).
 *
 * UNVERIFIED: written and typechecked on Windows, where Smart App Control blocks electron.exe.
 * Check on the Mac: docking, drag by the header, bounds restore, no focus steal, autoplay.
 */
import { nativeTheme, screen, shell, type BrowserWindow, type Rectangle } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { dockRect } from '../../renderer/src/features/player/dock'
import { color, hud } from '../../renderer/src/core/theme'

/** rgba(r,g,b,a) → rgb(r,g,b): the window isn't transparent, so its background can't take an alpha. */
const opaque = (c: string): string => c.replace(/^rgba\(\s*([^,]+),\s*([^,]+),\s*([^,]+),[^)]*\)$/, 'rgb($1,$2,$3)')

/**
 * Painted before the renderer draws (and under its glass): the player is a glass panel, so it follows
 * Settings → Appearance. Core main sets nativeTheme.themeSource from the pref, so shouldUseDarkColors is
 * the resolved appearance. Dark: the glass panel color; light: the kit's light HUD glass. Both from core/theme.
 */
const windowBg = (): string => opaque(nativeTheme.shouldUseDarkColors ? color.glass : hud.light.glass)

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

    // YouTube links must never open Electron windows.
    win.webContents.setWindowOpenHandler(({ url }) => {
      if (/^https:\/\//.test(url)) void shell.openExternal(url)
      return { action: 'deny' }
    })

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

    const reveal = (): void => {
      if (win.isDestroyed() || win.isVisible()) return
      win.showInactive()
      ctx.raise(win, -1)
    }
    // "Just teach me" (lesson.mode "lesson") has no video: never open or show the player for it (Michael, Sat 3:23 PM).
    const textLesson = (e: { type: string; payload?: unknown }): boolean =>
      e.type === 'lesson.ready' && (e.payload as { lesson?: { mode?: string } } | undefined)?.lesson?.mode === 'lesson'
    const hide = (): void => {
      if (!win.isDestroyed() && win.isVisible()) win.hide()
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
  }
})

