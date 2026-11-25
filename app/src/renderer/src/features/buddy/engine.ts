/**
 * Feature: buddy. bon's count from the engine (ui-v4 contract, shared/contracts/UI-V4.md section 2): the engine keeps how
 * many steps the learner has passed with the rest of their progress, so bon's level survives a new computer and is the
 * same in every window.
 *
 *   engine.hello   bon.import once per Mac (the count growth.ts kept in localStorage), when the hello lists bon.import;
 *                  then bon.get, when it lists bon.get. Neither is ever sent to an engine that did not list it.
 *   bon            { steps, level, ... }: growth.ts syncSteps(steps). Quiet. The engine's count is the count, down
 *                  too (Delete progress lowers bon). Only the first answer after this window's bon.import keeps the
 *                  larger of it and the count handed over: the engine keeps the larger on import, and so does this.
 *   step.passed    a ui-v4 pass (it carries `counted`, or its hello listed bon.get and it carries the contract's `key`)
 *                  grows bon only when `counted: true`: the engine already left out skipped, already-done and
 *                  counted-before passes. Any other pass (an older engine, or a scenario written before ui-v4: the
 *                  mock's default hello lists every V2 command) counts locally when it is not skipped and not
 *                  `already`, once per key: the fallback, as before ui-v4.
 *
 * Pure: createBonLink takes what it needs, so test/bonEngine.test.ts runs it without the bus or the bridge. wire.ts
 * wires it to the app.
 */
import type { PayloadOf } from '../../core/bus'

type Passed = Partial<PayloadOf<'step.passed'>> | null | undefined

const count = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : undefined)

/** The engine's passed-step count in a `bon` payload (BonState.steps), or undefined when it has none. */
export function bonSteps(payload: unknown): number | undefined {
  if (!payload || typeof payload !== 'object') return undefined
  return count((payload as { steps?: unknown }).steps)
}

export type BonDeps = {
  /** Did this connection's engine.hello list the command (core/lesson canSend)? */
  canSend: (type: string) => boolean
  /** Send one ui-v4 command to the engine. */
  send: (type: 'bon.get' | 'bon.import', payload: Record<string, unknown>) => void
  /** growth.ts: the count kept in localStorage (undefined when none was ever kept), and whether it was handed over. */
  local: () => { steps: number; seen: string[] } | undefined
  imported: () => boolean
  markImported: () => void
  /** growth.ts syncSteps / passStep. */
  sync: (steps: number) => void
  pass: (key: string) => number | undefined
  /** The running lesson's id, for a pass without a key. */
  lessonId: () => string | undefined
}

export type BonLink = {
  /** engine.hello arrived with these capabilities. */
  hello: (capabilities: unknown) => void
  /** A `bon` message. */
  bon: (payload: unknown) => void
  /** A step.passed. Returns the new level when this pass leveled bon up (the moment wire.ts plays), else undefined. */
  passed: (payload: Passed) => number | undefined
}

/** Does the engine say whether this pass counts? `listed`: its hello listed bon.get (it keeps bon's count). */
export function engineCounts(p: Passed, listed: boolean): boolean {
  if (!p) return false
  return typeof p.counted === 'boolean' || (listed && typeof p.key === 'string' && p.key !== '')
}

/** Does this pass grow bon? The engine's `counted` when it keeps the count, else any pass not skipped or already done. */
export function counts(p: Passed, listed: boolean): boolean {
  if (!p || typeof p.stepId !== 'string' || !p.stepId || p.skipped || p.already) return false
  return engineCounts(p, listed) ? p.counted === true : true
}

export function createBonLink(d: BonDeps): BonLink {
  /** The count handed over by this window's bon.import, until the engine's first answer after it. */
  let handed: number | undefined
  return {
    hello: (capabilities) => {
      const caps = Array.isArray(capabilities) ? capabilities.filter((c): c is string => typeof c === 'string') : []
      if (caps.includes('bon.import') && !d.imported()) {
        // Once per Mac: the engine keeps the larger count and adds `seen` to the keys it has counted.
        d.markImported()
        const kept = d.local()
        if (kept) {
          handed = kept.steps
          d.send('bon.import', { steps: kept.steps, seen: kept.seen })
        }
      }
      if (caps.includes('bon.get')) d.send('bon.get', {})
    },
    bon: (payload) => {
      const n = bonSteps(payload)
      if (n === undefined) return
      // The import's answer: the larger count wins, as in the engine. Every later `bon` is followed as it is.
      d.sync(handed !== undefined ? Math.max(n, handed) : n)
      handed = undefined
    },
    passed: (p) => {
      if (!counts(p, d.canSend('bon.get')) || !p) return undefined
      const key = typeof p.key === 'string' && p.key ? p.key : `${d.lessonId() ?? 'lesson'}:${p.stepId}`
      return d.pass(key)
    }
  }
}
