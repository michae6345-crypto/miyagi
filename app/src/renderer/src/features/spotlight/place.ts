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
export const CAPTION_GAP = 8
export const EDGE_MARGIN = 16
export const CAPTION_TOP_OFFSET = 21
/** How far the caption may slide along the hole to get clear of other UI before it settles for covering a little of it. */
export const MAX_SLIDE = 160

/**
 * Contract (shared/contracts/events.ts): rects are screen POINTS, top-left origin (Electron
 * convention), relative to the PRIMARY display's FULL frame (y = 0 is the very top, menu bar
 * included). The overlay window sits at `origin` in that same space (its bounds are the display's
 * full frame), so local = screen − origin: the identity on the primary display. A display left of /
 * above the primary has a negative origin; that just works if the engine ever watches more than one.
 */
export function toLocal(r: Rect, origin: Point): Rect {
  return { x: r.x - origin.x, y: r.y - origin.y, w: r.w, h: r.h }
}

/** A rect we can point at: finite numbers and a real size (the engine can send an empty or zero box). */
export function isUsableRect(r: Partial<Rect> | undefined | null): r is Rect {
  return !!r && [r.x, r.y, r.w, r.h].every((v) => typeof v === 'number' && Number.isFinite(v)) && r.w! > 0 && r.h! > 0
}

/** Below this share of the hole on screen it isn't worth a dim: say it on the pill instead. */
export const MIN_VISIBLE_SHARE = 0.25

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

type Placed = Point & { side: Side }

/**
 * Where the caption goes, in window coordinates. `target` is the hole, `bounds` the usable area
 * (the work area: no menu bar, dock or taskbar), `avoid` our other overlay UI (shortcut bar, pill, cards).
 *   1. right of the hole, top-aligned with its first line (FRONTEND-HANDOFF → Placement)
 *   2. flipped to the left when the right side would run off-screen
 *   3. below / above the hole when it's too wide for either side (a full-width terminal)
 *   4. last resort: inside the hole's top-right corner
 * Always clamped so it stays fully on screen (top and bottom edges included). Other UI it must not
 * cover (`avoid`, ignored where it overlaps the target itself):
 *   - the first of 1–3 whose spot is free wins;
 *   - else the free spot nearest to one of them, sliding it along its edge of the hole (≤ MAX_SLIDE);
 *   - else (nothing free nearby) the one that covers the least, so it stays next to the target.
 */
export function placeCaption(target: Rect, size: { w: number; h: number }, bounds: Rect, avoid: Rect[] = []): Placed {
  const left = bounds.x + EDGE_MARGIN
  const top = bounds.y + EDGE_MARGIN
  const right = bounds.x + bounds.w - EDGE_MARGIN
  const bottom = bounds.y + bounds.h - EDGE_MARGIN
  const sideY = clamp(target.y + Math.min(CAPTION_TOP_OFFSET, target.h / 4), top, bottom - size.h)
  const alongX = clamp(target.x, left, right - size.w)

  const rx = target.x + target.w + CAPTION_GAP
  const lx = target.x - CAPTION_GAP - size.w
  const by = target.y + target.h + CAPTION_GAP / 2
  const ay = target.y - CAPTION_GAP / 2 - size.h
  const inside: Placed = {
    x: clamp(target.x + target.w - size.w - 12, left, right - size.w),
    y: clamp(target.y + 12, top, bottom - size.h),
    side: 'inside'
  }
  const candidates: Array<Placed | false> = [
    rx + size.w <= right && { x: rx, y: sideY, side: 'right' },
    lx >= left && { x: lx, y: sideY, side: 'left' },
    by + size.h <= bottom && { x: alongX, y: by, side: 'below' },
    ay >= top && { x: alongX, y: ay, side: 'above' }
  ]
  const fitting = candidates.filter((p): p is Placed => !!p)
  // Covering the target is worse than nudging away from other UI, so `inside` is only for "nothing fits".
  if (!fitting.length) return inside

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

function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

function grow(r: Rect, by: number): Rect {
  return { x: r.x - by, y: r.y - by, w: r.w + by * 2, h: r.h + by * 2 }
}

/** Share of `a`'s area that lies inside `b` (0–1). */
export function overlapShare(a: Rect, b: Rect): number {
  return a.w * a.h > 0 ? overlapArea(a, b) / (a.w * a.h) : 0
}

/** OCR jitter: the engine re-reads the screen every ~2s and boxes wobble by a point or two. */
export function sameRect(a: Rect, b: Rect, tol = 2): boolean {
  return Math.abs(a.x - b.x) <= tol && Math.abs(a.y - b.y) <= tol && Math.abs(a.w - b.w) <= tol && Math.abs(a.h - b.h) <= tol
}
