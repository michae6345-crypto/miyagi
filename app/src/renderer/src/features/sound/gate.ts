/**
 * Feature: sound. The rules for WHEN a cue may play, as a pure function of the clock, so the Node check can drive it.
 *
 *   - Off means off. Taps also need their own sub-toggle.
 *   - Never more than one cue per MIN_GAP_MS (400 ms). Every cue is shorter than 250 ms, so two never overlap.
 *   - Never while the learner types (any key in a field within TYPING_QUIET_MS), and never in Do Not Disturb.
 *     The learner mostly types outside miyagi (VS Code, the terminal), so before a tick or done the store also asks
 *     main how long the whole system has been idle; under SYSTEM_BUSY_S counts as typing now (withSystemIdle below).
 *   - A tick or done that is only blocked by the gap or by typing waits for it (one pending cue, the most important
 *     one), up to MAX_WAIT_MS after it was asked for; then it is dropped. A tap is never held: late feedback is noise.
 *
 * Pure module: no imports beyond the Cue type.
 */
import type { Cue } from './synth'

export const MIN_GAP_MS = 400
export const TYPING_QUIET_MS = 1200
export const MAX_WAIT_MS = 2500
/** System-wide input (keys or mouse, any app) this recent counts as typing. getSystemIdleTime is whole seconds. */
export const SYSTEM_BUSY_S = 1

const RANK: Record<Cue, number> = { tap: 1, tick: 2, done: 3 }

export type GateEnv = {
  now: number
  /** Sounds: Subtle. */
  enabled: boolean
  /** The "primary press" sub-toggle. */
  taps: boolean
  /** Last key typed into a field, in any miyagi window (ms epoch; 0 = never). */
  typingAt: number
  /** macOS Do Not Disturb / a Focus is on (false when it can't be read). */
  dnd: boolean
}

/**
 * Fold the system idle time (seconds since the last key or mouse input anywhere; undefined when it can't be read) into
 * the env: any input within SYSTEM_BUSY_S counts as a keystroke right now, so the gate holds the cue and drops it after
 * MAX_WAIT_MS if the learner keeps going.
 */
export function withSystemIdle(env: GateEnv, idleSeconds: number | undefined): GateEnv {
  if (typeof idleSeconds !== 'number' || !Number.isFinite(idleSeconds) || idleSeconds >= SYSTEM_BUSY_S) return env
  return { ...env, typingAt: Math.max(env.typingAt, env.now) }
}

export type Verdict =
  | { play: true }
  | { play: false; reason: 'off' | 'taps-off' | 'dnd' | 'typing' | 'gap' | 'stale' | 'outranked' }
  | { play: false; reason: 'held'; retryInMs: number }

export type Gate = {
  /** Ask to play `cue`, first asked for at `bornAt` (pass env.now for a fresh cue; the original time on a retry). */
  ask(cue: Cue, env: GateEnv, bornAt?: number): Verdict
  /** The cue that is waiting, if any (the caller re-asks for it after retryInMs). */
  pending(): { cue: Cue; bornAt: number } | undefined
  /** Another miyagi window played a cue at `at` (ms epoch): the gap counts from it too. */
  note(at: number): void
  /** Forget everything (lesson reset). */
  reset(): void
}

export function createGate(): Gate {
  let lastAt = -Infinity
  let held: { cue: Cue; bornAt: number } | undefined

  const hold = (cue: Cue, bornAt: number, until: number, now: number): Verdict => {
    // One pending cue: the most important one wins; an equal one keeps the first.
    if (held && held.cue !== cue && RANK[held.cue] >= RANK[cue]) return { play: false, reason: 'outranked' }
    if (until - bornAt > MAX_WAIT_MS) {
      if (held?.cue === cue) held = undefined
      return { play: false, reason: 'stale' }
    }
    held = { cue, bornAt }
    return { play: false, reason: 'held', retryInMs: Math.max(1, Math.ceil(until - now)) }
  }

  return {
    ask(cue, env, bornAt = env.now) {
      const { now } = env
      const release = (): void => {
        if (held?.cue === cue) held = undefined
      }
      if (!env.enabled) return release(), { play: false, reason: 'off' }
      if (cue === 'tap' && !env.taps) return { play: false, reason: 'taps-off' }
      if (env.dnd) return release(), { play: false, reason: 'dnd' }
      if (now - bornAt > MAX_WAIT_MS) return release(), { play: false, reason: 'stale' }
      // A higher-ranked cue is waiting: nothing smaller jumps the queue.
      if (held && held.cue !== cue && RANK[held.cue] > RANK[cue]) return { play: false, reason: 'outranked' }

      const typingUntil = env.typingAt > 0 ? env.typingAt + TYPING_QUIET_MS : -Infinity
      const gapUntil = lastAt + MIN_GAP_MS
      if (now < typingUntil) return cue === 'tap' ? { play: false, reason: 'typing' } : hold(cue, bornAt, Math.max(typingUntil, gapUntil), now)
      if (now < gapUntil) return cue === 'tap' ? { play: false, reason: 'gap' } : hold(cue, bornAt, gapUntil, now)

      release()
      lastAt = now
      return { play: true }
    },
    pending: () => held,
    note(at) {
      if (at > lastAt) lastAt = at
    },
    reset() {
      held = undefined
      lastAt = -Infinity
    }
  }
}
