/**
 * Core: the launch splash (Michael, Nov 24: "don't go straight to the app"). A cold launch shows a window in exactly
 * the home window's frame (appWindows.appWindowFrame: same size, same place, never the whole display), in the app's
 * own paper (cream in light, the app's dark base in dark). The "miyagi" wordmark rises in letter by letter, and the
 * splash fades away onto the home window, which has opened and painted underneath it in the same frame.
 *
 * It is also the start-up's waiting room. Anything that should be ready before the learner sees the app calls
 * holdSplash(promise) (index.ts holds the overlay's first load, the first app window's first paint and the engine
 * link). The splash leaves once its animation has played (MIN_MS) and every hold has settled; each hold gives up after
 * its own cap, and the whole splash after MAX_MS, so a slow engine or a cache warm-up never strands anyone on it.
 *
 *   showSplash(frame)        cold launch: put the splash up in home's frame (index.ts, once the features have loaded)
 *   skipSplash()             no splash this launch (started at login, MIYAGI_QUIET_LAUNCH=1, MIYAGI_NO_SPLASH=1)
 *   holdSplash(p, maxMs?)    keep the splash up until p settles (at most maxMs); a no-op once it has left
 *   holdUntilPainted(win)    holdSplash until win's first paint (or its close)
 *
 * The page is a self-contained data: URL (inline CSS, the bundled Bricolage inlined), so it paints before the
 * renderer bundle has loaded. No preload, no IPC, sandboxed, nothing to click.
 */
import { BrowserWindow, nativeTheme, type Rectangle } from 'electron'
import bricolage from '../renderer/src/assets/fonts/BricolageGrotesque-latin.woff2?inline'
import { brand } from '../renderer/src/core/theme'
import { windowBackground } from './prefs'
import { overlayWindowOptions, raise } from './platform'

/** The wordmark's own animation plus a beat to read it: the splash never leaves before this. */
export const MIN_MS = 1800
/** Never longer than this, whatever is still loading. */
export const MAX_MS = 7000
/** The default cap on one hold. */
export const HOLD_MAX_MS = 4000
/** The leave animation (letters lift away, then the splash fades); the window closes after it. */
const LEAVE_MS = 700
/** A settled hold looks again a beat later, so a hold added in the same tick (home opens on the overlay's load) counts. */
const SETTLE_MS = 60

type State = 'idle' | 'up' | 'leaving' | 'done'
let state: State = 'idle'
let win: BrowserWindow | undefined
let shownAt = 0
let minTimer: ReturnType<typeof setTimeout> | undefined
let maxTimer: ReturnType<typeof setTimeout> | undefined
const pending = new Set<symbol>()

/** Keep the splash up until p settles, at most maxMs. Holds taken before the splash is up count too. */
export function holdSplash(p: Promise<unknown>, maxMs = HOLD_MAX_MS): void {
  if (state === 'leaving' || state === 'done') return
  const id = Symbol('hold')
  pending.add(id)
  const cap = setTimeout(release, maxMs)
  function release(): void {
    clearTimeout(cap)
    if (!pending.delete(id)) return
    setTimeout(check, SETTLE_MS)
  }
  p.then(release, release)
}

/** Hold until a window's first paint (ready-to-show) or its close, whichever comes first. */
export function holdUntilPainted(w: BrowserWindow): void {
  if (state === 'leaving' || state === 'done') return
  holdSplash(
    new Promise<void>((res) => {
      w.once('ready-to-show', () => res())
      w.once('closed', () => res())
    })
  )
}

/** No splash this launch: forget the holds. */
export function skipSplash(): void {
  if (state !== 'idle') return
  state = 'done'
  pending.clear()
}

/** Put the splash up in `frame`: the home window's frame, so it hands over in place. */
export function showSplash(frame: Rectangle): void {
  if (state !== 'idle') return
  state = 'up'
  shownAt = Date.now()
  const dark = nativeTheme.shouldUseDarkColors
  win = new BrowserWindow({
    ...overlayWindowOptions(frame),
    // The splash takes the clicks while it is up (nothing under it is meant to be used yet), but never the focus:
    // the home window underneath gets that.
    focusable: false,
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: false,
      devTools: false,
      backgroundThrottling: false
    }
  })
  const w = win
  w.once('ready-to-show', () => {
    if (w.isDestroyed() || state === 'done') return
    raise(w, 2) // over home while home paints underneath it
    w.setBounds(frame)
    w.showInactive()
  })
  w.on('closed', () => {
    if (win === w) win = undefined
    finish()
  })
  void w.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(splashPage(dark))}`)
  minTimer = setTimeout(check, MIN_MS)
  maxTimer = setTimeout(leave, MAX_MS)
}

function check(): void {
  if (state !== 'up') return
  if (Date.now() - shownAt < MIN_MS || pending.size > 0) return
  leave()
}

function leave(): void {
  if (state !== 'up') return
  state = 'leaving'
  clearTimeout(minTimer)
  clearTimeout(maxTimer)
  pending.clear()
  const w = win
  if (!w || w.isDestroyed()) return finish()
  w.setIgnoreMouseEvents(true) // the home window underneath is live from the first frame of the fade
  w.webContents.executeJavaScript("document.documentElement.classList.add('leave')").catch(() => undefined)
  setTimeout(() => {
    if (!w.isDestroyed()) w.destroy()
    finish()
  }, LEAVE_MS)
}

function finish(): void {
  state = 'done'
  clearTimeout(minTimer)
  clearTimeout(maxTimer)
  pending.clear()
}

const WORD = 'miyagi'

/** The splash page: inline CSS only (its CSP allows nothing else), the wordmark in the bundled Bricolage. */
export function splashPage(dark: boolean): string {
  const bg = windowBackground()
  const ink = dark ? '#ECEBE8' : brand.ink
  const faint = dark ? '#A3A29E' : brand.inkFaint
  const letters = [...WORD].map((c, i) => `<span style="--i:${i}">${c}</span>`).join('')
  return `<!doctype html>
<html lang="en"${dark ? ' class="dark"' : ''}>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; font-src data:">
<title>miyagi</title>
<style>
@font-face { font-family: "Bricolage Grotesque"; src: url(${bricolage}) format("woff2"); font-weight: 200 800; font-display: block; }
:root { --bg: ${bg}; --ink: ${ink}; --faint: ${faint}; --ease: cubic-bezier(.16, 1, .3, 1); }
html, body { margin: 0; height: 100%; overflow: hidden; background: transparent; cursor: default; -webkit-user-select: none; user-select: none; }
/* The paper lives on .win, not body (a body background would fill the whole transparent window, corners included). */
.win { position: fixed; inset: 0; display: grid; place-items: center; background: var(--bg); border-radius: 16px; transition: opacity .42s cubic-bezier(.4, 0, .2, 1) .2s; }
.mark { position: relative; display: flex; flex-direction: column; align-items: center; }
.word {
  display: flex; color: var(--ink);
  font-family: "Bricolage Grotesque", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  font-weight: 600; font-size: clamp(48px, 7.5vw, 104px); line-height: 1; letter-spacing: -0.04em;
  font-optical-sizing: auto; -webkit-font-smoothing: antialiased;
}
.word span {
  display: inline-block; opacity: 0; transform: translateY(.3em); filter: blur(10px);
  animation: rise .95s var(--ease) forwards; animation-delay: calc(140ms + var(--i) * 75ms);
}
@keyframes rise { to { opacity: 1; transform: none; filter: blur(0); } }
/* Still loading after the word has landed: a quiet hairline, one segment sweeping. */
.load {
  position: absolute; top: calc(100% + 34px); width: 88px; height: 2px; border-radius: 2px; overflow: hidden;
  background: color-mix(in srgb, var(--faint) 22%, transparent); opacity: 0;
  animation: show .5s ease 1.7s forwards;
}
.load::after {
  content: ""; position: absolute; inset: 0; width: 34%; border-radius: 2px; background: var(--faint);
  animation: sweep 1.15s cubic-bezier(.45, 0, .55, 1) infinite;
}
@keyframes show { to { opacity: 1; } }
@keyframes sweep { from { transform: translateX(-100%); } to { transform: translateX(300%); } }
/* Leaving: the letters lift away in order, then the splash fades onto home. */
.leave .win { opacity: 0; }
.leave .word span { animation: lift .36s cubic-bezier(.5, 0, .75, 0) forwards; animation-delay: calc(var(--i) * 28ms); }
.leave .load { animation: none; opacity: 0; transition: opacity .2s; }
@keyframes lift { from { opacity: 1; transform: none; filter: blur(0); } to { opacity: 0; transform: translateY(-.22em); filter: blur(8px); } }
@media (prefers-reduced-motion: reduce) {
  .word span { transform: none; filter: none; animation: show .5s ease forwards; animation-delay: 100ms; }
  .leave .word span { animation: none; opacity: 0; transition: opacity .3s; }
  .load::after { animation: none; width: 100%; opacity: .5; }
}
</style>
</head>
<body><div class="win"><div class="mark" aria-label="miyagi"><div class="word">${letters}</div><div class="load"></div></div></div></body>
</html>`
}
