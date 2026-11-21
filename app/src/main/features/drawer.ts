/**
 * Main-process side of the drawer (renderer: src/renderer/src/features/drawer/).
 *
 * Handles (bridge.invoke):
 *   drawer:copy  the current step's Copy button → the system clipboard. The overlay window is focusable: false, and
 *                Chromium refuses both navigator.clipboard and execCommand('copy') in an unfocused document (checked
 *                in headless Brave: "Document is not focused", execCommand → false), so the renderer can't copy alone.
 *
 * UNVERIFIED in Electron (typechecked only; the browser stage uses the web handler in features/drawer/plan.ts).
 */
import { clipboard } from 'electron'
import { defineMainFeature } from '../context'

/** The full code of one step, never a whole file dump. */
const MAX_CHARS = 100_000

export default defineMainFeature({
  id: 'drawer',
  setup(ctx) {
    ctx.handle('drawer:copy', (text) => {
      if (typeof text !== 'string' || !text || text.length > MAX_CHARS) return false
      clipboard.writeText(text)
      return true
    })
  }
})
