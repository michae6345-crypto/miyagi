/**
 * Launcher focus (UI-TEST 2026-11-21, item 4): Esc on the launcher returns the keyboard to the miyagi window that
 * opened it. Opened from another app, nothing here acts: main/index.ts hideLauncher already reactivates that app.
 *
 * Tracks which miyagi app window (home, progress, account...: never the overlay or the launcher) has the keyboard, takes
 * the one the launcher came from when it shows, and focuses it again when the launcher hides. main's own return to
 * "the last other app" (index.ts hideLauncher > returnFocus) runs first and may name Finder, so the window is focused
 * again a few times over ~0.5 s until it holds the keyboard.
 *
 * UNVERIFIED in Electron (no live run in this lane): see the manual repro in the PR. Pure logic: main/launcherFocus.ts.
 */
import { BrowserWindow } from 'electron'
import { defineMainFeature } from '../context'
import { createFocusMemory, REFOCUS_AT_MS } from '../launcherFocus'

export default defineMainFeature({
  id: 'launcher-focus',
  setup(ctx) {
    if (ctx.platform.os !== 'mac') return // Windows hands focus back by itself (platform.ts returnFocus)
    const memory = createFocusMemory()
    const isAppWindow = (w: BrowserWindow): boolean => w !== ctx.overlay && w !== ctx.launcher && !w.isDestroyed()

    ctx.app.on('browser-window-focus', (_e, w) => {
      if (isAppWindow(w)) memory.focus(w.id)
    })
    ctx.app.on('browser-window-blur', (_e, w) => {
      if (isAppWindow(w)) memory.blur(w.id)
    })
    ctx.launcher.on('show', () => memory.opened())

    ctx.onSignal('launcher:hidden', () => {
      const id = memory.closed()
      if (id === undefined) return
      const win = BrowserWindow.fromId(id)
      if (!win || win.isDestroyed() || !win.isVisible()) return
      for (const ms of REFOCUS_AT_MS) {
        setTimeout(() => {
          if (win.isDestroyed() || win.isFocused()) return
          if (!ctx.launcher.isDestroyed() && ctx.launcher.isVisible()) return // opened again meanwhile
          ctx.app.focus({ steal: true })
          win.focus()
        }, ms)
      }
    })
  }
})
