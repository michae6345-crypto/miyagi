/**
 * Feature: library. Home's logic (pure where it can be): what the hero offers, the recent activity list, and the ask
 * field's two ways to start, sent exactly as the launcher sends them (features/launcher is never edited; its
 * exported helpers are imported):
 *
 *   a goal, "Just teach me"   learn {query, mode: "lesson"}         (launcher teach())
 *   a goal, "Watch a video"   learn {query}, then the launcher opens on the streaming rows (launcher learn())
 *   a YouTube link            already a lesson here: library.start {id} (zero model calls, launcher build())
 *                             otherwise learn_url {url}             (launcher build())
 * The island then shows the build, so this window steps aside (closeWindow), like the dashboard's Start.
 */
import { create } from 'zustand'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { noteLearnMode } from '../../core/lesson'
import { closeWindow } from '../../core/surfaces'
import type { DashData } from '../dashboard/types'
import { startSearch } from '../launcher/store'
import { libraryMatch } from '../launcher/library'
import { parseYouTube, type YouTubeLink } from '../launcher/youtube'
import { start, useLibrary } from './store'

// ---- the hero ---------------------------------------------------------------------------------------------------

export type Hero =
  /** First answers still on their way. */
  | { kind: 'loading' }
  /** A lesson is open in miyagi right now: Continue goes back to it. */
  | { kind: 'live'; title: string; line: string; fraction: number }
  /** miyagi is building a lesson: no primary, the island has it. */
  | { kind: 'building'; title?: string; line: string; fraction?: number }
  /** A saved lesson left mid-way: Continue = library.start (zero model calls). */
  | { kind: 'resume'; id: string; title: string; line: string; fraction: number; when?: number; tools: LibraryItem['tools']; canStart: boolean }
  /** Nothing in progress, a lesson is ready on this Mac: Start it. */
  | { kind: 'fresh'; id: string; title: string; line: string; tools: LibraryItem['tools']; canStart: boolean }
  /** Nothing saved at all: the ask field is the way in. */
  | { kind: 'empty' }

export type HeroInput = {
  loaded: boolean
  dashLoading: boolean
  items: LibraryItem[]
  data?: DashData
  canStart: boolean
  live?: { title: string; stepTitle?: string; index: number; total: number; fraction: number }
  building?: { title?: string; message?: string; progress?: number }
}

const stepLine = (index: number, total: number, title?: string): string => `Step ${Math.min(index + 1, total)} of ${total}${title ? `. ${title}` : ''}`

export function pickHero(i: HeroInput): Hero {
  if (i.building) return { kind: 'building', title: i.building.title, line: i.building.message || 'Building your lesson', fraction: i.building.progress }
  if (i.live) return { kind: 'live', title: i.live.title, line: stepLine(i.live.index, i.live.total, i.live.stepTitle), fraction: i.live.fraction }
  if (!i.loaded && i.dashLoading) return { kind: 'loading' }
  // Newest saved lesson in progress: the engine's progress (it knows when) first, then the library's own rows.
  const active = [...(i.data?.inProgress ?? [])].filter((a) => a.libraryId).sort((a, b) => (b.lastActiveAt ?? 0) - (a.lastActiveAt ?? 0))
  for (const a of active) {
    const item = i.items.find((x) => x.id === a.libraryId)
    const total = a.stepCount ?? item?.progress?.total ?? item?.steps ?? 0
    const index = a.stepIndex ?? item?.progress?.stepIndex ?? 0
    if (!total) continue
    return {
      kind: 'resume',
      id: a.libraryId!,
      title: a.title || item?.title || 'Your lesson',
      line: stepLine(index, total, a.stepTitle ?? item?.progress?.stepTitle),
      fraction: Math.min(1, (a.passed ?? index) / total),
      when: a.lastActiveAt,
      tools: item?.tools ?? [],
      canStart: i.canStart && (item ? item.ready : true)
    }
  }
  const mid = i.items.find((x) => x.ready && x.progress && x.progress.stepIndex < x.progress.total)
  if (mid?.progress)
    return { kind: 'resume', id: mid.id, title: mid.title, line: stepLine(mid.progress.stepIndex, mid.progress.total, mid.progress.stepTitle), fraction: mid.progress.stepIndex / mid.progress.total, tools: mid.tools, canStart: i.canStart }
  if (!i.loaded) return { kind: 'loading' }
  const ready = i.items.find((x) => x.ready && !x.progress)
  if (ready)
    return { kind: 'fresh', id: ready.id, title: ready.title, line: [`${ready.steps} ${ready.steps === 1 ? 'step' : 'steps'}`, ready.estMinutes ? `about ${ready.estMinutes} min` : ''].filter(Boolean).join(', '), tools: ready.tools, canStart: i.canStart }
  return { kind: 'empty' }
}

// ---- recent activity --------------------------------------------------------------------------------------------

export type Recent = { key: string; title: string; done: boolean; passed: number; total: number; skipped: number; at?: number; libraryId?: string }

/** The last lessons, newest first: finished ones and ones in progress, with the steps passed and when. */
export function recentActivity(data: DashData | undefined, max = 5): Recent[] {
  if (!data) return []
  const rows: Recent[] = [
    ...data.inProgress.map((a) => ({
      key: `p:${a.lessonId}`,
      title: a.title,
      done: false,
      passed: a.passed ?? a.stepIndex ?? 0,
      total: a.stepCount ?? 0,
      skipped: a.skipped ?? 0,
      at: a.lastActiveAt,
      libraryId: a.libraryId
    })),
    ...data.completed.map((c) => ({
      key: `c:${c.lessonId}`,
      title: c.title,
      done: true,
      passed: c.result?.passed ?? 0,
      total: c.result?.total ?? 0,
      skipped: c.result?.skipped ?? 0,
      at: c.finishedAt,
      libraryId: c.libraryId
    }))
  ]
  return rows.sort((a, b) => (b.at ?? 0) - (a.at ?? 0)).slice(0, max)
}

/** "4 of 6 steps passed", "6 of 6 steps passed, 1 skipped". Never invents a number. */
export function stepsPassed(r: Recent): string {
  if (!r.total) return r.done ? 'Finished' : 'In progress'
  return `${r.passed} of ${r.total} ${r.total === 1 ? 'step' : 'steps'} passed${r.skipped ? `, ${r.skipped} skipped` : ''}`
}

// ---- the ask field ----------------------------------------------------------------------------------------------

export type How = 'lesson' | 'video'
export type AskState = { text: string; how: How; sending?: 'lesson' | 'video' | 'link' | 'saved'; note?: string }

export const useAsk = create<AskState>(() => ({ text: '', how: 'lesson' }))
const set = useAsk.setState
const get = useAsk.getState

export const setAskText = (text: string): void => set({ text: text.slice(0, 500), note: undefined })
export const setHow = (how: How): void => set({ how })
export const flipHow = (): void => set((s) => ({ how: s.how === 'lesson' ? 'video' : 'lesson' }))

export type AskRead =
  | { kind: 'idle' }
  | { kind: 'goal'; goal: string }
  | { kind: 'link'; link: YouTubeLink; match?: LibraryItem }

/** What's typed: nothing, a goal, or a YouTube link (and the saved lesson already made from that video, if any). */
export function readAsk(text: string, items: LibraryItem[], canStart: boolean): AskRead {
  const t = text.trim()
  if (!t) return { kind: 'idle' }
  const link = parseYouTube(t)
  if (link) return { kind: 'link', link, match: canStart ? libraryMatch(items, link) : undefined }
  return { kind: 'goal', goal: t }
}

/** How long the field shows "Sending" before the window steps aside for the island's build. */
const STEP_ASIDE_MS = 450

function stepAside(): void {
  setTimeout(() => {
    set({ text: '', sending: undefined })
    void closeWindow('library')
  }, STEP_ASIDE_MS)
}

/** Start what's typed, the way the launcher would. false when nothing went out (offline, empty, already sending). */
export function submitAsk(connected: boolean): boolean {
  const s = get()
  if (s.sending) return false
  const { items, caps } = useLibrary.getState()
  const read = readAsk(s.text, items, caps.start)
  if (read.kind === 'idle') return false
  if (!connected) {
    set({ note: 'miyagi is offline. Your text stays here.' })
    return false
  }
  if (read.kind === 'link') {
    if (read.match) {
      // Never build the same video twice: the saved lesson starts at once (library store waits for lesson.ready).
      set({ sending: 'saved' })
      void start(read.match.id).then(() => set({ sending: undefined, text: useLibrary.getState().startError ? get().text : '' }))
      return true
    }
    noteLearnMode(undefined)
    bridge.send(cmd('learn_url', { url: read.link.url }))
    set({ sending: 'link' })
    stepAside()
    return true
  }
  if (s.how === 'lesson') {
    noteLearnMode('lesson')
    bridge.send(cmd('learn', { query: read.goal, mode: 'lesson' }))
    set({ sending: 'lesson' })
    stepAside()
    return true
  }
  // Watch a video: the search runs here, its rows stream into the launcher, which opens to let the learner pick.
  noteLearnMode(undefined)
  startSearch(read.goal)
  bridge.send(cmd('learn', { query: read.goal }))
  bridge.emit('launcher:toggle')
  set({ sending: 'video' })
  setTimeout(() => set({ sending: undefined, text: '' }), STEP_ASIDE_MS)
  return true
}
