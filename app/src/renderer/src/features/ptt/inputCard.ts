/**
 * Feature: ptt. When the Input Monitoring card may show. Pure, so the rule is tested without a window.
 *
 * Without Input Monitoring a hold can never reach the helper, so this card is the learner's only way in. It shows only
 * when push to talk is on, Input Monitoring is off, the launch gate is open (signed in and first-run setup finished or
 * put off: main/gate.ts; a card there would talk over the guided steps), and the learner hasn't said "Not now" this run.
 * The card closes by itself after a few seconds, so a learner who wasn't looking would never see it: it comes back
 * every REOFFER_MS, at most MAX_OFFERS times a run. Allow, or granting it in System Settings, ends it.
 */
export type InputCardFacts = {
  /** How many times it has shown this run. */
  shownCount: number
  /** Milliseconds since it last showed (ignored while shownCount is 0). */
  sinceLastMs: number
  /** The learner pressed "Not now" this run. */
  declined: boolean
  inputDenied: boolean
  enabled: boolean
  gateOpen: boolean
}

export const REOFFER_MS = 5 * 60_000
export const MAX_OFFERS = 6

export function shouldShowInputCard(f: InputCardFacts): boolean {
  if (f.declined || !f.inputDenied || !f.enabled || !f.gateOpen) return false
  if (f.shownCount === 0) return true
  return f.shownCount < MAX_OFFERS && f.sinceLastMs >= REOFFER_MS
}
