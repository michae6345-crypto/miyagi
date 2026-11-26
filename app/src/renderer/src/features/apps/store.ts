/**
 * Feature: apps. Live state for the sidebar's Apps, the picker and the app page.
 *
 *   useApps          main's scan ({appId: installed}), whether the picker is open (and where it hangs)
 *   refreshInstalled()  ask main again (the home window calls it on mount and when it comes forward)
 *   useAppStates()   installState for every supported app, from the scan, the engine's health and "I have it"
 *   useSidebarApps() the ids the sidebar lists (pinned, or the default)
 *   togglePin(id)    tick or untick an app in the picker (prefs.pinnedApps, saved by main like any Settings pref)
 *   resetPins()      back to miyagi's default list (pinnedApps null)
 *   markHave(id)     "I have it" (prefs.haveApps)
 *   openApp(id)      the app's page: the Library page with the plans view set to that app
 *   goToPage(id)     a sidebar or ⌘N page pick: Library from an app's page lands on the Library list
 *   getApp(id)       "Get <app>": its download page through main's setup list (never the engine, never any URL)
 */
import { useMemo } from 'react'
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { setPrefs, usePrefs } from '../../core/prefs'
import { useLibrary } from '../library/store'
import { PLANS } from '../plans/catalog'
import { showApp, showLibrary, usePlans } from '../plans/store'
import { useHealth } from '../settings/permissions'
import { setPage, useShell, type PageId } from '../shell/store'
import { appContent, appMeta, APPS, hasActivity, installState, libraryNavResets, sidebarApps, togglePinned, type InstallState } from './model'
import './web'

type State = {
  /** main's apps:installed answer; undefined until it answers (or when nothing does). */
  scan?: Record<string, boolean>
  /** The picker is open, hanging off this box (the Add app row's rect, viewport px). */
  picker: { x: number; y: number; w: number } | null
}

export const useApps = create<State>(() => ({ picker: null }))

const cleanScan = (r: unknown): Record<string, boolean> | undefined => {
  if (!r || typeof r !== 'object' || Array.isArray(r)) return undefined
  const out: Record<string, boolean> = {}
  for (const [k, v] of Object.entries(r as Record<string, unknown>)) if (typeof v === 'boolean') out[k] = v
  return out
}

export function refreshInstalled(): void {
  bridge
    .invoke<unknown>('apps:installed')
    .then((r) => useApps.setState({ scan: cleanScan(r) }))
    .catch(() => undefined)
}

/** installState for every supported app. `live`: ask the engine for its health rows (the home window is up). */
export function useAppStates(live = true): Record<string, InstallState> {
  const scan = useApps((s) => s.scan)
  const have = usePrefs((s) => s.haveApps)
  const health = useHealth(live)
  return useMemo(() => Object.fromEntries(APPS.map((a) => [a.id, installState(a.id, scan, health, have ?? [])])), [scan, have, health])
}

/** The sidebar's apps, in order, given useAppStates()'s answer. */
export function useSidebarApps(states: Record<string, InstallState>): string[] {
  const pinned = usePrefs((s) => s.pinnedApps)
  const items = useLibrary((s) => s.items)
  const mine = usePlans((s) => s.mine)
  return useMemo(
    () => sidebarApps(pinned ?? null, (id) => states[id] ?? 'unknown', (id) => hasActivity(appContent(id, PLANS, items, mine))),
    [pinned, states, items, mine]
  )
}

export function togglePin(shown: readonly string[], id: string): void {
  setPrefs({ pinnedApps: togglePinned(shown, id) })
}

export const resetPins = (): void => setPrefs({ pinnedApps: null })

export function markHave(id: string): void {
  const have = usePrefs.getState().haveApps ?? []
  if (!have.includes(id)) setPrefs({ haveApps: [...have, id] })
}

export function openPicker(at: { x: number; y: number; w: number }): void {
  useApps.setState({ picker: at })
}
export const closePicker = (): void => useApps.setState({ picker: null })

/** The app's page (Library / Browse plans / <app>, Adrian's MIC-87 trail). */
export function openApp(id: string): void {
  closePicker()
  setPage('lessons')
  showApp(id)
}

/** A page pick from the sidebar or ⌘N: Library from an app's page (or from Library's own views) shows the list. */
export function goToPage(id: PageId): void {
  if (libraryNavResets(id, useShell.getState().page, usePlans.getState().view)) showLibrary()
  setPage(id)
}

/** "Get <app>": main opens the page only if it is on its setup list (main/safeOpen.ts). */
export function getApp(id: string): void {
  const url = appMeta(id)?.getUrl
  if (url) void bridge.invoke('open:external', { setup: url }).catch(() => undefined)
}
