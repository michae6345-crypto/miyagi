/**
 * Feature: notch-home. The home panel's layout math, pure so test/notchHomeLayout.test.ts runs it offline (MIC-89).
 *
 * Michael's shot (Nov 26, main 8d28b564) had the left half spilling over the divider: a long step line ("Step 1 of 7 ·
 * Set up profile reference and layout") and the progress bar ran under the right column, the title wrapped past the
 * thumbnail, Continue sat on the bottom edge with a dead gap above it, and bon was jammed into the Library row. The
 * cause of the spill: the left half was a grid whose one auto column grew to its widest nowrap line (a grid item's
 * min-width is its min-content), so `truncate` never truncated. Now every column has a fixed width from here:
 *
 *   | padX | left (thumb + text) | gutter | rule | gutter | right (rows) | padX |   = HOME_W
 *
 * and both columns stretch to one height, so the title block and the ask row share a top line and Continue lesson and
 * the Library row share a bottom line. The left half spaces its three groups (title block, progress, Continue) evenly.
 */
import { NOTCH_RADII, SHORT_OPEN_H } from '../../core/notchGeometry'

/** The panel's own width (the island adds its open top radius plus its taper, 19 + 18, each side): 634 in all. */
export const HOME_W = 560

export const HOME = {
  /** Inside the panel: left/right, top (under the notch's own height), bottom (clear of the rounded bottom corners). */
  padX: 18,
  padTop: 14,
  padBottom: 18,
  /** Each side of the divider, and the divider itself. */
  gutter: 16,
  rule: 1,
  /** The right column (ask, drop zone, ready lessons, Library + bon). */
  right: 212,
  /** The Continue thumbnail (16:9) and the space between it and its text. */
  thumb: { w: 80, h: 45 },
  thumbGap: 12,
  /** Right column rows: a row (as tall as Continue lesson, so the footer shares its line), the drop zone, the gap between them, the least room above the footer. */
  row: 30,
  drop: 36,
  rowGap: 4,
  footGap: 8,
  /** bon's own slot in the footer (its button is `bon` square; `bonGap` keeps it off the Library link). */
  bon: 26,
  bonGap: 12,
  /** How many ready lessons the right column lists. */
  ready: 2,
  /** The panel body's least height (the left half's own content needs about this). */
  minBody: 136,
  /** How far every element stays inside the island's slanted sides and rounded bottom corners. */
  clearance: 8
} as const

export type HomeColumns = {
  /** The width inside padX. */
  inner: number
  left: number
  right: number
  /** The title / step text beside the thumbnail. */
  text: number
  /** x of the divider and of the right column, from the panel's left edge. */
  ruleX: number
  rightX: number
}

/** The two columns at a panel width. Nothing crosses the divider: each column has its own fixed width. */
export function homeColumns(w: number = HOME_W): HomeColumns {
  const inner = w - 2 * HOME.padX
  const left = inner - HOME.right - 2 * HOME.gutter - HOME.rule
  return {
    inner,
    left,
    right: HOME.right,
    text: left - HOME.thumb.w - HOME.thumbGap,
    ruleX: HOME.padX + left + HOME.gutter,
    rightX: HOME.padX + left + 2 * HOME.gutter + HOME.rule
  }
}

/** The right column's natural height with `ready` lessons listed (capped at HOME.ready). */
export function rightHeight(ready: number): number {
  const n = Math.max(0, Math.min(HOME.ready, Math.floor(ready)))
  return HOME.row + HOME.rowGap + HOME.drop + n * (HOME.rowGap + HOME.row) + HOME.footGap + HOME.row
}

/** The panel body's height: as tall as the right column needs, never under HOME.minBody. */
export function bodyHeight(ready: number): number {
  return Math.max(HOME.minBody, rightHeight(ready))
}

/** The whole panel (what the island measures): body plus top and bottom padding. */
export function panelHeight(ready: number): number {
  return HOME.padTop + bodyHeight(ready) + HOME.padBottom
}

export type Seg = 'done' | 'at' | 'todo'

/** The progress segments: done, the step you are on, the rest. At most `max` segments (a long lesson is scaled). */
export function progressSegs(n: number, total: number, max = 24): Seg[] {
  if (!(total > 0)) return []
  const segs = Math.min(Math.floor(total), max)
  const step = Math.max(1, Math.min(n, total))
  const at = Math.min(segs - 1, Math.round(((step - 1) / total) * segs))
  return Array.from({ length: segs }, (_, i) => (i < at ? 'done' : i === at ? 'at' : 'todo'))
}

/** The drop zone's line. Any web or GitHub link builds a lesson now (ANY-LINK.md), so the idle line names a link. */
export function dropLabel(s: { sent: boolean; miss: boolean; linkAny: boolean }): string {
  if (s.sent) return 'Building your lesson…'
  if (s.miss) return s.linkAny ? 'That isn’t a link miyagi can read' : 'Only YouTube links work here'
  return 'Drop a link to learn it'
}

/**
 * How far the island's side is from its outer edge at depth `y` (0 = the display top) on an open shape `h` tall,
 * with the radii core/notchGeometry.ts notchPath draws: the concave ear down to `top`, then a slanted side leaning in
 * by `taper`, then the convex bottom corner. The shape is wide enough that no radius is clamped by width.
 */
export function sideInsetAt(h: number, y: number): number {
  const r = h < SHORT_OPEN_H ? NOTCH_RADII.peek : NOTCH_RADII.open
  const t = Math.max(0, Math.min(r.top, h))
  const k = r.taper
  const b = Math.max(0, Math.min(r.bottom, h - t))
  const lean = h - t > 0 ? k * (1 - b / (h - t)) : k
  const yy = Math.max(0, Math.min(h, y))
  if (yy <= t) return t // the ear: the side is a full top radius in
  if (yy <= h - b) return t + (h - b - t > 0 ? (lean * (yy - t)) / (h - b - t) : 0)
  // The bottom corner, a quadratic from (t + lean, h - b) through the control (t + k, h) to (t + k + b, h).
  const s = 1 - Math.sqrt((h - yy) / b)
  return (1 - s) * (1 - s) * (t + lean) + 2 * s * (1 - s) * (t + k) + s * s * (t + k + b)
}

/** Where the panel's left edge sits from the island's outer edge (core/notchGeometry.ts notchSize: top + taper). */
export const PANEL_INSET = NOTCH_RADII.open.top + NOTCH_RADII.open.taper
