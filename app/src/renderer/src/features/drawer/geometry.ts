/**
 * Feature: drawer. Where the tab and the panel sit, in overlay-window coordinates. Pure math, no React.
 *
 * The panel starts at the player dock's top and hugs the right edge with the dock's 8px inset, so when it
 * slides in over the player it reads as one column. panelRect's height is the MAX (down to the dock's
 * bottom, above the shortcut bar); the panel itself hugs its content and scrolls past that.
 */
import type { Layout } from '../../../../preload/api'
import type { Rect } from '../../core/lesson'

export const PANEL_W = 340
/** A "Just teach me" lesson has no player to line up with, and its drawer carries the code to type: give code room. */
export const PANEL_W_LESSON = 384
const INSET = 8
/** Same clearance as the player dock: the shortcut bar (88) + its 24px gap. */
const BAR_CLEARANCE = 112

/** The visible bar: 4×40, 6px from the right edge, vertically centered on the work area. */
export const TAB = { w: 4, h: 40, edge: 6 } as const
/** The click target around the bar (a 4px bar is too thin to hit). */
export const TAB_HIT = { w: 22, h: 64 } as const

/** Right edge of the usable area, in window coordinates. */
function rightEdge(layout: Layout): number {
  const wa = layout.workArea
  return Math.min(layout.width, wa.x + wa.width)
}

export function panelRect(layout: Layout, lessonMode = false): Rect {
  const wa = layout.workArea
  const w = Math.min(lessonMode ? PANEL_W_LESSON : PANEL_W, wa.width - INSET * 2)
  const h = Math.max(320, wa.height - INSET * 2 - BAR_CLEARANCE)
  return { x: rightEdge(layout) - INSET - w, y: wa.y + INSET, w, h }
}

/** The tab's hit box, flush with the right edge; the bar sits inside it, TAB.edge from that edge. */
export function tabRect(layout: Layout): Rect {
  const wa = layout.workArea
  return { x: rightEdge(layout) - TAB_HIT.w, y: Math.round(wa.y + wa.height / 2 - TAB_HIT.h / 2), w: TAB_HIT.w, h: TAB_HIT.h }
}
