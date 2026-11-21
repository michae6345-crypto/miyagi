/**
 * Main-process side of the overview (renderer: src/renderer/src/features/overview/).
 *
 * Handles (bridge.invoke):
 *   overview:open-stats  the footer's "Stats" link → the engine's live stats page (Tiger Data track) in the default
 *                        browser. Same host as ENGINE_URL (ws://host:port → http://host:port/stats). It opens through
 *                        safeOpenExternal (app-harden), which takes only a loopback /stats page: an engine on another
 *                        host (the venue Wi-Fi setup) no longer opens from here.
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { defineMainFeature } from '../context'
import { safeOpenExternal } from '../safeOpen'

export function statsUrl(engineUrl = process.env.ENGINE_URL ?? 'ws://localhost:8787'): string | undefined {
  try {
    return new URL('/stats', engineUrl.replace(/^ws(s?):/i, 'http$1:')).href
  } catch {
    return undefined
  }
}

export default defineMainFeature({
  id: 'overview',
  setup(ctx) {
    ctx.handle('overview:open-stats', () => {
      const url = statsUrl()
      return url ? safeOpenExternal(url) : false
    })
  }
})
