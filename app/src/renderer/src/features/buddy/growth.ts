/**
 * Feature: buddy. bon grows as the learner learns (Adrian, Nov 23: "i like the leaf growing, make it more pronounced,
 * multiple leaves and leveling up clear, gamify it, outline what it means").
 *
 * The rule, in one line the learner can read: bon grows each time you pass a step. A skipped step is not a pass, and
 * a step that was already done when the lesson got to it does not count either: only the ones passed by doing them.
 * Eight levels, each drawn clearly different (Character.tsx), from a seed's one leaf to a small shaped tree. The step
 * counts climb so the first levels come fast and the last ones are earned:
 *
 *   1 Seed        0   one leaf
 *   2 Sprout      3   two leaves
 *   3 Shoot       8   a third leaf, on a taller stem
 *   4 Sapling    15   four leaves in two tiers
 *   5 Budding    25   a bud
 *   6 In bloom   40   the bud opens
 *   7 Young tree 60   its first pad of foliage
 *   8 Bonsai     90   a small shaped tree: a trunk and three pads
 *
 *   useGrowth()       { steps, level, grew }   grew counts the level-ups that happened in this window
 *   passStep(key)     the engine said a step passed (wire.ts). `key` is the lesson and the step: one step counts once.
 *   progressOf(steps) the level, its name, and how far to the next one: what the growth card shows
 *
 * The count comes from the engine (ui-v4 `bon`, engine.ts): its passed-step counter, kept with the learner's progress
 * so it survives a new computer. sync(n) takes it. The count kept here before the engine kept one is handed to it once
 * per Mac (bon.import: local(), imported(), markImported()). The engine's count never lowers the one shown (a pass counted here a
 * moment before the engine's next answer would otherwise flicker back), and a sync never plays the level-up moment:
 * that belongs to the live step.passed.
 * The local count is the fallback, for an engine that does not send one yet: localStorage `miyagi.buddy.growth` in
 * the app, shared by every window and followed through the `storage` event; memory only in the browser stage, where
 * ?level=<1-8> or ?steps=<n> sets it.
 *
 * createGrowth() is the whole of it without the browser, so test/buddyGrowth.test.ts can run it.
 */
import { create, type StoreApi, type UseBoundStore } from 'zustand'

export type Level = { name: string; at: number; has: string }

export const LEVELS: readonly Level[] = [
  { name: 'Seed', at: 0, has: 'one leaf' },
  { name: 'Sprout', at: 3, has: 'two leaves' },
  { name: 'Shoot', at: 8, has: 'a third leaf' },
  { name: 'Sapling', at: 15, has: 'four leaves' },
  { name: 'Budding', at: 25, has: 'a bud' },
  { name: 'In bloom', at: 40, has: 'a blossom' },
  { name: 'Young tree', at: 60, has: 'its first pad' },
  { name: 'Bonsai', at: 90, has: 'a shaped tree' }
]
export const MAX_LEVEL = LEVELS.length

/** A level number kept to 1..MAX_LEVEL. */
export function clampLevel(n: unknown): number {
  const v = typeof n === 'number' && Number.isFinite(n) ? Math.round(n) : 1
  return Math.max(1, Math.min(MAX_LEVEL, v))
}

/** The level (1..8) for this many passed steps. */
export function levelFor(steps: number): number {
  let level = 1
  LEVELS.forEach((l, i) => {
    if (steps >= l.at) level = i + 1
  })
  return level
}

export type Progress = {
  level: number
  name: string
  steps: number
  /** The next level, when there is one. */
  next?: { level: number; name: string; at: number; left: number }
  /** How far through this level, 0..1 (1 at the last level). */
  fraction: number
}

export function progressOf(steps: number): Progress {
  const n = Math.max(0, Math.floor(Number.isFinite(steps) ? steps : 0))
  const level = levelFor(n)
  const here = LEVELS[level - 1]
  const up = LEVELS[level]
  if (!up) return { level, name: here.name, steps: n, fraction: 1 }
  return { level, name: here.name, steps: n, next: { level: level + 1, name: up.name, at: up.at, left: up.at - n }, fraction: (n - here.at) / (up.at - here.at) }
}

export const GROWTH_KEY = 'miyagi.buddy.growth'
/** Set once this Mac's local count was handed to the engine (bon.import). */
export const IMPORTED_KEY = 'miyagi.buddy.imported'
/** How many passed steps are remembered by name, so a replayed pass is not counted twice. */
const SEEN_MAX = 400

type GrowthState = { steps: number; level: number; grew: number }
type Saved = { steps: number; seen: string[]; engine?: number }
type Env = { app: boolean; search?: string; storage?: Pick<Storage, 'getItem' | 'setItem'> }

export type Growth = {
  store: UseBoundStore<StoreApi<GrowthState>>
  /** Count one passed step. Returns the new level when this pass leveled bon up, else undefined. */
  pass: (key: string) => number | undefined
  /** The engine's passed-step count (contract ui-v4). Quiet: no level-up moment. Ignores anything not a count. */
  sync: (engineSteps: unknown) => void
  onStorage: (key: string | null, value: string | null) => void
  /** The count kept in localStorage (the app only), for bon.import; undefined when none was ever kept. */
  local: () => { steps: number; seen: string[] } | undefined
  /** Was the local count handed to the engine on this Mac? (The browser stage has nothing to hand over: always true.) */
  imported: () => boolean
  markImported: () => void
}

function parse(raw: string | null | undefined): Saved | undefined {
  if (!raw) return undefined
  try {
    const v = JSON.parse(raw) as { steps?: unknown; seen?: unknown }
    if (typeof v.steps !== 'number' || !Number.isFinite(v.steps) || v.steps < 0) return undefined
    const seen = Array.isArray(v.seen) ? v.seen.filter((k): k is string => typeof k === 'string').slice(-SEEN_MAX) : []
    const engine = (v as { engine?: unknown }).engine
    return { steps: Math.floor(v.steps), seen, ...(typeof engine === 'number' && Number.isFinite(engine) && engine >= 0 ? { engine: Math.floor(engine) } : {}) }
  } catch {
    return undefined
  }
}

export function createGrowth(env: Env): Growth {
  const read = (): Saved | undefined => {
    if (!env.app) return undefined
    try {
      return parse(env.storage?.getItem(GROWTH_KEY))
    } catch {
      return undefined
    }
  }
  const fromStage = (): number | undefined => {
    if (env.app) return undefined
    const q = new URLSearchParams(env.search ?? '')
    const level = Number(q.get('level'))
    if (q.has('level') && Number.isFinite(level)) return LEVELS[clampLevel(level) - 1].at
    const steps = Number(q.get('steps'))
    return q.has('steps') && Number.isFinite(steps) && steps >= 0 ? Math.floor(steps) : undefined
  }
  const first = read()
  let mem: Saved = first ?? { steps: fromStage() ?? 0, seen: [] }
  const store = create<GrowthState>(() => ({ steps: mem.steps, level: levelFor(mem.steps), grew: 0 }))
  return {
    store,
    pass: (key) => {
      // Another window may have counted since this one last looked: start from what is saved.
      mem = read() ?? mem
      if (!key || mem.seen.includes(key)) {
        if (store.getState().steps !== mem.steps) store.setState({ steps: mem.steps, level: levelFor(mem.steps) })
        return undefined
      }
      const before = levelFor(mem.steps)
      mem = { ...mem, steps: mem.steps + 1, seen: [...mem.seen, key].slice(-SEEN_MAX) }
      if (env.app) {
        try {
          env.storage?.setItem(GROWTH_KEY, JSON.stringify(mem))
        } catch {
          // No storage: it grows for this window.
        }
      }
      const level = levelFor(mem.steps)
      const up = level > before
      store.setState((s) => ({ steps: mem.steps, level, grew: up ? s.grew + 1 : s.grew }))
      return up ? level : undefined
    },
    sync: (engineSteps) => {
      if (typeof engineSteps !== 'number' || !Number.isFinite(engineSteps) || engineSteps < 0) return
      const n = Math.floor(engineSteps)
      mem = read() ?? mem
      if (mem.engine === n && mem.steps >= n) return
      mem = { ...mem, steps: Math.max(mem.steps, n), engine: n }
      if (env.app) {
        try {
          env.storage?.setItem(GROWTH_KEY, JSON.stringify(mem))
        } catch {
          // No storage: the engine's count still shows in this window.
        }
      }
      if (store.getState().steps !== mem.steps) store.setState({ steps: mem.steps, level: levelFor(mem.steps) })
    },
    local: () => {
      const saved = read()
      return saved ? { steps: saved.steps, seen: saved.seen } : undefined
    },
    imported: () => {
      if (!env.app) return true
      try {
        return !!env.storage?.getItem(IMPORTED_KEY)
      } catch {
        return false
      }
    },
    markImported: () => {
      if (!env.app) return
      try {
        env.storage?.setItem(IMPORTED_KEY, '1')
      } catch {
        // No storage: nothing was kept to hand over either.
      }
    },
    onStorage: (key, value) => {
      if (!env.app || key !== GROWTH_KEY) return
      const next = parse(value)
      if (!next) return
      mem = next
      // Another window counted it: follow, quietly (the level-up moment belongs to the window that saw the pass).
      store.setState({ steps: next.steps, level: levelFor(next.steps) })
    }
  }
}

const here = typeof window !== 'undefined'
const app = here && 'tut' in window
const storage = ((): Env['storage'] => {
  try {
    return here ? window.localStorage : undefined
  } catch {
    return undefined
  }
})()
const growth = createGrowth({ app, search: here ? window.location.search : '', storage })
if (here && app) window.addEventListener('storage', (e) => growth.onStorage(e.key, e.newValue))

export const useGrowth = growth.store
export const passStep = growth.pass
export const syncSteps = growth.sync
export const localSteps = growth.local
export const bonImported = growth.imported
export const markBonImported = growth.markImported
