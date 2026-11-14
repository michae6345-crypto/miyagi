/** Feature: launcher. Search state (results stream in from the engine). */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'

export type SearchResult = Payload<'search.result'>
type SearchState = { query: string; results: SearchResult[]; done: boolean; pending: boolean }

const blank: SearchState = { query: '', results: [], done: false, pending: false }
export const useSearch = create<SearchState>(() => ({ ...blank }))

export const startSearch = (query: string): void => useSearch.setState({ query, results: [], done: false, pending: true })

onUi('reset', () => useSearch.setState({ ...blank }))
onMessage('search.result', (p) => useSearch.setState((s) => ({ results: s.results.filter((r) => r.id !== p.id).concat(p), pending: true })))
onMessage('search.done', () => useSearch.setState({ done: true, pending: false }))
