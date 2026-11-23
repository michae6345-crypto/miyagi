/**
 * Feature: circle. The circle-to-ask state machine, pure (test/circle.test.ts). The store (store.ts) feeds it push to
 * talk states, pointer strokes, the final words, timers and the engine's answer, and does what it says (send the ask,
 * make the overlay interactive or click-through).
 *
 *   idle      nothing drawn. The overlay is click-through.
 *   armed     the push-to-talk keys are held: the overlay takes the mouse and the pointer draws ink. The ONLY state in
 *             which the overlay is interactive. It ends on release, Esc, blur, an error, or ARMED_MAX_MS, whatever comes
 *             first, so the learner's mouse can never stay stuck.
 *   sealed    released with ink: waiting for the spoken words (or the news that there were none).
 *   asking    the ask went out (askId); the ink stays while the engine thinks. answer.delta text for this askId
 *             gathers in `stream` (the card opens beside the circle on the first words; "Looking" until then).
 *   answered  the answer card sits beside the circle until it is closed, Esc, a new hold, or ANSWER_MS.
 *
 * Asking and answered keep the hold's push-to-talk session: its final words, if they come late (after "What is this?"
 * went out), are claimed and dropped, never routed again as a second, plain ask.
 *
 * A hold with no ink is plain push to talk: the machine stays out of the way and the words route as before.
 */
import type { Box, Pt } from './geometry'
import { addPoint, MAX_POINTS, strokeBox } from './geometry'

/** The overlay never stays interactive longer than this in one hold (the brief's 8 s cap). */
export const ARMED_MAX_MS = 8000
/** After the keys are up, how long to wait for the final words before asking "What is this?". */
export const WORDS_WAIT_MS = 1500
/** Sealed while the learner keeps talking: a backstop past push to talk's own hard cap (65 s). */
export const SEALED_MAX_MS = 70_000
/** No answer by now: the ink fades and the pill says so. */
export const ASK_MAX_MS = 30_000
/** An answer nobody closes goes by itself (short: Esc does not reach the overlay after release, see the brief). */
export const ANSWER_MS = 25_000
/** The most streamed text one answer keeps: past it, more words are dropped (a runaway engine cannot grow the card). */
export const MAX_STREAM = 4000
/** The ask when nothing was said (the contract's default too). */
export const DEFAULT_ASK = 'What is this?'

export type PttPhase = 'idle' | 'arming' | 'listening' | 'sending' | 'error'

export type Answer = { title?: string; body: string }

/** The answer as it streams in (answer.delta): the text so far, whether the last delta came, and when the newest came. */
export type Stream = { text: string; done: boolean; at: number }

export type CircleState =
  | { k: 'idle' }
  | { k: 'armed'; session: string; since: number; strokes: Pt[][]; down: boolean; words?: string }
  | { k: 'sealed'; session: string; since: number; strokes: Pt[][]; box: Box; wordsBy?: number }
  | { k: 'asking'; session: string; askId: string; since: number; strokes: Pt[][]; box: Box; text: string; stream?: Stream }
  | { k: 'answered'; session: string; askId: string; since: number; strokes: Pt[][]; box: Box; text: string; answer: Answer }

export const IDLE: CircleState = { k: 'idle' }

export type CircleEvent =
  /**
   * A push-to-talk state (common/pttState): its phase, session id, why the last session ended, and whether the keys
   * came up while the helper was still arming (phase stays 'arming' until it says 'listening').
   */
  | { t: 'ptt'; phase: PttPhase; id?: string; lastCancel?: string; released?: boolean }
  | { t: 'down'; p: Pt }
  | { t: 'move'; p: Pt }
  | { t: 'up' }
  /** The session's final words (features/ptt routeFinal offers them here first). */
  | { t: 'final'; id: string; text: string }
  /** Esc, the card's close, a lesson ending. */
  | { t: 'cancel' }
  /** The overlay lost the pointer (window blur, the page hidden). */
  | { t: 'blur' }
  | { t: 'tick' }
  /** The engine answered: card {kind: "answer", askId}. */
  | { t: 'answer'; askId?: string; answer: Answer }
  /** A piece of the answer: answer.delta {askId, text, done?}. `text` is only the new words. */
  | { t: 'delta'; askId: string; text: string; done?: boolean }

export type Ask = { askId: string; text: string; box: Box }

export type Ctx = {
  now: number
  /** The overlay's size in its own px (the ink box is kept inside it). */
  width: number
  height: number
  newId: () => string
}

export type Step = {
  state: CircleState
  /** Send this ask now. */
  ask?: Ask
  /** The final words went with the circle: push to talk must not route them again. */
  claimed?: boolean
  /** Nothing came back in time (the store tells the learner). */
  timedOut?: boolean
}

/** The overlay takes the mouse only while armed. */
export const interactive = (s: CircleState): boolean => s.k === 'armed'

/** The streamed answer to show now ('' = none yet: the "Looking" chip). Leading space is not shown. */
export const shown = (s: CircleState): string => (s.k === 'asking' && s.stream ? s.stream.text.trimStart() : '')

/** The ink that is on screen. */
export const inkOf = (s: CircleState): Pt[][] => (s.k === 'idle' ? [] : s.strokes)

const live = (phase: PttPhase): boolean => phase === 'arming' || phase === 'listening'

/** Push-to-talk cancel reasons after which the circle is dropped, not asked about. */
const DROPS = new Set(['esc', 'disabled'])

function send(session: string, strokes: Pt[][], box: Box, words: string | undefined, ctx: Ctx): Step {
  const text = words?.trim() || DEFAULT_ASK
  const askId = ctx.newId()
  return { state: { k: 'asking', session, askId, since: ctx.now, strokes, box, text }, ask: { askId, text, box } }
}

/** The hold is over (released, blurred or capped): seal the ink, or step aside when there is none. */
function endHold(s: Extract<CircleState, { k: 'armed' }>, ctx: Ctx, pttOver: boolean, lastCancel?: string): Step {
  const box = strokeBox(s.strokes, ctx.width, ctx.height)
  if (!box) return { state: IDLE }
  if (lastCancel && DROPS.has(lastCancel)) return { state: IDLE }
  if (s.words !== undefined) return send(s.session, s.strokes, box, s.words, ctx)
  // Push to talk ended with no words to come (empty, short, keypress, timeout): ask now.
  if (pttOver && lastCancel) return send(s.session, s.strokes, box, undefined, ctx)
  return { state: { k: 'sealed', session: s.session, since: ctx.now, strokes: s.strokes, box, wordsBy: pttOver ? ctx.now + WORDS_WAIT_MS : undefined } }
}

/** Cut at MAX_STREAM, never in the middle of a two-part character. */
function capText(t: string): string {
  if (t.length < MAX_STREAM) return t
  const c = t.charCodeAt(MAX_STREAM - 1)
  // 55296 to 56319: the first half of a surrogate pair (an emoji, say).
  return t.slice(0, c >= 55296 && c <= 56319 ? MAX_STREAM - 1 : MAX_STREAM)
}

export function step(s: CircleState, e: CircleEvent, ctx: Ctx): Step {
  switch (e.t) {
    case 'ptt': {
      // A new hold starts: arm, whatever was on screen (a new circle replaces the last one and its answer). Keys that
      // are already up (released while arming) are no hold: that ends one instead.
      if (live(e.phase) && e.id && !e.released) {
        if (s.k === 'armed' && s.session === e.id) return { state: s }
        if (s.k === 'sealed' && s.session === e.id) return { state: s }
        return { state: { k: 'armed', session: e.id, since: ctx.now, strokes: [], down: false } }
      }
      if (s.k === 'armed') {
        if (e.phase === 'error') return { state: IDLE }
        // sending, or arming with the keys up: the words are on their way. idle: the session is over.
        return endHold(s, ctx, e.phase === 'idle', e.lastCancel)
      }
      if (s.k === 'sealed' && (e.phase === 'idle' || e.phase === 'error')) {
        if (e.phase === 'error' || (e.lastCancel && DROPS.has(e.lastCancel))) return { state: IDLE }
        if (e.lastCancel) return send(s.session, s.strokes, s.box, undefined, ctx)
        // Over with words: the final is on its way (or already here); wait a moment for it.
        if (s.wordsBy === undefined) return { state: { ...s, wordsBy: ctx.now + WORDS_WAIT_MS } }
      }
      return { state: s }
    }
    case 'down':
      if (s.k !== 'armed') return { state: s }
      if (s.strokes.flat().length >= MAX_POINTS) return { state: { ...s, down: false } }
      return { state: { ...s, down: true, strokes: [...s.strokes, [{ x: e.p.x, y: e.p.y }]] } }
    case 'move': {
      if (s.k !== 'armed' || !s.down || !s.strokes.length) return { state: s }
      if (s.strokes.flat().length >= MAX_POINTS) return { state: s }
      const last = s.strokes[s.strokes.length - 1]
      const next = addPoint(last, e.p)
      if (next === last) return { state: s }
      return { state: { ...s, strokes: [...s.strokes.slice(0, -1), next] } }
    }
    case 'up':
      return s.k === 'armed' && s.down ? { state: { ...s, down: false } } : { state: s }
    case 'final': {
      if (s.k === 'armed' && s.session === e.id) {
        // The words came before the state change: keep them; with no ink, push to talk routes them as ever.
        if (!strokeBox(s.strokes, ctx.width, ctx.height)) return { state: s }
        return { state: { ...s, words: e.text }, claimed: true }
      }
      if (s.k === 'sealed' && s.session === e.id) return { ...send(s.session, s.strokes, s.box, e.text, ctx), claimed: true }
      // Too late: "What is this?" already went for this hold. Drop the words (push to talk must not ask them again).
      if ((s.k === 'asking' || s.k === 'answered') && s.session === e.id) return { state: s, claimed: true }
      return { state: s }
    }
    case 'cancel':
      return { state: IDLE }
    case 'blur':
      return s.k === 'armed' ? endHold(s, ctx, false) : { state: s }
    case 'tick':
      if (s.k === 'armed' && ctx.now - s.since >= ARMED_MAX_MS) return endHold({ ...s, down: false }, ctx, false)
      if (s.k === 'sealed' && ((s.wordsBy !== undefined && ctx.now >= s.wordsBy) || ctx.now - s.since >= SEALED_MAX_MS)) return send(s.session, s.strokes, s.box, undefined, ctx)
      if (s.k === 'asking' && ctx.now - Math.max(s.since, s.stream?.at ?? 0) >= ASK_MAX_MS) {
        // The words came but the card never did: keep what was said as the answer, never drop it.
        if (shown(s)) return { state: { k: 'answered', session: s.session, askId: s.askId, since: ctx.now, strokes: s.strokes, box: s.box, text: s.text, answer: { body: shown(s) } } }
        return { state: IDLE, timedOut: true }
      }
      if (s.k === 'answered' && ctx.now - s.since >= ANSWER_MS) return { state: IDLE }
      return { state: s }
    case 'delta': {
      // Only the ask on screen, only before its card and its last delta. Anything else (an older ask, a closed one,
      // a delta after the card or after done) is dropped.
      if (s.k !== 'asking' || e.askId !== s.askId || s.stream?.done) return { state: s }
      const had = s.stream?.text ?? ''
      // Past MAX_STREAM the words are dropped (done still ends the stream).
      const add = typeof e.text === 'string' ? e.text.slice(0, Math.max(0, MAX_STREAM - had.length)) : ''
      if (!add && !e.done) return { state: s }
      return { state: { ...s, stream: { text: capText(had + add), done: !!e.done, at: ctx.now } } }
    }
    case 'answer':
      if (s.k !== 'asking') return { state: s }
      if (e.askId === s.askId) return { state: { k: 'answered', session: s.session, askId: s.askId, since: ctx.now, strokes: s.strokes, box: s.box, text: s.text, answer: e.answer } }
      // An older engine answers without the askId: its card shows where cards always do, and the ink goes.
      if (e.askId === undefined) return { state: IDLE }
      return { state: s }
  }
}
