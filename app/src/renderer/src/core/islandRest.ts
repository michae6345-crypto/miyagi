/**
 * What the notch island looks like at rest and how it is drawn, pure (no React, no DOM): the persistent ear, the
 * core cut when the notch is shared, the seam, the shadow, the springs. Tested offline (test/islandRest.test.ts).
 * Island.tsx only turns this plan into elements.
 */
import type { NotchLayout } from '../../../common/notch'
import { EAR_W, NOTCH_RADII, STRIP, notchOf, type NotchView } from './notchGeometry'

type Box = { x: number; y: number; w: number; h: number }

/** The notch shape's springs: opening (a touch of life), closing (critically damped: k=195, c=2*sqrt(k)=27.9), and the hover lean. */
export const NOTCH_SPRING = {
  // Nov 22: the open read as awkward (it overshot and wobbled): stiffer and near-critically damped, so it lands once.
  open: { type: 'spring', stiffness: 300, damping: 32, mass: 1 },
  close: { type: 'spring', stiffness: 195, damping: 28, mass: 1 },
  hover: { type: 'spring', duration: 0.38, bounce: 0.2 }
} as const

/** The lean when the pointer is on a closed island. */
export const HOVER_SCALE = 1.04
/**
 * The soft shadow, only while the island is open or the pointer is on it; never at rest (it would show on the black
 * notch). It falls downward like the pill's and the cards' (theme `shadows`): the even 6 px halo it replaced also spread
 * up and sideways, which drew a grey fringe on a light menu bar around the shape's top corners (MIC-83). One
 * drop-shadow, so the filter costs what it did.
 */
export const NOTCH_SHADOW = 'drop-shadow(0 6px 12px rgb(0 0 0 / 0.36))'
export const shadowFor = (open: boolean, hovering: boolean): string => (open || hovering ? NOTCH_SHADOW : 'none')

/**
 * The resting view of the island in the notch. Words (a line under the notch) win; otherwise the ear shows while the
 * engine is connected, a lesson is loaded, miyagi is thinking or has just landed; only a cold, empty island is bare notch.
 */
export function restViewFor(i: { wantsDrop?: boolean; connected: boolean; lessonLoaded: boolean; thinking?: boolean; landing?: boolean }): NotchView {
  if (i.wantsDrop) return 'drop'
  return i.connected || i.lessonLoaded || i.thinking || i.landing ? 'ears' : 'rest'
}

/** The 1 px seam: inside the window at its very top (never above it), inset by the top radius so it stays within the shape. */
export function seamRect(w: number, rt: number): { top: number; left: number; width: number; height: number } {
  return { top: 0, left: rt, width: Math.max(0, w - 2 * rt), height: STRIP }
}

/** Where the other app's notch core is, in the shape's own coordinates (the shape is centred on the notch). */
export function coreCut(w: number, nm: { width: number; height: number }): { x0: number; x1: number; y1: number } {
  return { x0: w / 2 - nm.width / 2, x1: w / 2 + nm.width / 2, y1: nm.height }
}

/**
 * A CSS `mask` that keeps everything except the notch core band (the top `y1` rows between x0 and x1), so a shared
 * notch has nothing of ours drawn where the other app owns it. Hard stops; `black` is just "opaque".
 */
export const coreMask = (c: { x0: number; x1: number; y1: number }): string => {
  const f = (n: number): string => `${Math.round(n * 100) / 100}px`
  return `linear-gradient(to right, black ${f(c.x0)}, transparent ${f(c.x0)}, transparent ${f(c.x1)}, black ${f(c.x1)}) 0 0 / 100% ${f(c.y1)} no-repeat, linear-gradient(black, black) 0 ${f(c.y1)} / 100% 100% no-repeat`
}

export type IslandPlan = {
  /** Open radii for the peek and cards. */
  radii: { top: number; bottom: number }
  /** Ears the island draws (the persistent ear included), each in the shape's own coordinates; none in the core. */
  ears: { left: Box; right: Box } | undefined
  /** The band nothing is drawn in (a shared notch), else undefined. */
  cut: { x0: number; x1: number; y1: number } | undefined
  seam: { top: number; left: number; width: number; height: number }
  shadow: string
}

/** The plan for a shape of size w x h in the notch `nm`. `coexist`: another notch app shares it. */
export function islandPlan(i: { nm: { width: number; height: number }; coexist: boolean; view: NotchView; open: boolean; hovering: boolean; w: number; h: number }): IslandPlan {
  const radii = i.open ? NOTCH_RADII.open : NOTCH_RADII.closed
  const hasEars = i.view === 'ears' || i.view === 'ears+drop'
  const x0 = i.w / 2 - i.nm.width / 2
  const x1 = i.w / 2 + i.nm.width / 2
  return {
    radii,
    ears: hasEars ? { left: { x: x0 - EAR_W, y: 0, w: EAR_W, h: i.nm.height }, right: { x: x1, y: 0, w: EAR_W, h: i.nm.height } } : undefined,
    cut: i.coexist ? coreCut(i.w, i.nm) : undefined,
    seam: seamRect(i.w, radii.top),
    shadow: shadowFor(i.open, i.hovering)
  }
}

/** Another notch app is present (layout.notch.coexist, set by main). Only ever a layout flag; never shown. */
export const coexistOf = (n: unknown): boolean => (n as { coexist?: unknown } | undefined)?.coexist === true

/** Sharing the notch only means something when the island is in it: a pill below the bar has nothing to share. */
export const coexistIn = (nm: NotchLayout | undefined, layoutNotch: unknown): boolean => !!nm && coexistOf(layoutNotch)

/**
 * The notch to draw: the layout's, or, when the layout momentarily has no usable notch on a display that has one (full
 * screen, a display change), the last good one. So the island never collapses to nothing on a notched display.
 */
export function stickyNotch(layout: { notch?: NotchLayout } | undefined, last: NotchLayout | undefined): NotchLayout | undefined {
  const now = notchOf(layout)
  if (now) return now
  const n = layout?.notch
  return n && n.hasNotch && n.place === 'notch' ? last : undefined
}
