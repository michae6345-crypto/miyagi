/**
 * Feature: ambient. The two settings: "Offer help with errors" (default on) and the apps never watched.
 *
 * Stored in localStorage under KEY. Every miyagi window shares that storage (one origin), and the `storage` event tells
 * the other windows, so Settings (its own window) and the overlay agree without a core change. Core request in
 * agents/app-ambient.md: move these into common/prefs.ts (Prefs.ambient) so main keeps them in prefs.json.
 *
 * ambient.set goes to the engine from the overlay window only (the stage in a browser), on every engine.hello and on
 * every change, and only when the engine's hello lists it (contract gate). The engine starts with spotting off.
 */
import { create } from 'zustand'
import { cmd } from '../../../../common/wire'
import { bridge, isElectron } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend } from '../../core/lesson'
import { cleanMuted, cleanPrefs, DEFAULT_AMBIENT, isMuted, type AmbientPrefs } from './model'

export const KEY = 'miyagi.ambient'

/** This window talks to the engine for ambient.set: the overlay (Electron) or the stage (browser). */
export const ownsEngine = (): boolean => {
  if (typeof location === 'undefined') return true
  const route = location.hash.replace(/^#\/?/, '') || (isElectron ? 'overlay' : 'stage')
  return route === 'overlay' || route === 'stage'
}

function read(): AmbientPrefs {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(KEY) : null
    return raw ? cleanPrefs(JSON.parse(raw)) : { ...DEFAULT_AMBIENT }
  } catch {
    return { ...DEFAULT_AMBIENT }
  }
}

export const useAmbientPrefs = create<AmbientPrefs>(() => read())

/** Tell the engine (overlay window only; gated on the hello). `caps`: the hello's own list, before core has stored it. */
export function syncEngine(caps?: readonly string[]): void {
  if (!ownsEngine()) return
  if (!(caps ? caps.includes('ambient.set') : canSend('ambient.set'))) return
  const p = useAmbientPrefs.getState()
  bridge.send(cmd('ambient.set', { errors: p.errors, mutedApps: p.mutedApps }))
}

export function setAmbientPrefs(patch: Partial<AmbientPrefs>): void {
  const next = cleanPrefs({ ...useAmbientPrefs.getState(), ...patch })
  useAmbientPrefs.setState(next)
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // private window: this session only
  }
  syncEngine()
}

export const setOfferErrors = (on: boolean): void => setAmbientPrefs({ errors: on })

/** Never watch this app (the card's "Not in Terminal", Settings' list). */
export function muteApp(app: string): void {
  const name = app.trim()
  if (!name) return
  const cur = useAmbientPrefs.getState().mutedApps
  if (isMuted(name, cur)) return
  setAmbientPrefs({ mutedApps: cleanMuted([...cur, name]) })
}

export function unmuteApp(app: string): void {
  const cur = useAmbientPrefs.getState().mutedApps
  setAmbientPrefs({ mutedApps: cur.filter((m) => m.trim().toLowerCase() !== app.trim().toLowerCase()) })
}

// Another window changed them (Settings): take the new values, and the overlay tells the engine.
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('storage', (e: StorageEvent) => {
    if (e.key !== KEY) return
    useAmbientPrefs.setState(read())
    syncEngine()
  })
}

// Every connect: the engine forgets per connection, and starts with spotting off.
onMessage('engine.hello', (p) => syncEngine(p?.capabilities ?? []))
