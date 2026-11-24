/**
 * Feature: settings, v4 page (Nov 24). What the Your data panel reads from main, which no contract or handler carries yet.
 *
 * `useYourData()`: the cache size and the lesson folder. Main has no handler yet (Core request in
 * agents/v4-settings.md: `data:summary`, `data:cache-clear`, `data:open-folder`); until then the stage shows the mock's
 * numbers and Electron shows no size. The pure half (the Apps list, sizes, the delete ask) is facts.ts.
 */
import { useEffect, useState } from 'react'
import { bridge, isElectron } from '../../../bridge'

export * from './facts'

export type YourData = { cacheBytes?: number; folder: string; lessons?: number }

const STAGE_DATA: YourData = { cacheBytes: 212 * 1024 * 1024, folder: '~/miyagi', lessons: 14 }

export function useYourData(live: boolean): YourData {
  const [d, set] = useState<YourData>(!isElectron ? STAGE_DATA : { folder: '~/miyagi' })
  useEffect(() => {
    if (!live || !isElectron) return
    let on = true
    bridge
      .invoke<YourData>('data:summary')
      .then((r) => on && r && set({ folder: r.folder || '~/miyagi', cacheBytes: r.cacheBytes, lessons: r.lessons }))
      .catch(() => undefined)
    return () => {
      on = false
    }
  }, [live])
  return d
}

/** Run a main handler that may not exist yet; the row says so instead of looking dead. */
export async function tryInvoke(channel: string, done: string): Promise<string> {
  try {
    await bridge.invoke(channel)
    return done
  } catch {
    return 'Not ready yet.'
  }
}
