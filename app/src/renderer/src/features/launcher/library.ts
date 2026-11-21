/**
 * Feature: launcher. The cached lessons the launcher offers when nothing is typed (Home-Launcher "Continue",
 * Home-LauncherInContext "Ready to run"): the engine's `library` answer to `library.list`, kept here (the library
 * window, A6, keeps its own copy; no feature imports another's opener or store for writing).
 *
 * Asked for each time the launcher opens, only when engine.hello lists library.list (an older engine never gets the
 * command; the sections then simply don't show). Starting one is `library.start {id}`: zero model calls, the engine
 * answers lesson.ready. Nothing here is ever a path: ids come from the engine and go straight back to it.
 */
import { create } from 'zustand'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend } from '../../core/lesson'
import type { YouTubeLink } from './youtube'
import { parseYouTube } from './youtube'

export type { LibraryItem }

/** Rows per section: the launcher stays a short list (the library window has the rest). */
export const MAX_CONTINUE = 2
export const MAX_READY = 3

export const useLibrary = create<{ items: LibraryItem[] }>(() => ({ items: [] }))

onMessage('library', (p) => {
  const items = Array.isArray(p.items) ? p.items.filter((i) => i && typeof i.id === 'string' && typeof i.title === 'string') : []
  useLibrary.setState({ items })
})

/** Ask the engine for its cached lessons (when it speaks library.list). */
export function refreshLibrary(): void {
  if (canSend('library.list')) bridge.send(cmd('library.list', {}))
}

/** Start a cached lesson. false when this engine can't (no library.start capability). */
export function startLibraryLesson(id: string): boolean {
  if (!canSend('library.start')) return false
  bridge.send(cmd('library.start', { id }))
  return true
}

/** Same topic, by title words (so the lesson in progress is never offered again under Ready to run). */
const norm = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

/**
 * The two launcher sections from the cached lessons:
 *   continue : started on this Mac and not finished (progress set), most recent first as the engine sent them
 *   ready    : built and ready, not started
 * The lesson in progress (by title) is in neither: it has its own Continue row.
 */
export function librarySections(items: LibraryItem[], current?: string): { cont: LibraryItem[]; ready: LibraryItem[] } {
  const skip = current ? norm(current) : ''
  const usable = items.filter((i) => i.ready && (!skip || norm(i.title) !== skip))
  const cont = usable.filter((i) => i.progress && i.progress.stepIndex < i.progress.total).slice(0, MAX_CONTINUE)
  const ready = usable.filter((i) => !i.progress).slice(0, MAX_READY)
  return { cont, ready }
}

/** A cached lesson built from this exact video, for a pasted link ("Already a lesson", "Ready instantly"). */
export function libraryMatch(items: LibraryItem[], link: YouTubeLink | null): LibraryItem | undefined {
  if (!link) return
  return items.find((i) => i.ready && i.source?.kind === 'youtube' && !!i.source.url && parseYouTube(i.source.url)?.videoId === link.videoId)
}

/** "VS Code and Jupyter", "the terminal": the tools a cached lesson runs in, for its meta line. */
const TOOL: Record<string, string> = { vscode: 'VS Code', jupyter: 'Jupyter', terminal: 'the terminal', excel: 'Excel' }
export function toolsLabel(tools: LibraryItem['tools'] | undefined): string | undefined {
  const names = (tools ?? []).map((t) => TOOL[t]).filter((t): t is string => !!t)
  if (!names.length) return
  return names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}
