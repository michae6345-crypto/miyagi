/**
 * Keep the overlay on top, never steal focus, and never let a click on the island fall through
 * (Michael's desktop test item 8 and screenshot audit A2 / A3).
 *
 * Item 8. Another app's always-on-top window at the same level (Wispr Flow's transparent "Status", level 1000) sat
 *    over the middle of the shortcut bar. Re-raise the overlay (level + moveTop) on lesson events (throttled, not while the
 *    launcher is open) and when the pointer enters the bar (renderer: features/shortcut-bar, bridge.invoke('overlay:raise'), throttled there).
 * A2. The overlay activated miyagi as a regular app: the menu bar read "Electron File Edit View Window", VS Code
 *    went inactive, and a click could move Spaces. On macOS miyagi is now an "accessory" app by default (no Dock
 *    icon, not in ⌘Tab, clicks never activate it or switch Spaces); MIYAGI_REGULAR_APP=1 opts out. It's named
 *    "miyagi" with a minimal menu (Edit stays, so ⌘C / ⌘V / ⌘A keep working in the launcher's field).
 * A3. A click on the pill fell through to the wallpaper: the overlay ignores the mouse until the renderer sees a
 *    hover, and a quick click can land first. Main polls the cursor and stops ignoring the mouse the moment it
 *    enters the island's rect.
 * Test 3, item 2. The same on the bar: Diagram and Skip step did nothing when the pointer arrived without a hover
 *    first (QA card 19), and a drag to select text in the drawer went to the app underneath (test 4: Finder came
 *    forward). The poll now covers every UI rect the overlay reports (bar, cards, drawer, island: ctx.overlayRects(),
 *    the overlay.bounds set) every 25 ms, so the first press or drag always counts. The renderer doesn't know about
 *    a grab made here, so main gives the mouse back itself when the pointer leaves them all (unless the renderer
 *    still wants it: its overlay:interactive), or the whole-screen overlay would keep eating clicks.
 *
 * Review A8. The overlay stayed full size and clickable over other apps. When another app has been in front for a few
 *    seconds (features/shortcut-bar/front.ts decides, from main/features/front-app.ts), the renderer says
 *    'overlay:away': the overlay is click-through everywhere, this poll grabs nothing and a renderer hover can't
 *    take the mouse either. It ends when the renderer says so (a lesson app is in front again, the pointer reached
 *    the bar's handle) or the pointer rests on the island for REST_MS (main broadcasts 'overlay:wake').
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { app, Menu, screen } from 'electron'
import { defineMainFeature } from '../context'

const isMac = process.platform === 'darwin'
const accessory = isMac && process.env.MIYAGI_REGULAR_APP !== '1'

// Main features are imported before app.whenReady (eager glob in main/index.ts), so the name lands in time.
app.setName('miyagi')

/** How often main checks the cursor against the overlay's UI. */
const POLL_MS = 15 // test 8: a move-and-click at once on a card's Hint landed between two 25 ms ticks
/** Grab the mouse this many px before the pointer reaches a control's edge (4 px let a quick move-and-click on a
 * card's X near the top go through to VS Code's command center: Michael's 5 AM shoot). */
const MARGIN = 12
/** Away (A8): the pointer resting this long on the island wakes the overlay; passing over it doesn't. */
const REST_MS = 500

type Box = { x: number; y: number; w: number; h: number }
const within = (p: { x: number; y: number }, r: Box): boolean =>
  p.x >= r.x - MARGIN && p.x <= r.x + r.w + MARGIN && p.y >= r.y - MARGIN && p.y <= r.y + r.h + MARGIN

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
    // Test 5: another app's window (Claude desktop) covered the drawer for a minute. Re-raise on the lesson
    // events that put something on screen, at most once a second, and never over the open launcher.
    const RAISE_ON = new Set(['lesson.ready', 'step.started', 'step.passed', 'card', 'spotlight', 'offtrack', 'diagram'])
    let lastRaise = 0
    ctx.engine.onEvent((e) => {
      if (!RAISE_ON.has(e.type) || Date.now() - lastRaise < 1000) return
      if (!ctx.launcher.isDestroyed() && ctx.launcher.isVisible()) return
      lastRaise = Date.now()
      raise()
    })
    ctx.handle('overlay:raise', raise)

    // ---- A3 / test 3 item 2: catch the pointer on any control before the click lands ---------------------------
    /** The renderer's last overlay:interactive (main/index.ts applies it; this only listens). */
    let wants = false
    /** This poll stopped ignoring the mouse; the renderer may not know. */
    let grabbed = false
    /** A8: the learner is in another app; the whole overlay is click-through (the renderer's 'overlay:away'). */
    let away = false
    let restSince = 0
    ctx.onSignal('overlay:interactive', (on) => {
      wants = !!on
      // A "no" while the pointer is still inside a rect (a passive chip, the margin) is grabbed again on the next tick.
      // No ping-pong: the renderer only emits on a change, and it already said no.
      if (!wants) grabbed = false
      // Away: main/index.ts just applied the hover; undo it (this listener runs right after, in the same tick).
      else if (away && !ctx.overlay.isDestroyed()) ctx.overlay.setIgnoreMouseEvents(true, { forward: true })
    })
    ctx.handle('overlay:away', (on) => {
      const next = !!on
      if (next === away || ctx.overlay.isDestroyed()) return away
      away = next
      restSince = 0
      grabbed = false
      if (away) ctx.overlay.setIgnoreMouseEvents(true, { forward: true })
      else if (wants) ctx.overlay.setIgnoreMouseEvents(false) // the renderer's hover from while away (it only emits changes)
      return away
    })
    // A reloaded renderer starts click-through (main/index.ts, ui:ready) and has forgotten what it wanted.
    ctx.overlay.webContents.on('did-start-loading', () => {
      wants = false
      grabbed = false
      away = false
    })
    const timer = setInterval(() => {
      if (ctx.overlay.isDestroyed()) return clearInterval(timer)
      if (!ctx.overlay.isVisible()) return
      const d = ctx.display().bounds
      const { w, h, dx = 0, dy = 0 } = ctx.islandSize()
      // The island from its live size and place (the reported rects lag up to 300 ms while it grows into a card or
      // moves off the spotlight: core/islandPlace.ts), plus the rest.
      const island = { x: d.x + d.width / 2 - w / 2 + dx, y: d.y + ctx.platform.pillTop + dy, w, h }
      const p = screen.getCursorScreenPoint()
      if (away) {
        // Grab nothing. The pointer resting on the island (the pill, an open card) asks the renderer to wake (A8).
        if (!within(p, island)) restSince = 0
        else if (!restSince) restSince = Date.now()
        else if (restSince > 0 && Date.now() - restSince >= REST_MS) {
          restSince = -1 // once per rest
          ctx.broadcast('overlay:wake')
        }
        return
      }
      const now = within(p, island) || ctx.overlayRects().some((r) => within(p, r))
      if (now && !grabbed) {
        grabbed = true
        ctx.overlay.setIgnoreMouseEvents(false)
      } else if (!now && grabbed) {
        grabbed = false
        if (!wants) ctx.overlay.setIgnoreMouseEvents(true, { forward: true })
      }
    }, POLL_MS)
    app.on('before-quit', () => clearInterval(timer))
  }
})
