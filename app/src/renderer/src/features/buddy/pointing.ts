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
 * The step's target: every new spotlight box the spotlight feature shows (the engine's `spotlight` target, the same
 * source features/annotate used) also gets a mark (why 'point', no label: the spotlight says its own words), so bon
 * flies to the button or line the step is about, points at it and circles it in its color (spotlit, fed by wire.ts).
 * It holds SPOT_HOLD_MS, long enough to be seen (Adrian: longer than 6 s). The engine's own marks (`annotate`, today a
 * circle-to-ask answer) win while they are up; once they are gone, spotlight boxes are marked again. When the engine
 * clears the spotlight, its mark goes with it and may come back. When the spotlight only fades on its own (a video
 * lesson's calm dim goes after 4 s or a keystroke: spotlight/calm.ts), bon keeps pointing until its own hold is up.
 * A Show me press is an explicit ask, so its box is marked again even if the learner already reached it.
 * The on-screen coach (an app lesson, Nov 24): a "point" mark with text is the step's action. bon flies to it and circles
 * it; features/annotate still draws the text box beside the loop (its BuddyLayer draws only that when bon draws). Like
 * that store, a text mark is not timed: it stays while its step is live and goes when the step passes or changes, the
 * learner reaches it, Esc, annotate {clear}, or the lesson ends. A text mark for a step that is not running is not
 * drawn, and while the lesson is quiet (lesson.paused, a blocker, status idle) text marks are put aside and come back,
 * with no re-send, once it is live again and their step still runs. A "Not yet" for this step (card verdict not_done)
 * or a Show me press is an ask: the engine's next annotate is drawn even if the learner already reached it.
 *
 * Diagnostics (a live test can tell an engine that sent nothing from an app that dropped it): perf counters
 * buddy.spotlit (a box came), buddy.spotlit.engine-up / .undrawable / .same (dropped, and why), buddy.annotate.
 *
 * Nothing here takes the mouse: the layer is click-through, always.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { sameRect, type Point, type Rect } from '../../core/geometry'
import { perf } from '../../core/perf'
import { cleanCoachText, fadeAt, HOLD, holdFor, isDrawable, knownKey, mergeMarks, timedMarks, validMarks, type Known, type Mark, type Shown } from './marks'

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
 * bridged  the marks now up are the spotlight's box (spotlit), not the engine's annotate. The spotlight puts its
 *        caption to the right of that box, so the buddy sits on its left.
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
/**
 * How long a spotlight box's mark stays (ms): bon flies there, circles it and points, and the learner needs time to
 * see it (Adrian, Nov 24: longer than 6 s). The engine's annotate names its own holdMs.
 */
export const SPOT_HOLD_MS = 10_000
/** The last spotlight box bridged, so the engine's re-reads of one box mark it once. */
let lastSpot: Rect | undefined
/** A spotlight box within this many px of the last one is the same box (the spotlight's own JITTER_PX). */
const SPOT_JITTER = 8

function stopHold(): void {
  clearTimeout(hold)
  hold = undefined
}

/** The step now running (step.started), so a text mark for another step is not drawn. */
let curStep: string | undefined
/** The lesson is not live for the learner: paused, a blocker in the way (by kind), status "idle". */
let paused = false
const blockers = new Set<string>()
let idle = false
const quiet = (): boolean => paused || blockers.size > 0 || idle
/** Text marks put aside while the lesson is quiet, to come back when it is live (showText). */
let hidden: Shown[] = []
/** A "Not yet" or a Show me for this step: the engine's next annotate draws its marks even if they are gone. */
let asked = false

/** A mark that carries the on-screen coach's text. */
const isText = (m: Mark): boolean => m.why === 'point' && !!cleanCoachText(m.text)
/** A text mark that is not drawn now: its step is not the one running, or the lesson is quiet. */
const notLive = (m: Mark): boolean => isText(m) && (quiet() || (!!m.stepId && m.stepId !== curStep))

/** Fade the timed marks among `marks` (those without text) at `at`; a text mark keeps no hold. */
function holdTimed(marks: readonly Shown[], at: number | undefined, now: number): void {
  stopHold()
  const keys = timedMarks(marks).map((m) => m.key)
  if (at === undefined || !keys.length) return
  hold = setTimeout(() => fade(keys), Math.max(0, at - now))
}

/** The lesson went quiet: the text marks go out of sight, kept aside (not gone). Timed marks keep their hold. */
function hideText(): void {
  const cur = get().marks
  const text = cur.filter((m) => m.text)
  if (!text.length) return
  hidden = text
  const left = cur.filter((m) => !m.text)
  set({ marks: left, total: left.length })
  if (!left.length) stopHold()
}

/** The lesson is live again: the hidden text marks of the step still running come back (same key and birth). */
function showText(): void {
  if (quiet() || !hidden.length) return
  const back = hidden.filter((m) => !m.stepId || m.stepId === curStep)
  hidden = []
  if (!back.length) return
  // Engine marks: a spotlight box bridged meanwhile gives way to them, as an annotate would.
  const cur = get().bridged ? [] : get().marks
  const marks = [...cur, ...back.filter((b) => !cur.some((c) => c.key === b.key))]
  set({ marks, total: marks.length, bridged: false })
}

/** The lesson is live from scratch (lesson.ended, lesson.ready, a reset). */
function liven(): void {
  paused = false
  blockers.clear()
  idle = false
}

/** Forget that this mark was reached or timed out this step, so it can be drawn again (an explicit ask). */
function unGone(m: Mark): void {
  if (m.id) return void gone.delete(knownKey(m, []) as string) // an id is its key, whatever the pool
  for (let k = knownKey(m, gone.values()); k !== undefined; k = knownKey(m, gone.values())) gone.delete(k)
}

/** Something asked where again (a Show me press): the engine's next annotate draws even marks already reached. */
export function askAgain(): void {
  asked = true
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

/** The buddy hops: something good happened that is not a mark (it grew a level). */
export function cheer(): void {
  set((s) => ({ cheer: s.cheer + 1 }))
}

/** Back to blank: nothing drawn, nothing remembered (step.passed, a new lesson, a reset). */
export function forget(): void {
  stopHold()
  gone.clear()
  lastAsk = undefined
  lastSpot = undefined
  hidden = []
  asked = false
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
 * The step's target: the spotlight feature now shows this box (screen points), or nothing. Nothing with `faded`: the
 * spotlight's dim went on its own (calm), so bon keeps pointing until SPOT_HOLD_MS is up; without it the engine
 * cleared the box, and its mark goes now. `again`: a Show me press asked for it. Leaves the engine's own marks alone
 * while they are up.
 */
export function spotlit(rect: Rect | undefined, again = false, faded = false): void {
  const engineUp = get().marks.length > 0 && !get().bridged
  if (!rect) {
    if (faded) return // the same box re-sent stays one mark (lastSpot); its hold ends it
    lastSpot = undefined
    return engineUp ? undefined : withdraw()
  }
  perf.count('buddy.spotlit')
  if (engineUp) return perf.count('buddy.spotlit.engine-up')
  if (!isDrawable(rect)) return perf.count('buddy.spotlit.undrawable')
  const mark: Mark = { x: rect.x, y: rect.y, w: rect.w, h: rect.h, why: 'point' }
  if (again) {
    // Forget that it was reached or timed out, and let it be born again.
    unGone(mark)
    const up = knownKey(mark, get().marks)
    if (up !== undefined) set({ marks: get().marks.filter((m) => m.key !== up) })
    lastSpot = undefined
  }
  if (lastSpot && sameRect(lastSpot, rect, SPOT_JITTER)) return perf.count('buddy.spotlit.same')
  lastSpot = rect
  if (!get().bridged) set({ bridged: true })
  show([mark], SPOT_HOLD_MS)
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
  // A text mark (the on-screen coach) is not timed: only the others fade at the hold.
  holdTimed(marks, fadeAt(timedMarks(marks), holdMs), now)
}

/** One `annotate` payload: { marks, holdMs? } or { clear: true }. Anything else is ignored. */
export function annotate(payload: unknown): void {
  perf.count('buddy.annotate')
  const p = (payload && typeof payload === 'object' ? payload : {}) as { marks?: unknown; holdMs?: unknown; clear?: unknown }
  const valid = p.clear || !('marks' in p) ? [] : validMarks(p.marks)
  // While quiet, this step's text marks wait with the hidden ones (the newest win), to come back once it is live.
  if (quiet()) {
    const later = valid.filter((m) => isText(m) && (!m.stepId || m.stepId === curStep))
    if (later.length) hidden = mergeMarks([], later, [], Date.now())
  }
  // A text mark for a step that is not live (a late answer) or while quiet is not drawn. An annotate with nothing live
  // left is ignored, so a late answer never replaces what the running step drew.
  const marks = valid.filter((m) => !notLive(m))
  if (valid.length && !marks.length) return
  if (get().bridged) set({ bridged: false })
  if (!payload || typeof payload !== 'object') return
  if (p.clear) {
    hidden = []
    return fade()
  }
  if (!('marks' in p)) return
  // The answer to an ask ("Not yet", Show me): its marks are drawn again even if the learner reached them this step.
  if (asked) {
    asked = false
    marks.forEach(unGone)
  }
  show(marks, holdFor(p.holdMs))
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
  if (p?.stepId) curStep = p.stepId
  if (p?.replay) return // a reconnect's replay of the step already running: not a new step
  idle = false // a new step is running: the lesson is live
  asked = false
  const keep = get().marks.filter((m) => m.stepId && m.stepId === p?.stepId)
  hidden = hidden.filter((m) => m.stepId && m.stepId === p?.stepId)
  stopHold()
  gone.clear()
  lastSpot = undefined
  set({ marks: keep, total: keep.length })
  // A kept text mark stays with its step; kept plain marks get the default hold from now.
  const now = Date.now()
  holdTimed(keep, now + HOLD.base, now)
  showText()
})
onMessage('step.passed', () => {
  curStep = undefined
  forget()
})
onMessage('lesson.ready', (p) => {
  liven() // a reconnect replays the pause and the blockers after the step: they re-arrive
  if (!p?.replay) curStep = undefined
  forget()
})
onMessage('lesson.ended', () => {
  curStep = undefined
  liven()
  forget()
})
onUi('reset', () => {
  curStep = undefined
  liven()
  forget()
})
onUi('dismiss', () => {
  hidden = []
  fade() // Esc: the learner wants the screen back. Never claims the event, so cards still close.
})
// "Not yet" for the step now running: the learner still needs the pointing, so the engine's re-send is drawn again.
onMessage('card', (p) => {
  if (p?.verdict === 'not_done' && p.stepId && p.stepId === curStep) asked = true
})
// The lesson is quiet: no text mark (the coach's text box hides too, features/annotate/store.ts). Live again: it comes back.
onMessage('lesson.paused', () => {
  paused = true
  hideText()
})
onMessage('lesson.resumed', () => {
  paused = false
  showText()
})
onMessage('blocker', (p) => {
  const kind = String(p?.kind ?? '')
  if (p?.clear) {
    blockers.delete(kind)
    return showText()
  }
  blockers.add(kind)
  hideText()
})
onMessage('status', (p) => {
  idle = p?.state === 'idle'
  if (idle) hideText()
  else showText()
})
