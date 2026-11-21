/**
 * Feature: dashboard. ONE list of "lessons to continue" for Home, Lessons and Progress.
 *
 * Why the three pages used to disagree: Home read the engine's `progress.inProgress` (newest first, saved lessons only),
 * Lessons read the library's own `progress` per saved lesson, and Progress listed `inProgress` rows even when the lesson
 * wasn't saved (Resume stayed disabled). Same lesson, different sources, different order. Here both sources are merged
 * by saved-lesson id (or title), a lesson finished after its last activity drops out, and the newest comes first.
 */
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import type { DashData } from './types'

export type Cont = {
  key: string
  title: string
  /** The saved lesson Continue starts. Without one the lesson can't be picked up from here, so it isn't listed. */
  libraryId: string
  stepIndex: number
  total: number
  stepTitle?: string
  passed: number
  at?: number
}

const norm = (s: string): string => s.toLowerCase().replace(/\s+/g, ' ').trim()

export function continueList(data: DashData | undefined, items: LibraryItem[]): Cont[] {
  const byLib = new Map<string, Cont>()
  const put = (c: Cont): void => {
    const have = byLib.get(c.libraryId)
    // The newer activity wins; a source with no time never replaces one that has it.
    if (!have || (c.at ?? 0) > (have.at ?? 0) || (have.at === undefined && c.at === undefined && c.total > have.total)) byLib.set(c.libraryId, { ...have, ...c, at: c.at ?? have?.at })
  }
  for (const a of data?.inProgress ?? []) {
    if (!a.libraryId) continue
    const item = items.find((x) => x.id === a.libraryId)
    // A lesson this Mac no longer has saved can't start: leave it out everywhere.
    if (items.length && !item) continue
    const total = a.stepCount ?? item?.progress?.total ?? item?.steps ?? 0
    if (!total) continue
    const stepIndex = a.stepIndex ?? item?.progress?.stepIndex ?? 0
    put({ key: a.libraryId, title: a.title || item?.title || 'Your lesson', libraryId: a.libraryId, stepIndex, total, stepTitle: a.stepTitle ?? item?.progress?.stepTitle, passed: a.passed ?? stepIndex, at: a.lastActiveAt })
  }
  for (const i of items) {
    const p = i.progress
    if (!p || p.stepIndex >= p.total || !i.ready) continue
    put({ key: i.id, title: i.title, libraryId: i.id, stepIndex: p.stepIndex, total: p.total, stepTitle: p.stepTitle, passed: p.stepIndex })
  }
  const done = data?.completed ?? []
  const out = [...byLib.values()].filter((c) => {
    const fin = done.filter((d) => d.libraryId === c.libraryId || norm(d.title) === norm(c.title))
    // Finished after it was last touched (or no time to compare, and the library no longer has it mid-way).
    return !fin.some((d) => (d.finishedAt ?? 0) >= (c.at ?? 0) && (c.at !== undefined || !items.find((x) => x.id === c.libraryId)?.progress))
  })
  // Two saved copies of one lesson read as one row.
  const seen = new Set<string>()
  return out
    .sort((a, b) => (b.at ?? 0) - (a.at ?? 0))
    .filter((c) => (seen.has(norm(c.title)) ? false : (seen.add(norm(c.title)), true)))
}

/** "Step 4 of 7 · Train it". */
export const contLine = (c: Pick<Cont, 'stepIndex' | 'total' | 'stepTitle'>): string =>
  `Step ${Math.min(c.stepIndex + 1, c.total)} of ${c.total}${c.stepTitle ? ` · ${c.stepTitle}` : ''}`
