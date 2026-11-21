/**
 * Feature: sound. The setting: Sounds Off (default) or Subtle, plus the "primary press" sub-toggle.
 *
 *   useSound(s => s.mode)       'off' | 'subtle'
 *   setSoundMode('subtle')      for the settings lane's "Sounds" row (Core request: move this into core Prefs)
 *   setSoundTaps(true)          the sub-toggle
 *
 * Where the value comes from, first match wins:
 *   1. the browser stage's ?sound= (1 / subtle, taps, dry, 0 / off). dry = everything on, nothing reaches the speakers.
 *   2. core Prefs `sounds` / `soundTaps`, once Core adds them (read defensively, so this lights up with no change here).
 *   3. localStorage `miyagi.sound`. Every miyagi window shares the origin, so a change in Settings reaches the overlay
 *      through the `storage` event.
 */
import { create } from 'zustand'
import { isElectron } from '../../bridge'
import { setPrefs, usePrefs, type Prefs } from '../../core/prefs'

export type SoundMode = 'off' | 'subtle'
export type SoundSettings = { mode: SoundMode; taps: boolean; dry: boolean; source: 'stage' | 'prefs' | 'local' | 'default' }

const KEY = 'miyagi.sound'
const DEFAULT: SoundSettings = { mode: 'off', taps: false, dry: false, source: 'default' }

function fromStage(): SoundSettings | undefined {
  if (isElectron || typeof location === 'undefined') return undefined
  const v = new URLSearchParams(location.search).get('sound')
  if (v === null) return undefined
  if (v === '0' || v === 'off') return { mode: 'off', taps: false, dry: false, source: 'stage' }
  if (v === 'taps') return { mode: 'subtle', taps: true, dry: false, source: 'stage' }
  if (v === 'dry') return { mode: 'subtle', taps: true, dry: true, source: 'stage' }
  return { mode: 'subtle', taps: false, dry: false, source: 'stage' }
}

function fromPrefs(): SoundSettings | undefined {
  const p = usePrefs.getState() as ReturnType<typeof usePrefs.getState> & { sounds?: unknown; soundTaps?: unknown }
  if (p.sounds !== 'off' && p.sounds !== 'subtle') return undefined
  return { mode: p.sounds, taps: p.soundTaps === true, dry: false, source: 'prefs' }
}

function fromLocal(): SoundSettings | undefined {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? 'null') as { mode?: unknown; taps?: unknown } | null
    if (!raw || (raw.mode !== 'off' && raw.mode !== 'subtle')) return undefined
    return { mode: raw.mode, taps: raw.taps === true, dry: false, source: 'local' }
  } catch {
    return undefined
  }
}

/** Read once; a change made in the stage (the monitor's Sounds control) updates it in place and keeps `dry`. */
let stage = fromStage()
const resolve = (): SoundSettings => stage ?? fromPrefs() ?? fromLocal() ?? DEFAULT

export const useSound = create<SoundSettings>(() => resolve())

const refresh = (): void => {
  const next = resolve()
  const s = useSound.getState()
  if (s.mode !== next.mode || s.taps !== next.taps || s.dry !== next.dry || s.source !== next.source) useSound.setState(next)
}

usePrefs.subscribe(refresh)
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) refresh()
  })
}

function save(patch: Partial<Pick<SoundSettings, 'mode' | 'taps'>>): void {
  const cur = useSound.getState()
  const next = { mode: patch.mode ?? cur.mode, taps: patch.taps ?? cur.taps }
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* private window: this session only */
  }
  if (stage) stage = { ...stage, ...next }
  useSound.setState({ ...next, source: stage ? 'stage' : 'local' })
  // Forward-compatible: once Core adds `sounds` / `soundTaps` to Prefs this persists in main too. Until then
  // sanitizePrefs drops the unknown keys and this is a no-op.
  setPrefs({ sounds: next.mode, soundTaps: next.taps } as unknown as Partial<Prefs>)
}

export const setSoundMode = (mode: SoundMode): void => save({ mode })
export const setSoundTaps = (taps: boolean): void => save({ taps })
