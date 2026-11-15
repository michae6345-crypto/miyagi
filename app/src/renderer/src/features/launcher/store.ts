/**
 * Feature: launcher. Search state: results stream in from the engine; errors land here while a search is live.
 * Videos only (Michael, Sat): a search offers YouTube tutorials or "Build a lesson from the internet", never
 * repos, papers, blogs or notebooks. The engine stops sending those; any that still arrive are dropped here.
 */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'

/**
 * One result row (contract search.result, incl. the finder fields). The launcher uses:
 *   warnings : up to 3 raw learner comments the engine's filter flagged (videos). Quoted, never paraphrased.
 *   verified : true = the engine opened the link itself.
 *   style / long / durationLabel : at most one extra meta segment ("No-code", "1 h 56 min · 30 chapters").
 */
export type SearchResult = Payload<'search.result'>

type SearchState = {
  /** The query the results belong to (the input may have moved on). */
  query: string
  results: SearchResult[]
  /** A learn is in flight: rows may still stream in. */
  pending: boolean
  done: boolean
  total?: number
  /** Engine `error` that arrived while a search was in flight or the launcher was open. */
  error?: string
  /** The launcher panel is showing (set by the component). */
  open: boolean
}

const blank = { query: '', results: [], pending: false, done: false, total: undefined, error: undefined } satisfies Partial<SearchState>

export const useSearch = create<SearchState>(() => ({ ...blank, open: false }))
const set = useSearch.setState
const get = useSearch.getState

export const startSearch = (query: string): void => set({ ...blank, query, pending: true })
/** A pasted link replaces the lesson and the old results with it. */
export const clearResults = (): void => set({ ...blank })
export const setLauncherOpen = (open: boolean): void => {
  if (get().open !== open) set({ open })
}

// A lesson-only reset (engine `lesson.ended`) must not wipe a search the learner is typing.
onUi('reset', (p) => {
  if ((p as { scope?: string } | undefined)?.scope === 'lesson') return
  set({ ...blank })
})

onMessage('search.result', (payload) => {
  const p = payload as SearchResult
  set((s) => {
    // The engine may re-send a row (same id) with more fields, e.g. learner warnings: update it in place, same slot.
    const i = s.results.findIndex((r) => r.id === p.id)
    if (i >= 0) {
      const results = s.results.slice()
      results[i] = { ...results[i], ...p }
      return { results }
    }
    if (!p.title) return s // an update for a row we never received: nothing to show
    if (p.kind !== 'video') return s // videos only: the list never shows repos, papers, blogs or notebooks
    return { results: [...s.results, p], pending: !s.done, error: undefined }
  })
})
onMessage('search.done', (p) => set({ done: true, pending: false, total: p.total }))
onMessage('error', (p) => {
  const s = get()
  if (s.pending || s.open) set({ error: p.message, pending: false })
})
