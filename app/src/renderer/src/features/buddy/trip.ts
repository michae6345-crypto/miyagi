/**
 * Feature: buddy. The buddy's trips, pure (no React, no DOM): how it flies, where it sits beside what it points at,
 * where it hovers by the learner's pointer, and how fast it speaks. Checked offline in test/buddyMarks.test.ts.
 *
 * The buddy is a character, not a highlighter. Clicky's cursor is the model for how it moves: it has a home, it
 * keeps the learner's pointer company when it is called, it travels to the thing on an arc that takes longer the
 * farther it goes and swells a little mid-flight, it lands BESIDE the thing and says a few words one letter at a time,
 * and it goes home again. miyagi's own version of each: the home is the notch, the traveler is the buddy's own
 * character (Character.tsx), its words are in an island-black bubble beside it, and the thing gets a mint loop it
 * throws once it has landed.
 */
import type { Point, Rect } from '../../core/geometry'
import { labelAt, type LabelSide } from './marks'

/**
 * The buddy's body.
 *   size   its size on the screen (px)
 *   home   its scale in the notch: it pops out of the island from this small, and shrinks back to it
 *   gap    between it and its speech bubble
 */
export const BODY = { size: 54, home: 0.28, gap: 5 } as const

/** How wide the buddy and its bubble are together (a bubble 0 wide: just the buddy). */
export const spanWidth = (bubbleW: number): number => BODY.size + (bubbleW > 0 ? BODY.gap + bubbleW : 0)

/**
 * A flight.
 *   seconds    base + distance / speed, kept between min and max: a hop next door is quick, a trip across the screen
 *              takes a second
 *   arc        the path bows off the straight line by this share of the distance, never more than arcMax px
 *   tilt       it leans into the way it is going, this many degrees at most, mid-flight
 *   swell      and is this much bigger mid-flight
 *   grow       leaving home it reaches full size over this first share of the flight (and shrinks over the last
 *              share coming home)
 */
export const FLIGHT = { base: 0.34, perPx: 1 / 1700, min: 0.46, max: 1.05, arc: 0.2, arcMax: 80, tilt: 12, swell: 0.1, grow: 0.42 } as const

/** 'out': from the notch. 'hop': from one place on the screen to another. 'home': back into the notch. */
export type Flight = { from: Point; ctrl: Point; to: Point; seconds: number; kind: 'out' | 'hop' | 'home' }

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v))
const smooth = (k: number): number => k * k * (3 - 2 * k)

/**
 * The path from `from` to `to`: a quadratic curve bowed toward the top of the screen (sideways when the two are one
 * above the other), kept at least `top` + 8 px down so it never leaves the display.
 */
export function flight(from: Point, to: Point, kind: Flight['kind'], top = 0): Flight {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const dist = Math.hypot(dx, dy)
  const arc = Math.min(dist * FLIGHT.arc, FLIGHT.arcMax)
  // The two normals of the line; take the one pointing up the screen (y is down), or to the right when it is level.
  let nx = dist > 0 ? -dy / dist : 0
  let ny = dist > 0 ? dx / dist : 0
  if (ny > 0 || (ny === 0 && nx < 0)) {
    nx = -nx
    ny = -ny
  }
  const ctrl = { x: (from.x + to.x) / 2 + nx * arc, y: Math.max(top + 8, (from.y + to.y) / 2 + ny * arc) }
  return { from, ctrl, to, seconds: clamp(FLIGHT.base + dist * FLIGHT.perPx, FLIGHT.min, FLIGHT.max), kind }
}

/** Where the buddy is at a share `t` of a flight. */
export function along(f: Flight, t: number): Point {
  const u = 1 - t
  return { x: u * u * f.from.x + 2 * u * t * f.ctrl.x + t * t * f.to.x, y: u * u * f.from.y + 2 * u * t * f.ctrl.y + t * t * f.to.y }
}

/** Its lean at `t`, degrees: into the way it is going, most in the middle, upright at both ends. */
export function tiltAt(f: Flight, t: number): number {
  const dx = f.to.x - f.from.x
  return clamp(dx / 240, -1, 1) * FLIGHT.tilt * Math.sin(Math.PI * clamp(t, 0, 1))
}

/**
 * Its scale at `t`: up to full size over the first part of a flight out, down to its home size over the last part
 * of the flight home, a little swell mid-flight. `start`: the scale it had when the flight began (a flight that was
 * turned round mid-air starts from wherever it had got to); the default is its home size leaving home and full size
 * otherwise.
 */
export function scaleAt(f: Flight, t: number, start: number = f.kind === 'out' ? BODY.home : 1): number {
  const k = clamp(t, 0, 1)
  const swell = FLIGHT.swell * Math.sin(Math.PI * k)
  if (f.kind === 'home') return start - (start - BODY.home) * smooth(clamp((k - (1 - FLIGHT.grow)) / FLIGHT.grow, 0, 1)) + swell * (1 - k)
  return start + (1 - start) * smooth(clamp(k / FLIGHT.grow, 0, 1)) + swell
}

/** Which way it looks on a flight, -1..1 each way: where it is going. */
export function gazeOf(f: Flight): Point {
  const dx = f.to.x - f.from.x
  const dy = f.to.y - f.from.y
  const d = Math.hypot(dx, dy) || 1
  return { x: dx / d, y: dy / d }
}

/**
 * Where the buddy sits for a mark: beside its loop, to the right on the circled line when it and its bubble fit,
 * else below, else to the left, else above (marks.ts labelAt). `body` is the buddy's center, the point everything
 * else is placed from. To the left of the loop it is mirrored: the buddy is next to the thing and its bubble runs
 * off to the left of it.
 */
export function perch(ring: Rect, bubble: { w: number; h: number }, bounds: Rect): { body: Point; side: LabelSide; mirrored: boolean; w: number } {
  const w = spanWidth(bubble.w)
  const h = Math.max(BODY.size, bubble.h)
  const at = labelAt(ring, { w, h }, bounds, 'right')
  const mirrored = at.side === 'left'
  return { body: { x: mirrored ? at.x + w - BODY.size / 2 : at.x + BODY.size / 2, y: at.y + h / 2 }, side: at.side, mirrored, w }
}

/** Which way it looks at its perch, -1..1 each way: at the thing it is pointing at. */
export function gazeAt(body: Point, ring: Rect): Point {
  return { x: clamp((ring.x + ring.w / 2 - body.x) / 60, -1, 1), y: clamp((ring.y + ring.h / 2 - body.y) / 60, -1, 1) }
}

/**
 * Keeping the learner company (Clicky's cursor does this): it hovers this far down and to the right of the pointer,
 * and catches up with it at this rate (per second: higher is tighter). Kept `edge` px inside the screen.
 */
export const FOLLOW = { dx: 30, dy: 30, rate: 9, edge: 30 } as const

/** Where it hovers for a pointer at `p`, kept on screen. */
export function beside(p: Point, bounds: Rect): Point {
  return {
    x: clamp(p.x + FOLLOW.dx, bounds.x + FOLLOW.edge, bounds.x + bounds.w - FOLLOW.edge),
    y: clamp(p.y + FOLLOW.dy, bounds.y + FOLLOW.edge, bounds.y + bounds.h - FOLLOW.edge)
  }
}

/** One step of catching up: from `at` toward `to` over `dt` seconds. Never overshoots; snaps when it is there. */
export function catchUp(at: Point, to: Point, dt: number): Point {
  const k = 1 - Math.exp(-FOLLOW.rate * Math.max(0, dt))
  const x = at.x + (to.x - at.x) * k
  const y = at.y + (to.y - at.y) * k
  return Math.hypot(to.x - x, to.y - y) < 0.3 ? to : { x, y }
}

/** It says its words one letter at a time, this many ms apart, starting this long after it lands. */
export const SPEECH = { letterMs: 30, afterMs: 140 } as const

/** How many letters of `length` it has said `ms` after it started. */
export function said(ms: number, length: number): number {
  return clamp(Math.floor((ms - SPEECH.afterMs) / SPEECH.letterMs) + 1, 0, length)
}

/** The pointer within this many px of the buddy: it turns to look at it. */
export const NOTICE_PX = 150

/** A sentence of its own is cut to this many characters (at a word), so the bubble stays a bubble. */
export const SAY_MAX = 96

/** The first sentence of `text`, without backticks, on one line, cut at a word to SAY_MAX. */
export function firstSentence(text: string): string {
  const flat = text.replace(/`/g, '').replace(/\s+/g, ' ').trim()
  const end = flat.search(/[.!?](\s|$)/)
  const one = end >= 0 ? flat.slice(0, end + 1) : flat
  if (one.length <= SAY_MAX) return one
  const cut = one.slice(0, SAY_MAX)
  return `${cut.slice(0, Math.max(cut.lastIndexOf(' '), SAY_MAX - 24)).replace(/[\s,;:]+$/, '')}…`
}
