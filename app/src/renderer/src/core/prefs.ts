/**
 * Core: general preferences in the renderer (Settings → General writes them; any feature reads them).
 *
 *   usePrefs(s => s.appearance)      'system' | 'light' | 'dark'
 *   setPrefs({ appearance: 'light' }) saves (main: userData/prefs.json) and reaches every window
 *   useAppearance()                   the resolved 'light' | 'dark'
 *
 * Appearance is applied as <html data-appearance="light|dark">; every themed token (core/theme.ts) switches on it, so
 * every window follows System, Light and Dark. The notch island, its cards and the overlay's passive layers stay black
 * (data-theme="dark", Overlay.tsx), like the real notch.
 */
import { create } from 'zustand'
import { DEFAULT_PREFS, sanitizePrefs, type Prefs } from '../../../common/prefs'
import { bridge, isElectron, registerWebHandler } from '../bridge'
import { themeCss } from './theme'

export type { Appearance, Prefs } from '../../../common/prefs'

export const usePrefs = create<Prefs>(() => ({ ...DEFAULT_PREFS }))

/** Change preferences. Optimistic here; main saves them and sends the merged result to every window. */
export function setPrefs(patch: Partial<Prefs>): void {
  usePrefs.setState(sanitizePrefs(patch))
  bridge.invoke<Prefs>('prefs:set', patch).then((p) => p && usePrefs.setState(p)).catch(() => undefined)
}

/**
 * Change preferences and wait for main's answer (not optimistic): the prefs as saved, or undefined when main is not
 * there. Settings > Shortcuts uses it, since main may keep the old key (another app owns the new one).
 */
export function savePrefs(patch: Partial<Prefs>): Promise<Prefs | undefined> {
  return bridge
    .invoke<Prefs>('prefs:set', patch)
    .then((p) => {
      if (p) usePrefs.setState(p)
      return p ?? undefined
    })
    .catch(() => undefined)
}

// Browser stage: no main process. Preferences aren't secret, so the stage keeps them in localStorage.
if (!isElectron) {
  const KEY = 'miyagi.prefs'
  // Stage only: ?appearance=light|dark forces the theme for this page (stage shots, no localStorage needed).
  const forced = sanitizePrefs({ appearance: new URLSearchParams(location.search).get('appearance') })
  const read = (): Prefs => {
    try {
      return { ...DEFAULT_PREFS, ...sanitizePrefs(JSON.parse(localStorage.getItem(KEY) ?? '{}')), ...forced }
    } catch {
      return { ...DEFAULT_PREFS, ...forced }
    }
  }
  registerWebHandler('prefs:get', () => read())
  registerWebHandler('prefs:set', (patch) => {
    const next = { ...read(), ...sanitizePrefs(patch) }
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      /* private window: this session only */
    }
    return next
  })
}

bridge.invoke<Prefs>('prefs:get').then((p) => p && usePrefs.setState(p)).catch(() => undefined)
bridge.onFeature('prefs', (p) => usePrefs.setState(sanitizePrefs(p)))

// ---- theme variables -----------------------------------------------------------------------------
// Every themed token (core/theme.ts `palette`) is a CSS variable. Written here, before any component renders, so the
// first paint already has them; <html data-appearance> (below) picks dark or light.
if (typeof document !== 'undefined' && !document.getElementById('mg-theme')) {
  const el = document.createElement('style')
  el.id = 'mg-theme'
  el.textContent = themeCss()
  document.head.prepend(el)
}

// ---- appearance ----------------------------------------------------------------------------------

const light = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: light)') : undefined
const resolve = (): 'light' | 'dark' => {
  const a = usePrefs.getState().appearance
  return a === 'light' || (a === 'system' && !!light?.matches) ? 'light' : 'dark'
}
export const useResolved = create<{ appearance: 'light' | 'dark' }>(() => ({ appearance: resolve() }))
const apply = (): void => {
  const a = resolve()
  if (typeof document !== 'undefined') document.documentElement.dataset.appearance = a
  if (useResolved.getState().appearance !== a) useResolved.setState({ appearance: a })
}
usePrefs.subscribe(apply)
light?.addEventListener('change', apply)
apply()

// macOS full screen (app windows only): main sends feat:fullscreen. <html data-fullscreen> lets a layout drop the strip it
// keeps under the traffic lights, which hide in full screen. The drag region keeps working either way.
bridge.onFeature('fullscreen', (on) => {
  if (typeof document === 'undefined') return
  if (on) document.documentElement.dataset.fullscreen = ''
  else delete document.documentElement.dataset.fullscreen
})

/** The appearance in effect right now ('system' resolved through the OS). */
export function useAppearance(): 'light' | 'dark' {
  return useResolved((s) => s.appearance)
}
