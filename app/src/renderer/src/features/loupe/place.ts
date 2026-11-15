/**
 * Loupe geometry (pure, no React): when to zoom, where the callout goes, and the arrow between it and the target.
 * All rects are in the overlay window's coordinates.
 */
import type { Rect } from '../../core/lesson'

/** A target smaller than this (pt, its larger side) gets the loupe without asking (Michael: the ▷ Run button is ~22 pt). */
export const ZOOM_UNDER = 32
/** How much bigger the drawn target is in the callout (Michael: 2-2.5x). */
export const SCALE = 2.25
/** The drawn ring never gets smaller than this, so a 12 pt target still reads. */
export const RING_MIN = 56
/** Callout padding around the ring, the gap to the target along the diagonal, and the margin to the work area's edge. */
export const PAD = 14
export const GAP = 36
export const EDGE = 16

export type Point = { x: number; y: number }

/** zoom: true from the engine (an additive spotlight field), or a tiny target. */
export function wantsZoom(rect: Rect, zoom: unknown): boolean {
  return zoom === true || Math.max(rect.w, rect.h) < ZOOM_UNDER
}

/** The glyph to show on the callout's keycap: a play/run symbol from the caption, else a short `code` span, else none. */
export function glyphFrom(caption: string | undefined): string | undefined {
  if (!caption) return undefined
  const sym = caption.match(/[▷▶►▸⏵⏯⟳↻⊕⋯⚙]/u)
  if (sym) return sym[0]
  const code = caption.match(/`([^`\s]{1,3})`/)
  return code ? code[1] : undefined
}

/** The ring's size in the callout: the target scaled up, at least RING_MIN on each side. */
export function ringSize(rect: Rect): { w: number; h: number } {
  return { w: Math.max(RING_MIN, Math.round(rect.w * SCALE)), h: Math.max(RING_MIN, Math.round(rect.h * SCALE)) }
}

/**
 * The callout: diagonal from the target, toward the middle of the work area (the Run button sits top-right, so the
 * callout lands below-left of it), clamped inside the work area.
 */
export function placeCallout(target: Rect, size: { w: number; h: number }, bounds: Rect): Rect {
  const cx = target.x + target.w / 2
  const cy = target.y + target.h / 2
  const dx = cx > bounds.x + bounds.w / 2 ? -1 : 1
  const dy = cy > bounds.y + bounds.h / 2 ? -1 : 1
  const x = cx + dx * (target.w / 2 + GAP + size.w / 2) - size.w / 2
  const y = cy + dy * (target.h / 2 + GAP + size.h / 2) - size.h / 2
  const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v))
  return {
    x: clamp(x, bounds.x + EDGE, bounds.x + bounds.w - size.w - EDGE),
    y: clamp(y, bounds.y + EDGE, bounds.y + bounds.h - size.h - EDGE),
    w: size.w,
    h: size.h
  }
}

/** Where the segment from r's center toward p leaves r. */
function exitPoint(r: Rect, p: Point): Point {
  const cx = r.x + r.w / 2
  const cy = r.y + r.h / 2
  const vx = p.x - cx
  const vy = p.y - cy
  if (!vx && !vy) return { x: cx, y: cy }
  const tx = vx ? r.w / 2 / Math.abs(vx) : Infinity
  const ty = vy ? r.h / 2 / Math.abs(vy) : Infinity
  const t = Math.min(tx, ty, 1)
  return { x: cx + vx * t, y: cy + vy * t }
}

/** The arrow: from the callout's edge to the target's edge, center to center, shortened by `inset` at both ends. */
export function arrow(callout: Rect, target: Rect, inset = 4): { from: Point; to: Point } | undefined {
  const c = { x: callout.x + callout.w / 2, y: callout.y + callout.h / 2 }
  const t = { x: target.x + target.w / 2, y: target.y + target.h / 2 }
  const a = exitPoint(callout, t)
  const b = exitPoint(target, c)
  const len = Math.hypot(b.x - a.x, b.y - a.y)
  if (len < inset * 2 + 8) return undefined // overlapping or touching: no room for an arrow
  const ux = (b.x - a.x) / len
  const uy = (b.y - a.y) / len
  return { from: { x: a.x + ux * inset, y: a.y + uy * inset }, to: { x: b.x - ux * inset, y: b.y - uy * inset } }
}
