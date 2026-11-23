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
 * Not here: his bridge that also circles today's spotlight boxes until the engine sends its first annotate.
 *
 * Nothing here takes the mouse: the layer is click-through, always.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import type { Point, Rect } from '../../core/geometry'
import { fadeAt, HOLD, holdFor, mergeMarks, validMarks, type Known, type Mark, type Shown } from './marks'

/**
 * Where the buddy is. 'home': in the notch. 'out': flying to a mark. 'perched': sitting beside the mark `at` (its
 * key), its tree at `tree` (the overlay window's coordinates), which is where that mark's loop is drawn from.
 * 'back': on its way home. Set by the pod's layer (Pod.tsx); read by the loop's layer and by <Buddy />.
 */
export type Trip = { phase: 'home' | 'out' | 'perched' | 'back'; at?: string; tree?: Point }

/**
 * marks  screen points, as the engine sent them (the layers map them into their window).
 * lean   -1 to 1, which way the bonsai leans while it points (set by the layer, which knows where both ends are).
 * pose   a box another layer asked the bonsai to point at (pointAt), screen points; the layer leans toward it when
 *        it has no mark of its own.
 * trip   where the buddy is.
 * cheer  bumped each time the learner gets to a mark: the buddy hops.
 */
export const usePointing = create<{ marks: Shown[]; lean: number; pose?: Rect; trip: Trip; cheer: number }>(() => ({ marks: [], lean: 0, trip: { phase: 'home' }, cheer: 0 }))
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
  set({ marks: left })
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
  if (get().marks.length) set({ marks: [] })
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
  const marks = mergeMarks(get().marks, incoming, gone.values(), now)
  set({ marks })
  stopHold()
  const at = fadeAt(marks, holdMs)
  if (at !== undefined) hold = setTimeout(() => fade(), Math.max(0, at - now))
}

/** One `annotate` payload: { marks, holdMs? } or { clear: true }. Anything else is ignored. */
export function annotate(payload: unknown): void {
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
  set({ marks: keep })
  if (keep.length) hold = setTimeout(() => fade(), HOLD.base)
})
onMessage('step.passed', forget)
onMessage('lesson.ready', forget)
onMessage('lesson.ended', forget)
onUi('reset', forget)
onUi('dismiss', () => {
  fade() // Esc: the learner wants the screen back. Never claims the event, so cards still close.
})
