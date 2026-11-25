/**
 * Feature: buddy. Where bon lives when it has nothing to do (Adrian, Nov 24: "bon should always be open on the corner
 * ... if you click on bon then you can ask him or talk to him and then he moves around").
 *
 *   corner   bon sits in the bottom right corner of the screen, always there, full size. A click on it wakes it: its
 *            bubble opens with Ask (the ask field) and how to talk to it (push to talk). Its trips start and end here.
 *            The default.
 *   notch    as before: bon is tucked in the island and only comes out to point or when it is talked to.
 *
 * Pure (no React, no DOM beyond localStorage), so test/buddyHome.test.ts runs it in node.
 * The pick is kept in localStorage `miyagi.buddy.home` until Prefs has a field for it (brief: Core requests); the
 * browser stage's ?bonhome=notch|corner shows either.
 */
import { create } from 'zustand'
import type { Point, Rect } from '../../core/geometry'

export type HomePlace = 'corner' | 'notch'
export const HOME_PLACES: readonly HomePlace[] = ['corner', 'notch']
export const DEFAULT_HOME: HomePlace = 'corner'

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

const KEY = 'miyagi.buddy.home'
const isPlace = (v: unknown): v is HomePlace => v === 'corner' || v === 'notch'

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
