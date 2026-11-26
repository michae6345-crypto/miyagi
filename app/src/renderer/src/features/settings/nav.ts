/**
 * Feature: settings. Search across settings and the "flash" that points at the row a result opened. Shared by the sheet
 * and the Settings page; neither keeps the other's panel (the sheet's is store.ts `section`, the page's is `page`).
 */
import { create } from 'zustand'
import type { PanelId } from './panels'

type Nav = {
  query: string
  /** The row (data-setting) to scroll to and highlight once, after a result opened its panel. */
  flash?: { id: string; n: number }
  /** The panel on show in the home window's Settings page. */
  page: PanelId
}

export const useNav = create<Nav>(() => ({ query: '', page: 'general' }))

export const setQuery = (query: string): void => useNav.setState({ query })
export const setPagePanel = (page: PanelId): void => useNav.setState({ page, query: '' })
export const flashRow = (id: string): void => useNav.setState((s) => ({ flash: { id, n: (s.flash?.n ?? 0) + 1 } }))
