/**
 * Feature: shell. The home window's pages and which one is on show (agents/shell.md).
 *
 *   PAGES          Home, Lessons, Skills, Progress, Settings, Account, in sidebar order (⌘1..⌘6 follow it)
 *   useShell       the page on show and the pages visited so far (a visited page stays mounted, so it keeps its
 *                  scroll and its state when the learner comes back)
 *   setPage(id)    switch, instantly (the content crossfades on the house spring; Shell.tsx)
 *   openPage(id)   from another surface: the home window, opened (or brought forward) on that page. Same window as
 *                  openLibrary() (core/surfaces), with args {page}; LibraryWindow reads them.
 *
 * Library's own section store still exists (Home's "See all" calls setSection('library')): any section other than
 * home is read here as "go to Lessons", and the section is put back to home so the next "See all" fires again.
 */
import { ChartNoAxesColumn, CircleUserRound, House, LibraryBig, Settings, Waypoints, type LucideIcon } from 'lucide-react'
import { create } from 'zustand'
import { openWindow, type SettingsSection } from '../../core/surfaces'
import { closeDetail, useLibrary } from '../library/store'

export type PageId = 'home' | 'lessons' | 'skills' | 'progress' | 'settings' | 'account'

export const PAGES: ReadonlyArray<{ id: PageId; label: string; icon: LucideIcon }> = [
  { id: 'home', label: 'Home', icon: House },
  { id: 'lessons', label: 'Lessons', icon: LibraryBig },
  { id: 'skills', label: 'Skills', icon: Waypoints },
  { id: 'progress', label: 'Progress', icon: ChartNoAxesColumn },
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'account', label: 'Account', icon: CircleUserRound }
]

export const isPage = (v: unknown): v is PageId => typeof v === 'string' && PAGES.some((p) => p.id === v)

type State = {
  page: PageId
  /** Pages mounted so far. Home is always there (it is the window's first view). */
  visited: PageId[]
  /** The Settings page's section (its own, not the settings sheet's: the sheet is another window). */
  settings: SettingsSection
}

export const useShell = create<State>(() => ({ page: 'home', visited: ['home'], settings: 'general' }))

export function setPage(page: PageId): void {
  const s = useShell.getState()
  // A lesson's preview belongs to the page it was opened from: switching pages closes it.
  if (useLibrary.getState().openId) closeDetail()
  if (s.page === page) return
  useShell.setState({ page, visited: s.visited.includes(page) ? s.visited : [...s.visited, page] })
}

const SECTIONS: readonly SettingsSection[] = ['general', 'permissions', 'privacy', 'account', 'shortcuts']
export const isSettingsSection = (v: unknown): v is SettingsSection => typeof v === 'string' && (SECTIONS as readonly string[]).includes(v)

export function setSettingsSection(section: SettingsSection): void {
  useShell.setState({ settings: section })
}

/** Open the home window on a page (and, for Settings, a section). Works from any window. */
export function openPage(page: PageId, section?: SettingsSection): Promise<boolean | undefined> {
  return openWindow('library', section ? { page, section } : { page })
}

/** Step one page up or down the sidebar, wrapping. */
export function stepPage(dir: 1 | -1): void {
  const i = PAGES.findIndex((p) => p.id === useShell.getState().page)
  setPage(PAGES[(i + dir + PAGES.length) % PAGES.length].id)
}

// Home's "See all N" (and anything else that asks Library for its list) lands on Lessons.
useLibrary.subscribe((s, prev) => {
  if (s.section === prev.section || s.section === 'home') return
  setPage('lessons')
  useLibrary.setState({ section: 'home' })
})
