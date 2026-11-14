/**
 * Main-process side of the drawer (renderer: src/renderer/src/features/drawer/).
 *
 * Handles (bridge.invoke from any window):
 *   drawer:open-url  (url) a source row was clicked → the default browser. http(s) only.
 *
 * Why not window.open: the overlay window has no setWindowOpenHandler (only the player's window does),
 * so window.open from the overlay would open a bare Electron window. See Core requests in agents/drawer.md.
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { shell } from 'electron'
import { defineMainFeature } from '../context'

function isWebLink(url: unknown): url is string {
  if (typeof url !== 'string') return false
  try {
    const u = new URL(url)
    return u.protocol === 'https:' || u.protocol === 'http:'
  } catch {
    return false
  }
}

export default defineMainFeature({
  id: 'drawer',
  setup(ctx) {
    ctx.handle('drawer:open-url', (url) => {
      if (!isWebLink(url)) return false
      void shell.openExternal(url)
      return true
    })
  }
})
