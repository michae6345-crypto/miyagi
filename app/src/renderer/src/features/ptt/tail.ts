/**
 * Feature: ptt. The app's safety net for the release tail: if the helper never sends a final for a released hold (an
 * old helper binary, a lost line), the last partial goes out SAFETY_MS after the keys came up. Pure (the clock is
 * passed in), so the timing is tested with a fake clock (test/pttStream.test.ts).
 *
 * The real tail lives in the helper (native/listen/Tail.swift): after release it sends the recognizer's final as soon
 * as it comes (about 100 to 150 ms on SpeechAnalyzer, measured by native/listen/measure-tail.sh), else the best text
 * once it has settled (at least 300 ms), else at its cap: 1000 ms, up to HELPER_TAIL_MAX_MS when audio queued during
 * a cold start was just flushed. Before Nov 22 it always waited up to 1500 ms.
 *
 * This net must never race the helper: if it fired first it would route the last partial, and the helper's better
 * final (the recognizer's, or the text with the last words) would be dropped by routeFinal's seen-id dedupe. So it
 * waits the helper's worst case plus 400 ms of IPC and scheduling slack, and only acts when the helper said nothing.
 * If there are no words yet (the recognizer was still starting), it waits for the helper's final or cancel as before.
 *
 * It also keeps one timing record per hold (down, up, final, which path), so the speed can be read in the console.
 */
import type { PttState } from '../../../../common/pttState'
import { stripWake } from './wake'

/** The helper's longest release tail (Tail.ceilingMs in native/listen/Tail.swift). Keep the two in step. */
export const HELPER_TAIL_MAX_MS = 1500
/** The app's safety net: strictly after the helper's worst case, so the helper's final always wins. */
export const SAFETY_MS = HELPER_TAIL_MAX_MS + 400

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
  const tailMs = Math.max(opts.tailMs ?? SAFETY_MS, SAFETY_MS) // never shorter than the helper's worst case
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
