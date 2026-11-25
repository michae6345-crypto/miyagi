/**
 * Feature: annotate (buddy draws). Which marks are drawn now, and when they go.
 *
 * In (engine -> app, shared/contracts/events.ts):
 *   annotate {marks, holdMs?}   replaces what is drawn. A mark with a key already drawn keeps its stroke (no redraw).
 *   annotate {clear: true}      fade everything now.
 * Today's pointing (spotlight): until the engine has sent one annotate, every new spotlight box the spotlight feature
 * shows also gets a buddy mark (why "point"), so the buddy points before the engine speaks annotate. Read from the
 * spotlight store (read-only), so its calm gate and front-app rule apply here too: when the spotlight hides (a clear,
 * or its app left the front) the bridged mark fades with it. A Show me press is an explicit ask, so its box draws
 * again even if the learner already reached it this step. Once annotate arrives, the engine owns pointing and the
 * bridge stops.
 *
 * Out: the marks fade (and stay gone for this step) when
 *   - the learner goes there (a click inside, or the pointer coming in and resting: marks.ts createReach),
 *   - the hold runs out (holdMs, or 6 s, from the newest mark's birth: a re-sent mark does not restart it),
 *   - the step changes (step.started keeps only marks for the new step; step.passed clears), the lesson ends, a reset,
 *   - Esc (dismiss).
 * On-screen coach (Nov 24, agents/app-onscreen-coach.md): a mark with text (the step's action, in an app lesson) is not
 * timed. It stays while its step is live and goes on step.passed, a step.started for another step, lesson.ended, a new
 * (non-replay) lesson.ready, Esc, annotate {clear}, a replacing annotate, or the learner reaching it. Marks without text
 * keep the hold above.
 * Only while its step is live: an annotate whose text mark names a step that is not running now (a late answer after
 * step.passed, or after the next step.started) draws no text mark. And no text mark on idle: lesson.paused, a blocker
 * (not a clear) or status "idle" withdraws the text marks (not remembered as gone, so the engine's re-send after
 * lesson.resumed draws them again), and an annotate meanwhile draws none.
 * An explicit ask brings pointing back after the learner reached or dismissed it: a Show me press ("where?"), or a
 * "Not yet" card (verdict not_done) for the current step. The engine re-sends the point mark then (same id), and the
 * next annotate after the ask draws its marks again even if they are gone this step. If the re-send came first (it was
 * skipped as gone), the "Not yet" draws it again itself. A re-send with no ask stays gone.
 * Nothing here takes the mouse: the layer is click-through, always.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { sameRect } from '../../core/geometry'
import { isDrawable, type Rect } from './geometry'
import { cleanText, fadeAt, hasText, holdFor, mergeMarks, sameMarkKeys, timedMarks, validMarks, DEFAULT_HOLD_MS, type Annotation, type DrawMark, type Known, type OnscreenFields } from './marks'

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
/** The step now running (step.started), so a "Not yet" for it counts as an ask. */
let curStep: string | undefined
/** A Show me press or a "Not yet" for this step, not yet answered by an engine annotate: that annotate draws again. */
let engineAsked = false
/** The marks of this step's latest annotate that were skipped as gone (and its hold): a "Not yet" draws them again. */
let dropped: { marks: Annotation[]; holdMs: number } | undefined
/** The lesson is not live for the learner now: paused (lesson.paused), a blocker in the way (by kind), status "idle". */
let paused = false
const blockers = new Set<string>()
let idle = false
const quiet = (): boolean => paused || blockers.size > 0 || idle

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
  engineAsked = false
  dropped = undefined
  paused = false
  blockers.clear()
  idle = false
  if (get().marks.length) set({ marks: [] })
}

/** Start the hold for the timed marks among `marks` (those without text): they fade at `at`; a text mark is untouched. */
function holdTimed(marks: readonly DrawMark[], at: number | undefined, now: number): void {
  stopHold()
  if (at === undefined) return
  const keys = timedMarks(marks).map((m) => m.key)
  if (keys.length) hold = setTimeout(() => fade(keys), Math.max(0, at - now))
}

/** Draw `incoming` in place of what is drawn. The hold counts from the newest mark's birth (fadeAt), so a re-send of
 * marks already drawn keeps the old deadline and only a new mark moves it. A mark with text gets no hold. */
export function show(incoming: readonly Annotation[], holdMs: number = DEFAULT_HOLD_MS, now = Date.now()): void {
  const ask = incoming.find((m) => m.askId)?.askId
  if (ask && ask !== lastAsk) {
    gone.clear()
    lastAsk = ask
  }
  const marks = mergeMarks(get().marks, incoming, gone.values(), now)
  set({ marks })
  holdTimed(marks, fadeAt(timedMarks(marks), holdMs), now)
}

/** Take the marks away (they fade out) without remembering them as gone: the thing they pointed at went away, the
 * learner did not reach it, so it may draw again when it comes back. */
function withdraw(): void {
  stopHold()
  if (get().marks.length) set({ marks: [] })
}

/** A mark that carries the coach's text (a "point" mark with text: mergeMarks keeps text for those only). */
const textOf = (m: Annotation): boolean => m.why === 'point' && !!cleanText((m as Annotation & OnscreenFields).text)

/** Not drawn now: a text mark for a step that is not the one running, or any text mark while the lesson is quiet. */
const notLive = (m: Annotation): boolean => textOf(m) && (quiet() || (!!m.stepId && m.stepId !== curStep))

/** The lesson went quiet (paused, a blocker, idle): the untimed text marks go, not remembered as gone, so a re-send
 * once it is live again draws them. Timed marks keep their hold. */
function withdrawText(): void {
  const cur = get().marks
  const left = cur.filter((m) => !hasText(m))
  if (left.length !== cur.length) set({ marks: left })
  if (!left.length) stopHold()
}

/** An explicit ask for this box (Show me): forget that it was reached or timed out, and let it be born again. */
function askAgain(m: Annotation): void {
  for (const k of sameMarkKeys(m, gone.values())) gone.delete(k)
  const drawn = new Set(sameMarkKeys(m, get().marks))
  if (drawn.size) set({ marks: get().marks.filter((d) => !drawn.has(d.key)) })
  lastSpot = undefined
}

onMessage('annotate', (p) => {
  engineAnnotates = true
  if (!p || typeof p !== 'object') return
  if ('clear' in p && p.clear) return fade()
  if (!('marks' in p)) return
  // A text mark for a step that is no longer live (a late answer) or while the lesson is quiet: not drawn, so a stale
  // untimed mark never stays up. It is not remembered as gone either. An annotate with nothing live left is ignored: a
  // late answer must not replace what the running step drew.
  const valid = validMarks(p.marks)
  const marks = valid.filter((m) => !notLive(m))
  if (valid.length && !marks.length) return
  const holdMs = holdFor(p.holdMs)
  // The answer to an explicit ask (Show me, "Not yet"): its marks are born again even if reached or dismissed.
  if (engineAsked) {
    engineAsked = false
    marks.forEach(askAgain)
  }
  show(marks, holdMs)
  const drawn = get().marks
  const skipped = marks.filter((m) => !sameMarkKeys(m, drawn).length)
  dropped = skipped.length ? { marks: skipped, holdMs } : undefined
})

// "Not yet" for the step now running: the learner still needs the pointing, so it counts as an ask.
onMessage('card', (p) => {
  if (p?.verdict !== 'not_done' || !p.stepId || p.stepId !== curStep) return
  if (!dropped) {
    engineAsked = true
    return
  }
  // The engine's re-send came before the card and was skipped as gone: draw it again now.
  const again = dropped
  dropped = undefined
  const live = again.marks.filter((m) => !notLive(m))
  if (!live.length) return
  live.forEach(askAgain)
  show(live, again.holdMs)
})

onMessage('step.started', (p) => {
  if (p?.stepId) curStep = p.stepId
  if (p?.replay) return // a reconnect's replay of the step already running: not a new step
  idle = false // a new step is running: the lesson is live
  const step = p?.stepId
  engineAsked = false
  dropped = undefined
  const keep = get().marks.filter((m) => m.stepId && m.stepId === step)
  stopHold()
  gone.clear()
  lastSpot = undefined
  set({ marks: keep })
  // A kept text mark stays with its step; kept plain marks get the default hold from now.
  const now = Date.now()
  holdTimed(keep, timedMarks(keep).length ? now + DEFAULT_HOLD_MS : undefined, now)
})
onMessage('step.passed', () => {
  curStep = undefined
  forget()
})
onMessage('lesson.ended', () => {
  curStep = undefined
  forget()
})
// A reconnect's replay of the lesson already running is not a new lesson: what is drawn stays.
onMessage('lesson.ready', (p) => {
  // A reconnect replays the pause and the blockers after the step (engine v2_snapshot): start from live, they re-arrive.
  paused = false
  blockers.clear()
  idle = false
  if (p?.replay) return
  curStep = undefined
  forget()
})
// No text mark on idle: the lesson waits (paused, a blocker in the way) or the engine is idle.
onMessage('lesson.paused', () => {
  paused = true
  withdrawText()
})
onMessage('lesson.resumed', () => void (paused = false))
onMessage('blocker', (p) => {
  const kind = String(p?.kind ?? '')
  if (p?.clear) return void blockers.delete(kind)
  blockers.add(kind)
  withdrawText()
})
onMessage('status', (p) => {
  idle = p?.state === 'idle'
  if (idle) withdrawText()
})
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
/** A Show me press not yet answered by a new spotlight box. */
let showMeAsked = false
void Promise.all([import('../spotlight/store'), import('../../core/shortcuts')]).then(([{ useSpotlight }, { usePressed }]) => {
  usePressed.subscribe((p, was) => {
    if (!p.kind || (p.kind === was.kind && p.at === was.at)) return
    showMeAsked = p.kind === 'show_me'
    // Show me ("where?") asks the engine too: its next annotate draws even marks already reached or dismissed.
    if (showMeAsked) engineAsked = true
  })
  onMessage('step.started', () => (showMeAsked = false))
  useSpotlight.subscribe((s, prev) => {
    if (engineAnnotates || s.target === prev.target) return
    if (!s.target) {
      // The spotlight hid (the engine cleared it, or its app left the front): the bridged mark goes with it.
      lastSpot = undefined
      withdraw()
      return
    }
    const r = s.target.rect
    if (!isDrawable(r)) return
    const mark: Annotation = { x: r.x, y: r.y, w: r.w, h: r.h, why: 'point' }
    if (s.showMe && showMeAsked) {
      showMeAsked = false
      askAgain(mark)
    }
    if (lastSpot && sameRect(lastSpot, r, SPOT_JITTER)) return
    lastSpot = r
    show([mark])
  })
})
