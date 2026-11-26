/**
 * "Hide miyagi overlays" (Michael, Nov 25; state: main/overlayHide.ts).
 *
 *   key          ⌃⌥M (Alt+M on Windows, common/shortcuts.ts hideOverlaysAccelerator), registered while the launch gate is
 *                open (main/gate.ts), like the launcher key. Never activates miyagi: the overlay and player are
 *                non-activating panels and only change what they draw.
 *   menu bar     features/launch.ts: "Hide miyagi overlays" / "Show miyagi overlays", with the key shown.
 *   overlays:hidden  → boolean (bridge.invoke), and broadcast feat:overlays:hidden on every change (every window).
 *   overlays:toggle  (on?: boolean) from a renderer (a control on a surface); no argument flips it. → the state now.
 *
 * While hidden the overlay ignores the mouse (clicks go to the learner's app) and overlay-raise grabs nothing. Hidden
 * lasts while the lesson runs; it ends with the lesson (lesson.ended, except "interrupted": an engine deploy that
 * comes back with the same lesson) and when the gate closes (a sign-out), so the next lesson starts with everything
 * on screen.
 */
import { globalShortcut } from 'electron'
import { hideOverlaysAccelerator } from '../../common/shortcuts'
import { defineMainFeature } from '../context'
import { onGate, gateIsOpen } from '../gate'
import { onOverlaysHidden, overlaysHidden, setOverlaysHidden, toggleOverlaysHidden } from '../overlayHide'

export default defineMainFeature({
  id: 'overlay-hide',
  setup(ctx) {
    const key = hideOverlaysAccelerator(ctx.platform.os === 'mac')

    onOverlaysHidden((hidden) => {
      // Click-through at once (the renderer stops reporting its controls a tick later).
      if (hidden && !ctx.overlay.isDestroyed()) ctx.overlay.setIgnoreMouseEvents(true, { forward: true })
      ctx.broadcast('overlays:hidden', hidden)
    })
    ctx.handle('overlays:hidden', () => overlaysHidden())
    ctx.handle('overlays:toggle', (on) => (typeof on === 'boolean' ? setOverlaysHidden(on) : toggleOverlaysHidden()))

    let bound = false
    const bind = (open: boolean): void => {
      if (open && !bound) {
        bound = globalShortcut.register(key, () => void toggleOverlaysHidden())
        if (!bound) console.warn(`[overlay-hide] ${key} is taken: hide from the menu bar item`)
      } else if (!open && bound) {
        globalShortcut.unregister(key)
        bound = false
      }
      if (!open) setOverlaysHidden(false)
    }
    bind(gateIsOpen())
    onGate((open) => bind(open))

    ctx.engine.onEvent((e) => {
      if (e.type !== 'lesson.ended') return
      if ((e.payload as { reason?: string } | undefined)?.reason === 'interrupted') return
      setOverlaysHidden(false)
    })
  }
})
