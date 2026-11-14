/** Feature: launcher. Search state: results stream in from the engine; errors land here while a search is live. */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'

/**
 * Extra fields the engine sends on search.result (server/finder/core.py PUBLIC_FIELDS), not in the contract yet.
 *   warnings : up to 3 raw learner comments (≤200 chars) the engine's filter flagged (videos). Quote them, never paraphrase.
 *   verified : true = the link was checked live; 'indexed' = only a search engine returned it. Missing = unknown.
 */
export type ResultExtras = { warnings?: string[]; verified?: true | 'indexed' }
export type SearchResult = Payload<'search.result'> & ResultExtras

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
export const setLauncherOpen = (open: boolean): void => {
  if (get().open !== open) set({ open })
}

onUi('reset', () => set({ ...blank }))

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
    return { results: [...s.results, p], pending: !s.done, error: undefined }
  })
})
onMessage('search.done', (p) => set({ done: true, pending: false, total: p.total }))
onMessage('error', (p) => {
  const s = get()
  if (s.pending || s.open) set({ error: p.message, pending: false })
})
