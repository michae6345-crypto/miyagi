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
 * Core logs render-process-gone in dev only; this adds the recovery, in every build.
 *
 * ROADMAP 1.4, reconnect and recovery (a lost socket, an engine crash or a Mac that slept never leaves dead UI):
 *   engine crash          the engine this app started dies while running → localEngine.ts asks setRespawnPolicy and
 *                         starts it again after 0.5 s, 2 s, 5 s (respawn.ts: at most 3 in 3 minutes; then it reports
 *                         the failure and the learner gets Retry). Meanwhile the surfaces say "miyagi is reconnecting".
 *   engine hung           ours, alive, but the link has been down HUNG_MS while the Mac is awake → restart it (same budget).
 *   Mac sleep / unlock    powerMonitor resume / unlock-screen → engine.wake(): probe an open socket (dead after a sleep
 *                         = dropped and reconnected at once) or try now with fast retries.
 *   lost socket           engine.ts: heartbeat pings, backoff reconnect.
 *   the session           nothing to send: on every connect the engine sends its snapshot (engine.hello.restored when it
 *                         kept the lesson: server/sessions resume), and core/lesson.ts holds the screen for the same lesson.
 *
 * UNVERIFIED: typechecked on Windows, where Smart App Control blocks electron.exe. Check on the Mac by killing a
 * Miyagi renderer ("Miyagi Helper (Renderer)") in Activity Monitor: the window should come back within a second.
 */
import { app, BrowserWindow, powerMonitor, type WebContents } from 'electron'
import { defineMainFeature, type MainContext } from '../context'
import { localEngineChildAlive, localEngineState, restartLocalEngine, setRespawnPolicy } from '../localEngine'
import { HUNG_MS, MAX_RESPAWNS, RespawnBudget } from '../respawn'

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

/** The engine side of recovery (see the header). */
function recoverEngine(ctx: MainContext): void {
  const budget = new RespawnBudget()
  setRespawnPolicy((why) => {
    const delay = budget.next()
    if (delay === undefined) console.error(`[recover] engine ${why} again; it keeps stopping, so it is reported (Retry starts it)`)
    else console.warn(`[recover] engine ${why}; starting it again in ${delay} ms (${budget.used()} of ${MAX_RESPAWNS})`)
    return delay
  })
  let hung: ReturnType<typeof setTimeout> | undefined
  let asleep = false
  const watchHung = (open: boolean): void => {
    clearTimeout(hung)
    hung = undefined
    if (open || asleep) return
    hung = setTimeout(() => {
      hung = undefined
      if (ctx.engine.connected || asleep) return
      if (localEngineState() !== 'running' || !localEngineChildAlive()) return
      const delay = budget.next()
      if (delay === undefined) return console.error('[recover] engine alive but not answering, and the restart budget is spent')
      console.warn(`[recover] engine alive but not answering for ${HUNG_MS / 1000} s; restarting it`)
      restartLocalEngine()
    }, HUNG_MS)
  }
  ctx.engine.onStatus((up) => {
    // A spent budget ends in a reported failure and Retry: an engine that answers again after that earns a fresh one.
    if (up && budget.used() >= MAX_RESPAWNS) budget.reset()
    watchHung(up)
  })
  powerMonitor.on('suspend', () => {
    asleep = true
    watchHung(true)
  })
  const woke = (): void => {
    asleep = false
    ctx.engine.wake()
    watchHung(ctx.engine.connected)
  }
  powerMonitor.on('resume', woke)
  powerMonitor.on('unlock-screen', () => ctx.engine.wake())
}

export default defineMainFeature({
  id: 'recover',
  setup(ctx) {
    recoverEngine(ctx)
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
