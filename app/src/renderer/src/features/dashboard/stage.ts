/**
 * Feature: dashboard. Browser stage only: mock/scenarios/dashboard.json is written around one day (`stageAnchor`,
 * "2026-11-20"). So the stage looks the same on any day, every date in a mock payload is moved by (today - anchor)
 * days before it is read. Never in Electron, never for a payload without `stageAnchor` (a real engine never sends it).
 */
import { engineMode } from '../../bridge'

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/
/** Epoch-second fields the dashboard reads. */
const TIME_KEYS = new Set(['finishedAt', 'lastActiveAt', 'masteredAt', 'lastPracticedAt', 'dueAt', 'lastAt', 'pausedFrom', 'pausedUntil'])

const noon = (k: string): Date => new Date(`${k}T12:00:00`)
const shiftKey = (k: string, days: number): string => {
  const d = noon(k)
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function walk(v: unknown, days: number): unknown {
  if (Array.isArray(v)) return v.map((x) => walk(x, days))
  if (!v || typeof v !== 'object') return v
  const out: Record<string, unknown> = {}
  for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
    if (k === 'date' && typeof x === 'string' && DAY_RE.test(x)) out[k] = shiftKey(x, days)
    else if (TIME_KEYS.has(k) && typeof x === 'number') out[k] = x + days * 86_400
    else out[k] = walk(x, days)
  }
  return out
}

export function stageRebase(raw: unknown): unknown {
  if (engineMode() !== 'inline' || !raw || typeof raw !== 'object') return raw
  const anchor = (raw as { stageAnchor?: unknown }).stageAnchor
  if (typeof anchor !== 'string' || !DAY_RE.test(anchor)) return raw
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12)
  const days = Math.round((today.getTime() - noon(anchor).getTime()) / 86_400_000)
  return days ? walk(raw, days) : raw
}
