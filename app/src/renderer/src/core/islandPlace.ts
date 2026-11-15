/**
 * Where a card-sized island goes so it never covers what the learner is working on (Michael's desktop test 3, item 3:
 * the "Not yet", setup and Explain cards sat top-centre over the editor's first lines, and the Hint / Show me box and
 * its caption were hidden under the "Not yet" card; test 4: the full off-track card covered lines 6-9 and the box on 8).
 *
 * The island stays at the notch unless an open card (not a hover peek) would overlap the spotlight's hole or the
 * coach's other targets. Then it moves as little as it can to a spot clear of them (a gap's worth of air included):
 * below the hole, or beside it (next to the drawer, say), preferring spots that don't cover the overlay's other UI
 * (drawer, bar, player). If no spot is clear, the one that covers the least. Island.tsx springs it there (transform
 * only) and back to the notch when the card closes, so the card is still born from the notch and returns to it.
 *
 * Owner: core.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react'
import type { Layout } from '../../../preload/api'
import { hole, intersects, isUsableRect, MIN_VISIBLE_SHARE, overlapShare, toLocal } from '../features/spotlight/place'
import { useSpotlight } from '../features/spotlight/store'
import type { Rect } from './lesson'

type Offset = { x: number; y: number }
const AT_NOTCH: Offset = { x: 0, y: 0 }
const NONE: Rect[] = []

/** Air between a moved card and the hole, or other UI it sits next to. */
export const CARD_GAP = 16
/** Kept from the screen's side edges. */
const EDGE = 16
/** The shortcut bar (88) and its 24 px gap: a moved card stays above it. */
const BAR_CLEARANCE = 112
/** Cost of one px² of covered hole, relative to one px² of covered UI: covering the target is never worth it. */
const HOLE_COST = 1000
/** Cost of moving one px: a 300 px move weighs as much as covering about 4800 px² of other UI. */
const MOVE_COST = 16
/** Other UI read from the DOM this often (same pace as the spotlight caption's). */
const UI_EVERY_MS = 400
/** A layer bigger than this share of the screen (a dim, a full-screen hit area) isn't something to step around. */
const HUGE_SHARE = 0.5

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v))
const grow = (r: Rect, by: number): Rect => ({ x: r.x - by, y: r.y - by, w: r.w + by * 2, h: r.h + by * 2 })
function covered(a: Rect, list: Rect[]): number {
  let sum = 0
  for (const b of list) {
    const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
    const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
    if (w > 0 && h > 0) sum += w * h
  }
  return sum
}

/**
 * The card's offset from its notch spot (`card`, window coordinates). `keepOff`: the holes it must not cover.
 * `bounds`: where it may go (its top never rises above the notch). `avoid`: other UI it should rather not cover.
 * Candidates: the notch column / row, and every spot just below, right or left of a hole or beside other UI.
 */
export function placeIsland(card: Rect, keepOff: Rect[], bounds: Rect, avoid: Rect[] = []): Offset {
  if (!keepOff.some((k) => intersects(card, k))) return AT_NOTCH
  const xMax = Math.max(bounds.x, bounds.x + bounds.w - card.w)
  const yMax = Math.max(card.y, bounds.y + bounds.h - card.h)
  const sides = [...keepOff, ...avoid].flatMap((r) => [r.x + r.w + CARD_GAP, r.x - CARD_GAP - card.w])
  const xs = [card.x, ...sides].map((x) => clamp(x, bounds.x, xMax))
  const ys = [card.y, ...keepOff.map((k) => k.y + k.h + CARD_GAP)].map((y) => clamp(y, card.y, yMax))
  const air = keepOff.map((k) => grow(k, CARD_GAP))
  let best = AT_NOTCH
  let bestCost = Infinity
  for (const y of ys) {
    for (const x of xs) {
      const r = { x, y, w: card.w, h: card.h }
      const cost = covered(r, air) * HOLE_COST + covered(r, avoid) + Math.hypot(x - card.x, y - card.y) * MOVE_COST
      if (cost < bestCost) {
        bestCost = cost
        best = { x: Math.round(x - card.x), y: Math.round(y - card.y) }
      }
    }
  }
  return best
}

/**
 * The overlay's other UI (data-hit / data-ui), window coordinates, minus the island itself and the spotlight scene
 * (its caption already steps around the island: reading it back here would make the two chase each other).
 */
function useOtherUi(wrapper: RefObject<HTMLElement | null>, on: boolean): Rect[] {
  const [rects, setRects] = useState<Rect[]>([])
  useLayoutEffect(() => {
    if (!on) return
    let last = ''
    const read = (): void => {
      const mine = wrapper.current
      const root = mine?.parentElement // the overlay root
      if (!mine || !root) return
      const box = root.getBoundingClientRect()
      if (!box.width) return
      const k = root.offsetWidth / box.width // undo the browser stage's CSS scale (1 in Electron)
      const screen = root.offsetWidth * root.offsetHeight
      const next = Array.from(root.querySelectorAll<HTMLElement>('[data-hit],[data-ui]'))
        .filter((el) => !mine.contains(el) && !el.closest('[data-spotlight]'))
        .map((el) => el.getBoundingClientRect())
        .map((r) => ({ x: Math.round((r.left - box.left) * k), y: Math.round((r.top - box.top) * k), w: Math.round(r.width * k), h: Math.round(r.height * k) }))
        .filter((r) => r.w > 1 && r.h > 1 && r.w * r.h < screen * HUGE_SHARE)
      const key = JSON.stringify(next)
      if (key !== last) {
        last = key
        setRects(next)
      }
    }
    read()
    const id = setInterval(read, UI_EVERY_MS)
    return () => clearInterval(id)
  }, [wrapper, on])
  return on ? rects : NONE
}

/**
 * The island's offset right now. `card`: the open card's mode and size (undefined for the pill or a hover peek: they
 * stay at the notch). `top`: the notch spot's top. `wrapper`: the island's positioning element (its parent is the
 * overlay root). A card that moved stays put when the spotlight clears (no hole left to dodge: a card that jumps
 * while it's read is worse); it goes back to the notch when it closes, or when a new hole leaves the notch clear.
 */
export function useIslandOffset(card: { id: string; w: number; h: number } | undefined, top: number, layout: Layout, wrapper: RefObject<HTMLElement | null>): Offset {
  const main = useSpotlight((s) => (s.target && isUsableRect(s.target.rect) ? s.target.rect : undefined))
  const others = useSpotlight((s) => s.targets)
  // The holes as the spotlight draws them: the main one while it's on this display, and the coach's others with it.
  const keepOff = useMemo(() => {
    if (!main) return []
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    return [main, ...others.map((t) => t.rect)].map((r) => hole(toLocal(r, layout.origin))).filter((h) => overlapShare(h, screen) >= MIN_VISIBLE_SHARE)
  }, [main, others, layout])
  const w = card?.w ?? 0
  const h = card?.h ?? 0
  const notch = useMemo(() => ({ x: (layout.width - w) / 2, y: top, w, h }), [layout.width, top, w, h])
  const moving = !!card && keepOff.some((k) => intersects(notch, k))
  const avoid = useOtherUi(wrapper, moving)
  const placed = useMemo(() => {
    if (!moving) return AT_NOTCH
    const wa = layout.workArea
    const bounds = { x: wa.x + EDGE, y: top, w: wa.width - EDGE * 2, h: wa.y + wa.height - BAR_CLEARANCE - top }
    return placeIsland(notch, keepOff, bounds, avoid)
  }, [moving, notch, keepOff, layout.workArea, top, avoid])
  const stuck = useRef<{ id: string; at: Offset }>(undefined)
  const offset = card && !keepOff.length && stuck.current?.id === card.id ? stuck.current.at : placed
  useEffect(() => {
    stuck.current = card && (offset.x || offset.y) ? { id: card.id, at: offset } : undefined
  })
  return offset
}
