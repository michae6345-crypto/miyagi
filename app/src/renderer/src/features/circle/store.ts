/**
 * Feature: circle (renderer). Circle to ask: hold the push-to-talk keys, circle anything on screen, say a question (or
 * nothing), let go. The words and the circled region go to the engine as one ask; the answer sits beside the circle.
 *
 * What this file does around the pure machine (machine.ts):
 *   - follows push to talk (features/ptt usePtt): a hold arms the circle, a release seals it;
 *   - while armed, and ONLY then, the overlay takes the mouse (ui:emit 'overlay:interactive', re-said every
 *     REASSERT_MS because core's hover tracking may say "no" when the pointer leaves a card mid-stroke). Every way out
 *     (release, Esc, blur, the 8 s cap, an engine drop) says click-through again, once;
 *   - takes the session's final words before push to talk routes them (ptt claimFinals), so they are not asked twice;
 *   - sends action ask {text, region, source: "circle", askId}; the region is screen points (layout.origin added) with
 *     the display's scale and id;
 *   - takes the answer card {kind: "answer", askId} (features/cards skips it: circleOwnsCard) and closes on its X, a
 *     new hold, a lesson ending, the engine dropping, or ANSWER_MS. Esc closes it only where the key reaches this
 *     window (the stage): in Electron the overlay never has focus and main does not relay Esc (a core request). Other
 *     cards' close ('dismiss') leaves the circle alone. While the answer shows, "away" is woken so its X stays
 *     clickable;
 *   - with the engine link down when the hold seals, sends nothing: the ink goes and the pill says so.
 *
 * Overlay window only (Electron): the launcher and the other windows import this too, and stay inert.
 * The crop is the engine's: the app sends a box, never pixels.
 */
import { create } from 'zustand'
import type { Layout } from '../../../../preload/api'
import { cmd } from '../../../../common/wire'
import { bridge, isElectron } from '../../bridge'
import { onMessage, type PayloadOf } from '../../core/bus'
import { notify, useLesson } from '../../core/lesson'
import { usePressed } from '../../core/shortcuts'
import { claimFinals, usePtt } from '../ptt/store'
import { useFront, wake } from '../shortcut-bar/front'
import { toRegion, type Pt } from './geometry'
import { IDLE, interactive, step, type CircleEvent, type CircleState } from './machine'

/** How often the overlay's "take the mouse" is said again while armed. */
export const REASSERT_MS = 200
/** How often the timers (8 s cap, words wait, answer hold) are checked while something is on screen. */
const TICK_MS = 150
/** The pill's line when the engine link is down as the circle is sealed. */
export const OFFLINE = "miyagi can't see the screen yet."

type Store = {
  state: CircleState
  /** The overlay's layout as the layer last saw it (origin, size, displayId). */
  layout?: Pick<Layout, 'origin' | 'width' | 'height' | 'displayId'>
  /** Circles asked this run (the tip's "done"). */
  asked: number
}

export const useCircle = create<Store>(() => ({ state: IDLE, asked: 0 }))
const get = useCircle.getState
const set = useCircle.setState

/** Only the overlay draws and asks (every window hears push to talk's broadcasts). */
const isOverlay = (): boolean => !isElectron || document.documentElement.dataset.route === 'overlay'

let seq = 0
const newId = (): string => `circle-${Date.now().toString(36)}-${++seq}`

/** The layer reports its layout (and the stage's CSS scale is undone before points reach here). */
export function setLayout(l: Pick<Layout, 'origin' | 'width' | 'height' | 'displayId'>): void {
  const cur = get().layout
  if (cur && cur.width === l.width && cur.height === l.height && cur.origin.x === l.origin.x && cur.origin.y === l.origin.y && cur.displayId === l.displayId) return
  set({ layout: { origin: l.origin, width: l.width, height: l.height, displayId: l.displayId } })
}

const scale = (): number => (typeof window !== 'undefined' && window.devicePixelRatio > 0 ? window.devicePixelRatio : 1)

/** Run one event through the machine and do what it says. Returns whether push to talk's words were taken. */
export function feed(e: CircleEvent): boolean {
  if (!isOverlay()) return false
  const l = get().layout ?? { origin: { x: 0, y: 0 }, width: innerWidth, height: innerHeight }
  const before = get().state
  const r = step(before, e, { now: Date.now(), width: l.width, height: l.height, newId })
  if (r.state !== before) set({ state: r.state })
  if (r.ask && !useLesson.getState().connected) {
    // Nothing is listening (never connected, or the link is down): no ask into the void, no 30 s "Looking".
    set({ state: IDLE })
    notify(OFFLINE)
  } else if (r.ask) {
    const region = toRegion(r.ask.box, l.origin, scale(), l.displayId)
    // Core request: sendAction(kind, text) has no room for region / source / askId yet. Recording the press keeps the
    // "never look dead" spinner rule (what sendAction would do), then the full ask goes out as the contract says.
    usePressed.setState({ kind: 'ask', at: Date.now() })
    bridge.send(cmd('action', { kind: 'ask', text: r.ask.text, region, source: 'circle', askId: r.ask.askId }))
    set((s) => ({ asked: s.asked + 1 }))
  }
  if (r.timedOut) notify('No answer yet. Try again.')
  sync()
  return !!r.claimed
}

// ---- the overlay's mouse ----

let wantMouse = false
let reassert: ReturnType<typeof setInterval> | undefined
let ticker: ReturnType<typeof setInterval> | undefined
let lastSaid = 0

function sayInteractive(on: boolean): void {
  lastSaid = Date.now()
  bridge.emit('overlay:interactive', on)
}

/** The pointer moved over the drawing layer: say "mine" again if it has been a moment (core may have said no). */
export function keepMouse(): void {
  if (wantMouse && Date.now() - lastSaid > REASSERT_MS / 2) sayInteractive(true)
}

/** Match the overlay's mouse and the timers to the state. Idempotent. */
function sync(): void {
  const s = get().state
  const want = interactive(s)
  if (want !== wantMouse) {
    wantMouse = want
    clearInterval(reassert)
    reassert = undefined
    if (want) {
      // Away (another app in front a while) makes main undo any hover: end it first, then take the mouse.
      if (useFront.getState().away) wake()
      sayInteractive(true)
      reassert = setInterval(() => {
        if (useFront.getState().away) wake()
        sayInteractive(true)
      }, REASSERT_MS)
    } else sayInteractive(false)
  }
  // Away makes the whole overlay click-through: the answer's X must stay clickable while it shows.
  if (s.k === 'answered' && useFront.getState().away) wake()
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

/** features/cards asks: is this card the answer to a circle on screen? (Then cards leaves it to the circle.) */
export function circleOwnsCard(c: PayloadOf<'card'>): boolean {
  const s = get().state
  return c.kind === 'answer' && !!c.askId && (s.k === 'asking' || s.k === 'answered') && s.askId === c.askId
}

// Not onUi('dismiss'): that is every other card's close (core/ui/atoms CloseButton, features/complete), and closing one
// of those must not wipe a circle and its answer. The circle closes on its own X (and Esc where the key arrives).
onMessage('lesson.ended', cancelCircle)
// Away turned on while the answer shows: wake at once (sync() also checks on every tick).
useFront.subscribe((f, prev) => {
  if (f.away && !prev.away && get().state.k === 'answered') wake()
})
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
