/**
 * Feature: settings, v4 page (Nov 24). What the Your data panel reads, through the ui-v4 contract
 * (shared/contracts/UI-V4.md §5): `data.get {}` and `data.delete {what}` are both answered with `data`
 * (DataInventory). The pure half (the Apps list, sizes, the inventory mapping, the delete ask) is facts.ts.
 *
 * `useYourData(live)`: asks once the page shows, when the engine lists data.get in engine.hello. Until an answer comes
 * (an older engine, or none) the stage shows the mock's numbers and Electron shows the folder with no size.
 * `clearCache()`: data.delete lesson_cache; offered only when the inventory's canDelete lists it.
 */
import { useEffect } from 'react'
import type { DataDeleteKind } from '../../../../../../../shared/contracts/events'
import { create } from 'zustand'
import { cmd } from '../../../../../common/wire'
import { bridge, isElectron } from '../../../bridge'
import { onMessage } from '../../../core/bus'
import { canSend, useCapability } from '../../../core/lesson'
import { fromInventory, type YourData } from './facts'

export * from './facts'

const STAGE_DATA: YourData = { cacheBytes: 212 * 1024 * 1024, folder: '~/miyagi', lessons: 14 }

const useData = create<{ data: YourData; deleted?: string[]; at: number }>(() => ({ data: !isElectron ? STAGE_DATA : { folder: '~/miyagi' }, at: 0 }))

onMessage('data', (inv) => useData.setState({ data: fromInventory(inv), deleted: inv.deleted, at: Date.now() }))

export function useYourData(live: boolean): YourData {
  const can = useCapability('data.get')
  useEffect(() => {
    if (live && can) bridge.send(cmd('data.get', {}))
  }, [live, can])
  return useData((s) => s.data)
}

/** data.delete lesson_cache; resolves with what the row says once the engine answered (or did not, within 8 s). */
export const clearCache = (): Promise<string> => clearKind('lesson_cache')

/** data.delete progress: lesson history, skills and plans start over (Your data's Clear lesson history). */
export const clearHistory = (): Promise<string> => clearKind('progress')

function clearKind(kind: DataDeleteKind): Promise<string> {
  if (!canSend('data.delete')) return Promise.resolve('Not ready yet.')
  const since = Date.now()
  bridge.send(cmd('data.delete', { what: [kind] }))
  return new Promise((done) => {
    const stop = useData.subscribe((s) => {
      if (s.at < since) return
      stop()
      clearTimeout(t)
      done(s.deleted?.includes(kind) ? 'Cleared.' : 'Not cleared.')
    })
    const t = setTimeout(() => {
      stop()
      done('No answer.')
    }, 8000)
  })
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
