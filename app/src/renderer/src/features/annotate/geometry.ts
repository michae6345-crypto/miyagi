/**
 * Buddy draws: the pure geometry (no React, no DOM). Tested offline: `npx tsx --test src/renderer/src/features/annotate/geometry.test.ts`.
 *
 *   toOverlay / onOverlay   a mark's screen points (Electron's global space, the spotlight.rect space; another display
 *                           has its own offset, maybe negative) to this overlay window's own coordinates, and whether
 *                           enough of it is on the display this overlay covers
 *   islandAnchor            where the branch starts: the bottom middle of the island (or of the notch when it rests)
 *   ringFor                 the loose ellipse around a box, roomy enough that the box's corners sit inside it
 *   buddyPath               ONE stroke: a smooth branch out of the island that flows into a hand-drawn loop around the box.
 *                           A seeded wobble, so the same mark always draws the same line (a re-sent mark never jumps)
 *   labelSpot               where the optional label goes: beside the loop on its own line (the end of a line of text is
 *                           mostly empty), else under it, or over it near the screen bottom
 *   textSpot                where the on-screen coach's text box goes (Nov 24): right of the loop, else left, below, above;
 *                           never over the target or the loop, always 16 pt inside the display
 */

export type Pt = { x: number; y: number }
export type Rect = { x: number; y: number; w: number; h: number }
/** An ellipse: center and radii. */
export type Ring = { cx: number; cy: number; rx: number; ry: number }

/** FNV-1a, 32 bits: a stable seed from a mark's id. */
export function hashSeed(s: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

/** mulberry32: a tiny seeded random source in [0, 1). */
export function rng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const finite = (...v: number[]): boolean => v.every(Number.isFinite)

/** A box worth drawing: finite numbers and some size. */
export function isDrawable(r: Partial<Rect> | undefined | null): r is Rect {
  return !!r && finite(r.x as number, r.y as number, r.w as number, r.h as number) && (r.w as number) > 0 && (r.h as number) > 0
}

/** Screen points to this window: the overlay sits at `origin` in the same global space (a display left of the primary: negative x). */
export function toOverlay(r: Rect, origin: Pt): Rect {
  return { x: r.x - origin.x, y: r.y - origin.y, w: r.w, h: r.h }
}

/** At least this share of a mark must be on this display to draw it here (the rest is another display's). */
export const MIN_ON_SCREEN = 0.5

/** Enough of `local` (already in window coordinates) lies inside the window's `size`. */
export function onOverlay(local: Rect, size: { width: number; height: number }, min = MIN_ON_SCREEN): boolean {
  const w = Math.max(0, Math.min(local.x + local.w, size.width) - Math.max(local.x, 0))
  const h = Math.max(0, Math.min(local.y + local.h, size.height) - Math.max(local.y, 0))
  return (w * h) / (local.w * local.h) >= min
}

/**
 * The branch's root: the island's bottom middle, tucked 2 pt up under its edge so the stroke reads as growing out of it.
 * `box` is the island's current box in window coordinates (core useIslandBox); with no size yet, the notch (or the
 * window's top middle) at `restBottom`.
 */
export function islandAnchor(box: Rect | undefined, fallback: { centerX: number; restBottom: number }): Pt {
  if (box && isDrawable(box)) return { x: box.x + box.w / 2, y: box.y + box.h - 2 }
  return { x: fallback.centerX, y: fallback.restBottom - 2 }
}

/** Room around the box: at least this much, more for a wide one (a whole line of code). */
export const RING_PAD = { x: 12, xShare: 0.1, y: 8 } as const
/** The smallest loop: a tiny icon still gets a circle a finger could point at. */
export const RING_MIN = 18
/** A very wide, very flat box would need a tall ellipse to contain its corners; never taller than this many times its half height. */
const RY_CAP = 3.2

/** The loose ellipse around a box (window coordinates): wide enough with padding, tall enough that the corners sit inside. */
export function ringFor(r: Rect): Ring {
  const a = r.w / 2
  const b = r.h / 2
  const rx = Math.max(RING_MIN, a + Math.max(RING_PAD.x, a * RING_PAD.xShare))
  // The corner (a, b) is inside when (a/rx)^2 + (b/ry)^2 <= 1.
  const room = 1 - (a / rx) ** 2
  const corner = room > 0 ? b / Math.sqrt(room) : b * RY_CAP
  const ry = Math.max(RING_MIN, b + RING_PAD.y, Math.min(corner * 1.04, Math.max(b, RING_MIN) * RY_CAP))
  return { cx: r.x + a, cy: r.y + b, rx, ry }
}

/** The point on the ring facing `p` (the ellipse's own parameter angle, so it lands on the curve). */
export function ringAngleToward(ring: Ring, p: Pt): number {
  return Math.atan2((p.y - ring.cy) / ring.ry, (p.x - ring.cx) / ring.rx)
}

export const ringPoint = (ring: Ring, t: number, scale = 1): Pt => ({ x: ring.cx + ring.rx * scale * Math.cos(t), y: ring.cy + ring.ry * scale * Math.sin(t) })

/** How far past one full turn the loop keeps going, so its ends cross like a hand-drawn circle. */
export const OVERSHOOT = 0.12
/** Radius wobble, as a share of the radius (two slow waves), and how much wider the loop ends than it starts. */
export const WOBBLE = { a1: 0.035, a2: 0.02, drift: 0.07 } as const
const LOOP_SAMPLES = 40

/** The loop's points: one turn and a bit, a slow seeded wobble, ending a little outside where it started. */
export function loopPoints(ring: Ring, start: number, seed: number): Pt[] {
  const r = rng(seed)
  const p1 = r() * Math.PI * 2
  const p2 = r() * Math.PI * 2
  // Clockwise on screen (y down) for most marks, the other way for some: hands differ.
  const dir = r() < 0.75 ? 1 : -1
  const sweep = Math.PI * 2 * (1 + OVERSHOOT)
  const pts: Pt[] = []
  for (let i = 0; i <= LOOP_SAMPLES; i++) {
    const u = i / LOOP_SAMPLES
    const t = start + dir * sweep * u
    const k = 1 + WOBBLE.a1 * Math.sin(2 * t + p1) * u + WOBBLE.a2 * Math.sin(3 * t + p2) + WOBBLE.drift * u
    pts.push(ringPoint(ring, t, k))
  }
  // The very first point sits exactly on the ring (no wobble at u = 0 for a1; a2 is small): pin it, so the branch meets it.
  pts[0] = ringPoint(ring, start, 1 + WOBBLE.a2 * Math.sin(3 * start + p2))
  return pts
}

/**
 * The branch: a cubic that leaves the island straight down and arrives along the loop's own direction at `to`, so the
 * line flows into the circle without a corner (`heading`: the loop's first step). A small seeded bow keeps it a branch,
 * not a ruler line.
 */
/** The most the branch's last control point reaches back from the join along the loop's direction (pt). */
export const BRANCH_REACH = 90

export function branchControls(from: Pt, to: Pt, heading: Pt, seed: number): [Pt, Pt] {
  const r = rng(seed ^ 0x9e3779b9)
  const dx = to.x - from.x
  const dy = to.y - from.y
  const dist = Math.hypot(dx, dy)
  const drop = Math.max(28, Math.abs(dy) * 0.4)
  const c1 = { x: from.x + (r() - 0.5) * 0.08 * dist, y: from.y + drop }
  const hl = Math.hypot(heading.x, heading.y) || 1
  // A short reach: a long one pulls the curve past the join and back (a J hook over the text before the loop).
  const reach = Math.min(BRANCH_REACH, Math.max(24, dist * 0.25))
  const c2 = { x: to.x - (heading.x / hl) * reach, y: to.y - (heading.y / hl) * reach }
  return [c1, c2]
}

const f = (n: number): string => (Math.round(n * 10) / 10).toString()

/** Catmull-Rom through the points as cubic segments (no leading M). */
function smooth(pts: Pt[]): string {
  let d = ''
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[i + 2] ?? p2
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 }
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 }
    d += ` C${f(c1.x)} ${f(c1.y)} ${f(c2.x)} ${f(c2.y)} ${f(p2.x)} ${f(p2.y)}`
  }
  return d
}

const cubicAt = (a: Pt, b: Pt, c: Pt, d: Pt, t: number): Pt => {
  const m = 1 - t
  return {
    x: m * m * m * a.x + 3 * m * m * t * b.x + 3 * m * t * t * c.x + t * t * t * d.x,
    y: m * m * m * a.y + 3 * m * m * t * b.y + 3 * m * t * t * c.y + t * t * t * d.y
  }
}

const polyLength = (pts: Pt[]): number => pts.slice(1).reduce((s, p, i) => s + Math.hypot(p.x - pts[i].x, p.y - pts[i].y), 0)

export type BuddyPath = {
  /** The whole stroke: branch then loop, one path (it draws in as one line). */
  d: string
  /** The loop alone (reduced motion and a re-sent mark show this when the branch has already gone). */
  loop: string
  ring: Ring
  /** Where the branch meets the loop. */
  join: Pt
  /** The branch, sampled (island to join): what the coach's text box keeps clear of (textSpot). */
  branch: Pt[]
  branchLength: number
  loopLength: number
}

/** The buddy's stroke for one mark: `from` the island anchor, around `box` (both window coordinates). */
export function buddyPath(from: Pt, box: Rect, seed: number): BuddyPath {
  const ring = ringFor(box)
  const start = ringAngleToward(ring, from)
  const loop = loopPoints(ring, start, seed)
  const join = loop[0]
  const [c1, c2] = branchControls(from, join, { x: loop[1].x - join.x, y: loop[1].y - join.y }, seed)
  const branchPts = Array.from({ length: 25 }, (_, i) => cubicAt(from, c1, c2, join, i / 24))
  const loopD = smooth(loop)
  return {
    d: `M${f(from.x)} ${f(from.y)} C${f(c1.x)} ${f(c1.y)} ${f(c2.x)} ${f(c2.y)} ${f(join.x)} ${f(join.y)}${loopD}`,
    loop: `M${f(join.x)} ${f(join.y)}${loopD}`,
    ring,
    join,
    branch: branchPts,
    branchLength: polyLength(branchPts),
    loopLength: polyLength(loop)
  }
}

/** Draw time (seconds): about 1.6 pt per ms of line, never quicker than 0.55 s or slower than 1.2 s. */
export function drawSeconds(length: number): number {
  return Math.min(1.2, Math.max(0.55, 0.35 + length / 1600))
}

/** Label: this far from the loop; kept this far from the window's edges. */
export const LABEL_GAP = 8
export const LABEL_EDGE = 12
/** A label is one short line; this is the room it is given for the flip decision. */
export const LABEL_H = 22
/** A rough label width for the fit decision: the small type is about this wide per character, plus its padding. */
export const LABEL_CHAR_W = 7
export const LABEL_PAD_W = 16

export const labelWidth = (text: string): number => text.length * LABEL_CHAR_W + LABEL_PAD_W

/**
 * Where the label goes. `x` is its anchor and `align` says which edge sits there (start: left edge, end: right edge,
 * center: middle); `y` is its top. Beside the loop first, centered on the circled line: right of it, else left of it.
 * The label is opaque and data-ui (so the engine's screen reader never reads miyagi's own words as the learner's
 * screen), so it should cover as little of the learner's text as it can; past the end of the circled line is mostly
 * empty. When neither side fits: under the loop, or over it near the bottom.
 */
export function labelSpot(ring: Ring, size: { width: number; height: number }, width = labelWidth('xxxxxxxxxx')): Pt & { above: boolean; align: 'start' | 'center' | 'end' } {
  const mid = Math.min(size.height - LABEL_EDGE - LABEL_H, Math.max(LABEL_EDGE, ring.cy - LABEL_H / 2))
  // A loop that runs off one edge still puts its label on screen (clamped in toward that edge).
  const right = Math.max(LABEL_EDGE, ring.cx + ring.rx + LABEL_GAP)
  if (right + width <= size.width - LABEL_EDGE) return { x: right, y: mid, above: false, align: 'start' }
  const left = Math.min(size.width - LABEL_EDGE, ring.cx - ring.rx - LABEL_GAP)
  if (left - width >= LABEL_EDGE) return { x: left, y: mid, above: false, align: 'end' }
  const below = ring.cy + ring.ry + LABEL_GAP
  const above = below + LABEL_H > size.height - LABEL_EDGE
  const y = above ? ring.cy - ring.ry - LABEL_GAP - LABEL_H : below
  const half = width / 2
  return { x: Math.min(size.width - LABEL_EDGE - half, Math.max(LABEL_EDGE + half, ring.cx)), y: Math.max(LABEL_EDGE, y), above, align: 'center' }
}

// ---------------------------------------------------------------------------------------------------------------
// On-screen coach (Nov 24): the step's action written beside the loop.
// ---------------------------------------------------------------------------------------------------------------

/** The text box keeps this far inside the display's edges. */
export const TEXT_EDGE = 16
/** The text box is at most this wide (it wraps to 2 lines inside it). */
export const TEXT_MAX_W = 280
/** The text box keeps this far from the buddy's line (pt), so the line never runs under the words. */
export const BRANCH_CLEAR = 10
/** Sliding a box along the loop to clear the line: this step (pt). */
const SLIDE_STEP = 8

export type Side = 'right' | 'left' | 'below' | 'above'
export type TextSpot = Pt & { side: Side; fits: boolean }

const overlap = (a: Rect, b: Rect): number =>
  Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y))

/** The ring's bounding box. */
export const ringBox = (ring: Ring): Rect => ({ x: ring.cx - ring.rx, y: ring.cy - ring.ry, w: ring.rx * 2, h: ring.ry * 2 })

const clamp = (v: number, lo: number, hi: number): number => (hi < lo ? lo : Math.min(hi, Math.max(lo, v)))

/** Does the segment a-b cross the rect (Liang-Barsky clipping)? */
export function segmentHitsRect(a: Pt, b: Pt, r: Rect): boolean {
  const dx = b.x - a.x
  const dy = b.y - a.y
  let t0 = 0
  let t1 = 1
  const edges: [number, number][] = [
    [-dx, a.x - r.x],
    [dx, r.x + r.w - a.x],
    [-dy, a.y - r.y],
    [dy, r.y + r.h - a.y]
  ]
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return false
      continue
    }
    const t = q / p
    if (p < 0) t0 = Math.max(t0, t)
    else t1 = Math.min(t1, t)
    if (t0 > t1) return false
  }
  return true
}

/** Does the polyline come within `pad` of the rect? */
export function lineHitsRect(line: readonly Pt[], r: Rect, pad = 0): boolean {
  const g = { x: r.x - pad, y: r.y - pad, w: r.w + pad * 2, h: r.h + pad * 2 }
  for (let i = 0; i < line.length - 1; i++) if (segmentHitsRect(line[i], line[i + 1], g)) return true
  return line.length === 1 && segmentHitsRect(line[0], line[0], g)
}

/**
 * Where the coach's text box goes (its top-left, window coordinates). `ring`: the loop; `target`: the circled box; `size`:
 * the display; `box`: the text box's size; `branch`: the buddy's line from the island to the loop (sampled), if drawn.
 *
 * Tries right of the loop (centered on its line), then left, below and above, LABEL_GAP from the loop. A side fits when
 * the box lies TEXT_EDGE inside the display without moving toward the loop. On a side the line crosses, the box slides
 * along the loop (the smallest slide first) until it is BRANCH_CLEAR off the line; a side with no clear slide yields to
 * the next, and if no side is clear of the line the first side that fits is used anyway.
 * When no side fits at all, each side is pushed inside the display and the one covering least of the loop wins among
 * those that leave the target uncovered (the box is data-ui: the engine's screen reader cannot see under it). Pure.
 */
export function textSpot(ring: Ring, target: Rect, size: { width: number; height: number }, box: { w: number; h: number }, branch?: readonly Pt[]): TextSpot {
  const rb = ringBox(ring)
  const { w, h } = box
  const loX = TEXT_EDGE
  const hiX = size.width - TEXT_EDGE - w
  const loY = TEXT_EDGE
  const hiY = size.height - TEXT_EDGE - h
  const midY = clamp(ring.cy - h / 2, loY, hiY)
  const midX = clamp(ring.cx - w / 2, loX, hiX)
  const raw: Record<Side, Pt> = {
    right: { x: rb.x + rb.w + LABEL_GAP, y: midY },
    left: { x: rb.x - LABEL_GAP - w, y: midY },
    below: { x: midX, y: rb.y + rb.h + LABEL_GAP },
    above: { x: midX, y: rb.y - LABEL_GAP - h }
  }
  const order: Side[] = ['right', 'left', 'below', 'above']
  const inside = (p: Pt): boolean => p.x >= loX && p.x <= hiX && p.y >= loY && p.y <= hiY
  const clear = (p: Pt): boolean => !branch || branch.length === 0 || !lineHitsRect(branch, { x: p.x, y: p.y, w, h }, BRANCH_CLEAR)
  let firstFit: TextSpot | undefined
  for (const side of order) {
    const p0 = raw[side]
    if (!inside(p0)) continue
    firstFit ??= { ...p0, side, fits: true }
    if (clear(p0)) return { ...p0, side, fits: true }
    // Slide along the loop's side (across it for left / right, along it for above / below), the smallest slide first.
    // Never so far that the words leave their loop: about the loop's half plus the box.
    const across = side === 'right' || side === 'left'
    const reach = across ? rb.h / 2 + h : rb.w / 2 + w
    for (let d = SLIDE_STEP; d <= reach; d += SLIDE_STEP) {
      for (const s of [d, -d]) {
        const p = across ? { x: p0.x, y: p0.y + s } : { x: p0.x + s, y: p0.y }
        if (inside(p) && clear(p)) return { ...p, side, fits: true }
      }
    }
  }
  if (firstFit) return firstFit
  // Nothing fits as is: push each side inside the display and keep the one covering least of the loop, target uncovered.
  let best: (TextSpot & { cost: number }) | undefined
  for (const side of order) {
    const p = { x: clamp(raw[side].x, loX, hiX), y: clamp(raw[side].y, loY, hiY) }
    const r = { x: p.x, y: p.y, w, h }
    // Covering the target costs far more than any loop overlap: only a target too big to avoid gets covered at all.
    const cost = overlap(r, target) * 1e6 + overlap(r, rb)
    if (!best || cost < best.cost) best = { ...p, side, fits: false, cost }
  }
  return { x: best!.x, y: best!.y, side: best!.side, fits: false }
}
