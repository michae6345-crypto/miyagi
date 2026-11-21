/**
 * Core (v2, W0-4): open another surface without importing the feature that owns it. Every opener is a
 * bridge.invoke, so no feature imports another feature's opener (BUILD-PLAN W0-4).
 *
 *   openOnboarding()            guided setup: in the home window, over home (the first-run flow layer); from any other
 *                               window, the home window opens on it ({setup}); the standalone setup window only when
 *                               the home window can't open (one window from start to finish, Michael Nov 21)
 *   setSetupOpener(fn)          the home window's flow (features/shell/flow) registers how it runs setup over home
 *   openSettings(section?)      the Settings sheet, grown from the pill (settings feature, main/features/settings.ts)
 *   openLibrary(id? | {page})   the Library app window, on a lesson's detail when `id` is given, or on a shell page
 *   openLogin(view?)            the login app window (features/auth; 'intro' plays the branded intro first)
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

export type AppRoute = 'onboarding' | 'library' | 'progress' | 'account' | 'auth'
/** The login window (features/auth): the branded intro first, or straight to "miyagi login". */
export type AuthView = 'intro' | 'login'
/** openLibrary's deep link: a lesson's preview ({id}), or a shell page ({page}, and for Settings a {section}). */
export type LibraryTarget = { id?: string; page?: string; section?: SettingsSection }
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

/** Set by the home window's first-run flow (features/shell/flow initFlow): setup asked for in that window runs there. */
let setupOpener: (() => void) | undefined
export function setSetupOpener(fn: (() => void) | undefined): void {
  setupOpener = fn
}
/**
 * Guided setup, never a second window over home. In the home window: the flow over home (setupOpener). Elsewhere (the
 * Settings sheet from the tray or the pill, another app window): the home window, opened or raised with {setup}, which
 * its flow reads (Shell.tsx). The standalone setup window only when the home window can't be opened.
 */
export async function openOnboarding(): Promise<boolean | undefined> {
  if (setupOpener) {
    setupOpener()
    return true
  }
  // A fresh value on every ask, so the home window can tell a new ask from the args it already acted on.
  if (await openWindow('library', { setup: Date.now() })) return true
  return openWindow('onboarding')
}
/** openLibrary() / openLibrary(id) as before; openLibrary({page, section?}) opens the home window on a shell page. */
export function openLibrary(target?: string | LibraryTarget): Promise<boolean | undefined> {
  if (typeof target === 'string') return openWindow('library', target ? { id: target } : undefined)
  const args: WindowArgs = {}
  if (target?.id) args.id = target.id
  if (target?.page) args.page = target.page
  if (target?.section) args.section = target.section
  return openWindow('library', Object.keys(args).length ? args : undefined)
}
/** The login window (features/auth). Main decides on the first run; this is for a later "Sign in". */
export const openLogin = (view: AuthView = 'login'): Promise<boolean | undefined> => openWindow('auth', { view })
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
