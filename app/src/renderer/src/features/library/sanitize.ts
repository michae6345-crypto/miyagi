/**
 * Feature: library. Pure checks shared by main (main/features/library.ts) and the renderer. No imports from electron,
 * react or the bridge, so both sides can use it.
 *
 * Everything the engine sends about a cached lesson goes through here before it is shown: ids must match
 * LIBRARY_ID (never a path), only the known fields survive (no workdir, no absolute path, no key), strings and lists
 * are capped. Anything that fails is dropped, never guessed.
 */
import type { LessonTool, LibraryItem, OutlineStep } from '../../../../../../shared/contracts/events'

export const LIBRARY_ID = /^[A-Za-z0-9_-]{1,64}$/
export const isLibraryId = (id: unknown): id is string => typeof id === 'string' && LIBRARY_ID.test(id)

export type LibraryDetail = { item: LibraryItem; steps: OutlineStep[]; overview?: string }

const TOOLS: readonly LessonTool[] = ['vscode', 'jupyter', 'terminal', 'excel']
const MAX_ITEMS = 200
const MAX_STEPS = 100

/** A path-looking string (/Users/..., C:\..., ~/...) is never shown: it can leak a home folder. */
const PATHY = /(^|\s)(\/(Users|home|private|var|tmp|opt)\/|~\/|[A-Za-z]:\\)/

function str(v: unknown, max = 160): string | undefined {
  if (typeof v !== 'string') return undefined
  const s = v.replace(/\s+/g, ' ').trim()
  if (!s || PATHY.test(s)) return undefined
  return s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s
}
function int(v: unknown, min: number, max: number): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max ? Math.round(v) : undefined
}
const obj = (v: unknown): Record<string, unknown> | undefined => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined)

/** A YouTube video id from a youtube.com / youtu.be https URL, or undefined. Used for the i.ytimg.com thumbnail. */
export function youtubeId(url: string | undefined): string | undefined {
  if (!url) return undefined
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return undefined
  }
  if (u.protocol !== 'https:') return undefined
  const host = u.hostname.replace(/^www\.|^m\./, '')
  const id = host === 'youtu.be' ? u.pathname.slice(1) : host === 'youtube.com' ? (u.searchParams.get('v') ?? '') : ''
  return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : undefined
}

function source(v: unknown): LibraryItem['source'] {
  const s = obj(v)
  if (!s) return undefined
  const kind = s.kind === 'youtube' || s.kind === 'goal' || s.kind === 'library' ? s.kind : undefined
  const title = str(s.title)
  if (!kind || !title) return undefined
  // Only a YouTube https link survives (it opens through the open:external allowlist); anything else is dropped.
  const url = typeof s.url === 'string' && youtubeId(s.url) ? s.url : undefined
  return { kind, title, channel: str(s.channel, 80), durationS: int(s.durationS, 0, 86_400), url }
}

export function cleanItem(v: unknown): LibraryItem | undefined {
  const o = obj(v)
  if (!o || !isLibraryId(o.id)) return undefined
  const title = str(o.title)
  if (!title) return undefined
  const steps = int(o.steps, 0, 1000) ?? 0
  // The engine's order (the main tool first), known tools only, no repeats.
  const tools = Array.isArray(o.tools) ? [...new Set(o.tools.filter((t): t is LessonTool => TOOLS.includes(t as LessonTool)))] : []
  const p = obj(o.progress)
  const total = p ? int(p.total, 1, 1000) : undefined
  const stepIndex = p ? int(p.stepIndex, 0, 999) : undefined
  const progress = p && total !== undefined && stepIndex !== undefined && stepIndex < total ? { stepIndex, stepTitle: str(p.stepTitle, 80) ?? '', total } : undefined
  return {
    id: o.id,
    title,
    by: str(o.by, 80),
    steps,
    estMinutes: int(o.estMinutes, 1, 1440),
    tools,
    ready: o.ready === true,
    progress,
    source: source(o.source),
    updatedAt: str(o.updatedAt, 40)
  }
}

/** library {items} or a bare array (HTTP /library) → clean items, unique ids. Anything else → []. */
export function cleanList(v: unknown): LibraryItem[] {
  const raw = Array.isArray(v) ? v : Array.isArray(obj(v)?.items) ? (obj(v)!.items as unknown[]) : []
  const seen = new Set<string>()
  const out: LibraryItem[] = []
  for (const r of raw.slice(0, MAX_ITEMS)) {
    const it = cleanItem(r)
    if (it && !seen.has(it.id)) {
      seen.add(it.id)
      out.push(it)
    }
  }
  return out
}

/** library.item {item, steps?, overview?} → a clean detail, or undefined. `want`: the id that was asked for. */
export function cleanDetail(v: unknown, want?: string): LibraryDetail | undefined {
  const o = obj(v)
  const item = cleanItem(o?.item)
  if (!o || !item || (want && item.id !== want)) return undefined
  const steps: OutlineStep[] = []
  if (Array.isArray(o.steps))
    for (const [i, s] of o.steps.slice(0, MAX_STEPS).entries()) {
      const r = obj(s)
      const title = str(r?.title, 120)
      if (!r || !title) continue
      steps.push({ index: int(r.index, 0, 999) ?? i, title, what: str(r.what, 120), estMinutes: int(r.estMinutes, 1, 600) })
    }
  return { item, steps, overview: str(o.overview, 400) }
}
