/**
 * Feature: sound. The rules for WHEN a cue may play, as a pure function of the clock, so the Node check can drive it.
 *
 *   - Off means off. Taps also need their own sub-toggle.
 *   - Never more than one cue per MIN_GAP_MS (400 ms). Every cue but the chime is shorter than 250 ms, so two never
 *     overlap; after the chime (900 ms, lesson complete) the next cue waits CHIME_GAP_MS instead.
 *   - Never while the learner types (any key in a field within TYPING_QUIET_MS), and never in Do Not Disturb.
 *     The learner mostly types outside miyagi (VS Code, the terminal), so before a tick or done the store also asks
 *     main how long the whole system has been idle; under SYSTEM_BUSY_S counts as busy now (withSystemIdle below).
 *   - A tick or done that is only blocked by the gap or by typing waits for it (one pending cue, the most important
 *     one), up to MAX_WAIT_MS after it was FIRST asked for; then it is dropped. A tap is never held: late feedback is
 *     noise. Typing in a miyagi field waits a fixed TYPING_QUIET_MS; input elsewhere is re-sampled every
 *     SYSTEM_POLL_MS and the cue plays at the first quiet sample (a pass mostly lands right after Cmd+S or
 *     Shift+Enter, and the idle clock is whole seconds, so a fixed wait from the pass would always trail the green).
 *
 * Pure module: no imports beyond the Cue type.
 */
import type { Cue } from './synth'

export const MIN_GAP_MS = 400
/** After the lesson-complete chime: it rings 900 ms, so nothing starts over its tail. */
export const CHIME_GAP_MS = 1000
export const TYPING_QUIET_MS = 1200
export const MAX_WAIT_MS = 2500
/** System-wide input (keys or mouse, any app) this recent counts as typing. getSystemIdleTime is whole seconds. */
export const SYSTEM_BUSY_S = 1
/** While a cue is held only by input elsewhere, the store asks for the system idle time again this often. */
export const SYSTEM_POLL_MS = 225

const RANK: Record<Cue, number> = { tap: 1, tick: 2, done: 3, chime: 4 }

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
  /** Key or mouse input anywhere on the Mac within SYSTEM_BUSY_S (set by withSystemIdle; absent = not known busy). */
  systemBusy?: boolean
}

/**
 * Fold the system idle time (seconds since the last key or mouse input anywhere; undefined when it can't be read) into
 * the env: any input within SYSTEM_BUSY_S marks the system busy, so the gate holds the cue, asks again after
 * SYSTEM_POLL_MS, and drops it MAX_WAIT_MS after the pass if the learner keeps going.
 */
export function withSystemIdle(env: GateEnv, idleSeconds: number | undefined): GateEnv {
  if (typeof idleSeconds !== 'number' || !Number.isFinite(idleSeconds) || idleSeconds >= SYSTEM_BUSY_S) return env
  return { ...env, systemBusy: true }
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
  /** How long the last cue keeps the gap closed (MIN_GAP_MS, or CHIME_GAP_MS after the chime). */
  let lastGap = MIN_GAP_MS
  let held: { cue: Cue; bornAt: number } | undefined

  const hold = (cue: Cue, bornAt: number, until: number, now: number): Verdict => {
    // One pending cue: the most important one wins; an equal one keeps the first (and its bornAt, so a second pass
    // never stretches the wait past MAX_WAIT_MS from the first).
    if (held && held.cue !== cue && RANK[held.cue] >= RANK[cue]) return { play: false, reason: 'outranked' }
    if (held?.cue === cue) bornAt = Math.min(held.bornAt, bornAt)
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
      const gapUntil = lastAt + lastGap
      if (now < typingUntil) return cue === 'tap' ? { play: false, reason: 'typing' } : hold(cue, bornAt, Math.max(typingUntil, gapUntil), now)
      // Input elsewhere: no fixed wait, the store samples the idle clock again after SYSTEM_POLL_MS.
      if (env.systemBusy) return cue === 'tap' ? { play: false, reason: 'typing' } : hold(cue, bornAt, Math.max(now + SYSTEM_POLL_MS, gapUntil), now)
      if (now < gapUntil) return cue === 'tap' ? { play: false, reason: 'gap' } : hold(cue, bornAt, gapUntil, now)

      release()
      lastAt = now
      lastGap = cue === 'chime' ? CHIME_GAP_MS : MIN_GAP_MS
      return { play: true }
    },
    pending: () => held,
    note(at) {
      if (at > lastAt) {
        lastAt = at
        lastGap = MIN_GAP_MS
      }
    },
    reset() {
      held = undefined
      lastAt = -Infinity
      lastGap = MIN_GAP_MS
    }
  }
}
