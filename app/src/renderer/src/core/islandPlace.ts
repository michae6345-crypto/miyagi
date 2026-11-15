/**
 * Where a card-sized island goes so it never covers what the learner is working on (Michael's desktop test 3, item 3:
 * the "Not yet", setup and Explain cards sat top-centre over the editor's first lines, and the Hint / Show me box and
 * its caption were hidden under the "Not yet" card; test 4: the full off-track card covered lines 6-9 and the box on 8).
 *
 * The island stays at the notch unless an open card (not a hover peek) would overlap the spotlight's hole, the
 * coach's other targets, or the spotlight's caption and target labels (Michael's review A4: the caption has to stay
 * readable). Then it moves as little as it can to a spot clear of them (a gap's worth of air included): below the
 * hole, or beside it (next to the drawer, say), preferring spots that don't cover the overlay's other UI (drawer, bar,
 * player). If no spot is clear, the one that covers the least. Island.tsx springs it there (transform only) and back
 * to the notch when the card closes, so the card is still born from the notch and returns to it.
 *
 * The spot is decided as the card opens and then held (Michael's desktop test 5: the setup card stepped down off the
 * box between his look and his click, and the first Install missed). See useIslandOffset.
 *
 * Owner: core.
 */
import { useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react'
import type { Layout } from '../../../preload/api'
import { hole, intersects, isUsableRect, MIN_VISIBLE_SHARE, overlapShare, sameRect, toLocal } from '../features/spotlight/place'
import { useSpotlight } from '../features/spotlight/store'
import { useLesson, type Rect } from './lesson'

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
/** The spotlight's chips (its caption, the coach's target labels): its [data-ui] elements. */
const CHIPS = '[data-spotlight] [data-ui]'
/**
 * An opening card's spot may follow its first measurements (its real size, a first read of the chips) this long:
 * about its spring out of the notch, before it's anything to click. After that it holds still.
 */
const SETTLE_MS = 300
/** Holes within this many px of the ones a card was placed for are the same box (OCR jitter, a re-sent off-track). */
const SAME_BOX_PX = 12

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

type OverlayUi = { others: Rect[]; chips: Rect[] }
const NO_UI: OverlayUi = { others: NONE, chips: NONE }

/**
 * The overlay's UI around the island, window coordinates, read from the DOM every UI_EVERY_MS while `on` (the spotlight
 * is up, card or not), and once more the moment `fresh` changes (a card opens: it's placed around the chips as they
 * are in that very frame, the coach's target labels that came with it included):
 *   - others: everything marked data-hit / data-ui, minus the island itself and the spotlight scene;
 *   - chips: the spotlight's caption and target labels. The caption steps around the island and springs to its new
 *     spot, so a chip counts once it's at rest (the same in two reads in a row; the first read is taken as it is).
 */
function useOverlayUi(wrapper: RefObject<HTMLElement | null>, on: boolean, fresh: string): OverlayUi {
  const [ui, setUi] = useState<OverlayUi>(NO_UI)
  useLayoutEffect(() => {
    if (!on) return
    let lastOthers = ''
    let lastChips = ''
    let seenChips: string | undefined
    const read = (): void => {
      const mine = wrapper.current
      const root = mine?.parentElement // the overlay root
      if (!mine || !root) return
      const box = root.getBoundingClientRect()
      if (!box.width) return
      const k = root.offsetWidth / box.width // undo the browser stage's CSS scale (1 in Electron)
      const screen = root.offsetWidth * root.offsetHeight
      const local = (el: Element): Rect => {
        const r = el.getBoundingClientRect()
        return { x: Math.round((r.left - box.left) * k), y: Math.round((r.top - box.top) * k), w: Math.round(r.width * k), h: Math.round(r.height * k) }
      }
      const others = Array.from(root.querySelectorAll<HTMLElement>('[data-hit],[data-ui]'))
        .filter((el) => !mine.contains(el) && !el.closest('[data-spotlight]'))
        .map(local)
        .filter((r) => r.w > 1 && r.h > 1 && r.w * r.h < screen * HUGE_SHARE)
      const chips = Array.from(root.querySelectorAll<HTMLElement>(CHIPS))
        .map(local)
        .filter((r) => r.w > 1 && r.h > 1)
      const othersKey = JSON.stringify(others)
      const chipsKey = JSON.stringify(chips)
      const settled = seenChips === undefined || chipsKey === seenChips
      seenChips = chipsKey
      const nextOthers = othersKey !== lastOthers
      const nextChips = settled && chipsKey !== lastChips
      if (!nextOthers && !nextChips) return
      if (nextOthers) lastOthers = othersKey
      if (nextChips) lastChips = chipsKey
      setUi((u) => ({ others: nextOthers ? others : u.others, chips: nextChips ? chips : u.chips }))
    }
    read()
    const id = setInterval(read, UI_EVERY_MS)
    return () => {
      clearInterval(id)
      setUi(NO_UI)
    }
  }, [wrapper, on, fresh])
  return on ? ui : NO_UI
}

const sameBoxes = (a: Rect[], b: Rect[]): boolean => a.length === b.length && a.every((r, i) => sameRect(r, b[i], SAME_BOX_PX))

/** Where the open card sits: its mode, the holes it was placed for, its offset, and until when it may still settle. */
type Spot = { id: string; boxes: Rect[]; at: Offset; until: number }

/**
 * The island's offset right now. `card`: the open card's mode and size (undefined for the pill or a hover peek: they
 * stay at the notch). `top`: the notch spot's top. `wrapper`: the island's positioning element (its parent is the
 * overlay root). `still`: the pointer is on the island or pressed it a moment ago (Island.tsx).
 *
 * A card's spot is decided as it opens, from the box, the coach's targets and the chips known then (chips not at rest
 * yet: their last place at rest), so the island springs from the notch straight to it. Its first SETTLE_MS may still
 * follow its real size. Then it holds still while it stays open: not for a chip that settles or moves (the caption
 * steps around the card, not the other way round), not when the card grows, not when the spotlight clears. Only a new
 * box (another target) places it again, and never while `still`: that waits until the pointer is off it. A card that
 * opens or replaces another under the pointer keeps the spot it's at.
 */
export function useIslandOffset(card: { id: string; w: number; h: number } | undefined, top: number, layout: Layout, wrapper: RefObject<HTMLElement | null>, still = false): Offset {
  const main = useSpotlight((s) => (s.target && isUsableRect(s.target.rect) ? s.target.rect : undefined))
  const others = useSpotlight((s) => s.targets)
  // The off-track's own targets, kept while the off-track stands: a spotlight clear wipes the spotlight's copy.
  const flagged = useLesson((s) => s.offtrack?.targets)
  // The holes as the spotlight draws them: the main one while it's on this display, and the coach's others with it.
  // The coach's targets count even with no spotlight up (Michael's desktop test 6/7, item 5: the "Not yet" card sat on
  // lines 40-48, the very lines it was talking about, because the step's box had cleared when it opened).
  const keepOff = useMemo(() => {
    const rects: Rect[] = []
    for (const r of [main, ...others.map((t) => t.rect), ...(flagged ?? []).map((t) => t?.rect)]) {
      if (isUsableRect(r) && !rects.some((k) => sameRect(k, r, SAME_BOX_PX))) rects.push(r)
    }
    if (!rects.length) return []
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    return rects.map((r) => hole(toLocal(r, layout.origin))).filter((h) => overlapShare(h, screen) >= MIN_VISIBLE_SHARE)
  }, [main, others, flagged, layout])
  const w = card?.w ?? 0
  const h = card?.h ?? 0
  const { others: avoid, chips } = useOverlayUi(wrapper, keepOff.length > 0, card?.id ?? '')

  const decide = (): Offset => {
    if (!card || !keepOff.length) return AT_NOTCH
    const notch = { x: (layout.width - w) / 2, y: top, w, h }
    const wa = layout.workArea
    const bounds = { x: wa.x + EDGE, y: top, w: wa.width - EDGE * 2, h: wa.y + wa.height - BAR_CLEARANCE - top }
    return placeIsland(notch, [...keepOff, ...chips], bounds, avoid)
  }
  const spot = useRef<Spot>(undefined)
  const prev = spot.current
  const now = Date.now()
  const fresh = (): Spot | undefined => card && { id: card.id, boxes: keepOff, at: decide(), until: now + SETTLE_MS }
  let next: Spot | undefined
  if (!card) next = undefined
  else if (!prev) next = still ? { id: card.id, boxes: keepOff, at: AT_NOTCH, until: 0 } : fresh() // grows out of the pill (opened under the pointer: stays put)
  else if (prev.id !== card.id) next = still ? { id: card.id, boxes: keepOff, at: prev.at, until: 0 } : fresh()
  else if (now < prev.until) next = { ...prev, boxes: keepOff, at: decide() } // still springing out: follow its real size
  else if (keepOff.length && !sameBoxes(keepOff, prev.boxes) && !still) next = fresh() // a new box
  else next = prev
  useLayoutEffect(() => {
    spot.current = next
  })
  return next?.at ?? AT_NOTCH
}
