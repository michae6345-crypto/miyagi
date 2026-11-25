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
import { useDash } from '../dashboard/store'
import { cleanDetail, cleanList, isLibraryId, type LibraryDetail } from './sanitize'

export type Caps = { list: boolean; get: boolean; start: boolean }
export type ToolFilter = LessonTool | 'all'
/** home = the lesson dashboard (features/dashboard), the window's first view. */
export type Section = 'home' | 'library' | 'continue'

type State = {
  items: LibraryItem[]
  /** The first answer came back (empty or not). */
  loaded: boolean
  caps: Caps
  /** library:caps came back at least once. Until then nothing says the engine can't start a lesson. */
  capsKnown: boolean
  /**
   * Previews by id: undefined = not asked yet (or the last ask got no answer), null = the engine answered and had
   * none (the list row is used). A null is asked again on the next refresh.
   */
  details: Record<string, LibraryDetail | null>
  /** Ids whose last library:get got no answer (engine not reachable yet). Asked again on the next refresh. */
  detailFailed: Record<string, boolean>
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
  capsKnown: false,
  details: {},
  detailFailed: {},
  section: 'home',
  tool: 'all',
  query: ''
}))
const set = useLibrary.setState
const get = useLibrary.getState

/** How long a start waits for lesson.ready before it says so. A cached lesson starts in a second or two. */
const START_MS = 15_000
const STARTED_LINGER_MS = 300

const NO_CAPS: Caps = { list: false, get: false, start: false }

let capsSeq = 0
/** Caps on their own: a slow library:list (WS ask, then HTTP) must not hold Start lesson back. */
async function refreshCaps(): Promise<void> {
  const seq = ++capsSeq
  const caps = await bridge.invoke<Partial<Caps> | null>('library:caps').then(
    (c) => ({ list: c?.list === true, get: c?.get === true, start: c?.start === true }),
    () => NO_CAPS
  )
  if (seq !== capsSeq) return
  set({ caps, capsKnown: true })
}

let listSeq = 0
export async function refresh(): Promise<void> {
  void refreshCaps()
  // A preview that got no answer, or whose engine had none, is asked again: the engine may have come back since.
  // Other null entries are dropped so they're asked again when opened; the open one stays on screen until its answer.
  const { openId, details, detailFailed } = get()
  const kept = Object.fromEntries(Object.entries(details).filter(([k, v]) => v !== null || k === openId))
  if (Object.keys(kept).length !== Object.keys(details).length) set({ details: kept })
  if (openId && (details[openId] === null || detailFailed[openId])) void loadDetail(openId, true)
  const seq = ++listSeq
  // An answer that never comes (an engine that drops library.list) must not keep the page on skeleton rows: after
  // LIST_WAIT_MS the page shows what it has (the empty or first-run layout); a late answer still lands.
  const timer = setTimeout(() => {
    if (seq === listSeq && !get().loaded) set({ loaded: true })
  }, LIST_WAIT_MS)
  const items = await bridge.invoke<unknown>('library:list').then(cleanList, () => [])
  clearTimeout(timer)
  if (seq !== listSeq) return
  set({ items, loaded: true })
}
/** How long the Library waits for library:list before it stops showing skeleton rows. */
const LIST_WAIT_MS = 4000

const asking = new Set<string>()
/** `again`: ask even when an answer is cached (a refresh after no answer, or after an empty one). */
export async function loadDetail(id: string, again = false): Promise<void> {
  if (!isLibraryId(id) || asking.has(id)) return
  if (!again && get().details[id] !== undefined) return
  asking.add(id)
  // Main rejects when nothing answered (engine not connected, the WS ask timed out, HTTP down). That is never cached.
  const d = await bridge.invoke<unknown>('library:get', id).then(
    (v): LibraryDetail | null => (v ? (cleanDetail(v, id) ?? null) : null),
    (): 'failed' => 'failed'
  )
  asking.delete(id)
  if (d === 'failed') {
    set((s) => ({ detailFailed: { ...s.detailFailed, [id]: true } }))
    return
  }
  set((s) => {
    const failed = { ...s.detailFailed }
    delete failed[id]
    return { details: { ...s.details, [id]: d }, detailFailed: failed }
  })
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
  // One start at a time across the window: Home's dashboard parts (Up next, skills) keep their own flag in useDash.
  if (s.starting || useDash.getState().starting || !isLibraryId(id)) return
  set({ starting: id, startError: undefined })
  // Mirror it there too, so those Start buttons wait (and show busy on the same lesson) without touching dashboard.
  useDash.setState({ starting: id })
  const release = (): void => {
    if (useDash.getState().starting === id) useDash.setState({ starting: undefined })
  }
  const sent = await bridge.invoke<boolean>('library:start', id).catch(() => false)
  if (!sent) {
    release()
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
      release()
      set({ starting: undefined })
      void closeWindow('library')
    }, STARTED_LINGER_MS)
    return
  }
  release()
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
