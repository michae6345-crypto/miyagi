/**
 * Feature: circle. The pure geometry of circle to ask: ink points to a box, the box to a ScreenRegion (the contract's
 * screen-point space), the ink's SVG path, and where the answer card sits. No DOM, no store: tested offline
 * (test/circle.test.ts).
 *
 * Spaces:
 *   overlay px  what the layer draws in: the overlay window's own CSS px (Electron: 1 px = 1 screen point; the browser
 *               stage scales the whole desktop with CSS, so pointer client px are divided by that scale first).
 *   screen pts  the contract's ScreenRegion: overlay px + the window's origin (layout.origin), top-left origin, the
 *               primary display at 0,0 (the spotlight.rect space).
 */
import type { ScreenRegion } from '../../../../../../shared/contracts/events'

export type Pt = { x: number; y: number }
export type Box = { x: number; y: number; w: number; h: number }

/** Air around the ink, so a tight circle still takes in the edge of what it was drawn around. */
export const INK_PAD = 6
/** A box smaller than this on both sides is a click, not a circle. */
export const MIN_INK = 10
/** At most this many points in one hold (a minute of scribbling stays cheap to draw and to send). */
export const MAX_POINTS = 1500

/** The bounding box of every point, or undefined when there are none. */
export function bounds(points: readonly Pt[]): Box | undefined {
  if (!points.length) return undefined
  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  for (const p of points) {
    if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) continue
    if (p.x < x0) x0 = p.x
    if (p.y < y0) y0 = p.y
    if (p.x > x1) x1 = p.x
    if (p.y > y1) y1 = p.y
  }
  if (x0 === Infinity) return undefined
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
}

/** Keep a box inside an area (both in the same space). A box larger than the area becomes the area. */
export function clampBox(b: Box, area: Box): Box {
  const w = Math.min(b.w, area.w)
  const h = Math.min(b.h, area.h)
  const x = Math.min(Math.max(b.x, area.x), area.x + area.w - w)
  const y = Math.min(Math.max(b.y, area.y), area.y + area.h - h)
  return { x, y, w, h }
}

/**
 * The circled box of one hold's strokes, padded and kept on the overlay (width x height). Undefined when the ink is
 * too small to be a circle (a click, a dot): MIN_INK on both sides.
 */
export function strokeBox(strokes: readonly (readonly Pt[])[], width: number, height: number, pad = INK_PAD): Box | undefined {
  const b = bounds(strokes.flat())
  if (!b || (b.w < MIN_INK && b.h < MIN_INK)) return undefined
  return clampBox({ x: b.x - pad, y: b.y - pad, w: b.w + 2 * pad, h: b.h + 2 * pad }, { x: 0, y: 0, w: width, h: height })
}

/** A pointer's client px to overlay px. `k` = the overlay's layout width / its drawn width (1 in Electron). */
export const toOverlay = (clientX: number, clientY: number, rect: { left: number; top: number }, k: number): Pt => ({
  x: (clientX - rect.left) * k,
  y: (clientY - rect.top) * k
})

/**
 * An overlay box to the contract's ScreenRegion: whole screen points, the window's origin added. `scale` is the
 * display's pixels per point (window.devicePixelRatio in Electron), `displayId` Electron's Display.id (0 = unknown:
 * the engine takes the display under the region).
 */
export function toRegion(b: Box, origin: Pt, scale: number, displayId: number | undefined): ScreenRegion {
  const x = Math.floor(b.x + origin.x)
  const y = Math.floor(b.y + origin.y)
  // Round the far edges outward so the region never loses a sliver of what was circled.
  const w = Math.ceil(b.x + origin.x + b.w) - x
  const h = Math.ceil(b.y + origin.y + b.h) - y
  return { x, y, w: Math.max(1, w), h: Math.max(1, h), displayId: Number.isFinite(displayId) ? Number(displayId) : 0, scale: scale > 0 && Number.isFinite(scale) ? scale : 1 }
}

/** The ScreenRegion back to overlay px (the answer card's echo of it). */
export const fromRegion = (r: Pick<ScreenRegion, 'x' | 'y' | 'w' | 'h'>, origin: Pt): Box => ({ x: r.x - origin.x, y: r.y - origin.y, w: r.w, h: r.h })

/** Add a point to a stroke unless it is within `min` px of the last one (a still hand adds nothing). */
export function addPoint(stroke: readonly Pt[], p: Pt, min = 1.5): Pt[] {
  const last = stroke[stroke.length - 1]
  if (last && Math.hypot(p.x - last.x, p.y - last.y) < min) return stroke as Pt[]
  return [...stroke, { x: Math.round(p.x * 10) / 10, y: Math.round(p.y * 10) / 10 }]
}

const f = (n: number): string => (Math.round(n * 10) / 10).toString()

/**
 * A smooth SVG path through the points (quadratic curves through the midpoints, so a shaky hand reads as one calm
 * line). One point is a tiny dot, so a press shows where it landed.
 */
export function inkPath(points: readonly Pt[]): string {
  if (!points.length) return ''
  const [a] = points
  if (points.length === 1) return `M${f(a.x)} ${f(a.y)}l0.1 0`
  if (points.length === 2) return `M${f(a.x)} ${f(a.y)}L${f(points[1].x)} ${f(points[1].y)}`
  let d = `M${f(a.x)} ${f(a.y)}`
  for (let i = 1; i < points.length - 1; i++) {
    const p = points[i]
    const n = points[i + 1]
    d += `Q${f(p.x)} ${f(p.y)} ${f((p.x + n.x) / 2)} ${f((p.y + n.y) / 2)}`
  }
  const z = points[points.length - 1]
  return `${d}L${f(z.x)} ${f(z.y)}`
}

export type CardSide = 'right' | 'left' | 'below' | 'above'

/**
 * Where the answer card goes beside the circled box: the first side it fits on (right, left, below, above), its
 * cross axis centred on the box, then kept `margin` px inside the overlay. If no side fits, it overlaps the box but
 * still stays on screen.
 */
export function placeCard(box: Box, card: { w: number; h: number }, area: { w: number; h: number }, gap = 14, margin = 16): { x: number; y: number; side: CardSide } {
  const inner = { x: margin, y: margin, w: Math.max(0, area.w - 2 * margin), h: Math.max(0, area.h - 2 * margin) }
  const cx = box.x + box.w / 2 - card.w / 2
  const cy = box.y + box.h / 2 - card.h / 2
  const tries: { side: CardSide; x: number; y: number; fits: boolean }[] = [
    { side: 'right', x: box.x + box.w + gap, y: cy, fits: box.x + box.w + gap + card.w <= inner.x + inner.w },
    { side: 'left', x: box.x - gap - card.w, y: cy, fits: box.x - gap - card.w >= inner.x },
    { side: 'below', x: cx, y: box.y + box.h + gap, fits: box.y + box.h + gap + card.h <= inner.y + inner.h },
    { side: 'above', x: cx, y: box.y - gap - card.h, fits: box.y - gap - card.h >= inner.y }
  ]
  const pick = tries.find((t) => t.fits) ?? tries[0]
  const c = clampBox({ x: pick.x, y: pick.y, w: card.w, h: card.h }, inner)
  return { x: Math.round(c.x), y: Math.round(c.y), side: pick.side }
}

/** Where a card opened: its top and its side (placeCard's y and side). */
export type CardHold = { y: number; side: CardSide }

/**
 * The card's place while its text streams in: the side and the top it opened with (placeCard), so the words being read
 * never move as lines are added below them. Only the screen edge moves it (kept `margin` px inside, like placeCard).
 */
export function holdCard(box: Box, card: { w: number; h: number }, area: { w: number; h: number }, hold: CardHold, gap = 14, margin = 16): { x: number; y: number; side: CardSide } {
  const inner = { x: margin, y: margin, w: Math.max(0, area.w - 2 * margin), h: Math.max(0, area.h - 2 * margin) }
  const x = hold.side === 'right' ? box.x + box.w + gap : hold.side === 'left' ? box.x - gap - card.w : box.x + box.w / 2 - card.w / 2
  const c = clampBox({ x, y: hold.y, w: card.w, h: card.h }, inner)
  return { x: Math.round(c.x), y: Math.round(c.y), side: hold.side }
}

/**
 * The answer card's place for one render, and the hold to keep for the next (one per ask: AnswerCard keeps it for the
 * life of its key). A card that opened while its words streamed (`streaming`, once `measured`) keeps that side and top
 * through the rest of the stream AND the final card, so it never jumps when the answer ends; only the screen edge
 * moves it. A card that never streamed (the final card came first) is placed fresh each time (placeCard).
 */
export function cardPlace(box: Box, card: { w: number; h: number }, area: { w: number; h: number }, hold: CardHold | undefined, streaming: boolean, measured: boolean): { p: { x: number; y: number; side: CardSide }; hold: CardHold | undefined } {
  if (hold) return { p: holdCard(box, card, area, hold), hold }
  const p = placeCard(box, card, area)
  return { p, hold: streaming && measured ? { y: p.y, side: p.side } : undefined }
}

/** A hand-drawn loop around a box (the browser stage's hand, web.ts, and the tests): a slightly tilted ellipse that wobbles and overshoots its start. */
export function loopPoints(x: number, y: number, w: number, h: number, n = 48): Pt[] {
  const cx = x + w / 2
  const cy = y + h / 2
  const rx = w / 2 + 14
  const ry = h / 2 + 12
  const pts: Pt[] = []
  for (let i = 0; i <= n; i++) {
    const t = i / n
    const a = -1.9 + t * (Math.PI * 2 + 0.55) // a bit more than once round
    const wob = 1 + 0.035 * Math.sin(a * 3 + 0.7) + 0.02 * Math.sin(a * 7)
    const grow = 1 + 0.06 * t // the end drifts outward, like a real hand
    const px = cx + Math.cos(a) * rx * wob * grow
    const py = cy + Math.sin(a) * ry * wob * grow + Math.cos(a) * 6 // a small tilt
    pts.push({ x: px, y: py })
  }
  return pts
}
