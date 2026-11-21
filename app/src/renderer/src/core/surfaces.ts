/**
 * Core (v2, W0-4): open another surface without importing the feature that owns it. Every opener is a
 * bridge.invoke, so no feature imports another feature's opener (BUILD-PLAN W0-4).
 *
 *   openOnboarding()            the Onboarding app window
 *   openSettings(section?)      the Settings sheet, grown from the pill (settings feature, main/features/settings.ts)
 *   openLibrary(id?)            the Library app window, on a lesson's detail when `id` is given
 *   openProgress()              the Progress app window
 *   openAccount(view)           the Account sheet (v2Cloud only; A9)
 *   closeWindow(route?)         close an app window (no route: the one this code runs in)
 *   useWindowArgs(route)        inside an app window: the args it was opened with (updates on every re-open)
 *
 * In Electron, main/appWindows.ts opens only allowlisted routes. In the browser stage, bridge.ts stands in: the
 * window shows over the stage (and ?window=<route> opens one on load).
 */
import { useEffect, useState } from 'react'
import { bridge } from '../bridge'

export type AppRoute = 'onboarding' | 'library' | 'progress' | 'account'
export type SettingsSection = 'general' | 'permissions' | 'privacy' | 'account' | 'shortcuts'
export type AccountView = 'menu' | 'upgrade' | 'signin' | 'pricing'
export type WindowArgs = Record<string, string | number | boolean>

const quiet = <T>(p: Promise<T>): Promise<T | undefined> =>
  p.catch((err) => {
    console.warn('[surfaces]', err instanceof Error ? err.message : 'failed')
    return undefined
  })

export function openWindow(route: AppRoute, args?: WindowArgs): Promise<boolean | undefined> {
  return quiet(bridge.invoke<boolean>('window:open', route, args))
}
export function closeWindow(route?: AppRoute): Promise<boolean | undefined> {
  return quiet(bridge.invoke<boolean>('window:close', route))
}
export function focusWindow(route: AppRoute): Promise<boolean | undefined> {
  return quiet(bridge.invoke<boolean>('window:focus', route))
}

export const openOnboarding = (): Promise<boolean | undefined> => openWindow('onboarding')
export const openLibrary = (id?: string): Promise<boolean | undefined> => openWindow('library', id ? { id } : undefined)
export const openProgress = (): Promise<boolean | undefined> => openWindow('progress')
export const openAccount = (view: AccountView): Promise<boolean | undefined> => openWindow('account', { view })
/** Settings stays the grow-from-pill sheet (decision 4); the section is a hint its feature reads (A4). */
export const openSettings = (section?: SettingsSection): Promise<unknown> => quiet(bridge.invoke('settings:open', section ? { section } : undefined))

/** Inside an app window: its args, now and on every later open (feat:window:args). `route` is for the browser stage. */
export function useWindowArgs(route: AppRoute): WindowArgs | undefined {
  const [args, setArgs] = useState<WindowArgs | undefined>(undefined)
  useEffect(() => {
    let live = true
    bridge
      .invoke<WindowArgs | null>('window:args', route)
      .then((a) => live && setArgs(a ?? undefined))
      .catch(() => undefined)
    const off = bridge.onFeature('window:args', (a) => {
      const p = a as { route?: string; args?: WindowArgs } | WindowArgs | null | undefined
      // Electron sends the args to that window only; the stage's single bus tags them with the route.
      if (p && typeof p === 'object' && 'route' in p && typeof p.route === 'string') {
        if (p.route === route) setArgs((p as { args?: WindowArgs }).args)
      } else setArgs((p as WindowArgs | null) ?? undefined)
    })
    return () => {
      live = false
      off()
    }
  }, [route])
  return args
}
