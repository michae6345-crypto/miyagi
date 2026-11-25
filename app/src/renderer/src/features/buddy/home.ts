/**
 * Feature: buddy. Where bon lives when it has nothing to do (Adrian, Nov 24: "bon should always be open ... if you
 * click on bon then you can ask him or talk to him and then he moves around"). He saw it in the bottom right corner
 * first ("it should be somewhere else"), then six places side by side, and picked under the island.
 *
 *   island   bon hangs just under the island, to its right: always there, full size, next to the thing every other
 *            surface comes out of. A click on it wakes it: its bubble opens with Ask (the ask field) and how to talk to
 *            it (push to talk). Its trips start and end here. When the island grows into a card, bon moves along its
 *            right edge so it never sits on the card (islandSide). The default.
 *   corner   the bottom right corner of the screen; and four more places on the screen, kept for the stage.
 *   notch    as before: bon is tucked in the island and only comes out to point or when it is talked to.
 *
 * Pure (no React, no DOM beyond localStorage), so test/buddyHome.test.ts runs it in node.
 * The pick is kept in localStorage `miyagi.buddy.home` until Prefs has a field for it (brief: Core requests); the
 * browser stage's ?bonhome=<place> shows any of them.
 */
import { create } from 'zustand'
import type { Point, Rect } from '../../core/geometry'

/**
 * On the screen: 'corner' (bottom right), 'bottom-left', 'top-right', 'top-left' (under the menu bar), 'right' (half way
 * down the right edge) and 'island' (hanging just under the island, to its right). Or 'notch': tucked in the island.
 * Places to try in the stage while Adrian picks where it lives (Nov 24: "it should be somewhere else").
 */
export type HomePlace = 'corner' | 'bottom-left' | 'top-right' | 'top-left' | 'right' | 'island' | 'notch'
export const HOME_PLACES: readonly HomePlace[] = ['corner', 'bottom-left', 'top-right', 'top-left', 'right', 'island', 'notch']
export const DEFAULT_HOME: HomePlace = 'island'

/**
 * The corner home.
 *   inset   from the right and bottom edges of the work area to bon's center (px): clear of the screen's rounded
 *           corner, and of the Dock when it is on the right (the work area already leaves the Dock out)
 *   hit     the side of the square that takes the click, centered on bon (px): a little more than its body
 */
export const HOME = { inset: 46, hit: 60 } as const

/** bon's center when it is home in the corner of `workArea` (the display without the menu bar and the Dock). */
export function cornerPoint(workArea: Rect): Point {
  return { x: workArea.x + workArea.w - HOME.inset, y: workArea.y + workArea.h - HOME.inset }
}

/**
 * Under the island ('island').
 *   dx    right of the screen's middle, when the island cannot be measured (px): just past a resting pill
 *   dy    under the work area's top edge (px)
 *   gap   from the island's right edge to bon's center (px): half its body, and room for an open island's slanted side
 */
export const BY_ISLAND = { dx: 168, dy: 34, gap: 54 } as const

/**
 * bon's x beside an island whose right edge is at `islandRight` (undefined: not measured). Never left of its resting
 * place, so it does not twitch when the pill shrinks, and never off the work area.
 */
export function islandSide(rest: number, islandRight: number | undefined, workArea: Rect): number {
  const x = islandRight === undefined ? rest : Math.max(rest, islandRight + BY_ISLAND.gap)
  return Math.min(x, workArea.x + workArea.w - HOME.inset)
}

/** bon's center at home for a place on the screen (not 'notch': there it is in the island, Reach.tsx bonsaiPoint). */
export function homePoint(place: HomePlace, workArea: Rect): Point {
  const left = workArea.x + HOME.inset
  const right = workArea.x + workArea.w - HOME.inset
  const top = workArea.y + HOME.inset
  const bottom = workArea.y + workArea.h - HOME.inset
  if (place === 'bottom-left') return { x: left, y: bottom }
  if (place === 'top-right') return { x: right, y: top }
  if (place === 'top-left') return { x: left, y: top }
  if (place === 'right') return { x: right, y: workArea.y + workArea.h / 2 }
  if (place === 'island') return { x: workArea.x + workArea.w / 2 + BY_ISLAND.dx, y: workArea.y + BY_ISLAND.dy }
  return cornerPoint(workArea)
}

const KEY = 'miyagi.buddy.home'
const isPlace = (v: unknown): v is HomePlace => typeof v === 'string' && (HOME_PLACES as readonly string[]).includes(v)

/** The place a stored or typed value means; anything else is the default. */
export function placeFrom(v: unknown): HomePlace {
  return isPlace(v) ? v : DEFAULT_HOME
}

function stored(): HomePlace {
  if (typeof window === 'undefined') return DEFAULT_HOME
  try {
    // The stage only (never the app, which has `tut`): ?bonhome= shows either place.
    const q = 'tut' in window ? null : new URLSearchParams(window.location.search).get('bonhome')
    if (isPlace(q)) return q
    return placeFrom(window.localStorage.getItem(KEY))
  } catch {
    return DEFAULT_HOME
  }
}

export const useHome = create<{ place: HomePlace }>(() => ({ place: stored() }))

/** Move bon's home. Kept for the next launch, and followed by every window (the `storage` event). */
export function setHomePlace(place: HomePlace): void {
  useHome.setState({ place })
  try {
    window.localStorage.setItem(KEY, place)
  } catch {
    /* private mode: the pick lasts for this window */
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) useHome.setState({ place: placeFrom(e.newValue) })
  })
}
