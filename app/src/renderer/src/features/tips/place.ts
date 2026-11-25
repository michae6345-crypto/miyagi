/**
 * Feature: tips. Where a coach mark goes: next to its element, never over it.
 *
 *   below / above  centred on the target, GAP under (or over) the thing to avoid; the caret points up (or down) at the
 *                  target's centre
 *   left           beside the thing to avoid (the lesson panel), level with the target's middle; the caret points right.
 *                  No room on the left (a panel docked on the left edge): the right side instead.
 * Then clamped inside the overlay with EDGE to spare; the caret stays on the target as the box slides, inside the corners.
 */
export type Rect = { x: number; y: number; w: number; h: number }
export type CaretSide = 'top' | 'bottom' | 'left' | 'right'
export type Placement = { x: number; y: number; caret: CaretSide; caretAt: number }

/** Air between the mark and what it points at. */
export const GAP = 12
/** Kept clear at the overlay's edges. */
const EDGE = 8
/** The caret never comes closer than this to a corner of the mark (its radius plus a little). */
const CARET_INSET = 22

const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v))

export function place(side: 'below' | 'above' | 'left', target: Rect, avoid: Rect, size: { w: number; h: number }, bounds: { w: number; h: number }): Placement {
  const cx = target.x + target.w / 2
  const cy = target.y + target.h / 2
  if (side === 'below' || side === 'above') {
    const x = clamp(cx - size.w / 2, EDGE, bounds.w - size.w - EDGE)
    const below = side === 'below'
    const y = below ? avoid.y + avoid.h + GAP : avoid.y - GAP - size.h
    return { x, y: clamp(y, EDGE, bounds.h - size.h - EDGE), caret: below ? 'top' : 'bottom', caretAt: clamp(cx - x, CARET_INSET, size.w - CARET_INSET) }
  }
  const leftX = avoid.x - GAP - size.w
  const onLeft = leftX >= EDGE
  const x = onLeft ? leftX : clamp(avoid.x + avoid.w + GAP, EDGE, bounds.w - size.w - EDGE)
  const y = clamp(cy - size.h / 2, EDGE, bounds.h - size.h - EDGE)
  return { x, y, caret: onLeft ? 'right' : 'left', caretAt: clamp(cy - y, CARET_INSET, size.h - CARET_INSET) }
}

export const sameRect = (a: Rect | undefined, b: Rect | undefined, tol = 1): boolean =>
  !!a && !!b && Math.abs(a.x - b.x) <= tol && Math.abs(a.y - b.y) <= tol && Math.abs(a.w - b.w) <= tol && Math.abs(a.h - b.h) <= tol
