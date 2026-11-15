/**
 * Crash recovery (Michael's live test, Sat 3:47 PM: "GPU process exited unexpectedly", then "renderer gone: killed"
 * for overlay / launcher / player, and the app was dead on screen).
 *
 * Electron restarts the GPU process by itself, but a window whose renderer died stays blank until it reloads.
 * So: reload it in place (same window, route and bounds). On load the renderer sends `ui:ready` and main replays
 * the engine log (core), so the lesson, step and cards come back as they were.
 *
 *   app 'render-process-gone' (one of our windows, not a clean exit) → reload after 300 ms, at most 3 times a
 *                                   minute per window, so a renderer that crashes on load can't loop.
 *   app 'child-process-gone' (GPU)  → logged; the renderers it takes down arrive as render-process-gone.
 *
 * Core logs render-process-gone in dev only; this adds the recovery, in every build. No core files touched.
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac by killing a
 * Miyagi renderer ("Miyagi Helper (Renderer)") in Activity Monitor: the window should come back within a second.
 */
import { app, BrowserWindow, type WebContents } from 'electron'
import { defineMainFeature } from '../context'

const PER_MS = 60_000
const MAX_RELOADS = 3
const reloads = new WeakMap<WebContents, number[]>()

function reloadSoon(wc: WebContents, reason: string): void {
  const now = Date.now()
  const recent = (reloads.get(wc) ?? []).filter((t) => now - t < PER_MS)
  if (recent.length >= MAX_RELOADS) {
    console.error(`[recover] renderer keeps dying (${reason}); not reloading it again for a minute`)
    return
  }
  reloads.set(wc, [...recent, now])
  setTimeout(() => {
    if (wc.isDestroyed()) return
    console.warn(`[recover] renderer gone (${reason}); reloading ${wc.getURL().split('#')[1] ?? ''}`)
    wc.reload()
  }, 300)
}

export default defineMainFeature({
  id: 'recover',
  setup() {
    app.on('render-process-gone', (_e, wc, details) => {
      if (details.reason === 'clean-exit') return
      if (!BrowserWindow.fromWebContents(wc)) return // only our own windows
      reloadSoon(wc, details.reason)
    })
    app.on('child-process-gone', (_e, details) => {
      if (details.type === 'GPU') console.error(`[recover] GPU process gone: ${details.reason} (exit ${details.exitCode})`)
    })
  }
})
