/**
 * Spotlight geometry, pure (no React): screen points → window coordinates, the padded hole, and
 * where the caption goes. Kept apart so the math is easy to check on its own.
 *
 * v2 (W0-5): the shared rect math (toLocal, isUsableRect, intersects, contains, hole, overlapShare, sameRect and the
 * hole constants) moved to core/geometry.ts and is re-exported here unchanged, so every import keeps working.
 */
import type { Rect } from '../../core/lesson'
import { grow, intersects, overlapArea, type Point } from '../../core/geometry'

export {
  contains,
  hole,
  HOLE_MIN,
  HOLE_PAD,
  HOLE_PAD_Y,
  intersects,
  isUsableRect,
  MIN_VISIBLE_SHARE,
  overlapShare,
  sameRect,
  toLocal,
  type Point
} from '../../core/geometry'

export type Side = 'right' | 'left' | 'below' | 'above' | 'inside'

export const HOLE_RADIUS = 12
/** Caption: gap to the hole, distance kept from the screen edges. */
export const CAPTION_GAP = 8
export const EDGE_MARGIN = 16
/** How far the caption may slide along the hole to get clear of other UI before it settles for covering a little of it. */
export const MAX_SLIDE = 160
/**
 * The lines a caption beside the box covers: the box's own, plus this much above and below its midline (a two-line
 * chip). Fixed, so the lane doesn't depend on the caption's measured size (which depends on the lane's width).
 */
const BAND = 22

/** Corner radius: at most a third of the short side, so a one-line hole is a rounded box, not a capsule. */
export function holeRadius(r: Rect): number {
  return Math.max(0, Math.min(HOLE_RADIUS, r.w / 3, r.h / 3))
}

const clamp = (v: number, lo: number, hi: number): number => (hi < lo ? lo : Math.min(hi, Math.max(lo, v)))

type Placed = Point & { side: Side }

/**
 * The empty lane right of the box (Michael's tests 2-3, A10: "captions in empty space, right of the longest visible
 * line"). `x`: where a caption there starts, past the box and past any other text the engine boxed on the same lines
 * in the same column (`text`: OCR'd rects such as the coach's targets; the engine sends no per-line rects yet, so
 * usually this is just the box's right edge). `room`: how wide it may be before the screen edge or other UI that
 * starts right of the box (the docked player): the caption wraps to fit it rather than moving off that side.
 */
export function rightLane(target: Rect, bounds: Rect, avoid: Rect[] = [], text: Rect[] = []): { x: number; room: number } {
  const mid = target.y + target.h / 2
  const y0 = Math.min(target.y, mid - BAND)
  const y1 = Math.max(target.y + target.h, mid + BAND)
  const onLines = (r: Rect): boolean => r.y < y1 && r.y + r.h > y0
  const end = target.x + target.w
  const lineEnd = text.reduce((e, r) => (onLines(r) && r.x < end && r.x + r.w > target.x ? Math.max(e, r.x + r.w) : e), end)
  const x = lineEnd + CAPTION_GAP
  const edge = avoid.reduce((e, o) => (onLines(o) && o.x >= end && !intersects(o, target) ? Math.min(e, o.x - 8) : e), bounds.x + bounds.w - EDGE_MARGIN)
  return { x, room: edge - x }
}

/**
 * Where the caption goes, in window coordinates. `target` is the hole, `bounds` the usable area
 * (the work area: no menu bar, dock or taskbar), `avoid` our other overlay UI (shortcut bar, pill, cards), `text`
 * other boxed text on screen (see rightLane). The same side every time (Michael's tests 2-3, A10), never over the
 * editor's gutter (left of the code) and never on the box:
 *   1. right of the hole in its empty lane (rightLane), a chip centered on its midline (mockup 01; Michael's audit
 *      A7: top-aligned, it hung ~10 px low and spilled onto the next row, e.g. a terminal's tab strip)
 *   2. below / above the hole, aligned with its left edge (the code's, not the gutter's), when the lane is too
 *      narrow (a long line, the screen edge, the docked player)
 *   3. left of the hole (over the gutter) only when none of 1-2 fits on screen at all
 *   4. last resort: inside the hole's top-right corner
 * Always clamped so it stays fully on screen (top and bottom edges included), and never on the hole
 * (a spot that clamping pushed onto it is dropped). Other UI it must not cover (`avoid`, ignored where it
 * overlaps the target itself):
 *   - the first of 1-2 whose spot is free wins;
 *   - else the free spot nearest to one of them, sliding it along its edge of the hole (≤ MAX_SLIDE);
 *   - else (nothing free nearby) the one that covers the least, so it stays next to the target.
 */
export function placeCaption(target: Rect, size: { w: number; h: number }, bounds: Rect, avoid: Rect[] = [], text: Rect[] = []): Placed {
  const left = bounds.x + EDGE_MARGIN
  const top = bounds.y + EDGE_MARGIN
  const right = bounds.x + bounds.w - EDGE_MARGIN
  const bottom = bounds.y + bounds.h - EDGE_MARGIN
  const sideY = clamp(target.y + target.h / 2 - size.h / 2, top, bottom - size.h)
  const alongX = clamp(target.x, left, right - size.w)
  const endX = clamp(target.x + target.w - size.w, left, right - size.w)

  const rx = rightLane(target, bounds, [], text).x
  const lx = target.x - CAPTION_GAP - size.w
  const by = target.y + target.h + CAPTION_GAP
  const ay = target.y - CAPTION_GAP - size.h
  const inside: Placed = {
    x: clamp(target.x + target.w - size.w - 12, left, right - size.w),
    y: clamp(target.y + 12, top, bottom - size.h),
    side: 'inside'
  }
  // The hole plus a hairline of air: no caption spot may touch it.
  const keepOff = grow(target, 2)
  const offHole = (p: Placed): boolean => !intersects({ x: p.x, y: p.y, w: size.w, h: size.h }, keepOff)
  const candidates: Array<Placed | false> = [
    rx + size.w <= right && { x: rx, y: sideY, side: 'right' },
    by + size.h <= bottom && { x: alongX, y: by, side: 'below' },
    ay >= top && { x: alongX, y: ay, side: 'above' },
    // Flipped to end at the hole's right edge, then the left side: for a target next to our own UI on its right (the
    // drawer), where every spot above runs under it (Michael's test 7: "Click ▷ t..." cut at the drawer's edge).
    by + size.h <= bottom && { x: endX, y: by, side: 'below' },
    ay >= top && { x: endX, y: ay, side: 'above' },
    lx >= left && { x: lx, y: sideY, side: 'left' }
  ]
  const fitting = candidates.filter((p): p is Placed => !!p && offHole(p))
  if (!fitting.length) {
    // Nothing fits right, below or above (a box that fills the screen's height at its right edge): the left side,
    // and covering the target only when even that doesn't fit.
    const l: Placed = { x: lx, y: sideY, side: 'left' }
    return lx >= left && offHole(l) ? l : inside
  }

  // Our other UI, slightly grown; plus the hole itself so sliding never covers the target.
  const blockers = [...avoid.filter((o) => !intersects(o, target)).map((o) => grow(o, 8)), grow(target, 4)]
  const covered = (x: number, y: number): number => blockers.reduce((sum, b) => sum + overlapArea({ x, y, w: size.w, h: size.h }, b), 0)

  const free = fitting.find((p) => !covered(p.x, p.y))
  if (free) return free

  let best: { p: Placed; d: number } | undefined
  for (const p of fitting) {
    for (let d = 4; d <= MAX_SLIDE && (!best || d < best.d); d += 4) {
      const y = [p.y - d, p.y + d].find((y) => y >= top && y + size.h <= bottom && !covered(p.x, y))
      if (y !== undefined) {
        best = { p: { ...p, y }, d }
        break
      }
    }
  }
  if (best) return best.p
  return fitting.reduce((a, b) => (covered(b.x, b.y) < covered(a.x, a.y) ? b : a))
}
