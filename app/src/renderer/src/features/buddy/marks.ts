/**
 * Feature: buddy, pass 2: the pointing branch. Brief: app/agents/buddy.md
 *
 * Pure (no React, no DOM, no timers): the marks the engine asks for, and the shape the branch draws to reach one.
 *   validMarks / keyOf  which marks can be drawn, and how a mark is known again when the engine re-sends it
 *   mergeMarks          a new annotate replaces the drawn set; a known mark keeps its birth (it is not drawn again);
 *                       a mark that already faded this step stays gone
 *   holdFor / fadeAt    how long the marks stay, counted from the newest mark's birth
 *   createReach         "the learner went there"
 *   reach               ONE path: a branch out of the bonsai to the mark, then a loose loop around it
 *   forkFor             where a second mark's branch leaves the first one's, so two marks read as one forked branch
 *   labelAt             where a mark's short label sits
 * Checked offline in test/buddyMarks.test.ts.
 *
 * The mark rules (everything down to "the shape") are the same as Michael's features/annotate/marks.ts on
 * michael/app-buddy-draw, number for number: 3 marks, 4 words, 6 s (1.5 to 30), 12 px, 280 ms, 6 px. His engine is
 * written against those, so whichever layer draws, a mark lives and dies the same way. Change them together.
 *
 * What is borrowed from other pointing apps, in miyagi's own look: the travel is an arc and takes longer the farther
 * it goes (cursor buddies fly that way), the loop is drawn on rather than faded in and its end overlaps its start
 * (circle-to-search), and a short name sits beside the target (shared-cursor chips).
 */
import type { Point, Rect } from '../../core/geometry'
import { duration, ease } from '../../core/ui/motionTokens'

/**
 * One mark as the engine sends it: the contract's `Annotation` (event `annotate`, Michael, Nov 22, branch
 * claude/contract-circle-ask). A local mirror until that contract is on this branch; then use Payload<'annotate'>.
 * x / y / w / h are screen points, the spotlight.rect space.
 */
export type Mark = { id?: string; x: number; y: number; w: number; h: number; displayId?: number; label?: string; why: 'point' | 'answer'; askId?: string; stepId?: string }
export type AnnotatePayload = { marks: Mark[]; holdMs?: number } | { clear: true }

/**
 * A mark being drawn. `rect` stays in screen points (the layer maps it into its window). `born`: when it first
 * appeared (ms); a re-sent mark keeps it, so it is not drawn again and does not push the fade back.
 */
export type Shown = { key: string; id?: string; rect: Rect; displayId?: number; label?: string; why: Mark['why']; stepId?: string; askId?: string; born: number }
/** What a mark is remembered by (drawn now, or gone this step). */
export type Known = Pick<Shown, 'key' | 'id' | 'rect' | 'why'>

/** The buddy circles a few things, not a page. */
export const MAX_MARKS = 3
/** The contract's limit for a label. */
export const LABEL_WORDS = 4
/** How long marks stay (ms): the engine's holdMs kept between min and max, or `base` when it names none. */
export const HOLD = { base: 6000, min: 1500, max: 30_000 } as const
/** A key for a mark with no id: its box on a grid this coarse. */
export const KEY_GRID = 12
/** OCR moves a box a few points between reads: a mark with no id within this of a drawn (or gone) one is that mark. */
export const SAME_PX = 12
/**
 * "Went there": the pointer must rest inside a box this long, after coming in from outside. The box counts `pad`
 * bigger than it is, since the loop itself sits outside it.
 */
export const REACH = { restMs: 280, pad: 6 } as const

const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v))
const hasId = (m: { id?: unknown }): boolean => typeof m.id === 'string' && !!m.id

/** The first LABEL_WORDS words on one line, never literal backticks; nothing when there are no words. */
export function cleanLabel(label: unknown): string | undefined {
  if (typeof label !== 'string') return undefined
  const words = label.replace(/`/g, '').replace(/\s+/g, ' ').trim().split(' ').filter(Boolean).slice(0, LABEL_WORDS)
  return words.length ? words.join(' ') : undefined
}

/** A rect that can be drawn: real numbers and a real size. */
export function isDrawable(r: Partial<Rect> | undefined | null): r is Rect {
  return !!r && num(r.x) && num(r.y) && num(r.w) && num(r.h) && r.w > 0 && r.h > 0
}

/** How a mark is known: the engine's id, or (no id) its kind and its box on a coarse grid. */
export function keyOf(m: Pick<Mark, 'id' | 'x' | 'y' | 'w' | 'h' | 'why' | 'displayId'>): string {
  if (hasId(m)) return `id:${m.id}`
  const g = (n: number): number => Math.round(n / KEY_GRID)
  return `${m.why}:${m.displayId ?? 'p'}:${g(m.x)},${g(m.y)},${g(m.w)},${g(m.h)}`
}

/** The drawable marks of an annotate: a known kind, a real box, one per key, MAX_MARKS at most. */
export function validMarks(list: unknown): Mark[] {
  if (!Array.isArray(list)) return []
  const seen = new Set<string>()
  const out: Mark[] = []
  for (const m of list as Array<Mark | null>) {
    if (!m || typeof m !== 'object' || (m.why !== 'point' && m.why !== 'answer') || !isDrawable(m)) continue
    const k = keyOf(m)
    if (seen.has(k)) continue
    seen.add(k)
    out.push(m)
    if (out.length >= MAX_MARKS) break
  }
  return out
}

const near = (a: Rect, b: Rect): boolean => Math.abs(a.x - b.x) <= SAME_PX && Math.abs(a.y - b.y) <= SAME_PX && Math.abs(a.w - b.w) <= SAME_PX && Math.abs(a.h - b.h) <= SAME_PX

/** The key this mark already has among `pool`: its id, or (no id) a mark of the same kind at nearly the same box. */
export function knownKey(m: Mark, pool: Iterable<Known>): string | undefined {
  if (hasId(m)) return keyOf(m)
  for (const k of pool) if (!k.id && k.why === m.why && near(k.rect, m)) return k.key
  return undefined
}

/** The new drawn set: `incoming` replaces `prev`; a known mark keeps its key and birth (no redraw); a gone one is skipped. */
export function mergeMarks(prev: readonly Shown[], incoming: readonly Mark[], gone: Iterable<Known>, now: number): Shown[] {
  const goneList = [...gone]
  const goneKeys = new Set(goneList.map((g) => g.key))
  const out: Shown[] = []
  for (const m of incoming) {
    const id = hasId(m)
    if (goneKeys.has(keyOf(m)) || (!id && knownKey(m, goneList))) continue
    const was = prev.find((p) => p.key === (knownKey(m, prev) ?? keyOf(m)))
    if (was && out.includes(was)) continue
    const label = cleanLabel(m.label)
    out.push({
      key: was ? was.key : keyOf(m),
      ...(id ? { id: m.id } : {}),
      // A re-read a few points off keeps the drawn box, so the stroke does not twitch.
      rect: was && near(was.rect, m) ? was.rect : { x: m.x, y: m.y, w: m.w, h: m.h },
      ...(m.displayId !== undefined ? { displayId: m.displayId } : {}),
      ...(label ? { label } : {}),
      why: m.why,
      ...(m.stepId ? { stepId: m.stepId } : {}),
      ...(m.askId ? { askId: m.askId } : {}),
      born: was ? was.born : now
    })
  }
  return out
}

/** The engine's holdMs kept within reason; anything else is the default. */
export function holdFor(holdMs: unknown): number {
  return num(holdMs) && holdMs > 0 ? clamp(holdMs, HOLD.min, HOLD.max) : HOLD.base
}

/**
 * When the drawn set fades: the hold counts from the newest mark's birth. A re-sent mark keeps its birth, so an
 * engine that re-sends the same marks every few seconds does not push the fade back; only a new mark does.
 */
export function fadeAt(marks: readonly Pick<Shown, 'born'>[], holdMs: number): number | undefined {
  if (!marks.length) return undefined
  return Math.max(...marks.map((m) => m.born)) + holdMs
}

type Box = { key: string; rect: Rect }
const inBox = (r: Rect, p: Point, pad: number = REACH.pad): boolean => p.x >= r.x - pad && p.x <= r.x + r.w + pad && p.y >= r.y - pad && p.y <= r.y + r.h + pad

/**
 * Tracks the pointer against the drawn boxes (window coordinates). `move` returns the keys the learner reached: the
 * pointer was seen OUTSIDE the box first (so a cursor already resting where the mark appears does not send it away),
 * then stayed inside for REACH.restMs. `press` returns the keys a real click landed in (the browser stage, or a click
 * the overlay does get). In Electron the overlay is click-through and only gets forwarded mouse moves, so the move
 * rule stands in for the click there.
 */
export function createReach(): { move(p: Point, boxes: readonly Box[], now: number): string[]; press(p: Point, boxes: readonly Box[]): string[]; reset(): void } {
  const armed = new Set<string>()
  const since = new Map<string, number>()
  return {
    move(p, boxes, now) {
      const hit: string[] = []
      const live = new Set(boxes.map((b) => b.key))
      for (const k of [...armed]) if (!live.has(k)) armed.delete(k)
      for (const k of [...since.keys()]) if (!live.has(k)) since.delete(k)
      for (const b of boxes) {
        if (!inBox(b.rect, p)) {
          armed.add(b.key)
          since.delete(b.key)
          continue
        }
        if (!armed.has(b.key)) continue
        const at = since.get(b.key) ?? now
        since.set(b.key, at)
        if (now - at >= REACH.restMs) hit.push(b.key)
      }
      return hit
    },
    press(p, boxes) {
      return boxes.filter((b) => inBox(b.rect, p)).map((b) => b.key)
    },
    reset() {
      armed.clear()
      since.clear()
    }
  }
}

// ---- the shape -------------------------------------------------------------------------------------------------

/**
 * The loop around a mark.
 *   padX / padY  room between the target and the stroke. Above and below it grows with the target's height from 0:
 *                one line of code (about 18 tall) gets a loop that stays in that line's own leading, like the
 *                spotlight's hole, and does not strike through the lines around it.
 *   minW / minH  a one-word target still gets a loop you can see.
 *   wobble       how far from a perfect ring it strays, as a share of its radius. Only ever outward, and
 *   drift        the loop grows this much from start to end, so the end passes outside the start, not onto it.
 *                Both push out from the target, so the stroke never cuts its corners; together they stay small
 *                enough that a one-line loop still fits between the lines above and below.
 *   lead         the branch joins the loop this far past the point nearest the bonsai (a share of the loop's length,
 *                kept between leadPx), so it comes in along the loop and not straight at it.
 *   overlap      how far past a full turn the loop goes (same units, kept between overlapPx).
 */
export const RING = { padX: 9, padY: 7, minW: 40, minH: 20, wobble: 0.02, drift: 0.05, lead: 0.07, leadPx: [8, 40], overlap: 0.09, overlapPx: [12, 56], points: 64 } as const
/** How finely the loop's outline is measured before it is walked at an even pace. */
const STEPS = 240

/**
 * A long, flat target gets a squarer loop, so a line of code is not wrapped in a huge ellipse: the exponent goes from
 * 2 (an ellipse) to 4 by an aspect of 6, and on to 6 by 14 (a whole line), where the loop hugs the line's own box.
 */
function axes(r: Rect, within?: Rect): { n: number; a: number; b: number } {
  const aspect = Math.max(r.w / r.h, r.h / r.w)
  let n = 2 + 2 * clamp((aspect - 1.6) / 4.4, 0, 1) + 2 * clamp((aspect - 6) / 8, 0, 1)
  const k = Math.pow(2, 1 / n) // what a superellipse of exponent n needs to pass through the rect's corners
  const padY = clamp((r.h - 18) * 0.25, 0, RING.padY)
  let a = Math.max(RING.minW / 2, (r.w / 2) * k + RING.padX)
  let b = Math.max(RING.minH / 2, (r.h / 2) * k + padY)
  if (within) {
    // A mark by a screen edge (a menu, a sidebar row, the Dock): pull the loop in so it stays on screen, never
    // tighter than the target itself, and square it up until the target's corners are inside it again.
    const cx = r.x + r.w / 2
    const cy = r.y + r.h / 2
    const roomX = (Math.min(cx - within.x, within.x + within.w - cx) - EDGE) / GROWN
    const roomY = (Math.min(cy - within.y, within.y + within.h - cy) - EDGE) / GROWN
    const a2 = Math.min(a, Math.max(r.w / 2 + EDGE, roomX))
    const b2 = Math.min(b, Math.max(r.h / 2 + EDGE, roomY))
    if (a2 < a || b2 < b) {
      a = a2
      b = b2
      while (n < 12 && Math.pow(r.w / 2 / a, n) + Math.pow(r.h / 2 / b, n) > 1) n += 0.5
    }
  }
  return { n, a, b }
}
/** The stroke's own room at a screen edge (px), and the most the wobble and drift grow a loop past its box. */
const EDGE = 3
const GROWN = (1 + RING.drift) * (1 + RING.wobble * 3.2)

/**
 * The loop's own box: what the label sits beside, and what "is this mark on this display" tests. `within`: the
 * screen the loop must stay on (see reach).
 */
export function ringBox(r: Rect, within?: Rect): Rect {
  const { a, b } = axes(r, within)
  return { x: r.x + r.w / 2 - a, y: r.y + r.h / 2 - b, w: a * 2, h: b * 2 }
}

/** A steady 0..1 from a key, so one mark always gets the same wobble (a re-render never redraws it differently). */
function seedOf(key: string): number {
  let h = 2166136261
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619)
  return (h >>> 0) / 4294967296
}

const f = (v: number): string => String(Math.round(v * 10) / 10)
const DOWN: Point = { x: 0, y: 1 }

export type Reach = {
  /** The whole stroke, from the bonsai to the end of the loop. */
  d: string
  /** Its length in px (an estimate, good to a few percent). */
  length: number
  /** The share of the length that is the branch; the rest is the loop. */
  split: number
  ring: Rect
  /** Which way the loop turns: 1 clockwise on screen, -1 the other way. */
  turn: 1 | -1
  /** The branch's cubic: its start, two control points, and where it meets the loop. */
  curve: [Point, Point, Point, Point]
  /** Where the branch meets the loop, and where the loop ends. */
  join: Point
  tip: Point
}

const cubic = (c: Reach['curve'], t: number): Point => {
  const u = 1 - t
  return {
    x: u * u * u * c[0].x + 3 * u * u * t * c[1].x + 3 * u * t * t * c[2].x + t * t * t * c[3].x,
    y: u * u * u * c[0].y + 3 * u * u * t * c[1].y + 3 * u * t * t * c[2].y + t * t * t * c[3].y
  }
}

/**
 * The stroke for one mark. It leaves `from` (the bonsai) along `heading` (down, out of the notch), bends toward the
 * mark, meets the loop a little past its nearest point, already running along it, and goes once round with a little
 * to spare. One path, so it draws in one motion. `within`: the screen, in the same coordinates; a loop by its edge
 * is pulled in to stay on it.
 */
export function reach(from: Point, target: Rect, key = '', heading: Point = DOWN, within?: Rect): Reach {
  const { n, a, b } = axes(target, within)
  const cx = target.x + target.w / 2
  const cy = target.y + target.h / 2
  // Turn away from the bonsai: a mark to its right is circled clockwise, one to its left the other way.
  const turn: 1 | -1 = cx >= from.x ? 1 : -1
  const pow = (v: number): number => Math.sign(v) * Math.pow(Math.abs(v), 2 / n)
  const at = (th: number, k = 1): Point => ({ x: cx + a * k * pow(Math.cos(th)), y: cy + b * k * pow(Math.sin(th)) })

  // Measure the outline: its length up to each of STEPS angles, and the angle nearest the bonsai.
  const dth = (Math.PI * 2) / STEPS
  const s = [0]
  let nearest = 0
  let best = Infinity
  let prev = at(0)
  for (let i = 0; i < STEPS; i++) {
    const dist = Math.hypot(prev.x - from.x, prev.y - from.y)
    if (dist < best) {
      best = dist
      nearest = i
    }
    const next = at((i + 1) * dth)
    s.push(s[i] + Math.hypot(next.x - prev.x, next.y - prev.y))
    prev = next
  }
  const around = s[STEPS]
  /** The angle at a distance along the outline (any distance: it wraps). */
  const angleAt = (dist: number): number => {
    const v = ((dist % around) + around) % around
    let lo = 0
    let hi = STEPS
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1
      if (s[mid] <= v) lo = mid
      else hi = mid
    }
    const span = s[lo + 1] - s[lo]
    return (lo + (span > 0 ? (v - s[lo]) / span : 0)) * dth
  }

  // Walk it at an even pace, from a little past the nearest point, once round and a little more.
  const begin = s[nearest] + turn * clamp(around * RING.lead, RING.leadPx[0], RING.leadPx[1])
  const total = around + clamp(around * RING.overlap, RING.overlapPx[0], RING.overlapPx[1])
  const seed = seedOf(key)
  const p1 = seed * Math.PI * 2
  const p2 = ((seed * 7.13) % 1) * Math.PI * 2
  const pts: Point[] = []
  for (let i = 0; i <= RING.points; i++) {
    const t = i / RING.points
    const th = angleAt(begin + turn * total * t)
    pts.push(at(th, (1 + RING.drift * t) * (1 + RING.wobble * (1.6 + Math.sin(2 * th + p1) + 0.6 * Math.sin(3 * th + p2)))))
  }

  const join = pts[0]
  const step = Math.hypot(pts[1].x - join.x, pts[1].y - join.y) || 1
  const tan = { x: (pts[1].x - join.x) / step, y: (pts[1].y - join.y) / step }
  const dist = Math.hypot(join.x - from.x, join.y - from.y)
  const hl = Math.hypot(heading.x, heading.y) || 1
  const k1 = clamp(dist * 0.35, 24, 240)
  const k2 = clamp(dist * 0.22, 14, 120)
  const curve: Reach['curve'] = [from, { x: from.x + (heading.x / hl) * k1, y: from.y + (heading.y / hl) * k1 }, { x: join.x - tan.x * k2, y: join.y - tan.y * k2 }, join]

  let d = `M${f(from.x)} ${f(from.y)} C${f(curve[1].x)} ${f(curve[1].y)} ${f(curve[2].x)} ${f(curve[2].y)} ${f(join.x)} ${f(join.y)}`
  // The loop: a smooth curve through the points (Catmull-Rom as cubic segments). The point "before" the first one
  // continues the branch's direction, so the join has no corner.
  const before = { x: join.x - tan.x * step, y: join.y - tan.y * step }
  let ringLen = 0
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = i === 0 ? before : pts[i - 1]
    const a1 = pts[i]
    const a2 = pts[i + 1]
    const p3 = pts[i + 2] ?? a2
    d += ` C${f(a1.x + (a2.x - p0.x) / 6)} ${f(a1.y + (a2.y - p0.y) / 6)} ${f(a2.x - (p3.x - a1.x) / 6)} ${f(a2.y - (p3.y - a1.y) / 6)} ${f(a2.x)} ${f(a2.y)}`
    ringLen += Math.hypot(a2.x - a1.x, a2.y - a1.y)
  }

  // The branch's length: its cubic walked in 24 steps.
  let branchLen = 0
  let last = from
  for (let i = 1; i <= 24; i++) {
    const p = cubic(curve, i / 24)
    branchLen += Math.hypot(p.x - last.x, p.y - last.y)
    last = p
  }
  const length = branchLen + ringLen
  return { d, length, split: length > 0 ? branchLen / length : 0, ring: { x: cx - a, y: cy - b, w: a * 2, h: b * 2 }, turn, curve, join, tip: pts[pts.length - 1] }
}

/**
 * Two marks read as one branch that forks, not as two lines out of the notch. A fork leaves the first mark's branch
 * (the trunk) `back` of the way before the point nearest the new mark, so it peels off at a slant, and never from
 * the first `min` or the last part past `max` of the trunk.
 */
export const FORK = { min: 0.14, max: 0.72, back: 0.16 } as const

/**
 * Where a later mark's branch leaves the trunk: the point, the direction the trunk is heading there, and how far
 * along the trunk's branch that is (0 to 1). Undefined when the mark is nearest the trunk's very start: then it is
 * behind the trunk and gets its own branch from the bonsai.
 */
export function forkFor(trunk: Reach, target: Rect): { at: Point; heading: Point; t: number } | undefined {
  const cx = target.x + target.w / 2
  const cy = target.y + target.h / 2
  let nearest = FORK.min
  let best = Infinity
  for (let t = FORK.min; t <= FORK.max + 1e-9; t += 0.02) {
    const p = cubic(trunk.curve, t)
    const dist = Math.hypot(p.x - cx, p.y - cy)
    if (dist < best) {
      best = dist
      nearest = t
    }
  }
  if (nearest <= FORK.min + 1e-9) return undefined
  const t = Math.max(FORK.min, nearest - FORK.back)
  const at = cubic(trunk.curve, t)
  const ahead = cubic(trunk.curve, t + 0.01)
  return { at, heading: { x: ahead.x - at.x, y: ahead.y - at.y }, t }
}

// ---- timing ----------------------------------------------------------------------------------------------------

/** The draw: a line drawing itself (duration.draw) plus time for the distance, never slower than `max`. Marks start `stagger` apart. */
export const DRAW = { perPx: 1 / 2400, max: 1, stagger: 0.12, leave: duration.slow } as const

/** Seconds to draw a stroke of this length. */
export function drawTime(length: number): number {
  return Math.min(DRAW.max, duration.draw + Math.max(0, length) * DRAW.perPx)
}

/**
 * The share of a draw's time (0 to 1) at which this share of the stroke is drawn, on the house ease.out. A fork
 * starts when the trunk's stroke has reached it.
 */
export function timeToDraw(share: number): number {
  const [x1, y1, x2, y2] = ease.out
  const bez = (u: number, p1: number, p2: number): number => 3 * (1 - u) * (1 - u) * u * p1 + 3 * (1 - u) * u * u * p2 + u * u * u
  const want = clamp(share, 0, 1)
  let lo = 0
  let hi = 1
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2
    if (bez(mid, y1, y2) < want) lo = mid
    else hi = mid
  }
  return bez((lo + hi) / 2, x1, x2)
}

// ---- the label -------------------------------------------------------------------------------------------------

/** gap: between the loop and the label. edge: kept from the screen edges. under: how far below the loop's top a label on the bonsai's side starts. */
export const LABEL = { gap: 10, edge: 12, under: 4 } as const
export type LabelSide = 'right' | 'left' | 'below' | 'above'

/**
 * Where the label goes. The branch comes down from the notch on the bonsai's side and meets the loop near its top,
 * so the label takes, in order: the side away from the bonsai (`away`), below the loop, the bonsai's side but kept
 * under the loop's top edge, and above only when nothing else fits on screen. Always fully inside `bounds`.
 */
export function labelAt(ring: Rect, size: { w: number; h: number }, bounds: Rect, away: 'right' | 'left'): Point & { side: LabelSide } {
  const x0 = bounds.x + LABEL.edge
  const y0 = bounds.y + LABEL.edge
  const x1 = Math.max(x0, bounds.x + bounds.w - LABEL.edge - size.w)
  const y1 = Math.max(y0, bounds.y + bounds.h - LABEL.edge - size.h)
  const midY = ring.y + ring.h / 2 - size.h / 2
  const midX = ring.x + ring.w / 2 - size.w / 2
  const near: 'right' | 'left' = away === 'right' ? 'left' : 'right'
  const beside = (side: 'right' | 'left', y: number): Point => ({ x: side === 'right' ? ring.x + ring.w + LABEL.gap : ring.x - LABEL.gap - size.w, y: clamp(y, y0, y1) })
  const spots: Array<Point & { side: LabelSide }> = [
    { ...beside(away, midY), side: away },
    { x: clamp(midX, x0, x1), y: ring.y + ring.h + LABEL.gap, side: 'below' },
    { ...beside(near, Math.max(midY, ring.y + LABEL.under)), side: near },
    { x: clamp(midX, x0, x1), y: ring.y - LABEL.gap - size.h, side: 'above' }
  ]
  const fits = (p: Point): boolean => p.x >= x0 && p.x <= x1 && p.y >= y0 && p.y <= y1
  const spot = spots.find(fits) ?? spots[0]
  return { x: clamp(spot.x, x0, x1), y: clamp(spot.y, y0, y1), side: spot.side }
}
