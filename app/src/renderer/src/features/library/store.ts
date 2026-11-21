/**
 * Feature: library. The Library window's state: the cached lessons, the open preview, the filter, and a start in
 * flight. Data only through main (library:list / library:get / library:start, main/features/library.ts); every
 * answer is cleaned again here (sanitize.ts). Never sends `learn`.
 */
import { create } from 'zustand'
import type { LessonTool, LibraryItem } from '../../../../../../shared/contracts/events'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { closeWindow } from '../../core/surfaces'
import { cleanDetail, cleanList, isLibraryId, type LibraryDetail } from './sanitize'

export type Caps = { list: boolean; get: boolean; start: boolean }
export type ToolFilter = LessonTool | 'all'
export type Section = 'library' | 'continue'

type State = {
  items: LibraryItem[]
  /** The first answer came back (empty or not). */
  loaded: boolean
  caps: Caps
  /** Previews by id: undefined = not asked yet, null = the engine had none (the list row is used). */
  details: Record<string, LibraryDetail | null>
  /** The preview on screen (Home-LessonDetail), or undefined for the list (Home-Library). */
  openId?: string
  section: Section
  tool: ToolFilter
  query: string
  /** A lesson whose library.start is in flight. */
  starting?: string
  /** Why the last start didn't happen (fixed copy, never the engine's text). */
  startError?: { id: string; text: string }
}

export const useLibrary = create<State>(() => ({
  items: [],
  loaded: false,
  caps: { list: false, get: false, start: false },
  details: {},
  section: 'library',
  tool: 'all',
  query: ''
}))
const set = useLibrary.setState
const get = useLibrary.getState

/** How long a start waits for lesson.ready before it says so. A cached lesson starts in a second or two. */
const START_MS = 15_000
const STARTED_LINGER_MS = 300

let listSeq = 0
export async function refresh(): Promise<void> {
  const seq = ++listSeq
  const [items, caps] = await Promise.all([
    bridge.invoke<unknown>('library:list').then(cleanList, () => []),
    bridge.invoke<Partial<Caps> | null>('library:caps').then(
      (c) => ({ list: c?.list === true, get: c?.get === true, start: c?.start === true }),
      () => ({ list: false, get: false, start: false })
    )
  ])
  if (seq !== listSeq) return
  set({ items, caps, loaded: true })
}

export async function loadDetail(id: string): Promise<void> {
  if (!isLibraryId(id) || get().details[id] !== undefined) return
  const d = await bridge.invoke<unknown>('library:get', id).then(
    (v) => (v ? (cleanDetail(v, id) ?? null) : null),
    () => null
  )
  set((s) => ({ details: { ...s.details, [id]: d } }))
}

export function openDetail(id: string): void {
  if (!isLibraryId(id)) return
  set({ openId: id, startError: undefined })
  void loadDetail(id)
}
export const closeDetail = (): void => set({ openId: undefined, startError: undefined })
export const setSection = (section: Section): void => set({ section, openId: undefined })
export const setTool = (tool: ToolFilter): void => set({ tool })
export const setQuery = (query: string): void => set({ query: query.slice(0, 120) })

/** The item for an id: the preview's when it came back, else the list row. */
export function itemFor(s: State, id: string): LibraryItem | undefined {
  return s.details[id]?.item ?? s.items.find((i) => i.id === id)
}

/**
 * Start a cached lesson: library.start {id} (zero model calls engine side). Waits for lesson.ready, then closes the
 * window so the lesson panel has the screen. Never falls back to `learn` (that would build with model calls).
 */
export async function start(id: string): Promise<void> {
  const s = get()
  if (s.starting || !isLibraryId(id)) return
  set({ starting: id, startError: undefined })
  const sent = await bridge.invoke<boolean>('library:start', id).catch(() => false)
  if (!sent) {
    set({ starting: undefined, startError: { id, text: 'This engine can’t start saved lessons yet.' } })
    return
  }
  const outcome = await new Promise<'ready' | 'error' | 'timeout'>((resolve) => {
    const offs: Array<() => void> = []
    const done = (r: 'ready' | 'error' | 'timeout'): void => {
      clearTimeout(timer)
      offs.forEach((f) => f())
      resolve(r)
    }
    const timer = setTimeout(() => done('timeout'), START_MS)
    offs.push(onMessage('lesson.ready', () => done('ready')))
    offs.push(onMessage('error', () => done('error')))
  })
  if (outcome === 'ready') {
    setTimeout(() => {
      set({ starting: undefined })
      void closeWindow('library')
    }, STARTED_LINGER_MS)
    return
  }
  set({
    starting: undefined,
    startError: { id, text: outcome === 'error' ? 'That lesson didn’t start. Try again.' : 'No answer from the engine yet. Try again.' }
  })
}

/** The lessons the list shows: section, tool and search applied. */
export function visible(s: Pick<State, 'items' | 'tool' | 'query' | 'section'>): { continuing: LibraryItem[]; ready: LibraryItem[] } {
  const q = s.query.trim().toLowerCase()
  const match = (i: LibraryItem): boolean =>
    (s.tool === 'all' || i.tools.includes(s.tool)) && (!q || i.title.toLowerCase().includes(q) || (i.by ?? '').toLowerCase().includes(q))
  const shown = s.items.filter(match)
  return { continuing: shown.filter((i) => i.progress), ready: s.section === 'continue' ? [] : shown }
}
