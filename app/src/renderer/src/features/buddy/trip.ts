/**
 * Feature: buddy. The buddy's trips, pure (no React, no DOM): how it flies from the notch to what it points at, where
 * it sits when it gets there, and how fast it speaks. Checked offline in test/buddyMarks.test.ts.
 *
 * The buddy is a character, not a highlighter. Clicky's cursor is the model: it has a home, it travels to the thing
 * on an arc that takes longer the farther it goes, it swells a little mid-flight, it lands BESIDE the thing and says a
 * few words one letter at a time, and it goes home again. miyagi's own version of each: the home is the notch, the
 * traveler is the bonsai in a small black pod (a droplet of the island, so it reads on any app), the words are the
 * mark's label, and the thing gets a mint loop the tree draws once it has landed.
 */
import type { Point, Rect } from '../../core/geometry'
import { labelAt, type LabelSide } from './marks'

/**
 * The pod: an island-black capsule with the tree at one end and the words beside it, like the pill in the notch.
 *   h          its height, and its width when it has nothing to say
 *   tree       the tree's size inside it
 *   homeTree   the tree's size in the notch ear: the pod leaves and comes home at this scale, so the swap can't be seen
 *   textAt     where the words start, from the pod's tree end
 *   padEnd     room after the last letter
 */
export const POD = { h: 38, tree: 26, homeTree: 16, textAt: 36, padEnd: 14 } as const

/** The pod's width with words `textW` px wide (0: just the tree). */
export const podWidth = (textW: number): number => (textW > 0 ? POD.textAt + textW + POD.padEnd : POD.h)

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
export const FLIGHT = { base: 0.34, perPx: 1 / 1700, min: 0.46, max: 1.05, arc: 0.2, arcMax: 80, tilt: 11, swell: 0.1, grow: 0.42 } as const

/** 'out': from the notch to a mark. 'hop': from one mark to the next. 'home': back into the notch. */
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

/** The pod's scale in the notch: its tree is then the size of the ear's. */
export const HOME_SCALE = POD.homeTree / POD.tree

/**
 * Its scale at `t`: up to full size over the first part of a flight out, down to the ear's size over the last part
 * of the flight home, a little swell mid-flight. `start`: the scale it had when the flight began (a flight that was
 * turned round mid-air starts from wherever it had got to); the default is the ear's size leaving home and full size
 * otherwise.
 */
export function scaleAt(f: Flight, t: number, start: number = f.kind === 'out' ? HOME_SCALE : 1): number {
  const k = clamp(t, 0, 1)
  const swell = FLIGHT.swell * Math.sin(Math.PI * k)
  if (f.kind === 'home') return start - (start - HOME_SCALE) * smooth(clamp((k - (1 - FLIGHT.grow)) / FLIGHT.grow, 0, 1)) + swell * (1 - k)
  return start + (1 - start) * smooth(clamp(k / FLIGHT.grow, 0, 1)) + swell
}

/** How far from the loop the pod sits. */
export const PERCH_GAP = 8

/**
 * Where the pod sits for a mark: beside its loop, to the right on the circled line when it fits, else below, else to
 * the left, else above (marks.ts labelAt). `tree` is the center of the tree, the point everything else is placed from.
 * To the left of the loop the pod is mirrored: the tree is at its right end, next to the thing, and the words run off
 * to the left of it.
 */
export function perch(ring: Rect, textW: number, bounds: Rect): { tree: Point; side: LabelSide; mirrored: boolean; w: number } {
  const w = podWidth(textW)
  const at = labelAt(ring, { w, h: POD.h }, bounds, 'right')
  const mirrored = at.side === 'left'
  return { tree: { x: mirrored ? at.x + w - POD.h / 2 : at.x + POD.h / 2, y: at.y + POD.h / 2 }, side: at.side, mirrored, w }
}

/** Which way the tree leans at its perch, -1 (left) to 1 (right): toward the thing it is pointing at. */
export function leanToward(tree: Point, ring: Rect): number {
  return clamp((ring.x + ring.w / 2 - tree.x) / 40, -1, 1)
}

/** It says its words one letter at a time, this many ms apart, starting this long after it lands. */
export const SPEECH = { letterMs: 34, afterMs: 140 } as const

/** How many letters of `length` it has said `ms` after landing. */
export function said(ms: number, length: number): number {
  return clamp(Math.floor((ms - SPEECH.afterMs) / SPEECH.letterMs) + 1, 0, length)
}

/** The pointer within this many px of the tree: the buddy turns to look at it. */
export const NOTICE_PX = 130
