/**
 * Feature: annotate (buddy draws). Which marks are drawn now, and when they go.
 *
 * In (engine -> app, shared/contracts/events.ts):
 *   annotate {marks, holdMs?}   replaces what is drawn. A mark with a key already drawn keeps its stroke (no redraw).
 *   annotate {clear: true}      fade everything now.
 * Today's pointing (spotlight): until the engine has sent one annotate, every new spotlight box the spotlight feature
 * shows also gets a buddy mark (why "point"), so the buddy points before the engine speaks annotate. Read from the
 * spotlight store (read-only), so its calm gate and front-app rule apply here too. Once annotate arrives, the engine
 * owns pointing and the bridge stops.
 *
 * Out: the marks fade (and stay gone for this step) when
 *   - the learner goes there (a click inside, or the pointer coming in and resting: marks.ts createReach),
 *   - the hold runs out (holdMs, or 6 s),
 *   - the step changes (step.started keeps only marks for the new step; step.passed clears), the lesson ends, a reset,
 *   - Esc (dismiss).
 * Nothing here takes the mouse: the layer is click-through, always.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { sameRect } from '../../core/geometry'
import { isDrawable, type Rect } from './geometry'
import { holdFor, mergeMarks, validMarks, DEFAULT_HOLD_MS, type Annotation, type DrawMark, type Known } from './marks'

export const useAnnotate = create<{ marks: DrawMark[] }>(() => ({ marks: [] }))
const set = useAnnotate.setState
const get = useAnnotate.getState

/** Keys the learner reached or that timed out this step: a re-send does not draw them again. */
const gone = new Map<string, Known>()
/** Asks the current `gone` belongs to: a new circle-to-ask starts fresh. */
let lastAsk: string | undefined
let hold: ReturnType<typeof setTimeout> | undefined
/** The engine speaks annotate: stop bridging spotlight boxes. */
let engineAnnotates = false
/** The last spotlight box bridged, so the engine's re-reads of one box draw it once. */
let lastSpot: Rect | undefined
const SPOT_JITTER = 8

function stopHold(): void {
  clearTimeout(hold)
  hold = undefined
}

/** Fade these marks (or all), and remember them as gone for this step. */
export function fade(keys?: readonly string[]): void {
  const cur = get().marks
  const out = keys ? cur.filter((m) => keys.includes(m.key)) : cur
  if (!out.length) return
  out.forEach((m) => gone.set(m.key, m))
  const left = cur.filter((m) => !out.includes(m))
  set({ marks: left })
  if (!left.length) stopHold()
}

/** Back to blank: nothing drawn, nothing remembered (a new step, a new lesson, a reset). */
function forget(): void {
  stopHold()
  gone.clear()
  lastAsk = undefined
  lastSpot = undefined
  if (get().marks.length) set({ marks: [] })
}

/** Draw `incoming` in place of what is drawn, and (re)start the hold. */
export function show(incoming: readonly Annotation[], holdMs: number = DEFAULT_HOLD_MS, now = Date.now()): void {
  const ask = incoming.find((m) => m.askId)?.askId
  if (ask && ask !== lastAsk) {
    gone.clear()
    lastAsk = ask
  }
  const marks = mergeMarks(get().marks, incoming, gone.values(), now)
  set({ marks })
  stopHold()
  if (marks.length) hold = setTimeout(() => fade(), holdMs)
}

onMessage('annotate', (p) => {
  engineAnnotates = true
  if (!p || typeof p !== 'object') return
  if ('clear' in p && p.clear) return fade()
  if (!('marks' in p)) return
  show(validMarks(p.marks), holdFor(p.holdMs))
})

onMessage('step.started', (p) => {
  if (p?.replay) return // a reconnect's replay of the step already running: not a new step
  const step = p?.stepId
  const keep = get().marks.filter((m) => m.stepId && m.stepId === step)
  stopHold()
  gone.clear()
  lastSpot = undefined
  set({ marks: keep })
  if (keep.length) hold = setTimeout(() => fade(), DEFAULT_HOLD_MS)
})
onMessage('step.passed', forget)
onMessage('lesson.ended', forget)
onMessage('lesson.ready', forget)
onUi('reset', () => {
  forget()
  engineAnnotates = false
})
// Esc: the learner wants the screen back.
onUi('dismiss', () => fade())

// Today's pointing: a new spotlight box gets a buddy mark too (until the engine sends its own annotate).
// Imported late, not at the top: features load A to Z and "annotate" is first, so a static import pulled the spotlight
// store's own import chain (shortcut-bar, cards, diagrams) in out of order ("Cannot access 'useCards' before
// initialization" in the stage). By the time this resolves, every feature module has run.
void import('../spotlight/store').then(({ useSpotlight }) => useSpotlight.subscribe((s, prev) => {
  if (engineAnnotates || s.target === prev.target) return
  const r = s.target?.rect
  if (!s.target || !isDrawable(r)) {
    if (!s.target) lastSpot = undefined
    return
  }
  if (lastSpot && sameRect(lastSpot, r, SPOT_JITTER)) return
  lastSpot = r
  show([{ x: r.x, y: r.y, w: r.w, h: r.h, why: 'point' }])
}))
