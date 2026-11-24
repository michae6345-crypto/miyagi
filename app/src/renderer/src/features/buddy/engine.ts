/**
 * Feature: buddy. bon's count from the engine (v4): the engine keeps how many steps the learner has passed with the rest
 * of their progress, so bon's level survives a new computer and is the same in every window. growth.ts syncSteps takes
 * it; the local count stays as the fallback for an engine that does not send one.
 *
 * Where it comes from: the ui-v4 contract (shared/contracts/UI-V4.md, owned by the contract agent) was not on
 * michael/app-ui-v4 when this was written, so passedOf reads the count from the places it is likely to land, typed
 * locally (EngineBon). When the contract lands, keep only its field here; nothing else in buddy changes.
 *
 * passedOf is pure, so test/buddyGrowth.test.ts checks it without the bus.
 */
import { onMessage } from '../../core/bus'
import { syncSteps } from './growth'

/** The shapes the engine's passed-step count may arrive in (placeholder until the ui-v4 contract lands). */
export type EngineBon = {
  bon?: { passed?: number | null; level?: number | null } | null
  activity?: { stepsPassed?: number | null } | null
  stepsPassed?: number | null
  passedSteps?: number | null
  /** On step.passed: the learner's total after this pass. */
  passedTotal?: number | null
}

const count = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : undefined)

/** The engine's passed-step count in this payload, or undefined when it has none. */
export function passedOf(payload: unknown): number | undefined {
  if (!payload || typeof payload !== 'object') return undefined
  const p = payload as EngineBon
  return count(p.bon?.passed) ?? count(p.activity?.stepsPassed) ?? count(p.stepsPassed) ?? count(p.passedSteps) ?? count(p.passedTotal)
}

const take = (payload: unknown): void => {
  const n = passedOf(payload)
  if (n !== undefined) syncSteps(n)
}

// progress.get's answer (the Progress and Home pages ask for it) carries the count; so may a pass, as a running total.
// The live level-up moment stays with wire.ts's step.passed handler; a sync is quiet.
onMessage('progress', take)
onMessage('step.passed', (p) => {
  // After wire.ts counted this pass locally (features load in file order: engine.ts is imported after wire.ts).
  queueMicrotask(() => take(p))
})
