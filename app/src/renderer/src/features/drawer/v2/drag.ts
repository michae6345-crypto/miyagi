/**
 * Feature: drawer (v2). Move the docked lesson panel by its header (a user on main 1d453ca0: "the step panel on the right
 * can't be moved"). The panel keeps its dock (core/dock panelRect) as home; the learner's drag is an offset from it,
 * saved, so it stays where they put it (this lesson and the next). A double-click on the header sends it home.
 *
 * Pure math here (tests: test/panelDrag.test.ts); the pointer handling is in LessonPanel.tsx (usePanelDrag).
 */
import { create } from 'zustand'
import type { Rect } from '../../../core/lesson'

export type Offset = { dx: number; dy: number }
export const HOME: Offset = { dx: 0, dy: 0 }

/** How far the pointer must travel before a press on the header is a drag (a plain press still clicks its buttons). */
export const DRAG_SLOP = 4
/** Of the panel, at least this much stays on screen below the work area's top: its header, so it can be dragged back. */
export const KEEP_VISIBLE = 72
/** The panel's shortest max height once moved down (its body scrolls past that). */
const MIN_H = 120

/** Has the pointer moved far enough to count as a drag? */
export const isDrag = (dx: number, dy: number, slop = DRAG_SLOP): boolean => Math.hypot(dx, dy) >= slop

/**
 * The offset, kept inside the work area (window coordinates): the whole width on screen, the top no higher than the
 * work area's top (never under the menu bar or the notch), and at least KEEP_VISIBLE of it above the bottom.
 */
export function clampOffset(rect: Rect, off: Offset, area: Rect, keep = KEEP_VISIBLE): Offset {
  const fin = (n: number): number => (Number.isFinite(n) ? n : 0)
  const minX = area.x
  const maxX = Math.max(minX, area.x + area.w - rect.w)
  const minY = area.y
  const maxY = Math.max(minY, area.y + area.h - keep)
  const x = Math.min(maxX, Math.max(minX, rect.x + fin(off.dx)))
  const y = Math.min(maxY, Math.max(minY, rect.y + fin(off.dy)))
  return { dx: Math.round(x - rect.x), dy: Math.round(y - rect.y) }
}

/** The panel's max height at this offset: its dock height, less what moving it down took (never under MIN_H). */
export const movedMaxHeight = (rect: Rect, off: Offset): number => Math.max(MIN_H, rect.h - Math.max(0, off.dy))

/** The panel's rect at this offset (window coordinates). */
export const movedRect = (rect: Rect, off: Offset): Rect => ({ x: rect.x + off.dx, y: rect.y + off.dy, w: rect.w, h: movedMaxHeight(rect, off) })

/** Is this press on something of its own (a button, a link, a field)? Then it's that control's, never a drag. */
export const ownsPress = (target: EventTarget | null): boolean => {
  const el = target as Element | null
  return !!el && typeof el.closest === 'function' && !!el.closest('button, a, input, textarea, select, [role="button"]')
}

// ---- the saved offset ------------------------------------------------------------------------------------------------

const KEY = 'miyagi.panel.offset'

/** A saved offset, or HOME when there is none or it isn't one. */
export function parseOffset(raw: string | null | undefined): Offset {
  if (!raw) return HOME
  try {
    const v = JSON.parse(raw) as Partial<Offset>
    return Number.isFinite(v?.dx) && Number.isFinite(v?.dy) ? { dx: Math.round(v.dx as number), dy: Math.round(v.dy as number) } : HOME
  } catch {
    return HOME
  }
}

function load(): Offset {
  try {
    return parseOffset(typeof localStorage === 'undefined' ? null : localStorage.getItem(KEY))
  } catch {
    return HOME
  }
}

export const usePanelOffset = create<{ off: Offset }>(() => ({ off: load() }))

/** The learner let go of the panel here (or double-clicked it home): keep it there. */
export function setPanelOffset(off: Offset): void {
  const cur = usePanelOffset.getState().off
  if (cur.dx === off.dx && cur.dy === off.dy) return
  usePanelOffset.setState({ off })
  try {
    if (off.dx === 0 && off.dy === 0) localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, JSON.stringify(off))
  } catch {
    // storage unavailable: the spot holds for this session only
  }
}
