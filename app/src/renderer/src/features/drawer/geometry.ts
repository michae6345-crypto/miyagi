/**
 * Feature: drawer. Where the tab and the panel sit, in overlay-window coordinates. Pure math, no React.
 *
 * The panel starts at the player dock's top, with the dock's 8px inset. In a video lesson the player is docked on the
 * right, so a right-hand drawer (and its tab) sits just left of the player instead of over it (Michael's test 10,
 * 7:35 AM: the drawer covered the right third of the video). panelRect's height is the MAX (down to the dock's
 * bottom, above the shortcut bar); the panel itself hugs its content and scrolls past that.
 */
import type { Layout } from '../../../../preload/api'
import type { Rect } from '../../core/lesson'
import { videoLayout } from '../../../../common/screenLayout'
import { panelRect as dockPanelRect } from '../../core/dock'
import { dockRect } from '../player/dock'
import { useDrawer, type Side } from './store'

/**
 * v2 (BUILD-PLAN A1): a "Just teach me" lesson's drawer is the docked lesson panel (v2/LessonPanel.tsx), 360 wide at
 * core/dock's place (right 16, top 52) in every lesson state (decision 6). It never yields, flips or tucks: the engine
 * keeps VS Code beside it (panel.state). false = the old drawer in lesson mode too (a one-line rollback).
 */
export const LESSON_PANEL_V2 = true

/** Where the v2 panel docks, in window coordinates (its max height; it hugs its content). */
export const lessonPanelRect = (layout: Layout): Rect => dockPanelRect(layout)

/** The edge the drawer is drawn on right now (store `at`): callers outside the layer get the same answer. */
const drawnAt = (): Side => useDrawer.getState().at

export const PANEL_W = 340
/**
 * A "Just teach me" lesson has no player to line up with, and its drawer carries the code to type and the option row
 * (Explain / Diagram / Show me / Hint + Check my work): mockup 01's width.
 */
export const PANEL_W_LESSON = 420
const INSET = 8
/** Same clearance as the player dock (core/geometry.ts): none, the bottom bar is gone. */
const BAR_CLEARANCE = 0

/** The visible bar: 4×40, 6px from the right edge, vertically centered on the work area. */
export const TAB = { w: 4, h: 40, edge: 6 } as const
/** The click target around the bar (a 4px bar is too thin to hit). */
export const TAB_HIT = { w: 22, h: 64 } as const

/**
 * Right edge of the usable area, in window coordinates. A video lesson (not lessonMode) has the player docked on the
 * right: the edge is the player's left side, so the drawer and its tab line up beside the video, never on it.
 */
function rightEdge(layout: Layout, lessonMode = true): number {
  const wa = layout.workArea
  const screen = Math.min(layout.width, wa.x + wa.width)
  return lessonMode ? screen : Math.min(screen, dockRect(wa).x)
}

/** Left edge of the usable area, in window coordinates. */
function leftEdge(layout: Layout): number {
  return Math.max(0, layout.workArea.x)
}

export function panelRect(layout: Layout, lessonMode = false, side: Side = drawnAt()): Rect {
  const wa = layout.workArea
  // A video lesson's drawer on the right lives in the column beside VS Code: under the player on a 1440x900-class Mac,
  // right of it on a wide screen (common/screenLayout.ts, Michael Nov 25: never over VS Code, never over the video).
  if (!lessonMode && side === 'right') {
    const p = videoLayout(wa).panel
    return { x: p.x, y: p.y, w: p.width, h: Math.max(120, p.height) }
  }
  const w = Math.min(lessonMode ? PANEL_W_LESSON : PANEL_W, wa.width - INSET * 2)
  const h = Math.max(320, wa.height - INSET * 2 - BAR_CLEARANCE)
  const x = side === 'left' ? leftEdge(layout) + INSET : rightEdge(layout, lessonMode) - INSET - w
  return { x, y: wa.y + INSET, w, h }
}

/** Mockup 02: the drawer collapsed to a step rail, and the concept panel to its left. */
export const RAIL_W = 52
export const CONCEPT_W = 560
const CONCEPT_GAP = 8

export function conceptRects(layout: Layout, lessonMode = false, side: Side = drawnAt()): { rail: Rect; panel: Rect } {
  const p = panelRect(layout, lessonMode, side)
  if (side === 'left') {  // mirrored: the rail on the left edge, the concept panel to its right
    const rail = { x: p.x, y: p.y, w: RAIL_W, h: p.h }
    const far = rightEdge(layout, lessonMode) - INSET
    const w = Math.max(280, Math.min(CONCEPT_W, far - (rail.x + RAIL_W + CONCEPT_GAP)))
    return { rail, panel: { x: rail.x + RAIL_W + CONCEPT_GAP, y: p.y, w, h: p.h } }
  }
  const rail = { x: p.x + p.w - RAIL_W, y: p.y, w: RAIL_W, h: p.h }
  const near = layout.workArea.x + INSET
  const w = Math.max(280, Math.min(CONCEPT_W, rail.x - CONCEPT_GAP - near))
  return { rail, panel: { x: rail.x - CONCEPT_GAP - w, y: p.y, w, h: p.h } }
}

/**
 * A "Just teach me" lesson's collapsed drawer: a labeled "Steps" handle on the right edge instead of the thin bar,
 * so the way back is plain to see (Michael, Sun 12:55 AM).
 */
export const HANDLE = { w: 30, h: 92, edge: 4 } as const

/**
 * The tab's hit box, flush with the right edge (in a video lesson, the player's left side); the bar (or the "Steps"
 * handle) sits inside it, TAB.edge from that edge. labeled = a "Just teach me" lesson (lessonMode).
 */
export function tabRect(layout: Layout, labeled = false, side: Side = drawnAt()): Rect {
  const wa = layout.workArea
  const s = labeled ? HANDLE : TAB_HIT
  const x = side === 'left' ? leftEdge(layout) : rightEdge(layout, labeled) - s.w
  return { x, y: Math.round(wa.y + wa.height / 2 - s.h / 2), w: s.w, h: s.h }
}
