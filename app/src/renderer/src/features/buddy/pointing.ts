/**
 * Feature: buddy, pass 2. What the bonsai is pointing at right now, from the engine's `annotate` event (Michael's
 * contract, Nov 22: "Buddy draws"), and how long each mark lives.
 *
 * Lifetime, as the contract says:
 *   - a new annotate REPLACES the marks drawn before; a mark re-sent under the same id stays drawn (marks.ts settle);
 *   - marks fade after holdMs (default HOLD.base), on { clear: true }, when the step changes, and when the lesson
 *     ends or resets;
 *   - they fade when the learner clicks inside one. The overlay is click-through, so in Electron the click itself
 *     never reaches this window (Core requests in the brief). Mouse moves do reach it, so the pointer arriving on a
 *     mark counts as "found it": the circle leaves HOLD.found later (found()). Esc clears them at once.
 *
 * A mark the learner dismissed (found, clicked, Esc) stays gone while the engine re-sends the same one, like a faded
 * spotlight; a different mark, a new step or an engine clear ends that.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { cleanMarks, HOLD, holdFor, settle, type Shown } from './marks'

/**
 * marks: screen points, as the engine sent them (the layer maps them into its window).
 * lean: -1 to 1, which way the bonsai leans while it points (set by the layer, which knows where both ends are).
 */
export const usePointing = create<{ marks: Shown[]; lean: number }>(() => ({ marks: [], lean: 0 }))
const get = usePointing.getState
const set = usePointing.setState

let timer: ReturnType<typeof setTimeout> | undefined
let until = 0
/** The running fade is the learner's (found): it ends in dismiss(), and a second found() changes nothing. */
let learners = false
/** Marks the learner sent away: a re-send of only these is ignored. */
const dismissed = new Set<string>()

function drop(): void {
  clearTimeout(timer)
  timer = undefined
  until = 0
  learners = false
  if (get().marks.length || get().lean) set({ marks: [], lean: 0 })
}

/** Fade the marks in `ms`. `byLearner`: remember them as dismissed when they go. */
function fadeIn(ms: number, byLearner = false): void {
  clearTimeout(timer)
  until = Date.now() + ms
  learners = byLearner
  timer = setTimeout(() => (byLearner ? dismiss() : drop()), ms)
}

/** The engine's doing (a clear, a new step, the lesson ending): gone, and nothing is held against a re-send. */
export function clearMarks(): void {
  dismissed.clear()
  drop()
}

/** The learner's doing (a click inside a mark, Esc): gone, and the engine re-sending the same marks does not bring them back. */
export function dismiss(): void {
  for (const m of get().marks) dismissed.add(m.key)
  drop()
}

/** The pointer is on a mark: the learner found it, so the circle gets out of the way soon. */
export function found(): void {
  if (!get().marks.length || learners) return
  fadeIn(Math.max(0, Math.min(until - Date.now(), HOLD.found)), true)
}

/** One `annotate` payload: { marks, holdMs? } or { clear: true }. Anything else is ignored. */
export function annotate(payload: unknown): void {
  if (!payload || typeof payload !== 'object') return
  const p = payload as { marks?: unknown; holdMs?: unknown; clear?: unknown }
  if (p.clear === true) return clearMarks()
  if (!Array.isArray(p.marks)) return
  const next = cleanMarks(p.marks)
  if (!next.length) return clearMarks()
  if (next.every((m) => dismissed.has(m.key))) return
  dismissed.clear()
  set((s) => ({ marks: settle(s.marks, next) }))
  fadeIn(holdFor(p.holdMs))
}

// `annotate` is in the contract branch (claude/contract-circle-ask) and not on this one yet, so the bus's MessageType
// does not know it. The bus is keyed by the type string: this cast goes when the contract lands (brief, Core requests).
;(onMessage as unknown as (type: string, fn: (payload: unknown) => void) => () => void)('annotate', annotate)

onMessage('step.started', clearMarks)
onMessage('step.passed', clearMarks)
onMessage('lesson.ready', clearMarks)
onMessage('lesson.ended', clearMarks)
onUi('reset', clearMarks)
onUi('dismiss', () => {
  dismiss() // Esc; never claims the event, so cards still close
})
