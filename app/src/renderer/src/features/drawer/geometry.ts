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
/**
 * A "Just teach me" lesson has no player to line up with, and its drawer carries the code to type and the option row
 * (Explain / Diagram / Show me / Hint + Check my work): mockup 01's width.
 */
export const PANEL_W_LESSON = 420
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

/** Mockup 02: the drawer collapsed to a step rail, and the concept panel to its left. */
export const RAIL_W = 52
export const CONCEPT_W = 560
const CONCEPT_GAP = 8

export function conceptRects(layout: Layout, lessonMode = false): { rail: Rect; panel: Rect } {
  const p = panelRect(layout, lessonMode)
  const rail = { x: p.x + p.w - RAIL_W, y: p.y, w: RAIL_W, h: p.h }
  const leftEdge = layout.workArea.x + INSET
  const w = Math.max(280, Math.min(CONCEPT_W, rail.x - CONCEPT_GAP - leftEdge))
  return { rail, panel: { x: rail.x - CONCEPT_GAP - w, y: p.y, w, h: p.h } }
}

/**
 * A "Just teach me" lesson's collapsed drawer: a labeled "Steps" handle on the right edge instead of the thin bar,
 * so the way back is plain to see (Michael, Sun 12:55 AM).
 */
export const HANDLE = { w: 30, h: 92, edge: 4 } as const

/** The tab's hit box, flush with the right edge; the bar (or the "Steps" handle) sits inside it, TAB.edge from that edge. */
export function tabRect(layout: Layout, labeled = false): Rect {
  const wa = layout.workArea
  const s = labeled ? HANDLE : TAB_HIT
  return { x: rightEdge(layout) - s.w, y: Math.round(wa.y + wa.height / 2 - s.h / 2), w: s.w, h: s.h }
}
