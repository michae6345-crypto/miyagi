/**
 * Feature: skills. The Skills page's state.
 *
 *   raw        the engine's last `progress` payload as sent (the dashboard store keeps only what types.ts reads, and the
 *              skill graph rides on `progress.graph`). The stage's day shift applies as on the dashboard.
 *   view       Path | Map | List, kept on this Mac (localStorage), like the dashboard's own UI prefs.
 *   selected   the skill whose panel is open.
 *   query      the search ("Find a skill").
 *   goal       the capstone the learner picked here. Sent as set_goal when the engine lists it; kept on this Mac either
 *              way and laid over the payload until the engine's own goal agrees (then forgotten).
 *   acked      the newest unlock event already played everywhere on this Mac (ms): skills.ack {until} goes to the
 *              engine when it lists it, and the local mark keeps an event from playing twice when it doesn't.
 *   played     per tree view, the events it already played (ids): each view plays only the events whose skill it shows,
 *              so an event the Path can't show still plays on the Map. The Map shows every skill: once it has played
 *              (or one view played all of them), the events are acked.
 *   picker     the goal picker is open over the page (Change goal).
 */
import { useEffect, useMemo } from 'react'
import { create } from 'zustand'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend } from '../../core/lesson'
import { stageRebase } from '../dashboard/stage'
import { startGoal, startSaved } from '../dashboard/store'
import { buildSkillGraph, type SkillGraph, type SkillGraphNode } from './model'

export type SkillsView = 'path' | 'map' | 'list'
export const VIEWS: ReadonlyArray<{ value: SkillsView; label: string }> = [
  { value: 'path', label: 'Path' },
  { value: 'map', label: 'Map' },
  { value: 'list', label: 'List' }
]

type State = {
  raw?: unknown
  view: SkillsView
  selected?: string
  query: string
  goal?: string
  acked?: number
  played: Record<'path' | 'map', string[]>
  picker: boolean
}

const KEY = { view: 'miyagi.skills.view', goal: 'miyagi.skills.goal', acked: 'miyagi.skills.acked', played: 'miyagi.skills.played' } as const

function read(key: string): string | undefined {
  try {
    return localStorage.getItem(key) ?? undefined
  } catch {
    return undefined
  }
}
function write(key: string, v: string | undefined): void {
  try {
    if (v === undefined) localStorage.removeItem(key)
    else localStorage.setItem(key, v)
  } catch {
    // Private mode or no storage: holds for this window only.
  }
}

const isView = (v: unknown): v is SkillsView => v === 'path' || v === 'map' || v === 'list'
const storedView = read(KEY.view)
const storedAck = Number(read(KEY.acked))
function storedPlayed(): Record<'path' | 'map', string[]> {
  try {
    const v = JSON.parse(read(KEY.played) ?? '{}') as Record<string, unknown>
    const ids = (x: unknown): string[] => (Array.isArray(x) ? x.filter((y): y is string => typeof y === 'string').slice(-200) : [])
    return { path: ids(v.path), map: ids(v.map) }
  } catch {
    return { path: [], map: [] }
  }
}

export const useSkills = create<State>(() => ({
  view: isView(storedView) ? storedView : 'path',
  query: '',
  goal: read(KEY.goal) || undefined,
  acked: Number.isFinite(storedAck) && storedAck > 0 ? storedAck : undefined,
  played: storedPlayed(),
  picker: false
}))
const set = useSkills.setState
const get = useSkills.getState

onMessage('progress', (raw) => set({ raw: stageRebase(raw) }))

/** Paint what main last saw while progress.get is on its way (the dashboard asks for the fresh one). */
export async function primeSkills(): Promise<void> {
  if (get().raw) return
  const last = await bridge.invoke<unknown>('progress:last').catch(() => undefined)
  if (last && !get().raw) set({ raw: stageRebase(last) })
}

export function setView(view: SkillsView): void {
  write(KEY.view, view)
  set({ view })
}
export const setQuery = (query: string): void => set({ query })
export const select = (id?: string): void => set({ selected: id })
export const openPicker = (): void => set({ picker: true, selected: undefined })
export const closePicker = (): void => set({ picker: false })

/** The learner picks a capstone. set_goal when the engine can take it; kept here either way. */
export function chooseGoal(capstoneId: string): void {
  write(KEY.goal, capstoneId)
  set({ goal: capstoneId, picker: false, selected: undefined })
  if (canSend('set_goal')) bridge.send(cmd('set_goal', { capstoneId }))
}

/** The payload with the learner's own pick laid over it (only for the graph shape, which has goals to pick). */
function withGoal(raw: unknown, goal: string | undefined): unknown {
  if (!goal || !raw || typeof raw !== 'object') return raw
  const g = (raw as { graph?: unknown }).graph
  if (!g || typeof g !== 'object' || Array.isArray(g)) return raw
  return { ...(raw as object), graph: { ...(g as object), goal } }
}

/** The view model for the page: the payload, the local goal, minus events this Mac already played. */
export function useSkillGraph(now: number): SkillGraph | undefined {
  const raw = useSkills((s) => s.raw)
  const goal = useSkills((s) => s.goal)
  const acked = useSkills((s) => s.acked)
  // The engine caught up with the local pick: forget it, the engine is the source again.
  const sent = raw && typeof raw === 'object' ? (raw as { graph?: { goal?: unknown } }).graph?.goal : undefined
  useEffect(() => {
    if (goal && sent === goal) {
      write(KEY.goal, undefined)
      set({ goal: undefined })
    }
  }, [goal, sent])
  return useMemo(() => {
    const g = buildSkillGraph(withGoal(raw, goal), now)
    if (!g || acked === undefined) return g
    return { ...g, events: g.events.filter((e) => e.at > acked) }
  }, [raw, goal, acked, now])
}

/**
 * `view` played `events` (the ones whose skills it shows): remember them for that view. When every unseen event has now
 * played in some view, mark them all played here and tell the engine (skills.ack) when it listens.
 */
export function ackEvents(g: SkillGraph, view: 'path' | 'map', events: SkillGraph['events']): void {
  if (!events.length) return
  const cur = get().played
  const played = { ...cur, [view]: [...cur[view], ...events.map((e) => e.id).filter((id) => !cur[view].includes(id))].slice(-200) }
  write(KEY.played, JSON.stringify(played))
  set({ played })
  const seen = new Set([...played.path, ...played.map])
  if (!g.events.every((e) => seen.has(e.id))) return
  const newest = Math.max(...g.events.map((e) => e.at))
  write(KEY.acked, String(newest))
  set({ acked: newest })
  if (g.ack !== undefined && canSend('skills.ack')) bridge.send(cmd('skills.ack', { until: g.ack }))
}

/** Start a skill: its saved lesson (library.start, zero model calls), else a lesson built for it (learn). */
export function startSkill(n: SkillGraphNode, g: SkillGraph): void {
  const pick = g.next?.skillId === n.id ? g.next : undefined
  const lib = pick?.libraryId ?? n.lessons.find((l) => l.inProgress && l.libraryId)?.libraryId ?? n.lessons.find((l) => l.libraryId && l.role !== 'uses')?.libraryId
  if (lib) {
    void startSaved(lib, 'library')
    return
  }
  startGoal(pick?.goal ?? `Teach me ${n.label}`, 'library')
}

/** Start a project: a lesson built from its brief. */
export function startProject(id: string, g: SkillGraph): void {
  const c = g.capstones.find((x) => x.id === id)
  startGoal(c?.brief ?? g.byId[id]?.label ?? '', 'library')
}
