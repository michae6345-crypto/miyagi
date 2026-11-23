/**
 * Main-process side of the overview (renderer: src/renderer/src/features/overview/).
 *
 * Handles (bridge.invoke):
 *   overview:open-stats  the footer's "Stats" link → the engine's live stats page (Tiger Data track) in the default
 *                        browser. Same host as ENGINE_URL (ws://host:port → http://host:port/stats). It opens only a
 *                        loopback /stats page on the engine's own port (safeOpen.ts isEngineStatsUrl, then
 *                        openEngineStats; app-harden): an engine on another host (the venue Wi-Fi setup) no longer opens
 *                        from here. The general open:external IPC never opens a loopback page.
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac.
 */
import { defineMainFeature } from '../context'
import { isEngineStatsUrl, openEngineStats } from '../safeOpen'

const engineUrl = (): string => process.env.ENGINE_URL ?? 'ws://localhost:8787'

export function statsUrl(url = engineUrl()): string | undefined {
  try {
    return new URL('/stats', url.replace(/^ws(s?):/i, 'http$1:')).href
  } catch {
    return undefined
  }
}

/** The engine's port, read the way main/localEngine.ts reads it (no port in ENGINE_URL = 8787). */
export function enginePort(url = engineUrl()): number {
  try {
    return Number(new URL(url).port) || 8787
  } catch {
    return 8787
  }
}

export default defineMainFeature({
  id: 'overview',
  setup(ctx) {
    ctx.handle('overview:open-stats', () => {
      const url = statsUrl()
      const port = enginePort()
      return url && isEngineStatsUrl(url, port) ? openEngineStats(url, port) : false
    })
  }
})
