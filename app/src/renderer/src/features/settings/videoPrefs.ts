/**
 * Feature: settings. The learner's video defaults (Lessons: playback speed and volume). The player (features/player
 * store.ts) already saves both under PREF_KEY and reads them when it starts, so this writes the same record: the next
 * lesson's video starts there. Nothing lesson-specific is stored.
 */
import { useEffect, useState } from 'react'
import { PREF_KEY, RATES } from '../player/store'

export const VOLUMES = [0, 25, 50, 75, 100] as const
export const RATE_OPTIONS: readonly number[] = [...RATES].sort((a, b) => a - b)

export type VideoPrefs = { volume: number; rate: number }

export function readVideo(): VideoPrefs {
  try {
    const v = JSON.parse(localStorage.getItem(PREF_KEY) ?? '{}') as { volume?: unknown; rate?: unknown }
    const volume = typeof v.volume === 'number' && v.volume >= 0 && v.volume <= 100 ? Math.round(v.volume) : 100
    const rate = typeof v.rate === 'number' && (RATES as readonly number[]).includes(v.rate) ? v.rate : 1
    return { volume, rate }
  } catch {
    return { volume: 100, rate: 1 }
  }
}

export function writeVideo(patch: Partial<VideoPrefs>): void {
  try {
    localStorage.setItem(PREF_KEY, JSON.stringify({ ...readVideo(), ...patch }))
  } catch {
    /* private window: not saved */
  }
}

/** One of the two values as state; follows a change made in another window. */
export function useVideoPref(key: keyof VideoPrefs): [number, (v: number) => void] {
  const [v, setV] = useState(() => readVideo()[key])
  useEffect(() => {
    const on = (e: StorageEvent): void => {
      if (e.key === PREF_KEY) setV(readVideo()[key])
    }
    window.addEventListener('storage', on)
    return () => window.removeEventListener('storage', on)
  }, [key])
  return [
    v,
    (n) => {
      writeVideo({ [key]: n })
      setV(n)
    }
  ]
}
