/**
 * Main-process side of the overview (renderer: src/renderer/src/features/overview/).
 *
 * Handles (bridge.invoke):
 *   overview:open-stats  the footer's "Stats" link → the engine's live stats page (Tiger Data track) in the default
 *                        browser. Same host as ENGINE_URL (ws://host:port → http://host:port/stats), so it works when
 *                        the engine runs on Michael's Mac and the app connects over the venue Wi-Fi.
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { shell } from 'electron'
import { defineMainFeature } from '../context'

function statsUrl(): string {
  const ws = process.env.ENGINE_URL ?? 'ws://localhost:8787'
  return new URL('/stats', ws.replace(/^ws(s?):/i, 'http$1:')).href
}

export default defineMainFeature({
  id: 'overview',
  setup(ctx) {
    ctx.handle('overview:open-stats', () => {
      const url = statsUrl()
      if (!/^https?:\/\//i.test(url)) return false
      void shell.openExternal(url)
      return true
    })
  }
})
