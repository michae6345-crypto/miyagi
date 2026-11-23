/**
 * Feature: settings. The learner's app preferences that live in the renderer (text size, density, reduce motion, the
 * start page). Same store pattern as store.ts: one zustand store, validated on read, persisted to localStorage (every
 * miyagi window shares the origin, so the `storage` event carries a change to the others). Pure helpers are exported
 * for test/settingsLocal.test.ts. No key, token or lesson content ever lands here.
 */
import { create } from 'zustand'

export const TEXT_SIZES = ['small', 'default', 'large'] as const
export type TextSize = (typeof TEXT_SIZES)[number]
export const DENSITIES = ['comfortable', 'compact'] as const
export type Density = (typeof DENSITIES)[number]
export const MOTIONS = ['system', 'reduce'] as const
export type MotionPref = (typeof MOTIONS)[number]
export const START_PAGES = ['home', 'lessons', 'skills', 'progress'] as const
export type StartPage = (typeof START_PAGES)[number]

export const CODE_SIZES = ['small', 'default', 'large'] as const
export type CodeSize = (typeof CODE_SIZES)[number]

export type Local = {
  textSize: TextSize
  density: Density
  motion: MotionPref
  startPage: StartPage
  /** Appearance: the home window's sidebar shows icons only, at any window size (features/shell Shell.tsx). */
  sidebarCompact: boolean
  /** Appearance: the setup status block under the sidebar's pages. */
  sidebarStatus: boolean
  /** Editor: the font size of code in lesson cards and the steps panel (apply.ts sets --mg-code-size). */
  codeSize: CodeSize
  /** Editor: number the lines of a code sample. */
  lineNumbers: boolean
  /** Editor: long lines wrap instead of scrolling sideways. */
  wrapCode: boolean
  /** Lessons: Skip step asks for a second press (settings/guard.ts). */
  confirmSkip: boolean
  /** Lessons: "about N min left" in the steps panel. */
  timeLeft: boolean
}
export const DEFAULT_LOCAL: Local = {
  textSize: 'default',
  density: 'comfortable',
  motion: 'system',
  startPage: 'home',
  sidebarCompact: false,
  sidebarStatus: true,
  codeSize: 'default',
  lineNumbers: false,
  wrapCode: false,
  confirmSkip: false,
  timeLeft: true
}
const FLAGS = ['sidebarCompact', 'sidebarStatus', 'lineNumbers', 'wrapCode', 'confirmSkip', 'timeLeft'] as const

const pick = <T extends string>(list: readonly T[], v: unknown): T | undefined => ((list as readonly string[]).includes(v as string) ? (v as T) : undefined)

/** Keep only known keys with valid values (storage and the `storage` event are untrusted). */
export function sanitizeLocal(raw: unknown): Partial<Local> {
  const o = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const out: Partial<Local> = {}
  const t = pick(TEXT_SIZES, o.textSize)
  if (t) out.textSize = t
  const d = pick(DENSITIES, o.density)
  if (d) out.density = d
  const m = pick(MOTIONS, o.motion)
  if (m) out.motion = m
  const s = pick(START_PAGES, o.startPage)
  if (s) out.startPage = s
  const c = pick(CODE_SIZES, o.codeSize)
  if (c) out.codeSize = c
  for (const k of FLAGS) if (typeof o[k] === 'boolean') out[k] = o[k] as boolean
  return out
}

/** The page zoom for a text size: a root scale, applied to the app windows only. */
export const TEXT_SCALE: Record<TextSize, number> = { small: 0.92, default: 1, large: 1.1 }
/** The code font size (px) for a code sample size: lesson cards and the steps panel read it as --mg-code-size. */
export const CODE_PX: Record<CodeSize, number> = { small: 11, default: 12, large: 14 }
/** A row's minimum height by density (px). */
export const ROW_HEIGHT: Record<Density, number> = { comfortable: 56, compact: 44 }

const KEY = 'miyagi.settings.local'

function read(): Local {
  try {
    return { ...DEFAULT_LOCAL, ...sanitizeLocal(JSON.parse(localStorage.getItem(KEY) ?? '{}')) }
  } catch {
    return { ...DEFAULT_LOCAL }
  }
}

export const useLocal = create<Local>(() => read())

export function setLocal(patch: Partial<Local>): void {
  const next = { ...useLocal.getState(), ...sanitizeLocal(patch) }
  useLocal.setState(next)
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* private window: this run only */
  }
}

/** Put every renderer preference back to its default (Storage and data). */
export function resetLocal(): void {
  setLocal({ ...DEFAULT_LOCAL })
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) useLocal.setState(read())
  })
}

// ---- search --------------------------------------------------------------------------------------------------------

export type Findable = { id: string; panel: string; label: string; caption?: string; keywords?: string }

/** Settings that match every word of the query, best first (label hits before caption and keyword hits). */
export function searchSettings<T extends Findable>(items: readonly T[], query: string): T[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return []
  const scored: { item: T; score: number }[] = []
  for (const item of items) {
    const label = item.label.toLowerCase()
    const rest = `${item.caption ?? ''} ${item.keywords ?? ''}`.toLowerCase()
    let score = 0
    let all = true
    for (const w of words) {
      if (label.startsWith(w)) score += 3
      else if (label.includes(w)) score += 2
      else if (rest.includes(w)) score += 1
      else {
        all = false
        break
      }
    }
    if (all) scored.push({ item, score })
  }
  return scored.sort((a, b) => b.score - a.score).map((s) => s.item)
}

// ---- export ----------------------------------------------------------------------------------------------------------

/** The learner's progress as pretty JSON, from what the app already loaded (never a key or a lesson's code). */
export function progressJson(data: unknown, now: Date = new Date()): string {
  return JSON.stringify({ app: 'miyagi', exportedAt: now.toISOString(), progress: data ?? null }, null, 2)
}
