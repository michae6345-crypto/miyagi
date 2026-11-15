/**
 * Keep the overlay on top, never steal focus, and never let a click on the island fall through
 * (Michael's desktop test item 8 and screenshot audit A2 / A3).
 *
 * Item 8. Another app's always-on-top window at the same level (Wispr Flow's transparent "Status", level 1000) sat
 *    over the middle of the shortcut bar. Re-raise the overlay (level + moveTop) on lesson.ready and when the
 *    pointer enters the bar (renderer: features/shortcut-bar, bridge.invoke('overlay:raise'), throttled there).
 * A2. The overlay activated miyagi as a regular app: the menu bar read "Electron File Edit View Window", VS Code
 *    went inactive, and a click could move Spaces. On macOS miyagi is now an "accessory" app by default (no Dock
 *    icon, not in ⌘Tab, clicks never activate it or switch Spaces); MIYAGI_REGULAR_APP=1 opts out. It's named
 *    "miyagi" with a minimal menu (Edit stays, so ⌘C / ⌘V / ⌘A keep working in the launcher's field).
 * A3. A click on the pill fell through to the wallpaper: the overlay ignores the mouse until the renderer sees a
 *    hover, and a quick click can land first. Main polls the cursor (50 ms) and stops ignoring the mouse the
 *    moment it enters the island's rect; the renderer still turns click-through back on when the pointer leaves.
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { app, Menu, screen } from 'electron'
import { defineMainFeature } from '../context'

const isMac = process.platform === 'darwin'
const accessory = isMac && process.env.MIYAGI_REGULAR_APP !== '1'

// Main features are imported before app.whenReady (eager glob in main/index.ts), so the name lands in time.
app.setName('miyagi')

/** How often main checks the cursor against the island. */
const POLL_MS = 50
/** Grab the mouse a few px before the pointer reaches the island's edge. */
const MARGIN = 4

export default defineMainFeature({
  id: 'overlay-raise',
  setup(ctx) {
    // ---- A2: an accessory app with a minimal menu ----------------------------------------------------------
    if (isMac) {
      Menu.setApplicationMenu(
        Menu.buildFromTemplate([
          { label: 'miyagi', submenu: [{ role: 'hide' }, { role: 'quit' }] },
          { role: 'editMenu' }
        ])
      )
    }
    if (accessory) {
      app.setActivationPolicy('accessory')
      console.log('[overlay-raise] accessory app (no Dock icon, clicks never switch Spaces); MIYAGI_REGULAR_APP=1 opts out')
    }

    // ---- item 8: keep the overlay on top -------------------------------------------------------------------
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

    // ---- A3: catch the pointer on the island before the click lands -----------------------------------------
    let inside = false
    const timer = setInterval(() => {
      if (ctx.overlay.isDestroyed()) return clearInterval(timer)
      if (!ctx.overlay.isVisible()) return
      const d = ctx.display().bounds
      const { w, h } = ctx.islandSize()
      const x = d.x + d.width / 2 - w / 2 - MARGIN
      const y = d.y + ctx.platform.pillTop - MARGIN
      const p = screen.getCursorScreenPoint()
      const now = p.x >= x && p.x <= x + w + MARGIN * 2 && p.y >= y && p.y <= y + h + MARGIN * 2
      // Only on entering: leaving is the renderer's call (it knows about cards, the bar and the drawer too).
      if (now && !inside) ctx.overlay.setIgnoreMouseEvents(false)
      inside = now
    }, POLL_MS)
    app.on('before-quit', () => clearInterval(timer))
  }
})
