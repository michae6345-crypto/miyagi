/**
 * Main-process side of the player (renderer: src/renderer/src/features/player/).
 *
 *   - One frameless window, route `player`, docked to the right 40% of the work area (dock.ts).
 *     The user can drag it by its header and resize it; its bounds are saved and restored.
 *   - Hidden until lesson.ready, then shown with showInactive() so it never takes focus from the editor.
 *     Not focusable, except while the pointer is over it (renderer → player:hover).
 *   - Floats above normal windows ('floating') but below the overlay ('screen-saver'), so the dim,
 *     spotlight and cards draw over it.
 *
 * Handles (bridge.invoke from any window):
 *   player:dock    snap back to the right 40% (and save that)
 *   player:hover   (on: boolean) focusable while hovered
 *   player:intent  ({t, play}) a card's video jump from another window → broadcast to the player window
 *
 * UNVERIFIED: written and typechecked on Windows, where Smart App Control blocks electron.exe.
 * Check on the Mac: docking, drag by the header, bounds restore, no focus steal, autoplay.
 */
import { screen, shell, type BrowserWindow, type Rectangle } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { dockRect } from '../../renderer/src/features/player/dock'
import { color } from '../../renderer/src/core/theme'

/**
 * Painted before the renderer draws: the panel color from core/theme (color.glass), made opaque
 * (the window isn't transparent, so it can't take an alpha). One source of truth for the brand.
 */
const WINDOW_BG = color.glass.replace(/^rgba\(\s*([^,]+),\s*([^,]+),\s*([^,]+),[^)]*\)$/, 'rgb($1,$2,$3)')

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
      backgroundColor: WINDOW_BG,
      webPreferences: { autoplayPolicy: 'no-user-gesture-required' }
    })
    win.setAlwaysOnTop(true, 'floating')
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
      win.setAlwaysOnTop(true, 'floating')
    }
    ctx.engine.onEvent((e) => {
      if (e.type === 'lesson.ready') reveal()
    })
    // A lesson already running (e.g. DEMO=1 started before this feature loaded).
    if (ctx.engine.log.some((e) => e.type === 'lesson.ready')) win.once('ready-to-show', reveal)

    ctx.handle('player:dock', () => {
      win.setBounds(dock())
      save()
    })
    ctx.handle('player:hover', (on) => {
      if (!win.isDestroyed()) win.setFocusable(!!on)
    })
    ctx.handle('player:intent', (intent) => ctx.broadcast('player:intent', intent))
  }
})
