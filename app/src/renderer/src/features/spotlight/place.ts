/**
 * Spotlight geometry, pure (no React): screen points → window coordinates, the padded hole, and
 * where the caption goes. Kept apart so the math is easy to check on its own.
 */
import type { Rect } from '../../core/lesson'

export type Point = { x: number; y: number }
export type Side = 'right' | 'left' | 'below' | 'above' | 'inside'

/** Breathing room around the OCR'd text block (the engine's own padding is small; this matches mockup 04). */
export const HOLE_PAD = 8
/** A one-word target still gets a hole you can see. */
export const HOLE_MIN = { w: 44, h: 30 } as const
export const HOLE_RADIUS = 12
/** Caption: gap to the hole, distance kept from the screen edges, offset from the hole's top (mockup 04: 21). */
export const CAPTION_GAP = 22
export const EDGE_MARGIN = 16
export const CAPTION_TOP_OFFSET = 21

/**
 * Engine rects are screen points with (0,0) at the PRIMARY display's top-left (macOS / Quartz,
 * y down, Retina already divided out). The overlay window sits at `origin` in the same space
 * (Electron's screen coordinates are also primary-top-left DIPs), so local = screen − origin.
 * A display left of / above the primary has a negative origin; that just works.
 */
export function toLocal(r: Rect, origin: Point): Rect {
  return { x: r.x - origin.x, y: r.y - origin.y, w: r.w, h: r.h }
}

export function intersects(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

export function contains(r: Rect, p: Point): boolean {
  return p.x >= r.x && p.x < r.x + r.w && p.y >= r.y && p.y < r.y + r.h
}

/** The cut-out: the target plus padding, grown around its center to a minimum size. */
export function hole(r: Rect, pad = HOLE_PAD): Rect {
  const w = Math.max(r.w + pad * 2, HOLE_MIN.w)
  const h = Math.max(r.h + pad * 2, HOLE_MIN.h)
  return { x: r.x + r.w / 2 - w / 2, y: r.y + r.h / 2 - h / 2, w, h }
}

/** Corner radius that never exceeds half the short side. */
export function holeRadius(r: Rect): number {
  return Math.min(HOLE_RADIUS, r.w / 2, r.h / 2)
}

const clamp = (v: number, lo: number, hi: number): number => (hi < lo ? lo : Math.min(hi, Math.max(lo, v)))

/**
 * Where the caption goes, in window coordinates. `target` is the hole, `bounds` the usable area
 * (the work area: no menu bar, dock or taskbar).
 *   1. right of the hole, top-aligned with its first line (FRONTEND-HANDOFF → Placement)
 *   2. flipped to the left when the right side would run off-screen
 *   3. below / above the hole when it's too wide for either side (a full-width terminal)
 *   4. last resort: inside the hole's top-right corner
 * Always clamped so it stays fully on screen (top and bottom edges included).
 */
export function placeCaption(target: Rect, size: { w: number; h: number }, bounds: Rect): Point & { side: Side } {
  const left = bounds.x + EDGE_MARGIN
  const top = bounds.y + EDGE_MARGIN
  const right = bounds.x + bounds.w - EDGE_MARGIN
  const bottom = bounds.y + bounds.h - EDGE_MARGIN
  const sideY = clamp(target.y + Math.min(CAPTION_TOP_OFFSET, target.h / 4), top, bottom - size.h)
  const alongX = clamp(target.x, left, right - size.w)

  const rx = target.x + target.w + CAPTION_GAP
  if (rx + size.w <= right) return { x: rx, y: sideY, side: 'right' }
  const lx = target.x - CAPTION_GAP - size.w
  if (lx >= left) return { x: lx, y: sideY, side: 'left' }
  const by = target.y + target.h + CAPTION_GAP / 2
  if (by + size.h <= bottom) return { x: alongX, y: by, side: 'below' }
  const ay = target.y - CAPTION_GAP / 2 - size.h
  if (ay >= top) return { x: alongX, y: ay, side: 'above' }
  return {
    x: clamp(target.x + target.w - size.w - 12, left, right - size.w),
    y: clamp(target.y + 12, top, bottom - size.h),
    side: 'inside'
  }
}

/** Share of `a`'s area that lies inside `b` (0–1). */
export function overlapShare(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return w > 0 && h > 0 && a.w * a.h > 0 ? (w * h) / (a.w * a.h) : 0
}

/** OCR jitter: the engine re-reads the screen every ~2s and boxes wobble by a point or two. */
export function sameRect(a: Rect, b: Rect, tol = 2): boolean {
  return Math.abs(a.x - b.x) <= tol && Math.abs(a.y - b.y) <= tol && Math.abs(a.w - b.w) <= tol && Math.abs(a.h - b.h) <= tol
}
