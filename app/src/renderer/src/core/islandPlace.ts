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
 * Avoid rects (Michael's desktop test 9, A3 / A4: the "Not yet" card and the step pill sat over VS Code's kernel
 * picker, top centre). The engine's `screen.avoid` says what is open on top of the learner's app and must stay visible
 * (a quick-pick: kernel picker, command palette, Select Interpreter). An open card steps out of it like out of a
 * spotlight box, and goes back to its own spot when it closes. The one
 * exception to "held once shown": a NEW avoid rect moves an open card (the learner opened that picker on purpose), but
 * never while the pointer is on it or just after a press. Nothing is guessed when the engine says nothing: the picker
 * opens top centre, right where every card and the pill are born, and a card moved off that spot for good would sit
 * over the editor's Run / Select Kernel buttons (top right) or the code itself (below).
 *
 * Owner: core.
 */
import { useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { create } from 'zustand'
import type { Layout } from '../../../preload/api'
import { useCards } from '../features/cards/store'
import { hole, intersects, isUsableRect, MIN_VISIBLE_SHARE, overlapShare, sameRect, toLocal } from '../features/spotlight/place'
import { useSpotlight } from '../features/spotlight/store'
import { onMessage, onUi } from './bus'
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

/**
 * Cards that keep the spot they opened at even when a new box arrives: the "Your lesson" sheet (Michael's test 8: it
 * opened top-centre, then jumped to the lower-left over the editor and terminal the moment VS Code finished opening).
 */
const HOLDS = new Set(['before-start'])

/**
 * The engine sends `screen.avoid` only when something changes ({rects: []} = closed). A close that never came is
 * dropped after this long (a picker is open a few seconds, not a minute).
 */
const AVOID_TTL_MS = 45_000
/** At most this many avoid rects are read from one message. */
const AVOID_MAX = 8

/**
 * `screen.avoid` (Michael, Sun 6:36 AM; additive, landing in shared/contracts/events.ts on integration/live):
 *   "screen.avoid": { rects: { kind: "quickpick"; x: number; y: number; w: number; h: number }[] }
 * Screen points, top-left origin, like spotlight.rect. Sent only when something changes; [] = the picker closed. Only
 * while a lesson is active; cleared on lesson.ended / reset too. Any kind is treated the same way.
 * TODO(contract): once adrian/shell's events.ts has "screen.avoid", drop AvoidEvent and the cast in onRaw below and
 * subscribe with onMessage('screen.avoid', ...) (common/wire.ts already lets the type through).
 * Browser stage: window.__miyagiAvoid([{ kind: 'quickpick', x: 456, y: 44, w: 600, h: 240 }]) opens one,
 * __miyagiAvoid([]) closes it; ?scenario=quickpick plays it on a "Not yet" card and the step pill.
 */
type AvoidEvent = { rects?: Array<{ kind?: string; x: number; y: number; w: number; h: number }> }
export const useAvoid = create<{ rects: Rect[] }>(() => ({ rects: NONE }))
let avoidTimer: ReturnType<typeof setTimeout> | undefined

function readAvoid(payload: unknown): Rect[] {
  const list = (payload as AvoidEvent | null | undefined)?.rects
  if (!Array.isArray(list)) return NONE
  const out: Rect[] = []
  for (const r of list.slice(0, AVOID_MAX)) {
    if (isUsableRect(r)) out.push({ x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.w), h: Math.round(r.h) })
  }
  return out
}

export function setAvoid(rects: Rect[]): void {
  clearTimeout(avoidTimer)
  if (rects.length) avoidTimer = setTimeout(() => setAvoid(NONE), AVOID_TTL_MS)
  const now = useAvoid.getState().rects
  if (now.length === rects.length && now.every((r, i) => sameRect(r, rects[i]))) return
  useAvoid.setState({ rects: rects.length ? rects : NONE })
}

/** onMessage for a type the contract on this branch doesn't have yet (see the TODO above). */
const onRaw = onMessage as unknown as (type: string, fn: (payload: unknown) => void) => () => void
onRaw('screen.avoid', (p) => setAvoid(readAvoid(p)))
onMessage('lesson.ended', () => setAvoid(NONE))
onUi('reset', () => void setAvoid(NONE))
if (typeof window !== 'undefined') {
  ;(window as unknown as { __miyagiAvoid?: (rects: unknown[]) => void }).__miyagiAvoid = (rects) => setAvoid(readAvoid({ rects }))
}

/** The avoid rects in window coordinates, the ones on this display. */
function useAvoidLocal(layout: Layout): Rect[] {
  const rects = useAvoid((s) => s.rects)
  return useMemo(() => {
    if (!rects.length) return NONE
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    return rects.map((r) => toLocal(r, layout.origin)).filter((r) => intersects(r, screen))
  }, [rects, layout])
}

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
/** An open card stepped out of avoid rects: the rects and holes it was placed for, and where (undefined: no need). */
type Aside = { id: string; clear: Rect[]; boxes: Rect[]; at?: Offset }

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
 *
 * The card's own targets (`card.targets`) count like the coach's, kept while the card is open: a spotlight clear or the
 * next step.started wipes the spotlight's copy (desktop test 9, A5: the step card sat on the code it talked about).
 *
 * Avoid rects (useAvoid: VS Code's quick-pick, desktop test 9, A3): a new one that overlaps the card's spot moves the
 * card out of it, even though the card is held, and when it closes the card goes back to its own spot. Held while the
 * same rects stand; never moved while `still` (it waits until the pointer is off it, then moves).
 */
export function useIslandOffset(card: { id: string; w: number; h: number } | undefined, top: number, layout: Layout, wrapper: RefObject<HTMLElement | null>, still = false): Offset {
  const main = useSpotlight((s) => (s.target && isUsableRect(s.target.rect) ? s.target.rect : undefined))
  const others = useSpotlight((s) => s.targets)
  // The off-track's own targets, kept while the off-track stands: a spotlight clear wipes the spotlight's copy.
  const flagged = useLesson((s) => s.offtrack?.targets)
  // The open card's own targets, the same way (desktop test 9, A5).
  const carded = useCards((s) => s.card?.targets)
  // The holes as the spotlight draws them: the main one while it's on this display, and the coach's others with it.
  // The coach's targets count even with no spotlight up (Michael's desktop test 6/7, item 5: the "Not yet" card sat on
  // lines 40-48, the very lines it was talking about, because the step's box had cleared when it opened).
  const keepOff = useMemo(() => {
    const rects: Rect[] = []
    for (const r of [main, ...others.map((t) => t.rect), ...(flagged ?? []).map((t) => t?.rect), ...(carded ?? []).map((t) => t?.rect)]) {
      if (isUsableRect(r) && !rects.some((k) => sameRect(k, r, SAME_BOX_PX))) rects.push(r)
    }
    if (!rects.length) return []
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    return rects.map((r) => hole(toLocal(r, layout.origin))).filter((h) => overlapShare(h, screen) >= MIN_VISIBLE_SHARE)
  }, [main, others, flagged, carded, layout])
  const clear = useAvoidLocal(layout)
  const w = card?.w ?? 0
  const h = card?.h ?? 0
  const { others: avoid, chips } = useOverlayUi(wrapper, keepOff.length > 0 || clear.length > 0, card?.id ?? '')

  const notch = { x: (layout.width - w) / 2, y: top, w, h }
  const wa = layout.workArea
  const bounds = { x: wa.x + EDGE, y: top, w: wa.width - EDGE * 2, h: wa.y + wa.height - BAR_CLEARANCE - top }
  const decide = (): Offset => {
    if (!card || !keepOff.length) return AT_NOTCH
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
  else if (keepOff.length && !sameBoxes(keepOff, prev.boxes) && !still && !HOLDS.has(card.id)) next = fresh() // a new box
  else next = prev
  const base = next?.at ?? AT_NOTCH

  // A3: out of what the engine says must stay visible (a quick-pick); back to `base` once it's gone. Any card, the
  // held "Your lesson" sheet too: a picker the learner opened on purpose wins.
  const aside = useRef<Aside>(undefined)
  const was = aside.current
  let nextAside: Aside | undefined
  if (!card) nextAside = undefined
  else if (still) nextAside = was && { ...was, id: card.id } // nothing moves under the pointer
  else if (!clear.length) nextAside = undefined // it closed: back to the card's own spot
  else if (was && was.id === card.id && sameBoxes(clear, was.clear) && sameBoxes(keepOff, was.boxes) && now >= (next?.until ?? 0)) nextAside = was
  else {
    const here = { x: notch.x + base.x, y: notch.y + base.y, w, h }
    const hit = clear.some((c) => intersects(here, grow(c, CARD_GAP)))
    nextAside = { id: card.id, clear, boxes: keepOff, at: hit ? placeIsland(notch, [...keepOff, ...chips, ...clear], bounds, avoid) : undefined }
  }
  useLayoutEffect(() => {
    spot.current = next
    aside.current = nextAside
  })
  return nextAside?.at ?? base
}
