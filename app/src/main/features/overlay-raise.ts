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
 *    "miyagi" (its one menu is set in main/index.ts setupMenu; Edit stays, so ⌘C / ⌘V / ⌘A keep working in the launcher's field).
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
 *    the bar's handle) or the pointer rests on the island for REST_MS (REST_NOTCH_MS in the notch) (main broadcasts 'overlay:wake').
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { app, screen } from 'electron'
import { defineMainFeature } from '../context'
import { createOtherOpenMute, GRAB, withinGrab } from '../../renderer/src/core/notchGeometry'
import { getNotchService } from '../notch'

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
/** In the notch rect hover wakes the overlay from away almost at once (and the peek opens with it). */
export const REST_NOTCH_MS = 120

type Box = { x: number; y: number; w: number; h: number }
/**
 * The grab zone around a UI rect. In the notch (`notch` true: the island sits at the display top) a rect touching the
 * display top is grabbed only +-6 pt sideways and 12 pt below, never into the menu bar beside the notch, so the menu
 * items next to it stay clickable. Below the menu bar it is MARGIN all round, as ever (core/notchGeometry.ts withinGrab).
 */
const within = (p: { x: number; y: number }, r: Box, notch = false, displayTop = 0, opts?: { coexist?: boolean; notch?: { x: number; width: number; height: number } }): boolean =>
  withinGrab(p, r, { notch, displayTop, margin: MARGIN }, opts)

/** The pointer strictly inside a rect (no grab margin). */
const inside = (p: { x: number; y: number }, r: Box): boolean => p.x >= r.x && p.x < r.x + r.w && p.y >= r.y && p.y < r.y + r.h
/** Two rects share any area (a hit rect that is the island, or part of its card, is left to the rest-to-wake rule). */
const overlaps = (a: Box, b: Box): boolean => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

export default defineMainFeature({
  id: 'overlay-raise',
  setup(ctx) {
    // ---- A2: an accessory app with a minimal menu ----------------------------------------------------------
    // The app menu (miyagi, Edit, View, Window) is defined once, in main/index.ts setupMenu. Edit stays in it, so ⌘C / ⌘V / ⌘A keep working in the launcher's field.
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
    // Desktop test 9, A1: grab only over controls. The renderer sends its data-hit rects ('overlay:hits'); until it
    // does (an older renderer), every reported rect counts, as before.
    let hits: Box[] | undefined
    ctx.handle('overlay:hits', (rects) => {
      hits = Array.isArray(rects) ? (rects as Box[]) : undefined
    })
    // A scroll over UI that can't scroll itself: give the mouse to the app below for a moment (renderer 'overlay:pass').
    let passUntil = 0
    ctx.handle('overlay:pass', (ms) => {
      passUntil = Date.now() + Math.min(2000, Math.max(0, Number(ms) || 0))
      grabbed = false
      if (!ctx.overlay.isDestroyed()) ctx.overlay.setIgnoreMouseEvents(true, { forward: true })
    })
    // Another notch app shares the notch (private flag from main/notch.ts): its core is not ours to grab, and while its
    // panel looks open (pointer dwelling in the core) we grab nothing until the pointer has left its open zone.
    const mute = createOtherOpenMute()
    let muteOn = false
    const timer = setInterval(() => {
      if (ctx.overlay.isDestroyed()) return clearInterval(timer)
      if (!ctx.overlay.isVisible()) return
      if (Date.now() < passUntil) return
      const d = ctx.display().bounds
      const { w, h, dx = 0, dy = 0, shown = true, top, place } = ctx.islandSize()
      // The notch island (renderer 'island:size' says so): its rect starts at the display top, not at pillTop.
      const inNotch = place === 'notch'
      // The island from its live size and place (the reported rects lag up to 300 ms while it grows into a card or
      // moves off the spotlight: core/islandPlace.ts), plus the rest.
      // A hidden island (no mode, or the launcher has it) is not a click target: no ghost box eating clicks.
      const island = shown ? { x: d.x + d.width / 2 - w / 2 + dx, y: d.y + (inNotch ? (top ?? 0) : ctx.platform.pillTop) + dy, w, h } : { x: -1e6, y: -1e6, w: 0, h: 0 }
      const p = screen.getCursorScreenPoint()
      // Notch rect in screen coordinates, only while sharing the notch.
      const svc = getNotchService()
      const g = inNotch && svc?.coexist() ? svc.geometryFor(ctx.display()) : undefined
      const shared = g ? { coexist: true, notch: { x: d.x + g.x, width: g.width, height: g.height } } : undefined
      const nowMuted = shared ? mute.step(Date.now(), p, shared.notch, d.y) : (mute.reset(), false)
      if (nowMuted !== muteOn) {
        muteOn = nowMuted
        ctx.broadcast('overlay:other-open', muteOn)
      }
      if (muteOn) {
        restSince = 0
        if (grabbed) {
          grabbed = false
          if (!wants) ctx.overlay.setIgnoreMouseEvents(true, { forward: true })
        }
        return
      }
      // The quick wake (REST_NOTCH_MS) applies only while the pointer is on the notch itself (its rect, with the grab
      // margins); cards and the pill body below it keep the ordinary REST_MS.
      const ng = inNotch ? (svc?.geometryFor(ctx.display()) ?? g) : undefined
      const inNotchRect = !!ng && p.x >= d.x + ng.x - GRAB.side && p.x <= d.x + ng.x + ng.width + GRAB.side && p.y >= d.y && p.y <= d.y + ng.height + GRAB.below
      if (away) {
        // Michael, Nov 22: the steps panel stayed on screen while he was in another app, but its X and drag did
        // nothing. A pointer right on a visible control that is not the island (the drawer, the player's cards: no
        // grab margin, so passing near one never counts) wakes the overlay at once and grabs in this same tick, so the
        // first press lands. The renderer hears 'overlay:wake' and starts a fresh away count.
        const overIsland = shown && within(p, island, inNotch, d.y, shared)
        if (!overIsland && (hits ?? []).some((r) => inside(p, r) && !overlaps(r, island))) {
          away = false
          restSince = 0
          grabbed = true
          ctx.overlay.setIgnoreMouseEvents(false)
          ctx.broadcast('overlay:wake')
          return
        }
        // Otherwise grab nothing. The pointer resting on the island (the pill, an open card) asks the renderer to wake (A8).
        if (!overIsland) restSince = 0
        else if (!restSince) restSince = Date.now()
        else if (restSince > 0 && Date.now() - restSince >= (inNotchRect ? REST_NOTCH_MS : REST_MS)) {
          restSince = -1 // once per rest
          ctx.broadcast('overlay:wake')
        }
        return
      }
      const now = (shown && within(p, island, inNotch, d.y, shared)) || (hits ?? ctx.overlayRects()).some((r) => within(p, r, inNotch, d.y, shared))
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
