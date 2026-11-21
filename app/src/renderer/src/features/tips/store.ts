/**
 * Feature: tips. What the learner has already been shown, and the one coach mark on screen right now.
 *
 *   seen     tips dismissed once (Got it, Esc, or read long enough before their target left): never shown again
 *   off      "Don't show tips": nothing is shown again until resetTips()
 *   active   the tip on screen (at most one)
 *
 * Persisted in localStorage (`miyagi.tips`), which works in the browser stage and in the Electron overlay's renderer
 * alike. When core adds a `tips` pref (Core request 1 in agents/tips.md: common/prefs.ts + sanitizePrefs), the same
 * state is read from and written to prefs instead, so it follows Settings' reset and every window; nothing here changes
 * then: `prefsHasTips()` turns the prefs path on by itself as soon as DEFAULT_PREFS carries the key.
 */
import { create } from 'zustand'
import { isElectron } from '../../bridge'
import { onUi } from '../../core/bus'
import { setPrefs, usePrefs, type Prefs } from '../../core/prefs'
import type { TipId } from './tips'

export type TipsSaved = { off: boolean; seen: TipId[] }

type TipsState = TipsSaved & {
  active?: TipId
  /** When the last tip closed (ms). The next one waits a moment, so tips never chain back to back. */
  closedAt: number
  /** The tip's own "…" menu is open. */
  menu: boolean
}

const KEY = 'miyagi.tips'
const EMPTY: TipsSaved = { off: false, seen: [] }

function clean(raw: unknown): TipsSaved {
  if (!raw || typeof raw !== 'object') return { ...EMPTY }
  const r = raw as Record<string, unknown>
  const seen = Array.isArray(r.seen) ? (r.seen.filter((x) => typeof x === 'string').slice(0, 32) as TipId[]) : []
  return { off: r.off === true, seen }
}

/** Core request 1: once DEFAULT_PREFS has `tips`, prefs are the store (main saves them, every window hears). */
function prefsHasTips(): boolean {
  return 'tips' in (usePrefs.getState() as object)
}

function readLocal(): TipsSaved {
  try {
    return clean(JSON.parse(localStorage.getItem(KEY) ?? '{}'))
  } catch {
    return { ...EMPTY }
  }
}

function load(): TipsSaved {
  if (prefsHasTips()) return clean((usePrefs.getState() as unknown as { tips: unknown }).tips)
  return readLocal()
}

function save(s: TipsSaved): void {
  if (prefsHasTips()) {
    setPrefs({ tips: s } as unknown as Partial<Prefs>)
    return
  }
  try {
    localStorage.setItem(KEY, JSON.stringify(s))
  } catch {
    // private window: this session only
  }
}

/**
 * Browser stage: tips stay out of every other lane's review shots unless asked for. `?tips` (any value) or
 * `?scenario=tips` turns them on; `?tips=reset` also forgets what was seen. Electron: always on (the product).
 */
const params = !isElectron && typeof location !== 'undefined' ? new URLSearchParams(location.search) : undefined
export const tipsEnabled = isElectron || !!params && (params.has('tips') || params.get('scenario') === 'tips')
if (params?.get('tips') === 'reset') save({ ...EMPTY })

export const useTips = create<TipsState>(() => ({ ...load(), active: undefined, closedAt: 0, menu: false }))

// Prefs arrive after start-up (and from other windows): follow them when they hold the tips.
usePrefs.subscribe((p) => {
  if (!prefsHasTips()) return
  const t = clean((p as unknown as { tips: unknown }).tips)
  const s = useTips.getState()
  if (t.off !== s.off || t.seen.join() !== s.seen.join()) useTips.setState({ ...t, active: t.off || (s.active && t.seen.includes(s.active)) ? undefined : s.active })
})

function persist(): void {
  const { off, seen } = useTips.getState()
  save({ off, seen })
}

/** Put a tip on screen (the layer decided it may show). */
export function showTip(id: TipId): void {
  const s = useTips.getState()
  if (s.off || s.active === id || s.seen.includes(id)) return
  useTips.setState({ active: id, menu: false })
}

/** The learner closed it (Got it, Esc): it never comes back. */
export function dismissTip(): void {
  const { active, seen } = useTips.getState()
  if (!active) return
  useTips.setState({ active: undefined, menu: false, closedAt: Date.now(), seen: seen.includes(active) ? seen : [...seen, active] })
  persist()
}

/** Its target left (the panel closed, a card opened). `read` = it was on screen long enough to count as seen. */
export function withdrawTip(read: boolean): void {
  if (read) return dismissTip()
  useTips.setState({ active: undefined, menu: false, closedAt: Date.now() })
}

/** Also mark another tip seen (the Mini tip teaches the same click as the pill's). */
export function markSeen(id: TipId): void {
  const { seen } = useTips.getState()
  if (seen.includes(id)) return
  useTips.setState({ seen: [...seen, id] })
  persist()
}

/** "Don't show tips". */
export function turnTipsOff(): void {
  useTips.setState({ off: true, active: undefined, menu: false, closedAt: Date.now() })
  persist()
}

/** Show every tip again (for Settings: Core request 3). */
export function resetTips(): void {
  useTips.setState({ off: false, seen: [], active: undefined, menu: false })
  persist()
}

export const setTipMenu = (menu: boolean): void => useTips.setState({ menu })

// Esc closes the tip first (its menu first of all), and stops there: the panel under it stays open. Capture phase on
// window, so the stage's own Esc (emitUi('dismiss')) never sees it while a tip is up.
if (typeof window !== 'undefined') {
  window.addEventListener(
    'keydown',
    (e) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      const s = useTips.getState()
      if (!s.active) return
      e.preventDefault()
      e.stopImmediatePropagation()
      if (s.menu) setTipMenu(false)
      else dismissTip()
    },
    true
  )
}
// A dismiss from elsewhere (a card's ✕, Electron's Esc path) also closes the tip: Esc means "not now" everywhere.
onUi('dismiss', () => {
  if (useTips.getState().active) dismissTip()
})
