/**
 * Feature: buddy, pass 2. What the bonsai is pointing at right now, from the engine's `annotate` event (Michael's
 * contract, Nov 22: "Buddy draws"), and when each mark goes.
 *
 * The rules are the ones in Michael's features/annotate/store.ts (michael/app-buddy-draw), so a mark lives and dies
 * the same way whichever layer draws it:
 *   In   annotate {marks, holdMs?}  replaces what is drawn. A mark with a key already drawn keeps its stroke.
 *        annotate {clear: true}     fade everything now.
 *   Out  the marks fade, and stay gone for this step even if the engine re-sends them, when
 *        - the learner goes there (a click inside, or the pointer coming in and resting: marks.ts createReach),
 *        - the hold runs out (holdMs, or 6 s, from the newest mark's birth: a re-sent mark does not restart it),
 *        - Esc.
 *        A new circle-to-ask (a new askId) starts fresh. A new step keeps only the marks sent for that step and
 *        forgets what was gone; step.passed, the lesson ending and a reset clear everything.
 * Today's pointing, as in his store: until the engine has sent one `annotate`, every new spotlight box the spotlight
 * feature shows also gets a mark (why 'point', no label: the spotlight says its own words), so the buddy goes there
 * before the engine speaks annotate (spotlit, fed by wire.ts). When the spotlight hides, that mark goes with it and may
 * come back. A Show me press is an explicit ask, so its box is marked again even if the learner already reached it.
 *
 * Nothing here takes the mouse: the layer is click-through, always.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { sameRect, type Point, type Rect } from '../../core/geometry'
import { fadeAt, HOLD, holdFor, isDrawable, knownKey, mergeMarks, validMarks, type Known, type Mark, type Shown } from './marks'

/**
 * Where the buddy is. 'home': in the notch. 'out': flying somewhere. 'perched': sitting beside the mark `at` (its
 * key), its body at `body` (the overlay window's coordinates), which is where that mark's loop is thrown from.
 * 'follow': keeping the learner's pointer company. 'back': on its way home. Set by the buddy's layer
 * (Companion.tsx); read by the loop's layer.
 */
export type Trip = { phase: 'home' | 'out' | 'perched' | 'follow' | 'back'; at?: string; body?: Point }

/**
 * marks  screen points, as the engine sent them (the layers map them into their window).
 * lean   -1 to 1, which way the bonsai leans while it points (set by the layer, which knows where both ends are).
 * pose   a box another layer asked the bonsai to point at (pointAt), screen points; the layer leans toward it when
 *        it has no mark of its own.
 * trip   where the buddy is.
 * cheer  bumped each time the learner gets to a mark: the buddy hops.
 * total  how many marks the set now up started with. The buddy takes them one at a time, so with marks.length this
 *        is its place in the tour: step total - marks.length + 1 of total.
 * bridged  the marks now up are the spotlight's box (spotlit), not the engine's annotate. The spotlight rings that
 *        box itself and puts its caption to the right of it, so the buddy draws no loop there and sits on the left.
 */
export const usePointing = create<{ marks: Shown[]; lean: number; pose?: Rect; trip: Trip; cheer: number; total: number; bridged: boolean }>(() => ({ marks: [], lean: 0, trip: { phase: 'home' }, cheer: 0, total: 0, bridged: false }))
const get = usePointing.getState
const set = usePointing.setState

export function setTrip(trip: Trip): void {
  set({ trip })
}

/** Keys the learner reached, or that timed out or were cleared this step: a re-send does not draw them again. */
const gone = new Map<string, Known>()
/** The ask the current `gone` belongs to: a new circle-to-ask starts fresh. */
let lastAsk: string | undefined
let hold: ReturnType<typeof setTimeout> | undefined
/** The engine speaks annotate: spotlight boxes are no longer bridged. */
let engineAnnotates = false
/** The last spotlight box bridged, so the engine's re-reads of one box mark it once. */
let lastSpot: Rect | undefined
/** A spotlight box within this many px of the last one is the same box (the spotlight's own JITTER_PX). */
const SPOT_JITTER = 8

function stopHold(): void {
  clearTimeout(hold)
  hold = undefined
}

/** Fade these marks (or all of them), and remember them as gone for this step. */
export function fade(keys?: readonly string[]): void {
  const cur = get().marks
  const out = keys ? cur.filter((m) => keys.includes(m.key)) : cur
  if (!out.length) return
  out.forEach((m) => gone.set(m.key, m))
  const left = cur.filter((m) => !out.includes(m))
  set(left.length ? { marks: left } : { marks: left, total: 0 })
  if (!left.length) stopHold()
}

/** The learner went there (the pointer rested on these marks, or a press landed in them): the buddy cheers, and they fade. */
export function reached(keys: readonly string[]): void {
  if (!keys.length) return
  set((s) => ({ cheer: s.cheer + 1 }))
  fade(keys)
}

/** Back to blank: nothing drawn, nothing remembered (step.passed, a new lesson, a reset). */
export function forget(): void {
  stopHold()
  gone.clear()
  lastAsk = undefined
  lastSpot = undefined
  if (get().marks.length || get().total) set({ marks: [], total: 0 })
}

/**
 * Take the marks away without remembering them as gone: the thing they pointed at went away, the learner did not
 * reach it, so it may be marked again when it comes back.
 */
function withdraw(): void {
  stopHold()
  if (get().marks.length || get().total) set({ marks: [], total: 0 })
}

/**
 * Today's pointing: the spotlight feature now shows this box (screen points), or nothing (it hid: the engine cleared
 * it, or its app left the front). `again`: a Show me press asked for it. Does nothing once the engine sends annotate.
 */
export function spotlit(rect: Rect | undefined, again = false): void {
  if (engineAnnotates) return
  if (!rect) {
    lastSpot = undefined
    return withdraw()
  }
  if (!isDrawable(rect)) return
  const mark: Mark = { x: rect.x, y: rect.y, w: rect.w, h: rect.h, why: 'point' }
  if (again) {
    // Forget that it was reached or timed out, and let it be born again.
    for (let k = knownKey(mark, gone.values()); k !== undefined; k = knownKey(mark, gone.values())) gone.delete(k)
    const up = knownKey(mark, get().marks)
    if (up !== undefined) set({ marks: get().marks.filter((m) => m.key !== up) })
    lastSpot = undefined
  }
  if (lastSpot && sameRect(lastSpot, rect, SPOT_JITTER)) return
  lastSpot = rect
  if (!get().bridged) set({ bridged: true })
  show([mark])
}

/**
 * Draw `incoming` in place of what is drawn. The hold counts from the newest mark's birth (fadeAt), so a re-send of
 * marks already drawn keeps the old deadline and only a new mark moves it.
 */
export function show(incoming: readonly Mark[], holdMs: number = HOLD.base, now = Date.now()): void {
  const ask = incoming.find((m) => m.askId)?.askId
  if (ask && ask !== lastAsk) {
    gone.clear()
    lastAsk = ask
  }
  const prev = get().marks
  const marks = mergeMarks(prev, incoming, gone.values(), now)
  // A set with a mark that was not up before is a new tour; a re-send of the same ones is the same tour.
  const fresh = marks.some((m) => !prev.some((q) => q.key === m.key))
  set({ marks, total: marks.length ? (fresh ? marks.length : Math.max(get().total, marks.length)) : 0 })
  stopHold()
  const at = fadeAt(marks, holdMs)
  if (at !== undefined) hold = setTimeout(() => fade(), Math.max(0, at - now))
}

/** One `annotate` payload: { marks, holdMs? } or { clear: true }. Anything else is ignored. */
export function annotate(payload: unknown): void {
  engineAnnotates = true
  if (get().bridged) set({ bridged: false })
  if (!payload || typeof payload !== 'object') return
  const p = payload as { marks?: unknown; holdMs?: unknown; clear?: unknown }
  if (p.clear) return fade()
  if (!('marks' in p)) return
  show(validMarks(p.marks), holdFor(p.holdMs))
}

/**
 * The point pose, for a layer that draws its own stroke (Michael's features/annotate): the bonsai leans toward this
 * box (screen points, the spotlight.rect space) until pointAt() with nothing. Marks from `annotate` already do this
 * on their own; this is for anything else that layer circles, such as a spotlight box.
 */
export function pointAt(box?: Rect): void {
  if (get().pose !== box) set({ pose: box })
}

// `annotate` is in the contract branch (claude/contract-circle-ask) and not on this one yet, so the bus's MessageType
// does not know it. The bus is keyed by the type string: this cast goes when the contract lands (brief, Core requests).
;(onMessage as unknown as (type: string, fn: (payload: unknown) => void) => () => void)('annotate', annotate)

onMessage('step.started', (p) => {
  if (p?.replay) return // a reconnect's replay of the step already running: not a new step
  const keep = get().marks.filter((m) => m.stepId && m.stepId === p?.stepId)
  stopHold()
  gone.clear()
  lastSpot = undefined
  set({ marks: keep, total: keep.length })
  if (keep.length) hold = setTimeout(() => fade(), HOLD.base)
})
onMessage('step.passed', forget)
onMessage('lesson.ready', forget)
onMessage('lesson.ended', forget)
onUi('reset', () => {
  forget()
  engineAnnotates = false
})
onUi('dismiss', () => {
  fade() // Esc: the learner wants the screen back. Never claims the event, so cards still close.
})
