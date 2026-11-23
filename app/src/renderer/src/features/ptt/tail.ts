/**
 * Feature: ptt. The release tail: after the keys come up, the words go out within TAIL_MS, whatever the recognizer does.
 * Pure (the clock is passed in), so the timing is tested with a fake clock (test/pttStream.test.ts).
 *
 * Measured in code before this lane (Session.swift, ptt.ts, common/pttState.ts, store.ts): on release the helper
 * closed the mic, ended the recognizer's input and waited for its final, up to finalWaitMs = 1500 ms, before it sent
 * `final`; main and the renderer add a few ms of IPC. So release to final was the recognizer's finalize time (often
 * several hundred ms on SpeechAnalyzer), capped at 1.5 s, and longer when the recognizer was still starting at release.
 *
 * Now the helper itself stops waiting after a tail of at most 300 ms (Session.swift, Tail.swift) and sends its best
 * text. This is the app's copy of the same rule, so an older helper (or a lost final) costs no more than the tail too:
 * when the session has been released (phase 'sending') for TAIL_MS and no final came, the last partial is the final.
 * If there are no words yet (the recognizer was still starting), it waits for the helper's final or cancel as before.
 *
 * It also keeps one timing record per hold (down, up, final, which path), so the speed can be read in the console.
 */
import type { PttState } from '../../../../common/pttState'
import { stripWake } from './wake'

/** The longest the words wait after release. */
export const TAIL_MS = 300

export type TailClock = { now: () => number; set: (fn: () => void, ms: number) => unknown; clear: (h: unknown) => void }

export const realClock: TailClock = {
  now: () => Date.now(),
  set: (fn, ms) => setTimeout(fn, ms),
  clear: (h) => clearTimeout(h as ReturnType<typeof setTimeout>)
}

/** One hold, timed. All times are the clock's ms. releaseToFinalMs: what the learner waits after letting go. */
export type PttTiming = { id: string; downAt?: number; upAt?: number; finalAt?: number; via?: 'helper' | 'tail'; releaseToFinalMs?: number }

export type TailView = Pick<PttState, 'phase' | 'id' | 'text' | 'released'>

/** Worth sending: at least two letters or digits once a wake word is dropped (the helper's isMeaningful). */
export const meaningful = (text: string): boolean => (stripWake(text).match(/[\p{L}\p{N}]/gu)?.length ?? 0) >= 2

export type Tail = {
  /** Every PttState, in order. */
  observe(s: TailView): void
  /** A final went out for this id (the helper's, or this tail's own). Returns the finished timing. */
  final(id: string, via: 'helper' | 'tail'): PttTiming | undefined
  /** The current (or last) hold's timing. */
  timing(): PttTiming | undefined
  /** Stop any timer (tests, teardown). */
  stop(): void
  /** The browser stage's hold-for-shots scripts: while paused the tail never sends (the helper's final still does). */
  pause(on: boolean): void
}

export function createTail(onFinal: (f: { id: string; text: string }) => void, opts: { tailMs?: number; clock?: TailClock } = {}): Tail {
  const clock = opts.clock ?? realClock
  const tailMs = Math.min(Math.max(opts.tailMs ?? TAIL_MS, 0), TAIL_MS)
  let timer: unknown
  let armed: string | undefined // the id the timer is for
  let text = ''
  let t: PttTiming | undefined
  let paused = false

  const cancel = (): void => {
    if (timer !== undefined) clock.clear(timer)
    timer = undefined
  }
  const fire = (): void => {
    timer = undefined
    const id = armed
    if (paused || !id || t?.id !== id || t.finalAt !== undefined) return
    // No words yet: the recognizer is still starting. The helper's final (or cancel) ends it, as before.
    if (!meaningful(text)) return
    api.final(id, 'tail')
    onFinal({ id, text })
  }

  const api: Tail = {
    observe(s) {
      if (!s.id) {
        // Back at rest (final, cancel, error, reset): nothing to wait for.
        cancel()
        armed = undefined
        return
      }
      if (t?.id !== s.id) {
        cancel()
        armed = undefined
        t = { id: s.id, downAt: s.phase === 'arming' ? clock.now() : undefined }
      }
      if (s.released && t.upAt === undefined) t.upAt = clock.now()
      if (s.phase !== 'sending') return
      if (t.upAt === undefined) t.upAt = clock.now()
      text = s.text
      if (armed !== s.id && t.finalAt === undefined) {
        armed = s.id
        timer = clock.set(fire, tailMs)
      }
    },
    final(id, via) {
      if (armed === id) cancel()
      if (t?.id !== id || t.finalAt !== undefined) return t?.id === id ? t : undefined
      const now = clock.now()
      t = { ...t, finalAt: now, via, releaseToFinalMs: t.upAt !== undefined ? now - t.upAt : undefined }
      return t
    },
    timing: () => t,
    stop: cancel,
    pause: (on) => void (paused = on)
  }
  return api
}
