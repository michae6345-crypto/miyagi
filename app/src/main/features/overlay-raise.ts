/**
 * Keep the overlay on top, and an opt-in for Spaces (Michael's desktop test, items 8 and 9).
 *
 * 8. Another app's always-on-top window at the same level (Wispr Flow's transparent "Status", level 1000) sat over
 *    the middle of the shortcut bar. Re-raise the overlay (level + moveTop) on lesson.ready and when the pointer
 *    enters the bar (renderer: features/shortcut-bar, bridge.invoke('overlay:raise'), throttled there).
 * 9. Clicking miyagi from a full-screen VS Code could switch macOS Spaces to the other VS Code window. The overlay is
 *    already a panel; MIYAGI_PANEL=1 also makes miyagi an "accessory" app (no Dock icon, not in ⌘Tab), so clicking
 *    it never activates the app or moves Spaces. Opt-in until it's tried on a Mac: the global shortcuts still open
 *    the launcher.
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { app } from 'electron'
import { defineMainFeature } from '../context'

export default defineMainFeature({
  id: 'overlay-raise',
  setup(ctx) {
    const raise = (): boolean => {
      if (ctx.overlay.isDestroyed()) return false
      ctx.raise(ctx.overlay)
      ctx.overlay.moveTop()
      return true
    }
    ctx.engine.onEvent((e) => {
      if (e.type === 'lesson.ready') raise()
    })
    ctx.handle('overlay:raise', raise)

    if (process.platform === 'darwin' && process.env.MIYAGI_PANEL === '1') {
      app.setActivationPolicy('accessory')
      console.log('[overlay-raise] MIYAGI_PANEL=1: accessory app (no Dock icon, clicks never switch Spaces)')
    }
  }
})
