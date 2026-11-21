/**
 * Feature: launcher. Where the panel goes while a spotlight is up (Michael's review A13: the ask panel covered the
 * line being asked about). Pure geometry in the launcher window's coordinates; the window covers the display, so the
 * spotlight's box (screen points → toLocal) lands in the same space.
 *
 * The panel always grows out of the notch. If its grown rect would cover the box:
 *   1. narrower, still centered under the notch, when the box sits to one side and at least MIN_WIDTH stays free;
 *   2. else full width, sliding down to just below the box, when it still fits above the work area's bottom;
 *   3. else where it always is (a panel half off-screen is worse than one over the box).
 */
import type { Rect } from '../../core/lesson'
import { intersects } from '../spotlight/place'

/** Room kept between the panel and the box. */
export const CLEAR_GAP = 12
/** Narrower than this the footer and rows get cramped: slide below the box instead. */
export const MIN_WIDTH = 480

/** The panel's grown width and how far below its usual top it sits (0 = at the notch). */
export type Placement = { w: number; dy: number }

export function placeClear({
  box,
  width,
  viewW,
  top,
  height,
  bottom
}: {
  /** The spotlight's cut-out (padded), window coordinates. */
  box?: Rect
  /** The panel's usual width. */
  width: number
  /** The window's width: the panel is centered in it. */
  viewW: number
  /** The panel's top edge (the notch's top). */
  top: number
  /** The panel's grown height. */
  height: number
  /** The work area's bottom edge, window coordinates. */
  bottom: number
}): Placement {
  const usual = { w: width, dy: 0 }
  if (!box) return usual
  const cx = viewW / 2
  const zone = { x: box.x - CLEAR_GAP, y: box.y - CLEAR_GAP, w: box.w + CLEAR_GAP * 2, h: box.h + CLEAR_GAP * 2 }
  if (!intersects({ x: cx - width / 2, y: top, w: width, h: height }, zone)) return usual
  // 1. Narrower: the half-width left between the center and the box's near edge.
  const room = zone.x >= cx ? zone.x - cx : zone.x + zone.w <= cx ? cx - (zone.x + zone.w) : 0
  const w = Math.floor(Math.min(width, room * 2))
  if (w >= MIN_WIDTH) return { w, dy: 0 }
  // 2. Below the box.
  const dy = Math.ceil(zone.y + zone.h - top)
  if (dy > 0 && top + dy + height <= bottom) return { w: width, dy }
  return usual
}
