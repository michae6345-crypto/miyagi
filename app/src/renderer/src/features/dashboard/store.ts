/**
 * Feature: dashboard. The lesson dashboard's state, shared by the two windows that show it (Library's Home section and
 * the Progress window):
 *
 *   data       the engine's `progress` answer, read by types.ts (both wire shapes). Asked for through the progress
 *              store (requestProgress: capability check, progress.get, the empty-state timeout); this store keeps the
 *              raw answer's extra fields that the contract type drops.
 *   prefs      the learner's daily goal, weekly goal and rhythm pause, kept on this Mac (localStorage) until the engine
 *              has a settings record (agents/dashboard.md, Core requests). Engine settings fill in what's unset.
 *   selected   the skill whose card is open.
 *   starting   a lesson start in flight (library.start, zero model calls) or a learn sent for an up-next goal.
 */
import { create } from 'zustand'
import { cmd, type Outgoing } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend } from '../../core/lesson'
import { closeWindow, type AppRoute } from '../../core/surfaces'
import { requestProgress, useProgress } from '../progress/store'
import { stageRebase } from './stage'
import { readDashboard, type DashData, type ReviewEntry } from './types'

export type Prefs = { daily?: number; weekly?: number; pause?: { from: number; until: number } | null }
export type Selected = { track: string; id: string }

type State = {
  data?: DashData
  prefs: Prefs
  selected?: Selected
  /** The 12-week grid instead of this week's strip. */
  showGrid: boolean
  starting?: string
  startError?: { key: string; text: string }
}

const PREFS_KEY = 'miyagi.dashboard.prefs'
const START_MS = 15_000

function loadPrefs(): Prefs {
  try {
    const raw = JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') as Record<string, unknown>
    const n = (v: unknown, max: number): number | undefined => (typeof v === 'number' && v >= 1 && v <= max ? Math.floor(v) : undefined)
    const p = raw.pause as { from?: unknown; until?: unknown } | null | undefined
    const pause = p && typeof p.from === 'number' && typeof p.until === 'number' ? { from: p.from, until: p.until } : p === null ? null : undefined
    return { daily: n(raw.daily, 10), weekly: n(raw.weekly, 7), pause }
  } catch {
    return {}
  }
}
function savePrefs(p: Prefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(p))
  } catch {
    // Private mode or no storage: the choice holds for this window only.
  }
}

export const useDash = create<State>(() => ({ prefs: loadPrefs(), showGrid: false }))
const set = useDash.setState
const get = useDash.getState

onMessage('progress', (raw) => {
  const data = readDashboard(stageRebase(raw))
  set({ data })
})

/** Ask for fresh data: paint what main last saw at once, then progress.get (when the engine lists it). */
export async function requestDashboard(): Promise<void> {
  if (!get().data) {
    const last = await bridge.invoke<unknown>('progress:last').catch(() => undefined)
    const cached = last ? readDashboard(stageRebase(last)) : undefined
    if (cached && !get().data) set({ data: cached })
  }
  await requestProgress()
}

/** Loading (nothing to show yet) / none (the engine has nothing, or can't answer) / ready. */
export function useLoad(): 'loading' | 'none' | 'ready' {
  const has = useDash((s) => !!s.data)
  const load = useProgress((s) => s.load)
  if (has) return 'ready'
  return load === 'none' ? 'none' : 'loading'
}

// ---- prefs ------------------------------------------------------------------------------------------------------

export function setDailyGoal(n: number): void {
  const prefs = { ...get().prefs, daily: Math.max(1, Math.min(10, Math.round(n))) }
  savePrefs(prefs)
  set({ prefs })
}
export function pauseRhythm(weeks: number, now = Date.now()): void {
  const prefs = { ...get().prefs, pause: { from: now, until: now + Math.max(1, Math.min(4, weeks)) * 7 * 86_400_000 } }
  savePrefs(prefs)
  set({ prefs })
}
export function resumeRhythm(): void {
  const prefs = { ...get().prefs, pause: null }
  savePrefs(prefs)
  set({ prefs })
}
export const toggleGrid = (): void => set((s) => ({ showGrid: !s.showGrid }))

// ---- selection --------------------------------------------------------------------------------------------------

export const select = (sel?: Selected): void => set({ selected: sel })

// ---- starting lessons -------------------------------------------------------------------------------------------

/**
 * A lesson saved on this Mac: library.start {id} through main (zero model calls). Waits for lesson.ready, then closes
 * this window so the lesson has the screen. Never falls back to `learn`.
 */
export async function startSaved(libraryId: string, route: AppRoute): Promise<void> {
  if (get().starting) return
  set({ starting: libraryId, startError: undefined })
  const sent = await bridge.invoke<boolean>('library:start', libraryId).catch(() => false)
  if (!sent) {
    set({ starting: undefined, startError: { key: libraryId, text: 'This engine can’t start saved lessons yet.' } })
    return
  }
  const outcome = await new Promise<'ready' | 'error' | 'timeout'>((resolve) => {
    const offs: Array<() => void> = []
    const done = (r: 'ready' | 'error' | 'timeout'): void => {
      clearTimeout(timer)
      offs.forEach((f) => f())
      resolve(r)
    }
    const timer = setTimeout(() => done('timeout'), START_MS)
    offs.push(onMessage('lesson.ready', () => done('ready')))
    offs.push(onMessage('error', () => done('error')))
  })
  set({ starting: undefined })
  if (outcome === 'ready') {
    void closeWindow(route)
    return
  }
  set({ startError: { key: libraryId, text: outcome === 'error' ? 'That lesson didn’t start. Try again.' : 'No answer from the engine yet. Try again.' } })
}

/**
 * An up-next lesson that isn't saved yet: the launcher's "Just teach me" (learn {query: goal, mode: "lesson"}, the same
 * as the completion card's Start next lesson). The island shows the build, so this window steps aside.
 */
export function startGoal(goal: string, route: AppRoute): void {
  if (get().starting) return
  bridge.send(cmd('learn', { query: goal, mode: 'lesson' }))
  void closeWindow(route)
}

/** The engine can take a review (review.start listed). Until it does, Start review stays disabled. */
export const canReview = (): boolean => canSend('review.start') || useProgress.getState().caps.review

/** review.start {skillId, label}: not in the contract yet (Core request), sent only when the engine lists it. */
export function startReview(item: ReviewEntry, route: AppRoute): void {
  if (!canReview()) return
  bridge.send({ type: 'review.start', payload: { skillId: item.skillId, label: item.label } } as unknown as Outgoing)
  void closeWindow(route)
}
