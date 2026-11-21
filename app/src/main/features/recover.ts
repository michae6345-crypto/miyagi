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
 *   webContents 'did-fail-load' (main frame: the dev server is down, ERR_CONNECTION_REFUSED) → a loud log line and
 *                                   a retry of the same URL every 2 s until it loads (Michael's test 7, item 10: the
 *                                   overlay stayed blank while main lived, a silent failure on stage).
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

const RETRY_MS = 2_000
/** Chromium's ERR_ABORTED: a navigation replaced by another one (a reload, a hash change), not a failure. */
const ABORTED = -3
const retrying = new WeakSet<WebContents>()

function retryLoad(wc: WebContents, url: string, code: number, desc: string): void {
  if (retrying.has(wc)) return
  retrying.add(wc)
  console.error(`[recover] !!! window failed to load ${url} (${desc}, ${code}); retrying every ${RETRY_MS / 1000} s`)
  setTimeout(() => {
    retrying.delete(wc)
    if (wc.isDestroyed()) return
    wc.loadURL(url).catch(() => undefined) // a new failure arrives as did-fail-load and schedules the next try
  }, RETRY_MS)
}

const watched = new WeakSet<WebContents>()

function watchLoads(win: BrowserWindow): void {
  const wc = win.webContents
  if (watched.has(wc)) return
  watched.add(wc)
  let failed = false
  wc.on('did-fail-load', (_ev, code, desc, url, isMainFrame) => {
    if (!isMainFrame || code === ABORTED || !url) return
    failed = true
    retryLoad(wc, url, code, desc)
  })
  wc.on('did-finish-load', () => {
    if (!failed || retrying.has(wc)) return
    failed = false
    console.warn(`[recover] window loaded again: ${wc.getURL()}`)
  })
}

export default defineMainFeature({
  id: 'recover',
  setup() {
    app.on('render-process-gone', (_e, wc, details) => {
      if (details.reason === 'clean-exit') return
      if (!BrowserWindow.fromWebContents(wc)) return // only our own windows
      reloadSoon(wc, details.reason)
    })
    // The overlay and launcher exist before features load: watch them, and every window made later.
    for (const w of BrowserWindow.getAllWindows()) watchLoads(w)
    app.on('browser-window-created', (_e, win) => watchLoads(win))
    app.on('child-process-gone', (_e, details) => {
      if (details.type === 'GPU') console.error(`[recover] GPU process gone: ${details.reason} (exit ${details.exitCode})`)
    })
  }
})
