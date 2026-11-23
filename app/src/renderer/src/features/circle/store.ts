/**
 * Feature: circle (renderer). Circle to ask: hold the push-to-talk keys, circle anything on screen, say a question (or
 * nothing), let go. The words and the circled region go to the engine as one ask; the answer sits beside the circle.
 *
 * What this file does around the pure machine (machine.ts):
 *   - follows push to talk (features/ptt usePtt): a hold arms the circle, a release seals it;
 *   - while armed, and ONLY then, the overlay takes the mouse (ui:emit 'overlay:interactive' {on: true, leaseMs},
 *     re-said every REASSERT_MS because core's hover tracking may say "no" when the pointer leaves a card mid-stroke;
 *     main drops the grab itself if the lease runs out, so a hung renderer cannot keep the screen). Every way out
 *     (release, Esc, blur, the 8 s cap, an engine drop) says click-through again, once;
 *   - from the hold to the answer's close, holds "away" off (shortcut-bar/front holdAwake), so the overlay never turns
 *     click-through under a stroke or under the answer's X;
 *   - takes the session's final words before push to talk routes them (ptt claimFinals), so they are not asked twice
 *     (late ones, after "What is this?" went, are dropped);
 *   - sends action ask {text, region, source: "circle", askId}; the region is screen points (layout.origin added) with
 *     the display's id and scale factor (layout.scaleFactor from main: devicePixelRatio would include page zoom);
 *   - takes the answer card {kind: "answer", askId} (features/cards skips it: circleOwnsCard, also once the circle
 *     closed that ask, so a card that lands after the X is not shown again in the island) and closes on its X, a
 *     new hold, a lesson ending, the engine dropping, or ANSWER_MS. Esc closes it only where the key reaches this
 *     window (the stage): in Electron the overlay never has focus and main does not relay Esc (a core request). Other
 *     cards' close ('dismiss') leaves the circle alone;
 *   - with the engine link down when the hold seals, sends nothing: the ink goes and the pill says so;
 *   - captures early (capture.ts): when a stroke is done while the keys are still held, asks main for a JPEG of that
 *     region at once (bridge.invoke('ptt:capture', region)), and sends it as the ask's `capture` only if it already
 *     settled ok for the very region asked about. Never waits for it; releases every ok capture it will not send;
 *   - streams the answer: answer.delta text for the ask on screen fills the answer card as it comes ("Looking" until
 *     the first words). The final card replaces it. Esc, the card's X or a new hold drops the stream.
 *
 * Inert until the layer mounts (setLayout): features/cards and features/tips import this even when the circle feature
 * is off, and a hold must never take the screen's mouse with nothing there to draw on. Overlay window only (Electron):
 * the launcher and the other windows import this too, and stay inert.
 * The crop is the engine's: the app sends a box and, at most, the path of a file main's helper wrote; never pixels.
 */
import { create } from 'zustand'
import type { Layout } from '../../../../preload/api'
import { cmd } from '../../../../common/wire'
import { bridge, isElectron } from '../../bridge'
import { onMessage, type PayloadOf } from '../../core/bus'
import { notify, useLesson } from '../../core/lesson'
import { usePressed } from '../../core/shortcuts'
import { claimFinals, usePtt } from '../ptt/store'
import { holdAwake } from '../shortcut-bar/front'
import type { CaptureResult } from '../../../../main/pttProtocol'
import { createCaptureTracker } from './capture'
import { strokeBox, toRegion, type Pt } from './geometry'
import { IDLE, interactive, step, type CircleEvent, type CircleState } from './machine'

/** How often the overlay's "take the mouse" is said again while armed. */
export const REASSERT_MS = 200
/** How often the timers (8 s cap, words wait, answer hold) are checked while something is on screen. */
const TICK_MS = 150
/** How long main keeps the grab without hearing it again (the lease; re-said every REASSERT_MS). */
export const LEASE_MS = 1000
/** The pill's line when the engine link is down as the circle is sealed. */
export const OFFLINE = "miyagi isn't connected yet. Try again soon."

type Store = {
  state: CircleState
  /** The overlay's layout as the layer last saw it (origin, size, displayId, scaleFactor). Unset: no layer, inert. */
  layout?: LayerLayout
  /** Circles asked this run (the tip's "done"). */
  asked: number
}

type LayerLayout = Pick<Layout, 'origin' | 'width' | 'height' | 'displayId' | 'scaleFactor'>

export const useCircle = create<Store>(() => ({ state: IDLE, asked: 0 }))
const get = useCircle.getState
const set = useCircle.setState

/** Only the overlay draws and asks (every window hears push to talk's broadcasts). */
const isOverlay = (): boolean => !isElectron || document.documentElement.dataset.route === 'overlay'

let seq = 0
const newId = (): string => `circle-${Date.now().toString(36)}-${++seq}`

/** The layer reports its layout (and the stage's CSS scale is undone before points reach here). It also turns the store on. */
export function setLayout(l: LayerLayout): void {
  const cur = get().layout
  if (cur && cur.width === l.width && cur.height === l.height && cur.origin.x === l.origin.x && cur.origin.y === l.origin.y && cur.displayId === l.displayId && cur.scaleFactor === l.scaleFactor) return
  set({ layout: { origin: l.origin, width: l.width, height: l.height, displayId: l.displayId, scaleFactor: l.scaleFactor } })
}

/** The layer went away: drop whatever was on screen (the mouse goes back) and go inert again. */
export function layerGone(): void {
  cancelCircle()
  set({ layout: undefined })
}

/** The display's backing scale from main; the browser stage has none, so it falls back to the page's ratio there. */
const scaleOf = (l: LayerLayout): number => {
  if (l.scaleFactor && l.scaleFactor > 0) return l.scaleFactor
  return typeof window !== 'undefined' && window.devicePixelRatio > 0 ? window.devicePixelRatio : 1
}

/** The early capture (Electron only: the browser stage has no helper, so it never asks). */
const captures = createCaptureTracker({
  capture: (region) => bridge.invoke<CaptureResult>('ptt:capture', region),
  release: (id) => {
    bridge.invoke('ptt:capture-release', id).catch(() => undefined)
  }
})

/** Holds whose ask already went out: their words, however late, are never routed again. */
const spent = new Set<string>()

/** How many closed asks are remembered (their late cards are swallowed, not shown in the island). */
const CLOSED_MAX = 20
/**
 * Asks the circle closed before or after their card (the X, Esc, a new hold, the ask timeout, the engine dropping): a
 * card that comes later for one of these is the circle's still, and goes nowhere. Oldest first; bounded.
 */
const closed = new Set<string>()
function rememberClosed(askId: string): void {
  closed.delete(askId)
  closed.add(askId)
  while (closed.size > CLOSED_MAX) closed.delete(closed.values().next().value as string)
}

/** Run one event through the machine and do what it says. Returns whether push to talk's words were taken. */
export function feed(e: CircleEvent): boolean {
  if (!isOverlay()) return false
  const l = get().layout
  // No layer mounted (the feature is off, or not drawn yet): nothing to draw on, so never take the mouse. A cancel
  // still settles, so the layer going away hands back whatever it had.
  if (!l && e.t !== 'cancel') return false
  const area = l ?? { origin: { x: 0, y: 0 }, width: innerWidth, height: innerHeight }
  const before = get().state
  const r = step(before, e, { now: Date.now(), width: area.width, height: area.height, newId })
  if (r.state !== before) set({ state: r.state })
  // The ask on screen went away (closed, timed out, replaced): its card, if it still comes, must not show again.
  if ((before.k === 'asking' || before.k === 'answered') && !((r.state.k === 'asking' || r.state.k === 'answered') && r.state.askId === before.askId)) rememberClosed(before.askId)
  if ((r.state.k === 'asking' || r.state.k === 'answered') && !spent.has(r.state.session)) {
    if (spent.size > 20) spent.clear()
    spent.add(r.state.session)
  }
  const now = r.state
  // A new hold, or nothing on screen any more: no ask will use what was captured.
  if ((now.k === 'idle' && before.k !== 'idle') || (now.k === 'armed' && (before.k !== 'armed' || before.session !== now.session))) captures.drop()
  // A stroke is done and the keys are still held: capture what it circles now, so the file is ready at release.
  if (e.t === 'up' && isElectron && before.k === 'armed' && before.down && now.k === 'armed') {
    const box = strokeBox(now.strokes, area.width, area.height)
    if (box) captures.begin(toRegion(box, area.origin, scaleOf(area), area.displayId))
  }
  if (r.ask && !useLesson.getState().connected) {
    // Nothing is listening (never connected, or the link is down): no ask into the void, no 30 s "Looking".
    captures.drop()
    set({ state: IDLE })
    notify(OFFLINE)
  } else if (r.ask) {
    const region = toRegion(r.ask.box, area.origin, scaleOf(area), area.displayId)
    // Only a capture that is already here and of this very region; never waited for (the engine grabs its own frame).
    const capture = captures.take(region)
    // Core request: sendAction(kind, text) has no room for region / source / askId yet. Recording the press keeps the
    // "never look dead" spinner rule (what sendAction would do), then the full ask goes out as the contract says.
    usePressed.setState({ kind: 'ask', at: Date.now() })
    bridge.send(cmd('action', { kind: 'ask', text: r.ask.text, region, source: 'circle', askId: r.ask.askId, ...(capture ? { capture } : {}) }))
    set((s) => ({ asked: s.asked + 1 }))
  }
  if (r.timedOut) notify('No answer yet. Try again.')
  sync()
  // A late final for a hold that was already asked about (and closed since): dropped too.
  return !!r.claimed || (e.t === 'final' && spent.has(e.id))
}

// ---- the overlay's mouse ----

let wantMouse = false
let reassert: ReturnType<typeof setInterval> | undefined
let ticker: ReturnType<typeof setInterval> | undefined
let lastSaid = 0

function sayInteractive(on: boolean): void {
  lastSaid = Date.now()
  // Taking the mouse is a lease: main gives it back itself if it is not said again within LEASE_MS.
  bridge.emit('overlay:interactive', on ? { on: true, leaseMs: LEASE_MS } : false)
}

/** The pointer moved over the drawing layer: say "mine" again if it has been a moment (core may have said no). */
export function keepMouse(): void {
  if (wantMouse && Date.now() - lastSaid > REASSERT_MS / 2) sayInteractive(true)
}

/** Match the overlay's mouse and the timers to the state. Idempotent. */
function sync(): void {
  const s = get().state
  const want = interactive(s)
  // Away (another app in front a while) makes main undo any hover and turns the whole overlay click-through. From the
  // hold to the answer's close it must not start: not under a stroke, not under the answer's X. Set before the mouse.
  holdAwake(s.k !== 'idle')
  if (want !== wantMouse) {
    wantMouse = want
    clearInterval(reassert)
    reassert = undefined
    if (want) {
      sayInteractive(true)
      reassert = setInterval(() => sayInteractive(true), REASSERT_MS)
    } else sayInteractive(false)
  }
  const ticking = s.k !== 'idle'
  if (ticking && !ticker) ticker = setInterval(() => feed({ t: 'tick' }), TICK_MS)
  else if (!ticking && ticker) {
    clearInterval(ticker)
    ticker = undefined
  }
}

// ---- inputs ----

/** Pointer input from the layer, in overlay px. */
export const pointerDown = (p: Pt): void => void feed({ t: 'down', p })
export const pointerMove = (p: Pt): void => {
  keepMouse()
  feed({ t: 'move', p })
}
export const pointerUp = (): void => void feed({ t: 'up' })
/** Esc, the card's X. */
export const cancelCircle = (): void => void feed({ t: 'cancel' })

/** For tests: which of the store's timers run (the mouse's re-say while armed, the state ticker). */
export const timersRunning = (): { reassert: boolean; ticker: boolean } => ({ reassert: reassert !== undefined, ticker: ticker !== undefined })

// Push to talk: every state (main's broadcast and the stage's mock both land in usePtt).
usePtt.subscribe((s, prev) => {
  if (s.ptt === prev.ptt) return
  const p = s.ptt
  if (p.phase === prev.ptt.phase && p.id === prev.ptt.id && p.lastCancel === prev.ptt.lastCancel && p.released === prev.ptt.released) return
  feed({ t: 'ptt', phase: p.phase, id: p.id, lastCancel: p.lastCancel, released: p.released })
})
// The final words: offered here before push to talk routes them as a plain ask or a launcher prefill.
claimFinals((f) => feed({ t: 'final', id: f.id, text: f.text }))

// The answer. features/cards skips the ones this owns (circleOwnsCard), so it shows once, beside the circle.
onMessage('card', (c) => {
  if (c.kind !== 'answer') return
  feed({ t: 'answer', askId: c.askId, answer: { title: c.title || undefined, body: c.body ?? '' } })
})

// The answer as it is written (contract answer.delta): only the ask on screen takes it (machine.ts drops the rest).
onMessage('answer.delta', (d) => {
  if (!d || typeof d.askId !== 'string') return
  feed({ t: 'delta', askId: d.askId, text: typeof d.text === 'string' ? d.text : '', done: d.done === true })
})

/** For tests: the early capture's newest state. */
export const captureState = (): ReturnType<typeof captures.peek> => captures.peek()

/**
 * features/cards asks: is this card the answer to a circle's ask? (Then cards leaves it to the circle.) True for the ask
 * on screen and for one the circle already closed: its card is late, and the learner has seen or dropped it.
 */
export function circleOwnsCard(c: PayloadOf<'card'>): boolean {
  if (c.kind !== 'answer' || !c.askId) return false
  const s = get().state
  return ((s.k === 'asking' || s.k === 'answered') && s.askId === c.askId) || closed.has(c.askId)
}

// Not onUi('dismiss'): that is every other card's close (core/ui/atoms CloseButton, features/complete), and closing one
// of those must not wipe a circle and its answer. The circle closes on its own X (and Esc where the key arrives).
onMessage('lesson.ended', cancelCircle)
// The engine link dropped: nothing will answer, and the mouse must go back.
let wasConnected = useLesson.getState().connected
useLesson.subscribe((s) => {
  if (wasConnected && !s.connected) cancelCircle()
  wasConnected = s.connected
})

if (typeof window !== 'undefined') {
  window.addEventListener('blur', () => feed({ t: 'blur' }))
  document.addEventListener('visibilitychange', () => document.hidden && feed({ t: 'blur' }))
  // The overlay never has focus in Electron and main relays no Esc, so after release this works in the stage only (and
  // if the overlay ever does get focus). While the keys are held, push to talk's own Esc cancel drops the circle.
  window.addEventListener('keydown', (e) => e.key === 'Escape' && get().state.k !== 'idle' && cancelCircle())
}
