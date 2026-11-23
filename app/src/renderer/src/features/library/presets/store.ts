/**
 * Feature: library / presets. Which packs this learner has added, on this Mac (renderer storage). A placeholder
 * download: `addPack` plays a short progress, then marks the pack added. No network, nothing is fetched.
 */
import { create } from 'zustand'

const KEY = 'miyagi.presets.added'
/** How long the placeholder progress runs. */
export const ADD_MS = 1100

function load(): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}
function save(ids: string[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(ids))
  } catch {
    /* storage can be blocked: the choice then lasts for this session only */
  }
}

type State = {
  /** Added pack ids, oldest first. */
  added: string[]
  /** Packs whose placeholder download is running. */
  adding: string[]
  /** The topic filter ('all' or a Topic id), shared by Lessons and Home's row. */
  topic: string
}

export const usePresets = create<State>(() => ({ added: load(), adding: [], topic: 'all' }))
const set = usePresets.setState
const timers = new Map<string, ReturnType<typeof setTimeout>>()

export function addPack(id: string): void {
  const s = usePresets.getState()
  if (s.added.includes(id) || s.adding.includes(id)) return
  set({ adding: [...s.adding, id] })
  timers.set(
    id,
    setTimeout(() => {
      timers.delete(id)
      const cur = usePresets.getState()
      const added = cur.added.includes(id) ? cur.added : [...cur.added, id]
      save(added)
      set({ added, adding: cur.adding.filter((x) => x !== id) })
    }, ADD_MS)
  )
}

export function removePack(id: string): void {
  const t = timers.get(id)
  if (t) clearTimeout(t)
  timers.delete(id)
  const cur = usePresets.getState()
  const added = cur.added.filter((x) => x !== id)
  save(added)
  set({ added, adding: cur.adding.filter((x) => x !== id) })
}

export const setTopic = (topic: string): void => set({ topic })
